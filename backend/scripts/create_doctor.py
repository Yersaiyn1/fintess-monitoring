"""Administrative provisioning script for doctor accounts.

There is intentionally NO public doctor registration endpoint. Doctors are created
or have their initial login credentials assigned by an administrator via this script.

Usage examples (from `backend/` or repository root):
    # Create a new doctor or assign credentials to an existing doctor by license:
    python scripts/create_doctor.py \
        --license "LIC-KZ-001" \
        --email "elena.petrova@example.com" \
        --password "StrongPassword1" \
        --name "Dr. Elena Petrova" \
        --specialty "Cardiology"
"""
import argparse
import asyncio
import getpass
import re
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.doctor import Doctor  # noqa: E402

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_doctor_credentials(email: str, password: str) -> str:
    normalized_email = email.strip().lower()
    if not _EMAIL_RE.match(normalized_email) or len(normalized_email) > 255:
        raise ValueError("Invalid email address.")
    if len(password) < 8 or len(password) > 64:
        raise ValueError("Password must be between 8 and 64 characters.")
    if not (re.search(r"[^\W\d_]", password) and re.search(r"\d", password)):
        raise ValueError("Password must contain at least one letter and one digit.")
    return normalized_email


async def provision_doctor(
    db: AsyncSession,
    *,
    license_number: str,
    email: str,
    password: str,
    full_name: str | None = None,
    specialty: str | None = None,
    is_active: bool = True,
) -> Doctor:
    """Create a doctor or assign/update credentials for an existing doctor by license_number."""
    license_clean = license_number.strip()
    if not license_clean:
        raise ValueError("License number must not be blank.")
    normalized_email = validate_doctor_credentials(email, password)

    # Check if another doctor already owns this email.
    email_owner = (
        await db.execute(select(Doctor).where(Doctor.email == normalized_email))
    ).scalar_one_or_none()

    existing = (
        await db.execute(select(Doctor).where(Doctor.license_number == license_clean))
    ).scalar_one_or_none()

    if email_owner is not None and (existing is None or email_owner.doctor_id != existing.doctor_id):
        raise ValueError(f"A doctor with email '{normalized_email}' already exists.")

    pwd_hash = hash_password(password)

    if existing is not None:
        existing.email = normalized_email
        existing.password_hash = pwd_hash
        existing.is_active = is_active
        if full_name and full_name.strip():
            existing.full_name = full_name.strip()
        if specialty is not None:
            existing.specialty = specialty.strip() or None
        doctor = existing
    else:
        if not full_name or not full_name.strip():
            raise ValueError("--name is required when creating a new doctor.")
        doctor = Doctor(
            full_name=full_name.strip(),
            specialty=specialty.strip() if specialty and specialty.strip() else None,
            license_number=license_clean,
            email=normalized_email,
            password_hash=pwd_hash,
            is_active=is_active,
        )
        db.add(doctor)

    await db.commit()
    await db.refresh(doctor)
    return doctor


async def _run_cli(args: argparse.Namespace) -> None:
    password = args.password or getpass.getpass("Doctor password: ")
    async with AsyncSessionLocal() as session:
        doctor = await provision_doctor(
            session,
            license_number=args.license_number,
            email=args.email,
            password=password,
            full_name=args.name,
            specialty=args.specialty,
            is_active=not args.inactive,
        )
        print(
            f"Provisioned doctor: doctor_id={doctor.doctor_id} "
            f"license={doctor.license_number} email={doctor.email} active={doctor.is_active}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a doctor account or assign login credentials to an existing doctor."
    )
    parser.add_argument("--license", required=True, dest="license_number", help="Unique license number")
    parser.add_argument("--email", required=True, help="Doctor login email")
    parser.add_argument("--password", default=None, help="Login password (prompted if omitted)")
    parser.add_argument("--name", default=None, help="Full name (required for new doctors)")
    parser.add_argument("--specialty", default=None, help="Medical specialty")
    parser.add_argument("--inactive", action="store_true", help="Provision account in disabled state")
    args = parser.parse_args()
    try:
        asyncio.run(_run_cli(args))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
