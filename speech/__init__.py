"""Speech input for IS-Advisor: an edge layer, like `multilingual/`.

Audio becomes text at the edge and the text pipeline is untouched. Retrieval,
the knowledge graph, the prompt, the LLM and the grounding validator never learn
that a microphone was involved - they receive a string, as they always did.

    audio (file or microphone)
      ↓  record.py            optional: --mic SECONDS, via sounddevice
      ↓  transcribe.py        faster-whisper, `small`, CPU, offline after download
      ↓  notation.py          "आई एस सत्रह सौ छियासी" → "IS 1786", "पच्चीस मिलीमीटर" → "25 mm"
      ↓  reconcile_language   Whisper's guess checked against the transcript's script
      ════════════════════    the existing text pipeline, unchanged
      multilingual.prepare_query → retrieval → KG → LLM → validate → localise

Three things are worth knowing before using it:

* **faster-whisper runs on CTranslate2, not torch**, which is why adding speech
  did not move the torch/numpy/transformers/sentencepiece versions pinned for
  Windows.
* **The transcript is always shown before the results.** Speech recognition is
  the least reliable link in this chain and the only one the user can sanity
  check at a glance, so hiding it would be hiding the thing most likely to be
  wrong.
* **The notation normaliser is where a dictated query is won or lost.** An IS
  number that comes back as "सत्रह सौ छियासी" matches nothing at all; as
  "IS 1786" it is pinned as a citation. See `notation.py`.

No API key, and nothing reaches the network after the model download.
"""

from speech.notation import Normalised, normalise_spoken_notation
from speech.record import MicrophoneUnavailable, record_to_wav
from speech.transcribe import (
    SpeechUnavailable,
    Transcript,
    load_model,
    reconcile_language,
    render_transcript,
    transcribe_file,
)

__all__ = [
    "MicrophoneUnavailable",
    "Normalised",
    "SpeechUnavailable",
    "Transcript",
    "load_model",
    "normalise_spoken_notation",
    "reconcile_language",
    "record_to_wav",
    "render_transcript",
    "transcribe_file",
]


def transcribe(
    audio_path=None,
    mic_seconds: float | None = None,
    language: str | None = None,
) -> Transcript:
    """One call for both input paths: a file, or `mic_seconds` from the microphone.

    The temporary recording is always deleted, including when transcription
    raises - audio of someone talking is not something to leave in the temp
    directory because a run failed.
    """
    if audio_path and mic_seconds:
        raise ValueError("give either an audio file or a microphone duration, not both")
    if not audio_path and not mic_seconds:
        raise ValueError("nothing to transcribe: pass an audio file or a microphone duration")

    if audio_path:
        return transcribe_file(audio_path, language=language)

    recorded = record_to_wav(float(mic_seconds))
    try:
        return transcribe_file(recorded, language=language)
    finally:
        recorded.unlink(missing_ok=True)
