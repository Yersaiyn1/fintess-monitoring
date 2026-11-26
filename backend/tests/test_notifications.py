from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.models.doctor import Doctor
from app.models.doctor_access import DoctorAccess
from app.models.user import User


URL = "/api/v1/notifications"


async def test_requires_login(client):
    response = await client.get(URL)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "start,end,own,visible",
    [
        (-5, 1, True, True),
        (-5, 7, True, True),
        (-5, 8, True, False),
        (-5, 0, True, False),
        (-5, -1, True, False),
        (1, 5, True, False),
        (-5, 3, False, False),
    ],
    ids=["tomorrow", "seven-days", "eight-days", "ends-today", "expired",
         "not-started", "other-patient"],
)
async def test_reminder_window(client, db_session, start, end, own, visible):
    registration = await client.post("/api/v1/auth/register", json={
        "full_name": "Alice", "birth_date": "2000-01-01",
        "email": "alice@example.com", "password": "Demo1234",
    })
    assert registration.status_code == 201
    account = registration.json()
    today = await db_session.scalar(select(func.current_date()))
    other = User(full_name="Bob", email="bob@example.com", birth_date=date(2000, 1, 1))
    doctor = Doctor(full_name="Dr Kim", license_number="LIC-TEST")
    db_session.add_all([other, doctor])
    await db_session.flush()
    expires = today + timedelta(days=end)
    db_session.add(DoctorAccess(
        user_id=account["user"]["user_id"] if own else other.user_id,
        doctor_id=doctor.doctor_id,
        access_start=today + timedelta(days=start),
        access_end=expires,
    ))
    await db_session.commit()
    response = await client.get(URL, headers={"Authorization": "Bearer " + account["access_token"]})
    assert response.status_code == 200
    expected = [{"doctor_id": doctor.doctor_id, "doctor_name": "Dr Kim", "access_end": expires.isoformat(),
                 "days_left": end, "priority": "HIGH" if end <= 2 else "NORMAL", "is_read": False}]
    assert response.json() == (expected if visible else [])

    headers = {"Authorization": "Bearer " + account["access_token"]}
    mark = await client.post(f"{URL}/{doctor.doctor_id}/{expires}/read", headers=headers)
    assert mark.status_code == (204 if visible else 404)
    assert (await client.post(URL + "/read-all", headers=headers)).status_code == 204
    grant = await db_session.get(DoctorAccess, (account["user"]["user_id"] if own else other.user_id, doctor.doctor_id))
    await db_session.refresh(grant)
    assert grant.reminder_read_for == (expires if visible else None)
    if visible:
        assert (await client.get(URL, headers=headers)).json()[0]["is_read"] is True
