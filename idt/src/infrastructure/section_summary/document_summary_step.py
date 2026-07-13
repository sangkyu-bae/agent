"""DocumentSummaryStep — 문서 요약 생성·저장 (document-summary-routing D2/D5/D7~D11).

섹션 요약 잡 completed 전이 직전에 러너가 호출하는 자기완결 단계:
모델 로드/검증 → 섹션 요약 전량 수집 → cap 이내 단일 패스 / 초과 시
배치 중간 요약→최종(2계층) → 키워드 빈도 집계(LLM 0회) → 임베딩 →
ES 먼저→Qdrant 마지막(결정적 ID 멱등 upsert) 저장. 실패는 raise —
러너가 잡을 failed("document summary failed: ...")로 마감한다.
"""
from typing import Callable

from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointStruct

from src.domain.elasticsearch.interfaces import (
    ElasticsearchRepositoryInterface,
)
from src.domain.elasticsearch.schemas import ESDocument
from src.domain.llm.interfaces import LLMFactoryInterface
from src.domain.llm_model.interfaces import LlmModelRepositoryInterface
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.domain.section_summary.entities import (
    DocumentSummaryRecord,
    SectionSummaryItem,
    SectionSummaryJob,
    document_summary_id_for,
)
from src.domain.section_summary.interfaces import (
    DocumentSummaryStepInterface,
)
from src.domain.section_summary.policy import SectionSummaryJobPolicy
from src.infrastructure.embeddings.embedding_factory import EmbeddingFactory
from src.infrastructure.section_summary.llm_summarizer import (
    parse_summary_json,
)
from src.infrastructure.section_summary.qdrant_section_source import (
    QdrantSectionSource,
)

_DOC_SUMMARY_CHUNK_TYPE = "document_summary"

# 중간(배치) 요약 줄 수 (D8) — 최종 줄 수는 domain 정책(DOC_SUMMARY_LINES)이 절단
_INTERIM_SUMMARY_LINES = 5

_SYSTEM_PROMPT_FINAL = (
    "당신은 금융/정책 문서 색인 전문가다. 아래는 한 문서의 섹션별 요약 목록이다. "
    f"문서 전체를 대표하는 핵심 내용을 정확히 "
    f"{SectionSummaryJobPolicy.DOC_SUMMARY_LINES}줄로 요약하라"
    "(각 줄 1문장, 사실만). 섹션 요약에 없는 내용을 추가하지 마라."
)
_SYSTEM_PROMPT_INTERIM = (
    "당신은 금융/정책 문서 색인 전문가다. 아래는 한 문서의 섹션별 요약 중 "
    f"일부 구간이다. 이 구간의 핵심 내용을 정확히 {_INTERIM_SUMMARY_LINES}줄로 "
    "요약하라(각 줄 1문장, 사실만). 구간에 없는 내용을 추가하지 마라."
)
_JSON_INSTRUCTION = (
    '반드시 다음 형식의 JSON만 출력하라(설명·코드펜스 금지): '
    '{"summary_lines": ["줄1", "줄2", "줄3", "줄4", "줄5"]}'
)


class DocumentSummaryOutput(BaseModel):
    """structured output 스키마 (D7) — 키워드는 집계로 대체(D9)."""

    summary_lines: list[str] = Field(
        default_factory=list, description="문서 대표 요약 정확히 5줄, 각 줄 1문장"
    )


class DocumentSummarizeError(Exception):
    """문서 요약 최종 실패 — 러너가 잡 failed로 마감한다."""


class LlmDocumentSummarizer:
    """LLM 호출 래퍼 — structured output → JSON 폴백 1회 재시도 (D7)."""

    def __init__(self, llm, logger: LoggerInterface) -> None:
        self._llm = llm
        self._logger = logger

    async def summarize(
        self, body: str, final: bool, request_id: str
    ) -> list[str]:
        messages = self._messages(body, final, json_mode=False)
        try:
            structured = self._llm.with_structured_output(DocumentSummaryOutput)
            result = await structured.ainvoke(messages)
            if isinstance(result, DocumentSummaryOutput) and result.summary_lines:
                return result.summary_lines
        except Exception as e:
            self._logger.warning(
                "Document summary structured output failed, falling back",
                request_id=request_id,
                error=str(e),
            )
        return await self._json_fallback(body, final, request_id)

    async def _json_fallback(
        self, body: str, final: bool, request_id: str
    ) -> list[str]:
        last_error: Exception | None = None
        for attempt in (1, 2):
            response = await self._llm.ainvoke(
                self._messages(body, final, json_mode=True)
            )
            content = getattr(response, "content", str(response))
            try:
                raw = parse_summary_json(content, ("summary_lines",))
                return [str(line) for line in raw["summary_lines"]]
            except (ValueError, TypeError) as e:
                last_error = e
                self._logger.warning(
                    "Document summary JSON parse failed, retrying",
                    request_id=request_id,
                    attempt=attempt,
                    error=str(e),
                )
        raise DocumentSummarizeError(
            f"문서 요약 결과를 해석할 수 없습니다: {last_error}"
        )

    @staticmethod
    def _messages(body: str, final: bool, json_mode: bool) -> list[dict]:
        system = _SYSTEM_PROMPT_FINAL if final else _SYSTEM_PROMPT_INTERIM
        if json_mode:
            system = system + "\n" + _JSON_INSTRUCTION
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": body},
        ]


class DocumentSummaryStep(DocumentSummaryStepInterface):
    def __init__(
        self,
        section_source: QdrantSectionSource,
        qdrant_client: AsyncQdrantClient,
        es_repo: ElasticsearchRepositoryInterface,
        es_index: str,
        llm_model_repo: LlmModelRepositoryInterface,
        llm_factory: LLMFactoryInterface,
        embedding_factory: EmbeddingFactory,
        policy: SectionSummaryJobPolicy,
        logger: LoggerInterface,
        input_char_cap: int,
        max_batches: int,
        summarizer_builder: Callable[..., "LlmDocumentSummarizer"] | None = None,
    ) -> None:
        self._section_source = section_source
        self._client = qdrant_client
        self._es_repo = es_repo
        self._es_index = es_index
        self._llm_model_repo = llm_model_repo
        self._llm_factory = llm_factory
        self._embedding_factory = embedding_factory
        self._policy = policy
        self._logger = logger
        self._input_char_cap = input_char_cap
        self._max_batches = max_batches
        self._summarizer_builder = summarizer_builder or (
            lambda llm: LlmDocumentSummarizer(llm, logger)
        )

    async def run(self, job: SectionSummaryJob, request_id: str) -> None:
        model = await self._llm_model_repo.find_by_id(
            job.llm_model_id, request_id
        )
        if model is None or not model.is_active:
            raise ValueError(
                f"summary LLM model unavailable or inactive: {job.llm_model_id}"
            )
        items = await self._section_source.list_summary_items(
            job.collection_name, job.document_id, request_id
        )
        if not items:
            self._logger.warning(
                "Document summary skipped: no section summaries",
                request_id=request_id,
                job_id=job.id,
                document_id=job.document_id,
            )
            return
        summarizer = self._summarizer_builder(
            self._llm_factory.create(model, 0.0)
        )
        lines, pass_mode, batches = await self._generate(
            summarizer, items, request_id
        )
        record = await self._build_record(job, items, lines)
        await self._write(record, request_id)
        self._logger.info(
            "Document summary generated",
            request_id=request_id,
            job_id=job.id,
            document_id=job.document_id,
            chunking_profile_id=job.chunking_profile_id,
            llm_model_id=job.llm_model_id,
            section_count=len(items),
            pass_mode=pass_mode,
            batches=batches,
        )

    async def _generate(
        self,
        summarizer: LlmDocumentSummarizer,
        items: list[SectionSummaryItem],
        request_id: str,
    ) -> tuple[list[str], str, int]:
        """단일 패스 또는 배치 중간 요약→최종의 2계층 (D8)."""
        # 방어 절단: 단일 블록이 cap을 넘는 극단 케이스도 배치 ≤ cap 보장 (NFR-07)
        blocks = [
            f"[{item.title}]\n{item.summary}"[: self._input_char_cap]
            for item in items
        ]
        combined = "\n\n".join(blocks)
        if len(combined) <= self._input_char_cap:
            lines = await summarizer.summarize(combined, True, request_id)
            return lines, "single", 1
        batches = self._split_batches(blocks)
        if len(batches) > self._max_batches:
            raise ValueError(
                f"document summary batches {len(batches)} exceed cap "
                f"{self._max_batches}"
            )
        interim: list[str] = []
        for batch in batches:
            batch_lines = await summarizer.summarize(
                "\n\n".join(batch), False, request_id
            )
            interim.append("\n".join(batch_lines))
        merged = "\n\n".join(interim)
        if len(merged) > self._input_char_cap:
            self._logger.warning(
                "Document summary interim merge truncated",
                request_id=request_id,
                merged_chars=len(merged),
                cap=self._input_char_cap,
            )
            merged = merged[: self._input_char_cap]
        lines = await summarizer.summarize(merged, True, request_id)
        return lines, "hierarchical", len(batches)

    def _split_batches(self, blocks: list[str]) -> list[list[str]]:
        """chunk_index 연속 구간을 유지한 cap 이하 배치 분할 (D8)."""
        batches: list[list[str]] = []
        current: list[str] = []
        current_len = 0
        for block in blocks:
            if current and current_len + len(block) > self._input_char_cap:
                batches.append(current)
                current, current_len = [], 0
            current.append(block)
            current_len += len(block) + 2
        if current:
            batches.append(current)
        return batches

    async def _build_record(
        self,
        job: SectionSummaryJob,
        items: list[SectionSummaryItem],
        lines: list[str],
    ) -> DocumentSummaryRecord:
        clean_lines = self._policy.sanitize_document_output(lines)
        summary_text = "\n".join(clean_lines)
        keywords = self._policy.aggregate_keywords(
            [item.keywords for item in items]
        )
        meta = items[0].meta
        filename = meta.get("filename", "")
        embedding = self._embedding_factory.create_from_string(
            provider=job.embedding_provider,
            model_name=job.embedding_model,
        )
        embed_input = f"{filename}\n{summary_text}" if filename else summary_text
        vector = await embedding.embed_text(embed_input)
        return DocumentSummaryRecord(
            summary_id=document_summary_id_for(job.document_id),
            document_id=job.document_id,
            collection_name=job.collection_name,
            kb_id=job.kb_id,
            kb_name=meta.get("kb_name", ""),
            user_id=meta.get("user_id", ""),
            keywords=keywords,
            summary_text=summary_text,
            vector=vector,
            section_count=len(items),
            filename=filename,
        )

    async def _write(
        self, record: DocumentSummaryRecord, request_id: str
    ) -> None:
        """ES 먼저 → Qdrant 마지막 — 결정적 ID 멱등 (D10)."""
        await self._es_repo.index(
            ESDocument(
                id=record.summary_id,
                body=self._es_body(record),
                index=self._es_index,
            ),
            request_id,
        )
        await self._client.upsert(
            collection_name=record.collection_name,
            points=[
                PointStruct(
                    id=record.summary_id,
                    vector=record.vector,
                    payload=self._qdrant_payload(record),
                )
            ],
        )

    @staticmethod
    def _es_body(record: DocumentSummaryRecord) -> dict:
        """기존 요약 전용 필드만 재사용 — 신규 매핑 0, content/morph_* 없음 (D11)."""
        body = {
            "chunk_id": record.summary_id,
            "chunk_type": _DOC_SUMMARY_CHUNK_TYPE,
            "summary_text": record.summary_text,
            "summary_keywords": record.keywords,
            "document_id": record.document_id,
            "user_id": record.user_id,
            "collection_name": record.collection_name,
            "kb_id": record.kb_id,
        }
        if record.kb_name:
            body["kb_name"] = record.kb_name
        if record.filename:
            body["filename"] = record.filename
        return body

    @staticmethod
    def _qdrant_payload(record: DocumentSummaryRecord) -> dict:
        payload = {
            "content": record.summary_text,
            "chunk_type": _DOC_SUMMARY_CHUNK_TYPE,
            "chunk_id": record.summary_id,
            "document_id": record.document_id,
            "collection_name": record.collection_name,
            "kb_id": record.kb_id,
            "user_id": record.user_id,
            "keywords": record.keywords,
            "summary": record.summary_text,
            "section_count": str(record.section_count),
        }
        if record.kb_name:
            payload["kb_name"] = record.kb_name
        if record.filename:
            payload["filename"] = record.filename
        return payload
