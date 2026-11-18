"""LLM 구조화 추출기 — 청크 1개에서 엔티티·관계 초안을 뽑는다.

Design Ref: graph-rag-foundation §7.2 D2 / Plan FR-06.
- 타입은 설정 목록 안에서만 허용하고, 목록 밖이면 '기타'로 둔다.
- 끝점이 이 청크의 엔티티가 아닌 관계는 버린다. 근거 문장 검증(원문 포함 여부)은
  유스케이스가 EvidencePolicy 로 한 곳에서 한다.
- LLM 은 모델 id 별로 한 번만 만든다(잡 하나가 같은 모델로 여러 청크 처리).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.domain.graph_rag.extraction import (
    ChunkUnit,
    ExtractionContext,
    ExtractionResult,
    Mention,
    NameNormalizer,
    RelationDraft,
)
from src.domain.graph_rag.interfaces import GraphExtractorPort
from src.domain.graph_rag.value_objects import OTHER_TYPE
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.graph_rag.extract.prompts import build_extraction_prompt

MAX_INPUT_CHARS = 12000


class _Entity(BaseModel):
    name: str = Field(description="문서에 나온 표기 그대로의 이름")
    type: str = Field(description="허용 타입 목록 중 하나")
    description: str = Field(default="", description="한 문장 설명")


class _Relation(BaseModel):
    source: str = Field(description="entities 의 name 중 하나")
    target: str = Field(description="entities 의 name 중 하나")
    type: str = Field(description="허용 관계 타입 목록 중 하나")
    evidence: str = Field(description="관계를 보여 주는 원문 문장 그대로")


class GraphExtractionOutput(BaseModel):
    entities: list[_Entity] = Field(default_factory=list)
    relations: list[_Relation] = Field(default_factory=list)


def _allowed(value: str, allowed: tuple[str, ...]) -> str:
    v = (value or "").strip()
    return v if v in allowed else OTHER_TYPE


class LlmGraphExtractor(GraphExtractorPort):
    def __init__(self, llm_model_repo: Any, llm_factory: Any, logger: LoggerInterface):
        self._llm_model_repo = llm_model_repo
        self._llm_factory = llm_factory
        self._logger = logger
        self._llms: dict[str, Any] = {}

    async def _structured(self, model_id: str, request_id: str) -> Any:
        if model_id not in self._llms:
            model = await self._llm_model_repo.find_by_id(model_id, request_id)
            if model is None:
                raise ValueError(f"extraction llm model not found: {model_id}")
            llm = self._llm_factory.create(model, 0.0)
            self._llms[model_id] = llm.with_structured_output(GraphExtractionOutput)
        return self._llms[model_id]

    async def extract(
        self, unit: ChunkUnit, context: ExtractionContext
    ) -> ExtractionResult:
        structured = await self._structured(context.model_id, context.request_id)
        prompt = build_extraction_prompt(
            unit.content[:MAX_INPUT_CHARS], context.entity_types, context.relation_types
        )
        output: GraphExtractionOutput = await structured.ainvoke(prompt)
        mentions = self._mentions(output, unit, context)
        names = {m.lookup_key for m in mentions}
        relations = tuple(
            RelationDraft(
                source=r.source.strip(),
                target=r.target.strip(),
                type=_allowed(r.type, context.relation_types),
                evidence=r.evidence,
                chunk_id=unit.chunk_id,
            )
            for r in output.relations
            if NameNormalizer.normalize(r.source) in names
            and NameNormalizer.normalize(r.target) in names
        )
        return ExtractionResult(mentions=mentions, relations=relations, llm_calls=1)

    @staticmethod
    def _mentions(
        output: GraphExtractionOutput, unit: ChunkUnit, context: ExtractionContext
    ) -> tuple[Mention, ...]:
        return tuple(
            Mention(
                name=e.name.strip(),
                type=_allowed(e.type, context.entity_types),
                description=(e.description or "").strip(),
                chunk_id=unit.chunk_id,
            )
            for e in output.entities
            if e.name and e.name.strip()
        )
