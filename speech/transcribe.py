"""Audio in, text out - and an honest account of which language that text is in.

This is the speech edge of the pipeline. It sits in exactly the same place the
multilingual layer does: audio becomes text, the text is normalised, and from
there the existing query layer, retrieval, knowledge graph, LLM and grounding
validator run on what they always ran on. Nothing downstream knows a microphone
was involved.

    audio file or microphone
      -> faster_whisper.WhisperModel.transcribe   text + Whisper's language guess
      -> notation.normalise_spoken_notation       "आई एस सत्रह सौ छियासी" -> "IS 1786"
      -> reconcile_language                       Whisper's guess vs our own detector
      ==========================================  the existing text pipeline
      (multilingual.prepare_query -> retrieval -> KG -> LLM -> validate -> localise)

**Why Whisper's language code is not trusted on its own.** Whisper reports the
language it thinks it heard, and for Hindi that is right about the *speech* and
unreliable about the *script*: it transcribes Hindi into Devanagari most of the
time, into Urdu script sometimes (Hindi and Urdu are the same language to an
acoustic model), and into Latin letters occasionally. Those three transcripts
need three different things from the layer downstream, and the transcript itself
says which - so `multilingual.detect` reads the script that actually came back
and that is what decides. Whisper's code is kept as a hint and reported
alongside, and a mismatch between the two is recorded rather than hidden.

`--lang` overrides both, because a caller who names the language knows something
neither the audio nor the transcript can tell us.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

from speech import config
from speech.notation import Normalised, normalise_spoken_notation


@dataclass
class Transcript:
    """What was heard, what it was rewritten to, and in which language."""

    text: str                          # after notation normalisation - what the pipeline uses
    raw_text: str = ""                 # exactly what Whisper returned
    language: str = "eng_Latn"         # FLORES code, after reconciliation
    whisper_language: str | None = None        # Whisper's own guess, ISO-639-1
    whisper_confidence: float | None = None    # Whisper's probability for that guess
    detected_script: str = ""          # what multilingual.detect saw in the transcript
    detection_method: str = ""         # how the final language was decided
    language_mismatch: str = ""        # set when Whisper and the script disagree
    duration: float | None = None      # audio length in seconds, as reported
    notation: Normalised | None = None # what the normaliser rewrote, for display
    engine: str = "faster-whisper"
    note: str = ""                     # why it is empty, when it is empty
    segments: list[tuple[float, float, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.text.strip())

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "raw_text": self.raw_text,
            "language": self.language,
            "whisper_language": self.whisper_language,
            "whisper_confidence": (
                round(self.whisper_confidence, 3) if self.whisper_confidence is not None else None
            ),
            "detected_script": self.detected_script,
            "detection_method": self.detection_method,
            "language_mismatch": self.language_mismatch,
            "duration": round(self.duration, 2) if self.duration else None,
            "notation_changes": self.notation.changes if self.notation else [],
            "engine": self.engine,
            "note": self.note,
        }


class SpeechUnavailable(RuntimeError):
    """faster-whisper is not installed, or the model could not be loaded."""


_model = None
_model_lock = threading.Lock()


def load_model():
    """Load and memoise the Whisper model. Raises SpeechUnavailable, not ImportError."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:      # pragma: no cover - depends on the install
            raise SpeechUnavailable(
                "faster-whisper is not installed. `pip install faster-whisper` - it runs on "
                "CTranslate2, not torch, so it does not disturb the pinned torch/numpy versions."
            ) from error
        try:
            _model = WhisperModel(
                config.MODEL_SIZE,
                device=config.DEVICE,
                compute_type=config.COMPUTE_TYPE,
                download_root=config.DOWNLOAD_ROOT,
            )
        except Exception as error:
            raise SpeechUnavailable(
                f"could not load Whisper {config.MODEL_SIZE} "
                f"({config.DEVICE}/{config.COMPUTE_TYPE}): {type(error).__name__}: {error}"
            ) from error
    return _model


# --- language reconciliation -------------------------------------------------

def reconcile_language(
    text: str, whisper_language: str | None, declared: str | None = None
) -> tuple[str, str, str, str]:
    """Decide the language of a transcript.

    Returns (flores_code, script, method, mismatch_note).

    The order of authority, strongest first:

    1. `declared` - what the caller passed as `--lang`.
    2. The **script of the transcript**, via `multilingual.detect`. This is the
       one that matters for everything downstream: the translator needs the code
       whose script the text is actually in, not the language that was spoken.
    3. Whisper's own guess, as a tie-breaker for Latin-script text, where the
       script says nothing on its own.
    """
    from multilingual import languages
    from multilingual.detect import detect

    if declared:
        resolved = languages.resolve(declared)
        if resolved is not None:
            detection = detect(text)
            return resolved.code, detection.script, "declared", ""

    detection = detect(text)
    whisper_resolved = languages.resolve(whisper_language) if whisper_language else None

    # Non-Latin script: the transcript settles it. Whisper saying "hi" over
    # Urdu-script text does not make the text Devanagari.
    if detection.script not in ("Latin", "") and not detection.romanised:
        mismatch = ""
        if whisper_resolved is not None and whisper_resolved.code != detection.code:
            mismatch = (
                f"Whisper reported {whisper_resolved.name} but the transcript is in "
                f"{detection.script} script, so it is handled as {detection.language.name}"
            )
        return detection.code, detection.script, detection.method, mismatch

    # Latin script. Our own romanised-Indic detection comes first, because
    # Whisper labels romanised Hindi as "hi" and the layer downstream must know
    # it is romanised (it deliberately does not machine-translate that).
    if detection.romanised:
        mismatch = ""
        if whisper_resolved is not None and whisper_resolved.code != detection.code:
            mismatch = (
                f"Whisper reported {whisper_resolved.name}; the transcript is romanised, "
                f"handled as romanised {detection.language.name}"
            )
        return detection.code, detection.script, "romanised", mismatch

    # Plain Latin text: trust Whisper over our function-word tables, which are
    # weakest exactly here.
    if whisper_resolved is not None and whisper_resolved.code != detection.code:
        return (
            whisper_resolved.code,
            detection.script,
            "whisper",
            f"transcript looked like {detection.language.name} to the text detector; "
            f"Whisper's {whisper_resolved.name} used instead",
        )
    return detection.code, detection.script, detection.method or "whisper", ""


# --- transcription -----------------------------------------------------------

def transcribe_file(
    path: str | Path,
    language: str | None = None,
    normalise_notation: bool = True,
) -> Transcript:
    """Transcribe an audio file and return the text the pipeline should use.

    `language` is passed to Whisper as a hint *and* used as the declared output
    language. Omitted, Whisper detects it and `reconcile_language` checks that
    against the transcript's own script.
    """
    audio_path = Path(path)
    if not audio_path.exists():
        raise FileNotFoundError(f"no such audio file: {audio_path}")

    model = load_model()

    # Whisper wants an ISO-639-1 code; our own codes are FLORES-style.
    whisper_hint = None
    if language:
        from multilingual import languages

        resolved = languages.resolve(language)
        whisper_hint = resolved.iso1 if resolved and resolved.iso1 else None

    segments, info = model.transcribe(
        str(audio_path),
        language=whisper_hint,
        beam_size=config.BEAM_SIZE,
        vad_filter=config.USE_VAD,
    )
    # faster-whisper streams segments lazily; this is where the work happens.
    collected = [(segment.start, segment.end, segment.text.strip()) for segment in segments]
    raw_text = " ".join(text for _, _, text in collected if text).strip()

    if not raw_text:
        return Transcript(
            text="", raw_text="", language="eng_Latn",
            whisper_language=getattr(info, "language", None),
            duration=getattr(info, "duration", None),
            note="no speech detected in the audio",
            segments=collected,
        )

    notation = normalise_spoken_notation(raw_text) if normalise_notation else None
    text = notation.text if notation else raw_text

    code, script, method, mismatch = reconcile_language(
        text, getattr(info, "language", None), declared=language
    )

    return Transcript(
        text=text,
        raw_text=raw_text,
        language=code,
        whisper_language=getattr(info, "language", None),
        whisper_confidence=getattr(info, "language_probability", None),
        detected_script=script,
        detection_method=method,
        language_mismatch=mismatch,
        duration=getattr(info, "duration", None),
        notation=notation,
        segments=collected,
    )


def render_transcript(transcript: Transcript) -> str:
    """The block printed before results, so the user can see what was heard."""
    from multilingual import languages

    lines = ["HEARD:"]
    lines.append(f"  transcript : {transcript.raw_text or '(nothing)'}")
    if transcript.notation and transcript.notation.changed:
        # Shown because a wrong rewrite is the failure most likely to send
        # retrieval after the wrong standard, and it is invisible otherwise.
        lines.append(f"  normalised : {transcript.text}")
        lines.append(f"  rewrote    : {transcript.notation.summary()}")
    language = languages.get(transcript.language)
    detail = f"  language   : {language.name} ({transcript.language}) by {transcript.detection_method}"
    if transcript.whisper_language:
        confidence = (
            f" {transcript.whisper_confidence:.2f}" if transcript.whisper_confidence is not None else ""
        )
        detail += f"; Whisper heard {transcript.whisper_language}{confidence}"
    lines.append(detail)
    if transcript.language_mismatch:
        lines.append(f"  note       : {transcript.language_mismatch}")
    if transcript.duration:
        lines.append(f"  audio      : {transcript.duration:.1f}s")
    return "\n".join(lines)
