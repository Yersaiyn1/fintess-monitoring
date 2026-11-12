"""Utility for shadow RLS checking.

The function runs the same SELECT statement with row security disabled
(`SET LOCAL row_security = off`) and compares the result with the
application‑level result.  Any mismatch is logged into
`rls_mismatch_log`.
"""
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.access_log import AccessLog  # not needed here

async def log_rls_mismatch(
    session: AsyncSession,
    endpoint: str,
    user_id: int | None,
    doctor_id: int | None,
    stmt: sa.Select,
) -> None:
    """Execute *stmt* twice – once with RLS, once without – and log mismatches.

    Args:
        session: Async DB session (already in a transaction).
        endpoint: API path for logging.
        user_id / doctor_id: optional identifiers from request headers.
        stmt: The SQLAlchemy Select object that will be executed.
    """
    # Normal execution (RLS enforced) – reuse the original session.
    result_rls = await session.execute(stmt)
    rows_rls = result_rls.fetchall()

    # Disable RLS for shadow execution.
    await session.execute(sa.text("SET LOCAL row_security = off"))
    result_no_rls = await session.execute(stmt)
    rows_no_rls = result_no_rls.fetchall()

    # Restore default (row_security back to on) – implicit at transaction end.
    if len(rows_rls) != len(rows_no_rls) or rows_rls != rows_no_rls:
        # Prepare a brief diff for logging (could be large, so truncate).
        details = f"RLS rows: {len(rows_rls)}, no‑RLS rows: {len(rows_no_rls)}"
        from app.models.rls_mismatch_log import RlsMismatchLog  # model placeholder
        log_entry = RlsMismatchLog(
            endpoint=endpoint,
            user_id=user_id,
            doctor_id=doctor_id,
            rows_mismatched=abs(len(rows_rls) - len(rows_no_rls)),
            details=details,
        )
        session.add(log_entry)
        await session.commit()

