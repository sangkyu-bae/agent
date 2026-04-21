"""Department, UserDepartment 도메인 엔티티."""
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Department:
    id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class UserDepartment:
    user_id: int
    department_id: str
    is_primary: bool
    created_at: datetime
