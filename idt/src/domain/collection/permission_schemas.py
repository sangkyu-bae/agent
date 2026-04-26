from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class CollectionScope(str, Enum):
    PERSONAL = "PERSONAL"
    DEPARTMENT = "DEPARTMENT"
    PUBLIC = "PUBLIC"


@dataclass
class CollectionPermission:
    collection_name: str
    owner_id: int
    scope: CollectionScope
    department_id: Optional[str] = None
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
