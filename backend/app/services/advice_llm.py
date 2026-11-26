"""Optional Anthropic LLM rephrasing layer with caching, privacy filtering, and fallback."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.advice_cache import AdviceCache
from app.models.user import User
from app.schemas.advice import AdviceItem, AdviceSource
from app.services.advice import AdviceMetrics
from app.services.workouts import aware

logger = logging.getLogger(__name__)

REFRESH_COOLDOWN_MINUTES = 10
MAX_LLM_TEXT_LENGTH = 400
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


class RefreshRateLimitError(Exception):
    """Raised when ?refresh=true is requested more than once per 10 minutes."""


class LlmClient(Protocol):
    """Minimal async LLM completion interface for dependency injection and testing."""

    async def complete(self, system: str, user: str) -> str: ...


class AnthropicLlmClient:
    """Async Anthropic Messages API client over httpx."""

    def __init__(self, api_key: str, model: str, timeout_s: float) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s

    async def complete(self, system: str, user: str) -> str:
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }
        body = {
            "model": self._model,
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            resp = await client.post(ANTHROPIC_MESSAGES_URL, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()

        parts = [
            block.get("text", "")
            for block in data.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(parts).strip()


def get_llm_client() -> LlmClient | None:
    """FastAPI dependency returning an LLM client when enabled and configured."""
    if not settings.ADVICE_LLM_ENABLED or not settings.ADVICE_LLM_API_KEY.strip():
        return None
    return AnthropicLlmClient(
        api_key=settings.ADVICE_LLM_API_KEY,
        model=settings.ADVICE_LLM_MODEL,
        timeout_s=settings.ADVICE_LLM_TIMEOUT_S,
    )


class _LlmAdviceItem(BaseModel):
    code: str
    text: str

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("LLM advice text cannot be empty.")
        if len(cleaned) > MAX_LLM_TEXT_LENGTH:
            raise ValueError("LLM advice text exceeds max length.")
        if "http" in cleaned.lower():
            raise ValueError("LLM advice text must not contain URLs.")
        return cleaned


class _LlmAdviceOutput(BaseModel):
    items: list[_LlmAdviceItem]


def build_llm_payload(
    metrics: AdviceMetrics, rules_items: list[AdviceItem], lang: str
) -> dict:
    """Build strictly anonymized aggregates + rule items payload (zero PII or raw readings)."""
    metrics_dict = asdict(metrics)
    return {
        "language": lang,
        "metrics": metrics_dict,
        "advice": [
            {
                "code": item.code,
                "severity": item.severity,
                "title": item.title,
                "text": item.text,
                "data": item.data,
            }
            for item in rules_items
        ],
    }


def compute_metrics_hash(
    metrics: AdviceMetrics, rules_items: list[AdviceItem], lang: str
) -> str:
    """Compute stable SHA-256 hash over anonymized aggregates, rules, and language."""
    metrics_dict = asdict(metrics)
    if metrics_dict["hours_since_last_sync"] is not None:
        # Bucket sync age to whole hours so sub-hour ticks reuse the cache within TTL.
        metrics_dict["hours_since_last_sync"] = int(metrics_dict["hours_since_last_sync"])
    canonical = {
        "lang": lang,
        "metrics": metrics_dict,
        "rules": [{"code": r.code, "severity": r.severity, "data": r.data} for r in rules_items],
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_system_prompt(lang: str) -> str:
    """Build system prompt constraining tone, safety, numbers, and JSON format."""
    target_language = "Russian" if lang == "ru" else "English"
    return (
        "You are a helpful fitness assistant. Rephrase the provided advice items in a friendly, "
        f"concise way in {target_language}.\n"
        "Strict rules:\n"
        "- Do not diagnose medical conditions, prescribe treatments, or recommend medications.\n"
        "- Do not invent or add any numbers that are not present in the input data.\n"
        "- When severity is 'warning', gently advise consulting a doctor.\n"
        "- Do not include URLs or links.\n"
        "- Keep each item's text under 400 characters.\n"
        "- Respond strictly with valid JSON matching: "
        '{"items":[{"code":"...","text":"..."}]} with exactly one item per input code and no extra codes.'
    )


def _validate_and_merge(raw_response: str, rules_items: list[AdviceItem]) -> list[AdviceItem]:
    parsed_json = json.loads(raw_response.strip())
    validated = _LlmAdviceOutput.model_validate(parsed_json)

    expected_codes = [item.code for item in rules_items]
    returned_codes = [item.code for item in validated.items]
    if len(returned_codes) != len(expected_codes) or set(returned_codes) != set(expected_codes):
        raise ValueError("LLM response codes do not match expected advice codes.")

    by_code = {item.code: item.text for item in validated.items}
    return [
        item.model_copy(update={"text": by_code[item.code]})
        for item in rules_items
    ]


async def generate_advice(
    db: AsyncSession,
    user: User,
    metrics: AdviceMetrics,
    rules_items: list[AdviceItem],
    lang: str,
    refresh: bool,
    llm_client: LlmClient | None,
    now: datetime | None = None,
) -> tuple[list[AdviceItem], AdviceSource]:
    """Return AI-rephrased advice when enabled, consented, and valid; otherwise rules fallback."""
    current_dt = aware(now) if now is not None else datetime.now(timezone.utc)

    if refresh:
        last_refresh = (
            await db.execute(
                select(func.max(AdviceCache.last_refresh_at)).where(
                    AdviceCache.user_id == user.user_id
                )
            )
        ).scalar_one()
        if last_refresh is not None:
            elapsed = current_dt - aware(last_refresh)
            if elapsed < timedelta(minutes=REFRESH_COOLDOWN_MINUTES):
                raise RefreshRateLimitError("Advice refresh is limited to once every 10 minutes.")

    if (
        not settings.ADVICE_LLM_ENABLED
        or llm_client is None
        or not user.ai_advice_consent
        or not rules_items
    ):
        return rules_items, "rules"

    metrics_hash = compute_metrics_hash(metrics, rules_items, lang)
    cache_row = await db.get(AdviceCache, (user.user_id, lang))

    if (
        not refresh
        and cache_row is not None
        and cache_row.metrics_hash == metrics_hash
        and (current_dt - aware(cache_row.created_at)) < timedelta(minutes=settings.ADVICE_CACHE_TTL_MIN)
    ):
        try:
            cached_items = [AdviceItem.model_validate(item) for item in cache_row.payload]
            if [i.code for i in cached_items] == [i.code for i in rules_items]:
                return cached_items, "ai"
        except (ValidationError, TypeError, ValueError):
            logger.warning("Invalid cached advice payload; regenerating.")

    system_prompt = build_system_prompt(lang)
    user_prompt = json.dumps(build_llm_payload(metrics, rules_items, lang), ensure_ascii=False)

    try:
        raw = await llm_client.complete(system_prompt, user_prompt)
        ai_items = _validate_and_merge(raw, rules_items)
    except (httpx.HTTPError, TimeoutError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        logger.warning("LLM advice generation failed (%s); falling back to rules.", type(exc).__name__)
        if refresh and cache_row is not None:
            cache_row.last_refresh_at = current_dt
            await db.commit()
        return rules_items, "rules"
    except Exception as exc:
        logger.warning("Unexpected LLM advice error (%s); falling back to rules.", type(exc).__name__)
        if refresh and cache_row is not None:
            cache_row.last_refresh_at = current_dt
            await db.commit()
        return rules_items, "rules"

    serialized = [item.model_dump() for item in ai_items]
    if cache_row is None:
        cache_row = AdviceCache(
            user_id=user.user_id,
            lang=lang,
            metrics_hash=metrics_hash,
            payload=serialized,
            created_at=current_dt,
            last_refresh_at=current_dt if refresh else None,
        )
        db.add(cache_row)
    else:
        cache_row.metrics_hash = metrics_hash
        cache_row.payload = serialized
        cache_row.created_at = current_dt
        if refresh:
            cache_row.last_refresh_at = current_dt
    await db.commit()
    return ai_items, "ai"
