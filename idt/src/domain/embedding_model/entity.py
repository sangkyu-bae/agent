from dataclasses import dataclass
from datetime import datetime


@dataclass
class EmbeddingModel:
    id: int
    provider: str
    model_name: str
    display_name: str
    vector_dimension: int
    is_active: bool
    description: str | None
    created_at: datetime
    updated_at: datetime
