"""Tests for Phase 4: Goals CRUD, live progress calculation, cross-user isolation,
7-day inactivity alert, and 7-day high heart-rate (> 100 bpm) alert.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.device import Device
from app.models.health_reading import HealthReading
from app.models.workout import Workout

USER_A = {
    "full_name": "Goal User A",
    "email": "goals.a@example.com",
    "birth_date": "1994-05-12",
    "password": "Password123",
}
USER_B = {
    "full_name": "Goal User B",
    "email": "goals.b@example.com",
    "birth_date": "1992-08-01",
    "password": "Password123",
}


async def _register(client, payload: dict) -> tuple[int, dict[str, str]]:
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201
    return r.json()["user"]["user_id"], {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_goals_require_authentication(client):
    assert (await client.get("/api/v1/goals")).status_code == 401
    assert (
        await client.post(
            "/api/v1/goals",
            json={"period": "daily", "metric": "steps", "target_value": 5000},
        )
    ).status_code == 401
    assert (await client.delete("/api/v1/goals/1")).status_code == 401


async def test_goals_crud_progress_and_isolation(client, db_session):
    uid_a, headers_a = await _register(client, USER_A)
    uid_b, headers_b = await _register(client, USER_B)

    # Record a device reading and a finished workout for User A today
    now = datetime.now(timezone.utc)
    dev = Device(user_id=uid_a, model="Band Pro", serial_number="SN-GOAL-A")
    db_session.add(dev)
    await db_session.flush()
    db_session.add(
        HealthReading(
            device_id=dev.device_id,
            date_time=now,
            heart_rate_bpm=78,
            steps=3500,
            calories_kcal=160.0,
        )
    )
    db_session.add(
        Workout(
            user_id=uid_a,
            kind="Run",
            started_at=now - timedelta(minutes=20),
            ended_at=now,
            steps=2500,
            distance_km=2.5,
            calories_kcal=200.0,
        )
    )
    await db_session.commit()

    # Create daily steps goal (target 5000, current = 3500 + 2500 = 6000 -> achieved!)
    r_create = await client.post(
        "/api/v1/goals",
        headers=headers_a,
        json={"period": "daily", "metric": "steps", "target_value": 5000},
    )
    assert r_create.status_code == 201
    g1 = r_create.json()
    assert g1["current_value"] == 6000
    assert g1["progress_percent"] == 100
    assert g1["achieved"] is True

    # Upsert same (daily, steps) target to 12000 -> progress drops to 50%, not achieved
    r_update = await client.post(
        "/api/v1/goals",
        headers=headers_a,
        json={"period": "daily", "metric": "steps", "target_value": 12000},
    )
    assert r_update.status_code == 201
    g1_updated = r_update.json()
    assert g1_updated["goal_id"] == g1["goal_id"]
    assert g1_updated["progress_percent"] == 50
    assert g1_updated["achieved"] is False

    # Create weekly workouts goal (target 2, current = 1 -> 50%)
    r_weekly = await client.post(
        "/api/v1/goals",
        headers=headers_a,
        json={"period": "weekly", "metric": "workouts", "target_value": 2},
    )
    assert r_weekly.status_code == 201
    assert r_weekly.json()["current_value"] == 1
    assert r_weekly.json()["progress_percent"] == 50

    # User B sees zero goals and cannot delete User A's goal
    summary_b = (await client.get("/api/v1/goals", headers=headers_b)).json()
    assert summary_b["goals"] == []
    assert (await client.delete(f"/api/v1/goals/{g1['goal_id']}", headers=headers_b)).status_code == 404

    # User A can delete their goal
    assert (await client.delete(f"/api/v1/goals/{g1['goal_id']}", headers=headers_a)).status_code == 204
    summary_a = (await client.get("/api/v1/goals", headers=headers_a)).json()
    assert len(summary_a["goals"]) == 1


async def test_inactivity_alert_and_high_heart_rate_alert(client, db_session):
    uid, headers = await _register(client, USER_A)

    # 1. Fresh user with zero activity -> inactivity_alert = True, high_heart_rate_alert = False
    s1 = (await client.get("/api/v1/goals", headers=headers)).json()
    assert s1["alerts"]["inactivity_alert"] is True
    assert s1["alerts"]["high_heart_rate_alert"] is False
    assert len(s1["alerts"]["messages"]) == 1

    # 2. Add readings with average HR > 100 bpm (e.g. 110 and 120) and some steps ->
    #    inactivity_alert clears (False), high_heart_rate_alert triggers (True)!
    now = datetime.now(timezone.utc)
    dev = Device(user_id=uid, model="Band Pro", serial_number="SN-ALERT-1")
    db_session.add(dev)
    await db_session.flush()
    db_session.add_all(
        [
            HealthReading(
                device_id=dev.device_id,
                date_time=now - timedelta(hours=2),
                heart_rate_bpm=110,
                steps=500,
                calories_kcal=30.0,
            ),
            HealthReading(
                device_id=dev.device_id,
                date_time=now - timedelta(hours=1),
                heart_rate_bpm=120,
                steps=500,
                calories_kcal=30.0,
            ),
        ]
    )
    await db_session.commit()

    s2 = (await client.get("/api/v1/goals", headers=headers)).json()
    assert s2["alerts"]["inactivity_alert"] is False
    assert s2["alerts"]["high_heart_rate_alert"] is True
    assert s2["alerts"]["avg_heart_rate_7d"] == 115.0
    assert s2["alerts"]["heart_rate_readings_7d"] == 2
