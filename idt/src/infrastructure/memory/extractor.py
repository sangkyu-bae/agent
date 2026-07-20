"""MemoryCandidateExtractor — LLM 기반 대화 메모리 후보 추출기.

agent-memory-extraction Design §3-2: WikiDistiller 동형 —
LLM은 주입(테스트 mock), 운영은 from_openai 팩토리. JSON 배열을 강제하고
파싱 실패·비배열은 warning 후 빈 목록(FR-05·격리 원칙).
"""
import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.application.memory.interfaces import (
    MemoryCandidate,
    MemoryExtractorInterface,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.memory.policies import MemoryPolicy

_SYSTEM_PROMPT = (
    "당신은 대화에서 사용자에 대한 '지속적인 배경 정보'만 골라내는 분류기입니다.\n"
    "다음 4가지 유형의 후보만 추출하세요:\n"
    "- profile: 소속·역할 등 사용자 프로필\n"
    "- domain_term: 사용자가 쓰는 용어의 정의·교정\n"
    "- preference: 답변 형식·스타일 선호\n"
    "- episode: 이후 대화에 참고할 맥락\n"
    "규칙:\n"
    "- 일회성 질문 내용·검색된 사실은 추출 금지 (사용자 자신에 대한 정보만)\n"
    "- [기존 메모리] 목록과 중복되는 내용 금지\n"
    "- 개인 식별 정보(주민번호·전화번호·계좌번호·이메일) 추출 절대 금지\n"
    "- 저장 가치가 없으면 빈 배열 []만 출력\n"
    "출력은 JSON 배열만 (설명 금지):\n"
    '[{"mem_type": "profile", "content": "간결한 한 문장", "confidence": 0~100}]'
)


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
    """```json ... ``` 코드펜스 제거."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[-1]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


class MemoryCandidateExtractor(MemoryExtractorInterface):
    def __init__(self, llm, logger: LoggerInterface) -> None:
        self._llm = llm
        self._logger = logger

    @classmethod
    def from_openai(cls, model_name: str, api_key: str, logger: LoggerInterface):
        from langchain_openai import ChatOpenAI

        return cls(ChatOpenAI(model=model_name, api_key=api_key, temperature=0), logger)

    async def extract(
        self,
        question: str,
        answer: str,
        existing_contents: list[str],
        request_id: str,
    ) -> list[MemoryCandidate]:
        turn_text = f"[사용자 질문]\n{question}\n\n[답변]\n{answer}"
        turn_text = turn_text[: MemoryPolicy.EXTRACT_INPUT_MAX]  # 결정 ①

        existing_block = ""
        if existing_contents:
            listed = "\n".join(f"- {c}" for c in existing_contents)
            existing_block = f"\n\n[기존 메모리 — 중복 금지]\n{listed}"

        messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=turn_text + existing_block),
        ]
        response = await self._llm.ainvoke(messages)
        return self._parse(_coerce_text(response.content), request_id)

    def _parse(self, text: str, request_id: str) -> list[MemoryCandidate]:
        try:
            parsed = json.loads(_strip_code_fence(text))
            if not isinstance(parsed, list):
                raise ValueError("response is not a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            self._logger.warning(
                "memory extraction response unparsable — skipped",
                request_id=request_id,
                error=str(e),
            )
            return []

        candidates: list[MemoryCandidate] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            mem_type = item.get("mem_type")
            content = item.get("content")
            if not mem_type or not content:
                continue
            candidates.append(
                MemoryCandidate(
                    mem_type=str(mem_type),
                    content=str(content),
                    confidence=MemoryPolicy.clamp_confidence(
                        int(item.get("confidence", 50))
                    ),
                )
            )
        return candidates
