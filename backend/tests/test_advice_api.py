"""Integration tests for /api/v1/goals and /api/v1/advice endpoints."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models.device import Device
from app.models.health_reading import HealthReading
from app.models.user_goal import UserGoal


async def _register(client, email: str, full_name: str = "Advice User") -> tuple[dict[str, str], int]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": full_name,
            "email": email,
            "birth_date": "1995-05-10",
            "password": "password123",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    return headers, me.json()["user_id"]


async def test_advice_and_goals_require_authentication(client):
    assert (await client.get("/api/v1/goals")).status_code == 401
    assert (
        await client.put("/api/v1/goals", json={"steps_daily": 8000, "workouts_weekly": 2})
    ).status_code == 401
    assert (await client.get("/api/v1/advice")).status_code == 401
    assert (
        await client.put("/api/v1/advice/consent", json={"enabled": True})
    ).status_code == 401


async def test_goals_get_returns_defaults_without_persisting_and_put_updates(client, db_session):
    headers, user_id = await _register(client, "goals@example.com")

    get_resp = await client.get("/api/v1/goals", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json() == {"steps_daily": 10000, "workouts_weekly": 3, "updated_at": None}

    row_count = (
        await db_session.execute(
            select(func.count()).select_from(UserGoal).where(UserGoal.user_id == user_id)
        )
    ).scalar_one()
    assert row_count == 0

    bad_resp = await client.put(
        "/api/v1/goals",
        headers=headers,
        json={"steps_daily": 500, "workouts_weekly": 20},
    )
    assert bad_resp.status_code == 422

    put_resp = await client.put(
        "/api/v1/goals",
        headers=headers,
        json={"steps_daily": 12000, "workouts_weekly": 4},
    )
    assert put_resp.status_code == 200
    body = put_resp.json()
    assert body["steps_daily"] == 12000
    assert body["workouts_weekly"] == 4
    assert body["updated_at"] is not None

    get_after = await client.get("/api/v1/goals", headers=headers)
    assert get_after.status_code == 200
    assert get_after.json()["steps_daily"] == 12000
    assert get_after.json()["workouts_weekly"] == 4


async def test_advice_no_data_and_language_selection(client):
    headers, _ = await _register(client, "empty_adv@example.com")

    en_resp = await client.get("/api/v1/advice", headers=headers)
    assert en_resp.status_code == 200
    en_body = en_resp.json()
    assert en_body["source"] == "rules"
    assert en_body["ai_available"] is False
    assert en_body["ai_consent"] is False
    assert en_body["disclaimer"] == "This is not medical advice."
    assert [i["code"] for i in en_body["items"]] == ["no_data"]

    ru_resp = await client.get("/api/v1/advice", params={"lang": "ru"}, headers=headers)
    assert ru_resp.status_code == 200
    ru_body = ru_resp.json()
    assert ru_body["disclaimer"] == "Это не медицинская рекомендация"
    assert ru_body["items"][0]["code"] == "no_data"
    assert "часы" in ru_body["items"][0]["text"].lower()

    hdr_ru_resp = await client.get(
        "/api/v1/advice",
        headers={**headers, "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.5"},
    )
    assert hdr_ru_resp.status_code == 200
    assert hdr_ru_resp.json()["disclaimer"] == "Это не медицинская рекомендация"


async def test_advice_high_hr_and_user_isolation(client, db_session):
    headers_a, user_a = await _register(client, "usera@example.com")
    headers_b, user_b = await _register(client, "userb@example.com")

    now = datetime.now(timezone.utc)
    dev_a = Device(user_id=user_a, model="Watch A", serial_number="A-1")
    dev_b = Device(user_id=user_b, model="Watch B", serial_number="B-1")
    db_session.add_all([dev_a, dev_b])
    await db_session.flush()

    # User A has high heart rate (110 bpm); User B has healthy readings.
    db_session.add_all([
        HealthReading(
            device_id=dev_a.device_id,
            date_time=now - timedelta(hours=2),
            heart_rate_bpm=110,
            steps=8500,
        ),
        HealthReading(
            device_id=dev_b.device_id,
            date_time=now - timedelta(hours=2),
            heart_rate_bpm=65,
            steps=9000,
        ),
    ])
    await db_session.commit()

    resp_a = await client.get("/api/v1/advice", headers=headers_a)
    assert resp_a.status_code == 200
    codes_a = [i["code"] for i in resp_a.json()["items"]]
    assert "high_hr" in codes_a

    resp_b = await client.get("/api/v1/advice", headers=headers_b)
    assert resp_b.status_code == 200
    codes_b = [i["code"] for i in resp_b.json()["items"]]
    assert "high_hr" not in codes_b
