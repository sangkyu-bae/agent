"""Interviewer: LLM 기반 명확화 질문 생성 및 완성도 평가."""
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.application.agent_builder.interview_session_store import QAPair
from src.domain.agent_builder.tool_registry import TOOL_REGISTRY
from src.domain.logging.interfaces.logger_interface import LoggerInterface


class _QuestionsOutput(BaseModel):
    questions: list[str] = Field(description="사용자에게 물어볼 명확화 질문 목록 (3-5개)")


class _EvaluationOutput(BaseModel):
    sufficient: bool = Field(description="충분한 정보가 수집됐는지 여부")
    questions: list[str] = Field(default=[], description="부족한 경우 추가 질문 목록 (최대 3개)")


class Interviewer:
    """LLM Step0: 사용자 요청 → 명확화 질문 → 완성도 평가."""

    _QUESTIONS_PROMPT = """\
당신은 AI 에이전트 설계 전문가입니다.
사용자가 원하는 에이전트를 정확히 만들기 위해 추가 정보를 수집해야 합니다.

[사용 가능한 도구]
{tool_list}

[사용자 요청]
{user_request}

다음 항목 중 불명확한 부분에 대해 구체적인 질문을 3~5개 생성하세요:
- 처리할 구체적인 데이터/주제 (예: 어떤 분야? 어떤 기업? 특정 키워드?)
- 출력 방식 (파일명, 저장 경로, 형식, 시트 구성 등)
- 수집/처리 범위 (개수, 기간, 범위 등)
- 응답 스타일 (상세/간결, 언어, 포함할 정보 등)
- 특별한 제약사항 (필터링 조건, 예외 처리 등)

이미 명확한 항목은 질문하지 마세요.
"""

    _EVALUATION_PROMPT = """\
당신은 AI 에이전트 설계 전문가입니다.

[사용자 기본 요청]
{user_request}

[수집된 질문과 답변]
{qa_history}

위 정보로 정확한 에이전트를 만들기에 충분한지 판단하세요.
- 에이전트 목적, 사용할 도구, 출력 방식이 파악됐다면 충분합니다.
- 부족하다면 아직 파악되지 않은 중요한 항목만 추가 질문하세요 (최대 3개).
"""

    def __init__(self, llm: ChatOpenAI, logger: LoggerInterface) -> None:
        self._q_llm = llm.with_structured_output(_QuestionsOutput)
        self._e_llm = llm.with_structured_output(_EvaluationOutput)
        self._logger = logger

    async def generate_initial_questions(
        self, user_request: str, request_id: str
    ) -> list[str]:
        """초기 명확화 질문 생성."""
        self._logger.info("Interviewer generate_questions start", request_id=request_id)
        try:
            tool_list = "\n".join(
                f"- {meta.tool_id}: {meta.description}"
                for meta in TOOL_REGISTRY.values()
            )
            system = self._QUESTIONS_PROMPT.format(
                tool_list=tool_list, user_request=user_request
            )
            output: _QuestionsOutput = await self._q_llm.ainvoke([
                {"role": "system", "content": system},
                {"role": "user", "content": "위 요청에 대한 명확화 질문을 생성해주세요."},
            ])
            self._logger.info(
                "Interviewer generate_questions done",
                request_id=request_id,
                count=len(output.questions),
            )
            return output.questions
        except Exception as e:
            self._logger.error(
                "Interviewer generate_questions failed", exception=e, request_id=request_id
            )
            raise

    async def evaluate_and_get_followup(
        self,
        user_request: str,
        qa_pairs: list[QAPair],
        request_id: str,
    ) -> tuple[bool, list[str]]:
        """수집된 정보 완성도 평가 → 충분 여부 + 추가 질문."""
        self._logger.info("Interviewer evaluate start", request_id=request_id)
        try:
            qa_history = "\n".join(
                f"Q: {qa.question}\nA: {qa.answer}" for qa in qa_pairs
            )
            system = self._EVALUATION_PROMPT.format(
                user_request=user_request, qa_history=qa_history
            )
            output: _EvaluationOutput = await self._e_llm.ainvoke([
                {"role": "system", "content": system},
                {"role": "user", "content": "충분한지 평가해주세요."},
            ])
            self._logger.info(
                "Interviewer evaluate done",
                request_id=request_id,
                sufficient=output.sufficient,
            )
            return output.sufficient, output.questions
        except Exception as e:
            self._logger.error(
                "Interviewer evaluate failed", exception=e, request_id=request_id
            )
            raise

    def build_enriched_context(
        self, user_request: str, qa_pairs: list[QAPair]
    ) -> str:
        """수집된 Q&A를 풍부한 컨텍스트 문자열로 변환."""
        lines = [f"기본 요청: {user_request}"]
        for i, qa in enumerate(qa_pairs, 1):
            lines.append(f"Q{i}: {qa.question}")
            lines.append(f"A{i}: {qa.answer}")
        return "\n".join(lines)
