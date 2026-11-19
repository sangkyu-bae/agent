"""검색 기록 → 뷰어 구절 정책, 저장 키 규칙 (Design §3.1). 순수 함수."""
import re
from typing import Any, Iterable, Optional

from src.domain.agent_run.entities import RetrievalSource
from src.domain.source_viewer.models import OriginalKind, Passage

# source_policy.WEB_COLLECTION 과 같은 값. agent_run.source_policy 를 import 하지 않아
# 경계 테스트(domain 은 agent_run.entities 만 허용)를 지킨다.
_WEB_COLLECTION = "tavily_web"
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_KIND_BY_EXT = {".pdf": OriginalKind.PDF, ".docx": OriginalKind.DOCX}
_RANK_LAST = 1 << 31


def storage_key(document_id: str) -> str:
    """`{앞 2자}/{uuid}` — UUID 형식이 아니면 ValueError (Design §7 경로 조작 차단)."""
    normalized = (document_id or "").strip().lower()
    if not _UUID.match(normalized):
        raise ValueError("document_id must be a UUID")
    return f"{normalized[:2]}/{normalized}"


def _text(metadata: Optional[dict[str, Any]], key: str) -> Optional[str]:
    value = (metadata or {}).get(key)
    return value if isinstance(value, str) and value.strip() else None


def _page(metadata: Optional[dict[str, Any]]) -> Optional[int]:
    raw = (metadata or {}).get("page")
    if isinstance(raw, bool):
        return None
    try:
        page = int(raw)
    except (TypeError, ValueError):
        return None
    return page if page > 0 else None


def _order(r: RetrievalSource) -> tuple:
    rank = r.rank_index if r.rank_index is not None else _RANK_LAST
    return (r.created_at, rank, r.id)


def _of_document(
    document_id: str, retrievals: Iterable[RetrievalSource],
) -> list[RetrievalSource]:
    return sorted(
        (
            r for r in retrievals
            if r.document_id == document_id and r.collection_name != _WEB_COLLECTION
        ),
        key=_order,
    )


class PassagePolicy:
    MAX_PASSAGES = 20

    @staticmethod
    def collect(
        document_id: str, retrievals: Iterable[RetrievalSource],
    ) -> tuple[Passage, ...]:
        """문서 1개의 인용 구절 — 검색 순서, chunk_id 중복 제거, 상한 적용."""
        seen: dict[str, Passage] = {}
        for r in _of_document(document_id, retrievals):
            chunk_id = _text(r.metadata_json, "chunk_id") or r.chunk_id or r.id
            if chunk_id in seen:
                continue
            seen[chunk_id] = Passage(
                chunk_id=chunk_id,
                parent_id=_text(r.metadata_json, "parent_id"),
                page=_page(r.metadata_json),
                rank=len(seen),
                excerpt=r.content_preview or "",
            )
            if len(seen) >= PassagePolicy.MAX_PASSAGES:
                break
        return tuple(seen.values())

    @staticmethod
    def kb_id_of(
        document_id: str, retrievals: Iterable[RetrievalSource],
    ) -> Optional[str]:
        for r in _of_document(document_id, retrievals):
            kb_id = _text(r.metadata_json, "kb_id")
            if kb_id:
                return kb_id
        return None

    @staticmethod
    def original_kind(filename: str) -> Optional[OriginalKind]:
        name = (filename or "").lower()
        dot = name.rfind(".")
        return _KIND_BY_EXT.get(name[dot:]) if dot >= 0 else None
