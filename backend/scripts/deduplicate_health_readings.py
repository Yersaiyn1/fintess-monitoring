#!/usr/bin/env python3
"""
Deduplication script for Health_Readings table.

Finds duplicate rows by (device_id, date_time) and keeps only the
row with the minimum reading_id (earliest insert). Processes in
batches of BATCH_SIZE rows. Safe to re-run multiple times (idempotent).

Usage:
    python scripts/deduplicate_health_readings.py
    python scripts/deduplicate_health_readings.py --batch-size 500 --dry-run

Environment:
    DATABASE_URL — PostgreSQL connection string (postgresql://user:pass@host/db)
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # python-dotenv not installed, rely on env vars

import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("deduplicate_health_readings")

BATCH_SIZE_DEFAULT = 1000


def get_connection(database_url: str):
    """Create a psycopg2 connection. Converts asyncpg URL to psycopg2 format."""
    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgresql+psycopg2://", "postgresql://")
    conn = psycopg2.connect(url)
    return conn


def count_duplicates(cur) -> int:
    """Count total number of duplicate rows (rows that will be deleted)."""
    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM "Health_Readings" hr
        WHERE hr.reading_id NOT IN (
            SELECT MIN(reading_id)
            FROM "Health_Readings"
            GROUP BY device_id, date_time
        )
    """)
    return cur.fetchone()["cnt"]


def delete_batch(cur, batch_size: int, dry_run: bool) -> int:
    """
    Delete one batch of duplicate rows.
    Returns the number of rows deleted (or that would be deleted in dry-run).
    """
    # Find batch of duplicate reading_ids to delete
    cur.execute("""
        SELECT reading_id
        FROM "Health_Readings"
        WHERE reading_id NOT IN (
            SELECT MIN(reading_id)
            FROM "Health_Readings"
            GROUP BY device_id, date_time
        )
        ORDER BY reading_id
        LIMIT %s
    """, (batch_size,))
    
    rows = cur.fetchall()
    if not rows:
        return 0
    
    ids_to_delete = [r["reading_id"] for r in rows]
    
    if dry_run:
        logger.info("[DRY RUN] Would delete %d rows: reading_ids %s ... %s",
                    len(ids_to_delete), ids_to_delete[0], ids_to_delete[-1])
        return len(ids_to_delete)
    
    cur.execute(
        'DELETE FROM "Health_Readings" WHERE reading_id = ANY(%s)',
        (ids_to_delete,)
    )
    return cur.rowcount


def run_deduplication(database_url: str, batch_size: int = BATCH_SIZE_DEFAULT, dry_run: bool = False):
    """Main deduplication routine."""
    logger.info("Starting Health_Readings deduplication")
    logger.info("Batch size: %d | Dry run: %s", batch_size, dry_run)
    
    conn = get_connection(database_url)
    conn.autocommit = False
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Count total duplicates before starting
            total_duplicates = count_duplicates(cur)
            logger.info("Total duplicate rows to remove: %d", total_duplicates)
            
            if total_duplicates == 0:
                logger.info("No duplicates found. Nothing to do.")
                return
            
            total_deleted = 0
            batch_num = 0
            
            while True:
                batch_num += 1
                start_time = time.monotonic()
                
                deleted = delete_batch(cur, batch_size, dry_run)
                
                if not dry_run:
                    conn.commit()
                
                elapsed = time.monotonic() - start_time
                total_deleted += deleted
                
                logger.info(
                    "Batch %d: deleted %d rows in %.3fs | total deleted: %d / %d",
                    batch_num, deleted, elapsed, total_deleted, total_duplicates,
                )
                
                if deleted == 0 or dry_run:
                    break
                
                # Small sleep to reduce load on prod DB
                time.sleep(0.05)
            
            if dry_run:
                logger.info("[DRY RUN] Would have deleted %d rows total (not committed)", total_deleted)
            else:
                # Final verification
                remaining = count_duplicates(cur)
                if remaining == 0:
                    logger.info("SUCCESS: All %d duplicate rows removed. No duplicates remain.", total_deleted)
                else:
                    logger.warning("WARNING: %d duplicates still remain after deduplication!", remaining)
    
    except Exception as e:
        conn.rollback()
        logger.exception("Deduplication failed: %s", e)
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Deduplicate Health_Readings table")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE_DEFAULT,
                        help=f"Rows per batch (default: {BATCH_SIZE_DEFAULT})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be deleted without actually deleting")
    args = parser.parse_args()
    
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable is not set.")
        sys.exit(1)
    
    run_deduplication(database_url, batch_size=args.batch_size, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
