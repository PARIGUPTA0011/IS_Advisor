"""Settings for the speech layer. Every one is an env override.

Sizes, so the disk cost is not a surprise: the `small` model is about 460 MB as
a CTranslate2 int8 conversion, downloaded once from HuggingFace on first use and
cached like every other model here. Nothing reaches the network after that.

`small` is the size this layer asks for because the request did, and because it
is the largest of the Whisper sizes that still answers in seconds rather than
minutes on a CPU laptop. `base` and `tiny` are faster and worse; `medium` and
`large-v3` are better and slow enough on CPU to be unusable for an interactive
query. None of those trade-offs have been measured on Indian procurement speech
here - see the README section.
"""

from __future__ import annotations

import os

# faster-whisper runs on CTranslate2, not torch, which is why adding it does not
# disturb the torch/numpy/transformers versions pinned for Windows.
MODEL_SIZE = os.getenv("IS_ADVISOR_WHISPER_MODEL", "small")

# int8 on CPU: roughly 4x less memory and noticeably faster than float32, at a
# quality cost that is real but small for this model size. float32 is available
# for anyone who wants to compare - no other code changes.
COMPUTE_TYPE = os.getenv("IS_ADVISOR_WHISPER_COMPUTE", "int8")
DEVICE = os.getenv("IS_ADVISOR_WHISPER_DEVICE", "cpu")

# Whisper's own default is 5. Greedy (1) is faster and measurably worse at
# numbers, which are the part of a procurement query that must not be wrong.
BEAM_SIZE = int(os.getenv("IS_ADVISOR_WHISPER_BEAMS", "5"))

# Voice-activity detection would trim silence before transcription, which helps
# most on microphone input where the recording window is fixed and the speaker
# finishes early. It is **off by default because it segfaults here**: VAD is the
# one part of faster-whisper that runs through onnxruntime, and on this machine
# (Windows, Python 3.11, Ryzen 5 5500U) loading it kills the process - no
# exception, exit code 139. Transcription itself is unaffected, so the cost of
# leaving it off is a few seconds of silence being transcribed as nothing.
# Set IS_ADVISOR_WHISPER_VAD=1 to try it on a machine where onnxruntime behaves.
USE_VAD = (os.getenv("IS_ADVISOR_WHISPER_VAD", "0") or "").strip().lower() in {"1", "true", "yes", "on"}

# Where the model is cached. None means HuggingFace's default location, shared
# with the translation checkpoints.
DOWNLOAD_ROOT = os.getenv("IS_ADVISOR_WHISPER_CACHE") or None

# Extensions the CLI flags accept. faster-whisper decodes via PyAV, so anything
# ffmpeg can read works - this list is what is claimed and tested, not a limit
# imposed by the decoder.
SUPPORTED_AUDIO_SUFFIXES = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".webm")

# Microphone capture settings. 16 kHz mono is what Whisper resamples to anyway,
# so recording at that rate avoids a conversion.
SAMPLE_RATE = int(os.getenv("IS_ADVISOR_MIC_RATE", "16000"))
CHANNELS = 1
MAX_MIC_SECONDS = int(os.getenv("IS_ADVISOR_MIC_MAX_SECONDS", "120"))
