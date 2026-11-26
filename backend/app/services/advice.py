"""Deterministic personalized health advice engine (metrics collection + rules)."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device
from app.models.health_reading import HealthReading
from app.schemas.advice import AdviceItem, AdviceSeverity
from app.schemas.goals import UserGoalsResponse
from app.services.dashboard import _as_date, build_daily_activity
from app.services.workouts import aware, day_start, finished_between

# ─────────────────────────────────────────────────────────────────────────────
# Rule thresholds (all numeric thresholds live here)
# ─────────────────────────────────────────────────────────────────────────────
WINDOW_DAYS = 7
HIGH_HR_THRESHOLD_BPM = 100.0
HR_RISE_RATIO_THRESHOLD = 0.10
SEDENTARY_STEPS_THRESHOLD = 3000
SEDENTARY_MIN_DAYS = 3
GOAL_STREAK_MIN_DAYS = 5
STEPS_BEHIND_AFTER_HOUR = 18
STEPS_BEHIND_RATIO = 0.50
BP_HIGH_SYSTOLIC = 140
BP_HIGH_DIASTOLIC = 90
NO_SYNC_HOURS_THRESHOLD = 24.0
MAX_ADVICE_ITEMS = 5

_BP_PATTERN = re.compile(r"^\s*(\d{2,3})\s*/\s*(\d{2,3})\s*$")
_SEVERITY_ORDER: dict[AdviceSeverity, int] = {"warning": 0, "info": 1, "success": 2}

_DISCLAIMER: dict[str, str] = {
    "en": "This is not medical advice.",
    "ru": "Это не медицинская рекомендация",
}

_TEMPLATES: dict[str, dict[str, tuple[str, str]]] = {
    "en": {
        "no_data": (
            "Connect your watch",
            "No activity or health readings have been recorded yet. Connect or sync your watch to unlock personalized insights.",
        ),
        "high_hr": (
            "Elevated 7-day heart rate",
            "Your 7-day average heart rate is {avg_hr_7d} bpm (above {threshold} bpm). Consider consulting a doctor if this persists.",
        ),
        "bp_high": (
            "Elevated blood pressure reading",
            "Your latest blood pressure reading was {systolic}/{diastolic} mmHg (at or above 140/90). Consider re-measuring at rest and consulting a doctor if it stays elevated.",
        ),
        "hr_rise": (
            "Heart rate trended up",
            "Your 7-day average heart rate ({avg_hr_7d} bpm) is {rise_pct}% higher than the previous 7 days ({avg_hr_prev_7d} bpm). Prioritize recovery and sleep.",
        ),
        "sedentary": (
            "Low-activity days this week",
            "{low_days} of the last 7 days had fewer than {threshold} steps. Short 10-minute walks can help break up sitting time.",
        ),
        "steps_behind_today": (
            "Behind today's step goal",
            "You have {steps_today} steps today ({pct_of_goal}% of your {steps_daily_goal} goal). An evening walk can help close the gap.",
        ),
        "no_workouts": (
            "No workouts logged this week",
            "You have 0 finished workouts in the last 7 days against your target of {workouts_weekly_goal}. Even one light session helps build momentum.",
        ),
        "no_sync": (
            "Watch sync is overdue",
            "No new data has arrived for {hours_since_last_sync} hours. Sync your watch or upload a fresh export to keep insights up to date.",
        ),
        "goal_streak": (
            "Strong step consistency",
            "You hit your {steps_daily_goal}-step daily goal on {hit_days} of the last 7 days. Great consistency!",
        ),
    },
    "ru": {
        "no_data": (
            "Подключите часы",
            "Данных о здоровье и активности пока нет. Подключите или синхронизируйте часы, чтобы получать персональные советы.",
        ),
        "high_hr": (
            "Повышенный средний пульс за 7 дней",
            "Средний пульс за последние 7 дней — {avg_hr_7d} уд/мин (выше {threshold} уд/мин). Если показатель держится, обратитесь к врачу.",
        ),
        "bp_high": (
            "Повышенное давление",
            "Последнее измерение давления — {systolic}/{diastolic} мм рт. ст. (от 140/90 и выше). Перемерьте в покое и обратитесь к врачу, если значения сохраняются.",
        ),
        "hr_rise": (
            "Пульс вырос за неделю",
            "Средний пульс за 7 дней ({avg_hr_7d} уд/мин) на {rise_pct}% выше прошлой недели ({avg_hr_prev_7d} уд/мин). Уделите внимание сну и восстановлению.",
        ),
        "sedentary": (
            "Малоподвижные дни на неделе",
            "{low_days} из 7 дней было меньше {threshold} шагов. Короткие прогулки по 10 минут помогут увеличить активность.",
        ),
        "steps_behind_today": (
            "Цель по шагам сегодня пока не достигнута",
            "Сегодня пройдено {steps_today} шагов ({pct_of_goal}% от цели {steps_daily_goal}). Вечерняя прогулка поможет наверстать темп.",
        ),
        "no_workouts": (
            "Нет тренировок за 7 дней",
            "За последние 7 дней не зафиксировано тренировок при цели {workouts_weekly_goal} в неделю. Попробуйте запланировать лёгкое занятие.",
        ),
        "no_sync": (
            "Часы давно не синхронизировались",
            "Новых данных не поступало уже {hours_since_last_sync} ч. Синхронизируйте часы или загрузите свежий экспорт.",
        ),
        "goal_streak": (
            "Отличная серия по шагам",
            "Цель в {steps_daily_goal} шагов выполнена {hit_days} из 7 дней. Отличная регулярность!",
        ),
    },
}


@dataclass(frozen=True)
class AdviceMetrics:
    """Anonymized 7-day aggregates used to evaluate deterministic advice rules."""

    has_any_data: bool
    avg_hr_7d: float | None
    avg_hr_prev_7d: float | None
    resting_hr_7d: float | None
    daily_steps_7d: list[int]
    days_without_data_7d: int
    workouts_count_7d: int
    latest_blood_pressure: str | None
    hours_since_last_sync: float | None
    steps_today: int
    current_hour: int
    steps_daily_goal: int
    workouts_weekly_goal: int


def resolve_lang(
    accept_language: str | None = None, lang_param: str | None = None
) -> Literal["en", "ru"]:
    """Resolve response language ('en' default, 'ru' supported)."""
    if lang_param:
        code = lang_param.strip().lower()
        if code.startswith("ru"):
            return "ru"
        if code.startswith("en"):
            return "en"

    if accept_language:
        best_lang: Literal["en", "ru"] = "en"
        best_q = -1.0
        for part in accept_language.split(","):
            tokens = [t.strip() for t in part.split(";") if t.strip()]
            if not tokens:
                continue
            tag = tokens[0].lower()
            q = 1.0
            for param in tokens[1:]:
                if param.startswith("q="):
                    try:
                        q = float(param[2:])
                    except ValueError:
                        q = 0.0
            if tag.startswith("ru") and q > best_q:
                best_lang = "ru"
                best_q = q
            elif tag.startswith("en") and q > best_q:
                best_lang = "en"
                best_q = q
        return best_lang

    return "en"


def get_disclaimer(lang: str) -> str:
    """Return fixed medical disclaimer in the requested language."""
    return _DISCLAIMER.get(lang, _DISCLAIMER["en"])


def parse_blood_pressure(bp: str | None) -> tuple[int, int] | None:
    """Parse 'SYS/DIA' blood pressure string; return None on malformed input."""
    if not bp or not isinstance(bp, str):
        return None
    match = _BP_PATTERN.match(bp)
    if not match:
        return None
    systolic = int(match.group(1))
    diastolic = int(match.group(2))
    if not (30 <= systolic <= 300 and 20 <= diastolic <= 200):
        return None
    return systolic, diastolic


async def collect_metrics(
    db: AsyncSession,
    user_id: int,
    goals: UserGoalsResponse,
    now: datetime | None = None,
) -> AdviceMetrics:
    """Collect SQL-aggregated 7-day metrics for `user_id` using core reading/workout tables."""
    current_dt = aware(now) if now is not None else datetime.now(timezone.utc)
    today = current_dt.date()
    first_day = today - timedelta(days=WINDOW_DAYS - 1)
    start_7d = day_start(first_day)
    end_today = day_start(today + timedelta(days=1))
    start_14d = day_start(first_day - timedelta(days=WINDOW_DAYS))

    workouts = await finished_between(db, user_id, first_day, today)
    daily_activity = await build_daily_activity(db, user_id, first_day, today, workouts)
    daily_steps_7d = [d.steps for d in daily_activity]
    steps_today = daily_activity[-1].steps if daily_activity else 0

    avg_hr_7d_val = (
        await db.execute(
            select(func.avg(HealthReading.heart_rate_bpm))
            .join(Device, HealthReading.device_id == Device.device_id)
            .where(
                Device.user_id == user_id,
                HealthReading.date_time >= start_7d,
                HealthReading.date_time < end_today,
                HealthReading.heart_rate_bpm.is_not(None),
            )
        )
    ).scalar_one()
    avg_hr_prev_7d_val = (
        await db.execute(
            select(func.avg(HealthReading.heart_rate_bpm))
            .join(Device, HealthReading.device_id == Device.device_id)
            .where(
                Device.user_id == user_id,
                HealthReading.date_time >= start_14d,
                HealthReading.date_time < start_7d,
                HealthReading.heart_rate_bpm.is_not(None),
            )
        )
    ).scalar_one()

    conn = await db.connection()
    if conn.dialect.name == "sqlite":
        hour_bucket = func.strftime("%Y-%m-%d %H", HealthReading.date_time)
    else:
        hour_bucket = func.date_trunc("hour", HealthReading.date_time)

    hourly_subq = (
        select(func.avg(HealthReading.heart_rate_bpm).label("hour_avg"))
        .join(Device, HealthReading.device_id == Device.device_id)
        .where(
            Device.user_id == user_id,
            HealthReading.date_time >= start_7d,
            HealthReading.date_time < end_today,
            HealthReading.heart_rate_bpm.is_not(None),
        )
        .group_by(hour_bucket)
        .subquery()
    )
    resting_hr_val = (await db.execute(select(func.min(hourly_subq.c.hour_avg)))).scalar_one()

    latest_bp = (
        await db.execute(
            select(HealthReading.blood_pressure)
            .join(Device, HealthReading.device_id == Device.device_id)
            .where(
                Device.user_id == user_id,
                HealthReading.blood_pressure.is_not(None),
            )
            .order_by(HealthReading.date_time.desc(), HealthReading.reading_id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    total_readings, latest_reading_dt = (
        await db.execute(
            select(
                func.count(HealthReading.reading_id),
                func.max(HealthReading.date_time),
            )
            .join(Device, HealthReading.device_id == Device.device_id)
            .where(Device.user_id == user_id)
        )
    ).one()

    latest_device_sync = (
        await db.execute(
            select(func.max(Device.last_sync_time)).where(Device.user_id == user_id)
        )
    ).scalar_one()

    reading_day_rows = (
        await db.execute(
            select(func.distinct(func.date(HealthReading.date_time)))
            .join(Device, HealthReading.device_id == Device.device_id)
            .where(
                Device.user_id == user_id,
                HealthReading.date_time >= start_7d,
                HealthReading.date_time < end_today,
            )
        )
    ).scalars().all()
    active_days: set[date] = {_as_date(d) for d in reading_day_rows if d is not None}
    for w in workouts:
        active_days.add(aware(w.started_at).date())
    days_without_data_7d = max(0, WINDOW_DAYS - len(active_days))

    sync_candidates = [aware(dt) for dt in (latest_reading_dt, latest_device_sync) if dt is not None]
    if sync_candidates:
        last_sync = max(sync_candidates)
        hours_since_last_sync: float | None = round(
            max(0.0, (current_dt - last_sync).total_seconds() / 3600.0),
            1,
        )
    else:
        hours_since_last_sync = None

    has_any_data = (
        int(total_readings or 0) > 0
        or len(workouts) > 0
        or latest_device_sync is not None
    )

    return AdviceMetrics(
        has_any_data=has_any_data,
        avg_hr_7d=round(float(avg_hr_7d_val), 1) if avg_hr_7d_val is not None else None,
        avg_hr_prev_7d=(
            round(float(avg_hr_prev_7d_val), 1) if avg_hr_prev_7d_val is not None else None
        ),
        resting_hr_7d=round(float(resting_hr_val), 1) if resting_hr_val is not None else None,
        daily_steps_7d=daily_steps_7d,
        days_without_data_7d=days_without_data_7d,
        workouts_count_7d=len(workouts),
        latest_blood_pressure=latest_bp,
        hours_since_last_sync=hours_since_last_sync,
        steps_today=steps_today,
        current_hour=current_dt.hour,
        steps_daily_goal=goals.steps_daily,
        workouts_weekly_goal=goals.workouts_weekly,
    )


def _render_item(
    code: str,
    severity: AdviceSeverity,
    data: dict[str, Any],
    lang: str,
) -> AdviceItem:
    templates = _TEMPLATES.get(lang, _TEMPLATES["en"])
    title, text_tmpl = templates[code]
    return AdviceItem(
        code=code,
        severity=severity,
        title=title,
        text=text_tmpl.format(**data),
        data=data,
    )


def evaluate_rules(metrics: AdviceMetrics, lang: str = "en") -> list[AdviceItem]:
    """Pure deterministic rule engine converting `AdviceMetrics` into prioritized `AdviceItem`s."""
    norm_lang = "ru" if lang == "ru" else "en"
    if not metrics.has_any_data:
        return [_render_item("no_data", "info", {}, norm_lang)]

    candidates: list[AdviceItem] = []

    if metrics.avg_hr_7d is not None and metrics.avg_hr_7d > HIGH_HR_THRESHOLD_BPM:
        candidates.append(
            _render_item(
                "high_hr",
                "warning",
                {
                    "avg_hr_7d": round(metrics.avg_hr_7d, 1),
                    "threshold": int(HIGH_HR_THRESHOLD_BPM),
                },
                norm_lang,
            )
        )

    parsed_bp = parse_blood_pressure(metrics.latest_blood_pressure)
    if parsed_bp is not None:
        systolic, diastolic = parsed_bp
        if systolic >= BP_HIGH_SYSTOLIC or diastolic >= BP_HIGH_DIASTOLIC:
            candidates.append(
                _render_item(
                    "bp_high",
                    "warning",
                    {"systolic": systolic, "diastolic": diastolic},
                    norm_lang,
                )
            )

    if (
        metrics.avg_hr_7d is not None
        and metrics.avg_hr_prev_7d is not None
        and metrics.avg_hr_prev_7d > 0
        and metrics.avg_hr_7d > metrics.avg_hr_prev_7d * (1.0 + HR_RISE_RATIO_THRESHOLD)
    ):
        rise_pct = round(
            ((metrics.avg_hr_7d - metrics.avg_hr_prev_7d) / metrics.avg_hr_prev_7d) * 100.0,
            1,
        )
        candidates.append(
            _render_item(
                "hr_rise",
                "info",
                {
                    "avg_hr_7d": round(metrics.avg_hr_7d, 1),
                    "avg_hr_prev_7d": round(metrics.avg_hr_prev_7d, 1),
                    "rise_pct": rise_pct,
                },
                norm_lang,
            )
        )

    low_days = sum(1 for steps in metrics.daily_steps_7d if steps < SEDENTARY_STEPS_THRESHOLD)
    if low_days >= SEDENTARY_MIN_DAYS:
        candidates.append(
            _render_item(
                "sedentary",
                "info",
                {"low_days": low_days, "threshold": SEDENTARY_STEPS_THRESHOLD},
                norm_lang,
            )
        )

    if (
        metrics.current_hour >= STEPS_BEHIND_AFTER_HOUR
        and metrics.steps_today < metrics.steps_daily_goal * STEPS_BEHIND_RATIO
    ):
        pct_of_goal = round((metrics.steps_today / max(metrics.steps_daily_goal, 1)) * 100)
        candidates.append(
            _render_item(
                "steps_behind_today",
                "info",
                {
                    "steps_today": metrics.steps_today,
                    "steps_daily_goal": metrics.steps_daily_goal,
                    "pct_of_goal": pct_of_goal,
                },
                norm_lang,
            )
        )

    if metrics.workouts_weekly_goal > 0 and metrics.workouts_count_7d == 0:
        candidates.append(
            _render_item(
                "no_workouts",
                "info",
                {"workouts_weekly_goal": metrics.workouts_weekly_goal},
                norm_lang,
            )
        )

    if (
        metrics.hours_since_last_sync is not None
        and metrics.hours_since_last_sync > NO_SYNC_HOURS_THRESHOLD
    ):
        candidates.append(
            _render_item(
                "no_sync",
                "info",
                {"hours_since_last_sync": round(metrics.hours_since_last_sync, 1)},
                norm_lang,
            )
        )

    hit_days = sum(1 for steps in metrics.daily_steps_7d if steps >= metrics.steps_daily_goal)
    if hit_days >= GOAL_STREAK_MIN_DAYS:
        candidates.append(
            _render_item(
                "goal_streak",
                "success",
                {"hit_days": hit_days, "steps_daily_goal": metrics.steps_daily_goal},
                norm_lang,
            )
        )

    candidates.sort(key=lambda item: _SEVERITY_ORDER[item.severity])
    return candidates[:MAX_ADVICE_ITEMS]
