"""부정 피드백 드릴다운 응답 (negative-feedback-drilldown Design §4.4).

Plan FR-06: 허용 필드만 선언해 user_id·session_id가 응답에 실리지 않게 한다.
"""
from pydantic import BaseModel

from src.application.agent_run.use_cases.get_message_retrievals_use_case import (
    MessageRetrievalsDto,
)
from src.application.eval.drilldown_use_case import NegativeDrilldownDto
from src.interfaces.schemas.agent_run_response import (
    MessageRetrievalsResponse,
    MessageRunRetrievalsDto,
)


class NegativeDrilldownResponse(BaseModel):
    message_id: int
    agent_id: str
    question: str | None = None
    answer: str
    runs: list[MessageRunRetrievalsDto] = []

    @classmethod
    def from_dto(cls, dto: NegativeDrilldownDto) -> "NegativeDrilldownResponse":
        # 런·근거 변환은 기존 응답을 통과시켜 복제하지 않는다
        converted = MessageRetrievalsResponse.from_dto(
            MessageRetrievalsDto(message_id=dto.message_id, runs=dto.runs)
        )
        return cls(
            message_id=dto.message_id,
            agent_id=dto.agent_id,
            question=dto.question,
            answer=dto.answer,
            runs=converted.runs,
        )
