"""개정 검색 가드 커버리지 계약 — document-revision Design §9.5.

Qdrant·ES 에 직접 질의를 만드는 파일은 전부 "가드 적용" 또는 "의도 제외" 중 하나로
분류돼 있어야 한다. 새 검색 경로가 생기면 이 테스트가 실패해 가드 여부를 결정하게 만든다.
(search_by_vector 호출자는 G1 QdrantVectorStore 가 최하단에서 가드하므로 대상이 아니다.)
"""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

# 직접 질의 생성 패턴: ES 검색 요청 / Qdrant 벡터 질의 / Qdrant scroll
_QUERY_PATTERN = re.compile(r"ESSearchQuery\(|\.query_points\(|\.scroll\(")

GUARDED = {
    "infrastructure/vector/qdrant_vectorstore.py": "apply_revision_guard",
    "infrastructure/retriever/qdrant_retriever.py": "apply_revision_guard",
    "application/hybrid_search/use_case.py": "es_revision_guard_clause",
    "infrastructure/routed_retrieval/hybrid_section_router.py": "es_revision_guard_clause",
    "infrastructure/graph_rag/es_evidence_fetcher.py": "es_revision_guard_clause",
}

# 의도 제외 — 사유를 남긴다.
EXEMPT = {
    "application/knowledge_base/browse_sources.py": "문서 단위 콘텐츠 브라우저(구버전 열람 허용)",
    "application/doc_browse/get_chunks_use_case.py": "문서 단위 청크 조회",
    "infrastructure/graph_rag/es_chunk_reader.py": "그래프 추출 입력(문서 지정)",
    "infrastructure/routed_retrieval/es_chunk_expander.py": "라우팅이 이미 고른 문서 안 확장",
    "infrastructure/retriever/parent_child_retriever.py": "가드된 child 히트의 parent 조회",
    "infrastructure/section_summary/qdrant_section_source.py": "요약 생성용 문서 지정 조회",
    "infrastructure/wiki/wiki_source_provider.py": "위키 문서(KB 문서 아님)",
    "api/routes/rag_tool_router.py": "메타데이터 키 샘플링(검색 아님)",
    "infrastructure/document_revision/candidate_head_reader.py": (
        "개정 후보(active 문서) 앞부분 — 문서 지정 조회"
    ),
}


def _query_files() -> set[str]:
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith("domain/"):
            continue
        if _QUERY_PATTERN.search(path.read_text(encoding="utf-8")):
            found.add(rel)
    return found


def test_every_query_site_is_classified() -> None:
    unclassified = _query_files() - set(GUARDED) - set(EXEMPT)
    assert not unclassified, (
        f"새 Qdrant/ES 질의 파일 — 개정 가드 적용 또는 EXEMPT 사유 등록 필요: {sorted(unclassified)}"
    )


def test_classification_has_no_stale_entries() -> None:
    stale = (set(GUARDED) | set(EXEMPT)) - _query_files()
    assert not stale, f"더 이상 질의하지 않는 파일 — 목록 정리 필요: {sorted(stale)}"


def test_guarded_files_call_the_guard() -> None:
    missing = [
        rel
        for rel, symbol in GUARDED.items()
        if symbol not in (SRC / rel).read_text(encoding="utf-8")
    ]
    assert not missing, f"가드 호출 누락: {missing}"
