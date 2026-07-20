"""메모리 추출 계약 (agent-memory-extraction Design §3-1).

WikiDistillerInterface와 동일한 배치 — application이 포트를 정의하고
infrastructure(MemoryCandidateExtractor)가 구현한다.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MemoryCandidate:
    """LLM이 제안한 메모리 후보 — 저장 전 검증(mem_type/길이/중복)을 거친다."""

    mem_type: str      # MemoryType value 기대 — 불량 값은 서비스에서 탈락
    content: str
    confidence: int


class MemoryExtractorInterface(ABC):
    @abstractmethod
    async def extract(
        self,
        question: str,
        answer: str,
        existing_contents: list[str],
        request_id: str,
    ) -> list[MemoryCandidate]:
        """마지막 턴에서 저장 가치가 있는 후보를 추출한다. 없으면 []."""
