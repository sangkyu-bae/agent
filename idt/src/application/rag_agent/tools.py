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


_RAG_DENIED_MSG = "RAG 검색 권한이 없습니다."


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

        if self.use_multi_query and self.multi_query_use_case is not None:
            return await self._multi_query_search(query)
        return await self._single_query_search(query)

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

        return await self._format_results(result.results)

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

        return await self._format_results(result.results)

    async def _format_results(self, results: list) -> str:
        """검색 결과를 텍스트로 포맷팅 + (tracker 주입 시) retrieval 영속화.

        M4: 각 hit에 대해 best-effort로 `tracker.record_retrieval`을 호출한다.
        실패는 warning 로그만 남기고 다음 hit 진행 — RAG 답변 흐름을 차단하지 않는다.
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
                await self.tracker.record_retrieval(
                    run_id=ctx.run_id,
                    tool_call_id=ctx.tool_call_id,
                    collection_name=collection,
                    document_id=hit.metadata.get("document_id"),
                    chunk_id=hit.id,
                    score=hit.score,
                    rank_index=rank_index,
                    content_preview=preview,
                    metadata=dict(hit.metadata) if hit.metadata else None,
                )
            except Exception as e:
                if self.logger is not None:
                    self.logger.warning(
                        "record_retrieval failed in InternalDocumentSearchTool (best-effort)",
                        exception=e,
                        chunk_id=hit.id,
                    )

        return "\n\n".join(lines)
