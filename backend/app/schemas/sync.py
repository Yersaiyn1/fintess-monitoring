from typing import Dict, List

from pydantic import BaseModel, Field, model_validator

from app.schemas.health_reading import HealthReadingCreate

MAX_SYNC_BATCH_SIZE = 1000


class SyncBatchRequest(BaseModel):
    device_id: int = Field(..., ge=1)
    readings: List[HealthReadingCreate] = Field(..., max_length=MAX_SYNC_BATCH_SIZE)

    @model_validator(mode="after")
    def _check_reading_device_ids(self) -> "SyncBatchRequest":
        for item in self.readings:
            if item.device_id is not None and item.device_id != self.device_id:
                raise ValueError(
                    f"Reading device_id ({item.device_id}) does not match batch device_id ({self.device_id})."
                )
        return self


class SyncBatchResponse(BaseModel):
    device_id: int
    synced_count: int
    skipped_count: int


class HealthConnectUploadResponse(BaseModel):
    filename: str
    total_parsed: int
    inserted: int
    duplicates_skipped: int
    metrics_breakdown: Dict[str, int]
