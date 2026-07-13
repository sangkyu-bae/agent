"""InternalDocumentSearchTool: 내부 문서 BM25 + Vector 5:5 하이브리드 검색 LangChain 도구.

M4 (agent-run-observability-m4):
  - tracker DI + RunContext에서 run_id/tool_call_id 획득
  - `_format_results`가 async로 변경 — hit 별 record_retrieval best-effort 호출

agent-user-context Design §7.2:
  - auth_ctx 명시 주입 + ContextVar fallback (Defense in Depth)
  - USE_RAG_SEARCH 없으면 즉시 거부 (1차)
  - READ_DEPARTMENT_DOCS 없으면 metadata_filter['visibility']='public' 강제 (2차)
"""
from typing import Any

from langchain_core.tools import BaseTool
from pydantic import ConfigDict, Field

from src.application.agent_run.auth_context import get_current_auth_context
from src.application.agent_run.context import get_current_run_context
from src.application.agent_run.schemas import RunObservabilityConfig
from src.domain.agent_run.auth_context import AuthContext
from src.domain.hybrid_search.schemas import HybridSearchRequest
from src.domain.permission.value_objects import PermissionCode
from src.domain.rag_agent.schemas import DocumentSource
from src.domain.routed_retrieval.schemas import (
    RoutedChunk,
    RoutedParams,
    RoutedScope,
)


_RAG_DENIED_MSG = "RAG 검색 권한이 없습니다."

# rag-routed-integration D4: 라우팅 스코프 필터 키 3분류.
# kb_id는 RoutedScope로 매핑, viewer_department_ids는 기존 hybrid 경로에서도
# 실효 없는 키(Repository 미지원 시 무시 — _apply_auth_filter 주석)라 동일 취급,
# 그 외 키(visibility 포함)는 요약 payload에 존재 보장이 없어 강등한다.
_ROUTED_SCOPE_KEYS = frozenset({"kb_id"})
_ROUTED_IGNORED_KEYS = frozenset({"viewer_department_ids"})
# rag-routed-integration D6: 근거 헤더의 섹션 요약 1줄 절단 상한 (NFR-04)
_ROUTED_EVIDENCE_SUMMARY_MAX = 150


_DEFAULT_OBS_CFG = RunObservabilityConfig()


class InternalDocumentSearchTool(BaseTool):
    """MORPH-IDX-001 색인 문서 대상 BM25(ES) + Vector(Qdrant) 5:5 하이브리드 검색 도구.

    LangGraph ReAct 에이전트에서 사용. 질문과 관련된 내부 문서를 검색하여
    출처(source) 메타데이터와 함께 반환한다.

    M4: tracker가 주입되면 `_format_results`에서 hit별로 `record_retrieval`을
    best-effort로 호출해 `ai_retrieval_source` 테이블을 채운다.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "internal_document_search"
    description: str = (
        "내부 문서에서 관련 정보를 검색합니다. "
        "질문에 대한 내부 문서 정보가 필요할 때 사용하세요. "
        "입력은 검색할 한국어 쿼리 문자열입니다."
    )

    hybrid_search_use_case: Any
    multi_query_use_case: Any = None
    top_k: int = 5
    request_id: str = ""
    collected_sources: list[DocumentSource] = Field(default_factory=list)
    search_mode: str = "hybrid"
    use_multi_query: bool = False
    rrf_k: int = 60
    # 벡터 코사인 유사도 컷오프 하한 (0.0 = 비활성). ToolFactory가 주입.
    score_threshold: float = 0.0
    metadata_filter: dict[str, str] = Field(default_factory=dict)
    collection_name: str | None = None
    es_index: str | None = None
    # ── M4 추가 필드 (Optional — graph 외 단독 사용 시 None) ─────────────
    tracker: Any = None  # RunTracker | None
    logger: Any = None   # LoggerInterface | None
    config: Any = None   # RunObservabilityConfig | None
    # ── agent-user-context Design §7.2: AuthContext (Optional) ─────────────
    auth_ctx: Any = None  # AuthContext | None — ToolFactory.bind_auth_ctx로 주입
    # ── rag-routed-integration D1/D2: 라우팅 검색 opt-in (기존 search_mode와 독립) ──
    use_routed_search: bool = False
    routed_retrieval_getter: Any = None  # Callable[[], RoutedRetrievalUseCase] | None

    def _run(self, query: str) -> str:
        raise NotImplementedError("비동기 _arun을 사용하세요.")

    def _resolve_auth_ctx(self) -> AuthContext:
        """Defense in Depth: 명시 → ContextVar → public_anonymous 순.

        anonymous는 USE_RAG_SEARCH 권한이 없으므로 자동 거부.
        """
        if isinstance(self.auth_ctx, AuthContext):
            return self.auth_ctx
        from_var = get_current_auth_context()
        if from_var is not None:
            return from_var
        return AuthContext.public_anonymous()

    def _get_effective_filter(self) -> dict[str, str]:
        """_arun에서 세팅된 _effective_metadata_filter 반환.

        _arun이 호출되지 않은 경로(테스트 등)에서는 원본 metadata_filter 그대로.
        """
        eff = getattr(self, "_effective_metadata_filter", None)
        if eff is None:
            return self.metadata_filter
        return eff

    def _apply_auth_filter(
        self, ctx: AuthContext, base_filter: dict[str, str]
    ) -> dict[str, str]:
        """권한에 따라 metadata_filter 자동 보강.

        - READ_DEPARTMENT_DOCS 없으면 visibility=public 강제 (2차 필터)
        - 있으면 viewer_department_ids 주입 (Repository에서 OR 처리)

        주의: 실제 SQL/Qdrant 필터 적용은 HybridSearchUseCase/Repository 책임 (3차 방어).
        """
        eff = dict(base_filter)
        if not ctx.has(PermissionCode.READ_DEPARTMENT_DOCS.value):
            eff["visibility"] = "public"
        else:
            # 향후 Repository가 viewer_department_ids를 OR 처리하도록 확장.
            # 현재는 metadata_filter에 키만 주입 (Repository 미지원 시 무시).
            eff["viewer_department_ids"] = ",".join(ctx.department_ids)
        return eff

    async def _arun(self, query: str) -> str:
        """BM25(ES) + Vector(Qdrant) 하이브리드 검색 실행.

        agent-user-context: 1차 권한 검증을 수행하고 metadata_filter를 보강.
        """
        ctx = self._resolve_auth_ctx()

        # ★ 1차 차단: USE_RAG_SEARCH 권한 없으면 즉시 거부.
        if not ctx.has(PermissionCode.USE_RAG_SEARCH.value):
            return _RAG_DENIED_MSG

        # ★ 2차 필터링: 부서 권한에 따라 visibility 강제.
        # self.metadata_filter는 Pydantic 필드라 직접 변경하지 않고 적용 시점에 합성.
        self._effective_metadata_filter = self._apply_auth_filter(
            ctx, self.metadata_filter,
        )

        # rag-routed-integration D3: opt-in 시 라우팅 시도 — None(강등)이면
        # 아래 기존 흐름(이 에이전트의 search_mode 경로) 그대로 계속.
        if self.use_routed_search:
            routed = await self._routed_search(query)
            if routed is not None:
                return routed

        if self.use_multi_query and self.multi_query_use_case is not None:
            return await self._multi_query_search(query)
        return await self._single_query_search(query)

    def _routed_degrade(self, reason: str, **extra) -> None:
        """강등 사유 로그 (D5) — 교차검증 강등률 관측용."""
        if self.logger is not None:
            self.logger.warning(
                "Routed search degraded to legacy path",
                reason=reason,
                request_id=self.request_id,
                **extra,
            )

    def _routed_scope(self) -> RoutedScope | None:
        """effective filter 키 3분류 → 스코프 매핑 또는 None(강등) (D4)."""
        effective = self._get_effective_filter()
        incompatible = [
            key
            for key in effective
            if key not in _ROUTED_SCOPE_KEYS and key not in _ROUTED_IGNORED_KEYS
        ]
        if incompatible:
            self._routed_degrade(
                "filter_incompatible", filter_keys=sorted(incompatible)
            )
            return None
        return RoutedScope(
            collection_name=self.collection_name,
            kb_id=effective.get("kb_id"),
        )

    async def _routed_search(self, query: str) -> str | None:
        """3계층 라우팅 검색 시도 — 실패/비호환 시 None 반환(강등) (D3~D5)."""
        if self.routed_retrieval_getter is None:
            self._routed_degrade("not_wired")
            return None
        scope = self._routed_scope()
        if scope is None:
            return None
        params = RoutedParams(top_k=self.top_k, rrf_k=self.rrf_k)
        try:
            result = await self.routed_retrieval_getter().execute(
                query, scope, params, self.request_id
            )
        except Exception as e:
            self._routed_degrade("error", exception=e)
            return None
        if not result.results:
            self._routed_degrade("empty")
            return None
        if self.logger is not None:
            self.logger.info(
                "Routed search completed",
                request_id=self.request_id,
                routed_results=len(result.results) - result.fallback_count,
                fallback_used=result.fallback_used,
            )
        return await self._format_routed_results(result.results, query)

    async def _multi_query_search(self, query: str) -> str:
        """Multi-Query 워크플로우를 통한 검색."""
        result = await self.multi_query_use_case.execute(
            query=query,
            request_id=self.request_id,
            top_k=self.top_k,
            collection_name=self.collection_name,
            es_index=self.es_index,
            metadata_filter=self._get_effective_filter() if self._get_effective_filter() else None,
        )

        if not result.results:
            return "관련 내부 문서를 찾지 못했습니다."

        # retrieval-observability D6: chunk_id → 기여 쿼리 역맵.
        # per_query_hits 미제공(None)이면 빈 맵 → search_query는 원 tool 입력 폴백.
        hit_queries: dict[str, list[str]] = {}
        for pq in (result.per_query_hits or []):
            for hid in pq.hit_ids:
                hit_queries.setdefault(hid, []).append(pq.query)

        return await self._format_results(
            result.results,
            search_query=query,
            query_source="multi_query",
            search_mode="hybrid",
            hit_queries=hit_queries,
            extra_metadata={"generated_queries": result.generated_queries},
        )

    async def _single_query_search(self, query: str) -> str:
        """기존 단일 쿼리 하이브리드 검색."""
        if self.search_mode == "vector_only":
            bm25_top_k = 0
            vector_top_k = self.top_k * 2
        elif self.search_mode == "bm25_only":
            bm25_top_k = self.top_k * 2
            vector_top_k = 0
        else:
            bm25_top_k = self.top_k * 2
            vector_top_k = self.top_k * 2

        request = HybridSearchRequest(
            query=query,
            top_k=self.top_k,
            bm25_top_k=bm25_top_k,
            vector_top_k=vector_top_k,
            rrf_k=self.rrf_k,
            metadata_filter=self._get_effective_filter(),
            collection_name=self.collection_name,
            es_index=self.es_index,
            vector_score_threshold=self.score_threshold,
        )
        result = await self.hybrid_search_use_case.execute(request, self.request_id)

        if not result.results:
            return "관련 내부 문서를 찾지 못했습니다."

        return await self._format_results(
            result.results,
            search_query=query,
            query_source="original",
            search_mode=self.search_mode,
        )

    async def _format_routed_results(
        self, chunks: list[RoutedChunk], query: str = ""
    ) -> str:
        """라우팅 결과 포맷팅 — 근거 헤더 + 요약 1줄 + 본문 (D6).

        내장 폴백 결과(from_fallback)는 기존 포맷을 준용하고,
        collected_sources/record_retrieval은 기존 계약과 동형으로 채운다.
        """
        lines: list[str] = []
        ctx = get_current_run_context() if self.tracker is not None else None
        for rank_index, chunk in enumerate(chunks, start=1):
            source = self._routed_source_label(chunk)
            if chunk.from_fallback or chunk.section is None:
                lines.append(f"[출처: {source}]\n{chunk.content}")
            else:
                summary_line = chunk.section.summary.split("\n")[0][
                    :_ROUTED_EVIDENCE_SUMMARY_MAX
                ]
                lines.append(
                    f"[출처: {source}]\n요약: {summary_line}\n{chunk.content}"
                )
            self.collected_sources.append(
                DocumentSource(
                    content=chunk.content,
                    source=source,
                    chunk_id=chunk.section_ref,
                    score=chunk.score,
                )
            )
            await self._record_routed_retrieval(ctx, chunk, rank_index, query)
        return "\n\n".join(lines)

    @staticmethod
    def _routed_source_label(chunk: RoutedChunk) -> str:
        if chunk.from_fallback or chunk.document is None:
            return chunk.clause_title or chunk.document_id or "unknown"
        filename = chunk.document.filename or chunk.document_id
        if chunk.clause_title:
            return f"{filename} > {chunk.clause_title}"
        return filename

    async def _record_routed_retrieval(
        self, ctx, chunk: RoutedChunk, rank_index: int, query: str = ""
    ) -> None:
        """라우팅 hit의 record_retrieval — 기존 계약과 동형 best-effort.

        metadata에 search=routed/from_fallback을 표기해 RRF 점수 스케일을
        기존 코사인/BM25 기록과 구분한다 (D6, 혼합 비교 금지).
        retrieval-observability D7: search_mode=routed, 개별 점수는 NULL 유지.
        """
        if ctx is None or ctx.run_id is None:
            return
        preview_max = (self.config or _DEFAULT_OBS_CFG).retrieval_preview_max_bytes
        try:
            await self.tracker.record_retrieval(
                run_id=ctx.run_id,
                tool_call_id=ctx.tool_call_id,
                collection_name=self.collection_name or "unknown",
                document_id=chunk.document_id or None,
                chunk_id=chunk.section_ref,
                score=chunk.score,
                rank_index=rank_index,
                content_preview=chunk.content[:preview_max] if chunk.content else None,
                metadata={
                    "search": "routed",
                    "from_fallback": str(chunk.from_fallback),
                    "clause_title": chunk.clause_title,
                },
                search_query=query or None,
                query_source="original",
                search_mode="routed",
            )
        except Exception as e:
            if self.logger is not None:
                self.logger.warning(
                    "record_retrieval failed in routed search (best-effort)",
                    exception=e,
                    chunk_id=chunk.section_ref,
                )

    async def _format_results(
        self,
        results: list,
        *,
        search_query: str | None = None,
        query_source: str | None = None,
        search_mode: str | None = None,
        hit_queries: dict[str, list[str]] | None = None,
        extra_metadata: dict | None = None,
    ) -> str:
        """검색 결과를 텍스트로 포맷팅 + (tracker 주입 시) retrieval 영속화.

        M4: 각 hit에 대해 best-effort로 `tracker.record_retrieval`을 호출한다.
        실패는 warning 로그만 남기고 다음 hit 진행 — RAG 답변 흐름을 차단하지 않는다.

        retrieval-observability D5~D7: 검색 실행 컨텍스트를 함께 기록.
        - hit_queries: chunk_id → 기여 재작성 쿼리 목록 (D6, multi_query 전용).
          해당 hit의 search_query는 첫 기여 쿼리, 전체는 metadata.matched_queries.
        - 개별 점수는 HybridSearchResult 필드에서 getattr — 없는 결과형은 NULL (D7).
        """
        lines: list[str] = []
        ctx = get_current_run_context() if self.tracker is not None else None
        preview_max = (self.config or _DEFAULT_OBS_CFG).retrieval_preview_max_bytes

        for rank_index, hit in enumerate(results, start=1):
            source = hit.metadata.get("source", "unknown")
            self.collected_sources.append(
                DocumentSource(
                    content=hit.content,
                    source=source,
                    chunk_id=hit.id,
                    score=hit.score,
                )
            )
            lines.append(f"[출처: {source}]\n{hit.content}")

            if ctx is None or ctx.run_id is None:
                continue

            try:
                preview = hit.content[:preview_max] if hit.content else None
                collection = (
                    self.collection_name
                    or hit.metadata.get("collection")
                    or "unknown"
                )
                matched = hit_queries.get(hit.id, []) if hit_queries else []
                metadata = dict(hit.metadata) if hit.metadata else {}
                if matched:
                    metadata["matched_queries"] = matched
                if extra_metadata:
                    metadata.update(extra_metadata)
                await self.tracker.record_retrieval(
                    run_id=ctx.run_id,
                    tool_call_id=ctx.tool_call_id,
                    collection_name=collection,
                    document_id=hit.metadata.get("document_id"),
                    chunk_id=hit.id,
                    score=hit.score,
                    rank_index=rank_index,
                    content_preview=preview,
                    metadata=metadata or None,
                    search_query=(matched[0] if matched else search_query),
                    query_source=query_source,
                    search_mode=search_mode,
                    bm25_score=getattr(hit, "bm25_score", None),
                    vector_score=getattr(hit, "vector_score", None),
                    bm25_rank=getattr(hit, "bm25_rank", None),
                    vector_rank=getattr(hit, "vector_rank", None),
                    fusion_source=getattr(hit, "source", None),
                )
            except Exception as e:
                if self.logger is not None:
                    self.logger.warning(
                        "record_retrieval failed in InternalDocumentSearchTool (best-effort)",
                        exception=e,
                        chunk_id=hit.id,
                    )

        return "\n\n".join(lines)
