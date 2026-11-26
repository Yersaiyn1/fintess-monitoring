"""Inspect an Android Health Connect export (.zip or .db) in read-only mode.

Usage:
    python scripts/inspect_hc_export.py path/to/health_connect_export.zip
"""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.hc_importer import EXPECTED_HC_TABLES, _extract_db_file  # noqa: E402


def inspect_hc_export(export_path: Path) -> str:
    """Inspect tables, columns, row counts, and missing expected columns in a Health Connect export."""
    if not export_path.is_file():
        raise FileNotFoundError(f"Export file not found: {export_path}")

    raw_bytes = export_path.read_bytes()
    lines: list[str] = [f"Inspecting: {export_path}"]

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = _extract_db_file(raw_bytes, export_path.name, tmpdir)
        sqlite_uri = Path(db_path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(sqlite_uri, uri=True)) as conn:
            cur = conn.cursor()
            existing_tables = {
                row[0]
                for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }

            lines.append("\n=== Importer Expected Tables ===")
            for table, spec in EXPECTED_HC_TABLES.items():
                if table not in existing_tables:
                    lines.append(f"- {table}: MISSING")
                    continue

                cols = [row[1] for row in cur.execute(f'PRAGMA table_info("{table}")').fetchall()]
                col_set = set(cols)
                row_count = cur.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

                missing: list[str] = []
                for req in spec["required"]:
                    if req not in col_set:
                        missing.append(req)
                ts_candidates = spec["ts_candidates"]
                if ts_candidates and not any(c in col_set for c in ts_candidates):
                    missing.append(f"timestamp({'/'.join(ts_candidates)})")
                for opt in spec["optional"]:
                    if opt not in col_set:
                        missing.append(f"{opt} (optional)")

                lines.append(f"- {table}: PRESENT ({row_count} rows)")
                lines.append(f"  columns: {', '.join(cols) if cols else '(none)'}")
                if missing:
                    lines.append(f"  missing expected columns: {', '.join(missing)}")
                else:
                    lines.append("  missing expected columns: none")

            extra_tables = sorted(existing_tables - set(EXPECTED_HC_TABLES))
            if extra_tables:
                lines.append("\n=== Other Tables in Export ===")
                for table in extra_tables:
                    row_count = cur.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                    lines.append(f"- {table}: {row_count} rows")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect tables, columns, and row counts of a Health Connect .zip or .db export (read-only)."
    )
    parser.add_argument("path", type=Path, help="Path to a Health Connect .zip or .db file.")
    args = parser.parse_args(argv)
    try:
        report = inspect_hc_export(args.path)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
