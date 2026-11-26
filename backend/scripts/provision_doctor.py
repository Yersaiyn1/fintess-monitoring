"""Create a doctor profile and provision its private login credentials.

Run only from a trusted admin workstation after the database migrations:
    python scripts/provision_doctor.py --name "Dr. Ada Smith" --license-number LIC-123
"""
import argparse
import asyncio
import getpass
import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from pydantic import EmailStr, TypeAdapter  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.doctor import Doctor  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Provision a doctor login account")
    parser.add_argument("--name", required=True, help="Doctor's full name")
    parser.add_argument("--license-number", required=True, help="Verified license number")
    parser.add_argument("--specialty", default=None, help="Optional specialty")
    args = parser.parse_args()
    if not args.name.strip() or not args.license_number.strip():
        parser.error("Name and license number must not be blank.")

    email = input("Doctor email: ").strip().lower()
    try:
        email = str(TypeAdapter(EmailStr).validate_python(email))
    except Exception:
        parser.error("Enter a valid email address.")

    password = getpass.getpass("Temporary password (8+ characters, include letters and digits): ")
    if len(password) < 8 or len(password) > 64 or not re.search(r"[^\W\d_]", password) or not re.search(r"\d", password):
        parser.error("Password must be 8-64 characters and contain a letter and a digit.")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        parser.error("Passwords do not match.")

    async with AsyncSessionLocal() as db:
        doctor = (await db.execute(
            select(Doctor).where(Doctor.license_number == args.license_number.strip())
        )).scalar_one_or_none()
        if doctor and (doctor.email or doctor.password_hash):
            parser.error("This doctor already has login credentials; refusing to overwrite them.")
        if doctor is None:
            doctor = Doctor(
                full_name=args.name.strip(),
                specialty=args.specialty.strip() if args.specialty else None,
                license_number=args.license_number.strip(),
            )
            db.add(doctor)
        doctor.email = email
        doctor.password_hash = hash_password(password)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            parser.error("That email or license number is already in use.")
        print(f"Doctor account provisioned for {doctor.full_name} (ID {doctor.doctor_id}).")


if __name__ == "__main__":
    asyncio.run(main())
