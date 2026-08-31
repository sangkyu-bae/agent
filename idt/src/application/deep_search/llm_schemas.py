"""LLM 구조화 출력 스키마 (Design §4.3).

`with_structured_output` 전용이므로 LLM에 결합된 자산 — domain이 아닌
application 계층에 둔다 (§9.4).

D19: OpenAI structured outputs(strict)는 모든 object에 `additionalProperties: false`와
전 키 `required`를 요구하므로 **열린 맵(`dict[str, str]`)을 표현할 수 없다**.
도메인은 계속 dict를 쓰되(AD-5 유지), LLM 경계에서만 key/value 목록으로 주고받고
`to_mapping()`으로 변환한다.
"""
from __future__ import annotations

from typing import Literal, Sequence

from pydantic import BaseModel, Field


class KeyValueOut(BaseModel):
    """열린 맵을 strict 스키마로 표현하기 위한 key/value 쌍 (D19)."""

    key: str = Field(description="속성 이름")
    value: str = Field(description="속성 값")


def to_mapping(pairs: Sequence[KeyValueOut] | None) -> dict[str, str]:
    """key/value 목록을 도메인 dict으로 변환. 빈 키는 버리고 뒤 값이 이긴다."""
    if not pairs:
        return {}
    return {p.key.strip(): p.value for p in pairs if p.key.strip()}


class RequirementOut(BaseModel):
    id: str = Field(description="요구 식별자 (r1, r2 …)")
    description: str = Field(description="찾아야 할 정보 단위 하나를 한 문장으로")
    constraints: list[KeyValueOut] = Field(
        default_factory=list,
        description=(
            "충족 조건 key/value 목록. 관례 key: entity(대상), metric(지표), "
            "period(시점), align(비교 정렬 규칙), count(개수), order(정렬). "
            "없으면 빈 목록"
        ),
    )


class QueryOut(BaseModel):
    requirement_id: str = Field(description="이 쿼리가 겨냥하는 요구 id")
    query: str = Field(description="검색 엔진에 보낼 쿼리 한 문장")


class SearchPlanOut(BaseModel):
    """plan 노드 산출 — 전략 판정 + 요구 분해 + 쿼리 생성 (D1)."""

    strategy: Literal["single", "parallel", "iterative"] = Field(
        description="single=한 번 검색으로 충분, parallel=독립 사실 여러 개, "
                    "iterative=후보 수집 후 항목별 확인이 필요",
    )
    requirements: list[RequirementOut] = Field(default_factory=list)
    queries: list[QueryOut] = Field(default_factory=list)
    reasoning: str = Field(default="", description="분해 근거")


class EvidenceOut(BaseModel):
    requirement_id: str = Field(description="이 근거가 채우는 요구 id")
    content: str = Field(description="검색 결과 원문에 근거한 사실 서술")
    source: str = Field(description="출처 URL 또는 기관명 — 원문에 없으면 이 근거를 만들지 말 것")
    confidence: float = Field(default=0.0, description="0.0~1.0 확신도")
    attrs: list[KeyValueOut] = Field(
        default_factory=list,
        description="선택 속성 key/value 목록. 관례 key: value, unit, period, entity",
    )


class EvidenceExtractOut(BaseModel):
    """extract 노드 산출 — 검색 결과에서 구조화한 근거 목록."""

    evidence: list[EvidenceOut] = Field(default_factory=list)


class RequirementVerdictOut(BaseModel):
    id: str
    satisfied: bool = Field(description="근거가 요구와 그 constraints를 모두 충족하면 true")
    reason: str = Field(default="", description="미충족이면 무엇이 부족한지")


class CoverageVerdictOut(BaseModel):
    """evaluate 노드 산출 — 충족 판정 + 재계획을 한 번에 (D2)."""

    requirements: list[RequirementVerdictOut] = Field(default_factory=list)
    complete: bool = Field(default=False, description="모든 요구가 충족되었는가")
    can_retry: bool = Field(
        default=True, description="다른 검색 전략이 남아 있으면 true, 없으면 false",
    )
    retry_reason: str = Field(default="", description="can_retry=false인 이유")
    next_queries: list[QueryOut] = Field(
        default_factory=list, description="미충족 요구만을 겨냥한 다음 쿼리",
    )
