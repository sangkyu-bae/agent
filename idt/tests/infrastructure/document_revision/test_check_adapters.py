"""사전 점검 어댑터 — 본문 유사도·후보 앞부분·LLM 판정 (Design §10.5)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domain.document_revision.value_objects import LlmVerdict
from src.infrastructure.document_revision.candidate_head_reader import (
    EsCandidateHeadReader,
)
from src.infrastructure.document_revision.head_similarity_search import (
    QdrantHeadSimilaritySearch,
    split_head,
)
from src.infrastructure.document_revision.llm_revision_judge import (
    LlmRevisionJudge,
    RevisionJudgeOutput,
)


# ── 본문 유사도 ─────────────────────────────────────────────
def test_split_head_into_three_parts() -> None:
    parts = split_head("가" * 90, 3)
    assert [len(p) for p in parts] == [30, 30, 30]
    assert split_head("짧음", 3) == ["짧음"]
    assert split_head("", 3) == []


def _doc(doc_id: str, score: float):
    return SimpleNamespace(metadata={"document_id": doc_id}, score=score)


class _FakeStore:
    def __init__(self, per_call):
        self.per_call = list(per_call)
        self.filters = []

    async def search_by_vector(self, vector, top_k, filter, collection_name=None):
        self.filters.append((filter, collection_name, top_k))
        return self.per_call.pop(0)


@pytest.mark.asyncio
async def test_similarity_averages_best_score_per_segment() -> None:
    store = _FakeStore([
        [_doc("a", 0.9), _doc("a", 0.7), _doc("b", 0.6)],
        [_doc("a", 0.8), _doc("b", 0.9)],
        [_doc("a", 1.0)],
    ])
    embedder = AsyncMock()
    embedder.embed.return_value = [[0.1], [0.2], [0.3]]
    search = QdrantHeadSimilaritySearch(store, embedder, MagicMock(), top_k=30)
    scores = await search.search(
        collection_name="col", kb_id="kb-1", head_text="가" * 90, request_id="r"
    )
    assert scores["a"] == pytest.approx((0.9 + 0.8 + 1.0) / 3)
    assert scores["b"] == pytest.approx((0.6 + 0.9 + 0.0) / 3)
    f, collection, top_k = store.filters[0]
    assert f.metadata == {"kb_id": "kb-1"} and collection == "col" and top_k == 30
    embedder.embed.assert_awaited_once()


@pytest.mark.asyncio
async def test_similarity_empty_head_skips_embedding() -> None:
    embedder = AsyncMock()
    search = QdrantHeadSimilaritySearch(_FakeStore([]), embedder, MagicMock())
    assert await search.search(
        collection_name="c", kb_id="k", head_text="", request_id="r"
    ) == {}
    embedder.embed.assert_not_awaited()


# ── 후보 앞부분 ─────────────────────────────────────────────
def _hit(idx, ctype, content):
    return SimpleNamespace(
        id=f"h{idx}", score=1.0, index="documents",
        source={"chunk_index": idx, "chunk_type": ctype, "content": content},
    )


@pytest.mark.asyncio
async def test_head_reader_prefers_parents_in_order_and_truncates() -> None:
    es = MagicMock()
    es.search = AsyncMock(return_value=[
        _hit(2, "parent", "셋째"), _hit(0, "parent", "첫째"),
        _hit(1, "child", "자식"), _hit(1, "parent", "둘째"),
    ])
    reader = EsCandidateHeadReader(es, "documents", MagicMock())
    text = await reader.read("doc-1", 5, "r")
    assert text == "첫째\n둘째"  # parent 만, chunk_index 순, max_chars 절단
    q = es.search.call_args.args[0]
    assert q.index == "documents"
    filters = q.query["bool"]["filter"]
    assert {"term": {"document_id": "doc-1"}} in filters
    must_not = q.query["bool"]["must_not"]
    assert {"terms": {"chunk_type": ["document_summary", "section_summary"]}} in must_not


@pytest.mark.asyncio
async def test_head_reader_without_parents_uses_all_chunks() -> None:
    es = MagicMock()
    es.search = AsyncMock(return_value=[_hit(1, "child", "B"), _hit(0, "child", "A")])
    reader = EsCandidateHeadReader(es, "documents", MagicMock())
    assert await reader.read("d", 100, "r") == "A\nB"


# ── LLM 판정 ────────────────────────────────────────────────
class _FakeLLM:
    def __init__(self, output):
        self.output = output
        self.prompts = []

    def with_structured_output(self, schema):
        outer = self

        class _Runnable:
            async def ainvoke(self, messages):
                outer.prompts.append(messages)
                return outer.output

        return _Runnable()


@pytest.mark.asyncio
async def test_judge_maps_structured_output() -> None:
    llm = _FakeLLM(RevisionJudgeOutput(
        verdict="same_document_revision", reason="제1조 동일", confidence=0.9
    ))
    provider = AsyncMock()
    provider.get.return_value = llm
    judge = LlmRevisionJudge(provider, MagicMock())
    out = await judge.judge(
        new_filename="n.pdf", new_head="새 앞부분", candidate_filename="o.pdf",
        candidate_head="구 앞부분", request_id="r",
    )
    assert out.verdict is LlmVerdict.SAME and out.reason == "제1조 동일"
    text = str(llm.prompts[0])
    assert "n.pdf" in text and "o.pdf" in text and "새 앞부분" in text


@pytest.mark.asyncio
async def test_judge_returns_none_when_no_model() -> None:
    provider = AsyncMock()
    provider.get.return_value = None
    judge = LlmRevisionJudge(provider, MagicMock())
    assert await judge.judge(
        new_filename="n", new_head="a", candidate_filename="o", candidate_head="b",
        request_id="r",
    ) is None


@pytest.mark.asyncio
async def test_judge_reason_is_truncated() -> None:
    llm = _FakeLLM(RevisionJudgeOutput(verdict="uncertain", reason="x" * 500, confidence=0.1))
    provider = AsyncMock()
    provider.get.return_value = llm
    out = await LlmRevisionJudge(provider, MagicMock()).judge(
        new_filename="n", new_head="a", candidate_filename="o", candidate_head="b",
        request_id="r",
    )
    assert out.verdict is LlmVerdict.UNCERTAIN and len(out.reason) == 200


# ── 컬렉션 임베딩 ───────────────────────────────────────────
@pytest.mark.asyncio
async def test_embedder_resolves_collection_model_like_upload() -> None:
    from src.infrastructure.document_revision.head_similarity_search import (
        CollectionHeadEmbedder,
    )

    log_repo = AsyncMock()
    log_repo.find_all.return_value = [SimpleNamespace(detail={"embedding_model": "m1"})]
    model_repo = AsyncMock()
    model_repo.find_by_model_name.return_value = SimpleNamespace(
        provider="openai", model_name="m1"
    )
    embedding = AsyncMock()
    embedding.embed_documents.return_value = [[0.1], [0.2]]
    factory = MagicMock()
    factory.create_from_string.return_value = embedding
    embedder = CollectionHeadEmbedder(log_repo, model_repo, factory)

    vectors = await embedder.embed("col", ["a", "b"], "r")

    assert vectors == [[0.1], [0.2]]
    assert log_repo.find_all.call_args.kwargs == {
        "request_id": "r", "collection_name": "col", "action": "CREATE", "limit": 1,
    }
    factory.create_from_string.assert_called_once_with(provider="openai", model_name="m1")


@pytest.mark.asyncio
async def test_embedder_unknown_model_raises() -> None:
    from src.infrastructure.document_revision.head_similarity_search import (
        CollectionHeadEmbedder,
    )

    log_repo = AsyncMock()
    log_repo.find_all.return_value = []
    embedder = CollectionHeadEmbedder(log_repo, AsyncMock(), MagicMock())
    with pytest.raises(ValueError):
        await embedder.embed("col", ["a"], "r")
