"""Grant administrator access to an existing patient account.

Run after applying migrations, from a trusted local admin workstation:
    python scripts/promote_admin.py --email admin@example.com
"""
import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Grant admin rights to an existing user")
    parser.add_argument("--email", required=True, help="Email of the existing patient account")
    args = parser.parse_args()
    email = args.email.strip().lower()
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(func.lower(User.email) == email))).scalar_one_or_none()
        if user is None:
            parser.error("No user with that email exists. Create the patient account first.")
        if user.is_admin:
            print(f"{user.email} already has administrator access.")
            return
        user.is_admin = True
        await db.commit()
        print(f"Administrator access granted to {user.email} (user ID {user.user_id}).")


if __name__ == "__main__":
    asyncio.run(main())
