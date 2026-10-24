"""Role routing and negotiation headroom use synthetic keys only."""
import pytest

from app.config import settings
from app.services import gemini_agent


@pytest.fixture(autouse=True)
def slots(monkeypatch):
    for slot in (1, 2, 3):
        gemini_agent.slot_limiters[slot].reset()
        monkeypatch.setattr(settings, f"GEMINI_API_KEY_{slot}", f"test-slot-{slot}")
    gemini_agent.rate_limiter.reset()
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    monkeypatch.setattr(settings, "GEMINI_ROLE_MAP_JSON", "")
    monkeypatch.setattr(settings, "GEMINI_RPM_LIMIT", 15)
    monkeypatch.setattr(settings, "GEMINI_RPD_LIMIT", 1500)
    monkeypatch.setattr(settings, "GEMINI_KEY_3_RESERVE_RPM", 5)
    monkeypatch.setattr(settings, "GEMINI_KEY_3_RESERVE_RPD", 300)
    yield
    for limiter in gemini_agent.slot_limiters.values():
        limiter.reset()


def test_role_assignment_and_status_has_no_secret():
    assert gemini_agent._acquire_key("intake", set())[1] == 1
    assert gemini_agent._acquire_key("drafter", set())[1] == 2
    assert gemini_agent._acquire_key("negotiator", set())[1] == 3
    status = gemini_agent.get_rate_limit_status()
    assert [row["rpm_used"] for row in status["slots"]] == [1, 1, 1]
    assert "test-slot" not in str(status)


def test_429_fails_over_and_preserves_slot_3_headroom(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_RPM_LIMIT", 2)
    monkeypatch.setattr(settings, "GEMINI_KEY_3_RESERVE_RPM", 1)
    gemini_agent.slot_limiters[1].record_429(60)
    assert gemini_agent._acquire_key("intake", set())[1] == 2
    gemini_agent.slot_limiters[2].record_429(60)
    assert gemini_agent._acquire_key("intake", set())[1] == 3
    with pytest.raises(gemini_agent.GeminiRateLimitError):
        gemini_agent._acquire_key("intake", set())
    assert gemini_agent._acquire_key("negotiator", set())[1] == 3


def test_configurable_role_map_is_validated(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_ROLE_MAP_JSON", '{"drafter":1}')
    assert gemini_agent._acquire_key("drafter", set())[1] == 1
    monkeypatch.setattr(settings, "GEMINI_ROLE_MAP_JSON", '{"drafter":4}')
    with pytest.raises(ValueError):
        gemini_agent._acquire_key("drafter", set())


def test_upstream_429_retries_least_loaded_slot(monkeypatch):
    seen = []

    class Response:
        def __init__(self, status):
            self.status_code = status
            self.headers = {"retry-after": "30"}

        def raise_for_status(self):
            assert self.status_code == 200

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text":
                '{"summary":"Checked","rationale":"Evidence only","reply_draft":""}'}]}}]}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, **kwargs):
            seen.append(kwargs["headers"]["x-goog-api-key"])
            return Response(429 if len(seen) == 1 else 200)

    monkeypatch.setattr(gemini_agent.httpx, "Client", Client)
    result = gemini_agent.generate({"case": "synthetic"}, "summary", role="intake")
    assert result.summary == "Checked"
    assert seen == ["test-slot-1", "test-slot-2"]
    assert gemini_agent.get_rate_limit_status()["slots"][0]["throttled"]


def test_legacy_fallback_does_not_retry_same_secret(monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-slot-1")
    for slot in (1, 2, 3):
        gemini_agent.slot_limiters[slot].record_429(60)
    with pytest.raises(gemini_agent.GeminiRateLimitError):
        gemini_agent._acquire_key("intake", set())


def test_intent_classifier_uses_key_3(monkeypatch):
    seen = []
    class Response:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"intent":"haggling"}'}]}}]}
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            seen.append(kwargs["headers"]["x-goog-api-key"])
            return Response()
    monkeypatch.setattr(gemini_agent.httpx, "Client", Client)
    assert gemini_agent.classify_intent("Could we have more time?") == "haggling"
    assert seen == ["test-slot-3"]


def test_intent_classifier_quota_error_fails_over(monkeypatch):
    seen = []
    class Response:
        def __init__(self, status):
            self.status_code = status
        def raise_for_status(self):
            assert self.status_code == 200
        def json(self):
            if self.status_code == 403:
                return {"error": {"status": "RESOURCE_EXHAUSTED"}}
            return {"candidates": [{"content": {"parts": [{"text": '{"intent":"haggling"}'}]}}]}
    class Client:
        def __init__(self, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, **kwargs):
            seen.append(kwargs["headers"]["x-goog-api-key"])
            return Response(403 if len(seen) == 1 else 200)
    monkeypatch.setattr(gemini_agent.httpx, "Client", Client)
    assert gemini_agent.classify_intent("Could we have more time?") == "haggling"
    assert seen == ["test-slot-3", "test-slot-1"]
