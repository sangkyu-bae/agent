"""DocumentSummaryStep 테스트 (document-summary-routing D2/D5/D7~D11)."""
import json
from types import SimpleNamespace

import pytest

from src.domain.section_summary.entities import (
    SectionSummaryItem,
    SectionSummaryJob,
    document_summary_id_for,
)
from src.domain.section_summary.policy import SectionSummaryJobPolicy
from src.infrastructure.section_summary.document_summary_step import (
    DocumentSummaryOutput,
    DocumentSummaryStep,
    DocumentSummarizeError,
    LlmDocumentSummarizer,
)


class _FakeLogger:
    def debug(self, *a, **k): ...
    def info(self, *a, **k): ...
    def warning(self, *a, **k): ...
    def error(self, *a, **k): ...
    def critical(self, *a, **k): ...


class _FakeSource:
    def __init__(self, items):
        self._items = items

    async def list_summary_items(self, collection_name, document_id, request_id):
        return self._items


class _FakeEsRepo:
    def __init__(self, order):
        self.docs = []
        self._order = order

    async def index(self, document, request_id):
        self._order.append("es")
        self.docs.append(document)
        return document.id


class _FakeQdrantClient:
    def __init__(self, order):
        self.upserts = []
        self._order = order

    async def upsert(self, collection_name, points):
        self._order.append("qdrant")
        self.upserts.append((collection_name, points))


class _FakeSummarizer:
    """(body, final) 호출 기록 — 반환은 5줄 고정."""

    def __init__(self):
        self.calls: list[tuple[str, bool]] = []

    async def summarize(self, body, final, request_id):
        self.calls.append((body, final))
        return [f"line {i}" for i in range(1, 6)]


class _FakeEmbedding:
    def __init__(self):
        self.inputs = []

    async def embed_text(self, text):
        self.inputs.append(text)
        return [0.1, 0.2]


class _FakeEmbeddingFactory:
    def __init__(self):
        self.embedding = _FakeEmbedding()

    def create_from_string(self, provider, model_name):
        return self.embedding


class _FakeLlmModelRepo:
    def __init__(self, model=None):
        self.model = (
            model
            if model is not None
            else SimpleNamespace(id="model-1", is_active=True)
        )

    async def find_by_id(self, model_id, request_id):
        return self.model


class _FakeLlmFactory:
    def create(self, llm_model, temperature=0.0):
        return object()


def _job() -> SectionSummaryJob:
    return SectionSummaryJob(
        id="job-1",
        document_id="doc-1",
        kb_id="kb-1",
        collection_name="col",
        chunking_profile_id="prof-1",
        llm_model_id="model-1",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        status="processing",
    )


def _item(index: int, keywords=None) -> SectionSummaryItem:
    return SectionSummaryItem(
        title=f"제{index + 1}조",
        summary=f"요약 {index}",
        keywords=keywords or ["대출"],
        chunk_index=index,
        meta={"kb_name": "여신규정", "user_id": "7", "filename": "rule.pdf"},
    )


def _step(items, order=None, cap=1000, max_batches=10, llm_repo=None):
    order = order if order is not None else []
    es_repo = _FakeEsRepo(order)
    client = _FakeQdrantClient(order)
    embedding_factory = _FakeEmbeddingFactory()
    summarizer = _FakeSummarizer()
    step = DocumentSummaryStep(
        section_source=_FakeSource(items),
        qdrant_client=client,
        es_repo=es_repo,
        es_index="documents",
        llm_model_repo=llm_repo or _FakeLlmModelRepo(),
        llm_factory=_FakeLlmFactory(),
        embedding_factory=embedding_factory,
        policy=SectionSummaryJobPolicy(),
        logger=_FakeLogger(),
        input_char_cap=cap,
        max_batches=max_batches,
        summarizer_builder=lambda llm: summarizer,
    )
    return step, summarizer, es_repo, client, embedding_factory, order


@pytest.mark.asyncio
async def test_single_pass_when_within_cap():
    items = [_item(0), _item(1)]
    step, summarizer, es_repo, client, _, order = _step(items)

    await step.run(_job(), "req-1")

    assert [final for _, final in summarizer.calls] == [True]
    assert "제1조" in summarizer.calls[0][0]
    assert "제2조" in summarizer.calls[0][0]
    assert order == ["es", "qdrant"]


@pytest.mark.asyncio
async def test_hierarchical_pass_when_over_cap():
    """cap 초과 → 연속 구간 배치 중간 요약 + 최종 1회 (D8)."""
    items = [_item(i) for i in range(4)]
    step, summarizer, *_ = _step(items, cap=30)

    await step.run(_job(), "req-1")

    finals = [final for _, final in summarizer.calls]
    assert finals[-1] is True
    assert finals[:-1] and all(f is False for f in finals[:-1])
    # 중간 요약 배치가 chunk_index 순 연속 구간
    assert "제1조" in summarizer.calls[0][0]


@pytest.mark.asyncio
async def test_oversized_single_block_is_truncated_to_cap():
    """단일 블록 > cap 극단 케이스도 배치 ≤ cap 방어 절단 (NFR-07)."""
    huge = SectionSummaryItem(
        title="제1조", summary="가" * 200, keywords=["kw"], chunk_index=0,
        meta={"filename": "rule.pdf"},
    )
    step, summarizer, *_ = _step([huge], cap=50)

    await step.run(_job(), "req-1")

    for body, _final in summarizer.calls:
        assert len(body) <= 50


@pytest.mark.asyncio
async def test_max_batches_exceeded_raises():
    items = [_item(i) for i in range(6)]
    step, *_ = _step(items, cap=20, max_batches=2)

    with pytest.raises(ValueError, match="exceed cap"):
        await step.run(_job(), "req-1")


@pytest.mark.asyncio
async def test_no_items_skips_without_writes():
    """섹션 요약 0건 → 스킵, 저장·LLM 없음 (D5)."""
    step, summarizer, es_repo, client, _, order = _step([])

    await step.run(_job(), "req-1")

    assert summarizer.calls == []
    assert order == []


@pytest.mark.asyncio
async def test_inactive_model_raises():
    repo = _FakeLlmModelRepo(SimpleNamespace(id="m", is_active=False))
    step, *_ = _step([_item(0)], llm_repo=repo)

    with pytest.raises(ValueError, match="unavailable"):
        await step.run(_job(), "req-1")


@pytest.mark.asyncio
async def test_storage_contract():
    """§4.1/§4.2 — 결정적 ID·집계 키워드·ES 필드 격리·임베딩 입력 (D9~D11)."""
    items = [
        _item(0, keywords=["대출", "금리"]),
        _item(1, keywords=["대출", "한도"]),
    ]
    step, _, es_repo, client, embedding_factory, _ = _step(items)

    await step.run(_job(), "req-1")

    expected_id = document_summary_id_for("doc-1")
    doc = es_repo.docs[0]
    assert doc.id == expected_id
    body = doc.body
    for forbidden in ("content", "morph_text", "morph_keywords", "section_ref"):
        assert forbidden not in body
    assert body["chunk_type"] == "document_summary"
    assert body["summary_keywords"][0] == "대출"  # 빈도 1위
    assert body["kb_name"] == "여신규정"

    collection, points = client.upserts[0]
    assert collection == "col"
    point = points[0]
    assert point.id == expected_id
    payload = point.payload
    assert payload["chunk_type"] == "document_summary"
    assert payload["section_count"] == "2"
    assert payload["keywords"] == ["대출", "금리", "한도"]
    assert payload["summary"] == payload["content"]

    # 임베딩 입력 = filename + 요약 (D10)
    assert embedding_factory.embedding.inputs[0].startswith("rule.pdf\n")


class _StructuredRunnable:
    def __init__(self, output):
        self._output = output

    async def ainvoke(self, messages):
        if isinstance(self._output, Exception):
            raise self._output
        return self._output


class _FakeLlm:
    def __init__(self, structured=None, raw_contents=None):
        self._structured = structured
        self._raw_contents = list(raw_contents or [])

    def with_structured_output(self, schema):
        return _StructuredRunnable(self._structured)

    async def ainvoke(self, messages):
        content = self._raw_contents.pop(0)
        resp = SimpleNamespace()
        resp.content = content
        return resp


@pytest.mark.asyncio
async def test_llm_summarizer_structured_success():
    llm = _FakeLlm(
        structured=DocumentSummaryOutput(summary_lines=["a", "b", "c", "d", "e"])
    )
    result = await LlmDocumentSummarizer(llm, _FakeLogger()).summarize(
        "body", True, "req-1"
    )
    assert result == ["a", "b", "c", "d", "e"]


@pytest.mark.asyncio
async def test_llm_summarizer_json_fallback():
    payload = json.dumps({"summary_lines": ["줄1", "줄2"]}, ensure_ascii=False)
    llm = _FakeLlm(
        structured=RuntimeError("no structured"),
        raw_contents=[f"```json\n{payload}\n```"],
    )
    result = await LlmDocumentSummarizer(llm, _FakeLogger()).summarize(
        "body", True, "req-1"
    )
    assert result == ["줄1", "줄2"]


@pytest.mark.asyncio
async def test_llm_summarizer_parse_failure_raises():
    llm = _FakeLlm(
        structured=RuntimeError("no structured"),
        raw_contents=["not json", "still not json"],
    )
    with pytest.raises(DocumentSummarizeError):
        await LlmDocumentSummarizer(llm, _FakeLogger()).summarize(
            "body", True, "req-1"
        )
