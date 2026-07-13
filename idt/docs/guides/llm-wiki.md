# LLM Wiki (Self-Improving RAG) — 등록·사용 가이드

> Task ID: LLM-WIKI-001
> Last Updated: 2026-07-07
> 관련 마이그레이션: `db/migration/V036__create_wiki_article.sql`

---

## 1. 개요

LLM Wiki는 **원본 문서 청크를 LLM으로 정제(distill)해 만든 "정제 지식 항목(WikiArticle)"의 저장소**다.
에이전트가 RAG 검색을 할 때 원본 청크보다 정제된 위키 항목을 우선 노출해 답변 품질을 높이는 것이 목적이다.

핵심 설계 원칙 두 가지:

1. **거버넌스 게이트** — LLM이 자동 생성한 항목은 무조건 `draft`로 적재되고, **관리자 승인(approve) 후에만 검색에 노출**된다. 환각이 지식 베이스에 누적되는 것을 막는 보수적 기본값이다.
2. **출처 불변식** — `source_refs`(출처 추적 식별자)가 비어 있으면 위키 항목을 생성할 수 없다. 모든 위키 지식은 원본으로 역추적 가능해야 한다.

```
[원본 문서 청크 (ES)] ──distill(LLM 정제)──▶ [WikiArticle draft]
                                                  │
                                     관리자 승인(approve) ← /admin/wiki UI
                                                  ▼
[에이전트 RAG 검색] ──위키 우선 검색──▶ [approved + 미만료 위키] ──부족분──▶ [기존 hybrid search 폴백]
```

---

## 2. 구성 요소 맵 (레이어별)

| 레이어 | 파일 | 역할 |
|--------|------|------|
| domain | `src/domain/wiki/entity.py` | `WikiArticle` 엔티티, `WikiStatus`/`WikiSourceType` enum, 상태 전이 메서드 |
| domain | `src/domain/wiki/policies.py` | `WikiPolicy` — 생성 불변식·상태 전이·confidence 검증 |
| application | `src/application/wiki/distill_use_case.py` | `DistillToWikiUseCase` — 원본 → draft 위키 생성 |
| application | `src/application/wiki/review_use_case.py` | `WikiReviewUseCase` — 승인/반려/폐기/복구/편집 |
| application | `src/application/wiki/query_use_case.py` | `WikiQueryUseCase` — 목록/단건 조회 |
| application | `src/application/wiki/wiki_first_search_use_case.py` | `WikiFirstSearchUseCase` — 위키 우선 검색 + 원본 폴백 |
| application | `src/application/wiki/run_scoped_wiki_search.py` | `RunScopedWikiSearch` — 에이전트 런타임 검색 어댑터 |
| application | `src/application/wiki/interfaces.py` | `WikiSourceProvider`, `WikiDistillerInterface` 추상화 |
| application | `src/application/repositories/wiki_repository.py` | `WikiArticleRepository` 인터페이스 |
| infrastructure | `src/infrastructure/wiki/wiki_repository.py` | MySQL(SoT) + Qdrant(벡터) 합성 저장소 구현 |
| infrastructure | `src/infrastructure/wiki/wiki_distiller.py` | `WikiDistiller` — ChatOpenAI 기반 LLM 정제기 |
| infrastructure | `src/infrastructure/wiki/wiki_source_provider.py` | `ElasticsearchWikiSourceProvider` — ES 청크 조회·그룹핑 |
| infrastructure | `src/infrastructure/wiki/models.py` | `WikiArticleModel` (SQLAlchemy ORM) |
| interfaces(API) | `src/api/routes/wiki_router.py` | `/api/v1/wiki` 엔드포인트 |
| DI | `src/api/main.py` → `create_wiki_factories()` | per-request UseCase 팩토리 + `dependency_overrides` 주입 |
| 프론트 | `idt_front/src/pages/WikiPage/` | `/admin/wiki` 관리 화면 (목록·상세·승인·편집) |
| 프론트 | `idt_front/src/hooks/useWiki.ts`, `services/wikiService.ts`, `types/wiki.ts` | TanStack Query 훅 / API 클라이언트 / 타입 |

---

## 3. 데이터 모델

### 3-1. 저장소 이원화

| 저장소 | 역할 |
|--------|------|
| **MySQL** (`wiki_article` 테이블) | 메타데이터·라이프사이클의 **Source of Truth**. 상태(status)의 권위는 항상 MySQL |
| **Qdrant** (`wiki_knowledge` 컬렉션) | 본문 임베딩 색인. 유사도 검색 담당. hit 후 MySQL로 하이드레이션 |
| ES(BM25) | 현재 위키 검색 경로에서는 **미사용** (후속 도입 예정) |

`save()`/`update()` 시 MySQL 저장과 동시에 본문 임베딩을 Qdrant에 색인한다
(`wiki_repository.py:_index_vector`, 메타데이터: `agent_id`, `status`, `source_type`, `title`).

### 3-2. `WikiArticle` 주요 필드

| 필드 | 의미 |
|------|------|
| `agent_id` | 소속 에이전트. **위키는 에이전트 단위로 스코프**된다 |
| `title` / `content` | 제목(≤200자) / 정제 본문(≤8,000자) |
| `source_type` | `distilled`(문서 정제) · `conversation`(대화 환류) · `websearch`(웹서치 환류) · `human`(사람 작성) |
| `source_refs` | 출처 청크 id 목록. **최소 1개 필수(출처 불변식)** |
| `status` | `draft` → `approved` → `deprecated` 라이프사이클 |
| `confidence` | 신뢰도 0~1 (기본 0.5, 환류 신호로 갱신 예정). 검색 결과의 score로 사용됨 |
| `valid_until` | 만료 시각. `NULL`=무기한. 만료된 항목은 approved여도 검색 비노출 |
| `version` / `editor_id` / `reviewer_id` | 편집 버전(편집 시 +1) / 마지막 편집자 / 승인자 |

### 3-3. 상태 전이 (WikiPolicy.ALLOWED_TRANSITIONS)

```
draft ──approve──▶ approved ──deprecate──▶ deprecated
  │                    ▲                        │
  └──reject──▶ deprecated └──────restore────────┘
```

- 허용 전이: `draft→approved`, `draft→deprecated`, `approved→deprecated`, `deprecated→approved`
- 검색 노출 조건: `status == approved` **AND** 미만료 (`WikiArticle.is_searchable()`)

---

## 4. 등록(생성) 경로

### 4-1. 자동 정제 — Distill API (현재 유일한 자동 생성 경로)

관리자가 특정 에이전트의 문서 컬렉션을 지정해 일괄 정제를 트리거한다.

```
POST /api/v1/wiki/distill        (admin 권한)
{
  "agent_id": "<에이전트 UUID>",
  "collection_name": "<ES 인덱스(컬렉션)명>",
  "max_articles": 50               // 1~500, 기본 50
}
```

내부 흐름 (`DistillToWikiUseCase.execute`):

1. **원본 조회·그룹핑** — `ElasticsearchWikiSourceProvider`가 ES 인덱스에서 청크를 최대 200건 조회하고, `source` 필드(문서 단위) 기준으로 그룹핑한다. 각 그룹이 위키 항목 후보 1건이 된다. 빈 content 청크는 제외.
2. **LLM 정제** — `WikiDistiller`가 그룹별 청크를 합쳐 ChatOpenAI(`openai_llm_model`, temperature=0)로 요약한다. 시스템 프롬프트는 "원문에 있는 사실만 사용, 추측·창작 금지, 결정사항·수치·조건 보존" 규칙을 강제한다. 제목은 `topic_hint`(그룹 키) 또는 본문 첫 문장에서 파생.
3. **불변식 검증** — `WikiPolicy.validate_for_creation`으로 제목/본문 길이, `source_refs ≥ 1`, confidence 범위를 검증. **위반 그룹은 저장하지 않고 건너뛴다**(warning 로그).
4. **저장** — `status=draft`, `source_type=distilled`로 MySQL 저장 + Qdrant 색인.

응답으로 생성된 draft 목록(`created_count`, `items`)이 반환되며, 이 시점에는 **검색에 노출되지 않는다**.

### 4-2. 사람 편집 — Edit API

```
PUT /api/v1/wiki/{id}            (admin 권한)
{ "title": "...", "content": "...", "editor_id": "<사용자 id>" }
```

- 기존 항목의 제목/본문을 교체하고 `version`을 +1 한다. 상태는 바뀌지 않는다.
- 편집 시에도 생성 불변식(제목/본문 길이 등)을 재검증한다.
- 신규 항목을 사람이 처음부터 작성하는 API(`source_type=human` 신규 생성)는 현재 없다 — 편집만 가능.

### 4-3. 환류 생성 (예정, 미구현)

`WikiSourceType.CONVERSATION`(대화 환류) / `WEBSEARCH`(웹서치 환류)는 enum과 스키마에 예약만 되어 있고, **생성 코드는 아직 없다**(Phase 3 예정). websearch 출처는 `valid_until` 설정이 권장된다.

---

## 5. 거버넌스(승인) 흐름

모든 리뷰 API는 admin 권한이 필요하며, `WikiReviewUseCase`가 `WikiPolicy.validate_transition`으로 전이를 검증한다.

| API | 전이 | 비고 |
|-----|------|------|
| `PATCH /api/v1/wiki/{id}/approve` | draft → approved | body: `{"reviewer_id": "..."}`. 승인자 기록. **이후 검색 노출** |
| `PATCH /api/v1/wiki/{id}/reject` | draft → deprecated | 초안 반려 |
| `PATCH /api/v1/wiki/{id}/deprecate` | approved → deprecated | 운영 중 폐기. **즉시 검색 제외** |
| `PATCH /api/v1/wiki/{id}/restore` | deprecated → approved | body: `{"reviewer_id": "..."}`. 복구 |

- 미존재 항목 → 404, 허용되지 않은 전이 → 422.
- 상태 변경은 MySQL 갱신 + Qdrant 재색인(메타데이터의 `status` 갱신)을 함께 수행하지만, **검색 노출 판정은 항상 MySQL 하이드레이션 후 도메인 `is_searchable()`로 최종 필터**하므로 Qdrant 메타가 낡아도 안전하다.

### 조회 API

| API | 설명 |
|-----|------|
| `GET /api/v1/wiki?agent_id=...&status=...` | 에이전트 스코프 목록 (status 필터 선택, 로그인 사용자) |
| `GET /api/v1/wiki/{id}` | 단건 조회 |

---

## 6. 사용(검색) 경로 — 에이전트 RAG에서 위키가 쓰이는 방식

### 6-1. 옵트인 방식: RAG 도구별 `use_wiki_first` 플래그

위키 우선 검색은 전역이 아니라 **RAG 도구(내부 문서 검색) 단위로 옵트인**한다.

- 도메인: `src/domain/agent_builder/rag_tool_config.py` → `RagToolConfig.use_wiki_first: bool = False`
- API 스키마: `src/application/agent_builder/schemas.py` → `RagToolConfigSchema.use_wiki_first`
- 프론트: Agent Builder의 RAG 설정 패널(`idt_front/src/components/agent-builder/RagConfigPanel.tsx`)에 체크박스로 노출

에이전트 생성/수정 시 이 플래그를 켜면 해당 도구만 위키 우선 검색을 탄다.

### 6-2. 런타임 흐름

```
InternalDocumentSearchTool.execute(query)
        │  (ToolFactory._select_search: use_wiki_first=True → wiki_search 주입)
        ▼
RunScopedWikiSearch.execute(request, request_id)
        │  RunContext(ContextVar)에서 agent_id 획득
        │  ├─ agent_id 없음(graph 외부 호출 등) → 기존 HybridSearchUseCase로 즉시 폴백
        │  └─ agent_id 있음 → session_factory로 MySQL 세션 오픈 후 ↓
        ▼
WikiFirstSearchUseCase.execute(request, agent_id, now, request_id)
        │  1) WikiArticleRepository.search_similar:
        │     쿼리 임베딩 → Qdrant(wiki_knowledge, agent_id 필터) top_k 검색
        │     → hit id를 MySQL로 하이드레이션 → is_searchable(approved+미만료)만 통과
        │  2) 위키 결과 ≥ top_k → 위키만 반환
        │  3) 부족하면 기존 HybridSearchUseCase 폴백 → 위키 우선 병합(id 중복 시 위키 유지)
        ▼
HybridSearchResponse  (위키 결과는 source="wiki", score=confidence,
                       metadata에 title/source_type/status/agent_id/wiki="true")
```

설계 포인트:

- `RunScopedWikiSearch`는 기존 hybrid search와 동일한 `execute(request, request_id)` 시그니처를 유지해 **`InternalDocumentSearchTool`을 수정하지 않고 끼워 넣는다**.
- ToolFactory는 앱 싱글톤이므로, 위키 저장소(MySQL 세션 필요)는 **매 호출마다 `session_factory`로 세션을 열어 구성**한다(RunTracker와 동일 패턴).
- 배선 위치: `src/api/main.py` (약 2021행, "LLM-WIKI-001 Step6" 주석) — `RunScopedWikiSearch` 구성 후 `ToolFactory(wiki_search=...)`로 주입.

### 6-3. 검색 결과에서 위키 구분

답변/로그에서 위키 유래 결과는 다음으로 식별한다:

- `source == "wiki"`
- `metadata.wiki == "true"`, `metadata.title`, `metadata.source_type`, `metadata.status`

---

## 7. 프론트엔드 (관리 UI)

| 경로/파일 | 역할 |
|-----------|------|
| `/admin/wiki` (`idt_front/src/pages/WikiPage/`) | 위키 관리 페이지. 에이전트/상태 필터 목록(`WikiArticleTable`) + 상세 패널(`WikiDetailPanel`)에서 승인·반려·폐기·복구·편집·정제 트리거 |
| `idt_front/src/hooks/useWiki.ts` | `useWikiList`, `useWikiArticle`, `useDistillWiki`, `useApproveArticle`, `useRejectArticle`, `useDeprecateArticle`, `useRestoreArticle`, `useUpdateArticle` — 뮤테이션 성공 시 wiki 쿼리 전체 무효화 |
| `idt_front/src/services/wikiService.ts` | axios 기반 API 클라이언트 |
| `idt_front/src/types/wiki.ts` | 백엔드 `api_schemas.py`와 동기화된 타입 |
| `idt_front/src/components/agent-builder/RagConfigPanel.tsx` | Agent Builder에서 `use_wiki_first` 체크박스 |

---

## 8. 설정

| 설정 | 위치 | 기본값 |
|------|------|--------|
| `wiki_collection_name` | `src/config.py` | `wiki_knowledge` (Qdrant 컬렉션명) |
| 임베딩 모델 | `settings.openai_embedding_model` | `text-embedding-3-small` |
| 정제 LLM | `settings.openai_llm_model` | `gpt-4o-mini` |
| ES 접속 | `settings.es_host/es_port/es_scheme` | distill 원본 조회용 |
| 청크 조회 상한 | `ElasticsearchWikiSourceProvider.chunk_fetch_limit` | 200 (생성자 파라미터) |
| 그룹핑 필드 | `ElasticsearchWikiSourceProvider.group_field` | `source` (생성자 파라미터) |

---

## 9. 테스트 맵

| 대상 | 테스트 파일 |
|------|-------------|
| 라우터 (API 계약) | `tests/api/test_wiki_router.py` |
| 위키 우선 검색 | `tests/application/wiki/test_wiki_first_search_use_case.py` |
| 런타임 어댑터 | `tests/application/wiki/test_run_scoped_wiki_search.py` |
| 저장소 계약 | `tests/application/wiki/test_wiki_repository_contract.py` |
| 정제기 | `tests/infrastructure/wiki/test_wiki_distiller.py` |
| 저장소 구현/통합 | `tests/infrastructure/wiki/test_wiki_repository.py`, `test_wiki_repository_integration.py` |
| 소스 프로바이더 | `tests/infrastructure/wiki/test_wiki_source_provider.py` |

---

## 10. 현재 한계 / 후속 과제

- **환류 생성 미구현** — `conversation`/`websearch` source_type은 예약만 됨(Phase 3). confidence를 환류 신호로 갱신하는 로직도 미구현(`WikiPolicy.clamp_confidence`만 준비됨).
- **ES(BM25) 위키 색인 미도입** — 위키 검색은 현재 Qdrant 벡터 검색만 사용.
- **human 신규 작성 API 없음** — 사람은 기존 항목 편집만 가능, 신규 작성은 distill 경로뿐.
- **만료 항목 자동 정리 없음** — `valid_until` 경과 항목은 검색에서만 제외되고 별도 배치 정리는 없다.
- 위키 항목 삭제 API는 라우터에 노출되어 있지 않다(repository `delete`는 존재).
