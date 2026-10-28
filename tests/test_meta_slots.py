import pytest

from app.config import settings
from app.services import meta_agent


@pytest.fixture(autouse=True)
def _slots(monkeypatch):
    for slot in (1, 2, 3):
        meta_agent.slot_limiters[slot].reset()
        monkeypatch.setattr(settings, f"META_API_KEY_{slot}", f"test-slot-{slot}")
    meta_agent.rate_limiter.reset()
    monkeypatch.setattr(settings, "META_MODEL_API_KEY", "")
    monkeypatch.setattr(settings, "META_ROLE_MAP_JSON", "")
    monkeypatch.setattr(settings, "META_RPM_LIMIT", 15)
    monkeypatch.setattr(settings, "META_RPD_LIMIT", 1500)
    monkeypatch.setattr(settings, "META_KEY_3_RESERVE_RPM", 5)
    monkeypatch.setattr(settings, "META_KEY_3_RESERVE_RPD", 300)
    monkeypatch.setattr(settings, "AGENT_MODEL", "muse-spark-1.3")
    yield
    for limiter in meta_agent.slot_limiters.values():
        limiter.reset()
    meta_agent.rate_limiter.reset()


def test_role_slot_mapping_and_status():
    assert meta_agent._acquire_key("intake", set())[1] == 1
    assert meta_agent._acquire_key("drafter", set())[1] == 2
    assert meta_agent._acquire_key("negotiator", set())[1] == 3
    status = meta_agent.get_rate_limit_status()
    assert [slot["slot"] for slot in status["slots"]] == [1, 2, 3]
    assert all(slot["configured"] for slot in status["slots"])


def test_failover_skips_throttled_and_exhausted_slots(monkeypatch):
    monkeypatch.setattr(settings, "META_RPM_LIMIT", 2)
    monkeypatch.setattr(settings, "META_KEY_3_RESERVE_RPM", 1)
    meta_agent.slot_limiters[1].record_429(60)
    assert meta_agent._acquire_key("intake", set())[1] == 2
    meta_agent.slot_limiters[2].record_429(60)
    assert meta_agent._acquire_key("intake", set())[1] == 3
    with pytest.raises(meta_agent.MetaRateLimitError):
        meta_agent._acquire_key("intake", set())
    assert meta_agent._acquire_key("negotiator", set())[1] == 3


def test_role_map_override_and_validation(monkeypatch):
    monkeypatch.setattr(settings, "META_ROLE_MAP_JSON", '{"drafter":1}')
    assert meta_agent._acquire_key("drafter", set())[1] == 1
    monkeypatch.setattr(settings, "META_ROLE_MAP_JSON", '{"drafter":4}')
    with pytest.raises(ValueError, match="META_ROLE_MAP_JSON"):
        meta_agent._acquire_key("drafter", set())


def _chat_response(text):
    return {"choices": [{"message": {"content": text}}]}


def test_generate_fails_over_to_next_slot_on_429(monkeypatch):
    calls = []

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.headers = {}
        def raise_for_status(self):
            pass
        def json(self):
            return _chat_response(
                '{"summary":"s","rationale":"r","reply_draft":"Thanks."}')

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            calls.append(kwargs["headers"]["Authorization"])
            assert url.endswith("/chat/completions")
            assert kwargs["json"]["model"] == settings.AGENT_MODEL
            assert kwargs["json"]["response_format"] == {"type": "json_object"}
            if len(calls) == 1:
                return Response(429)
            return Response(200)

    monkeypatch.setattr(meta_agent.httpx, "Client", Client)
    result = meta_agent.generate({"case": "synthetic"}, "summary", role="intake")
    assert result.reply_draft == "Thanks."
    assert calls == ["Bearer test-slot-1", "Bearer test-slot-2"]
    assert meta_agent.get_rate_limit_status()["slots"][0]["throttled"]


def test_same_secret_is_not_retried_as_legacy(monkeypatch):
    monkeypatch.setattr(settings, "META_MODEL_API_KEY", "test-slot-1")
    for slot in (1, 2, 3):
        meta_agent.slot_limiters[slot].record_429(60)
    with pytest.raises(meta_agent.MetaRateLimitError):
        meta_agent._acquire_key("intake", set())


def test_classify_intent_returns_valid_label(monkeypatch):
    class Response:
        status_code = 200
        headers = {}
        def raise_for_status(self):
            pass
        def json(self):
            return _chat_response('{"intent": "haggling"}')

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            assert kwargs["headers"]["Authorization"] == "Bearer test-slot-3"
            return Response()

    monkeypatch.setattr(meta_agent.httpx, "Client", Client)
    assert meta_agent.classify_intent("Could we have more time?") == "haggling"


def test_classify_rejects_unknown_label(monkeypatch):
    class Response:
        status_code = 200
        headers = {}
        def raise_for_status(self):
            pass
        def json(self):
            return _chat_response('{"intent": "bribe"}')

    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            return Response()

    monkeypatch.setattr(meta_agent.httpx, "Client", Client)
    with pytest.raises(RuntimeError, match="unknown intent"):
        meta_agent.classify_intent("Could we have more time?")
