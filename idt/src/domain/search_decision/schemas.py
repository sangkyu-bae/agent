"""웹 검색 필요 판단 도메인 스키마."""

from pydantic import BaseModel, Field


class WebSearchDecision(BaseModel):
    """분석 답변에 외부(웹) 정보 보강이 필요한지에 대한 구조화 판단.

    LLM `with_structured_output`의 출력 스키마이자 도메인 VO로 함께 사용한다.
    """

    needs_web_search: bool = Field(
        ...,
        description=(
            "분석이 엑셀 데이터만으로 불충분해 최신/외부 정보가 필요하면 True"
        ),
    )
    reason: str = Field(default="", description="판단 근거(짧게)")
