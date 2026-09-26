"""Auth domain entities."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class UserStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class User:
    email: str
    password_hash: str
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.PENDING
    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Design Ref: mcp-identity-header §3.1 — 관리자가 지정한 사내 메일함 UPN.
    # 로그인 email 과 독립이며, 신원 헤더 MCP 호출의 클레임 소스가 된다.
    mailbox_upn: Optional[str] = None
