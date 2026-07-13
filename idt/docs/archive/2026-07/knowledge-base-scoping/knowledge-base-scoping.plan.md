# knowledge-base-scoping Planning Document

> **Summary**: 벡터DB 물리 컬렉션 생성을 관리자 전용으로 제한하고, 일반 사용자는 "지식베이스(논리 단위)"를 생성해 Qdrant payload(메타데이터) 필터링으로 격리·공유하는 구조를 신규 경로로 병행 도입한다. 기존 API/메서드는 유지하고, 검증 후 추후 교체한다.
>
> **Project**: sangplusbot (idt 백엔드 전용)
> **Author**: 배상규
> **Date**: 2026-07-07
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재는 일반 사용자가 각자 Qdrant 물리 컬렉션을 직접 생성하고 에이전트가 그중 하나를 선택한다. 컬렉션이 사용자 수만큼 파편화되어 지식 베이스 공유가 어렵고(권한을 컬렉션 단위로만 제어), 물리 컬렉션 난립으로 운영 관리도 힘들다. |
| **Solution** | 물리 컬렉션 생성은 관리자 전용 신규 엔드포인트로 제한하고, 사용자는 "지식베이스"라는 논리 단위를 생성한다. 지식베이스 메타(이름·소유자·scope)는 MySQL `knowledge_base` 테이블에 저장하고, 문서 업로드 시 청크 payload에 `kb_id`를 주입해 Qdrant/ES 양쪽에서 필터링 가능하게 한다. 기존 컬렉션 CRUD·업로드 경로는 그대로 두고 신규 경로를 병행 추가한다. |
| **Function/UX Effect** | 사용자는 물리 컬렉션을 몰라도 지식베이스 이름만 만들어 문서를 올리고, PERSONAL/DEPARTMENT/PUBLIC 스코프로 공유한다. 관리자는 소수의 물리 컬렉션(임베딩 모델별)만 관리하면 된다. |
| **Core Value** | 지식 베이스 공유의 단위를 "물리 컬렉션"에서 "논리 지식베이스"로 전환 — 공유가 쉬워지고, 컬렉션 수가 통제되며, 추후 에이전트 RAG 필터 연동의 기반이 된다. |

---

## 1. Overview

### 1.1 Purpose

물리 컬렉션(Qdrant collection)과 논리 지식베이스(payload 필터 단위)를 분리한다.

- **관리자**: 물리 컬렉션 생성/삭제 (임베딩 모델·벡터 차원 단위의 인프라 관리)
- **사용자**: 지식베이스 생성 → 관리자 컬렉션 중 하나를 선택해 그 안에 payload로 격리 저장
- **격리/공유**: 검색 시 `kb_id` payload 필터 + MySQL 스코프 권한으로 제어

이번 사이클은 **백엔드 신규 경로만** 추가한다. 기존 엔드포인트/유스케이스/메서드는 수정하지 않고(additive-only), 신규 구조 검증 후 별도 PDCA로 교체(갈아끼기)한다.

### 1.2 Background — 현재 구조 (2026-07-07 코드 확인)

**컬렉션 생성이 사용자 개방형**
- `POST /api/v1/collections` (`src/api/routes/collection_router.py:237`) — `get_current_user`만 통과하면 누구나 물리 컬렉션 생성. scope(PERSONAL/DEPARTMENT/PUBLIC)는 MySQL `collection_permissions`(V013)로 관리.
- `CollectionManagementUseCase` (`src/application/collection/use_case.py`) — 생성/삭제/rename/scope 변경 모두 구현되어 있으며 재사용 가능.

**payload 필터링 인프라는 이미 절반 존재**
- 업로드 시 청크 payload에 `document_id`, `user_id`, `collection_name` 주입 중 (`src/application/unified_upload/use_case.py:98-101`) — Qdrant와 ES 양쪽에 동일 metadata가 흘러감.
- 에이전트 RAG 도구 설정 `RagToolConfig` (`src/domain/agent_builder/rag_tool_config.py`)에 `metadata_filter: dict[str, str]`가 이미 있고 ToolFactory → hybrid search까지 전달됨 (`src/infrastructure/agent_builder/tool_factory.py:86`). 즉 **`kb_id`를 payload에 심기만 하면 후속 연동의 기술적 장벽은 낮다.**
- `QdrantRetriever.retrieve*`는 `MetadataFilter.to_qdrant_filter()`로 payload 필터 검색을 이미 지원.

**RBAC 준비 완료**
- `UserRole.ADMIN` 존재 (`src/domain/auth/entities.py`), `require_role('admin')` dependency 제공 (`src/interfaces/dependencies/auth.py:70`).

**주의: 하이브리드 검색 = Qdrant + Elasticsearch**
- 격리가 유효하려면 `kb_id`가 Qdrant payload와 ES 문서 필드 **양쪽에** 저장되어야 한다. 업로드 경로에서 chunk.metadata에 주입하면 두 저장소로 함께 전파되는 구조임을 확인했다.

### 1.3 사용자 결정 사항 (2026-07-07 확인)

| 질문 | 결정 |
|------|------|
| 물리 컬렉션 매핑 | **지식베이스 생성 시 사용자가 관리자 컬렉션 중 선택**. 단, 추후 "관리자가 매핑 지정" 방식으로 전환 가능성이 있으므로 **매핑 결정 로직을 정책 객체로 추상화**해 유연성 확보 |
| 지식베이스 메타 저장소 | **MySQL 테이블(1차 소스: 목록/검색/권한) + Qdrant payload에도 식별 정보 이중 기록**(추후 payload 단독 필터링 대비) |
| 공유 권한 모델 | 기존 3단계 스코프(PERSONAL/DEPARTMENT/PUBLIC) **그대로 재사용** |
| 이번 구현 범위 | **지식베이스 CRUD API + 업로드 경로 신규 버전**. 검색/RAG 필터 연동, 삭제 시 벡터 정리는 후속 |
| 기존 코드 | 기존 메서드/엔드포인트 무수정 유지, 신규 경로 병행 추가 후 추후 교체 |

---

## 2. Scope

### 2.1 In Scope (백엔드 idt/)

**A. 지식베이스 도메인 + 영속화**
- [ ] `domain/knowledge_base/`: 엔티티(`KnowledgeBase`), 스키마, `KnowledgeBaseRepositoryInterface`, 정책(`KnowledgeBasePolicy` — 이름 검증, 소유자당 이름 유니크, 스코프 규칙)
- [ ] 물리 컬렉션 배정 정책 추상화: `CollectionAssignmentPolicy`(가칭) — 현재 구현은 "사용자 선택 + 해당 컬렉션 접근 가능 여부 검증", 추후 "관리자 지정 매핑" 구현체로 교체 가능한 인터페이스
- [ ] Flyway 마이그레이션 `V040__create_knowledge_base.sql`: `kb_id`(UUID, payload 필터 키), `name`, `description`, `owner_id`, `scope`, `department_id`, `collection_name`, timestamps — FK 참조 시 CHARSET/COLLATE 명시 금지 관례(V037 선례) 준수
- [ ] `infrastructure/persistence/`: SQLAlchemy 모델 + repository (세션 규칙 `docs/rules/db-session.md` 준수)

**B. 지식베이스 CRUD API — 신규 라우터 `/api/v1/knowledge-bases`**
- [ ] `POST /` — 생성: name, description, scope(+department_id), collection_name(관리자 컬렉션 중 선택). 대상 컬렉션 존재·읽기 권한 검증
- [ ] `GET /` — 목록: 접근 가능한 것만(본인 PERSONAL + 소속 부서 DEPARTMENT + PUBLIC)
- [ ] `GET /{kb_id}` — 상세 (문서 수 등 부가정보는 Design에서 범위 확정)
- [ ] `DELETE /{kb_id}` — 소유자 또는 관리자만. **MySQL 레코드만 삭제** (Qdrant/ES 벡터 정리는 후속 — 고아 payload가 남는다는 점을 API 응답/문서에 명시)
- [ ] application layer: `KnowledgeBaseUseCase` (기존 `CollectionManagementUseCase` 패턴 준수, activity log 연동 여부는 Design에서 결정)

**C. 관리자 전용 컬렉션 생성 — 신규 엔드포인트**
- [ ] `POST /api/v1/admin/collections` — `Depends(require_role('admin'))` 가드, 내부는 기존 `CollectionManagementUseCase.create_collection` 재사용 (로직 복제 금지)
- [ ] 기존 `POST /api/v1/collections`는 무수정 유지 (deprecation은 후속 PDCA)

**D. 지식베이스 지정 업로드 — 신규 버전**
- [ ] `POST /api/v1/knowledge-bases/{kb_id}/documents` — 흐름: KB 조회 → 쓰기 권한 검증(소유자/스코프) → KB의 `collection_name` 자동 결정(사용자가 컬렉션을 직접 지정하지 않음) → 청크 payload에 `kb_id`(필터 키) + `kb_name`(표시용) 주입 → Qdrant + ES 동시 저장
- [ ] 구현 방식: 기존 `UnifiedUploadUseCase`를 최대 재사용. `UnifiedUploadRequest`에 optional `extra_metadata` 필드 추가(additive, 기존 호출 무영향) vs 얇은 wrapper 유스케이스 — **Design에서 최종 확정** (추천: additive optional 필드)

**E. 테스트 (TDD — 구현 전 작성)**
- [ ] domain 정책 단위 테스트, use case 테스트(mock repo), router 테스트(admin 가드 403 포함), 업로드 payload 주입 검증 테스트

### 2.2 Out of Scope (후속 PDCA)

| 항목 | 사유/비고 |
|------|-----------|
| 검색/RAG 도구의 지식베이스 필터 연동 | `RagToolConfig.metadata_filter`에 `kb_id` 지정으로 연결 가능 — 인프라 확인 완료, 별도 사이클 |
| KB 삭제 시 Qdrant 포인트/ES 문서 정리 | delete-by-payload-filter 구현 필요, 이번엔 레코드만 삭제 |
| 기존 컬렉션 생성 경로 차단·이관("갈아끼기") | 신규 구조 검증 후 진행 |
| KB rename / scope 변경 API | kb_id 필터 방식이라 rename이 payload 재태깅을 요구하지 않음 — 필요 시 저비용 추가 가능 |
| 문서 목록/삭제의 KB 스코프 버전 (doc_browse) | 후속 |
| 프론트엔드 (idt_front) | 백엔드 검증 후 별도 진행 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| FR-01 | 관리자만 신규 경로(`/api/v1/admin/collections`)로 물리 컬렉션을 생성할 수 있다. 일반 사용자는 403 | High |
| FR-02 | 사용자는 지식베이스를 생성할 수 있다 — 이름, 설명, 스코프, 대상 물리 컬렉션(접근 가능한 것 중) 선택 | High |
| FR-03 | 지식베이스 목록/상세는 스코프 권한(PERSONAL 본인/DEPARTMENT 소속/PUBLIC 전체)에 따라 필터링된다 | High |
| FR-04 | 지식베이스 지정 업로드 시 모든 청크 payload에 `kb_id`가 자동 주입되어 Qdrant·ES 양쪽에 저장된다 | High |
| FR-05 | 지식베이스 메타데이터는 MySQL이 1차 소스이며, 식별 정보(`kb_id`, `kb_name`)는 payload에도 이중 기록된다 | High |
| FR-06 | 소유자/관리자는 지식베이스를 삭제할 수 있다 (이번 범위: MySQL 레코드만) | Medium |
| FR-07 | 동일 소유자 내 지식베이스 이름은 중복될 수 없다 | Medium |

### 3.2 Non-Functional Requirements

| ID | 요구사항 |
|----|----------|
| NFR-01 | 기존 엔드포인트·유스케이스·테스트에 회귀 없음 (additive-only; optional 필드 추가만 허용) |
| NFR-02 | Thin DDD 레이어 준수 — domain은 LangChain/DB 무참조, 정책은 domain에 |
| NFR-03 | TDD — 테스트 선작성 (pytest) |
| NFR-04 | 함수 40줄 이하, if 중첩 2단계 이하, config 하드코딩 금지 |
| NFR-05 | 로깅 규칙(LOG-001) 준수 — print 금지, request_id 전파 |
| NFR-06 | DB 세션 규칙 준수 — repository 내 commit/rollback 금지, UseCase 단일 세션 |

---

## 4. 핵심 설계 방향 (Plan 레벨 결정, 상세는 Design)

1. **필터 키는 불변 UUID `kb_id`** — 이름(`kb_name`)은 표시용으로만 payload에 동봉. 이름 변경 시 벡터 재태깅이 불필요해진다.
2. **물리 컬렉션 배정의 유연성** — "누가 어느 컬렉션에 배정되는가"를 domain 정책 인터페이스로 분리. 현재: 사용자 선택형. 추후: 관리자 매핑형으로 구현체만 교체.
3. **권한 재사용** — `CollectionScope` enum(`src/domain/collection/permission_schemas.py`)을 그대로 사용하되, 판정 로직은 KB 전용으로 신규 작성(기존 `collection_permissions` 테이블과 얽지 않음 — 이중 권한 체계의 공존 혼란 방지).
4. **Qdrant payload 인덱스** — `kb_id` keyword payload index 생성 여부를 Design에서 결정(필터 검색 성능 대비).

---

## 5. Risks & Mitigations

| 리스크 | 영향 | 대응 |
|--------|------|------|
| ES 인덱스 매핑에 `kb_id` 필드 부재/dynamic mapping 동작 차이 | 하이브리드 검색 격리 실패 | Design에서 `es_index_mappings.py` 확인, 필요 시 매핑 추가 |
| 기존 컬렉션 권한과 KB 스코프의 이중 체계 공존 | 권한 판정 혼란 | KB 경로에서는 KB 스코프만 판정. 물리 컬렉션 권한은 KB 생성 시 1회만 검사 |
| KB 삭제 후 고아 payload 잔존 (벡터 정리 후속) | 스토리지 낭비, 재생성 시 이름 충돌은 없음(kb_id 상이) | API 문서에 명시 + 후속 과제로 delete-by-filter 등록 |
| 하나의 컬렉션에 다수 KB 집중 시 필터 검색 성능 | 검색 지연 | `kb_id` payload index 검토 (Design) |
| 기존 업로드 경로와 신규 경로의 payload 스키마 불일치 | 추후 이관 시 마이그레이션 필요 | 기존 데이터는 `kb_id` 없음이 정상 — 이관 PDCA에서 백필 전략 수립 |

---

## 6. Acceptance Criteria

- [ ] 일반 사용자로 `POST /api/v1/admin/collections` 호출 시 403, 관리자는 201
- [ ] 지식베이스 생성 → 목록/상세 조회가 스코프별로 올바르게 필터링됨 (PERSONAL 타인 KB 비노출)
- [ ] `POST /api/v1/knowledge-bases/{kb_id}/documents` 업로드 후 Qdrant 포인트 payload와 ES 문서에 `kb_id` 존재
- [ ] 업로드 시 물리 컬렉션은 KB 레코드에서 자동 결정됨 (요청 본문에 컬렉션 지정 없음)
- [ ] 기존 테스트 스위트 전체 통과 (사전 실패분 제외 — 신규 회귀 0건)
- [ ] `/verify-architecture`, `/verify-tdd` 통과

---

## 7. 후속 로드맵 (참고)

1. **kb-rag-filter**: `RagToolConfig`에 지식베이스 선택 추가 → 에이전트 검색이 `kb_id` 필터로 동작
2. **kb-vector-cleanup**: KB 삭제 시 Qdrant delete-by-filter + ES delete-by-query
3. **collection-path-migration**: 기존 사용자 컬렉션 생성 경로 차단, 기존 데이터 백필/이관, 구 API deprecated
4. **프론트엔드**: 지식베이스 관리 UI + 에이전트 빌더 연동 (`/api-contract-sync`)
