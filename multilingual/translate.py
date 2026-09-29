"""Machine translation, locally and offline.

Two engines, chosen per language rather than per request:

* **IndicTrans2** (`ai4bharat/indictrans2-*-dist-200M`) for the 22 scheduled
  languages. It is the strongest open model for them, and for Bodo, Dogri,
  Konkani and Santali it is the only option - the installed NLLB-200 tokenizer
  carries no code for those four (probed, not assumed; Manipuri as `mni_Beng`
  *is* carried, which an earlier version of this note got wrong).
* **NLLB-200 distilled** for everything else, and as the fallback if the
  IndicTrans2 checkpoints are not present.

Everything degrades rather than fails. If no model can be loaded - no
checkpoint on disk, no network on first run, `sentencepiece` broken - a
`Translation` still comes back, carrying the original text, `translated=False`
and a `note` saying why. The retrieval pipeline then runs on the untranslated
text, which for Latin-script input is exactly what it did before this layer
existed, and for Indic-script input returns the honest "no candidates" rather
than a crash.

**Romanised input is deliberately not translated.** "TMT sariya Fe500D chahiye"
already retrieves well, because `Semantic_Analysis/data/aliases.csv` carries
exactly those trade names and BM25 matches them as tokens. Feeding it to a
model trained on native script would be trading a measured path for an
unmeasured one. `Translator.to_english` returns it unchanged with
`note="romanised"`.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from . import config, languages, protect
from .detect import Detection, detect, normalise
from .languages import ENGLISH


@dataclass(frozen=True)
class Translation:
    """A translation, and an honest account of how it was produced."""

    text: str                  # the translated text (or the original, if not translated)
    source: str                # FLORES code translated from
    target: str                # FLORES code translated to
    engine: str = "none"       # indictrans2 | nllb | none
    translated: bool = False
    note: str = ""             # why it was not translated, when it was not
    original: str = ""         # what came in, always kept

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "source": self.source,
            "target": self.target,
            "engine": self.engine,
            "translated": self.translated,
            "note": self.note,
        }


class _Backend:
    """Common lazy-loading plumbing. Subclasses own the model specifics."""

    name = "none"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._failed = False
        self._reason = ""

    def available(self) -> bool:
        return not self._failed

    @property
    def reason(self) -> str:
        return self._reason

    def _fail(self, reason: str) -> None:
        self._failed = True
        self._reason = reason
        print(f"! {self.name}: {reason}", file=sys.stderr)

    def _load_seq2seq(self, model_id: str, trust_remote_code: bool = False):
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(
            model_id, trust_remote_code=trust_remote_code
        )
        model = AutoModelForSeq2SeqLM.from_pretrained(
            model_id, trust_remote_code=trust_remote_code
        )
        model = model.to(config.DEVICE).eval()
        return tokenizer, model

    def _generate(self, tokenizer, model, batch: list[str], **generate_kwargs) -> list[str]:
        import torch

        encoded = tokenizer(
            batch, padding=True, truncation=True, max_length=512, return_tensors="pt"
        ).to(config.DEVICE)
        with torch.no_grad():
            output = model.generate(
                **encoded,
                num_beams=config.NUM_BEAMS,
                max_new_tokens=config.MAX_NEW_TOKENS,
                **generate_kwargs,
            )
        return tokenizer.batch_decode(output, skip_special_tokens=True)


class IndicTrans2Backend(_Backend):
    """AI4Bharat IndicTrans2, one checkpoint per direction.

    Preprocessing normally comes from `IndicTransToolkit.IndicProcessor`. When
    that package is not installed, the tags it prepends (`src_lang tgt_lang `)
    are prepended directly instead, which is the part the model actually
    requires; what is lost is script normalisation across Unicode variants,
    and `detect.normalise` already does the NFC half of that. The fallback is
    reported through `note` so a quality question can be traced to it.
    """

    name = "indictrans2"

    def __init__(self) -> None:
        super().__init__()
        self._pairs: dict[str, tuple] = {}
        self._processor = None
        self._processor_checked = False
        self._gate_checked = False
        self._gate_open = False

    def available(self) -> bool:
        """Whether these checkpoints can be reached at all.

        Both are gated on HuggingFace (`gated=auto`), so a machine without a
        token cannot download them. Checking for a token or a local copy first
        turns that from a 401 traceback on every process into one line of
        explanation - it is a configuration state, not an error, and the
        fallback to NLLB is the designed behaviour rather than a failure.
        """
        if self._failed:
            return False
        if self._pairs:
            return True
        if not self._gate_checked:
            self._gate_checked = True
            self._gate_open = self._token_present() or self._cached_locally()
            if not self._gate_open:
                self._reason = (
                    "gated on HuggingFace: no token found and no local copy. Accept the model "
                    "terms and set HF_TOKEN to enable it; NLLB-200 is used until then."
                )
        return self._gate_open

    @staticmethod
    def _token_present() -> bool:
        if os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN"):
            return True
        try:
            from huggingface_hub import get_token

            return bool(get_token())
        except Exception:
            return False

    @staticmethod
    def _cached_locally() -> bool:
        try:
            from huggingface_hub import try_to_load_from_cache

            return any(
                isinstance(try_to_load_from_cache(model_id, "config.json"), str)
                for model_id in (config.INDICTRANS2_INDIC_EN, config.INDICTRANS2_EN_INDIC)
            )
        except Exception:
            return False

    def supports(self, source: str, target: str) -> bool:
        if source == target:
            return False
        if source == ENGLISH:
            return target in languages.INDIC_CODES
        if target == ENGLISH:
            return source in languages.INDIC_CODES
        return False        # Indic-to-Indic would need a third checkpoint

    def _processor_for(self, into_english: bool):
        if self._processor_checked:
            return self._processor
        self._processor_checked = True
        try:
            from IndicTransToolkit.processor import IndicProcessor   # type: ignore

            self._processor = IndicProcessor(inference=True)
        except Exception:
            try:
                from IndicTransToolkit import IndicProcessor          # type: ignore

                self._processor = IndicProcessor(inference=True)
            except Exception:
                self._processor = None
        del into_english
        return self._processor

    def _pair(self, into_english: bool):
        key = "indic-en" if into_english else "en-indic"
        if key in self._pairs:
            return self._pairs[key]
        with self._lock:
            if key in self._pairs:
                return self._pairs[key]
            model_id = (
                config.INDICTRANS2_INDIC_EN if into_english else config.INDICTRANS2_EN_INDIC
            )
            try:
                self._pairs[key] = self._load_seq2seq(model_id, trust_remote_code=True)
            except Exception as error:
                self._fail(f"could not load {model_id}: {type(error).__name__}: {error}")
                raise
            return self._pairs[key]

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        into_english = target == ENGLISH
        tokenizer, model = self._pair(into_english)
        processor = self._processor_for(into_english)

        if processor is not None:
            prepared = processor.preprocess_batch(texts, src_lang=source, tgt_lang=target)
        else:
            prepared = [f"{source} {target} {text}" for text in texts]

        decoded = self._generate(tokenizer, model, prepared)
        if processor is not None:
            decoded = processor.postprocess_batch(decoded, lang=target)
        return [text.strip() for text in decoded]


class NllbBackend(_Backend):
    """NLLB-200 distilled 600M: the fallback, and the non-Indian languages.

    Language support is probed against the loaded tokenizer rather than taken
    from a table, because which codes a checkpoint carries is a property of
    the checkpoint.
    """

    name = "nllb"

    def __init__(self) -> None:
        super().__init__()
        self._loaded: tuple | None = None

    def _load(self):
        if self._loaded is not None:
            return self._loaded
        with self._lock:
            if self._loaded is None:
                try:
                    self._loaded = self._load_seq2seq(config.NLLB_MODEL)
                except Exception as error:
                    self._fail(
                        f"could not load {config.NLLB_MODEL}: {type(error).__name__}: {error}"
                    )
                    raise
        return self._loaded

    def _token_id(self, tokenizer, code: str) -> int | None:
        token_id = tokenizer.convert_tokens_to_ids(code)
        unknown = getattr(tokenizer, "unk_token_id", None)
        if token_id is None or token_id == unknown:
            return None
        return token_id

    def supports(self, source: str, target: str) -> bool:
        if source == target or not self.available():
            return False
        try:
            tokenizer, _ = self._load()
        except Exception:
            return False
        return (
            self._token_id(tokenizer, source) is not None
            and self._token_id(tokenizer, target) is not None
        )

    def translate(self, texts: list[str], source: str, target: str) -> list[str]:
        tokenizer, model = self._load()
        tokenizer.src_lang = source
        target_id = self._token_id(tokenizer, target)
        if target_id is None:
            raise ValueError(f"{config.NLLB_MODEL} does not carry the language code {target!r}")
        decoded = self._generate(tokenizer, model, texts, forced_bos_token_id=target_id)
        return [text.strip() for text in decoded]


class Translator:
    """The facade the rest of the repo uses. One instance per process is enough.

    Backends are constructed eagerly (cheap - no weights are touched) and
    loaded lazily on the first sentence that needs them.
    """

    def __init__(self, enabled: bool | None = None):
        self.enabled = config.TRANSLATION_ENABLED if enabled is None else enabled
        self._indictrans2 = IndicTrans2Backend()
        self._nllb = NllbBackend()
        self._cache: OrderedDict[tuple[str, str, str], str] = OrderedDict()

    # --- plumbing ----------------------------------------------------------

    def _backends_for(self, source: str, target: str) -> list:
        ordered = []
        if self._indictrans2.available() and self._indictrans2.supports(source, target):
            ordered.append(self._indictrans2)
        if self._nllb.available():
            ordered.append(self._nllb)
        return ordered

    def _cached(self, text: str, source: str, target: str) -> str | None:
        key = (text, source, target)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def _store(self, text: str, source: str, target: str, result: str) -> None:
        self._cache[(text, source, target)] = result
        while len(self._cache) > config.CACHE_SIZE:
            self._cache.popitem(last=False)

    def _translate_one(self, text: str, source: str, target: str) -> tuple[str, str, str]:
        """Returns (text, engine, note). Never raises."""
        cached = self._cached(text, source, target)
        if cached is not None:
            return cached, "cache", ""

        last_note = "no translation backend is available"
        for backend in self._backends_for(source, target):
            if backend is self._nllb and not backend.supports(source, target):
                # backend.reason carries the real cause when the checkpoint
                # could not be loaded at all - a broken torch install, say.
                # Reporting "does not carry hin_Deva -> eng_Latn" for a DLL
                # failure sends the reader after the wrong problem.
                last_note = backend.reason or (
                    f"{config.NLLB_MODEL} does not carry {source} -> {target}"
                )
                continue
            try:
                result = backend.translate([text], source, target)[0]
            except Exception as error:
                last_note = f"{backend.name} failed: {type(error).__name__}: {error}"
                continue
            if result:
                self._store(text, source, target, result)
                return result, backend.name, ""
            last_note = f"{backend.name} returned an empty string"
        return text, "none", last_note

    # --- the two directions -------------------------------------------------

    def _classify(
        self, text: str, source: str | None
    ) -> tuple["Translation | None", str, "protect.Protected | None"]:
        """Decide what needs a model, without loading one.

        Returns either a finished `Translation` (nothing to translate, for one
        of several honest reasons) or the source code plus the lifted text a
        model should see. Both the single and the batch path go through here,
        so the reasons a query is left alone are stated in exactly one place.
        """
        original = text or ""
        detection = detect(original, declared=source) if source is None else None
        code = languages.get(source).code if source else detection.code
        normalised = normalise(original)

        if code == ENGLISH:
            return (
                Translation(normalised, ENGLISH, ENGLISH, "none", False, "already English", original),
                code, None,
            )
        if detection is not None and detection.romanised:
            # Latin script already, and the trade names in it are what the
            # keyword index was built to match. See the module docstring.
            return (
                Translation(normalised, code, ENGLISH, "none", False, "romanised", original),
                code, None,
            )
        if not self.enabled:
            return (
                Translation(normalised, code, ENGLISH, "none", False, "translation disabled", original),
                code, None,
            )

        lifted = protect.lift(normalised)
        if not lifted.text.strip():
            # Nothing but notation - no model needed, and the notation is
            # already in the form retrieval wants.
            return (
                Translation(normalised, code, ENGLISH, "none", True, "notation only", original),
                code, None,
            )
        return None, code, lifted

    def to_english(self, text: str, source: str | None = None) -> Translation:
        """Translate one query into English for retrieval.

        Technical notation is lifted out before the model sees it and appended
        afterwards (see `protect`), so a citation or grade code cannot come
        back reformatted.
        """
        return self.to_english_batch([text], source=source)[0]

    def to_english_batch(self, texts: list[str], source: str | None = None) -> list[Translation]:
        """`to_english` over several line items, one model call per language.

        A tender is many short lines, and a seq2seq model translates a batch of
        them for barely more than the cost of one. `is_advisor.query
        .parse_document` calls this, where the alternative was one model call
        per line item.
        """
        if not texts:
            return []

        results: list[Translation | None] = [None] * len(texts)
        pending: list[tuple[int, protect.Protected, str]] = []

        for index, text in enumerate(texts):
            finished, code, lifted = self._classify(text, source)
            if finished is not None or lifted is None:
                results[index] = finished
            else:
                pending.append((index, lifted, code))

        for code in dict.fromkeys(item[2] for item in pending):
            group = [(index, lifted) for index, lifted, src in pending if src == code]
            outputs, engine, note = self._translate_batch(
                [lifted.text for _, lifted in group], code, ENGLISH
            )
            for (index, lifted), output in zip(group, outputs):
                original = texts[index] or ""
                if engine == "none":
                    results[index] = Translation(
                        normalise(original), code, ENGLISH, "none", False, note, original
                    )
                else:
                    results[index] = Translation(
                        protect.reattach(output, lifted), code, ENGLISH, engine, True, "", original
                    )

        return [result for result in results if result is not None]

    def from_english(self, text: str, target: str | None) -> Translation:
        """Translate English output into the reader's language.

        Notation is masked with placeholders rather than lifted, because word
        order matters in prose. Two things can go wrong with a placeholder, and
        both are handled - see `_resolve_masked`.
        """
        original = text or ""
        target_code = languages.get(target).code
        if target_code == ENGLISH or not original.strip():
            return Translation(original, ENGLISH, ENGLISH, "none", False, "target is English", original)
        if not self.enabled:
            return Translation(original, ENGLISH, target_code, "none", False, "translation disabled", original)

        masked = protect.mask(original)
        translated, engine, note = self._translate_one(masked.text, ENGLISH, target_code)
        if engine == "none":
            return Translation(original, ENGLISH, target_code, "none", False, note, original)

        text_out, note_out, engine_out = self._resolve_masked(
            original, masked, translated, engine, target_code
        )
        return Translation(text_out, ENGLISH, target_code, engine_out, True, note_out, original)

    def _resolve_masked(
        self, original: str, masked: protect.Protected, translated: str,
        engine: str, target_code: str, retry: str | None = None,
    ) -> tuple[str, str, str]:
        """Turn a translated masked sentence back into a usable one.

        A placeholder can fail two ways, and the second one is not theoretical:
        NLLB-200 **transliterates** a sentence-initial placeholder into the
        target script, so `PLHA` comes back as `पीलहेऐ`. Tolerant matching
        cannot find that, and the IS number it stood for would be lost from the
        middle of the sentence.

        So when anything is missing, the sentence is translated a second time
        with the real notation left inline, and whichever attempt keeps more of
        the notation wins. Handing the model `IS 1786:2008` directly usually
        works - it copies Latin-script technical tokens - and the risk it was
        masked against (a reformatted `IS 1,786`) is checked for rather than
        assumed away: a value only counts as kept if it appears verbatim.
        """
        restored, missing = protect.unmask(translated, masked)
        if not missing:
            return restored, "", engine

        if retry is None:
            retry, retry_engine, _ = self._translate_one(original, ENGLISH, target_code)
            if retry_engine == "none":
                retry = ""
            else:
                engine = retry_engine
        if retry:
            lost = [value for value in masked.values if value not in retry]
            if len(lost) < len(missing):
                if lost:
                    retry = f"{retry} ({', '.join(lost)})"
                return (
                    retry,
                    "notation left inline after the model did not return a placeholder",
                    engine,
                )

        return (
            f"{restored} ({', '.join(missing)})",
            f"{len(missing)} placeholder(s) reattached at the end",
            engine,
        )

    def _translate_batch(
        self, texts: list[str], source: str, target: str
    ) -> tuple[list[str], str, str]:
        """One model call per batch of strings. Returns (texts, engine, note)."""
        cached = [self._cached(text, source, target) for text in texts]
        if texts and all(item is not None for item in cached):
            return [item for item in cached if item is not None], "cache", ""

        last_note = "no translation backend is available"
        for backend in self._backends_for(source, target):
            if backend is self._nllb and not backend.supports(source, target):
                # backend.reason carries the real cause when the checkpoint
                # could not be loaded at all - a broken torch install, say.
                # Reporting "does not carry hin_Deva -> eng_Latn" for a DLL
                # failure sends the reader after the wrong problem.
                last_note = backend.reason or (
                    f"{config.NLLB_MODEL} does not carry {source} -> {target}"
                )
                continue
            try:
                outputs: list[str] = []
                for begin in range(0, len(texts), config.BATCH_SIZE):
                    chunk = texts[begin : begin + config.BATCH_SIZE]
                    outputs.extend(backend.translate(chunk, source, target))
            except Exception as error:
                last_note = f"{backend.name} failed: {type(error).__name__}: {error}"
                continue
            if len(outputs) == len(texts):
                # A model can legitimately return "" for one string in an
                # otherwise-good batch (seen with very short/placeholder-only
                # inputs like "STEP {{step}}" into Korean) - that one string
                # falls back to its own English text rather than discarding
                # every other translation the batch got right.
                resolved = [output if output else text for text, output in zip(texts, outputs)]
                for text, output in zip(texts, resolved):
                    self._store(text, source, target, output)
                return resolved, backend.name, ""
            last_note = f"{backend.name} returned {len(outputs)} outputs for {len(texts)} inputs"
        return list(texts), "none", last_note


    def batch_from_english(self, texts: list[str], target: str | None) -> list[Translation]:
        """`from_english` over a list, in one model call.

        This is what makes a localised response affordable. A single answer
        carries a dozen short strings - five `why` lines, five title glosses, a
        tier name, a citation note - and one model call for all of them costs a
        fraction of twelve calls. Masking is deterministic, so every string
        translated here is also a cache hit for the later per-field
        `from_english` call that formats it.
        """
        target_code = languages.get(target).code
        if target_code == ENGLISH or not self.enabled:
            return [self.from_english(text, target) for text in texts]

        masked = [protect.mask(text or "") for text in texts]
        translatable = [
            index for index, item in enumerate(masked) if (texts[index] or "").strip()
        ]
        outputs, engine, note = self._translate_batch(
            [masked[index].text for index in translatable], ENGLISH, target_code
        )
        by_index = dict(zip(translatable, outputs))

        # One extra batched call for the sentences that lost a placeholder, and
        # only those. See _resolve_masked for why a second attempt exists.
        needs_retry = [
            index for index in translatable
            if engine != "none" and protect.unmask(by_index[index], masked[index])[1]
        ]
        retries: dict[int, str] = {}
        if needs_retry:
            retry_outputs, retry_engine, _ = self._translate_batch(
                [texts[index] or "" for index in needs_retry], ENGLISH, target_code
            )
            if retry_engine != "none":
                retries = dict(zip(needs_retry, retry_outputs))

        results: list[Translation] = []
        for index, text in enumerate(texts):
            original = text or ""
            if index not in by_index or engine == "none":
                results.append(
                    Translation(original, ENGLISH, target_code, "none", False,
                                note if index in by_index else "empty string", original)
                )
                continue
            text_out, note_out, engine_out = self._resolve_masked(
                original, masked[index], by_index[index], engine, target_code,
                retry=retries.get(index, "" if index in needs_retry else None),
            )
            results.append(
                Translation(text_out, ENGLISH, target_code, engine_out, True, note_out, original)
            )
        return results

    # --- reporting ----------------------------------------------------------

    def status(self) -> dict:
        return {
            "enabled": self.enabled,
            "indictrans2": {
                "available": self._indictrans2.available(),
                "reason": self._indictrans2.reason,
                "models": [config.INDICTRANS2_INDIC_EN, config.INDICTRANS2_EN_INDIC],
            },
            "nllb": {
                "available": self._nllb.available(),
                "reason": self._nllb.reason,
                "model": config.NLLB_MODEL,
            },
            "cached_strings": len(self._cache),
        }


_DEFAULT: Translator | None = None

# Set by warm_up() at server startup, read by GET /health so a caller can tell
# "still loading the model" apart from "loaded and ready" apart from "never
# attempted" - the three states get_translator().status() alone cannot
# distinguish, because its "available" flag defaults to True until a load has
# actually FAILED, not until one has actually SUCCEEDED.
WARMUP_STATUS: dict = {"state": "not_started", "elapsed_s": None, "detail": ""}


def warm_up(sample_language: str = "hin_Deva", sample_text: str = "नमस्ते") -> dict:
    """Force the translation backend to load now, synchronously, instead of on
    whatever request happens to arrive first.

    This is the fix for a real bug: without it, the FIRST non-English request
    after every server start (or every `--reload` restart) pays the full
    2.5GB NLLB load cost - measured at ~20s on this machine - *inside* that
    user's request/response cycle, on top of retrieval and the LLM call. A
    slow first request looks indistinguishable from a broken one, and if the
    combined total creeps past the frontend's timeout, the user sees a
    timeout on every attempt if they keep hitting the same cold path (e.g.
    after each `--reload` restart during development).

    Call this once, at startup, via multilingual.warmup.warm_up_in_background()
    when the server has an event loop to run it on, or directly (as here) when
    it does not. Updates and returns WARMUP_STATUS; never raises - a failed
    warm-up is reported, not fatal, because English queries never need
    translation at all and should keep working regardless.
    """
    started = time.time()
    WARMUP_STATUS.update(state="loading", elapsed_s=None, detail="")
    try:
        translator = get_translator()
        if not translator.enabled:
            WARMUP_STATUS.update(state="disabled", elapsed_s=0.0, detail="translation disabled (IS_ADVISOR_TRANSLATE=0)")
            return dict(WARMUP_STATUS)
        inbound = translator.to_english(sample_text, source=sample_language)
        outbound = translator.from_english("language support", target=sample_language)
        elapsed = time.time() - started
        if inbound.translated and outbound.translated:
            WARMUP_STATUS.update(
                state="ready", elapsed_s=round(elapsed, 1),
                detail=f"translation directions loaded in {elapsed:.1f}s",
            )
            print(f"[warmup] translation directions ready in {elapsed:.1f}s", flush=True)
        else:
            notes = [item.note for item in (inbound, outbound) if not item.translated and item.note]
            detail = "; ".join(notes) or "one or more translation directions are unavailable"
            WARMUP_STATUS.update(
                state="failed", elapsed_s=round(elapsed, 1),
                detail=detail,
            )
            print(f"! [warmup] translation warm-up did not succeed: {detail}", flush=True)
    except Exception as error:
        elapsed = time.time() - started
        WARMUP_STATUS.update(state="failed", elapsed_s=round(elapsed, 1), detail=f"{type(error).__name__}: {error}")
        print(f"! [warmup] translation warm-up raised {type(error).__name__}: {error}", flush=True)
    return dict(WARMUP_STATUS)


def get_translator() -> Translator:
    """Process-wide translator. Loading two MT checkpoints per request would
    dominate the latency of everything else in the pipeline."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Translator()
    return _DEFAULT


def detect_and_translate(text: str, declared: str | None = None) -> tuple[Detection, Translation]:
    """Detect the language of `text` and translate it into English."""
    detection = detect(text, declared)
    translator = get_translator()
    if detection.romanised or detection.code == ENGLISH:
        # to_english's own detection would repeat the work; pass the verdict in.
        translation = Translation(
            normalise(text), detection.code, ENGLISH, "none", False,
            "romanised" if detection.romanised else "already English", text or "",
        )
        return detection, translation
    return detection, translator.to_english(text, source=detection.code)
