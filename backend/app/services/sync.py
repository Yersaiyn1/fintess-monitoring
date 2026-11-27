"""Database upsert helpers for synced health readings and sleep sessions."""
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import case, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.health_reading import HealthReading
from app.models.sleep_session import SleepSession

_UPDATABLE_COLS = (
    "heart_rate_bpm",
    "steps",
    "calories_kcal",
    "blood_pressure",
    "spo2_percent",
)


@dataclass
class UpsertResult:
    """Counts returned from upserting a list of health readings."""

    inserted: int
    updated: int
    unchanged_skipped: int


def _norm_dt(dt: datetime) -> datetime:
    """Normalize datetimes to naive UTC for dialect-consistent set membership checks."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _dedupe_rows(device_id: int, rows: list[dict]) -> list[dict]:
    """Ensure unique (device_id, date_time) keys within a single batch."""
    by_dt: dict[datetime, dict] = {}
    for raw in rows:
        dt = raw["date_time"]
        existing = by_dt.get(dt)
        if existing is None:
            by_dt[dt] = {
                "device_id": device_id,
                "date_time": dt,
                "end_time": raw.get("end_time"),
                "heart_rate_bpm": raw.get("heart_rate_bpm"),
                "steps": raw.get("steps"),
                "calories_kcal": raw.get("calories_kcal"),
                "blood_pressure": raw.get("blood_pressure"),
                "spo2_percent": raw.get("spo2_percent"),
            }
        else:
            for col in _UPDATABLE_COLS:
                if raw.get(col) is not None:
                    existing[col] = raw[col]
            new_end = raw.get("end_time")
            if new_end is not None:
                cur_end = existing.get("end_time")
                if cur_end is None or new_end > cur_end:
                    existing["end_time"] = new_end
    return list(by_dt.values())


async def upsert_readings(
    db: AsyncSession,
    device_id: int,
    rows: list[dict],
    batch_size: int = 500,
) -> UpsertResult:
    """Insert new Health_Readings or backfill NULL fields on (device_id, date_time) conflicts."""
    if not rows:
        return UpsertResult(inserted=0, updated=0, unchanged_skipped=0)

    prepared = _dedupe_rows(device_id, rows)
    conn = await db.connection()
    dialect_name = conn.dialect.name
    insert_fn = sqlite_insert if dialect_name == "sqlite" else pg_insert

    inserted = 0
    updated = 0

    for i in range(0, len(prepared), batch_size):
        batch = prepared[i : i + batch_size]

        existing_dts: set[datetime] = set()
        if dialect_name == "sqlite":
            batch_dts = [r["date_time"] for r in batch]
            existing_rows = (
                await db.execute(
                    select(HealthReading.date_time).where(
                        HealthReading.device_id == device_id,
                        HealthReading.date_time.in_(batch_dts),
                    )
                )
            ).scalars().all()
            existing_dts = {_norm_dt(dt) for dt in existing_rows}

        stmt = insert_fn(HealthReading).values(batch)
        set_map = {
            col: func.coalesce(stmt.excluded[col], getattr(HealthReading, col))
            for col in _UPDATABLE_COLS
        }
        end_time_expr = case(
            (HealthReading.end_time.is_(None), stmt.excluded.end_time),
            (stmt.excluded.end_time.is_(None), HealthReading.end_time),
            (stmt.excluded.end_time > HealthReading.end_time, stmt.excluded.end_time),
            else_=HealthReading.end_time,
        )
        set_map["end_time"] = end_time_expr
        where_clause = or_(
            *(getattr(HealthReading, col).is_distinct_from(expr) for col, expr in set_map.items())
        )

        if dialect_name == "sqlite":
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=["device_id", "date_time"],
                set_=set_map,
                where=where_clause,
            ).returning(HealthReading.date_time)
            returned_dts = (await db.execute(upsert_stmt)).scalars().all()
            for dt in returned_dts:
                if _norm_dt(dt) in existing_dts:
                    updated += 1
                else:
                    inserted += 1
        else:
            upsert_stmt = stmt.on_conflict_do_update(
                index_elements=["device_id", "date_time"],
                set_=set_map,
                where=where_clause,
            ).returning(text("(xmax = 0) AS inserted"))
            for (is_inserted,) in (await db.execute(upsert_stmt)).all():
                if is_inserted:
                    inserted += 1
                else:
                    updated += 1

    unchanged_skipped = max(0, len(rows) - inserted - updated)
    return UpsertResult(
        inserted=inserted,
        updated=updated,
        unchanged_skipped=unchanged_skipped,
    )


async def upsert_sleep_sessions(
    db: AsyncSession,
    device_id: int,
    sessions: list[dict],
    batch_size: int = 500,
) -> int:
    """Insert or update Sleep_Sessions keyed by (device_id, start_time)."""
    if not sessions:
        return 0

    conn = await db.connection()
    insert_fn = sqlite_insert if conn.dialect.name == "sqlite" else pg_insert

    for i in range(0, len(sessions), batch_size):
        batch = [
            {
                "device_id": device_id,
                "start_time": s["start_time"],
                "end_time": s["end_time"],
            }
            for s in sessions[i : i + batch_size]
        ]
        stmt = insert_fn(SleepSession).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["device_id", "start_time"],
            set_={"end_time": stmt.excluded.end_time},
        )
        await db.execute(stmt)

    return len(sessions)
