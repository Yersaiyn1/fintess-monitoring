"""Tests for Android Health Connect archive/db upload (`POST /api/v1/sync/upload-hc`)."""
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
import io
import logging
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile

from sqlalchemy import func, select

from app.core.config import settings
from app.models.device import Device
from app.models.health_reading import HealthReading
from app.models.sleep_session import SleepSession
from scripts.inspect_hc_export import inspect_hc_export


def _build_custom_hc_db_bytes(setup_sql: str, inserts: list[tuple[str, tuple]] | None = None) -> bytes:
    """Create a custom SQLite DB from DDL/DML statements and return raw bytes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "health_connect_export.db")
        with closing(sqlite3.connect(db_path)) as conn:
            cur = conn.cursor()
            cur.executescript(setup_sql)
            for sql, params in inserts or []:
                cur.execute(sql, params)
            conn.commit()
        with open(db_path, "rb") as f:
            return f.read()


def _norm_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


async def test_upload_hc_zip_idempotent_and_updates_activity_totals(client, db_session):
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
    assert body1["total_parsed"] == 6
    assert body1["inserted"] == 6
    assert body1["updated"] == 0
    assert body1["unchanged_skipped"] == 0
    assert body1["duplicates_skipped"] == 0
    assert body1["sleep_sessions"] == 1
    assert body1["metrics_breakdown"] == {
        "steps": 2,
        "heart_rate": 1,
        "calories": 1,
        "blood_pressure": 1,
        "spo2": 1,
        "sleep": 1,
    }

    # Snapshot persisted readings before re-upload to verify idempotency.
    before_rows = [
        (r.date_time, r.end_time, r.steps, r.heart_rate_bpm, r.calories_kcal, r.blood_pressure, r.spo2_percent)
        for r in (
            await db_session.execute(select(HealthReading).order_by(HealthReading.date_time))
        ).scalars().all()
    ]

    # Uploading the exact same archive a second time must skip all rows without duplicates or errors.
    second = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("export.zip", zip_bytes, "application/zip")},
    )
    assert second.status_code == 200
    body2 = second.json()
    assert body2["total_parsed"] == 6
    assert body2["inserted"] == 0
    assert body2["updated"] == 0
    assert body2["unchanged_skipped"] == 6
    assert body2["duplicates_skipped"] == 6
    assert body2["sleep_sessions"] == 1

    after_rows = [
        (r.date_time, r.end_time, r.steps, r.heart_rate_bpm, r.calories_kcal, r.blood_pressure, r.spo2_percent)
        for r in (
            await db_session.execute(select(HealthReading).order_by(HealthReading.date_time))
        ).scalars().all()
    ]
    assert after_rows == before_rows

    count = (await db_session.execute(select(func.count()).select_from(HealthReading))).scalar_one()
    assert count == 6
    spo2_val = (
        await db_session.execute(
            select(HealthReading.spo2_percent).where(HealthReading.spo2_percent.is_not(None))
        )
    ).scalar_one()
    assert spo2_val == 98.5
    sleep_count = (await db_session.execute(select(func.count()).select_from(SleepSession))).scalar_one()
    assert sleep_count == 1

    device = (await db_session.execute(select(Device))).scalar_one()
    assert device.model == "POCO X7 Pro"

    dash = await client.get("/api/v1/dashboard", headers=headers)
    assert dash.status_code == 200
    week = dash.json()["week"]
    today = week[-1]
    assert today["steps"] == 2000
    assert today["calories"] == 120.5
    assert today["caloriesEstimated"] is False

    for period in ("week", "month"):
        analytics = await client.get("/api/v1/analytics/workouts", params={"period": period}, headers=headers)
        assert analytics.status_code == 200
        summary = analytics.json()
        assert summary["totals"]["workouts"] == 0
        assert summary["byKind"] == []
        for activity, history in zip(week, summary["days"][-len(week):], strict=True):
            assert history["date"] == activity["date"]
            assert history["steps"] == activity["steps"]
            assert history["caloriesKcal"] == activity["calories"]
            assert history["distanceKm"] == activity["distanceKm"]
            assert history["durationMin"] == activity["activeMinutes"]


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
    assert body["total_parsed"] == 6
    assert body["inserted"] == 6
    assert body["duplicates_skipped"] == 0
    assert body["sleep_sessions"] == 1


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


async def test_upload_hc_coalesce_backfill_preserves_existing_values(client, db_session):
    headers = await _register_headers(client, email="backfill@example.com")
    ts = int(datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc).timestamp() * 1000)

    ddl = """
        CREATE TABLE steps_record_table (start_time INTEGER, end_time INTEGER, count INTEGER);
        CREATE TABLE heart_rate_record_series_table (beats_per_minute INTEGER, epoch_millis INTEGER);
    """
    file1 = _build_custom_hc_db_bytes(
        ddl,
        [("INSERT INTO steps_record_table VALUES (?, ?, ?)", (ts, ts + 60_000, 1500))],
    )
    r1 = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("step1.zip", _wrap_zip(file1), "application/zip")},
    )
    assert r1.status_code == 200
    assert r1.json()["inserted"] == 1
    assert r1.json()["updated"] == 0

    file2 = _build_custom_hc_db_bytes(
        ddl,
        [
            ("INSERT INTO steps_record_table VALUES (?, ?, ?)", (ts, ts + 60_000, 1500)),
            ("INSERT INTO heart_rate_record_series_table VALUES (?, ?)", (84, ts)),
        ],
    )
    r2 = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("step2.zip", _wrap_zip(file2), "application/zip")},
    )
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["inserted"] == 0
    assert b2["updated"] == 1
    assert b2["unchanged_skipped"] == 0

    reading = (await db_session.execute(select(HealthReading))).scalar_one()
    assert reading.steps == 1500
    assert reading.heart_rate_bpm == 84

    # Re-uploading file1 (no HR) must NOT overwrite HR with NULL and must count as unchanged.
    r3 = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("step1_again.zip", _wrap_zip(file1), "application/zip")},
    )
    assert r3.status_code == 200
    b3 = r3.json()
    assert b3["inserted"] == 0
    assert b3["updated"] == 0
    assert b3["unchanged_skipped"] == 1

    await db_session.refresh(reading)
    assert reading.steps == 1500
    assert reading.heart_rate_bpm == 84


async def test_upload_hc_spo2_and_sleep_sessions_saved_and_updated(client, db_session):
    headers = await _register_headers(client, email="sleep_spo2@example.com")
    t_spo2 = datetime(2026, 11, 20, 7, 0, tzinfo=timezone.utc)
    t_sleep_start = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)
    t_sleep_end_1 = datetime(2026, 11, 21, 5, 30, tzinfo=timezone.utc)
    t_sleep_end_2 = datetime(2026, 11, 21, 6, 45, tzinfo=timezone.utc)

    ddl = """
        CREATE TABLE oxygen_saturation_record_table (time INTEGER, percentage REAL);
        CREATE TABLE sleep_session_record_table (start_time INTEGER, end_time INTEGER);
    """
    db1 = _build_custom_hc_db_bytes(
        ddl,
        [
            ("INSERT INTO oxygen_saturation_record_table VALUES (?, ?)", (int(t_spo2.timestamp() * 1000), 97.2)),
            ("INSERT INTO oxygen_saturation_record_table VALUES (?, ?)", (int(t_spo2.timestamp() * 1000) + 1000, -5.0)),
            ("INSERT INTO oxygen_saturation_record_table VALUES (?, ?)", (int(t_spo2.timestamp() * 1000) + 2000, 120.0)),
            ("INSERT INTO sleep_session_record_table VALUES (?, ?)", (int(t_sleep_start.timestamp() * 1000), int(t_sleep_end_1.timestamp() * 1000))),
        ],
    )
    r1 = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("spo2_sleep1.zip", _wrap_zip(db1), "application/zip")},
    )
    assert r1.status_code == 200
    b1 = r1.json()
    assert b1["total_parsed"] == 1
    assert b1["inserted"] == 1
    assert b1["sleep_sessions"] == 1
    assert b1["metrics_breakdown"] == {"spo2": 1, "sleep": 1}

    hr_row = (await db_session.execute(select(HealthReading))).scalar_one()
    assert hr_row.spo2_percent == 97.2

    sleep_row = (await db_session.execute(select(SleepSession))).scalar_one()
    assert _norm_utc(sleep_row.start_time) == t_sleep_start
    assert _norm_utc(sleep_row.end_time) == t_sleep_end_1

    # Updating the sleep session with a later end_time updates the existing row in place.
    db2 = _build_custom_hc_db_bytes(
        ddl,
        [
            ("INSERT INTO sleep_session_record_table VALUES (?, ?)", (int(t_sleep_start.timestamp() * 1000), int(t_sleep_end_2.timestamp() * 1000))),
        ],
    )
    r2 = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("spo2_sleep2.zip", _wrap_zip(db2), "application/zip")},
    )
    assert r2.status_code == 200
    assert r2.json()["sleep_sessions"] == 1

    db_session.expire_all()
    all_sleeps = (await db_session.execute(select(SleepSession))).scalars().all()
    assert len(all_sleeps) == 1
    assert _norm_utc(all_sleeps[0].end_time) == t_sleep_end_2


async def test_upload_hc_empty_or_invalid_metrics_create_no_rows_and_log_warnings(
    client, db_session, caplog
):
    headers = await _register_headers(client, email="invalid_metrics@example.com")
    ts = int(datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc).timestamp() * 1000)

    ddl = """
        CREATE TABLE steps_record_table (start_time INTEGER, count INTEGER);
        CREATE TABLE heart_rate_record_series_table (beats_per_minute INTEGER, epoch_millis INTEGER);
        CREATE TABLE active_calories_burned_record_table (start_time INTEGER, energy REAL);
        CREATE TABLE oxygen_saturation_record_table (time INTEGER, percentage REAL);
        CREATE TABLE sleep_session_record_table (start_time INTEGER);
    """
    db_bytes = _build_custom_hc_db_bytes(
        ddl,
        [
            ("INSERT INTO steps_record_table VALUES (?, ?)", (ts, -10)),
            ("INSERT INTO heart_rate_record_series_table VALUES (?, ?)", (20, ts)),
            ("INSERT INTO heart_rate_record_series_table VALUES (?, ?)", (250, ts + 1000)),
            ("INSERT INTO active_calories_burned_record_table VALUES (?, ?)", (ts, -5.0)),
            ("INSERT INTO oxygen_saturation_record_table VALUES (?, ?)", (ts, 101.0)),
            ("INSERT INTO sleep_session_record_table VALUES (?)", (ts,)),
        ],
    )
    with caplog.at_level(logging.WARNING, logger="app.services.hc_importer"):
        resp = await client.post(
            "/api/v1/sync/upload-hc",
            headers=headers,
            files={"file": ("invalid.zip", _wrap_zip(db_bytes), "application/zip")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_parsed"] == 0
    assert body["inserted"] == 0
    assert body["sleep_sessions"] == 0
    assert body["metrics_breakdown"] == {}

    assert (await db_session.execute(select(func.count()).select_from(HealthReading))).scalar_one() == 0
    assert (await db_session.execute(select(func.count()).select_from(SleepSession))).scalar_one() == 0
    assert any(
        "sleep_session_record_table" in rec.message and "end_time" in rec.message
        for rec in caplog.records
    )


async def test_upload_hc_no_fabricated_calories_and_dashboard_estimates(client, db_session):
    headers = await _register_headers(client, email="nocal@example.com")
    today_ts = int(
        datetime.combine(datetime.now(timezone.utc).date(), time(9, 0), tzinfo=timezone.utc).timestamp() * 1000
    )
    db_bytes = _build_custom_hc_db_bytes(
        "CREATE TABLE steps_record_table (start_time INTEGER, end_time INTEGER, count INTEGER);",
        [("INSERT INTO steps_record_table VALUES (?, ?, ?)", (today_ts, today_ts + 120_000, 2500))],
    )

    resp = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("steps_only.zip", _wrap_zip(db_bytes), "application/zip")},
    )
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 1

    reading = (await db_session.execute(select(HealthReading))).scalar_one()
    assert reading.steps == 2500
    assert reading.calories_kcal is None

    dash = await client.get("/api/v1/dashboard", headers=headers)
    assert dash.status_code == 200
    today = dash.json()["week"][-1]
    assert today["steps"] == 2500
    assert today["calories"] == 100.0
    assert today["caloriesEstimated"] is True


async def test_upload_hc_rejects_oversized_file_413(client, monkeypatch):
    headers = await _register_headers(client, email="big@example.com")
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 1)
    oversized = b"x" * (1024 * 1024 + 1024)

    resp = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("huge.zip", oversized, "application/zip")},
    )
    assert resp.status_code == 413


async def test_upload_hc_rejects_zip_bomb_ambiguous_zip_and_record_cap(client, monkeypatch):
    headers = await _register_headers(client, email="sec@example.com")

    # 1. Zip bomb: small compressed archive expanding beyond MAX_UNPACKED_MB -> HTTP 400.
    monkeypatch.setattr(settings, "MAX_UNPACKED_MB", 1)
    big_uncompressed = b"SQLite format 3\x00" + (b"\x00" * (1024 * 1024 + 64 * 1024))
    bomb_zip = _wrap_zip(big_uncompressed)
    assert len(bomb_zip) < 100_000  # small upload well under MAX_UPLOAD_MB

    bomb_resp = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("bomb.zip", bomb_zip, "application/zip")},
    )
    assert bomb_resp.status_code == 400
    assert "too large when unpacked" in bomb_resp.json()["detail"].lower()

    # 2. Ambiguous ZIP with multiple non-preferred .db files -> HTTP 400.
    monkeypatch.setattr(settings, "MAX_UNPACKED_MB", 300)
    ambiguous_buf = io.BytesIO()
    with zipfile.ZipFile(ambiguous_buf, "w") as zf:
        zf.writestr("a.db", b"SQLite format 3\x00")
        zf.writestr("b.db", b"SQLite format 3\x00")
    ambiguous_resp = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("multi.zip", ambiguous_buf.getvalue(), "application/zip")},
    )
    assert ambiguous_resp.status_code == 400
    assert "multiple .db" in ambiguous_resp.json()["detail"].lower()

    # 3. Record count limit -> HTTP 400.
    monkeypatch.setattr(settings, "MAX_HC_RECORDS", 2)
    base_ts = int(datetime(2026, 11, 20, 8, 0, tzinfo=timezone.utc).timestamp() * 1000)
    cap_db = _build_custom_hc_db_bytes(
        "CREATE TABLE steps_record_table (start_time INTEGER, end_time INTEGER, count INTEGER);",
        [
            ("INSERT INTO steps_record_table VALUES (?, ?, ?)", (base_ts + i * 60_000, base_ts + (i + 1) * 60_000, 100))
            for i in range(4)
        ],
    )
    cap_resp = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("toomany.zip", _wrap_zip(cap_db), "application/zip")},
    )
    assert cap_resp.status_code == 400
    assert "maximum allowed limit" in cap_resp.json()["detail"].lower()


async def test_upload_hc_uses_dedicated_device_and_updates_model(client, db_session):
    headers = await _register_headers(client, email="devices@example.com")

    # Create a manual device first.
    manual_resp = await client.post(
        "/api/v1/sync/devices",
        headers=headers,
        json={"model": "Manual Band", "serial_number": "MAN-001"},
    )
    assert manual_resp.status_code == 201
    manual_device = manual_resp.json()
    assert manual_device["provider"] == "manual"

    ts = int(datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc).timestamp() * 1000)
    ddl = """
        CREATE TABLE device_info_table (display_name TEXT, manufacturer TEXT, model TEXT);
        CREATE TABLE steps_record_table (start_time INTEGER, end_time INTEGER, count INTEGER);
    """
    db1 = _build_custom_hc_db_bytes(
        ddl,
        [
            ("INSERT INTO device_info_table VALUES (?, ?, ?)", ("POCO X7 Pro", "Xiaomi", "2412DPC0AG")),
            ("INSERT INTO steps_record_table VALUES (?, ?, ?)", (ts, ts + 60_000, 500)),
        ],
    )
    up1 = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("phone1.zip", _wrap_zip(db1), "application/zip")},
    )
    assert up1.status_code == 200

    devices_list = (await client.get("/api/v1/sync/devices", headers=headers)).json()
    assert len(devices_list) == 2
    hc_dev_resp = next(d for d in devices_list if d["provider"] == "health_connect")
    assert hc_dev_resp["model"] == "POCO X7 Pro"
    assert hc_dev_resp["serial_number"].startswith("HC-")

    manual_readings = (
        await db_session.execute(
            select(func.count())
            .select_from(HealthReading)
            .where(HealthReading.device_id == manual_device["device_id"])
        )
    ).scalar_one()
    assert manual_readings == 0

    # Upload from a new phone model -> updates the HC device's model without creating a third device.
    db2 = _build_custom_hc_db_bytes(
        ddl,
        [
            ("INSERT INTO device_info_table VALUES (?, ?, ?)", ("Pixel 9 Pro", "Google", "Pixel 9 Pro")),
            ("INSERT INTO steps_record_table VALUES (?, ?, ?)", (ts + 60_000, ts + 120_000, 700)),
        ],
    )
    up2 = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("phone2.zip", _wrap_zip(db2), "application/zip")},
    )
    assert up2.status_code == 200

    devices_after = (await client.get("/api/v1/sync/devices", headers=headers)).json()
    assert len(devices_after) == 2
    hc_after = next(d for d in devices_after if d["provider"] == "health_connect")
    assert hc_after["device_id"] == hc_dev_resp["device_id"]
    assert hc_after["model"] == "Pixel 9 Pro"


async def test_upload_hc_preserves_and_merges_end_time_intervals(client, db_session):
    headers = await _register_headers(client, email="intervals@example.com")
    start_dt = datetime(2026, 11, 20, 14, 0, tzinfo=timezone.utc)
    end_steps = start_dt + timedelta(minutes=10)
    end_cals = start_dt + timedelta(minutes=25)

    ddl = """
        CREATE TABLE steps_record_table (start_time INTEGER, end_time INTEGER, count INTEGER);
        CREATE TABLE active_calories_burned_record_table (start_time INTEGER, end_time INTEGER, energy REAL);
    """
    db_bytes = _build_custom_hc_db_bytes(
        ddl,
        [
            ("INSERT INTO steps_record_table VALUES (?, ?, ?)", (int(start_dt.timestamp() * 1000), int(end_steps.timestamp() * 1000), 900)),
            ("INSERT INTO active_calories_burned_record_table VALUES (?, ?, ?)", (int(start_dt.timestamp() * 1000), int(end_cals.timestamp() * 1000), 45.0)),
        ],
    )
    resp = await client.post(
        "/api/v1/sync/upload-hc",
        headers=headers,
        files={"file": ("intervals.zip", _wrap_zip(db_bytes), "application/zip")},
    )
    assert resp.status_code == 200
    assert resp.json()["inserted"] == 1

    reading = (await db_session.execute(select(HealthReading))).scalar_one()
    assert _norm_utc(reading.date_time) == start_dt
    assert _norm_utc(reading.end_time) == end_cals


def test_inspect_hc_export_script_reports_tables_and_missing_columns():
    db_bytes = _build_custom_hc_db_bytes(
        """
        CREATE TABLE steps_record_table (start_time INTEGER, count INTEGER);
        CREATE TABLE custom_extra_table (id INTEGER);
        """,
        [("INSERT INTO steps_record_table VALUES (?, ?)", (1700000000000, 123))],
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "sample_export.zip"
        zip_path.write_bytes(_wrap_zip(db_bytes))
        report = inspect_hc_export(zip_path)

    assert "steps_record_table: PRESENT (1 rows)" in report
    assert "end_time (optional)" in report
    assert "sleep_session_record_table: MISSING" in report
    assert "custom_extra_table: 0 rows" in report
