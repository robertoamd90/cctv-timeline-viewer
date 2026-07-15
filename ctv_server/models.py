"""Modelli Pydantic per validazione richieste API."""

from pydantic import BaseModel, Field
from typing import Optional


class CameraCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Nome della telecamera")
    source_path: str = Field(..., min_length=1, description="Percorso sorgente delle registrazioni")
    timezone: str = Field(default="", description="Timezone (es. Europe/Rome). Vuoto = auto-detect dal sistema")
    indexing_mode: str = Field(default="partitioned", pattern="^(partitioned|full)$")
    directory_pattern: str = Field(default="{YYYY}/{MM}/{DD}", min_length=1)


class CameraUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    source_path: str = Field(..., min_length=1)
    timezone: str = Field(..., min_length=1)
    indexing_mode: str = Field(default="partitioned", pattern="^(partitioned|full)$")
    directory_pattern: str = Field(default="{YYYY}/{MM}/{DD}", min_length=1)


class CameraResponse(BaseModel):
    id: int
    name: str
    source_path: str
    timezone: str
    config: str = "{}"
    indexing_mode: str = "partitioned"
    directory_pattern: str = "{YYYY}/{MM}/{DD}"
    source_status: str = "unknown"
    source_error: Optional[str] = None
    last_scan_started: Optional[float] = None
    last_scan_completed: Optional[float] = None
    recordings_available: int = 0
    recordings_missing: int = 0


class ScanResult(BaseModel):
    status: str
    camera_id: Optional[int] = None
    cameras: Optional[int] = None
