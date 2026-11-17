"""LlmTopicProposer — 문서 앞부분 → 주제 제안(구조화 출력).

Design Ref: graph-rag-foundation §11.9. 모델은 추출 모델(설정 extraction_llm_model_id).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.domain.graph_rag.interfaces import GraphSettingsReaderPort, TopicProposerPort
from src.domain.graph_rag.topic import (
    MAX_SECONDARY_TOPICS,
    TopicProposal,
    TopicSuggestion,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.graph_rag.topic.prompts import PROPOSER_SYSTEM


class _Suggestion(BaseModel):
    name: str = Field(description="짧은 주제 이름")
    description: str = Field(default="", description="한 문장 설명")


class TopicProposalOutput(BaseModel):
    major: _Suggestion = Field(description="업무 대분류")
    minor: _Suggestion | None = Field(default=None, description="세부 주제")
    secondary: list[str] = Field(default_factory=list, description="다른 대분류 이름")


class LlmTopicProposer(TopicProposerPort):
    def __init__(
        self,
        llm_model_repo: Any,
        llm_factory: Any,
        reader: GraphSettingsReaderPort,
        logger: LoggerInterface,
    ) -> None:
        self._repo = llm_model_repo
        self._factory = llm_factory
        self._reader = reader
        self._logger = logger
        self._llms: dict[str, Any] = {}

    async def _structured(self, request_id: str) -> Any:
        model_id = (await self._reader.get()).extraction_llm_model_id
        if not model_id:
            raise ValueError("extraction llm model not configured")
        if model_id not in self._llms:
            model = await self._repo.find_by_id(model_id, request_id)
            if model is None:
                raise ValueError(f"extraction llm model not found: {model_id}")
            llm = self._factory.create(model, 0.0)
            self._llms[model_id] = llm.with_structured_output(TopicProposalOutput)
        return self._llms[model_id]

    async def propose(self, excerpt: str, request_id: str) -> TopicProposal:
        structured = await self._structured(request_id)
        out: TopicProposalOutput = await structured.ainvoke(
            [("system", PROPOSER_SYSTEM), ("human", f"[문서 앞부분]\n{excerpt}")]
        )
        minor = None
        if out.minor is not None and out.minor.name.strip():
            minor = TopicSuggestion(
                out.minor.name.strip(), out.minor.description.strip()
            )
        secondary = tuple(s.strip() for s in out.secondary if s and s.strip())[
            : MAX_SECONDARY_TOPICS + 1
        ]  # 대표와 같은 이름이 섞일 수 있어 1개 여유
        return TopicProposal(
            major=TopicSuggestion(
                out.major.name.strip(), out.major.description.strip()
            ),
            minor=minor,
            secondary=secondary,
        )
