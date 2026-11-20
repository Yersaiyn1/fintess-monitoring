"""Tests for Android Health Connect archive/db upload (`POST /api/v1/sync/upload-hc`)."""
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
import io
import os
import sqlite3
import tempfile
import zipfile

from sqlalchemy import func, select

from app.models.device import Device
from app.models.health_reading import HealthReading


def _build_sample_hc_db_bytes(now_utc: datetime) -> bytes:
    """Create a minimal SQLite DB matching health_connect_export.db schema and return raw bytes."""
    today_start = datetime.combine(now_utc.date(), time(8, 0), tzinfo=timezone.utc)
    ts_steps_1 = int(today_start.timestamp() * 1000)
    ts_steps_2 = int((today_start + timedelta(minutes=15)).timestamp() * 1000)
    ts_hr = int((today_start + timedelta(minutes=30)).timestamp() * 1000)
    ts_cal = int((today_start + timedelta(minutes=45)).timestamp() * 1000)
    ts_bp = int((today_start + timedelta(minutes=60)).timestamp() * 1000)
    ts_spo2 = int((today_start + timedelta(minutes=75)).timestamp() * 1000)
    ts_sleep = int((today_start + timedelta(minutes=90)).timestamp() * 1000)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "health_connect_export.db")
        with closing(sqlite3.connect(db_path)) as conn:
            cur = conn.cursor()
            cur.executescript(
                """
                CREATE TABLE application_info_table (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    package_name TEXT,
                    app_name TEXT,
                    app_icon BLOB,
                    record_types_used TEXT,
                    device_info_id INTEGER
                );
                CREATE TABLE device_info_table (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    manufacturer TEXT,
                    model TEXT,
                    device_type INTEGER,
                    device_id TEXT,
                    display_name TEXT,
                    udi TEXT
                );
                CREATE TABLE steps_record_table (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid BLOB,
                    last_modified_time INTEGER,
                    client_record_id TEXT,
                    client_record_version TEXT,
                    device_info_id INTEGER,
                    app_info_id INTEGER,
                    recording_method INTEGER,
                    dedupe_hash BLOB,
                    start_time INTEGER,
                    start_zone_offset INTEGER,
                    end_time INTEGER,
                    end_zone_offset INTEGER,
                    local_date INTEGER,
                    count INTEGER,
                    device_data_provider_id INTEGER
                );
                CREATE TABLE heart_rate_record_table (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid BLOB,
                    last_modified_time INTEGER,
                    client_record_id TEXT,
                    client_record_version TEXT,
                    device_info_id INTEGER,
                    app_info_id INTEGER,
                    recording_method INTEGER,
                    dedupe_hash BLOB,
                    start_time INTEGER,
                    start_zone_offset INTEGER,
                    end_time INTEGER,
                    end_zone_offset INTEGER,
                    local_date INTEGER,
                    device_data_provider_id INTEGER
                );
                CREATE TABLE heart_rate_record_series_table (
                    parent_key INTEGER,
                    beats_per_minute INTEGER,
                    epoch_millis INTEGER
                );
                CREATE TABLE resting_heart_rate_record_table (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time INTEGER,
                    beats_per_minute INTEGER
                );
                CREATE TABLE active_calories_burned_record_table (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time INTEGER,
                    end_time INTEGER,
                    energy REAL
                );
                CREATE TABLE blood_pressure_record_table (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time INTEGER,
                    systolic REAL,
                    diastolic REAL
                );
                CREATE TABLE oxygen_saturation_record_table (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    time INTEGER,
                    percentage REAL
                );
                CREATE TABLE sleep_session_record_table (
                    row_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time INTEGER,
                    end_time INTEGER,
                    title TEXT
                );
                """
            )
            cur.execute(
                "INSERT INTO application_info_table (package_name, app_name) VALUES (?, ?)",
                ("app.qozgal.steps", "Qozgal"),
            )
            cur.execute(
                "INSERT INTO device_info_table (manufacturer, model, device_type, display_name) "
                "VALUES (?, ?, ?, ?)",
                ("Xiaomi", "2412DPC0AG", 2, "POCO X7 Pro"),
            )
            cur.execute(
                "INSERT INTO steps_record_table (start_time, end_time, count) VALUES (?, ?, ?)",
                (ts_steps_1, ts_steps_1 + 60_000, 1200),
            )
            cur.execute(
                "INSERT INTO steps_record_table (start_time, end_time, count) VALUES (?, ?, ?)",
                (ts_steps_2, ts_steps_2 + 60_000, 800),
            )
            cur.execute(
                "INSERT INTO heart_rate_record_series_table (parent_key, beats_per_minute, epoch_millis) "
                "VALUES (?, ?, ?)",
                (1, 78, ts_hr),
            )
            cur.execute(
                "INSERT INTO active_calories_burned_record_table (start_time, end_time, energy) "
                "VALUES (?, ?, ?)",
                (ts_cal, ts_cal + 60_000, 120.5),
            )
            cur.execute(
                "INSERT INTO blood_pressure_record_table (time, systolic, diastolic) VALUES (?, ?, ?)",
                (ts_bp, 118.0, 76.0),
            )
            cur.execute(
                "INSERT INTO oxygen_saturation_record_table (time, percentage) VALUES (?, ?)",
                (ts_spo2, 98.5),
            )
            cur.execute(
                "INSERT INTO sleep_session_record_table (start_time, end_time, title) VALUES (?, ?, ?)",
                (ts_sleep, ts_sleep + 3_600_000, "Night sleep"),
            )
            conn.commit()

        with open(db_path, "rb") as f:
            return f.read()


def _wrap_zip(db_bytes: bytes, inner_name: str = "health_connect_export.db") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_name, db_bytes)
    return buf.getvalue()


async def _register_headers(client, email: str = "hc@example.com") -> dict[str, str]:
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "HC User",
            "email": email,
            "birth_date": "1995-05-10",
            "password": "password123",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_upload_hc_zip_idempotent_and_updates_dashboard(client, db_session):
    headers = await _register_headers(client)
    db_bytes = _build_sample_hc_db_bytes(datetime.now(timezone.utc))
    zip_bytes = _wrap_zip(db_bytes)

    first = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("export.zip", zip_bytes, "application/zip")},
    )
    assert first.status_code == 200
    body1 = first.json()
    assert body1["filename"] == "export.zip"
    assert body1["total_parsed"] == 7
    assert body1["inserted"] == 7
    assert body1["duplicates_skipped"] == 0
    assert body1["metrics_breakdown"] == {
        "steps": 2,
        "heart_rate": 1,
        "calories": 1,
        "blood_pressure": 1,
        "spo2": 1,
        "sleep": 1,
    }

    # Uploading the exact same archive a second time must skip all rows without duplicates or errors.
    second = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("export.zip", zip_bytes, "application/zip")},
    )
    assert second.status_code == 200
    body2 = second.json()
    assert body2["total_parsed"] == 7
    assert body2["inserted"] == 0
    assert body2["duplicates_skipped"] == 7

    count = (await db_session.execute(select(func.count()).select_from(HealthReading))).scalar_one()
    assert count == 7

    device = (await db_session.execute(select(Device))).scalar_one()
    assert device.model == "POCO X7 Pro"

    dash = await client.get("/api/v1/dashboard", headers=headers)
    assert dash.status_code == 200
    today = dash.json()["week"][-1]
    assert today["steps"] == 2000
    # 1200 * 0.04 (48.0) + 800 * 0.04 (32.0) + 120.5 = 200.5
    assert today["calories"] == 200.5


async def test_upload_hc_direct_db_file(client):
    headers = await _register_headers(client, email="dbuser@example.com")
    db_bytes = _build_sample_hc_db_bytes(datetime.now(timezone.utc))

    resp = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("health_connect_export.db", db_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "health_connect_export.db"
    assert body["total_parsed"] == 7
    assert body["inserted"] == 7
    assert body["duplicates_skipped"] == 0


async def test_upload_hc_requires_auth_and_valid_file(client):
    zip_bytes = _wrap_zip(b"not a sqlite file")
    unauth = await client.post(
        "/api/v1/sync/upload-hc",
        files={"file": ("export.zip", zip_bytes, "application/zip")},
    )
    assert unauth.status_code == 401

    headers = await _register_headers(client, email="val@example.com")
    bad_ext = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert bad_ext.status_code == 400

    empty_zip = io.BytesIO()
    with zipfile.ZipFile(empty_zip, "w") as zf:
        zf.writestr("readme.txt", "no db here")
    no_db = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("empty.zip", empty_zip.getvalue(), "application/zip")},
    )
    assert no_db.status_code == 400
