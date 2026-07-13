"""LlmSectionSummarizer — 섹션 1건 → 키워드+3줄 요약 (card-section-summary Design D10).

1차: with_structured_output(SectionSummaryOutput). 실패/빈 결과 시
JSON 지시 프롬프트 + 수동 파싱 1회 재시도 폴백 (slot_extractor 선례) —
vLLM 등 function calling 미지원 모델 대응.
"""
import json
import re

from pydantic import BaseModel, Field

from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.section_summary.entities import (
    SectionCard,
    SectionSummaryResult,
)
from src.domain.section_summary.interfaces import SectionSummarizerInterface

_CODE_FENCE_RE = re.compile(r"```[a-zA-Z]*\n?|```")

_SYSTEM_PROMPT = (
    "당신은 금융/정책 문서 색인 전문가다. 주어진 조문 섹션을 읽고 "
    "(1) 검색 키워드 3~8개(명사구, 섹션에 실제 등장하거나 직접 지칭하는 개념), "
    "(2) 섹션의 핵심 내용을 정확히 3줄로 요약하라(각 줄 1문장, 사실만). "
    "섹션에 없는 내용을 추가하지 마라."
)
_JSON_INSTRUCTION = (
    '반드시 다음 형식의 JSON만 출력하라(설명·코드펜스 금지): '
    '{"keywords": ["키워드", ...], "summary_lines": ["줄1", "줄2", "줄3"]}'
)


class SectionSummaryOutput(BaseModel):
    """structured output 스키마 (D10)."""

    keywords: list[str] = Field(
        default_factory=list, description="검색 키워드 3~8개 (명사구)"
    )
    summary_lines: list[str] = Field(
        default_factory=list, description="핵심 요약 정확히 3줄, 각 줄 1문장"
    )


class SectionSummarizeError(Exception):
    """섹션 요약 최종 실패 — 러너가 섹션 단위로 격리한다."""


def parse_summary_json(content: str, required_keys: tuple[str, ...]) -> dict:
    """LLM JSON 응답 파싱 — 코드펜스 제거 + 필수 배열 키 검증.

    섹션/문서 요약자 공용 (document-summary-routing D7).
    """
    text = _CODE_FENCE_RE.sub("", str(content).strip()).strip()
    raw = json.loads(text)
    if not isinstance(raw, dict):
        raise ValueError(f"JSON 객체가 아님: {type(raw).__name__}")
    for key in required_keys:
        if not isinstance(raw.get(key), list):
            raise ValueError(f"{key} 배열 누락")
    return raw


class LlmSectionSummarizer(SectionSummarizerInterface):
    def __init__(
        self, llm, logger: LoggerInterface, input_char_cap: int
    ) -> None:
        self._llm = llm
        self._logger = logger
        self._input_char_cap = input_char_cap

    async def summarize(
        self, card: SectionCard, request_id: str
    ) -> SectionSummaryResult:
        user_prompt = self._build_user_prompt(card)
        output = await self._try_structured(user_prompt, request_id)
        if output is not None and output.summary_lines:
            return SectionSummaryResult(
                keywords=output.keywords, summary_lines=output.summary_lines
            )
        return await self._json_fallback(user_prompt, request_id)

    async def _try_structured(
        self, user_prompt: str, request_id: str
    ) -> SectionSummaryOutput | None:
        try:
            structured = self._llm.with_structured_output(SectionSummaryOutput)
            result = await structured.ainvoke(
                self._messages(user_prompt, json_mode=False)
            )
            if isinstance(result, SectionSummaryOutput):
                return result
            return None
        except Exception as e:
            self._logger.warning(
                "Section summary structured output failed, falling back to JSON",
                request_id=request_id,
                error=str(e),
            )
            return None

    async def _json_fallback(
        self, user_prompt: str, request_id: str
    ) -> SectionSummaryResult:
        last_error: Exception | None = None
        for attempt in (1, 2):
            response = await self._llm.ainvoke(
                self._messages(user_prompt, json_mode=True)
            )
            content = getattr(response, "content", str(response))
            try:
                return self._parse(content)
            except (ValueError, TypeError) as e:
                last_error = e
                self._logger.warning(
                    "Section summary JSON parse failed, retrying",
                    request_id=request_id,
                    attempt=attempt,
                    error=str(e),
                )
        raise SectionSummarizeError(
            f"섹션 요약 결과를 해석할 수 없습니다: {last_error}"
        )

    def _build_user_prompt(self, card: SectionCard) -> str:
        text = card.text[: self._input_char_cap]
        return f"[섹션 제목]\n{card.title}\n\n[섹션 본문]\n{text}"

    @staticmethod
    def _messages(user_prompt: str, json_mode: bool) -> list[dict]:
        system = _SYSTEM_PROMPT + ("\n" + _JSON_INSTRUCTION if json_mode else "")
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _parse(content: str) -> SectionSummaryResult:
        raw = parse_summary_json(content, ("keywords", "summary_lines"))
        return SectionSummaryResult(
            keywords=[str(k) for k in raw["keywords"]],
            summary_lines=[str(line) for line in raw["summary_lines"]],
        )
