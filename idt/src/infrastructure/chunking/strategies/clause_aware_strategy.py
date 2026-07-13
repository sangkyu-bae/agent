"""조·항 경계 인식 청킹 전략 (clause-aware-chunking Design §6).

파이프라인:
  ① parent 경계 규칙(조)으로 분할 → 조 전체 = parent
  ② 조 내부를 child 경계(항·호)로 세그먼트화 → chunk_size 이내 그리디 병합
  ③ 병합 후에도 초과하는 조각만 토큰 분할 + overlap 적용

산출 메타데이터는 기존 parent_child 계약(chunk_type/chunk_id/parent_id/children_ids/
chunk_index/total_chunks)을 준수하여 하이브리드 검색이 무수정 동작한다 (Design D9).
추가 필드: clause_title, page_start, page_end, boundary.
"""
import re
import uuid
from typing import Pattern

from langchain_core.documents import Document

from src.domain.chunking.interfaces import ChunkingStrategy
from src.domain.chunking.value_objects import ChunkingConfig
from src.infrastructure.chunking.base_token_chunker import BaseTokenChunker

_PAGE_SEPARATOR = "\n\n"
_CHUNK_META_KEYS = frozenset({
    "chunk_type", "chunk_id", "chunk_index", "total_chunks",
    "parent_id", "children_ids", "clause_title", "page_start",
    "page_end", "boundary",
})


class ClauseAwareStrategy(ChunkingStrategy):
    def __init__(
        self,
        parent_patterns: list[Pattern],
        child_patterns: list[Pattern],
        parent_config: ChunkingConfig,
        child_config: ChunkingConfig,
    ) -> None:
        self._parent_patterns = parent_patterns
        self._child_patterns = child_patterns
        self._parent_config = parent_config
        self._child_config = child_config
        self._parent_chunker = BaseTokenChunker(parent_config)
        self._child_chunker = BaseTokenChunker(child_config)

    def chunk(self, documents: list[Document]) -> list[Document]:
        if not documents:
            return []

        full_text, page_map, base_meta = self._join_pages(documents)
        if not full_text.strip():
            return []

        segments = self._split_parents(full_text)
        result: list[Document] = []
        for clause_title, seg_text, boundary, start in segments:
            page_start, page_end = self._locate_pages(page_map, start, seg_text)
            result.extend(
                self._build_parent_with_children(
                    base_meta, clause_title, seg_text,
                    boundary, page_start, page_end,
                )
            )

        self._reindex_children(result)
        return result

    def _join_pages(
        self, documents: list[Document]
    ) -> tuple[str, list[tuple[int, int, int]], dict]:
        """페이지 결합 + offset→페이지 매핑 + chunk 관련 키 제거한 base 메타 (D8)."""
        parts: list[str] = []
        page_map: list[tuple[int, int, int]] = []
        cursor = 0
        for doc in documents:
            text = doc.page_content or ""
            page_no = doc.metadata.get("page", len(page_map) + 1)
            end = cursor + len(text)
            page_map.append((cursor, end, page_no))
            parts.append(text)
            cursor = end + len(_PAGE_SEPARATOR)
        base_meta = {
            k: v
            for k, v in documents[0].metadata.items()
            if k not in _CHUNK_META_KEYS
        }
        return _PAGE_SEPARATOR.join(parts), page_map, base_meta

    def _split_parents(self, text: str) -> list[tuple[str, str, str, int]]:
        """첫 매치가 존재하는 parent 패턴으로 분할.

        (clause_title, text, boundary, start_offset) — start_offset은 페이지 매핑용
        누적 오프셋으로, 동일 텍스트 조가 중복돼도 정확한 페이지를 산출한다 (Design D8).
        """
        matches = self._first_matching(text, self._parent_patterns)
        if not matches:
            return [("(전문)", text, "fallback", 0)]

        segments: list[tuple[str, str, str, int]] = []
        if matches[0].start() > 0:
            preamble = text[: matches[0].start()]
            if preamble.strip():
                segments.append(("(전문)", preamble, "clause", 0))

        for idx, match in enumerate(matches):
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            seg_text = text[start:end]
            if seg_text.strip():
                segments.append(
                    (self._title_of(seg_text), seg_text, "clause", start)
                )
        return segments

    def _first_matching(
        self, text: str, patterns: list[Pattern]
    ) -> list[re.Match]:
        for pattern in patterns:
            found = list(pattern.finditer(text))
            if found:
                return found
        return []

    def _build_parent_with_children(
        self,
        base_meta: dict,
        clause_title: str,
        seg_text: str,
        boundary: str,
        page_start: int,
        page_end: int,
    ) -> list[Document]:
        """조가 parent 상한 초과 시 복수 parent로 분할(같은 clause_title 공유)."""
        result: list[Document] = []
        parent_texts = self._parent_chunker.split_by_tokens(seg_text)
        for parent_text in parent_texts:
            parent_id = self._new_id()
            children = self._split_children(parent_text)
            children_ids = [self._new_id() for _ in children]
            common = {
                "clause_title": clause_title,
                "page_start": page_start,
                "page_end": page_end,
            }
            parent_meta = {
                **base_meta, **common,
                "chunk_type": "parent",
                "chunk_id": parent_id,
                "chunk_index": len(result),
                "total_chunks": len(parent_texts),
                "children_ids": children_ids,
                "boundary": boundary,
            }
            result.append(
                Document(page_content=parent_text, metadata=parent_meta)
            )
            for child_id, (child_text, child_boundary) in zip(
                children_ids, children
            ):
                child_meta = {
                    **base_meta, **common,
                    "chunk_type": "child",
                    "chunk_id": child_id,
                    "parent_id": parent_id,
                    "chunk_index": 0,
                    "total_chunks": 0,
                    "boundary": child_boundary,
                }
                result.append(
                    Document(page_content=child_text, metadata=child_meta)
                )
        return result

    def _split_children(self, parent_text: str) -> list[tuple[str, str]]:
        """② child 경계로 세그먼트화 → 그리디 병합 → ③ 초과분만 토큰 분할."""
        segments = self._segment_by_children(parent_text)
        merged = self._greedy_merge(segments)

        children: list[tuple[str, str]] = []
        for seg in merged:
            if self._child_chunker.count_tokens(seg) > self._child_config.chunk_size:
                for sub in self._child_chunker.split_by_tokens(seg):
                    children.append((sub, "token"))
            else:
                children.append((seg, "clause"))
        if not children:
            children.append((parent_text, "clause"))
        return children

    def _segment_by_children(self, text: str) -> list[str]:
        matches = self._first_matching(text, self._child_patterns)
        if not matches:
            return [text]
        segments: list[str] = []
        if matches[0].start() > 0:
            head = text[: matches[0].start()]
            if head.strip():
                segments.append(head)
        for idx, match in enumerate(matches):
            start = match.start()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            seg = text[start:end]
            if seg.strip():
                segments.append(seg)
        return segments

    def _greedy_merge(self, segments: list[str]) -> list[str]:
        """인접 세그먼트를 chunk_size 이내로 그리디 병합 (Design D16)."""
        merged: list[str] = []
        current = ""
        for seg in segments:
            candidate = (current + "\n" + seg) if current else seg
            if self._child_chunker.count_tokens(candidate) > self._child_config.chunk_size:
                if current:
                    merged.append(current)
                current = seg
            else:
                current = candidate
        if current:
            merged.append(current)
        return merged

    def _locate_pages(
        self, page_map: list[tuple[int, int, int]], start: int, seg_text: str
    ) -> tuple[int, int]:
        if start < 0:
            first = page_map[0][2] if page_map else 1
            last = page_map[-1][2] if page_map else 1
            return first, last
        end = start + len(seg_text)
        page_start = page_map[0][2] if page_map else 1
        page_end = page_start
        for lo, hi, page_no in page_map:
            if lo < end and hi > start:
                page_end = page_no
                if lo <= start:
                    page_start = page_no
        return page_start, page_end

    @staticmethod
    def _reindex_children(result: list[Document]) -> None:
        """child의 chunk_index/total_chunks를 문서 전체 기준 재부여 (parent_child 선례)."""
        children = [d for d in result if d.metadata.get("chunk_type") == "child"]
        total = len(children)
        for i, child in enumerate(children):
            child.metadata["chunk_index"] = i
            child.metadata["total_chunks"] = total

    @staticmethod
    def _title_of(seg_text: str) -> str:
        first_line = seg_text.strip().splitlines()[0] if seg_text.strip() else ""
        return first_line[:100]

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())

    def get_strategy_name(self) -> str:
        return "clause_aware"

    def get_chunk_size(self) -> int:
        return self._child_config.chunk_size
