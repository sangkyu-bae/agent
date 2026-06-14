"""RolePermission, UserPermission 도메인 엔티티.

agent-user-context Design §3.

- RolePermission: role_permissions 테이블 — role(user/admin)이 기본으로 가지는 권한
- UserPermission: user_permissions 테이블 — 특정 user에 추가 부여된 권한
"""
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RolePermission:
    role: str
    permission_code: str


@dataclass(frozen=True)
class UserPermission:
    user_id: int
    permission_code: str
    granted_at: datetime
    granted_by: int | None  # 부여한 admin user_id (NULL 허용 — system grant)
