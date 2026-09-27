"""Tests for LLM provider selection and the OpenAI-compatible client.

    python tests/test_llm_providers.py

No API key and no network. Provider resolution is checked directly, and the
request/response path is checked against a mock OpenAI-compatible server
running on localhost - which is exactly what Ollama is from the client's point
of view, so this exercises the real code path rather than a stub of it.

What these cover, in order of how likely each is to break someone's setup:

1. `LLM_PROVIDER=groq` / `=ollama` resolve to the right base URL and model.
2. Ollama needs no key; Groq says so clearly when the key is missing.
3. `LLM_MODEL` from the environment beats the preset default (this was a real
   bug - the module used to read it at import time, before .env was loaded).
4. A server that rejects `response_format` still gets an answer, because the
   client retries without it.
"""

from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag import llm_client  # noqa: E402
from rag.llm_client import (  # noqa: E402
    AnthropicLLMClient,
    OpenAICompatibleLLMClient,
    TogetherLLMClient,
    get_llm_client,
)

FAILURES: list[str] = []


def check(label: str, got, expected) -> None:
    if got == expected:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label}\n          got      {got!r}\n          expected {expected!r}")
        FAILURES.append(label)


class _Handler(BaseHTTPRequestHandler):
    """Minimal /v1/chat/completions. `reject_json_mode` mimics a server that
    does not implement response_format and 400s the whole request."""

    reject_json_mode = False
    received: list[dict] = []

    def do_POST(self) -> None:                                  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        type(self).received.append({
            "path": self.path,
            "authorization": self.headers.get("Authorization", ""),
            "body": payload,
        })

        if type(self).reject_json_mode and "response_format" in payload:
            body = json.dumps({"error": {"message": "response_format is not supported"}})
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())
            return

        content = '{"direct_recommendations": [], "warnings": [], "confidence": "insufficient_evidence"}'
        body = json.dumps({
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": payload.get("model", "mock"),
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args) -> None:                       # keep test output clean
        return


class MockServer:
    def __enter__(self) -> "MockServer":
        _Handler.received = []
        _Handler.reject_json_mode = False
        self._server = HTTPServer(("127.0.0.1", 0), _Handler)
        self.base_url = f"http://127.0.0.1:{self._server.server_port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()

    @property
    def requests(self) -> list[dict]:
        return _Handler.received


def with_env(**overrides):
    """Run a test with exactly these LLM_* variables set, and no real .env.

    `get_llm_client()` calls `load_dotenv()`, which would otherwise read the
    developer's own `.env` and make every assertion below depend on what
    happens to be in it - a suite that passes today and fails the moment
    someone adds their Groq key is worse than no suite. So the loader is
    stubbed out for these tests, and `test_reads_dotenv` checks separately
    that it really is called.
    """
    def decorator(function):
        def wrapper():
            managed = ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_MAX_TOKENS")
            saved = {key: os.environ.get(key) for key in managed}
            real_loader = llm_client.load_dotenv
            for key in managed:
                os.environ.pop(key, None)
            os.environ.update({k: v for k, v in overrides.items() if v is not None})
            llm_client.load_dotenv = lambda *a, **k: False
            try:
                function()
            finally:
                llm_client.load_dotenv = real_loader
                for key, value in saved.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value
        return wrapper
    return decorator


def test_reads_dotenv() -> None:
    print(".env is read by the factory")
    # The LLM side used to depend on Neo4jKGClient.from_env() having run first,
    # because that was the only caller of load_dotenv(). Anyone testing the LLM
    # on its own got the hardcoded defaults instead of their .env.
    calls: list[bool] = []
    real_loader = llm_client.load_dotenv
    saved = os.environ.get("LLM_PROVIDER")
    llm_client.load_dotenv = lambda *a, **k: calls.append(True)
    os.environ["LLM_PROVIDER"] = "definitely-not-a-provider"
    try:
        try:
            llm_client.get_llm_client()
        except ValueError:
            pass
        check("load_dotenv called before resolving the provider", calls, [True])
    finally:
        llm_client.load_dotenv = real_loader
        if saved is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = saved


# --- provider resolution -----------------------------------------------------

@with_env(LLM_PROVIDER="groq", LLM_API_KEY="gsk_test_key_not_real")
def test_groq_preset() -> None:
    print("groq preset")
    client = get_llm_client()
    check("client type", type(client).__name__, "OpenAICompatibleLLMClient")
    check("base url filled in", str(client.base_url), "https://api.groq.com/openai/v1")
    check("default model", client.model, "openai/gpt-oss-120b")


@with_env(LLM_PROVIDER="ollama")
def test_ollama_preset_needs_no_key() -> None:
    print("ollama preset")
    client = get_llm_client()
    check("base url filled in", str(client.base_url), "http://localhost:11434/v1")
    check("default model", client.model, "qwen2.5:3b")


@with_env(LLM_PROVIDER="groq")
def test_groq_without_key_says_so() -> None:
    print("groq without a key")
    try:
        get_llm_client()
    except RuntimeError as error:
        check("names the variable", "LLM_API_KEY" in str(error), True)
        check("points at the free key page", "console.groq.com" in str(error), True)
    else:
        check("missing key is refused", "no error raised", "RuntimeError")


@with_env(LLM_PROVIDER="openai_compatible")
def test_openai_compatible_without_base_url_says_so() -> None:
    print("openai_compatible without a base URL")
    try:
        get_llm_client()
    except RuntimeError as error:
        check("names the variable", "LLM_BASE_URL" in str(error), True)
        check("suggests the presets", "LLM_PROVIDER=groq" in str(error), True)
    else:
        check("missing base URL is refused", "no error raised", "RuntimeError")


@with_env(LLM_PROVIDER="groq", LLM_API_KEY="gsk_test", LLM_MODEL="openai/gpt-oss-20b")
def test_env_model_beats_preset() -> None:
    print("LLM_MODEL overrides the preset")
    # The bug this guards: the module used to read LLM_MODEL at import time,
    # which is before .env is loaded, so the .env value was ignored entirely.
    check("env model wins", get_llm_client().model, "openai/gpt-oss-20b")


@with_env()
def test_unconfigured_checkout_points_at_the_free_options() -> None:
    print("nothing configured at all")
    # LLM_PROVIDER still defaults to "together" for backwards compatibility, so
    # a fresh checkout would otherwise fail inside Together's SDK on a missing
    # key. Naming the two free providers instead is the whole point.
    saved = os.environ.pop("TOGETHER_API_KEY", None)
    try:
        get_llm_client()
    except RuntimeError as error:
        check("mentions groq", "LLM_PROVIDER=groq" in str(error), True)
        check("mentions ollama", "LLM_PROVIDER=ollama" in str(error), True)
        check("links the free key page", "console.groq.com" in str(error), True)
    else:
        check("unconfigured checkout is refused", "no error raised", "RuntimeError")
    finally:
        if saved is not None:
            os.environ["TOGETHER_API_KEY"] = saved


@with_env(LLM_PROVIDER="unsupported-thing")
def test_unknown_provider_lists_the_supported_ones() -> None:
    print("unknown provider")
    try:
        get_llm_client()
    except ValueError as error:
        check("names the offender", "unsupported-thing" in str(error), True)
        for provider in ("groq", "ollama", "together", "anthropic"):
            check(f"lists {provider}", provider in str(error), True)
    else:
        check("unknown provider is refused", "no error raised", "ValueError")


def test_together_and_anthropic_still_resolve() -> None:
    print("together and anthropic are untouched")
    # Constructed directly, because building them requires their SDKs and keys.
    # What matters here is that the factory still routes to them, and that the
    # protocol they satisfy has not changed.
    for client_class in (TogetherLLMClient, AnthropicLLMClient):
        check(f"{client_class.__name__} has generate", callable(client_class.generate), True)
    import inspect

    from rag import llm_client

    source = inspect.getsource(llm_client.get_llm_client)
    check("factory still routes together", 'provider == "together"' in source, True)
    check("factory still routes anthropic", 'provider == "anthropic"' in source, True)


# --- the request path, against a real local server ---------------------------

def test_request_shape_against_a_local_server() -> None:
    print("request path (mock OpenAI-compatible server)")
    with MockServer() as server:
        client = OpenAICompatibleLLMClient(
            base_url=server.base_url, api_key="test-key", model="mock-model"
        )
        text = client.generate("system rules", "the evidence", json_mode=True)
        check("content returned", json.loads(text)["confidence"], "insufficient_evidence")
        check("one request made", len(server.requests), 1)

        request = server.requests[0]
        check("path", request["path"], "/v1/chat/completions")
        check("key sent as bearer", request["authorization"], "Bearer test-key")
        check("model sent", request["body"]["model"], "mock-model")
        check("json mode requested", request["body"]["response_format"], {"type": "json_object"})
        check("system prompt first", request["body"]["messages"][0]["role"], "system")
        check("system prompt content", request["body"]["messages"][0]["content"], "system rules")
        check("user message second", request["body"]["messages"][1]["content"], "the evidence")


def test_json_mode_fallback() -> None:
    print("server that rejects response_format")
    with MockServer() as server:
        _Handler.reject_json_mode = True
        client = OpenAICompatibleLLMClient(
            base_url=server.base_url, api_key="test-key", model="mock-model"
        )
        text = client.generate("system rules", "the evidence", json_mode=True)
        check("still answers", json.loads(text)["confidence"], "insufficient_evidence")
        check("retried once without json mode", len(server.requests), 2)
        check("first attempt asked for json", "response_format" in server.requests[0]["body"], True)
        check("retry dropped it", "response_format" in server.requests[1]["body"], False)

        # The rejection is remembered, so the next query does not pay for it.
        client.generate("system rules", "more evidence", json_mode=True)
        check("no further failed attempts", len(server.requests), 3)
        check("still no json mode", "response_format" in server.requests[2]["body"], False)


@with_env(LLM_PROVIDER="openai_compatible", LLM_BASE_URL="http://localhost:11434/v1")
def test_bare_openai_compatible_infers_ollama() -> None:
    print("openai_compatible pointed at Ollama")
    # No key and no model set. The Ollama preset is inferred from the base URL,
    # which supplies both - otherwise this combination would fail on a missing
    # LLM_API_KEY for a server that does not want one. No request is made, so
    # Ollama does not have to be running for this.
    client = get_llm_client()
    check("model inferred from the base URL", client.model, "qwen2.5:3b")
    check("base url kept as given", str(client.base_url), "http://localhost:11434/v1")


@with_env(LLM_PROVIDER="openai_compatible", LLM_BASE_URL="https://example.invalid/v1")
def test_unknown_endpoint_demands_a_model() -> None:
    print("openai_compatible pointed somewhere unknown")
    try:
        get_llm_client()
    except RuntimeError as error:
        # An unknown endpoint gets no guessed default - a wrong model id fails
        # at request time with a less obvious message than this one.
        check("names the variable", "LLM_MODEL" in str(error), True)
    else:
        check("missing model is refused", "no error raised", "RuntimeError")


def main() -> int:
    test_reads_dotenv()
    test_groq_preset()
    test_ollama_preset_needs_no_key()
    test_groq_without_key_says_so()
    test_openai_compatible_without_base_url_says_so()
    test_env_model_beats_preset()
    test_unconfigured_checkout_points_at_the_free_options()
    test_unknown_provider_lists_the_supported_ones()
    test_together_and_anthropic_still_resolve()
    test_request_shape_against_a_local_server()
    test_json_mode_fallback()
    test_bare_openai_compatible_infers_ollama()
    test_unknown_endpoint_demands_a_model()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) failed:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("all LLM provider checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
