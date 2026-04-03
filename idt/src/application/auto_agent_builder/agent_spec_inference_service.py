"""AgentSpecInferenceService: LLM으로 에이전트 명세 자동 추론."""
import json

from langchain_openai import ChatOpenAI

from src.domain.auto_agent_builder.schemas import AgentSpecResult, ConversationTurn
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_SYSTEM_PROMPT = """You are an expert at configuring AI agent pipelines.
Given a user's task description and available tools/middlewares,
determine the optimal agent configuration. Respond ONLY in valid JSON."""

_TOOL_DESCRIPTIONS = """Available tools:
- internal_document_search: 내부 벡터/ES 하이브리드 검색 (정책/지식베이스 질의)
- tavily_search: Tavily 웹 검색 (최신 외부 정보, 뉴스)
- excel_export: pandas Excel 파일 생성 (데이터 정리/보고서)
- python_code_executor: Python 코드 샌드박스 실행 (계산/데이터 처리)"""

_MIDDLEWARE_DESCRIPTIONS = """Available middlewares:
- summarization: 긴 대화 컨텍스트 자동 압축
- pii: 개인정보(이메일/신용카드) 자동 마스킹
- tool_retry: 실패 도구 자동 재시도
- model_call_limit: LLM 호출 횟수 제한 (비용 제어)
- model_fallback: 주 모델 실패 시 대체 모델 전환"""

_RESPONSE_FORMAT = """\nRespond in JSON:
{
  "confidence": 0.0-1.0,
  "tool_ids": ["..."],
  "middlewares": [{"type": "...", "config": {...}}],
  "system_prompt": "...",
  "clarifying_questions": [],
  "reasoning": "..."
}
Note: clarifying_questions must be empty if confidence >= 0.8."""


class AgentSpecInferenceService:

    def __init__(self, model_name: str, logger: LoggerInterface) -> None:
        self._model_name = model_name
        self._logger = logger

    async def infer(
        self,
        user_request: str,
        conversation_history: list[ConversationTurn],
        request_id: str,
        model_name: str | None = None,
    ) -> AgentSpecResult:
        self._logger.info(
            "AgentSpecInferenceService infer start",
            request_id=request_id,
            user_request=user_request[:100],
        )
        try:
            llm = ChatOpenAI(model=model_name or self._model_name, temperature=0)
            messages = self._build_messages(user_request, conversation_history)
            raw = await llm.ainvoke(messages)
            result = self._parse_response(raw.content, request_id)
            self._logger.info(
                "AgentSpecInferenceService infer done",
                request_id=request_id,
                confidence=result.confidence,
                tool_ids=result.tool_ids,
            )
            return result
        except Exception as e:
            self._logger.error(
                "AgentSpecInferenceService infer failed",
                exception=e,
                request_id=request_id,
            )
            raise

    def _build_messages(
        self,
        user_request: str,
        conversation_history: list[ConversationTurn],
    ) -> list[dict]:
        user_content = (
            f"{_TOOL_DESCRIPTIONS}\n\n"
            f"{_MIDDLEWARE_DESCRIPTIONS}\n\n"
            f"User request: {user_request!r}"
        )
        if conversation_history:
            history_lines = []
            for i, turn in enumerate(conversation_history, 1):
                for q, a in zip(turn.questions, turn.answers):
                    history_lines.append(f"[Round {i}] Q: {q}")
                    history_lines.append(f"[Round {i}] A: {a}")
            user_content += "\n\nAdditional context:\n" + "\n".join(history_lines)
        user_content += _RESPONSE_FORMAT
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _parse_response(self, content: str, request_id: str) -> AgentSpecResult:
        """LLM JSON 응답 파싱. 실패 시 ValueError."""
        try:
            text = content.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
        except (json.JSONDecodeError, IndexError) as e:
            self._logger.warning(
                "AgentSpecInferenceService JSON parse failed",
                request_id=request_id,
                raw=content[:200],
            )
            raise ValueError(f"LLM response is not valid JSON: {e}") from e

        return AgentSpecResult(
            confidence=float(data.get("confidence", 0.0)),
            tool_ids=data.get("tool_ids", []),
            middleware_configs=data.get("middlewares", []),
            system_prompt=data.get("system_prompt", ""),
            clarifying_questions=data.get("clarifying_questions", []),
            reasoning=data.get("reasoning", ""),
        )
