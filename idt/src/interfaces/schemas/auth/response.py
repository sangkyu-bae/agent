"""Auth response schemas."""
from typing import Optional
from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    role: str
    status: str
    display_name: Optional[str] = None  # agent-user-context: 가입 후 노출


class PendingUserResponse(BaseModel):
    id: int
    email: str
    role: str
    created_at: Optional[str]  # ISO 8601


class AdminCreateUserResponse(BaseModel):
    """admin-user-registration: 관리자 생성 결과."""
    id: int
    email: str
    role: str
    status: str
    display_name: str
    position: Optional[str] = None
    employee_no: Optional[str] = None
    joined_at: Optional[str] = None  # ISO 8601 (date)
    department_id: Optional[str] = None


class AdminUserListItemResponse(BaseModel):
    id: int
    email: str
    role: str
    status: str
    display_name: Optional[str] = None
    position: Optional[str] = None
    department_names: list[str] = []
    created_at: Optional[str] = None  # ISO 8601


class AdminUserListResponse(BaseModel):
    items: list[AdminUserListItemResponse]
    total: int
