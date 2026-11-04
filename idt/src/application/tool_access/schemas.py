"""관리자 도구 권한 API 스키마.

Design Ref: tool-access-control §4.2 — tool_id 는 모두 카탈로그 표기.
"""
from typing import Literal

from pydantic import BaseModel, Field


class ExcludedToolInfo(BaseModel):
    """권한이 없어 제외된 도구 — 포크·실행 응답 공용 (§4.2 additive)."""

    tool_id: str
    name: str
    reason: Literal["no_permission"] = "no_permission"


class ToolAccessInfo(BaseModel):
    """에이전트에 붙은 도구의 현재 사용자 기준 허용 여부 — 상세 응답용 (FR-13)."""

    tool_id: str
    name: str
    permitted: bool


class ReplaceToolAccessRequest(BaseModel):
    """전체 교체 요청 — 저장 표기(`excel_export`)도 받아 정규화한다."""

    tool_ids: list[str] = Field(default_factory=list, max_length=1000)


class DefaultToolAccessResponse(BaseModel):
    tool_ids: list[str]


class DepartmentToolAccessResponse(BaseModel):
    department_id: str
    department_name: str
    tool_ids: list[str]
    default_tool_ids: list[str]


class ToolGrantSourceResponse(BaseModel):
    kind: Literal["default", "department"]
    department_id: str | None = None
    department_name: str | None = None


class InheritedToolAccessResponse(BaseModel):
    tool_id: str
    sources: list[ToolGrantSourceResponse]


class UserToolAccessResponse(BaseModel):
    user_id: int
    is_admin: bool
    tool_ids: list[str]
    inherited: list[InheritedToolAccessResponse]
