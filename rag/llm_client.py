"""
LLM client for the RAG pipeline. No LLM provider exists in the repo
(Checkpoint 0), so this is new. Provider is selected via LLM_PROVIDER env var
so a different provider can be added later without touching the rest of the
pipeline. No API keys are hardcoded - each client resolves credentials from
its own env var (ANTHROPIC_API_KEY / TOGETHER_API_KEY).

Default provider: Together AI (LLM_PROVIDER=together).

Model note: Qwen/Qwen3-30B-A3B was the originally requested model, but every
Qwen3 variant on this Together account requires a paid dedicated endpoint
(confirmed via live API calls - all return "non-serverless model"; a plain
Llama-3.3-70B-Instruct-Turbo call succeeded on the same key, so this is a
Qwen3-specific availability gap, not a broken key or broken code). Defaulting
to Llama-3.3-70B-Instruct-Turbo, which is confirmed serverless-callable.
Swap back to Qwen3 later by setting LLM_MODEL to your dedicated endpoint id -
no code change needed.
"""

import os
from typing import Protocol

DEFAULT_TOGETHER_MODEL = os.getenv("LLM_MODEL", "meta-llama/Llama-3.3-70B-Instruct-Turbo")
DEFAULT_ANTHROPIC_MODEL = os.getenv("LLM_MODEL", "claude-opus-5")
DEFAULT_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))


class LLMClient(Protocol):
    def generate(self, system_prompt: str, user_message: str, json_mode: bool = False) -> str: ...


class TogetherLLMClient:
    def __init__(self, model: str | None = None, max_tokens: int | None = None):
        from together import Together

        self._client = Together()  # resolves TOGETHER_API_KEY from env
        self._model = model or DEFAULT_TOGETHER_MODEL
        self._max_tokens = max_tokens or DEFAULT_MAX_TOKENS

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
        self._model = model or DEFAULT_ANTHROPIC_MODEL
        self._max_tokens = max_tokens or DEFAULT_MAX_TOKENS

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


def get_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "together").lower()
    if provider == "together":
        return TogetherLLMClient()
    if provider == "anthropic":
        return AnthropicLLMClient()
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider!r}")
