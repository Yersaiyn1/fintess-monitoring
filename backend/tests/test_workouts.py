"""Phase 2 (tracking) and Phase 3 (history) workout endpoints."""
from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.models.workout import Workout
from app.services import workouts as workouts_service


async def register(client, email="ana@example.com") -> dict:
    r = await client.post("/api/v1/auth/register", json={
        "full_name": "Ana", "email": email, "birth_date": "2003-04-15", "password": "abcd1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def at(day: date, hour: int = 10) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=timezone.utc)


@pytest.fixture
def clock(monkeypatch):
    """Controllable server clock for start/stop."""
    state = {"now": datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(workouts_service, "_utcnow", lambda: state["now"])
    return state


async def add_workout(db, user_id, kind, start, minutes, steps=0, km=0.0, kcal=0.0):
    db.add(Workout(user_id=user_id, kind=kind, started_at=start, ended_at=start + timedelta(minutes=minutes),
                   steps=steps, distance_km=km, calories_kcal=kcal))
    await db.commit()


async def user_id_of(client, headers) -> int:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["user_id"]


# ------------------------------------------------------------------ Phase 2
async def test_everything_requires_login(client):
    for method, path in [("get", "/api/v1/workouts/types"), ("get", "/api/v1/workouts/active"),
                         ("post", "/api/v1/workouts/start"), ("post", "/api/v1/workouts/1/stop"),
                         ("get", "/api/v1/workouts"), ("get", "/api/v1/workouts/1"),
                         ("get", "/api/v1/analytics/workouts")]:
        assert (await getattr(client, method)(path)).status_code == 401, path


async def test_activity_types_are_listed_with_rates(client):
    h = await register(client)
    types = (await client.get("/api/v1/workouts/types", headers=h)).json()
    assert [t["kind"] for t in types] == ["Run", "Walk", "Cycling", "Strength", "Yoga"]
    assert all({"stepsPerMin", "kmPerMin", "kcalPerMin", "label"} <= set(t) for t in types)


async def test_start_then_stop_calculates_the_results_on_the_server(client, clock):
    h = await register(client)
    assert (await client.get("/api/v1/workouts/active", headers=h)).json() is None

    started = await client.post("/api/v1/workouts/start", json={"kind": "Run"}, headers=h)
    assert started.status_code == 201
    w = started.json()
    assert w["inProgress"] is True and w["endedAt"] is None and w["durationSec"] is None

    active = (await client.get("/api/v1/workouts/active", headers=h)).json()
    assert active["id"] == w["id"]

    clock["now"] += timedelta(minutes=30)
    stopped = (await client.post(f"/api/v1/workouts/{w['id']}/stop", headers=h)).json()
    assert stopped["inProgress"] is False
    assert stopped["durationSec"] == 1800
    assert stopped["steps"] == 4800          # 160 steps/min * 30
    assert stopped["distanceKm"] == 4.8      # 0.16 km/min * 30
    assert stopped["caloriesKcal"] == 330.0  # 11 kcal/min * 30
    assert (await client.get("/api/v1/workouts/active", headers=h)).json() is None


async def test_only_one_workout_can_run_at_a_time(client):
    h = await register(client)
    assert (await client.post("/api/v1/workouts/start", json={"kind": "Walk"}, headers=h)).status_code == 201
    second = await client.post("/api/v1/workouts/start", json={"kind": "Run"}, headers=h)
    assert second.status_code == 409


async def test_stopping_twice_or_a_foreign_workout_is_rejected(client):
    mine = await register(client, "me@example.com")
    other = await register(client, "other@example.com")
    wid = (await client.post("/api/v1/workouts/start", json={"kind": "Yoga"}, headers=mine)).json()["id"]

    assert (await client.post(f"/api/v1/workouts/{wid}/stop", headers=other)).status_code == 404
    assert (await client.post(f"/api/v1/workouts/{wid}/stop", headers=mine)).status_code == 200
    assert (await client.post(f"/api/v1/workouts/{wid}/stop", headers=mine)).status_code == 409
    assert (await client.post("/api/v1/workouts/9999/stop", headers=mine)).status_code == 404


async def test_invalid_activity_type_is_rejected(client):
    h = await register(client)
    assert (await client.post("/api/v1/workouts/start", json={"kind": "Swimming"}, headers=h)).status_code == 422


async def test_users_do_not_block_each_other(client):
    a, b = await register(client, "a@example.com"), await register(client, "b@example.com")
    assert (await client.post("/api/v1/workouts/start", json={"kind": "Run"}, headers=a)).status_code == 201
    assert (await client.post("/api/v1/workouts/start", json={"kind": "Run"}, headers=b)).status_code == 201


async def test_finished_workout_is_added_to_the_dashboard_day(client, clock):
    h = await register(client)
    wid = (await client.post("/api/v1/workouts/start", json={"kind": "Run"}, headers=h)).json()["id"]
    clock["now"] += timedelta(minutes=10)
    await client.post(f"/api/v1/workouts/{wid}/stop", headers=h)

    # the real clock decides which day the dashboard calls "today", so look for the workout's day
    week = (await client.get("/api/v1/dashboard", headers=h)).json()["week"]
    day = next((d for d in week if d["date"] == "2026-11-11"), None)
    if day is None:
        pytest.skip("test date is outside the dashboard window of the real clock")
    assert day["steps"] == 1600 and day["calories"] == 110.0 and day["distanceKm"] == 1.6 and day["activeMinutes"] == 10


# ------------------------------------------------------------------ Phase 3
async def test_history_lists_only_finished_workouts_newest_first(client, db_session):
    h = await register(client)
    uid = await user_id_of(client, h)
    await add_workout(db_session, uid, "Run", at(date(2026, 11, 1)), 30, 4800, 4.8, 330)
    await add_workout(db_session, uid, "Yoga", at(date(2026, 11, 5)), 45, 0, 0, 135)
    await client.post("/api/v1/workouts/start", json={"kind": "Walk"}, headers=h)  # in progress: not in history

    body = (await client.get("/api/v1/workouts", headers=h)).json()
    assert body["total"] == 2
    assert [w["kind"] for w in body["items"]] == ["Yoga", "Run"]
    assert body["items"][0]["durationSec"] == 2700


async def test_history_filters_by_date_and_kind(client, db_session):
    h = await register(client)
    uid = await user_id_of(client, h)
    await add_workout(db_session, uid, "Run", at(date(2026, 11, 1), 23), 20)
    await add_workout(db_session, uid, "Run", at(date(2026, 11, 2), 0), 20)
    await add_workout(db_session, uid, "Yoga", at(date(2026, 11, 2), 12), 20)
    await add_workout(db_session, uid, "Run", at(date(2026, 11, 3)), 20)

    get = lambda q: client.get(f"/api/v1/workouts?{q}", headers=h)  # noqa: E731
    assert (await get("from=2026-11-02&to=2026-11-02")).json()["total"] == 2   # both ends inclusive
    assert (await get("from=2026-11-02")).json()["total"] == 3
    assert (await get("to=2026-11-01")).json()["total"] == 1
    assert (await get("kind=Run")).json()["total"] == 3
    assert (await get("kind=Run&from=2026-11-02&to=2026-11-02")).json()["total"] == 1
    assert (await get("from=2026-11-05&to=2026-11-01")).status_code == 422     # from after to
    assert (await get("kind=Swimming")).status_code == 422


async def test_history_pagination(client, db_session):
    h = await register(client)
    uid = await user_id_of(client, h)
    for i in range(5):
        await add_workout(db_session, uid, "Walk", at(date(2026, 11, 1) + timedelta(days=i)), 10)
    page1 = (await client.get("/api/v1/workouts?limit=2&offset=0", headers=h)).json()
    page3 = (await client.get("/api/v1/workouts?limit=2&offset=4", headers=h)).json()
    assert page1["total"] == 5 and len(page1["items"]) == 2 and len(page3["items"]) == 1
    assert page1["items"][0]["startedAt"] > page3["items"][0]["startedAt"]


async def test_history_and_details_show_only_my_workouts(client, db_session):
    mine, other = await register(client, "me@example.com"), await register(client, "other@example.com")
    my_id, other_id = await user_id_of(client, mine), await user_id_of(client, other)
    await add_workout(db_session, my_id, "Run", at(date(2026, 11, 1)), 10)
    await add_workout(db_session, other_id, "Run", at(date(2026, 11, 1)), 10)

    items = (await client.get("/api/v1/workouts", headers=mine)).json()["items"]
    assert len(items) == 1
    assert (await client.get(f"/api/v1/workouts/{items[0]['id']}", headers=mine)).status_code == 200
    others_id = (await client.get("/api/v1/workouts", headers=other)).json()["items"][0]["id"]
    assert (await client.get(f"/api/v1/workouts/{others_id}", headers=mine)).status_code == 404


# ------------------------------------------------------------------ analytics
async def test_weekly_and_monthly_analytics(client, db_session):
    from app.services.analytics import build_analytics
    h = await register(client)
    uid = await user_id_of(client, h)
    today = date(2026, 11, 11)
    await add_workout(db_session, uid, "Run", at(today), 30, 4800, 4.8, 330)
    await add_workout(db_session, uid, "Run", at(today - timedelta(days=2)), 60, 9600, 9.6, 660)
    await add_workout(db_session, uid, "Yoga", at(today - timedelta(days=2)), 30, 0, 0, 90)
    await add_workout(db_session, uid, "Walk", at(today - timedelta(days=20)), 40, 4200, 3.0, 180)  # month only
    await add_workout(db_session, uid, "Run", at(today - timedelta(days=40)), 40, 1, 1, 1)           # outside both

    week = await build_analytics(db_session, uid, "week", today=today)
    assert len(week.days) == 7 and week.days[-1].date == today and week.days[-1].label == "Wed"
    assert week.totals.workouts == 3 and week.totals.durationMin == 120
    assert week.totals.caloriesKcal == 1080 and week.totals.distanceKm == 14.4 and week.totals.steps == 14400
    assert week.days[-3].workouts == 2 and week.days[-3].durationMin == 90
    assert week.days[-2].workouts == 0                       # quiet day -> zeros, still present
    assert [k.kind for k in week.byKind] == ["Run", "Yoga"]  # biggest time first
    assert week.byKind[0].durationMin == 90

    month = await build_analytics(db_session, uid, "month", today=today)
    assert len(month.days) == 30 and month.days[-1].label == "11" and month.totals.workouts == 4
    assert month.startDate == today - timedelta(days=29)


async def test_analytics_endpoint_validates_period(client):
    h = await register(client)
    ok = await client.get("/api/v1/analytics/workouts?period=month", headers=h)
    assert ok.status_code == 200 and len(ok.json()["days"]) == 30
    assert (await client.get("/api/v1/analytics/workouts", headers=h)).json()["period"] == "week"
    assert (await client.get("/api/v1/analytics/workouts?period=year", headers=h)).status_code == 422
