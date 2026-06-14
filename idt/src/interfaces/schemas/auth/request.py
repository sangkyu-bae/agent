"""Auth request schemas."""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    # agent-user-context: 회원가입 시 표시 이름 필수 (LLM 노출용)
    display_name: str = Field(..., min_length=1, max_length=100)


class AdminCreateUserRequest(BaseModel):
    """admin-user-registration: 관리자 직접 사용자 생성 요청."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    display_name: str = Field(..., min_length=1, max_length=100)
    position: Optional[str] = Field(None, max_length=50)
    employee_no: Optional[str] = Field(None, max_length=50)
    joined_at: Optional[date] = None
    role: Literal["user", "admin"] = "user"
    department_id: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
