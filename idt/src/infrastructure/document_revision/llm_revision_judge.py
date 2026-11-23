"""LlmRevisionJudge — 두 문서 앞부분으로 '같은 문서의 개정인지' 판정.

Design Ref: document-revision §10.5 — 보조 LLM(UtilityLLMProviderPort) + structured output.
모델 미설정이면 None(llm_status=skipped). 호출 실패는 예외로 올려 호출부가 failed 처리한다.
"원칙: LLM은 제안, 사람이 확정" — 결과는 업로드 모달의 제안 근거로만 쓰인다.
"""
from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.domain.document_revision.interfaces import RevisionJudgePort
from src.domain.document_revision.value_objects import JudgeOutcome, LlmVerdict
from src.domain.llm.interfaces import UtilityLLMProviderPort
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_REASON_MAX = 200

_SYSTEM = (
    "당신은 문서 관리 담당자입니다. 두 문서의 파일명과 앞부분을 보고, 새 문서가 기존 문서의 "
    "개정판(같은 문서의 다른 판본)인지 판정합니다.\n"
    "- same_document_revision: 제목·목적·조문 구성이 같은 문서이고 내용이나 날짜·판수만 다름\n"
    "- different_document: 주제나 문서 종류가 다른 별개 문서(같은 분야의 다른 규정 포함)\n"
    "- uncertain: 앞부분만으로 판단할 근거가 부족함\n"
    "reason 에는 판단 근거를 한국어 한두 문장으로, 문서에 실제로 있는 표현을 들어 적습니다."
)

_HUMAN = (
    "[새 문서] 파일명: {new_filename}\n앞부분:\n{new_head}\n\n"
    "[기존 문서] 파일명: {candidate_filename}\n앞부분:\n{candidate_head}"
)


class RevisionJudgeOutput(BaseModel):
    verdict: Literal["same_document_revision", "different_document", "uncertain"]
    reason: str = Field(description="판단 근거 (한국어 1~2문장)")
    confidence: float = Field(ge=0.0, le=1.0)


class LlmRevisionJudge(RevisionJudgePort):
    def __init__(
        self, llm_provider: UtilityLLMProviderPort, logger: LoggerInterface
    ) -> None:
        self._provider = llm_provider
        self._logger = logger

    async def judge(
        self,
        *,
        new_filename: str,
        new_head: str,
        candidate_filename: str,
        candidate_head: str,
        request_id: str,
    ) -> JudgeOutcome | None:
        llm = await self._provider.get(0.0)
        if llm is None:
            self._logger.info("Revision judge skipped: no utility LLM", request_id=request_id)
            return None
        runnable = llm.with_structured_output(RevisionJudgeOutput)
        output: RevisionJudgeOutput = await runnable.ainvoke(
            [
                SystemMessage(content=_SYSTEM),
                HumanMessage(
                    content=_HUMAN.format(
                        new_filename=new_filename,
                        new_head=new_head,
                        candidate_filename=candidate_filename,
                        candidate_head=candidate_head,
                    )
                ),
            ]
        )
        return JudgeOutcome(
            verdict=LlmVerdict(output.verdict),
            reason=output.reason[:_REASON_MAX],
            confidence=output.confidence,
        )
