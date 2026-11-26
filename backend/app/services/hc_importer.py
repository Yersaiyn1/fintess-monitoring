"""Parser for Android Health Connect SQLite exports (.zip containing .db or raw .db)."""
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import io
import logging
import os
import sqlite3
import tempfile
import zipfile


SQLITE_MAGIC = b"SQLite format 3\x00"
logger = logging.getLogger(__name__)


@dataclass
class ParsedHealthConnectData:
    """Normalized records and summary extracted from a Health Connect export."""

    readings: list[dict]
    sleep_sessions: list[dict]
    metrics_breakdown: dict[str, int]
    device_model: str


def _ms_to_utc(ms: int | float) -> datetime:
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=timezone.utc)


def _get_columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    rows = cur.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {row[1] for row in rows}


def _resolve_ts_col(cols: set[str], candidates: tuple[str, ...]) -> str | None:
    return next((col for col in candidates if col in cols), None)


def _ensure_reading(by_time: dict[datetime, dict], dt: datetime) -> dict:
    reading = by_time.get(dt)
    if reading is None:
        reading = {
            "date_time": dt,
            "end_time": None,
            "steps": None,
            "heart_rate_bpm": None,
            "calories_kcal": None,
            "blood_pressure": None,
            "spo2_percent": None,
        }
        by_time[dt] = reading
    return reading


def _merge_end_time(reading: dict, start_dt: datetime, end_ms: int | float | None) -> None:
    """Keep the maximum valid interval end_time when merging records sharing start_dt."""
    if end_ms is None:
        return
    end_dt = _ms_to_utc(end_ms)
    if end_dt < start_dt:
        return
    existing = reading["end_time"]
    if existing is None or end_dt > existing:
        reading["end_time"] = end_dt


def _bump(breakdown: dict[str, int], key: str) -> None:
    breakdown[key] = breakdown.get(key, 0) + 1


def _extract_db_file(data: bytes, filename: str, tmpdir: str) -> str:
    """Locate or materialize the SQLite .db file inside `tmpdir`."""
    lower_name = filename.lower()
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            db_members = [
                info
                for info in zf.infolist()
                if not info.is_dir() and info.filename.lower().endswith(".db")
            ]
            if not db_members:
                raise ValueError("No .db file found inside the ZIP archive.")
            preferred = next(
                (m for m in db_members if os.path.basename(m.filename).lower() == "health_connect_export.db"),
                db_members[0],
            )
            db_path = os.path.join(tmpdir, "health_connect_export.db")
            with zf.open(preferred, "r") as src, open(db_path, "wb") as dst:
                dst.write(src.read())
            return db_path

    if lower_name.endswith(".zip"):
        raise ValueError("Invalid or corrupted ZIP archive.")

    if data.startswith(SQLITE_MAGIC) or lower_name.endswith(".db"):
        if not data.startswith(SQLITE_MAGIC):
            raise ValueError("Invalid or corrupted SQLite .db file.")
        db_path = os.path.join(tmpdir, "upload.db")
        with open(db_path, "wb") as dst:
            dst.write(data)
        return db_path

    raise ValueError("Unsupported or corrupted file. Expected a Health Connect .zip or .db file.")


def _extract_device_model(cur: sqlite3.Cursor, existing_tables: set[str]) -> str:
    if "device_info_table" not in existing_tables:
        return "Android Health Connect"
    cols = _get_columns(cur, "device_info_table")
    select_cols = [c for c in ("display_name", "manufacturer", "model") if c in cols]
    if not select_cols:
        return "Android Health Connect"
    rows = cur.execute(f'SELECT {", ".join(select_cols)} FROM device_info_table').fetchall()
    for row in rows:
        data = dict(zip(select_cols, row))
        display_name = (data.get("display_name") or "").strip()
        if display_name:
            return display_name[:255]
        combined = " ".join(
            part.strip()
            for part in (data.get("manufacturer") or "", data.get("model") or "")
            if part and part.strip()
        )
        if combined:
            return combined[:255]
    return "Android Health Connect"


def _parse_steps(
    cur: sqlite3.Cursor, existing_tables: set[str], by_time: dict[datetime, dict], breakdown: dict[str, int]
) -> None:
    table = "steps_record_table"
    if table not in existing_tables:
        return
    cols = _get_columns(cur, table)
    if not {"start_time", "count"} <= cols:
        return
    has_end = "end_time" in cols
    select_cols = "start_time, count, end_time" if has_end else "start_time, count"
    rows = cur.execute(
        f"SELECT {select_cols} FROM {table} WHERE start_time IS NOT NULL AND count IS NOT NULL"
    ).fetchall()
    for row in rows:
        start_ms, count = row[0], row[1]
        end_ms = row[2] if has_end else None
        steps_val = int(count)
        if steps_val < 0:
            continue
        dt = _ms_to_utc(start_ms)
        reading = _ensure_reading(by_time, dt)
        reading["steps"] = (reading["steps"] or 0) + steps_val
        _merge_end_time(reading, dt, end_ms)
        _bump(breakdown, "steps")


def _parse_heart_rate(
    cur: sqlite3.Cursor, existing_tables: set[str], by_time: dict[datetime, dict], breakdown: dict[str, int]
) -> None:
    sources = (
        ("heart_rate_record_series_table", ("epoch_millis", "time", "start_time")),
        ("heart_rate_record_table", ("start_time", "time", "epoch_millis")),
        ("resting_heart_rate_record_table", ("time", "start_time", "epoch_millis")),
    )
    for table, ts_candidates in sources:
        if table not in existing_tables:
            continue
        cols = _get_columns(cur, table)
        ts_col = _resolve_ts_col(cols, ts_candidates)
        if ts_col is None or "beats_per_minute" not in cols:
            continue
        rows = cur.execute(
            f"SELECT {ts_col}, beats_per_minute FROM {table} "
            f"WHERE {ts_col} IS NOT NULL AND beats_per_minute IS NOT NULL"
        ).fetchall()
        for ts_ms, bpm in rows:
            bpm_int = int(round(float(bpm)))
            # Matches HealthReading CheckConstraint("heart_rate_bpm BETWEEN 30 AND 220")
            if not (30 <= bpm_int <= 220):
                continue
            reading = _ensure_reading(by_time, _ms_to_utc(ts_ms))
            reading["heart_rate_bpm"] = bpm_int
            _bump(breakdown, "heart_rate")


def _parse_calories(
    cur: sqlite3.Cursor, existing_tables: set[str], by_time: dict[datetime, dict], breakdown: dict[str, int]
) -> None:
    for table in ("active_calories_burned_record_table", "total_calories_burned_record_table"):
        if table not in existing_tables:
            continue
        cols = _get_columns(cur, table)
        ts_col = _resolve_ts_col(cols, ("start_time", "time"))
        if ts_col is None or "energy" not in cols:
            continue
        has_end = "end_time" in cols
        select_cols = f"{ts_col}, energy, end_time" if has_end else f"{ts_col}, energy"
        rows = cur.execute(
            f"SELECT {select_cols} FROM {table} WHERE {ts_col} IS NOT NULL AND energy IS NOT NULL"
        ).fetchall()
        for row in rows:
            ts_ms, energy = row[0], row[1]
            end_ms = row[2] if has_end else None
            val = float(energy)
            if val < 0:
                continue
            kcal = round(val / 1000.0, 2) if val > 10000.0 else round(val, 2)
            dt = _ms_to_utc(ts_ms)
            reading = _ensure_reading(by_time, dt)
            reading["calories_kcal"] = round((reading["calories_kcal"] or 0.0) + kcal, 2)
            _merge_end_time(reading, dt, end_ms)
            _bump(breakdown, "calories")


def _parse_blood_pressure(
    cur: sqlite3.Cursor, existing_tables: set[str], by_time: dict[datetime, dict], breakdown: dict[str, int]
) -> None:
    table = "blood_pressure_record_table"
    if table not in existing_tables:
        return
    cols = _get_columns(cur, table)
    ts_col = _resolve_ts_col(cols, ("time", "start_time"))
    if ts_col is None or not {"systolic", "diastolic"} <= cols:
        return
    rows = cur.execute(
        f"SELECT {ts_col}, systolic, diastolic FROM {table} "
        f"WHERE {ts_col} IS NOT NULL AND systolic IS NOT NULL AND diastolic IS NOT NULL"
    ).fetchall()
    for ts_ms, sys_v, dia_v in rows:
        sys_i, dia_i = int(round(float(sys_v))), int(round(float(dia_v)))
        if sys_i <= 0 or dia_i <= 0:
            continue
        reading = _ensure_reading(by_time, _ms_to_utc(ts_ms))
        reading["blood_pressure"] = f"{sys_i}/{dia_i}"[:20]
        _bump(breakdown, "blood_pressure")


def _parse_spo2(
    cur: sqlite3.Cursor, existing_tables: set[str], by_time: dict[datetime, dict], breakdown: dict[str, int]
) -> None:
    table = "oxygen_saturation_record_table"
    if table not in existing_tables:
        return
    cols = _get_columns(cur, table)
    ts_col = _resolve_ts_col(cols, ("time", "start_time"))
    if ts_col is None or "percentage" not in cols:
        return
    rows = cur.execute(
        f"SELECT {ts_col}, percentage FROM {table} WHERE {ts_col} IS NOT NULL AND percentage IS NOT NULL"
    ).fetchall()
    for ts_ms, pct in rows:
        pct_val = float(pct)
        # Matches HealthReading CheckConstraint("spo2_percent BETWEEN 0 AND 100")
        if not (0.0 <= pct_val <= 100.0):
            continue
        reading = _ensure_reading(by_time, _ms_to_utc(ts_ms))
        reading["spo2_percent"] = round(pct_val, 2)
        _bump(breakdown, "spo2")


def _parse_sleep(
    cur: sqlite3.Cursor,
    existing_tables: set[str],
    sleep_by_start: dict[datetime, datetime],
    breakdown: dict[str, int],
) -> None:
    table = "sleep_session_record_table"
    if table not in existing_tables:
        return
    cols = _get_columns(cur, table)
    missing = [c for c in ("start_time", "end_time") if c not in cols]
    if missing:
        logger.warning(
            "Health Connect table '%s' is missing expected column(s): %s (available: %s)",
            table,
            ", ".join(missing),
            ", ".join(sorted(cols)),
        )
        return
    rows = cur.execute(
        f"SELECT start_time, end_time FROM {table} WHERE start_time IS NOT NULL AND end_time IS NOT NULL"
    ).fetchall()
    for start_ms, end_ms in rows:
        start_dt = _ms_to_utc(start_ms)
        end_dt = _ms_to_utc(end_ms)
        if end_dt <= start_dt:
            continue
        existing_end = sleep_by_start.get(start_dt)
        if existing_end is None or end_dt > existing_end:
            sleep_by_start[start_dt] = end_dt
    if sleep_by_start:
        breakdown["sleep"] = len(sleep_by_start)


def parse_health_connect_bytes(data: bytes, filename: str = "") -> ParsedHealthConnectData:
    """Parse an uploaded Health Connect .zip or .db payload into HealthReading dictionaries."""
    if not data:
        raise ValueError("Uploaded file is empty.")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = _extract_db_file(data, filename, tmpdir)
        # Explicitly close sqlite3.Connection before TemporaryDirectory cleanup (required on Windows).
        with closing(sqlite3.connect(db_path)) as conn:
            cur = conn.cursor()
            existing_tables = {
                row[0]
                for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            device_model = _extract_device_model(cur, existing_tables)
            by_time: dict[datetime, dict] = {}
            sleep_by_start: dict[datetime, datetime] = {}
            breakdown: dict[str, int] = {}

            _parse_steps(cur, existing_tables, by_time, breakdown)
            _parse_heart_rate(cur, existing_tables, by_time, breakdown)
            _parse_calories(cur, existing_tables, by_time, breakdown)
            _parse_blood_pressure(cur, existing_tables, by_time, breakdown)
            _parse_spo2(cur, existing_tables, by_time, breakdown)
            _parse_sleep(cur, existing_tables, sleep_by_start, breakdown)

    readings = sorted(by_time.values(), key=lambda r: r["date_time"])
    sleep_sessions = [
        {"start_time": start_dt, "end_time": end_dt}
        for start_dt, end_dt in sorted(sleep_by_start.items())
    ]
    return ParsedHealthConnectData(
        readings=readings,
        sleep_sessions=sleep_sessions,
        metrics_breakdown=breakdown,
        device_model=device_model,
    )
