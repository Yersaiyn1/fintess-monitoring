"""Unit tests for the deterministic personalized advice rule engine."""
import pytest

from app.services.advice import AdviceMetrics, evaluate_rules, parse_blood_pressure


def _metrics(**overrides) -> AdviceMetrics:
    defaults = {
        "has_any_data": True,
        "avg_hr_7d": 72.0,
        "avg_hr_prev_7d": 71.0,
        "resting_hr_7d": 60.0,
        "daily_steps_7d": [8000, 8000, 8000, 8000, 8000, 8000, 8000],
        "days_without_data_7d": 0,
        "workouts_count_7d": 2,
        "latest_blood_pressure": "120/80",
        "hours_since_last_sync": 2.0,
        "steps_today": 8000,
        "current_hour": 14,
        "steps_daily_goal": 10000,
        "workouts_weekly_goal": 3,
    }
    defaults.update(overrides)
    return AdviceMetrics(**defaults)


def test_no_data_short_circuits_other_rules():
    items = evaluate_rules(
        _metrics(
            has_any_data=False,
            avg_hr_7d=130.0,
            latest_blood_pressure="160/100",
            workouts_count_7d=0,
        ),
        lang="ru",
    )
    assert len(items) == 1
    assert items[0].code == "no_data"
    assert items[0].severity == "info"
    assert "часы" in items[0].text.lower()


@pytest.mark.parametrize(
    ("avg_hr", "expected"),
    [(99.9, False), (100.0, False), (100.1, True), (118.0, True)],
)
def test_high_hr_threshold(avg_hr: float, expected: bool):
    codes = [i.code for i in evaluate_rules(_metrics(avg_hr_7d=avg_hr))]
    assert ("high_hr" in codes) is expected


def test_high_hr_mentions_doctor_and_is_warning():
    items = evaluate_rules(_metrics(avg_hr_7d=112.5), lang="en")
    hr_item = next(i for i in items if i.code == "high_hr")
    assert hr_item.severity == "warning"
    assert "doctor" in hr_item.text.lower()
    assert hr_item.data["avg_hr_7d"] == 112.5


@pytest.mark.parametrize(
    ("curr", "prev", "expected"),
    [(77.0, 70.0, False), (77.1, 70.0, True), (85.0, None, False), (85.0, 0.0, False)],
)
def test_hr_rise_threshold(curr: float, prev: float | None, expected: bool):
    codes = [i.code for i in evaluate_rules(_metrics(avg_hr_7d=curr, avg_hr_prev_7d=prev))]
    assert ("hr_rise" in codes) is expected


@pytest.mark.parametrize(
    ("daily_steps", "expected"),
    [
        ([2999, 2999, 3000, 8000, 8000, 8000, 8000], False),
        ([2999, 2999, 2999, 8000, 8000, 8000, 8000], True),
    ],
)
def test_sedentary_threshold(daily_steps: list[int], expected: bool):
    codes = [i.code for i in evaluate_rules(_metrics(daily_steps_7d=daily_steps))]
    assert ("sedentary" in codes) is expected


@pytest.mark.parametrize(
    ("daily_steps", "expected"),
    [
        ([10000, 10000, 10000, 10000, 9999, 5000, 5000], False),
        ([10000, 10000, 10000, 10000, 10000, 5000, 5000], True),
    ],
)
def test_goal_streak_threshold(daily_steps: list[int], expected: bool):
    items = evaluate_rules(_metrics(daily_steps_7d=daily_steps, steps_daily_goal=10000))
    streak = [i for i in items if i.code == "goal_streak"]
    assert bool(streak) is expected
    if streak:
        assert streak[0].severity == "success"


@pytest.mark.parametrize(
    ("hour", "steps_today", "expected"),
    [(17, 1000, False), (18, 5000, False), (18, 4999, True), (22, 0, True)],
)
def test_steps_behind_today_threshold(hour: int, steps_today: int, expected: bool):
    codes = [
        i.code
        for i in evaluate_rules(
            _metrics(current_hour=hour, steps_today=steps_today, steps_daily_goal=10000)
        )
    ]
    assert ("steps_behind_today" in codes) is expected


@pytest.mark.parametrize(
    ("workouts_7d", "goal", "expected"),
    [(0, 0, False), (0, 3, True), (1, 3, False)],
)
def test_no_workouts_rule(workouts_7d: int, goal: int, expected: bool):
    codes = [
        i.code
        for i in evaluate_rules(
            _metrics(workouts_count_7d=workouts_7d, workouts_weekly_goal=goal)
        )
    ]
    assert ("no_workouts" in codes) is expected


@pytest.mark.parametrize(
    ("bp_raw", "parsed", "triggers_warning"),
    [
        ("140/85", (140, 85), True),
        ("130/90", (130, 90), True),
        ("139/89", (139, 89), False),
        (" 145 / 95 ", (145, 95), True),
        ("invalid", None, False),
        ("120", None, False),
        ("120/abc", None, False),
        ("999/999", None, False),
        (None, None, False),
    ],
)
def test_blood_pressure_parsing_and_rule(
    bp_raw: str | None, parsed: tuple[int, int] | None, triggers_warning: bool
):
    assert parse_blood_pressure(bp_raw) == parsed
    codes = [i.code for i in evaluate_rules(_metrics(latest_blood_pressure=bp_raw))]
    assert ("bp_high" in codes) is triggers_warning


@pytest.mark.parametrize(
    ("hours", "expected"),
    [(None, False), (24.0, False), (24.1, True)],
)
def test_no_sync_threshold(hours: float | None, expected: bool):
    codes = [i.code for i in evaluate_rules(_metrics(hours_since_last_sync=hours))]
    assert ("no_sync" in codes) is expected


def test_sorting_warning_info_success_and_max_five_limit():
    items = evaluate_rules(
        _metrics(
            avg_hr_7d=115.0,
            avg_hr_prev_7d=70.0,
            latest_blood_pressure="150/95",
            daily_steps_7d=[1000, 1000, 1000, 1000, 1000, 1000, 1000],
            workouts_count_7d=0,
            workouts_weekly_goal=3,
            hours_since_last_sync=48.0,
            current_hour=20,
            steps_today=1000,
        ),
        lang="ru",
    )
    assert len(items) == 5
    severities = [i.severity for i in items]
    assert severities[:2] == ["warning", "warning"]
    assert all(s == "info" for s in severities[2:])
