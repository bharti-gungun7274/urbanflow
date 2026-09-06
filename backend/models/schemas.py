from typing import Optional
from pydantic import BaseModel, Field


class ValidationSaveRequest(BaseModel):
    point_id: int = Field(..., ge=1)
    reference_class: int = Field(..., ge=0, le=7)
    latitude: float
    longitude: float
    dynamic_world_class: Optional[int] = Field(default=None, ge=0, le=7)
