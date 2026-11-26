from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

AdviceSeverity = Literal["info", "success", "warning"]
AdviceSource = Literal["ai", "rules"]


class AdviceItem(BaseModel):
    """Single personalized recommendation item."""

    code: str
    severity: AdviceSeverity
    title: str
    text: str
    data: dict[str, Any] = Field(default_factory=dict)


class AdviceResponse(BaseModel):
    """Response returned by GET /api/v1/advice."""

    items: list[AdviceItem]
    source: AdviceSource
    generated_at: datetime
    disclaimer: str
    ai_available: bool = False
    ai_consent: bool = False


class AdviceConsentRequest(BaseModel):
    """Payload for toggling AI rephrasing consent."""

    enabled: bool


class AdviceConsentResponse(BaseModel):
    """Current AI advice consent status."""

    enabled: bool
