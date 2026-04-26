# Design: 커스텀 RAG 도구 (Custom RAG Tool for Agent Builder)

> Feature ID: CUSTOM-RAG-TOOL-001  
> Plan: `docs/01-plan/features/custom-rag-tool.plan.md`  
> Created: 2026-04-21  
> Status: Draft

---

## 1. 아키텍처 개요

### 1-1. 데이터 흐름

```
[프론트엔드]                    [백엔드]
AgentBuilderPage                
  ├─ RAG 도구 선택              
  ├─ RagConfigPanel 표시        
  │   ├─ collection 선택        GET /api/v1/rag-tools/collections
  │   ├─ metadata key 조회      GET /api/v1/rag-tools/metadata-keys
  │   ├─ top_k / search_mode    
  │   └─ tool_name / desc       
  └─ 에이전트 생성 요청         POST /api/v1/agents
       body.tools[].tool_config ─────→ CreateAgentUseCase
                                         ├─ ToolSelector (tool_id 선택)
                                         ├─ PromptGenerator (프롬프트 생성)
                                         └─ Repository.save()
                                              └─ agent_tool.tool_config (JSON)
```

### 1-2. 에이전트 실행 흐름 (변경 부분)

```
RunAgentUseCase
  └─ WorkflowCompiler.compile()
       └─ ToolFactory.create(tool_id, config)   ← config 전달 추가
            └─ InternalDocumentSearchTool(
                 hybrid_search_use_case,
                 top_k=config.top_k,            ← config 기반 파라미터
                 metadata_filter=config.metadata_filter,
                 search_mode=config.search_mode,
                 name=config.tool_name,
                 description=config.tool_description,
               )
                 └─ HybridSearchUseCase.execute(request)
                      ├─ ES: metadata filter → query.filter
                      └─ Qdrant: metadata filter → query_filter
```

---

## 2. Domain Layer 변경

### 2-1. RagToolConfig (신규)

**파일**: `src/domain/agent_builder/rag_tool_config.py`

```python
from dataclasses import dataclass, field
from typing import Literal

SearchMode = Literal["hybrid", "vector_only", "bm25_only"]


@dataclass(frozen=True)
class RagToolConfig:
    """RAG 도구 커스텀 설정 Value Object."""

    collection_name: str | None = None
    es_index: str | None = None
    metadata_filter: dict[str, str] = field(default_factory=dict)
    top_k: int = 5
    search_mode: SearchMode = "hybrid"
    rrf_k: int = 60
    tool_name: str = "내부 문서 검색"
    tool_description: str = (
        "내부 문서에서 관련 정보를 검색합니다. "
        "질문에 대한 내부 문서 정보가 필요할 때 사용하세요."
    )

    def __post_init__(self) -> None:
        if not 1 <= self.top_k <= 20:
            raise ValueError(f"top_k must be 1~20, got {self.top_k}")
        if self.search_mode not in ("hybrid", "vector_only", "bm25_only"):
            raise ValueError(f"Invalid search_mode: {self.search_mode}")
        if self.rrf_k < 1:
            raise ValueError(f"rrf_k must be >= 1, got {self.rrf_k}")


class RagToolConfigPolicy:
    """RAG 도구 설정 검증 정책."""

    MAX_METADATA_FILTERS = 10
    MAX_TOOL_NAME_LENGTH = 100
    MAX_TOOL_DESCRIPTION_LENGTH = 500

    @classmethod
    def validate(cls, config: RagToolConfig) -> None:
        if len(config.metadata_filter) > cls.MAX_METADATA_FILTERS:
            raise ValueError(
                f"metadata_filter max {cls.MAX_METADATA_FILTERS} entries"
            )
        if len(config.tool_name) > cls.MAX_TOOL_NAME_LENGTH:
            raise ValueError(
                f"tool_name max {cls.MAX_TOOL_NAME_LENGTH} chars"
            )
        if len(config.tool_description) > cls.MAX_TOOL_DESCRIPTION_LENGTH:
            raise ValueError(
                f"tool_description max {cls.MAX_TOOL_DESCRIPTION_LENGTH} chars"
            )
```

### 2-2. WorkerDefinition 확장

**파일**: `src/domain/agent_builder/schemas.py`

```python
@dataclass
class WorkerDefinition:
    """에이전트가 사용할 단일 워커 정의."""

    tool_id: str
    worker_id: str
    description: str
    sort_order: int = 0
    tool_config: dict | None = None   # ← 추가: RAG 등 도구별 설정
```

### 2-3. HybridSearchRequest 확장

**파일**: `src/domain/hybrid_search/schemas.py`

```python
@dataclass(frozen=True)
class HybridSearchRequest:
    """BM25 + 벡터 하이브리드 검색 요청."""

    query: str
    top_k: int = 10
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    metadata_filter: dict[str, str] = field(default_factory=dict)  # ← 추가
```

---

## 3. Infrastructure Layer 변경

### 3-1. AgentToolModel 확장

**파일**: `src/infrastructure/agent_builder/models.py`

```python
from sqlalchemy import JSON

class AgentToolModel(Base):
    __tablename__ = "agent_tool"
    # ... 기존 필드 ...
    tool_config: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, default=None
    )  # ← 추가
```

### 3-2. DB 마이그레이션

**파일**: `db/migration/V014__add_agent_tool_config.sql`

```sql
ALTER TABLE agent_tool
ADD COLUMN tool_config JSON DEFAULT NULL
COMMENT 'Tool-specific configuration (e.g. RAG search scope, parameters)';
```

### 3-3. AgentDefinitionRepository 변경

**파일**: `src/infrastructure/agent_builder/agent_definition_repository.py`

변경 포인트:

1. **save()**: `AgentToolModel` 생성 시 `tool_config=w.tool_config` 전달
2. **_to_domain()**: `WorkerDefinition` 생성 시 `tool_config=t.tool_config` 매핑

```python
# save() 내부
AgentToolModel(
    id=str(uuid.uuid4()),
    agent_id=agent.id,
    tool_id=w.tool_id,
    worker_id=w.worker_id,
    description=w.description,
    sort_order=w.sort_order,
    tool_config=w.tool_config,  # ← 추가
)

# _to_domain() 내부
WorkerDefinition(
    tool_id=t.tool_id,
    worker_id=t.worker_id,
    description=t.description or "",
    sort_order=t.sort_order,
    tool_config=t.tool_config,  # ← 추가
)
```

### 3-4. ToolFactory 확장

**파일**: `src/infrastructure/agent_builder/tool_factory.py`

```python
from src.domain.agent_builder.rag_tool_config import RagToolConfig

class ToolFactory:
    def create(
        self, tool_id: str, request_id: str = "", tool_config: dict | None = None
    ) -> BaseTool:
        get_tool_meta(tool_id)

        match tool_id:
            case "internal_document_search":
                rag_config = self._parse_rag_config(tool_config)
                return InternalDocumentSearchTool(
                    hybrid_search_use_case=self._hybrid_search,
                    request_id=request_id,
                    top_k=rag_config.top_k,
                    search_mode=rag_config.search_mode,
                    rrf_k=rag_config.rrf_k,
                    metadata_filter=rag_config.metadata_filter,
                    collection_name=rag_config.collection_name,
                    es_index=rag_config.es_index,
                    name=rag_config.tool_name,
                    description=rag_config.tool_description,
                )
            # ... 나머지 도구 동일 ...

    def _parse_rag_config(self, tool_config: dict | None) -> RagToolConfig:
        """tool_config dict → RagToolConfig 변환. None이면 기본값."""
        if not tool_config:
            return RagToolConfig()
        return RagToolConfig(**tool_config)
```

### 3-5. HybridSearchUseCase 메타데이터 필터 적용

**파일**: `src/application/hybrid_search/use_case.py`

`_fetch_both()` 메서드 변경:

```python
async def _fetch_both(
    self, request: HybridSearchRequest, request_id: str
) -> tuple[list[SearchHit], list[SearchHit]]:
    # BM25 — metadata_filter를 ES query에 반영
    es_query_body = {"match": {"content": request.query}}
    if request.metadata_filter:
        filter_clauses = [
            {"term": {k: v}} for k, v in request.metadata_filter.items()
        ]
        es_query_body = {
            "bool": {
                "must": [{"match": {"content": request.query}}],
                "filter": filter_clauses,
            }
        }

    es_query = ESSearchQuery(
        index=self._es_index,  # config.es_index는 UseCase 외부에서 처리
        query=es_query_body,
        size=request.bm25_top_k,
    )
    # ... BM25 결과 처리 동일 ...

    # Vector — metadata_filter를 Qdrant filter로 변환
    query_vector = await self._embedding.embed_text(request.query)
    
    search_filter = None
    if request.metadata_filter:
        from src.domain.retriever.value_objects.metadata_filter import MetadataFilter
        search_filter = MetadataFilter(
            custom_filters=request.metadata_filter
        )
    
    vector_docs = await self._vector_store.search_by_vector(
        vector=query_vector,
        top_k=request.vector_top_k,
        filter=search_filter.to_qdrant_filter() if search_filter else None,
    )
    # ... Vector 결과 처리 동일 ...
```

---

## 4. Application Layer 변경

### 4-1. InternalDocumentSearchTool 확장

**파일**: `src/application/rag_agent/tools.py`

```python
class InternalDocumentSearchTool(BaseTool):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "internal_document_search"
    description: str = (
        "내부 문서에서 관련 정보를 검색합니다. "
        "질문에 대한 내부 문서 정보가 필요할 때 사용하세요."
    )

    hybrid_search_use_case: Any
    top_k: int = 5
    request_id: str = ""
    collected_sources: list[DocumentSource] = Field(default_factory=list)

    # ← 신규 필드
    search_mode: str = "hybrid"
    rrf_k: int = 60
    metadata_filter: dict[str, str] = Field(default_factory=dict)
    collection_name: str | None = None
    es_index: str | None = None

    async def _arun(self, query: str) -> str:
        request = HybridSearchRequest(
            query=query,
            top_k=self.top_k,
            bm25_top_k=self.top_k * 2,
            vector_top_k=self.top_k * 2,
            rrf_k=self.rrf_k,
            metadata_filter=self.metadata_filter,  # ← 필터 전달
        )

        # search_mode에 따라 분기
        if self.search_mode == "vector_only":
            result = await self._vector_only_search(query)
        elif self.search_mode == "bm25_only":
            result = await self._bm25_only_search(query)
        else:
            result = await self.hybrid_search_use_case.execute(
                request, self.request_id
            )

        # ... 결과 처리 동일 ...
```

### 4-2. CreateAgentUseCase 변경

**파일**: `src/application/agent_builder/create_agent_use_case.py`

- `CreateAgentRequest`에 `tool_configs` 필드 추가 시 `WorkerDefinition`에 config 전달

### 4-3. WorkflowCompiler 변경

**파일**: `src/application/agent_builder/workflow_compiler.py`

- `compile()` 시 `WorkerDefinition.tool_config`을 `ToolFactory.create()`에 전달

### 4-4. AgentSpecInferenceService 확장

**파일**: `src/application/auto_agent_builder/agent_spec_inference_service.py`

`_TOOL_DESCRIPTIONS`에 RAG config 옵션 설명 추가:

```python
_TOOL_DESCRIPTIONS = """Available tools:
- internal_document_search: 내부 벡터/ES 하이브리드 검색 (정책/지식베이스 질의)
  * Configurable: collection_name, metadata_filter, top_k, search_mode
  * metadata_filter example: {"department": "finance", "category": "policy"}
  * search_mode: "hybrid" (default), "vector_only", "bm25_only"
- tavily_search: ...
- excel_export: ...
- python_code_executor: ..."""

_RESPONSE_FORMAT = """\nRespond in JSON:
{
  "confidence": 0.0-1.0,
  "tool_ids": ["..."],
  "tool_configs": {
    "internal_document_search": {
      "metadata_filter": {},
      "top_k": 5,
      "search_mode": "hybrid",
      "tool_name": "...",
      "tool_description": "..."
    }
  },
  "middlewares": [...],
  "system_prompt": "...",
  "clarifying_questions": [],
  "reasoning": "..."
}"""
```

`AgentSpecResult`에 `tool_configs` 필드 추가:

```python
@dataclass(frozen=True)
class AgentSpecResult:
    confidence: float
    tool_ids: list[str]
    middleware_configs: list[dict]
    system_prompt: str
    clarifying_questions: list[str]
    reasoning: str
    tool_configs: dict[str, dict] = field(default_factory=dict)  # ← 추가
```

---

## 5. Interfaces Layer 변경

### 5-1. API 스키마 변경

**파일**: `src/application/agent_builder/schemas.py`

```python
class RagToolConfigRequest(BaseModel):
    """RAG 도구 설정 요청 스키마."""
    collection_name: str | None = None
    es_index: str | None = None
    metadata_filter: dict[str, str] = Field(default_factory=dict)
    top_k: int = Field(5, ge=1, le=20)
    search_mode: str = Field("hybrid", pattern="^(hybrid|vector_only|bm25_only)$")
    rrf_k: int = Field(60, ge=1)
    tool_name: str = Field("내부 문서 검색", max_length=100)
    tool_description: str = Field("", max_length=500)


class WorkerInfo(BaseModel):
    tool_id: str
    worker_id: str
    description: str
    sort_order: int
    tool_config: dict | None = None   # ← 추가


class CreateAgentRequest(BaseModel):
    user_request: str = Field(..., max_length=1000)
    name: str = Field(..., max_length=200)
    user_id: str
    llm_model_id: str | None = None
    visibility: str = Field("private", pattern="^(private|department|public)$")
    department_id: str | None = None
    temperature: float = Field(0.70, ge=0.0, le=2.0)
    tool_configs: dict[str, RagToolConfigRequest] | None = None  # ← 추가


class ToolMetaResponse(BaseModel):
    tool_id: str
    name: str
    description: str
    configurable: bool = False        # ← 추가: 설정 가능 여부
    config_schema: dict | None = None # ← 추가: 설정 스키마 (프론트 동적 렌더링용)
```

### 5-2. 새 API 엔드포인트

**파일**: `src/api/routes/rag_tool_router.py` (신규)

```python
router = APIRouter(prefix="/api/v1/rag-tools", tags=["RAG Tools"])


@router.get("/collections")
async def list_collections(
    qdrant_client=Depends(get_qdrant_client),
) -> CollectionsResponse:
    """사용 가능한 Qdrant 컬렉션 목록."""
    collections = await qdrant_client.get_collections()
    return CollectionsResponse(
        collections=[
            CollectionInfo(
                name=c.name,
                display_name=COLLECTION_ALIASES.get(c.name, c.name),
                vectors_count=c.vectors_count,
            )
            for c in collections.collections
        ]
    )


@router.get("/metadata-keys")
async def list_metadata_keys(
    collection_name: str = Query(None),
    es_repo=Depends(get_es_repo),
    qdrant_client=Depends(get_qdrant_client),
) -> MetadataKeysResponse:
    """필터링 가능한 메타데이터 키 목록 + 샘플 값."""
    # Qdrant 컬렉션에서 샘플 포인트를 조회하여 메타데이터 키 추출
    ...
```

### 5-3. 응답 스키마

```python
class CollectionInfo(BaseModel):
    name: str
    display_name: str
    vectors_count: int | None = None


class CollectionsResponse(BaseModel):
    collections: list[CollectionInfo]


class MetadataKeyInfo(BaseModel):
    key: str
    sample_values: list[str]
    value_count: int


class MetadataKeysResponse(BaseModel):
    keys: list[MetadataKeyInfo]
```

---

## 6. 프론트엔드 변경

### 6-1. 타입 정의

**파일**: `idt_front/src/types/ragToolConfig.ts`

```typescript
export interface RagToolConfig {
  collection_name?: string;
  es_index?: string;
  metadata_filter: Record<string, string>;
  top_k: number;
  search_mode: 'hybrid' | 'vector_only' | 'bm25_only';
  rrf_k: number;
  tool_name: string;
  tool_description: string;
}

export interface CollectionInfo {
  name: string;
  display_name: string;
  vectors_count?: number;
}

export interface MetadataKeyInfo {
  key: string;
  sample_values: string[];
  value_count: number;
}
```

### 6-2. API 상수

**파일**: `idt_front/src/constants/api.ts`

```typescript
export const RAG_TOOLS = {
  COLLECTIONS: '/api/v1/rag-tools/collections',
  METADATA_KEYS: '/api/v1/rag-tools/metadata-keys',
} as const;
```

### 6-3. 커스텀 훅

**파일**: `idt_front/src/hooks/useRagToolConfig.ts`

```typescript
export function useCollections() {
  return useQuery({
    queryKey: ['rag-tools', 'collections'],
    queryFn: () => ragToolService.getCollections(),
  });
}

export function useMetadataKeys(collectionName?: string) {
  return useQuery({
    queryKey: ['rag-tools', 'metadata-keys', collectionName],
    queryFn: () => ragToolService.getMetadataKeys(collectionName),
    enabled: !!collectionName,
  });
}
```

### 6-4. UI 컴포넌트 구조

```
AgentBuilderPage/
  └─ ToolSelector (기존)
       └─ RagConfigPanel (신규)
            ├─ CollectionSelect      — 컬렉션 드롭다운
            ├─ MetadataFilterEditor   — key-value 필터 입력 (동적 추가/삭제)
            ├─ SearchParamsControl    — top_k 슬라이더 + search_mode 라디오
            └─ ToolIdentityEditor     — tool_name, tool_description 입력
```

**표시 조건**: `tool_id === "internal_document_search"` 선택 시에만 RagConfigPanel 노출

---

## 7. 다중 RAG 도구 지원 설계

### 7-1. UniqueConstraint 변경

현재 `agent_tool` 테이블에 `(agent_id, tool_id)` 유니크 제약이 있어 같은 `tool_id`를 복수 추가할 수 없음.

**해결**: 유니크 제약을 `(agent_id, worker_id)`로 변경

```sql
-- 기존 제약 삭제
ALTER TABLE agent_tool DROP INDEX uq_agent_tool;

-- 새 제약 추가 (worker_id 기준)
ALTER TABLE agent_tool
ADD CONSTRAINT uq_agent_worker UNIQUE (agent_id, worker_id);
```

### 7-2. worker_id 생성 규칙

다중 RAG 도구 시 `worker_id`를 구분:

```
internal_document_search        → worker_id: "rag_worker_1"
internal_document_search (2번째) → worker_id: "rag_worker_2"
```

`ToolSelector` 또는 프론트엔드에서 자동 suffix 부여.

### 7-3. LLM 도구 구분

각 RAG 도구가 **다른 name과 description**을 가지므로 LLM이 올바른 도구를 선택할 수 있음:

```
Tool 1: name="금융 정책 검색", description="금융 관련 내부 정책 문서를 검색합니다."
Tool 2: name="기술 매뉴얼 검색", description="기술 지원 매뉴얼을 검색합니다."
```

---

## 8. 하위 호환성

### 8-1. tool_config = NULL 처리

- `tool_config`이 NULL/None이면 `RagToolConfig()` 기본값 사용
- 기존 에이전트는 변경 없이 동작 (전체 문서 검색, top_k=5, hybrid 모드)

### 8-2. API 하위 호환

- `CreateAgentRequest.tool_configs`는 Optional — 기존 요청 그대로 동작
- `WorkerInfo.tool_config`도 Optional — 기존 응답 호환

### 8-3. DB 마이그레이션

- `tool_config` 컬럼은 `DEFAULT NULL` — 기존 행 영향 없음
- 유니크 제약 변경은 별도 마이그레이션 (V015)

---

## 9. 구현 순서 (Implementation Checklist)

### Phase 1: Domain 스키마 (의존성 없음)

- [ ] `src/domain/agent_builder/rag_tool_config.py` — RagToolConfig VO + Policy
- [ ] `src/domain/agent_builder/schemas.py` — WorkerDefinition에 `tool_config` 추가
- [ ] `src/domain/hybrid_search/schemas.py` — HybridSearchRequest에 `metadata_filter` 추가
- [ ] `src/domain/auto_agent_builder/schemas.py` — AgentSpecResult에 `tool_configs` 추가
- [ ] 각 변경에 대한 단위 테스트

### Phase 2: DB 마이그레이션 (Phase 1 이후)

- [ ] `db/migration/V014__add_agent_tool_config.sql`
- [ ] `db/migration/V015__change_agent_tool_unique.sql`
- [ ] `src/infrastructure/agent_builder/models.py` — tool_config 컬럼
- [ ] `src/infrastructure/agent_builder/agent_definition_repository.py` — save/to_domain 매핑

### Phase 3: 검색 확장 (Phase 1 이후)

- [ ] `src/application/hybrid_search/use_case.py` — metadata_filter 적용
- [ ] `src/application/rag_agent/tools.py` — InternalDocumentSearchTool 확장
- [ ] 하이브리드 검색 필터 통합 테스트

### Phase 4: ToolFactory + Agent 실행 (Phase 2, 3 이후)

- [ ] `src/infrastructure/agent_builder/tool_factory.py` — config 기반 도구 생성
- [ ] `src/application/agent_builder/workflow_compiler.py` — config 전달
- [ ] `src/application/agent_builder/create_agent_use_case.py` — tool_configs 처리
- [ ] 에이전트 생성-실행 통합 테스트

### Phase 5: API 엔드포인트 (Phase 3 이후)

- [ ] `src/api/routes/rag_tool_router.py` — collections, metadata-keys 엔드포인트
- [ ] `src/application/agent_builder/schemas.py` — RagToolConfigRequest, ToolMetaResponse 확장
- [ ] `src/api/routes/agent_builder_router.py` — tool_configs 전달

### Phase 6: Auto Agent Builder 연동 (Phase 4, 5 이후)

- [ ] `src/application/auto_agent_builder/agent_spec_inference_service.py` — 프롬프트 + 파싱
- [ ] `src/application/auto_agent_builder/auto_build_use_case.py` — tool_configs 전달

### Phase 7: 프론트엔드 (Phase 5 이후)

- [ ] `idt_front/src/types/ragToolConfig.ts` — 타입 정의
- [ ] `idt_front/src/constants/api.ts` — 엔드포인트 상수
- [ ] `idt_front/src/services/ragToolService.ts` — API 호출
- [ ] `idt_front/src/hooks/useRagToolConfig.ts` — 커스텀 훅
- [ ] `idt_front/src/components/agent-builder/RagConfigPanel.tsx` — 설정 UI
- [ ] AgentBuilderPage에 RagConfigPanel 통합

---

## 10. 테스트 전략

### 10-1. 단위 테스트

| 대상 | 테스트 항목 |
|------|------------|
| `RagToolConfig` | 기본값 생성, 유효성 검증 (top_k 범위, search_mode 값), 불변성 |
| `RagToolConfigPolicy` | metadata_filter 개수 제한, tool_name/description 길이 제한 |
| `HybridSearchRequest` | metadata_filter 포함/미포함 요청 생성 |
| `ToolFactory._parse_rag_config()` | None → 기본값, 부분 config → 머지, 잘못된 config → ValueError |
| `AgentSpecResult` | tool_configs 파싱, 기존 포맷 하위 호환 |

### 10-2. 통합 테스트

| 시나리오 | 검증 항목 |
|---------|----------|
| config 포함 에이전트 생성 | tool_config이 DB에 올바르게 저장되는지 |
| config 포함 에이전트 실행 | metadata_filter가 검색 결과에 실제 반영되는지 |
| config 없는 에이전트 실행 | 기존과 동일하게 전체 문서 검색하는지 (하위 호환) |
| 다중 RAG 도구 에이전트 | 두 RAG 도구가 각각 다른 범위를 검색하는지 |
| 자동 빌더 RAG 추론 | "금융 문서만" 요청 시 적절한 tool_configs 생성되는지 |

### 10-3. 프론트엔드 테스트

| 컴포넌트 | 테스트 항목 |
|---------|------------|
| `RagConfigPanel` | 렌더링, 값 변경 콜백, 기본값 표시 |
| `CollectionSelect` | 컬렉션 목록 로딩, 선택 시 metadata-keys 재조회 |
| `MetadataFilterEditor` | 필터 추가/삭제, 최대 개수 제한 |

---

## 11. 참고

- Plan 문서: `docs/01-plan/features/custom-rag-tool.plan.md`
- 기존 MetadataFilter VO: `src/domain/retriever/value_objects/metadata_filter.py`
- Qdrant 필터 변환: `MetadataFilter.to_qdrant_filter()`
- ES 쿼리 구조: `src/domain/elasticsearch/schemas.py`
