"""실행 단위 인용 번호 레지스트리 (answer-citation-verification D-01·D-02).

검색 도구(라벨러)와 답변 노드는 같은 프로세스에서 같은 run_id 를 본다 —
RunContext·실행 유스케이스를 바꾸지 않고 프로세스 메모리 사전으로 번호를 공유한다.
TTL 이 지난 실행과 최대 실행 수를 넘는 오래된 실행은 버린다(LRU).
"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field

from src.domain.answer_citation.models import RegisteredChunk


@dataclass
class _RunEntry:
    touched_at: float
    keys: dict[str, int] = field(default_factory=dict)
    chunks: dict[int, RegisteredChunk] = field(default_factory=dict)


class CitationRegistry:
    def __init__(
        self,
        *,
        ttl_seconds: float = 1800.0,
        max_runs: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_runs = max_runs
        self._clock = clock
        self._runs: OrderedDict[str, _RunEntry] = OrderedDict()
        self._lock = threading.Lock()

    def assign(
        self,
        run_id: str,
        *,
        chunk_id: str | None,
        document_id: str | None,
        page: int | None,
        text: str,
    ) -> int:
        """같은 실행·같은 청크는 같은 번호. 새 청크는 다음 번호(1부터)."""
        key = chunk_id or "text:" + hashlib.sha1(text.encode("utf-8")).hexdigest()
        with self._lock:
            entry = self._entry(run_id)
            marker = entry.keys.get(key)
            if marker is None:
                marker = len(entry.chunks) + 1
                entry.keys[key] = marker
                entry.chunks[marker] = RegisteredChunk(
                    marker=marker,
                    chunk_id=chunk_id,
                    document_id=document_id,
                    page=page,
                    text=text,
                )
            return marker

    def chunks(self, run_id: str) -> dict[int, RegisteredChunk]:
        """번호 → 청크 (복사본). 없거나 만료면 빈 사전."""
        with self._lock:
            self._evict()
            entry = self._runs.get(run_id)
            return dict(entry.chunks) if entry is not None else {}

    def discard(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)

    def _entry(self, run_id: str) -> _RunEntry:
        self._evict()
        now = self._clock()
        entry = self._runs.get(run_id)
        if entry is None:
            entry = _RunEntry(touched_at=now)
            self._runs[run_id] = entry
        entry.touched_at = now
        self._runs.move_to_end(run_id)
        while len(self._runs) > self._max_runs:
            self._runs.popitem(last=False)
        return entry

    def _evict(self) -> None:
        now = self._clock()
        expired = [r for r, e in self._runs.items() if now - e.touched_at > self._ttl]
        for run_id in expired:
            del self._runs[run_id]
