# graph-rag-foundation Design Document

> **Summary**: 코어에는 확장 훅 레지스트리와 실행별 허용값(`SupplementalGrant`)만 넣고, 그래프 RAG는 `wire_graph_rag(app)` 한 줄로 끼워 넣는 독립 모듈로 만든다. 업로드 뒤 추출 잡이 엔티티·관계를 Neo4j(Aura)에 쌓고, Jev와 LLM이 같은 엔티티인지 판정하며, 도구의 최종 검색 결과에 그래프 결과를 RRF로 한 번 더 합친다.
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-16
> **Status**: Draft
> **Planning Doc**: [graph-rag-foundation.plan.md](../../01-plan/features/graph-rag-foundation.plan.md) (v0.3)
> **Selected Architecture**: Option C — Pragmatic Balance

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 여러 문서에 걸친 관계·용어 별칭을 하이브리드 검색이 따라가지 못함. GraphRAG를 받을 저장소·추출·판정·검색 경로가 전혀 없음 |
| **WHO** | 1차: P3 관리자(테스트 페이지에서 추출·판정·검색 검증), 최종 수혜: P1 심사역·P4 행원(근거 회수 향상), P2 KB 운영자(후속 사이클에서 KB 화면 노출) |
| **RISK** | 잘못된 엔티티 병합이 그래프 전체 검색을 오염 / 전역 공유 그래프에서 권한 없는 KB 근거 노출 / Aura(외부 클라우드)에 사내 규정 내용 보관 — 개발·PoC 한정, 도입 전 자체 호스팅 전환 / 청크 수 비례 LLM 비용 / 비대화 경로(웹훅·백그라운드)로 그래프 노출 |
| **SUCCESS** | `GRAPH_BACKEND=off`에서 기존 동작 100% 동일 · 관계·언급의 근거 청크 역추적 실패 0건 · 다문서 질문 부분집합에서 RAGAS context_recall 향상, 나머지 회귀 없음 · 관리자가 DB/Swagger 없이 추출→확인→검색 비교→검토 완주 · `admin_only`에서 일반 사용자 경로 그래프 실행 0건 · 모듈 등록 줄 제거 시 전체 테스트 통과 |
| **SCOPE** | 독립 모듈(코어는 훅 인터페이스만 앎) + 노출 단계 `off → admin_only → general` (이번 사이클은 `admin_only`까지). 백엔드 기반 + 관리자 테스트 페이지 + 관리자에게만 보이는 빌더 토글. 커뮤니티 요약·그래프 시각화·KB 단위 격리·`general` 전환 실행은 제외 |

---

## 1. Overview

### 1.1 Design Goals

1. **빼낼 수 있는 모듈**: `wire_graph_rag(app)` 호출을 지우면 그래프 기능이 흔적 없이 꺼지고, 전체 테스트가 통과한다(SC-9).
2. **기본은 닫힘**: 그래프 검색은 노출 단계, 실행별 허용값, 에이전트 설정의 세 조건이 모두 참일 때만 실행된다. 값이 없거나 읽을 수 없으면 실행하지 않는다.
3. **출처 불변식**: 모든 언급(`MENTIONED_IN`)과 관계(`RELATES`·`REFERS_TO`)는 근거 `chunk_id`·`document_id`를 갖는다. 그래프 검색의 최종 결과는 항상 실제 청크다.
4. **장애 격리**: Neo4j 정지(Aura Free 자동 정지 포함)나 추출 잡 실패는 업로드·채팅을 실패시키지 않는다.
5. **판정 감사**: 같은 엔티티 판정은 판정자·확률·구간과 함께 MySQL에 남고, 사람이 사후에 되돌릴 수 있다.

### 1.2 Design Principles

- **코어는 그래프를 모른다**: 코어가 아는 것은 `domain/extension_hooks/`의 포트와 `SupplementalGrant`뿐이고, 코어 코드에는 "graph" 타입 import가 없다. 단, `RagToolConfig.use_graph`라는 설정 필드 이름은 예외다.
- **선례를 따른다**: 런처 주입은 `summary_launcher`, 전역 설정은 `multimodal_setting`(V065)과 `wire_multimodal`, 실행별 opt-in은 `inject_memory` 선례를 따른다.
- **명시적 전달**: 실행별 허용값은 키워드 인자 체인으로 넘긴다. 싱글턴 상태를 바꾸는 방식(`bind_auth_ctx` 같은)은 쓰지 않는다.
- **얇은 DDD**: 범용 이벤트 버스나 N개 목록용 RRF 재설계는 하지 않는다(YAGNI).

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | A: Minimal | B: Clean | **C: Pragmatic** |
|----------|:-:|:-:|:-:|
| **Approach** | 코어에 그래프 런처·검색을 직접 주입 | 범용 이벤트 버스 + N목록 RRF 재설계 + ContextVar | 좁은 훅 3개(레지스트리) + 최종 결과 재결합(`merge_many`) + 키워드 인자 체인 |
| **New Files** | ~25 | ~45 | ~38 |
| **Modified Files** | ~8 | ~18 | ~12 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (모듈 제거 불가) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 경계 붕괴, SC-9 불충족 | RRF·하이브리드·라우팅 회귀 | 키워드 체인 누락(계약 테스트로 방어) |
| **Recommendation** | ✗ | 구독자 1개뿐이라 과함 | **✓ 선택됨** |

**Selected**: Option C. **Rationale**: "관리자 테스트 후 끼워 넣기"라는 요구를 만족하는 가장 작은 구조다. 하이브리드 검색 내부(`HybridSearchUseCase`·`RRFFusionPolicy.merge`)를 바꾸지 않아 기존 검색 회귀 위험이 낮다. 라우팅·멀티쿼리·단일 검색 세 경로에 같은 방식으로 적용된다.

### 2.1 Component Diagram

```
┌──────────────────────── 코어 (graph_rag 를 import 하지 않음) ─────────────────────────┐
│                                                                                     │
│  domain/extension_hooks/                                                            │
│    ExtensionHooks(registry) ── post_ingest: PostIngestHook | None                   │
│                             ── deletion:    DocumentDeletionHook | None             │
│                             ── supplemental: SupplementalRetrievalSource | None     │
│                             ── exposure:    FeatureExposurePort | None              │
│    SupplementalGrant(caller_is_admin)   SupplementalQuery                           │
│                                                                                     │
│  KnowledgeBaseUploadUseCase ──(업로드 후)──▶ hooks.post_ingest.on_document_ingested │
│  DeleteDocumentUseCase / KB delete ───────▶ hooks.deletion.on_document(s)_deleted   │
│  InternalDocumentSearchTool._arun ────────▶ hooks.supplemental.retrieve (grant 有)  │
│        └─ RRFFusionPolicy.merge_many([primary, supplemental])                       │
│  Agent 저장 유스케이스 ───────────────────▶ hooks.exposure.is_visible (use_graph 정리) │
│  RunAgentUseCase.stream/execute(*, supplemental_grant=None)                         │
│        → _prepare_graph → WorkflowCompiler.compile → ToolFactory.create → Tool      │
│  ws_router / agent_builder_router  : grant 생성 (대화 경로만)                         │
│  webhook / background / schedule / RAGAS / resume : grant 없음 (계약 테스트)          │
└───────────────────────────────▲─────────────────────────────────────────────────────┘
                                │ register(...)  ← api/graph_rag_di.py wire_graph_rag(app)
┌───────────────────────────────┴──────── graph_rag 모듈 ─────────────────────────────┐
│ GraphIngestHook → GraphExtractionLauncher → ExtractGraphUseCase (asyncio task)      │
│     ES 청크 읽기 → RuleExtractor + LlmExtractor → EntityResolver(Jev→LLM) → Neo4j     │
│ GraphDeletionHook → GraphStorePort.delete_document / delete_kb                      │
│ GraphRetrievalSource → RolloutPolicy → EntityLinker → traverse → ES 권한 필터 조회     │
│ GraphExposure → RolloutPolicy.is_visible                                             │
│ admin_graph_rag_router (require_role admin) · graph_rag_router (capabilities)        │
│ Neo4jGraphStore (neo4j driver, 앱 수명 싱글턴) · MySQL 저장소 4종                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                     │                                   │
               Neo4j Aura (neo4j+s://)            MySQL / ES / Qdrant(기존)
```

### 2.2 Data Flow

**적재(추출)**
```
KB 업로드 완료 (KnowledgeBaseUploadUseCase.execute, 요약 런처 직후)
 → hooks.post_ingest.on_document_ingested(DocumentIngestedEvent)  ※ 예외는 로그만 남기고 삼킴
 → GraphIngestHook: stage≠off AND extraction_enabled AND 엑셀 아님 AND status≠failed
 → graph_extraction_job INSERT(pending) → asyncio.create_task(run)
 → ES에서 document_id 청크 조회(요약 청크 제외) → 청크별:
     RuleExtractor(조문 참조) ─┐
     LlmExtractor(구조화 출력) ─┴→ 근거 검증(evidence ⊂ chunk) → 언급 목록
     → EntityResolver: 후보 검색(정규화·별칭·벡터) → 판정 → decision INSERT
     → Neo4j upsert(Entity/Alias/Chunk/MENTIONED_IN/RELATES/REFERS_TO)
 → 카운터 갱신 → completed | partial | failed
```

**검색**
```
InternalDocumentSearchTool._arun
 → 기존 경로(routed | multi | single)로 hits 획득           (변경 없음)
 → 조건: grant≠None AND config.use_graph AND hooks.supplemental≠None
 → GraphRetrievalSource.retrieve(SupplementalQuery)  (timeout_ms, 실패 시 [])
     RolloutPolicy.allows(stage, grant.caller_is_admin)? 아니면 []
     → EntityLinker(Kiwi 명사 + 정규화/별칭 일치 + 질의 벡터) → 씨앗 엔티티 ≤5
     → Neo4j 최대 N단계 탐색 → 후보 chunk_id ≤50 (점수: Σ 1/(1+hops))
     → ES terms(chunk_id) + 도구의 hard/lenient 필터 + collection 범위 → 권한 통과 청크만
 → RRFFusionPolicy.merge_many([("primary",hits,1.0),("graph",ghits,w)], top_k)
 → _format_results → tracker.record_retrieval(fusion_source="graph"|"both+graph"…)
```

**판정**
```
언급 m(이름, 타입, 근거 chunk)
 → 정규화 키 n = normalize(m.name)
 → 후보 C = (scope_key 안의 정규화 이름·별칭 정확 일치) ∪ (이름 벡터 top-K, cos≥0.75), 같은 타입(또는 '기타')만, 최대 K
 → |C|=0                    → NEW         (decided_by=rule, band=auto_new)
 → 정확 일치 1개·같은 타입   → LINK        (decided_by=rule, band=auto_link)
 → Jev 사용 가능(설정 on, 포트 조립, 오류 없음):
       ChoiceQuestion{C1..Ck, NEW} → p* = max_i p(Ci)
       p* ≥ link_threshold → LINK argmax  (jev, auto_link)
       p* < new_threshold  → NEW          (jev, auto_new)
       그 사이             → LLM 재판정   (llm_rejudge, review=pending)
 → Jev 불가(off·미조립·JudgmentError) → LLM 선택 {label, confidence}
       (llm_fallback, confidence≠high 이면 review=pending)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| GraphRetrievalSource | GraphStorePort, MorphAnalyzerInterface, EmbeddingInterface, ES repo, GraphSettingsReader | 연결·탐색·권한 필터 |
| ExtractGraphUseCase | ES repo(청크 읽기), LlmExtractor, RuleExtractor, EntityResolver, GraphStorePort, JobRepo | 추출 잡 |
| EntityResolver | GraphStorePort(후보), JudgmentPort(선택), LlmChoiceResolver, DecisionRepo | 같은 엔티티 판정 |
| Neo4jGraphStore | `neo4j` Python driver (5.x, async) | Aura/자체 호스팅 공용 |
| 코어 훅 지점 | `domain/extension_hooks` 만 | 경계 |

신규 의존성: `neo4j>=5.20` — `pyproject.toml`의 선택 extra `graph`. 이 extra가 설치되지 않았는데 `GRAPH_BACKEND=neo4j`이면 경고 로그를 남기고 모듈을 등록하지 않는다.

---

## 3. Data Model

### 3.1 Domain Entities (domain/graph_rag/)

```python
class RolloutStage(StrEnum): OFF="off"; ADMIN_ONLY="admin_only"; GENERAL="general"
class ResolutionBand(StrEnum): AUTO_LINK="auto_link"; AUTO_NEW="auto_new"; REJUDGE="rejudge"; FALLBACK="fallback"
class DecidedBy(StrEnum): RULE="rule"; JEV="jev"; LLM_REJUDGE="llm_rejudge"; LLM_FALLBACK="llm_fallback"
class ReviewStatus(StrEnum): NONE="none"; PENDING="pending"; APPROVED="approved"; REJECTED="rejected"

@dataclass(frozen=True)
class GraphRagSettings:          # 값 검증 단일 출처 (__post_init__ → ValueError)
    rollout_stage: RolloutStage
    extraction_enabled: bool
    jev_enabled: bool
    link_threshold: float        # 0 < new_threshold < link_threshold <= 1
    new_threshold: float
    extraction_llm_model_id: str | None
    rejudge_llm_model_id: str | None   # None → extraction 모델 사용
    concurrency: int             # 1..8
    max_llm_calls_per_doc: int   # 1..2000
    candidate_top_k: int         # 1..8 (Jev 라벨 수 = k+1)
    max_hops: int                # 1..3
    graph_rrf_weight: float      # 0..1
    retrieval_timeout_ms: int    # 100..5000
    entity_types: tuple[str, ...]     # '기타' 반드시 포함
    relation_types: tuple[str, ...]   # '기타' 반드시 포함

@dataclass(frozen=True)
class Mention:      name: str; type: str; description: str; chunk_id: str; document_id: str; kb_id: str|None; context: str
@dataclass(frozen=True)
class RelationDraft: source: str; target: str; type: str; evidence: str; chunk_id: str; document_id: str; kb_id: str|None
@dataclass(frozen=True)
class Candidate:    entity_id: str; name: str; type: str; description: str; aliases: tuple[str,...]; match: Literal["exact","vector"]; similarity: float
@dataclass(frozen=True)
class ResolutionOutcome: entity_id: str | None; create_new: bool; decided_by: DecidedBy; band: ResolutionBand; probability: float|None; review_status: ReviewStatus; chosen_label: str
```

코어 확장 포트 (`domain/extension_hooks/`, graph 용어 없음):

```python
@dataclass(frozen=True)
class DocumentIngestedEvent: document_id: str; kb_id: str|None; collection_name: str; filename: str; user_id: str; chunk_count: int; status: str
@dataclass(frozen=True)
class DocumentDeletedEvent:  document_id: str; kb_id: str|None; collection_name: str
@dataclass(frozen=True)
class SupplementalGrant:     caller_is_admin: bool          # 존재 자체가 "대화 경로 opt-in"
@dataclass(frozen=True)
class SupplementalQuery:     query: str; top_k: int; collection_name: str|None; es_index: str|None
                             hard_filter: Mapping[str,Any]; lenient_filter: Mapping[str,Any]
                             grant: SupplementalGrant; request_id: str

class PostIngestHook(ABC):            async def on_document_ingested(self, e, request_id) -> None
class DocumentDeletionHook(ABC):      async def on_document_deleted(self, e, request_id) -> None
                                      async def on_kb_deleted(self, kb_id, request_id) -> None
class SupplementalRetrievalSource(ABC):
    source_label: str                                        # "graph"
    weight: float                                            # 설정에서 읽은 RRF 가중치
    async def retrieve(self, q: SupplementalQuery) -> list[HybridSearchResult]
class FeatureExposurePort(ABC):       async def is_visible(self, feature: str, caller_is_admin: bool) -> bool

@dataclass
class ExtensionHooks:                 # main.py 단일 인스턴스, 기본은 전부 None(no-op)
    post_ingest: PostIngestHook | None = None
    deletion: DocumentDeletionHook | None = None
    supplemental: SupplementalRetrievalSource | None = None
    exposure: FeatureExposurePort | None = None
    def register(...): ...            # 같은 슬롯 이중 등록 시 ValueError(기동 시점 실패)
```

`ExtensionHooks`는 기동 시 한 번 채우고, 요청 중에는 읽기만 한다. 이 점에서 `bind_auth_ctx`처럼 요청마다 바뀌는 상태와는 다르다.

### 3.2 Neo4j Graph Model

```
(:Entity {id, scope_key, name, normalized_name, type, description,
          name_embedding: float[DIM], created_at, updated_at})
(:Alias  {scope_key, normalized, surface})-[:ALIAS_OF]->(:Entity)
(:Chunk  {chunk_id, document_id, kb_id, collection_name, extractor_version, extracted_at})

(:Entity)-[:MENTIONED_IN {decision_id, document_id}]->(:Chunk)
(:Entity)-[:RELATES {id, type, evidence_chunk_id, document_id, kb_id, evidence_text,
                     source_decision_id, target_decision_id, extractor_version}]->(:Entity)
(:Entity {type:'조문'})-[:REFERS_TO {evidence_chunk_id, document_id, kb_id}]->(:Entity {type:'조문'})
```

- `scope_key`: 이번 사이클은 항상 `"global"`이다. KB 단위로 격리할 때는 `"kb:{kb_id}"`로 바꾼다(D6). 후보 검색과 별칭 일치는 모두 `scope_key` 조건을 건다.
- 근거별 엣지: 같은 두 엔티티 사이에도 근거 청크마다 `RELATES` 엣지를 따로 둔다. 출처를 보존하고, 문서를 삭제할 때 `document_id`로 깔끔하게 지우기 위해서다.
- 조문 엔티티 이름: `"{document_id}::제N조(의M)"`. 다른 문서의 같은 조문 번호와 충돌하지 않게 문서 단위로 둔다. 화면에 보이는 이름은 `"{파일명} 제N조"`다.

부트스트랩(`ensure_schema()`, 기동 시 멱등 실행):

```cypher
CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;
CREATE CONSTRAINT chunk_id  IF NOT EXISTS FOR (c:Chunk)  REQUIRE c.chunk_id IS UNIQUE;
CREATE INDEX entity_norm IF NOT EXISTS FOR (e:Entity) ON (e.scope_key, e.normalized_name);
CREATE INDEX alias_norm  IF NOT EXISTS FOR (a:Alias)  ON (a.scope_key, a.normalized);
CREATE INDEX chunk_doc   IF NOT EXISTS FOR (c:Chunk)  ON (c.document_id);
CREATE VECTOR INDEX entity_name_vec IF NOT EXISTS FOR (e:Entity) ON e.name_embedding
  OPTIONS {indexConfig: {`vector.dimensions`: $dim, `vector.similarity_function`: 'cosine'}};
```

- `DIM`은 `GRAPH_ENTITY_EMBEDDING_DIMENSIONS`(기본 512)다. Aura Free 저장 용량을 아끼려고 축소 차원을 쓴다.
- 임베딩 모델이 차원 지정을 지원하지 않으면 모델 기본 차원을 쓰고, 기동 로그에 남긴다. 기동 시 인덱스 차원과 설정값이 다르면 그래프 모듈을 비활성화하고 오류 로그를 남긴다. 차원이 다른 벡터로 조용히 검색하지 않게 하려는 것이다.

### 3.3 MySQL Schema (V086~V089 — ✅ 2026-11-16 사용자 승인)

> CHARSET/COLLATE를 명시하지 않는다. COMMENT 안에 콤마를 쓰지 않는다. FK 없이 소프트 참조(V065 선례)로 둔다. 열거값은 VARCHAR로 두고 애플리케이션이 검증한다.

```sql
-- V086__create_graph_rag_setting.sql
CREATE TABLE graph_rag_setting (
    id                      VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT '고정 단일 행 식별자',
    rollout_stage           VARCHAR(16)  NOT NULL DEFAULT 'off' COMMENT '노출 단계 off 또는 admin_only 또는 general',
    extraction_enabled      TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '업로드 후 자동 추출 여부',
    jev_enabled             TINYINT(1)   NOT NULL DEFAULT 0 COMMENT 'Jev 판정 사용 여부 — 끄면 LLM 선택으로 판정',
    link_threshold          DECIMAL(4,3) NOT NULL DEFAULT 0.800 COMMENT '이 확률 이상이면 기존 엔티티에 연결',
    new_threshold           DECIMAL(4,3) NOT NULL DEFAULT 0.400 COMMENT '이 확률 미만이면 새 엔티티 생성',
    extraction_llm_model_id VARCHAR(36)  NULL COMMENT 'llm_model.id 소프트 참조 — 추출용',
    rejudge_llm_model_id    VARCHAR(36)  NULL COMMENT 'llm_model.id 소프트 참조 — 재판정용 NULL이면 추출 모델',
    concurrency             INT          NOT NULL DEFAULT 3 COMMENT '추출 동시 LLM 호출 수',
    max_llm_calls_per_doc   INT          NOT NULL DEFAULT 300 COMMENT '문서당 LLM 호출 상한 — 초과 시 partial',
    candidate_top_k         INT          NOT NULL DEFAULT 5 COMMENT '판정 후보 수 상한',
    max_hops                INT          NOT NULL DEFAULT 2 COMMENT '그래프 검색 최대 탐색 단계',
    graph_rrf_weight        DECIMAL(4,3) NOT NULL DEFAULT 0.500 COMMENT '그래프 결과 RRF 가중치',
    retrieval_timeout_ms    INT          NOT NULL DEFAULT 800 COMMENT '그래프 검색 시간 상한 밀리초',
    entity_types            JSON         NOT NULL COMMENT '허용 엔티티 타입 목록',
    relation_types          JSON         NOT NULL COMMENT '허용 관계 타입 목록',
    created_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각'
) ENGINE=InnoDB COMMENT='그래프 RAG 전역 설정 — 단일 행';

INSERT INTO graph_rag_setting (id, entity_types, relation_types) VALUES (
  'c0000000-0000-4000-8000-000000000001',
  JSON_ARRAY('상품·서비스','대상','조건·요건','규정·문서','조문','용어','조직·부서','수치기준','절차','기타'),
  JSON_ARRAY('적용대상','요건','예외','한도','정의','참조','포함','담당','기타'));

-- V087__create_graph_extraction_job.sql
CREATE TABLE graph_extraction_job (
    id                VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT '잡 식별자',
    document_id       VARCHAR(36)  NOT NULL COMMENT 'document_metadata.document_id 소프트 참조',
    kb_id             VARCHAR(36)  NULL COMMENT 'knowledge_base.id 소프트 참조',
    collection_name   VARCHAR(255) NOT NULL COMMENT '청크가 저장된 컬렉션',
    status            VARCHAR(16)  NOT NULL DEFAULT 'pending' COMMENT 'pending 또는 processing 또는 completed 또는 partial 또는 failed',
    mode              VARCHAR(16)  NOT NULL DEFAULT 'resume' COMMENT 'resume 완료 청크 건너뜀 또는 rebuild 문서 그래프 삭제 후 재추출',
    trigger_source    VARCHAR(16)  NOT NULL COMMENT 'upload 자동 또는 admin 수동',
    extractor_version VARCHAR(16)  NOT NULL COMMENT '추출기 버전 — 바뀌면 resume도 재추출',
    total_chunks      INT          NOT NULL DEFAULT 0 COMMENT '대상 청크 수',
    processed_chunks  INT          NOT NULL DEFAULT 0 COMMENT '처리 완료 청크 수',
    failed_chunks     INT          NOT NULL DEFAULT 0 COMMENT '처리 실패 청크 수',
    llm_calls         INT          NOT NULL DEFAULT 0 COMMENT '추출과 판정 LLM 호출 합계',
    judge_calls       INT          NOT NULL DEFAULT 0 COMMENT 'Jev 호출 수',
    entities_created  INT          NOT NULL DEFAULT 0 COMMENT '새로 만든 엔티티 수',
    entities_linked   INT          NOT NULL DEFAULT 0 COMMENT '기존 엔티티에 연결한 언급 수',
    relations_created INT          NOT NULL DEFAULT 0 COMMENT '저장한 관계 엣지 수',
    error_message     TEXT         NULL COMMENT '실패 사유 요약',
    requested_by      VARCHAR(36)  NULL COMMENT '요청 사용자 id 소프트 참조',
    started_at        DATETIME     NULL COMMENT '처리 시작 시각',
    finished_at       DATETIME     NULL COMMENT '처리 종료 시각',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
    INDEX idx_gej_document (document_id, created_at),
    INDEX idx_gej_status (status)
) ENGINE=InnoDB COMMENT='그래프 추출 잡 — 문서 단위 실행 이력';

-- V088__create_graph_resolution_decision.sql
CREATE TABLE graph_resolution_decision (
    id                VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT '판정 식별자 — Neo4j 엣지 decision_id와 동일',
    job_id            VARCHAR(36)  NOT NULL COMMENT 'graph_extraction_job.id 소프트 참조',
    document_id       VARCHAR(36)  NOT NULL COMMENT '근거 문서',
    chunk_id          VARCHAR(64)  NOT NULL COMMENT '근거 청크',
    mention_text      VARCHAR(255) NOT NULL COMMENT '언급 원문',
    mention_type      VARCHAR(32)  NOT NULL COMMENT '언급 타입',
    candidates        JSON         NOT NULL COMMENT '후보 목록 라벨 엔티티id 이름 유사도',
    probabilities     JSON         NULL COMMENT 'Jev 라벨별 확률',
    chosen_label      VARCHAR(16)  NOT NULL COMMENT '선택 라벨 C1부터 또는 NEW',
    entity_id         VARCHAR(36)  NOT NULL COMMENT '최종 연결 엔티티 id',
    created_new       TINYINT(1)   NOT NULL COMMENT '새 엔티티 생성 여부',
    decided_by        VARCHAR(16)  NOT NULL COMMENT 'rule 또는 jev 또는 llm_rejudge 또는 llm_fallback',
    band              VARCHAR(16)  NOT NULL COMMENT 'auto_link 또는 auto_new 또는 rejudge 또는 fallback',
    probability       DECIMAL(5,4) NULL COMMENT '판정 확률 — rule은 NULL',
    llm_confidence    VARCHAR(8)   NULL COMMENT 'LLM 판정 자기평가 high 또는 medium 또는 low',
    llm_reason        VARCHAR(500) NULL COMMENT 'LLM 판정 사유 요약',
    review_status     VARCHAR(16)  NOT NULL DEFAULT 'none' COMMENT 'none 또는 pending 또는 approved 또는 rejected',
    reviewed_by       VARCHAR(36)  NULL COMMENT '검토자 id',
    reviewed_at       DATETIME     NULL COMMENT '검토 시각',
    review_note       VARCHAR(500) NULL COMMENT '검토 메모',
    created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    INDEX idx_grd_review (review_status, created_at),
    INDEX idx_grd_document (document_id),
    INDEX idx_grd_entity (entity_id)
) ENGINE=InnoDB COMMENT='엔티티 동일성 판정 기록과 검토 큐';

-- V089__create_graph_rag_stage_change.sql
CREATE TABLE graph_rag_stage_change (
    id                   VARCHAR(36)  NOT NULL PRIMARY KEY COMMENT '변경 이력 식별자',
    from_stage           VARCHAR(16)  NOT NULL COMMENT '이전 단계',
    to_stage             VARCHAR(16)  NOT NULL COMMENT '새 단계',
    changed_by           VARCHAR(36)  NOT NULL COMMENT '변경한 관리자 id',
    eval_baseline_run_id VARCHAR(36)  NULL COMMENT '그래프 off RAGAS 실행 id 소프트 참조',
    eval_graph_run_id    VARCHAR(36)  NULL COMMENT '그래프 on RAGAS 실행 id 소프트 참조',
    force_reason         VARCHAR(500) NULL COMMENT '평가 기록 없이 강제 전환한 사유',
    created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '변경 시각',
    INDEX idx_grsc_created (created_at)
) ENGINE=InnoDB COMMENT='그래프 RAG 노출 단계 변경 이력';
```

- SQLAlchemy 모델(`infrastructure/graph_rag/models.py`)에도 `comment=`를 똑같이 반영한다.
- 작성 전에 `/db-migration`, `docs/wiki/backend/db/mysql-fk-collation.md`를 확인한다.
- 로컬 DB에는 V086~V089를 한 번만 적용한다.
- 운영 Flyway 순서는 V085 다음이다.

### 3.4 Graph ↔ MySQL 정합 규칙

- **진실 공급원**: 그래프는 파생 데이터다. 문서 재추출(`rebuild`)로 언제든 다시 만들 수 있다. 판정 기록과 잡 이력은 MySQL이 진실 공급원이다.
- **판정 기록 시점**: 판정 행을 먼저 INSERT한 뒤 Neo4j에 쓴다. Neo4j 쓰기가 실패하면 해당 청크를 실패로 세고 판정 행은 그대로 둔다. 재실행하면 같은 `decision_id`(uuid5)로 덮어쓴다.
- **결정적 ID**:
  - `decision_id = uuid5(NS, f"{chunk_id}:{normalized}:{type}")`
  - 엔티티 id = `uuid4`. 새로 만들 때만 발급한다.
  - `RELATES.id = uuid5(NS, f"{chunk_id}:{src_norm}:{type}:{tgt_norm}")`
- **resume 판단**: `(:Chunk).extractor_version`이 현재 버전과 같으면 그 청크는 건너뛴다.

---

## 4. API Specification

공통 규칙:
- 관리자 API는 전부 `Depends(require_role("admin"))`를 건다.
- 응답 스키마 위치는 `interfaces/schemas/graph_rag.py`다.
- `rollout_stage=off`일 때 허용되는 관리자 API는 설정 조회·수정, 상태(health)뿐이고, 나머지는 `409 GRAPH_STAGE_OFF`를 돌려준다.

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/graph-rag/capabilities` | `{visible, stage?}` — 빌더·채팅 UI 노출 판단 | 로그인 사용자 |
| GET | `/api/v1/admin/graph-rag/settings` | 전역 설정 조회 | admin |
| PUT | `/api/v1/admin/graph-rag/settings` | 설정 수정(단계 제외) | admin |
| POST | `/api/v1/admin/graph-rag/stage` | 노출 단계 변경 | admin |
| GET | `/api/v1/admin/graph-rag/stage-history` | 단계 변경 이력 | admin |
| GET | `/api/v1/admin/graph-rag/health` | 백엔드 연결·노드/관계 수·Aura Free 한도 대비 | admin |
| GET | `/api/v1/admin/graph-rag/kbs/{kb_id}/documents` | 문서별 최근 잡 상태·카운터 | admin |
| POST | `/api/v1/admin/graph-rag/documents/{document_id}/extract` | 추출 실행 `{mode: resume\|rebuild}` | admin |
| GET | `/api/v1/admin/graph-rag/jobs/{job_id}` | 잡 상세 | admin |
| GET | `/api/v1/admin/graph-rag/entities` | 엔티티 검색 `q, type, page, size` | admin |
| GET | `/api/v1/admin/graph-rag/entities/{entity_id}` | 별칭·관계·언급(근거 청크 미리보기) | admin |
| POST | `/api/v1/admin/graph-rag/search-test` | 그래프·하이브리드·결합 결과 비교 | admin |
| GET | `/api/v1/admin/graph-rag/review` | 검토 큐 `status=pending` | admin |
| POST | `/api/v1/admin/graph-rag/review/{decision_id}/approve` | 승인(유지) | admin |
| POST | `/api/v1/admin/graph-rag/review/{decision_id}/reject` | 거절(분리·재연결) | admin |
| GET | `/api/v1/admin/graph-rag/integrity` | 근거 청크 실재 점검(샘플 또는 KB 단위) | admin |

`wire_graph_rag`가 등록하지 않으면 위 라우터는 모두 존재하지 않는다(404). 프론트는 capabilities 404를 `visible=false`로 처리한다.

### 4.2 Detailed Specification

#### `GET /api/v1/graph-rag/capabilities`
```json
// 일반 사용자, stage=admin_only
{ "visible": false }
// admin, stage=admin_only
{ "visible": true, "stage": "admin_only" }
```
`visible = RolloutPolicy.is_visible(stage, caller_is_admin)`. 일반 사용자 응답에는 `stage`를 넣지 않는다.

#### `POST /api/v1/admin/graph-rag/stage`
```json
{ "to_stage": "general", "eval_baseline_run_id": "…", "eval_graph_run_id": "…", "force_reason": null }
```
- `StageTransitionPolicy`:
  - `general`로 바꾸려면 두 RAGAS 실행 id가 모두 존재하고 완료 상태여야 한다.
  - 그렇지 않으면 `force_reason`(10자 이상)이 있어야 한다.
  - 둘 다 없으면 `409 GRAPH_STAGE_EVAL_REQUIRED`를 돌려준다.
- `off`·`admin_only`로 바꿀 때는 조건이 없다.
- 이력 테이블 INSERT와 설정 UPDATE는 한 트랜잭션에서 처리한다. 설정 캐시는 즉시 무효화한다.
- RAGAS 실행 테이블·상태 값은 Do 단계 module-7 첫 작업에서 `docs/wiki/backend/db/erd-evaluation.md`로 확인한다.

#### `POST /api/v1/admin/graph-rag/documents/{document_id}/extract`
- Request: `{ "mode": "resume" }`
- Response `202`: `{ "job_id": "…", "status": "pending" }`
- Errors:
  - `404 DOCUMENT_NOT_FOUND`
  - `409 GRAPH_JOB_BUSY`: 같은 문서에 pending/processing 잡이 있음
  - `422 GRAPH_EXTRACTION_MODEL_MISSING`: 추출 모델 미설정
  - `503 GRAPH_BACKEND_UNAVAILABLE`

#### `POST /api/v1/admin/graph-rag/search-test`
```json
// Request
{ "query": "A상품 대상 고객의 예외 규정", "kb_id": "…", "top_k": 5, "max_hops": 2 }
// Response 200
{
  "linked_entities": [{ "id":"…","name":"A상품","type":"상품·서비스","via":"exact|alias|vector","score":1.0 }],
  "paths": [{ "chunk_id":"…","hops":2,"path":["A상품","적용대상→","개인사업자","예외→","특례 조항"] }],
  "graph_hits":  [{ "chunk_id":"…","document_id":"…","filename":"…","score":0.83,"content_preview":"…" }],
  "hybrid_hits": [ … ],
  "fused_hits":  [{ …, "fusion_source":"both+graph" }],
  "timings_ms": { "link": 40, "traverse": 120, "fetch": 60, "hybrid": 310 },
  "filtered_out": 3
}
```
- 관리자 본인의 권한으로 필터를 적용한다. 일반 사용자 권한을 흉내 내는 기능은 없다.
- 노출 단계 검사는 하지 않는다. 테스트 API이므로 `admin_only`와 `general`에서 동작한다.

#### `POST /api/v1/admin/graph-rag/review/{decision_id}/reject`
```json
{ "target_entity_id": "…" | null, "note": "카드 한도와 다른 개념" }
```
- **원래 판정이 기존 엔티티에 연결(link)한 경우**: `target_entity_id`가 null이면 이 `decision_id`가 붙은 엣지(`MENTIONED_IN`, `RELATES`의 source·target)를 새 엔티티로 옮겨 분리한다.
- **원래 판정이 새 엔티티를 만든(new) 경우**: `target_entity_id`가 필수다. 해당 엣지를 대상 엔티티로 옮긴 뒤, 남은 엣지가 없는 엔티티를 지운다.
- 이미 처리된 건이면 `409 GRAPH_REVIEW_ALREADY_DONE`, 판정 타입과 대상 엔티티 타입이 다르면 `422 GRAPH_TYPE_MISMATCH`를 돌려준다.

---

## 5. UI/UX Design

### 5.1 Screen Layout — `/admin/graph-rag` (AdminLayout, `docs-quality` 그룹)

```
┌ 그래프 RAG (테스트) ─────────────── [단계: admin_only ▾] [Neo4j ● 연결됨 · 노드 12,340/200,000] ┐
│ [설정] [추출] [엔티티·관계] [검색 테스트] [검토 큐 (7)]                                         │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ (탭 본문)                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

| 탭 | 내용 |
|----|------|
| 설정 | 추출 on/off, **Jev 판정 on/off**, 연결·신규 기준값(슬라이더 + 숫자, new<link 검증), 추출·재판정 모델(llm_model 선택), 동시 실행 수, 문서당 호출 상한, 후보 수, 최대 단계, RRF 가중치, 시간 상한, 엔티티·관계 타입 칩 편집('기타'는 삭제 불가) |
| 추출 | KB 선택 → 문서 표(파일명, 최근 잡 상태 배지, 처리/전체 청크, 엔티티·관계 수, LLM 호출 수, 시각) + [이어서 실행] [다시 만들기]. 진행 중이면 5초 폴링 |
| 엔티티·관계 | 검색창 + 타입 필터 → 표(이름, 타입, 별칭 수, 관계 수, 언급 수) → 행을 펼치면 별칭·관계(유형·상대·근거 문서)·언급 근거 청크 원문 미리보기 |
| 검색 테스트 | 질문·KB·top_k·최대 단계 입력 → 연결된 엔티티 칩 → 경로 목록 → 3열 비교(그래프 / 하이브리드 / 결합), 각 카드에 fusion_source 배지·점수, 권한 필터로 제외된 수, 단계별 시간 |
| 검토 큐 | 표(언급, 문서, 판정자, 확률, 선택 엔티티, 후보) → [승인] [거절] (거절 시 분리 또는 대상 엔티티 검색 선택 + 메모) |

단계 변경: 헤더 드롭다운을 바꾸면 확인 창이 뜬다. `general`로 바꿀 때는 RAGAS 실행 두 건을 선택하는 칸이 나온다. 선택하지 않으면 사유 입력 칸이 필수가 되고, 버튼 문구가 "강제 전환"으로 바뀐다.

### 5.2 User Flow

```
관리자: 설정(추출 on·모델·단계 admin_only) → 추출 탭에서 KB 문서 [다시 만들기]
      → 엔티티 탭에서 별칭·관계 확인 → 검색 테스트로 하이브리드와 비교
      → 검토 큐 처리 → 빌더에서 테스트 에이전트에 "그래프 검색(테스트)" 켬 → 채팅으로 확인
일반 사용자: 아무것도 보이지 않음 (빌더 토글·근거 칩 배지 없음)
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| AdminGraphRagPage | `idt_front/src/pages/AdminGraphRagPage/index.tsx` | 탭 컨테이너, 헤더(단계·health) |
| GraphRagSettingsTab | `…/GraphRagSettingsTab.tsx` | 설정 폼 |
| GraphRagExtractionTab | `…/GraphRagExtractionTab.tsx` | KB 문서·잡 |
| GraphRagEntitiesTab | `…/GraphRagEntitiesTab.tsx` | 엔티티 표·상세 |
| GraphRagSearchTestTab | `…/GraphRagSearchTestTab.tsx` | 비교 3열 |
| GraphRagReviewTab | `…/GraphRagReviewTab.tsx` | 검토 큐 |
| StageChangeDialog | `…/StageChangeDialog.tsx` | 단계 변경 + 평가 근거 |
| RagConfigPanel (수정) | `components/agent-builder/RagConfigPanel.tsx` | `capabilities.visible`일 때만 "그래프 검색(테스트)" 토글 |
| types / service / hooks | `types/graphRag.ts`, `services/graphRagService.ts`, `hooks/useGraphRag*.ts` | 계약·쿼리 |

런타임 상수(탭 키, 단계 라벨)는 `src/types/graphRag.ts`에 `as const`로 둔다. 컴포넌트 파일에서 export하지 않는다(프론트 규칙).

### 5.4 Page UI Checklist

#### AdminGraphRagPage
- [ ] 헤더: 현재 단계 배지 + 단계 드롭다운
- [ ] 헤더: Neo4j 연결 상태(연결됨/정지/미설정) + 노드·관계 수 / 한도
- [ ] 탭 5개, 검토 큐 탭에 pending 건수 배지
- [ ] `stage=off`일 때 설정 탭 외 탭은 비활성 + 안내 문구
- [ ] Neo4j 미연결 시 추출·검색 버튼 비활성 + 사유 표시

#### 설정 탭
- [ ] 추출 on/off, Jev on/off 토글
- [ ] link/new 기준값 입력, new ≥ link면 저장 버튼 비활성 + 오류 문구
- [ ] 추출·재판정 모델 선택(llm_model 목록)
- [ ] 동시 실행 수, 문서당 호출 상한, 후보 수, 최대 단계, RRF 가중치, 시간 상한 숫자 입력(범위 검증)
- [ ] 엔티티·관계 타입 칩 추가/삭제, '기타' 삭제 불가

#### 추출 탭
- [ ] KB 선택 드롭다운
- [ ] 문서 행: 파일명, 상태 배지(pending/processing/completed/partial/failed), 처리/전체, 엔티티·관계 수, LLM·Jev 호출 수, 최근 시각
- [ ] [이어서 실행] [다시 만들기] 버튼, busy면 비활성
- [ ] 실패 행 오류 메시지 툴팁
- [ ] processing 잡이 있으면 5초 폴링, 없으면 중지

#### 엔티티·관계 탭
- [ ] 검색 입력 + 타입 필터 + 페이지네이션
- [ ] 행 펼침: 별칭 목록, 관계 목록(유형·방향·상대·근거 파일명), 언급 근거 청크 미리보기(200자)

#### 검색 테스트 탭
- [ ] 질문·KB·top_k·최대 단계 입력
- [ ] 연결 엔티티 칩(via 표시)
- [ ] 경로 목록(hops 표시)
- [ ] 3열 결과(그래프/하이브리드/결합), fusion_source 배지, 점수, 파일명, 미리보기
- [ ] 권한 필터 제외 수, 단계별 소요 시간

#### 검토 큐 탭
- [ ] 행: 언급, 근거 미리보기, 판정자, 확률/LLM 확신도, 선택 엔티티, 후보 목록
- [ ] [승인] [거절] → 거절 시 분리/대상 엔티티 검색 선택 + 메모
- [ ] 처리 후 목록·배지 즉시 갱신

#### RagConfigPanel (빌더)
- [ ] `capabilities.visible=false`이면 토글 DOM이 렌더되지 않음
- [ ] `visible=true`이면 "그래프 검색(테스트)" 토글 + "관리자 테스트 중인 기능" 보조 문구

---

## 6. Error Handling

### 6.1 Error Code Definition

| Code | HTTP | Cause | Handling |
|------|------|-------|----------|
| GRAPH_STAGE_OFF | 409 | stage=off에서 추출·검색·검토 API 호출 | 화면 비활성 안내 |
| GRAPH_BACKEND_UNAVAILABLE | 503 | Neo4j 미설정·연결 실패·Aura 정지 | 헤더 상태 표시, 재시도 안내 |
| GRAPH_JOB_BUSY | 409 | 같은 문서 잡 진행 중 | 버튼 비활성 |
| GRAPH_EXTRACTION_MODEL_MISSING | 422 | 추출 모델 미설정 | 설정 탭 이동 안내 |
| GRAPH_SETTINGS_INVALID | 422 | VO 검증 실패 | 필드 오류 표시 |
| GRAPH_STAGE_EVAL_REQUIRED | 409 | general 전환에 평가 근거·사유 없음 | 다이얼로그 필수 입력 |
| GRAPH_REVIEW_ALREADY_DONE | 409 | 이미 처리된 판정 | 목록 갱신 |
| GRAPH_TYPE_MISMATCH | 422 | 거절 재연결 대상 타입 불일치 | 대상 재선택 |
| GRAPH_EMBEDDING_DIM_MISMATCH | (기동 로그) | 인덱스 차원 ≠ 설정 | 모듈 비활성, 운영 조치 |

### 6.2 경로별 실패 처리 (답변 경로는 절대 깨지지 않음)

| 지점 | 실패 | 처리 |
|------|------|------|
| `post_ingest` 훅 | 예외 | 코어가 감싸서 `logger.error(..., exc_info=True)`만 남김. 업로드 응답 불변 |
| 추출 잡 청크 | LLM·Neo4j 오류 | 해당 청크 failed_chunks+1, 계속 진행. 전부 실패면 failed |
| 추출 잡 | 호출 상한 도달 | 남은 청크 중단, status=partial |
| 기동 시 | processing 잡 잔존(재기동으로 중단) | lifespan에서 failed(`interrupted`)로 전환. 관리자가 resume |
| `deletion` 훅 | 예외 | 로그만. 문서 삭제 성공 유지. 정합성 점검 API가 고아 탐지 |
| `supplemental.retrieve` | 예외·타임아웃 | `[]` 반환(도구 쪽 `asyncio.wait_for` + try). 원래 hits로 응답, 로그에 사유 |
| Jev | `JudgmentError` 3종 | 해당 언급만 LLM 대체(llm_fallback), 잡 내 연속 5회 실패하면 잡 남은 구간은 Jev 생략 |
| LLM 재판정/대체 | 파싱 실패 | NEW로 처리 + review=pending (잘못 합치는 것보다 쪼개지는 쪽을 택함) |

에러 응답 형식은 기존 라우터 관례 `{"detail": {"code": "...", "message": "..."}}`를 따른다. 정확한 형식은 `admin_multimodal_router.py`를 기준으로 Do 단계에서 맞춘다.

---

## 7. Security Considerations

- [ ] **3중 AND 게이트**(Plan FR-20). `grant`는 대화 라우트에서만 만든다.
  - `ws_router.py:284` stream
  - `agent_builder_router.py:303` execute
  - `agent_builder_router.py:354` stream
  - 생성 코드는 `SupplementalGrant(caller_is_admin=user.role == UserRole.ADMIN)`이다.
- [ ] **비대화 경로에는 grant가 없음**. 다음 경로를 소스 계약 테스트로 고정한다(W2·W3 패턴).
  - `invoke_webhook_agent_use_case.py:86`
  - `background_job/worker.py:295`
  - `trigger_due_schedules_use_case.py:145`
  - `main.py:_run_agent_headless`(RAGAS 기본 경로)
  - `resume_from_snapshot`(execute/stream을 거치지 않음)
- [ ] **청크 단위 권한**. 그래프 탐색은 전역이지만, 결과 청크는 ES에서 도구와 같은 필터로 다시 조회한다.
  - hard 필터, lenient `visibility`, 부서 필터를 쓴다.
  - 범위는 `collection_name`과 도구의 kb 필터로 제한한다.
  - 따라서 권한 없는 청크와 에이전트 범위 밖 청크는 반환되지 않는다(SC-7).
- [ ] **엔티티 이름·경로 비노출**. 이름과 경로는 관리자 API에서만 보인다. 에이전트 도구 결과에는 청크 본문과 기존 메타데이터만 들어간다. LLM 컨텍스트에 그래프 경로를 넣지 않는다.
- [ ] **저장 시 정리**. 에이전트 저장 경로에서 `exposure.is_visible("graph_rag", is_admin)`이 False이면 `use_graph`를 조용히 False로 바꾸고 info 로그를 남긴다. 모듈이 등록되지 않았을 때도 False다.
  - 대상 저장 경로: 빌더 생성·수정, 위저드, 자동 빌더.
  - 정확한 유스케이스 목록은 module-1 첫 작업에서 grep으로 확정한다.
- [ ] **비밀값**. `NEO4J_PASSWORD`는 `idt/.env`에만 둔다. `.env.example`에는 자리표시만 넣는다. 로그에 URI 인증 정보를 남기지 않는다.
- [ ] **Aura 데이터 범위**. PoC KB에는 고객 개인정보가 없는 규정 문서만 넣는다. 관리자 페이지 헤더에 "외부 클라우드 저장(Aura)" 표시를 둔다. 표시 여부는 URI scheme(`neo4j+s://*.databases.neo4j.io`)으로 판정한다.
- [ ] **Cypher 주입 방지**. 모든 쿼리는 파라미터 바인딩으로 쓴다. 라벨·관계 타입은 코드 상수로만 쓰고, 관계 `type`은 속성 값으로 저장한다.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit | 도메인 정책(RolloutPolicy, StageTransitionPolicy, ResolutionPolicy, EvidencePolicy, NameNormalizer, GraphRagSettings 검증, merge_many) | pytest | Do |
| Unit | EntityResolver(Jev 페이크·LLM 페이크·오류 대체), RuleExtractor, LlmExtractor(구조화 출력 페이크) | pytest | Do |
| Unit | Tool 결합(그래프 소스 페이크, 게이트 8조합, 타임아웃) | pytest | Do |
| Contract | 코어→graph_rag import 0 (AST), 비대화 호출자 grant 없음(소스), JudgmentPort `_DECLARED_CONSUMERS` | pytest | Do |
| Integration | Neo4jGraphStore (`-m neo4j`, `NEO4J_URI` 없으면 skip; 로컬 컨테이너·Aura 양쪽) | pytest | Do/Check |
| Integration | MySQL 저장소 4종, 마이그레이션 COMMENT 검사 | pytest | Do |
| L1 API | 관리자·capabilities 라우터 | TestClient / curl | Check |
| L2 UI | 관리자 페이지·빌더 토글 | Vitest + RTL + MSW | Do |
| L3 E2E | 업로드→추출→검색 비교→검토→에이전트 채팅 | 수동 + Chrome MCP | Check |
| Eval | 별칭 라벨셋 정밀도(SC-3), RAGAS on/off(SC-4) | 스크립트 + RAGAS | Check |

### 8.2 L1: API Test Scenarios

| # | Endpoint | Method | Description | Expected |
|---|----------|--------|-------------|----------|
| 1 | /admin/graph-rag/settings | GET | 일반 사용자 토큰 | 403 |
| 2 | /admin/graph-rag/settings | PUT | new_threshold ≥ link_threshold | 422 GRAPH_SETTINGS_INVALID |
| 3 | /admin/graph-rag/stage | POST | general, 평가 id·사유 없음 | 409 GRAPH_STAGE_EVAL_REQUIRED |
| 4 | /admin/graph-rag/stage | POST | general, force_reason 있음 | 200 + 이력 1행 |
| 5 | /graph-rag/capabilities | GET | 일반 사용자, admin_only | `{visible:false}`, stage 키 없음 |
| 6 | /graph-rag/capabilities | GET | admin, admin_only | `{visible:true, stage}` |
| 7 | /admin/graph-rag/documents/{id}/extract | POST | 진행 중 잡 있음 | 409 GRAPH_JOB_BUSY |
| 8 | /admin/graph-rag/documents/{id}/extract | POST | stage=off | 409 GRAPH_STAGE_OFF |
| 9 | /admin/graph-rag/search-test | POST | Neo4j 중지 | 503 GRAPH_BACKEND_UNAVAILABLE |
| 10 | /admin/graph-rag/review/{id}/reject | POST | 이미 approved | 409 |
| 11 | (모듈 미등록) 모든 graph-rag 경로 | ANY | wire 줄 제거 | 404 |

### 8.3 L2: UI Action Test Scenarios

| # | Page | Action | Expected Result |
|---|------|--------|----------------|
| 1 | AdminGraphRagPage | 진입 | 헤더 단계·health 표시, 탭 5개 |
| 2 | 설정 | new ≥ link 입력 | 저장 비활성 + 오류 문구 |
| 3 | 설정 | Jev 토글 후 저장 | PUT 호출, 토스트 |
| 4 | 추출 | [다시 만들기] | POST mode=rebuild, 행 상태 pending→폴링 |
| 5 | 검색 테스트 | 질문 실행 | 3열 렌더, fusion_source 배지 |
| 6 | 검토 큐 | 거절→대상 선택→확인 | POST reject, 배지 감소 |
| 7 | StageChangeDialog | general 선택·평가 미선택 | 사유 필수, 버튼 "강제 전환" |
| 8 | RagConfigPanel | capabilities visible=false | 토글 DOM 없음 |
| 9 | RagConfigPanel | capabilities 404 | 토글 DOM 없음 |

### 8.4 L3: E2E Scenario Test Scenarios

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | 관리자 폐루프 | 설정→추출→엔티티 확인→검색 비교→검토 | DB/Swagger 0회 (SC-5) |
| 2 | 관리자 에이전트 | 빌더 토글 on → 관리자 채팅 | 근거 칩 정상, 기록 fusion_source에 graph 포함 |
| 3 | 일반 사용자 차단 | 같은 에이전트를 일반 사용자가 채팅 | 그래프 실행 0, 로그 사유 `grant_not_admin` (SC-8) |
| 4 | 웹훅 차단 | 같은 에이전트 웹훅 호출 | 그래프 실행 0 (SC-8) |
| 5 | 장애 격리 | Neo4j(Aura) 정지 상태로 업로드·채팅 | 둘 다 성공 (SC-6) |
| 6 | 모듈 제거 | `wire_graph_rag` 주석 → 기동·전체 테스트 | 통과 (SC-9) |
| 7 | 문서 삭제 | 추출된 문서 삭제 → integrity | 고아 근거 0 (SC-2) |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:------------:|---------------------|
| 테스트 KB | 1 | 규정 문서 2~3개(서로 조문·용어를 참조), 고객 정보 없음 |
| 사용자 | 2 | admin 1, 일반 user 1(같은 부서) |
| 별칭 라벨셋 | 30쌍 | `{mention_a, mention_b, same: bool}` — `idt/tests/fixtures/graph_rag/alias_pairs.json` |
| 다문서 질문셋 | 10문항 | RAGAS testset에 `tag=multi_doc` |
| llm_model | 1 | 추출 모델(structured output 지원) |

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| Interfaces | 라우터, 요청/응답 스키마 | `src/api/routes/admin_graph_rag_router.py`, `graph_rag_router.py`, `src/interfaces/schemas/graph_rag.py` |
| Application | 추출 잡, 판정, 검색 소스, 관리 유스케이스 | `src/application/graph_rag/` |
| Domain | 확장 훅 포트(코어), 그래프 VO·정책·포트 | `src/domain/extension_hooks/`, `src/domain/graph_rag/` |
| Infrastructure | Neo4j, LLM 추출기·판정기, Jev 어댑터 연결, MySQL 저장소 | `src/infrastructure/graph_rag/` |
| Composition | 모듈 조립 | `src/api/graph_rag_di.py` (`wire_graph_rag`) |

### 9.2 Dependency Rules

```
코어(application/*, domain/* 의 기존 모듈) ──▶ domain/extension_hooks   (허용)
코어 ──▶ domain/graph_rag | application/graph_rag | infrastructure/graph_rag   (금지, AST 테스트)
application/graph_rag ──▶ domain/graph_rag, domain/extension_hooks, domain/judgment, domain/morph, domain/vector
infrastructure/graph_rag ──▶ domain/graph_rag (구현), neo4j driver (여기만)
api/graph_rag_di.py ──▶ 전부 (조립 지점)
```

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| ExtensionHooks, 포트 4종, 이벤트·Grant·Query VO | Domain(코어) | `domain/extension_hooks/{ports,events,registry}.py` |
| `RRFFusionPolicy.merge_many` | Domain(코어, 기존 파일) | `domain/hybrid_search/policies.py` |
| GraphRagSettings, enums, Mention 등 VO | Domain | `domain/graph_rag/value_objects.py` |
| RolloutPolicy, StageTransitionPolicy, ResolutionPolicy, EvidencePolicy, NameNormalizer | Domain | `domain/graph_rag/policies.py` |
| GraphStorePort, ExtractorPort, EntityChooserPort, 저장소 포트 | Domain | `domain/graph_rag/interfaces.py` |
| GraphIngestHook, GraphExtractionLauncher, ExtractGraphUseCase | Application | `application/graph_rag/extraction/` |
| EntityResolver | Application | `application/graph_rag/resolution/resolver.py` |
| GraphRetrievalSource, EntityLinker | Application | `application/graph_rag/retrieval/` |
| GraphDeletionHook, GraphExposure | Application | `application/graph_rag/hooks.py` |
| Settings/Stage/Entities/Review/SearchTest/Integrity 유스케이스 | Application | `application/graph_rag/admin/` |
| Neo4jGraphStore, schema bootstrap | Infrastructure | `infrastructure/graph_rag/neo4j/` |
| RuleExtractor, LlmExtractor | Infrastructure | `infrastructure/graph_rag/extract/` |
| JevEntityChooser(JudgmentPort 사용), LlmEntityChooser | Infrastructure | `infrastructure/graph_rag/resolution/` |
| ES 청크 리더 | Infrastructure | `infrastructure/graph_rag/es_chunk_reader.py` |
| MySQL 모델·저장소 4종 | Infrastructure | `infrastructure/graph_rag/{models,repositories}.py` |

---

## 10. Coding Convention Reference

### 10.1 이 기능의 규칙

| Item | Convention Applied |
|------|-------------------|
| 함수 길이 | 40줄 이하. Cypher 문자열은 모듈 상수로 분리 |
| if 중첩 | 2단계 이하. 판정 분기는 `ResolutionPolicy.classify()`가 enum을 반환 → 매핑 테이블로 처리 |
| 로깅 | LOG-001 — 잡(job_id·document_id), 판정(decision_id), 검색(request_id·skip_reason) 구조화 로그, `exc_info=True` |
| 세션 | 잡 실행 중 청크마다 짧은 세션(SessionScoped 저장소, section_summary 선례). LLM·Neo4j 호출은 트랜잭션 밖에서. Repository 내부 commit 금지 |
| 싱글턴 | Neo4j `AsyncDriver`는 앱 수명 싱글턴, lifespan 종료 시 `close()` |
| 포맷 | `ruff format`은 새 파일에만. `main.py`는 Edit로 최소 줄 수정 |
| 설정 캐시 | `GraphSettingsReader` TTL 30초. PUT·stage 변경 시 즉시 무효화 |
| Design 주석 | 모듈 첫 줄 `"""Design Ref: graph-rag-foundation §x — ..."""`, 핵심 분기 `# Plan SC-n` |

### 10.2 Environment Variables

| Variable | Purpose | Default | Scope |
|----------|---------|---------|-------|
| `GRAPH_BACKEND` | `off` \| `neo4j` | `off` | Server |
| `NEO4J_URI` | `bolt://localhost:7687` 또는 Aura `neo4j+s://xxxx.databases.neo4j.io` | (없음) | Server |
| `NEO4J_USER` | 사용자 | `neo4j` | Server |
| `NEO4J_PASSWORD` | 비밀번호(`.env`만) | (없음) | Server |
| `NEO4J_DATABASE` | DB 이름(Aura Free는 단일) | `neo4j` | Server |
| `NEO4J_MAX_POOL_SIZE` | 드라이버 풀 | `10` | Server |
| `NEO4J_CONNECT_TIMEOUT_S` | 연결 시간 상한 | `5` | Server |
| `GRAPH_ENTITY_EMBEDDING_MODEL` | 엔티티 이름 임베딩 모델 | `settings.openai_embedding_model` | Server |
| `GRAPH_ENTITY_EMBEDDING_DIMENSIONS` | 벡터 인덱스 차원 | `512` | Server |
| `GRAPH_AURA_FREE_NODE_LIMIT` / `_REL_LIMIT` | health 표시용 한도 | `200000` / `400000` | Server |

`.env.example`에 블록으로 추가한다. 기존처럼 Bash append로 넣는다(bkit hook이 `.env*` Write를 막는다).

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── db/migration/V086…V089__*.sql
├── src/domain/extension_hooks/{__init__,ports,events,registry}.py        # 코어
├── src/domain/hybrid_search/policies.py                                  # merge_many 추가
├── src/domain/agent_builder/rag_tool_config.py                           # use_graph: bool=False
├── src/domain/graph_rag/{value_objects,policies,interfaces,exceptions}.py
├── src/application/graph_rag/
│   ├── hooks.py                         # GraphIngestHook, GraphDeletionHook, GraphExposure
│   ├── extraction/{launcher,use_case}.py
│   ├── resolution/resolver.py
│   ├── retrieval/{source,linker}.py
│   └── admin/{settings,stage,entities,review,search_test,integrity,jobs}_use_case.py
├── src/infrastructure/graph_rag/
│   ├── neo4j/{driver,store,schema,cypher}.py
│   ├── extract/{rule_extractor,llm_extractor,prompts}.py
│   ├── resolution/{jev_chooser,llm_chooser}.py
│   ├── es_chunk_reader.py
│   ├── models.py · repositories.py · settings_reader.py
├── src/interfaces/schemas/graph_rag.py
├── src/api/routes/{admin_graph_rag_router,graph_rag_router}.py
├── src/api/graph_rag_di.py              # wire_graph_rag(app, *, hooks, deps…)
└── tests/… (domain/graph_rag, application/graph_rag, infrastructure/graph_rag[-m neo4j],
             api/test_graph_rag_*, contracts/test_graph_rag_boundaries.py, test_supplemental_grant_callers.py)

수정(코어): main.py(ExtensionHooks 생성·주입·wire 한 줄·lifespan close),
  knowledge_base/upload_use_case.py, doc_browse/delete_document_use_case.py, knowledge_base/use_case.py(KB 삭제),
  rag_agent/tools.py, infrastructure/agent_builder/tool_factory.py, agent_builder/workflow_compiler.py,
  agent_builder/run_agent_use_case.py, ws_router.py, agent_builder_router.py, 에이전트 저장 유스케이스(정리),
  infrastructure/judgment 경계 테스트 _DECLARED_CONSUMERS, config.py, pyproject.toml(extra graph), .env.example

idt_front/src/
├── pages/AdminGraphRagPage/{index,GraphRagSettingsTab,GraphRagExtractionTab,GraphRagEntitiesTab,
│                            GraphRagSearchTestTab,GraphRagReviewTab,StageChangeDialog}.tsx
├── types/graphRag.ts · services/graphRagService.ts · hooks/useGraphRag{Settings,Capabilities,Jobs,Entities,Review,SearchTest}.ts
├── constants/api.ts · constants/adminNav.ts('docs-quality') · App.tsx(라우트)
├── types/agentBuilder(RagToolConfig).ts  use_graph?: boolean
└── components/agent-builder/RagConfigPanel.tsx (조건부 토글)
```

### 11.2 Implementation Order

1. [ ] **코어 확장 지점**(그래프 코드 0줄)
   - ExtensionHooks, `merge_many`, `use_graph`
   - grant 키워드 체인, 도구 결합(페이크 소스)
   - 저장 시 정리
   - 계약 테스트
2. [ ] **설정·단계·저장소 기반**
   - V086·V089, 설정·단계 유스케이스
   - Neo4j 드라이버·스키마 부트스트랩, health·capabilities
   - `wire_graph_rag` 골격, `GraphExposure`
3. [ ] **추출 잡**
   - V087, ES 청크 리더, Rule·LLM 추출기, 근거 검증
   - 런처·훅, 기동 시 interrupted 처리
   - 판정은 임시로 "정확 일치 또는 새로 생성"만
4. [ ] **판정과 검토**
   - V088, 후보 검색(정규화·별칭·벡터)
   - Jev 선택기, LLM 재판정·대체
   - 검토 승인·거절(분리·재연결)
5. [ ] **그래프 검색과 삭제 정합**
   - GraphRetrievalSource(링커·탐색·ES 권한 재조회)
   - 삭제 훅, integrity, search-test
6. [ ] **프론트**: 관리자 페이지 5탭, 빌더 토글, MSW 테스트
7. [ ] **평가·전환 게이트**
   - RAGAS on/off 비교 실행(관리자 요청 시에만 grant)
   - StageTransitionPolicy 실평가 연결
   - 별칭 라벨셋 측정, Aura 실연결 스모크

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 코어 확장 지점 | `module-1` | M0 — 훅 레지스트리·grant 체인·merge_many·도구 결합·저장 정리·계약 테스트 (그래프 코드 없음) | 35-45 |
| 설정·단계·Neo4j 기반 | `module-2` | M1+M2 — V086·V089, 설정/단계/health/capabilities API, Neo4j 드라이버·스키마, wire 골격 | 35-45 |
| 추출 잡 | `module-3` | M3 — V087, ES 청크 리더, 규칙·LLM 추출, 런처·훅, interrupted | 35-45 |
| 판정·검토 | `module-4` | M4+M5 — V088, 후보·Jev·LLM 재판정/대체, 검토 API | 35-45 |
| 그래프 검색·삭제 | `module-5` | M6+M7 — 검색 소스, 권한 재조회, 삭제 훅, integrity, search-test | 30-40 |
| 관리자 UI·빌더 토글 | `module-6` | M8 + M6-b 프론트 — 5탭·다이얼로그·토글·MSW | 35-45 |
| 평가·전환 | `module-7` | M9 — RAGAS 비교, 단계 전환 게이트 실연결, 라벨셋 측정, Aura 스모크 | 20-30 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1` | 35-45 |
| Session 3 | Do | `--scope module-2` | 35-45 |
| Session 4 | Do | `--scope module-3` | 35-45 |
| Session 5 | Do | `--scope module-4` | 35-45 |
| Session 6 | Do | `--scope module-5` | 30-40 |
| Session 7 | Do | `--scope module-6` | 35-45 |
| Session 8 | Do + Check | `--scope module-7` + `/pdca analyze` | 40-50 |

각 module이 끝날 때마다 master 대비 회귀(FAILED diff)를 확인한다. module-1은 그래프 코드 없이 머지할 수 있어서, 먼저 PR로 내면 코어 회귀 위험을 분리할 수 있다.

### 11.4 Do 단계 첫 작업으로 확인할 사실 (설계 가정)

| # | 가정 | 확인 방법 | 틀릴 때 |
|---|------|-----------|---------|
| V1 | parent_child 청킹의 parent 청크가 ES에 `chunk_type=parent`로 저장되고 hybrid hit의 `id`로 쓰인다 | ES 매핑·업로드 코드 확인 (module-3) | child 청크 단위로 추출. 근거 칩은 hit chunk_id 기준 |
| V2 | `KnowledgeBaseUploadUseCase`가 모든 KB 업로드의 단일 경로다(위저드·빠른 KB 구성 포함) | 호출자 grep (module-1) | 다른 경로에도 같은 훅 호출 추가 |
| V3 | 에이전트 저장 유스케이스 목록 | grep `RagToolConfig`·`tool_config` 저장 (module-1) | 목록에 맞춰 정리 지점 추가 |
| V4 | Aura에서 `CREATE VECTOR INDEX`·`db.index.vector.queryNodes` 동작 | Aura Free 스모크 (module-2) | Qdrant `graph_entities` 컬렉션으로 대체(포트 뒤, D9 재결정) |
| V5 | 임베딩 모델이 `dimensions` 지정을 지원 | EmbeddingFactory·OpenAIEmbedding 확인 (module-2) | 기본 차원 사용, Aura 용량 재계산 |
| V6 | routed 검색 결과도 `_format_results` 전에 hit 목록으로 합칠 수 있다 | `tools.py:227·367` 확인 (module-1) | routed 경로는 기록 함수에 합류 지점 별도 추가 |
| V7 | RAGAS 실행 테이블·완료 상태 값 | erd-evaluation 위키 (module-7) | StageTransitionPolicy 검증 쿼리 조정 |

### 11.5 module-1 구현 중 결정 (2026-11-17)

| # | Design 원안 | 구현 | 이유 |
|---|------------|------|------|
| M1-1 | `DocumentDeletionHook.on_kb_deleted` | **제외** | KB 삭제는 soft delete이고 벡터도 정리 시점까지 남는다(`knowledge_base/use_case.py` delete). 그래프는 결과 청크를 ES에서 다시 조회하므로 기존 검색과 같은 기준을 따른다 |
| M1-2 | 세 검색 경로 모두 결합 (V6 가정) | **단일·멀티쿼리만 결합, 라우팅 결과는 그대로** (`skip_reason=routed_path`) | V6 확인 결과 라우팅은 `RoutedChunk`라는 다른 타입과 별도의 기록 방식을 쓴다. 사용자 결정(2026-11-17). 라우팅이 강등되면 기존 경로로 내려가 결합이 적용된다 |
| M1-3 | 저장 정리 대상: 생성·수정·위저드·자동 빌더 | **create·update·fork** 3곳 | V3 확인 결과 사용자가 `tool_config`를 직접 넣는 경로는 이 3곳이다. 시스템이 만드는 경로는 실행 시점 3중 AND가 막는다 |
| M1-4 | fork의 역할 판정 | **항상 일반 사용자 기준** | fork 경로에는 역할 정보가 없다. 관리자가 fork해도 `use_graph`가 꺼진다(테스트 단계에서는 감수) |
| M1-5 | `retrieve()`가 `list[HybridSearchResult]` 반환 | `SupplementalResult{label, hits, weight, skip_reason}` | 가중치(설정값)와 미실행 사유를 예외 없이 전달하기 위해 |
| M1-6 | 컴파일러가 grant를 항상 전달 | grant가 있을 때만 `**{"supplemental_grant": …}`로 펼쳐서 전달 | 기존 fake ToolFactory 테스트와 호환된다(`pii_scope`와 같은 방식). 계약 테스트 C4가 이 문자열을 고정한다 |
| M1-7 | 타임아웃 위치 | 소스가 설정값으로 먼저 끊고, 도구는 하드 상한 `_SUPPLEMENTAL_HARD_TIMEOUT_S=6.0`초로 한 번 더 끊음 | 소스가 상한을 지키지 못해도 답변 경로가 막히지 않게 하는 마지막 방어선 |

### 11.6 module-2 구현 중 결정 (2026-11-17)

| # | Design 원안 | 구현 | 이유 |
|---|------------|------|------|
| M2-1 | V086 설정 / V087 추출 잡 / V088 판정 / V089 단계 이력 | **V086 설정 / V087 단계 이력 / V088 추출 잡(module-3) / V089 판정(module-4)** | Flyway 기본값 `outOfOrder=false`에서는 module-2가 V089를 먼저 적용하면 나중의 V087·V088이 무시되거나 검증에 실패한다. 승인된 DDL 내용은 그대로 두고 번호만 만드는 순서로 맞췄다 |
| M2-2 | `main.py` 호출 1줄 | `wire_graph_rag` 1줄 + lifespan `start_graph_rag`·`close_graph_rag` 2줄 | 스키마 생성(비동기)과 드라이버 정리는 lifespan이 필요하다. 셋 다 wire하지 않으면 아무 일도 하지 않는다 |
| M2-3 | general 전환 근거 검증 | `UnverifiedEvalEvidence`(항상 근거 불인정) 자리표시. 실검증은 module-7 | RAGAS 테이블 확인(V7) 전에는 강제 사유 경로로만 전환할 수 있다(닫힘) |
| M2-4 | `neo4j>=5.20` | 설치 결과 6.4.1. `pyproject` extra `graph` + pytest 마커 `neo4j`(기본 제외) | 실연결 테스트는 `NEO4J_URI`가 있을 때 `-m neo4j`로만 돈다 |
| M2-5 | 기동 시 연결 실패 처리 | 차원 불일치면 모듈 비활성(store=None), 연결 실패(Aura 정지 등)면 경고만 남기고 store 유지 | Aura Free 자동 정지는 일시적이라 재기동 없이 회복해야 한다 |
| M2-6 | 백엔드 off일 때 노출 판단 | off여도 `GraphExposure`를 등록해 단계(stage)대로 노출 | 관리자 화면에서 백엔드가 없는 것은 health로 보이게 한다. 실제 검색은 module-5 소스가 store 부재로 건너뛴다 |

### 11.7 module-3 구현 중 결정 (2026-11-17)

| # | Design 원안 | 구현 | 이유 |
|---|------------|------|------|
| M3-1 | V1 가정: parent 청크가 ES에 있는지 확인 필요 | **확인됨**: ES에 parent·child·요약이 모두 저장된다. parent가 있으면 parent만, 없으면(full·semantic·section_aware) 그 청크를, 요약(`section_summary`·`document_summary`)은 제외 | parent는 문맥이 넓고 LLM 호출 수가 적다. 근거 `chunk_id`는 parent id다. 하이브리드 결과의 child id와 겹침 처리는 module-5에서 정한다 |
| M3-2 | 판정(module-4) | module-3는 **임시 판정**: (scope, 정규화 키, 타입) 정확 일치면 연결, 아니면 새 엔티티. 같은 잡 안에서는 메모리 캐시로 중복 생성을 막는다 | module-4에서 후보 검색과 Jev/LLM 판정으로 교체한다. 판정 기록 테이블(V089)도 module-4에서 만든다 |
| M3-3 | 조문 엔티티 키 | 규칙 추출기가 `Mention.key="{document_id}::제N조"`를 직접 지정하고, 표시 이름은 "제N조"로 둔다 | 다른 문서의 같은 조문 번호와 섞이지 않게 한다. LLM 프롬프트는 조문을 뽑지 않도록 지시해 중복을 줄인다 |
| M3-4 | 쓰기 | 청크 1개분(청크·새 엔티티·언급·RELATES·REFERS_TO)을 Neo4j **한 트랜잭션**으로 저장(`execute_write`) | 중간에 실패해도 청크 단위로 롤백된다. resume은 `Chunk.extractor_version`으로 판단한다 |
| M3-5 | LLM 호출 상한 | 호출 전에 1회를 예약하고 상한에 닿으면 남은 청크를 건너뛰고 partial(`budget exhausted`) | 동시 실행 중에도 상한을 넘지 않는다. 실패한 호출도 1회로 센다 |
| M3-6 | 실행 시점 store | 러너는 `RuntimeGraphStore`(현재 store로 매번 위임)를 받는다 | 기동 시 차원 불일치로 store가 꺼져도 러너가 이전 store를 붙잡지 않는다 |
| M3-7 | 업로드 훅 조건 | 단계 off, 추출 off, 모델 미설정, 업로드 실패, 청크 0개, 엑셀(.xlsx·.xls·.csv)이면 건너뜀 | 섹션 요약 선례(엑셀 제외)와 같다 |
| M3-8 | LLM 팩토리 | 섹션 요약 잡과 같은 `LLMFactory`(PII 가드 미적용) | 업로드 후 잡 선례를 따랐다. PoC 문서는 고객 정보가 없는 규정 문서로 제한한다(가이드 §5). 사내 도입 전 PII 가드 적용 여부를 다시 검토한다 |
| M3-9 | 관리자 KB 문서 목록 | KB 권한 검사 없이 `document_metadata.find_by_kb_id` + 문서별 최근 잡 | 관리자 전용 API다(`require_role("admin")`) |
| M3-10 | 표 데이터 제외는 업로드 훅에만 적용 | `DocumentEligibilityPolicy`로 업로드 훅과 관리자 수동 실행 모두 엑셀·CSV를 제외한다(수동 실행은 422 `GRAPH_UNSUPPORTED_DOCUMENT`) | 2026-11-17 첫 실추출에서 엑셀 문서가 값(금액·비율)을 엔티티로 만들고 관계가 모두 '기타'로 나왔다. 대표자 이름·사업자번호 같은 값도 Aura에 저장됐다(E2E 샘플 데이터, 즉시 삭제) |

#### 11.7.1 실추출 관찰 (2026-11-17, Aura + gpt-5.1)

| 문서 | 결과 | 관찰 |
|------|------|------|
| `거래처정보_한빛상사.xlsx` (E2E 샘플) | 엔티티 23, 관계 13, 모두 '기타' | 표 데이터라 그래프에 맞지 않음 → M3-10, 그래프 삭제 완료 |
| `여신취급규정.pdf` (청크 2 → 추출 단위 1, LLM 1회, 약 20초) | 엔티티 29, 관계 24 | 관계 타입이 설정 목록(적용대상·한도·예외·요건·포함·정의)대로 나왔고 근거 문장이 모두 원문에 있다. "운전자금대출 한도 -[예외]-> 담보 제공 시 매출액의 40%"처럼 예외 관계가 잡혔다 |

module-4 이후 개선 후보:
- **조문↔개념 연결 없음:** 청크가 "여신 취급 규정 (발췌)"로 시작해 첫머리 조문 규칙이 맞지 않았다. 그래서 `제12조`~`제25조`가 고립 엔티티가 됐다. `제N조(제목)` 패턴으로 조문과 제목 개념을 잇는 규칙을 추가하는 것을 검토한다.
- **수치 엔티티:** "연 4.2%", "최장 36개월"이 독립 엔티티가 됐다. 기준값으로서 검색에 쓸모는 있지만, 같은 값이 다른 문맥에서 잘못 연결될 수 있다. module-4 판정에서 `수치기준` 타입은 자동 연결하지 않는 방안을 검토한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-16 | 초안 — Option C 선택, Neo4j 벡터 인덱스(D9), 비관리자 use_graph 조용히 False, general 전환 평가 기록 필수(사유 입력 시 강제 가능), DDL V086~V089 초안 | 배상규 |
| 0.2 | 2026-11-16 | DDL V086~V089 사용자 승인 | 배상규 |
| 0.3 | 2026-11-17 | module-1 구현 중 결정 M1-1~M1-7 (§11.5) | 배상규 |
| 0.4 | 2026-11-17 | module-2 구현 중 결정 M2-1~M2-6 (§11.6), 마이그레이션 번호 재배치 | 배상규 |
| 0.5 | 2026-11-17 | module-3 구현 중 결정 M3-1~M3-9 (§11.7), V1 가정 확인 | 배상규 |
| 0.6 | 2026-11-17 | Aura 실연결로 V4 확인, 첫 실추출 관찰(§11.7.1), M3-10 표 데이터 제외 통일 | 배상규 |
