"""Pydantic schemas for conversation API endpoints.

These DTOs handle request/response validation for the interfaces layer.
"""
from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConversationMessageCreate(BaseModel):
    """Schema for creating a conversation message."""

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1)
    turn_index: int = Field(..., ge=1)

    @field_validator("user_id", "session_id", "content")
    @classmethod
    def not_empty_after_strip(cls, v: str) -> str:
        """Ensure fields are not empty after stripping whitespace."""
        if not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v


class ConversationMessageResponse(BaseModel):
    """Schema for conversation message response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    session_id: str
    role: str
    content: str
    turn_index: int
    created_at: datetime


class ConversationMessageListResponse(BaseModel):
    """Schema for list of conversation messages response."""

    messages: List[ConversationMessageResponse]
    total: int


class ConversationSummaryCreate(BaseModel):
    """Schema for creating a conversation summary."""

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1)
    session_id: str = Field(..., min_length=1)
    summary_content: str = Field(..., min_length=1)
    start_turn: int = Field(..., ge=1)
    end_turn: int = Field(..., ge=1)

    @field_validator("user_id", "session_id", "summary_content")
    @classmethod
    def not_empty_after_strip(cls, v: str) -> str:
        """Ensure fields are not empty after stripping whitespace."""
        if not v.strip():
            raise ValueError("Field cannot be empty or whitespace only")
        return v

    @model_validator(mode="after")
    def validate_turn_range(self) -> "ConversationSummaryCreate":
        """Validate that end_turn >= start_turn."""
        if self.end_turn < self.start_turn:
            raise ValueError("end_turn must be >= start_turn")
        return self


class ConversationSummaryResponse(BaseModel):
    """Schema for conversation summary response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    session_id: str
    summary_content: str
    start_turn: int
    end_turn: int
    created_at: datetime
