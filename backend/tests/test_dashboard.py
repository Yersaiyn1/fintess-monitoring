"""Tests for the dashboard endpoint and the weekly aggregation."""
from datetime import date, datetime, time, timedelta, timezone

from app.models.device import Device
from app.models.health_reading import HealthReading
from app.models.user import User
from app.services.dashboard import build_week

TODAY = date(2026, 11, 11)


def at(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=timezone.utc)


async def make_user_with_device(session, email: str, serial: str):
    user = User(full_name=email, email=email, birth_date=date(1990, 1, 1))
    session.add(user)
    await session.flush()
    device = Device(user_id=user.user_id, model="Band", serial_number=serial)
    session.add(device)
    await session.flush()
    return user, device


async def test_week_has_seven_days_with_zeros_when_no_data(db_session):
    user, _ = await make_user_with_device(db_session, "a@example.com", "SN1")
    week = await build_week(db_session, user.user_id, today=TODAY)
    assert len(week) == 7
    assert week[-1].date == TODAY and week[0].date == TODAY - timedelta(days=6)
    assert all(d.steps == 0 and d.calories == 0 and d.distanceKm == 0 for d in week)
    assert [d.label for d in week][-1] == "Wed"  # 11 Nov 2026 is a Wednesday


async def test_week_sums_readings_per_day_over_all_devices_of_the_user(db_session):
    user, dev1 = await make_user_with_device(db_session, "a@example.com", "SN1")
    dev2 = Device(user_id=user.user_id, model="Mini", serial_number="SN2")
    db_session.add(dev2)
    await db_session.flush()
    db_session.add_all([
        HealthReading(device_id=dev1.device_id, date_time=at(TODAY, 8), steps=1000, calories_kcal=50),
        HealthReading(device_id=dev1.device_id, date_time=at(TODAY, 9), steps=2000, calories_kcal=100.5),
        HealthReading(device_id=dev2.device_id, date_time=at(TODAY, 10), steps=500, calories_kcal=25),
        HealthReading(device_id=dev1.device_id, date_time=at(TODAY - timedelta(days=2), 12), steps=4000, calories_kcal=200),
    ])
    await db_session.commit()

    week = await build_week(db_session, user.user_id, today=TODAY)
    today, two_days_ago = week[-1], week[-3]
    assert today.steps == 3500
    assert today.calories == 175.5
    assert today.distanceKm == round(3500 * 0.00075, 2)
    assert today.activeMinutes == 35
    assert two_days_ago.steps == 4000
    assert week[-2].steps == 0  # yesterday: no readings -> zeros


async def test_week_ignores_other_users_and_older_than_seven_days(db_session):
    me, my_dev = await make_user_with_device(db_session, "me@example.com", "SN1")
    other, other_dev = await make_user_with_device(db_session, "other@example.com", "SN2")
    db_session.add_all([
        HealthReading(device_id=other_dev.device_id, date_time=at(TODAY, 8), steps=9999, calories_kcal=1),
        HealthReading(device_id=my_dev.device_id, date_time=at(TODAY - timedelta(days=7), 8), steps=7777, calories_kcal=1),
        HealthReading(device_id=my_dev.device_id, date_time=at(TODAY, 8), steps=100, calories_kcal=1),
    ])
    await db_session.commit()

    week = await build_week(db_session, me.user_id, today=TODAY)
    assert sum(d.steps for d in week) == 100


async def test_dashboard_endpoint_requires_login_and_matches_frontend_contract(client):
    assert (await client.get("/api/v1/dashboard")).status_code == 401

    token = (await client.post("/api/v1/auth/register", json={
        "full_name": "Ana", "email": "ana@example.com", "birth_date": "2003-04-15", "password": "abcd1234",
    })).json()["access_token"]
    r = await client.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["week"]) == 7
    # exactly the fields of the Angular `DailyActivity` interface
    assert set(body["week"][0]) == {"date", "label", "steps", "calories", "distanceKm", "activeMinutes"}


async def test_old_unauthenticated_path_with_user_id_is_gone(client):
    assert (await client.get("/api/v1/dashboard/1")).status_code in (404, 405)
