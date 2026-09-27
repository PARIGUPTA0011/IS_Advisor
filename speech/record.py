"""Recording from the microphone, for `--mic SECONDS`.

Kept separate from `transcribe.py` because it is the one part of this layer that
needs hardware, and therefore the one part that fails for reasons nothing else
here can do anything about: no input device, a device the OS will not share, no
PortAudio. `sounddevice` is an optional dependency for exactly that reason -
`--audio FILE` works without it, and the error below says so rather than
reporting a missing module.

A fixed recording window is a deliberate simplification. Voice-activity
detection could stop the recording when the speaker stops, and Whisper's VAD
already trims the trailing silence before transcription, so what a fixed window
costs is a few seconds of the user's patience rather than accuracy.
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

from speech import config


class MicrophoneUnavailable(RuntimeError):
    """No usable input device, or `sounddevice` is not installed."""


def available() -> tuple[bool, str]:
    """Whether microphone capture can be attempted, and why not if it cannot."""
    try:
        import sounddevice
    except Exception as error:
        return False, (
            "microphone capture needs sounddevice: `pip install sounddevice` "
            f"({type(error).__name__}). --audio FILE works without it."
        )
    try:
        devices = sounddevice.query_devices()
    except Exception as error:                       # pragma: no cover - hardware
        return False, f"sounddevice could not list audio devices: {type(error).__name__}: {error}"
    if not any(device.get("max_input_channels", 0) > 0 for device in devices):
        return False, "no audio input device is available to record from"
    return True, ""


def record_to_wav(seconds: float, sample_rate: int | None = None) -> Path:
    """Record `seconds` of mono audio and return the path to a temporary WAV.

    The caller owns the file and should delete it; the CLIs do that in a
    `finally` so an interrupted run does not leave audio in the temp directory.
    """
    if seconds <= 0:
        raise ValueError("--mic needs a positive number of seconds")
    if seconds > config.MAX_MIC_SECONDS:
        raise ValueError(
            f"--mic is capped at {config.MAX_MIC_SECONDS}s "
            f"(IS_ADVISOR_MIC_MAX_SECONDS raises it); asked for {seconds:g}s"
        )

    ok, reason = available()
    if not ok:
        raise MicrophoneUnavailable(reason)

    import sounddevice
    rate = sample_rate or config.SAMPLE_RATE

    try:
        frames = sounddevice.rec(
            int(seconds * rate), samplerate=rate, channels=config.CHANNELS, dtype="int16"
        )
        sounddevice.wait()
    except Exception as error:                       # pragma: no cover - hardware
        raise MicrophoneUnavailable(
            f"recording failed: {type(error).__name__}: {error}"
        ) from error

    handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    handle.close()
    path = Path(handle.name)
    # Written with the stdlib rather than soundfile: 16-bit mono PCM is what was
    # just recorded, and this adds no dependency to write it.
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(config.CHANNELS)
        wav.setsampwidth(2)                          # int16
        wav.setframerate(rate)
        wav.writeframes(frames.tobytes())
    return path
