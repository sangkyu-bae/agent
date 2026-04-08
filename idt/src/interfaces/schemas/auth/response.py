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


class PendingUserResponse(BaseModel):
    id: int
    email: str
    role: str
    created_at: Optional[str]  # ISO 8601
