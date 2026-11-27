"""Tests for the optional LLM advice layer (mock client, privacy, fallback, cache, consent)."""
from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from app.core.config import settings
from app.main import app
from app.models.device import Device
from app.models.health_reading import HealthReading
from app.services.advice_llm import get_llm_client


class MockLlmClient:
    """In-memory mock LlmClient recording calls and returning configurable outputs."""

    def __init__(self, handler) -> None:
        self._handler = handler
        self.calls: list[tuple[str, str]] = []

    async def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        result = self._handler(system, user, len(self.calls))
        if isinstance(result, BaseException):
            raise result
        return result


async def _setup_user_with_high_hr(client, db_session, email: str, full_name: str) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": full_name,
            "email": email,
            "birth_date": "1994-03-12",
            "password": "password123",
        },
    )
    assert resp.status_code == 201
    headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()

    now = datetime.now(timezone.utc)
    device = Device(user_id=me["user_id"], model="Galaxy Watch", serial_number="SN-SECRET-999")
    db_session.add(device)
    await db_session.flush()
    db_session.add(
        HealthReading(
            device_id=device.device_id,
            date_time=now - timedelta(hours=1),
            heart_rate_bpm=112,
            steps=7000,
        )
    )
    await db_session.commit()
    return headers


async def test_llm_not_called_without_consent(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "ADVICE_LLM_ENABLED", True)
    headers = await _setup_user_with_high_hr(client, db_session, "noconsent@example.com", "Secret Name")

    mock = MockLlmClient(lambda s, u, n: '{"items":[]}')
    app.dependency_overrides[get_llm_client] = lambda: mock
    try:
        resp = await client.get("/api/v1/advice", headers=headers)
    finally:
        app.dependency_overrides.pop(get_llm_client, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "rules"
    assert body["ai_available"] is True
    assert body["ai_consent"] is False
    assert len(mock.calls) == 0


async def test_llm_rephrasing_privacy_cache_and_rate_limit(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "ADVICE_LLM_ENABLED", True)
    email = "private_user@example.com"
    full_name = "Alice SecretSurname"
    headers = await _setup_user_with_high_hr(client, db_session, email, full_name)

    consent_resp = await client.put("/api/v1/advice/consent", headers=headers, json={"enabled": True})
    assert consent_resp.status_code == 200
    assert consent_resp.json() == {"enabled": True}

    def ok_handler(system: str, user: str, call_num: int) -> str:
        payload = json.loads(user)
        items = [
            {"code": item["code"], "text": f"AI phrasing #{call_num} for {item['code']}."}
            for item in payload["advice"]
        ]
        return json.dumps({"items": items})

    mock = MockLlmClient(ok_handler)
    app.dependency_overrides[get_llm_client] = lambda: mock
    try:
        # 1st call populates cache and invokes LLM once.
        r1 = await client.get("/api/v1/advice", params={"lang": "en"}, headers=headers)
        assert r1.status_code == 200
        b1 = r1.json()
        assert b1["source"] == "ai"
        assert b1["ai_consent"] is True
        assert any("AI phrasing #1" in item["text"] for item in b1["items"])
        assert len(mock.calls) == 1

        # Verify zero PII or device serial numbers leaked into prompts.
        sys_prompt, usr_prompt = mock.calls[0]
        combined_prompt = f"{sys_prompt}\n{usr_prompt}"
        assert email not in combined_prompt
        assert full_name not in combined_prompt
        assert "SN-SECRET-999" not in combined_prompt
        assert "user_id" not in combined_prompt

        # 2nd call hits cache without calling LLM again.
        r2 = await client.get("/api/v1/advice", params={"lang": "en"}, headers=headers)
        assert r2.status_code == 200
        assert r2.json()["source"] == "ai"
        assert len(mock.calls) == 1

        # Explicit ?refresh=true bypasses cache and calls LLM.
        r3 = await client.get(
            "/api/v1/advice", params={"lang": "en", "refresh": "true"}, headers=headers
        )
        assert r3.status_code == 200
        assert any("AI phrasing #2" in item["text"] for item in r3.json()["items"])
        assert len(mock.calls) == 2

        # Immediate second ?refresh=true within 10 minutes is rejected with HTTP 429.
        r4 = await client.get(
            "/api/v1/advice", params={"lang": "en", "refresh": "true"}, headers=headers
        )
        assert r4.status_code == 429
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


@pytest.mark.parametrize(
    "mode",
    [
        "timeout",
        "http_error",
        "bad_json",
        "missing_code",
        "extra_code",
        "contains_url",
        "too_long",
    ],
)
async def test_llm_errors_and_invalid_outputs_fallback_to_rules(
    client, db_session, monkeypatch, mode: str
):
    monkeypatch.setattr(settings, "ADVICE_LLM_ENABLED", True)
    headers = await _setup_user_with_high_hr(
        client, db_session, f"fb_{mode}@example.com", "Fallback User"
    )
    await client.put("/api/v1/advice/consent", headers=headers, json={"enabled": True})

    def bad_handler(system: str, user: str, call_num: int):
        if mode == "timeout":
            return TimeoutError("LLM timed out")
        if mode == "http_error":
            return httpx.ConnectError("Network error")
        if mode == "bad_json":
            return "not valid json at all"

        payload = json.loads(user)
        codes = [item["code"] for item in payload["advice"]]
        if mode == "missing_code":
            return json.dumps({"items": [{"code": codes[0], "text": "Only first."}]}) if len(codes) > 1 else "{}"
        if mode == "extra_code":
            items = [{"code": c, "text": "Ok text."} for c in codes]
            items.append({"code": "unknown_code", "text": "Extra."})
            return json.dumps({"items": items})
        if mode == "contains_url":
            return json.dumps({
                "items": [
                    {"code": c, "text": "Visit https://example.com" if i == 0 else "Ok text."}
                    for i, c in enumerate(codes)
                ]
            })
        return json.dumps({
            "items": [
                {"code": c, "text": ("x" * 401) if i == 0 else "Ok text."}
                for i, c in enumerate(codes)
            ]
        })

    mock = MockLlmClient(bad_handler)
    app.dependency_overrides[get_llm_client] = lambda: mock
    try:
        resp = await client.get("/api/v1/advice", headers=headers)
    finally:
        app.dependency_overrides.pop(get_llm_client, None)

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "rules"
    assert any(item["code"] == "high_hr" for item in body["items"])
