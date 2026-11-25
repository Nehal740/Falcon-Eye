"""AI assistant connection: error reasons, token limits, model list and diagnosis (no network)."""

import pytest

httpx = pytest.importorskip("httpx")

import assistant_service as svc  # noqa: E402
from config import settings  # noqa: E402


@pytest.fixture(autouse=True)
def llm_settings(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_api_key", "SECRET-KEY-123")
    monkeypatch.setattr(settings, "llm_model", "gemini-test-flash")
    monkeypatch.setattr(settings, "llm_base_url", "https://generativelanguage.googleapis.com/v1beta/openai")
    monkeypatch.setattr(settings, "llm_max_tokens", 1500)


def response(status, payload, url="https://x.test/"):
    return httpx.Response(status, json=payload, request=httpx.Request("POST", url))


class Recorder:
    def __init__(self, post=None, get=None):
        self.post_calls, self._post, self._get = [], post, get

    def post(self, url, **kw):
        self.post_calls.append((url, kw))
        return self._post(url, kw)

    def get(self, url, **kw):
        return self._get(url, kw)


def install(monkeypatch, post=None, get=None):
    rec = Recorder(post, get)
    monkeypatch.setattr(httpx, "post", rec.post)
    monkeypatch.setattr(httpx, "get", rec.get)
    return rec


GOOD = {"choices": [{"message": {"content": "Hello!"}, "finish_reason": "stop"}]}
MODELS = {"object": "list", "data": [{"id": "models/gemini-3-flash"}, {"id": "models/gemini-3-pro"},
                                      {"id": "models/text-embedding-9"}, {"id": "models/imagen-9"}]}


def test_good_answer_and_request_shape(monkeypatch):
    rec = install(monkeypatch, post=lambda u, kw: response(200, GOOD))
    assert svc.call_llm("sys", [], "hi") == "Hello!"
    url, kw = rec.post_calls[0]
    assert url.endswith("/openai/chat/completions")
    assert kw["json"]["max_tokens"] == 1500 and "max_completion_tokens" not in kw["json"]
    assert kw["headers"]["Authorization"] == "Bearer SECRET-KEY-123"


def test_openai_com_uses_max_completion_tokens(monkeypatch):
    monkeypatch.setattr(settings, "llm_base_url", None)
    rec = install(monkeypatch, post=lambda u, kw: response(200, GOOD))
    svc.call_llm("sys", [], "hi")
    assert "max_completion_tokens" in rec.post_calls[0][1]["json"]


@pytest.mark.parametrize("status,words", [(401, "key was rejected"), (403, "key was rejected"),
                                          (404, "model name"), (429, "usage limit"), (503, "having problems")])
def test_http_errors_become_plain_reasons(monkeypatch, status, words):
    install(monkeypatch, post=lambda u, kw: response(status, {"error": {"message": "nope"}}))
    with pytest.raises(svc.LLMUnavailable) as err:
        svc.call_llm("sys", [], "hi")
    assert words in str(err.value) and f"HTTP {status}" in str(err.value)
    assert err.value.status == status and err.value.detail == "nope"


def test_the_key_is_never_in_the_message_or_detail(monkeypatch):
    install(monkeypatch, post=lambda u, kw: response(
        400, [{"error": {"message": "API key SECRET-KEY-123 is not valid"}}]))
    with pytest.raises(svc.LLMUnavailable) as err:
        svc.call_llm("sys", [], "hi")
    assert "SECRET-KEY-123" not in str(err.value) and "SECRET-KEY-123" not in err.value.detail


def test_timeout_is_explained(monkeypatch):
    def slow(u, kw):
        raise httpx.ReadTimeout("slow")
    install(monkeypatch, post=slow)
    with pytest.raises(svc.LLMUnavailable, match="too long"):
        svc.call_llm("sys", [], "hi")


def test_empty_answer_cut_off_by_the_token_limit_is_explained(monkeypatch):
    install(monkeypatch, post=lambda u, kw: response(
        200, {"choices": [{"message": {"content": None}, "finish_reason": "length"}]}))
    with pytest.raises(svc.LLMUnavailable, match="LLM_MAX_TOKENS"):
        svc.call_llm("sys", [], "hi")


def test_model_list_is_cleaned(monkeypatch):
    install(monkeypatch, get=lambda u, kw: response(200, MODELS))
    assert svc.list_models() == ["gemini-3-flash", "gemini-3-pro"]


def test_suggestion_prefers_flash():
    assert svc.suggest_model(["gemini-3-pro", "gemini-3-flash"]) == "gemini-3-flash"
    assert svc.suggest_model([]) is None


def test_diagnose_points_to_the_right_model_when_the_name_is_wrong(monkeypatch):
    install(monkeypatch, get=lambda u, kw: response(200, MODELS),
            post=lambda u, kw: response(404, {"error": {"message": "model not found"}}))
    result = svc.diagnose()
    assert result["ok"] is False and result["model_listed"] is False
    assert "LLM_MODEL=gemini-3-flash" in result["next_step"]
    assert "SECRET-KEY-123" not in str(result)


def test_diagnose_reports_success(monkeypatch):
    monkeypatch.setattr(settings, "llm_model", "gemini-3-flash")
    install(monkeypatch, get=lambda u, kw: response(200, MODELS),
            post=lambda u, kw: response(200, GOOD))
    result = svc.diagnose()
    assert result["ok"] is True and result["model_listed"] is True and result["test"]["sample"] == "Hello!"


def test_diagnose_without_a_key_says_what_to_do(monkeypatch):
    monkeypatch.setattr(settings, "llm_api_key", None)
    result = svc.diagnose()
    assert result["ok"] is False and "LLM_API_KEY" in result["next_step"]
