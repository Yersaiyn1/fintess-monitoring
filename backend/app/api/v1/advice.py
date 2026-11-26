from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.schemas.advice import AdviceConsentRequest, AdviceConsentResponse, AdviceResponse
from app.services.advice import collect_metrics, evaluate_rules, get_disclaimer, resolve_lang
from app.services.advice_llm import (
    LlmClient,
    RefreshRateLimitError,
    generate_advice,
    get_llm_client,
)
from app.services.goals import get_user_goals

router = APIRouter()


@router.get("", response_model=AdviceResponse, summary="Get personalized health advice")
async def read_advice(
    lang: str | None = Query(default=None),
    refresh: bool = Query(default=False),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    llm_client: LlmClient | None = Depends(get_llm_client),
) -> AdviceResponse:
    """Return personalized rule-based (or optionally AI-rephrased) health advice."""
    resolved_lang = resolve_lang(accept_language=accept_language, lang_param=lang)
    goals = await get_user_goals(db, user.user_id)
    metrics = await collect_metrics(db, user.user_id, goals)
    rules_items = evaluate_rules(metrics, lang=resolved_lang)

    try:
        items, source = await generate_advice(
            db=db,
            user=user,
            metrics=metrics,
            rules_items=rules_items,
            lang=resolved_lang,
            refresh=refresh,
            llm_client=llm_client,
        )
    except RefreshRateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc

    ai_available = bool(settings.ADVICE_LLM_ENABLED and llm_client is not None)
    return AdviceResponse(
        items=items,
        source=source,
        generated_at=datetime.now(timezone.utc),
        disclaimer=get_disclaimer(resolved_lang),
        ai_available=ai_available,
        ai_consent=bool(user.ai_advice_consent),
    )


@router.put(
    "/consent",
    response_model=AdviceConsentResponse,
    summary="Update AI advice rephrasing consent",
)
async def update_advice_consent(
    payload: AdviceConsentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdviceConsentResponse:
    """Enable or disable AI phrasing consent for the current user."""
    user.ai_advice_consent = payload.enabled
    await db.commit()
    await db.refresh(user)
    return AdviceConsentResponse(enabled=bool(user.ai_advice_consent))
