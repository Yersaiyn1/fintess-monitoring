from typing import Dict, List

from pydantic import BaseModel

from app.schemas.health_reading import HealthReadingCreate


class SyncBatchRequest(BaseModel):
    device_id: int
    readings: List[HealthReadingCreate]


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
