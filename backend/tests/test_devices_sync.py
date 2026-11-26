"""Tests for device registration, idempotent ensure, batch HR boundaries, and dashboard integration."""
import asyncio
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models.device import Device
from app.models.health_reading import HealthReading


async def register_user(client, email="device-user@example.com") -> tuple[dict, int]:
    res = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Device Tester",
            "email": email,
            "birth_date": "1995-05-10",
            "password": "Password123!",
        },
    )
    assert res.status_code == 201
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    me = await client.get("/api/v1/auth/me", headers=headers)
    return headers, me.json()["user_id"]


async def test_devices_endpoints_require_authentication(client):
    assert (await client.get("/api/v1/sync/devices")).status_code == 401
    assert (
        await client.post(
            "/api/v1/sync/devices",
            json={"model": "Band", "serial_number": "SN-1"},
        )
    ).status_code == 401
    assert (
        await client.post(
            "/api/v1/sync/devices/ensure",
            json={"provider": "demo", "name": "Demo Watch"},
        )
    ).status_code == 401


async def test_create_device_default_and_invalid_provider(client):
    headers, user_id = await register_user(client)

    default_res = await client.post(
        "/api/v1/sync/devices",
        json={"model": "FitBand X1", "serial_number": "SN-MANUAL-1"},
        headers=headers,
    )
    assert default_res.status_code == 201
    body = default_res.json()
    assert body["user_id"] == user_id
    assert body["provider"] == "manual"
    assert body["is_active"] is True

    explicit_res = await client.post(
        "/api/v1/sync/devices",
        json={"model": "Forerunner", "serial_number": "SN-GARMIN-1", "provider": "garmin"},
        headers=headers,
    )
    assert explicit_res.status_code == 201
    assert explicit_res.json()["provider"] == "garmin"

    bad_res = await client.post(
        "/api/v1/sync/devices",
        json={"model": "Unknown", "serial_number": "SN-BAD", "provider": "apple_magic"},
        headers=headers,
    )
    assert bad_res.status_code == 422


async def test_ensure_device_creation_truncation_and_idempotency(client, db_session):
    headers, user_id = await register_user(client, "ble@example.com")
    long_name = "Polar H10 " + ("X" * 300)

    first = await client.post(
        "/api/v1/sync/devices/ensure",
        json={"provider": "bluetooth", "name": long_name},
        headers=headers,
    )
    assert first.status_code == 200
    d1 = first.json()
    assert d1["provider"] == "bluetooth"
    assert d1["serial_number"] == f"BLE-{user_id}"
    assert d1["is_active"] is True
    assert len(d1["model"]) == 255

    second = await client.post(
        "/api/v1/sync/devices/ensure",
        json={"provider": "bluetooth", "name": "Different BLE Name"},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["device_id"] == d1["device_id"]

    demo_res = await client.post(
        "/api/v1/sync/devices/ensure",
        json={"provider": "demo", "name": "Demo Watch"},
        headers=headers,
    )
    assert demo_res.status_code == 200
    assert demo_res.json()["serial_number"] == f"DEMO-{user_id}"

    invalid = await client.post(
        "/api/v1/sync/devices/ensure",
        json={"provider": "invalid_provider", "name": "Bad"},
        headers=headers,
    )
    assert invalid.status_code == 422

    count = (
        await db_session.execute(
            select(func.count())
            .select_from(Device)
            .where(Device.user_id == user_id, Device.provider == "bluetooth")
        )
    ).scalar_one()
    assert count == 1


async def test_ensure_device_concurrent_calls_create_single_row(client, db_session):
    headers, user_id = await register_user(client, "concurrent@example.com")

    responses = await asyncio.gather(
        client.post(
            "/api/v1/sync/devices/ensure",
            json={"provider": "demo", "name": "Demo Watch"},
            headers=headers,
        ),
        client.post(
            "/api/v1/sync/devices/ensure",
            json={"provider": "demo", "name": "Demo Watch"},
            headers=headers,
        ),
    )
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json()["device_id"] == responses[1].json()["device_id"]

    count = (
        await db_session.execute(
            select(func.count())
            .select_from(Device)
            .where(Device.user_id == user_id, Device.provider == "demo")
        )
    ).scalar_one()
    assert count == 1


async def test_ensure_device_isolation_between_users(client):
    h1, u1 = await register_user(client, "alice-dev@example.com")
    h2, u2 = await register_user(client, "bob-dev@example.com")

    d1 = (
        await client.post(
            "/api/v1/sync/devices/ensure",
            json={"provider": "bluetooth", "name": "HR Band"},
            headers=h1,
        )
    ).json()
    d2 = (
        await client.post(
            "/api/v1/sync/devices/ensure",
            json={"provider": "bluetooth", "name": "HR Band"},
            headers=h2,
        )
    ).json()

    assert d1["device_id"] != d2["device_id"]
    assert d1["serial_number"] == f"BLE-{u1}"
    assert d2["serial_number"] == f"BLE-{u2}"

    list1 = (await client.get("/api/v1/sync/devices", headers=h1)).json()
    list2 = (await client.get("/api/v1/sync/devices", headers=h2)).json()
    assert [d["device_id"] for d in list1] == [d1["device_id"]]
    assert [d["device_id"] for d in list2] == [d2["device_id"]]


async def test_sync_batch_hr_boundaries_validation_and_deduplication(client, db_session):
    headers, _ = await register_user(client, "batch@example.com")
    device_id = (
        await client.post(
            "/api/v1/sync/devices/ensure",
            json={"provider": "bluetooth", "name": "Polar H10"},
            headers=headers,
        )
    ).json()["device_id"]

    # Boundary values 30 and 220 succeed
    valid_payload = {
        "device_id": device_id,
        "readings": [
            {"date_time": "2026-11-26T10:00:01Z", "heart_rate_bpm": 30},
            {"date_time": "2026-11-26T10:00:02Z", "heart_rate_bpm": 220},
        ],
    }
    first_sync = await client.post("/api/v1/sync/batch", json=valid_payload)
    assert first_sync.status_code == 200
    assert first_sync.json() == {"device_id": device_id, "synced_count": 2, "skipped_count": 0}

    # Re-sending identical timestamps is idempotent
    second_sync = await client.post("/api/v1/sync/batch", json=valid_payload)
    assert second_sync.status_code == 200
    assert second_sync.json() == {"device_id": device_id, "synced_count": 0, "skipped_count": 2}

    total_rows = (
        await db_session.execute(
            select(func.count())
            .select_from(HealthReading)
            .where(HealthReading.device_id == device_id)
        )
    ).scalar_one()
    assert total_rows == 2

    # Out-of-range heart rates are rejected with 422
    for invalid_hr in (0, 29, 221):
        bad_sync = await client.post(
            "/api/v1/sync/batch",
            json={
                "device_id": device_id,
                "readings": [
                    {"date_time": "2026-11-26T10:01:00Z", "heart_rate_bpm": invalid_hr}
                ],
            },
        )
        assert bad_sync.status_code == 422


async def test_demo_watch_batch_shows_up_on_dashboard(client):
    headers, _ = await register_user(client, "demo-dash@example.com")
    device_id = (
        await client.post(
            "/api/v1/sync/devices/ensure",
            json={"provider": "demo", "name": "Demo Watch"},
            headers=headers,
        )
    ).json()["device_id"]

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    sync_res = await client.post(
        "/api/v1/sync/batch",
        json={
            "device_id": device_id,
            "readings": [
                {
                    "device_id": device_id,
                    "date_time": now_iso,
                    "heart_rate_bpm": 78,
                    "steps": 240,
                    "calories_kcal": 10.8,
                }
            ],
        },
    )
    assert sync_res.status_code == 200
    assert sync_res.json()["synced_count"] == 1

    dash = await client.get("/api/v1/dashboard", headers=headers)
    assert dash.status_code == 200
    today = dash.json()["week"][-1]
    assert today["steps"] == 240
    assert today["calories"] == 10.8
