"""
LLM client for the RAG pipeline. No LLM provider exists in the repo
(Checkpoint 0), so this is new. Provider is selected via LLM_PROVIDER env var
so a different provider can be added without touching the rest of the
pipeline. No API keys are hardcoded - each client resolves credentials from
its own env var (ANTHROPIC_API_KEY / TOGETHER_API_KEY / LLM_API_KEY).

Four providers, all behind the same one-method `LLMClient` protocol:

| LLM_PROVIDER | Client | Needs |
|---|---|---|
| `groq` | OpenAICompatibleLLMClient | a free Groq key |
| `ollama` | OpenAICompatibleLLMClient | Ollama running locally, no key |
| `openai_compatible` | OpenAICompatibleLLMClient | LLM_BASE_URL + LLM_API_KEY |
| `together` (default) | TogetherLLMClient | TOGETHER_API_KEY |
| `anthropic` | AnthropicLLMClient | ANTHROPIC_API_KEY |

`groq` and `ollama` are the same client as `openai_compatible` with the base
URL and a default model filled in, because those two are the ones people
actually type and getting a base URL slightly wrong is a confusing failure.

**Env is resolved when a client is constructed, not when this module is
imported.** That distinction was a real bug: the module used to read
`os.getenv("LLM_MODEL")` at import time, and `.env` is not loaded until
`Neo4jKGClient.from_env()` runs, which is after `import rag.llm_client` in both
`run_query.py` and `api/main.py`. So `LLM_MODEL` in `.env` was silently
ignored and the hardcoded default was used instead. `get_llm_client()` now
calls `load_dotenv()` itself, so the LLM side no longer depends on the KG side
having run first.

Model note, kept for the record: Qwen/Qwen3-30B-A3B was the originally
requested model, but every Qwen3 variant on the Together account used here
requires a paid dedicated endpoint (confirmed via live API calls - all return
"non-serverless model"; a plain Llama-3.3-70B-Instruct-Turbo call succeeded on
the same key, so this is a Qwen3-specific availability gap, not a broken key or
broken code).
"""

import os
from typing import Protocol

from dotenv import load_dotenv

DEFAULT_TOGETHER_MODEL = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_MAX_TOKENS = 4096

# --- OpenAI-compatible presets ----------------------------------------------
#
# Anything that speaks the OpenAI chat-completions API can be used, which is
# most things: Groq, Ollama, llama.cpp's server, vLLM, LM Studio, OpenRouter,
# Together's own OpenAI-compatible endpoint. The two presets below exist only
# so that the common cases need three lines of .env instead of four.
#
# Groq: openai/gpt-oss-120b, chosen by asking a real free key what it can
# call rather than by reading the model table. The Llama models are listed on
# Groq's docs page but tagged "Enterprise", and a free key gets
# `404 model_not_found` for llama-3.3-70b-versatile and llama-3.1-8b-instant
# alike - which is exactly the error this default was picked to avoid. What a
# free key does carry: openai/gpt-oss-120b, openai/gpt-oss-20b (both ~1 s for
# a query this size) and qwen/qwen3.8-27b. gpt-oss-120b is the strongest of
# the three and, per Groq's docs, one of only three models there supporting
# strict structured output - so JSON mode is on firmer ground than it was with
# Llama, where only best-effort json_object mode was available.
#
# JSON object mode requires the prompt to ask for JSON explicitly, which
# rag/prompt_builder.py already does.
#
# Ollama: qwen2.5:3b is ~1.9 GB and answers on a CPU laptop. It is a 3B model
# being asked for strict JSON, so expect a weaker result than Groq - see the
# note in rag/README.md. llama3.2:3b and qwen3:1.7b are the obvious
# alternatives if it is too slow or too loose.

_PRESETS: dict[str, dict[str, str | bool]] = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "openai/gpt-oss-120b",
        "needs_key": True,
    },
    "ollama": {
        # Ollama requires an api_key field and ignores its value.
        "base_url": "http://localhost:11434/v1",
        "model": "qwen2.5:3b",
        "needs_key": False,
        "placeholder_key": "ollama",
    },
}


class LLMClient(Protocol):
    def generate(self, system_prompt: str, user_message: str, json_mode: bool = False) -> str: ...


class OpenAICompatibleLLMClient:
    """Any endpoint that speaks the OpenAI chat-completions API.

    Reads `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL`. A `preset`
    ("groq" / "ollama") supplies the base URL and a default model, and an
    explicit env var always wins over the preset so a preset can be pointed
    somewhere else without code changes.
    """

    def __init__(
        self,
        preset: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
    ):
        from openai import OpenAI

        defaults = _PRESETS.get(preset or "", {})
        self.base_url = base_url or os.getenv("LLM_BASE_URL") or defaults.get("base_url")
        if not self.base_url:
            raise RuntimeError(
                "LLM_BASE_URL must be set for LLM_PROVIDER=openai_compatible "
                "(for example https://api.groq.com/openai/v1 for Groq, or "
                "http://localhost:11434/v1 for Ollama). Setting LLM_PROVIDER=groq "
                "or LLM_PROVIDER=ollama fills it in for you."
            )

        # With no preset, infer one from the URL so that a bare
        # LLM_PROVIDER=openai_compatible + LLM_BASE_URL still gets a sensible
        # default model instead of failing on a missing LLM_MODEL.
        if not defaults:
            defaults = self._infer_preset(str(self.base_url))

        self._model = model or os.getenv("LLM_MODEL") or defaults.get("model")
        if not self._model:
            raise RuntimeError(
                f"LLM_MODEL must be set for base URL {self.base_url!r} - this endpoint "
                "is not one of the known presets, so there is no default worth guessing."
            )

        resolved_key = api_key or os.getenv("LLM_API_KEY")
        if not resolved_key:
            if defaults.get("needs_key", True):
                raise RuntimeError(
                    f"LLM_API_KEY must be set for {self.base_url}. A Groq key is free: "
                    "https://console.groq.com/keys"
                )
            # A local server wants the field populated and ignores the value.
            resolved_key = str(defaults.get("placeholder_key", "not-needed"))

        self._client = OpenAI(base_url=str(self.base_url), api_key=resolved_key)
        self._max_tokens = max_tokens or int(os.getenv("LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS))
        # Set once a json_mode call has been rejected, so the fallback below
        # costs one failed request per process rather than one per query.
        self._json_mode_unsupported = False

    @staticmethod
    def _infer_preset(base_url: str) -> dict[str, str | bool]:
        lowered = base_url.lower()
        for name, preset in _PRESETS.items():
            if name in lowered or str(preset["base_url"]).lower() in lowered:
                return preset
        if "11434" in lowered:                      # Ollama on a non-default host
            return _PRESETS["ollama"]
        return {}

    @property
    def model(self) -> str:
        return str(self._model)

    def _create(self, messages: list[dict], json_mode: bool):
        kwargs: dict = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return self._client.chat.completions.create(
            model=str(self._model),
            max_tokens=self._max_tokens,
            messages=messages,
            **kwargs,
        )

    def _available_models(self) -> list[str]:
        """Model ids this key can actually call, best effort.

        Only used to turn a dead-end error into an actionable one, so every
        failure here is swallowed - a listing that does not work must not
        replace the real error with its own.
        """
        try:
            return sorted(model.id for model in self._client.models.list().data)
        except Exception:
            return []

    def _explain_model_not_found(self, error: Exception) -> RuntimeError:
        """Hosted providers retire model ids, and the raw 404 does not say what
        to use instead. A free Groq key, for instance, cannot call any Llama
        model even though the docs list them."""
        available = self._available_models()
        listing = (
            "Models this key can call: " + ", ".join(available)
            if available
            else "Could not list the available models for this key."
        )
        return RuntimeError(
            f"{self.base_url} rejected model {self._model!r} as not found or not accessible. "
            f"{listing} Set LLM_MODEL in .env to one of those. Original error: {error}"
        )

    @staticmethod
    def _is_model_not_found(error: Exception) -> bool:
        text = str(error).lower()
        return "model_not_found" in text or "does not exist or you do not have access" in text

    def generate(self, system_prompt: str, user_message: str, json_mode: bool = False) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        want_json = json_mode and not self._json_mode_unsupported
        try:
            response = self._create(messages, want_json)
        except Exception as error:
            if self._is_model_not_found(error):
                raise self._explain_model_not_found(error) from error
            # Not every OpenAI-compatible server implements response_format,
            # and the ones that do not reject the whole request rather than
            # ignoring the field. Retrying without it is safe here because the
            # prompt asks for JSON in words too, and response_parser.py never
            # raises on output that is not JSON - it returns
            # confidence="parse_error" with the raw text preserved.
            if not want_json:
                raise
            # Checked above, not here: a model-not-found 404 fails the first
            # call too, and treating that as "this server has no JSON mode"
            # would latch the flag off for the whole process over an unrelated
            # problem - which is what happened before the check was added.
            self._json_mode_unsupported = True
            try:
                response = self._create(messages, False)
            except Exception as retry_error:
                if self._is_model_not_found(retry_error):
                    raise self._explain_model_not_found(retry_error) from retry_error
                raise

        return response.choices[0].message.content or ""


class TogetherLLMClient:
    def __init__(self, model: str | None = None, max_tokens: int | None = None):
        from together import Together

        self._client = Together()  # resolves TOGETHER_API_KEY from env
        self._model = model or os.getenv("LLM_MODEL") or DEFAULT_TOGETHER_MODEL
        self._max_tokens = max_tokens or int(os.getenv("LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS))

    def generate(self, system_prompt: str, user_message: str, json_mode: bool = False) -> str:
        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            **kwargs,
        )
        return response.choices[0].message.content


class AnthropicLLMClient:
    def __init__(self, model: str | None = None, max_tokens: int | None = None):
        import anthropic

        self._client = anthropic.Anthropic()  # resolves credentials from env
        self._model = model or os.getenv("LLM_MODEL") or DEFAULT_ANTHROPIC_MODEL
        self._max_tokens = max_tokens or int(os.getenv("LLM_MAX_TOKENS", DEFAULT_MAX_TOKENS))

    def generate(self, system_prompt: str, user_message: str, json_mode: bool = False) -> str:
        # json_mode is a no-op here: Anthropic's structured-output equivalent
        # is output_config.format, which this pipeline doesn't currently use
        # since prompt-level JSON instructions already suffice for this task.
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


SUPPORTED_PROVIDERS = ("groq", "ollama", "openai_compatible", "together", "anthropic")


def get_llm_client() -> LLMClient:
    """Build the client named by LLM_PROVIDER, reading .env if it has not been read.

    `load_dotenv()` does not overwrite variables already set in the real
    environment, so an explicit `LLM_PROVIDER=... python run_query.py ...` still
    wins over the file.
    """
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "together").strip().lower()

    # The default is still "together" so that an existing setup keeps working,
    # but an unconfigured checkout hitting that default deserves to be pointed
    # at the free options rather than at a missing-credentials error from a
    # paid provider's SDK.
    if not os.getenv("LLM_PROVIDER") and not os.getenv("TOGETHER_API_KEY"):
        raise RuntimeError(
            "No LLM provider configured. LLM_PROVIDER defaults to 'together', which needs a "
            "paid key. Two free options, either of which goes in .env (see .env.example): "
            "LLM_PROVIDER=groq with LLM_API_KEY=<free key from https://console.groq.com/keys>, "
            "or LLM_PROVIDER=ollama with LLM_API_KEY=ollama (after: ollama pull qwen2.5:3b)."
        )

    if provider in _PRESETS:                       # "groq", "ollama"
        return OpenAICompatibleLLMClient(preset=provider)
    if provider in {"openai_compatible", "openai-compatible", "openai"}:
        return OpenAICompatibleLLMClient()
    if provider == "together":
        return TogetherLLMClient()
    if provider == "anthropic":
        return AnthropicLLMClient()
    raise ValueError(
        f"Unsupported LLM_PROVIDER: {provider!r}. Supported: {', '.join(SUPPORTED_PROVIDERS)}"
    )
