from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RoutingReason(str, Enum):
    DOCUMENT_TYPE_MATCH = "document_type_match"
    LOW_CONFIDENCE_FALLBACK = "low_confidence_fallback"
    NO_ANALYSIS_FALLBACK = "no_analysis_fallback"
    CONFIG_OVERRIDE = "config_override"


class RoutingDecision(BaseModel):
    parser_type: str
    document_type: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    reason: RoutingReason
    is_fallback: bool

    model_config = {"frozen": True}
