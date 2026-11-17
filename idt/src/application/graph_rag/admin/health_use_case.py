"""그래프 백엔드 상태 (Design §4.1 health) — 연결 실패도 예외 없이 상태로 돌려준다."""

from __future__ import annotations

from src.domain.graph_rag.interfaces import GraphStorePort
from src.domain.graph_rag.policies import is_external_graph_uri
from src.domain.graph_rag.value_objects import GraphHealth


class GraphHealthUseCase:
    def __init__(
        self,
        *,
        store: GraphStorePort | None,
        backend: str,
        uri: str | None,
        node_limit: int,
        rel_limit: int,
    ) -> None:
        self._store = store
        self._backend = backend
        self._uri = uri
        self._node_limit = node_limit
        self._rel_limit = rel_limit

    async def execute(self) -> GraphHealth:
        external = is_external_graph_uri(self._uri)
        if self._store is None:
            return GraphHealth(
                backend=self._backend,
                connected=False,
                external=external,
                error=None if self._backend == "off" else "store not wired",
            )
        try:
            await self._store.ping()
            nodes, rels = await self._store.counts()
        except Exception as e:  # noqa: BLE001 — 상태 조회는 실패를 값으로 돌려준다
            return GraphHealth(
                backend=self._backend,
                connected=False,
                external=external,
                error=f"{type(e).__name__}: {e}"[:300],
            )
        return GraphHealth(
            backend=self._backend,
            connected=True,
            external=external,
            node_count=nodes,
            relationship_count=rels,
            node_limit=self._node_limit,
            relationship_limit=self._rel_limit,
        )
