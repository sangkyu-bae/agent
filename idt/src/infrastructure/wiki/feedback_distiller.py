"""FeedbackWikiDistiller — 부정 평가(Q/A+이유)에서 팀 지식 초안 판정·정제 (wiki-feedback-loop §3-3).

WikiDistiller 동형: LLM 주입(테스트 mock), 운영은 from_openai 팩토리.
판정+정제를 LLM 1회로 통합 — worthy=false·파싱 실패·빈 필드는 None(강제 생성 금지).
"""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.application.wiki.interfaces import FeedbackWikiDistillerInterface
from src.application.wiki.schemas import FeedbackWikiDraft
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.wiki.policies import WikiPolicy

_SYSTEM_PROMPT = (
    "당신은 사용자 피드백에서 '팀 전체에 유효한 일반 지식'만 골라내는 심사자입니다.\n"
    "사용자가 AI 답변에 '싫어요'를 누르고 이유를 남겼습니다.\n"
    "다음에 해당하는 지식만 승격 대상입니다:\n"
    "- 용어의 정의·교정\n"
    "- 사실/수치의 교정 (이유에 근거가 있는 경우만)\n"
    "- 정책·규정·절차 지식\n"
    "규칙:\n"
    "- 개인 선호·일회성 불만·형식 불평은 승격 금지\n"
    "- 이유에 없는 원인이나 사실을 추측하지 마세요\n"
    "- 승격 가치가 없으면 {\"worthy\": false} 만 출력\n"
    "- 있으면 다음 JSON만 출력 (설명 금지):\n"
    '{"worthy": true, "title": "간결한 제목", "content": "위키 본문(사실 중심)", '
    '"confidence": 0~100}'
)
_TITLE_MAX = 200
_DEFAULT_CONFIDENCE = 0.5


def _coerce_text(content) -> str:
    """LLM content가 블록 리스트로 와도 문자열로 정규화 (wiki_distiller 선례)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            blk.get("text", "") if isinstance(blk, dict) else str(blk)
            for blk in content
        ]
        return "".join(parts)
    return str(content)


def _strip_code_fence(text: str) -> str:
    """```json ... ``` 코드펜스 제거 (memory extractor 선례)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


class FeedbackWikiDistiller(FeedbackWikiDistillerInterface):
    def __init__(self, llm, logger: LoggerInterface) -> None:
        self._llm = llm
        self._logger = logger

    @classmethod
    def from_openai(cls, model_name: str, api_key: str, logger: LoggerInterface):
        from langchain_openai import ChatOpenAI

        return cls(ChatOpenAI(model=model_name, api_key=api_key, temperature=0), logger)

    async def distill_feedback(
        self, question: str, answer: str, feedback_note: str, request_id: str,
    ) -> FeedbackWikiDraft | None:
        human = (
            f"[사용자 질문]\n{question}\n\n"
            f"[AI 답변]\n{answer}\n\n"
            f"[싫어요 이유]\n{feedback_note}"
        )
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=human),
        ]
        response = await self._llm.ainvoke(messages)
        return self._parse(_coerce_text(response.content), request_id)

    def _parse(self, text: str, request_id: str) -> FeedbackWikiDraft | None:
        try:
            parsed = json.loads(_strip_code_fence(text))
            if not isinstance(parsed, dict):
                raise ValueError("response is not a JSON object")
        except (json.JSONDecodeError, ValueError) as e:
            self._logger.warning(
                "feedback wiki distill response unparsable — skipped",
                request_id=request_id,
                error=str(e),
            )
            return None

        if not parsed.get("worthy"):
            return None
        title = str(parsed.get("title") or "").strip()[:_TITLE_MAX]
        content = str(parsed.get("content") or "").strip()
        if not title or not content:
            self._logger.warning(
                "feedback wiki distill missing title/content — skipped",
                request_id=request_id,
            )
            return None
        return FeedbackWikiDraft(
            title=title, content=content,
            confidence=self._parse_confidence(parsed.get("confidence")),
        )

    @staticmethod
    def _parse_confidence(raw) -> float:
        """0~100 점수를 /100 클램프 — 부재·비수치는 기본값(초안은 유지)."""
        try:
            return WikiPolicy.clamp_confidence(float(raw) / 100.0)
        except (TypeError, ValueError):
            return _DEFAULT_CONFIDENCE
