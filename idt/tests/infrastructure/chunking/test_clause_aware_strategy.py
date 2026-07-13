"""ClauseAwareStrategy 테스트 (clause-aware-chunking Design §10)."""
from langchain_core.documents import Document

from src.infrastructure.chunking.chunking_factory import ChunkingStrategyFactory

_PARENT_PATTERNS = ["^제[0-9]+조의[0-9]+", "^제[0-9]+조"]
_CHILD_PATTERNS = [
    "^[ ]*[①②③④⑤⑥⑦⑧⑨⑩]",
    "^[ ]*[0-9]+[.]",
]


def _strategy(chunk_size=500, chunk_overlap=50, parent_chunk_size=2000):
    return ChunkingStrategyFactory.create_strategy(
        "clause_aware",
        parent_patterns=_PARENT_PATTERNS,
        child_patterns=_CHILD_PATTERNS,
        parent_chunk_size=parent_chunk_size,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def _doc(text: str, page: int = 1, **extra) -> Document:
    meta = {"page": page, "user_id": "u1"}
    meta.update(extra)
    return Document(page_content=text, metadata=meta)


def _parents(chunks):
    return [c for c in chunks if c.metadata["chunk_type"] == "parent"]


def _children(chunks):
    return [c for c in chunks if c.metadata["chunk_type"] == "child"]


class TestClauseBoundary:
    def test_splits_by_article(self):
        text = (
            "제1조(목적) 이 규정은 목적을 정한다.\n"
            "제2조(정의) 용어의 정의는 다음과 같다.\n"
            "제3조(적용) 이 규정을 적용한다."
        )
        chunks = _strategy().chunk([_doc(text)])
        parents = _parents(chunks)
        assert len(parents) == 3
        # 각 parent는 조 시작으로 시작 — 경계가 중간에서 잘리지 않음
        assert parents[0].page_content.startswith("제1조")
        assert parents[1].page_content.startswith("제2조")
        assert parents[2].page_content.startswith("제3조")

    def test_clause_title_captured(self):
        text = "제1조(목적) 목적.\n제2조(정의) 정의."
        chunks = _strategy().chunk([_doc(text)])
        titles = [p.metadata["clause_title"] for p in _parents(chunks)]
        assert titles[0].startswith("제1조")
        assert titles[1].startswith("제2조")

    def test_preamble_kept_as_leading_segment(self):
        text = "규정 전문 머리말입니다.\n제1조(목적) 목적을 정한다."
        chunks = _strategy().chunk([_doc(text)])
        parents = _parents(chunks)
        assert parents[0].metadata["clause_title"] == "(전문)"
        assert "머리말" in parents[0].page_content

    def test_article_of_variant(self):
        text = "제3조의2(특례) 특례를 둔다.\n제4조(삭제) 삭제한다."
        chunks = _strategy().chunk([_doc(text)])
        parents = _parents(chunks)
        assert parents[0].page_content.startswith("제3조의2")


class TestPageJoining:
    def test_article_spanning_pages_stays_one_parent(self):
        # 조가 2페이지에 걸침 → parent 1개 + page_start/page_end 정확
        page1 = _doc("제1조(목적) 이 조는 매우 긴", page=1)
        page2 = _doc("설명이 이어지는 내용이다.", page=2)
        chunks = _strategy().chunk([page1, page2])
        parents = _parents(chunks)
        assert len(parents) == 1
        assert parents[0].metadata["page_start"] == 1
        assert parents[0].metadata["page_end"] == 2

    def test_page_numbers_from_metadata(self):
        chunks = _strategy().chunk(
            [_doc("제1조(목적) 목적.", page=5)]
        )
        assert _parents(chunks)[0].metadata["page_start"] == 5

    def test_duplicate_clause_text_maps_correct_pages(self):
        # 동일 본문을 가진 조가 서로 다른 페이지에 있어도 offset으로 정확히 매핑 (G1)
        p1 = _doc("제1조(목적) 같은 문장이다.", page=1)
        p2 = _doc("제2조(목적) 같은 문장이다.", page=7)
        chunks = _strategy().chunk([p1, p2])
        parents = _parents(chunks)
        assert parents[0].metadata["page_start"] == 1
        assert parents[1].metadata["page_start"] == 7


class TestTokenSplitOnlyWhenExceeding:
    def test_small_clause_no_token_split(self):
        text = "제1조(목적) 짧은 조문."
        chunks = _strategy(chunk_size=500).chunk([_doc(text)])
        children = _children(chunks)
        assert all(c.metadata["boundary"] == "clause" for c in children)

    def test_large_child_token_split_with_overlap(self):
        # chunk_size를 작게 해 강제로 토큰 분할 유발
        big = "항목 내용 " * 300
        text = f"제1조(목적) {big}"
        chunks = _strategy(chunk_size=60, chunk_overlap=20).chunk([_doc(text)])
        token_children = [
            c for c in _children(chunks) if c.metadata["boundary"] == "token"
        ]
        assert len(token_children) >= 2  # 분할 발생

    def test_greedy_merge_short_items(self):
        # 여러 짧은 항이 한 child로 병합
        text = (
            "제1조(목적)\n"
            "1. 가\n2. 나\n3. 다\n4. 라\n5. 마"
        )
        chunks = _strategy(chunk_size=500).chunk([_doc(text)])
        # 짧은 항들이 과분할되지 않음 (child 수가 항 수보다 적음)
        assert len(_children(chunks)) < 5


class TestFallback:
    def test_no_pattern_match_fallback(self):
        text = "표와 그림만 있는 문서입니다. 조항 없음."
        chunks = _strategy().chunk([_doc(text)])
        parents = _parents(chunks)
        assert len(parents) == 1
        assert parents[0].metadata["boundary"] == "fallback"
        # parent/child 쌍은 항상 존재
        assert len(_children(chunks)) >= 1

    def test_empty_documents(self):
        assert _strategy().chunk([]) == []

    def test_blank_content(self):
        assert _strategy().chunk([_doc("   ")]) == []


class TestParentChildContract:
    def test_contract_fields_present(self):
        text = "제1조(목적) 목적.\n1. 첫째\n2. 둘째"
        chunks = _strategy().chunk([_doc(text)])
        for parent in _parents(chunks):
            assert parent.metadata["chunk_type"] == "parent"
            assert "chunk_id" in parent.metadata
            assert "children_ids" in parent.metadata
            assert "total_chunks" in parent.metadata
        for child in _children(chunks):
            assert child.metadata["chunk_type"] == "child"
            assert child.metadata["parent_id"] is not None
            assert "chunk_id" in child.metadata

    def test_child_index_reassigned_globally(self):
        text = "제1조(목적) 목적.\n1. 가\n2. 나\n제2조(정의) 정의.\n1. 다"
        chunks = _strategy().chunk([_doc(text)])
        children = _children(chunks)
        indices = [c.metadata["chunk_index"] for c in children]
        assert indices == list(range(len(children)))
        assert all(
            c.metadata["total_chunks"] == len(children) for c in children
        )

    def test_child_parent_id_links_to_parent(self):
        text = "제1조(목적) 목적.\n1. 가\n2. 나"
        chunks = _strategy().chunk([_doc(text)])
        parent_ids = {p.metadata["chunk_id"] for p in _parents(chunks)}
        for child in _children(chunks):
            assert child.metadata["parent_id"] in parent_ids

    def test_base_metadata_preserved(self):
        text = "제1조(목적) 목적."
        chunks = _strategy().chunk([_doc(text, user_id="u42", kb_id="kb1")])
        for c in chunks:
            assert c.metadata["user_id"] == "u42"
            assert c.metadata["kb_id"] == "kb1"


class TestStrategyName:
    def test_name(self):
        assert _strategy().get_strategy_name() == "clause_aware"

    def test_chunk_size(self):
        assert _strategy(chunk_size=333).get_chunk_size() == 333
