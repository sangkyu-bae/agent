# kb-rag-filter Planning Document

> **Summary**: `/agent-builder` 도구함 → 내부문서검색 설정에서 물리 컬렉션 대신 논리 "지식베이스(KB)"를 선택할 수 있게 한다. `RagToolConfig`에 독립 opt-in 필드 `kb_id`를 신설하고, 검색 시 `kb_id` payload 필터로 격리하며, KB scope에 따른 에이전트 공개범위 자동 제한도 이식한다. 기존 컬렉션 선택 UI/필드는 그대로 보존한다(교차검증 기준선).
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Author**: 배상규
> **Date**: 2026-07-09
> **Status**: Draft
> **Predecessor**: `knowledge-base-scoping` (2026-07 아카이브) — 후속 과제 1번 "kb-rag-filter" 착수

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 문서 구조를 "물리 컬렉션 다수"에서 "단일(소수) 컬렉션 + 이름(kb_id) 메타데이터 격리"로 전환하기로 했고 백엔드 KB 계층(`knowledge_base` 테이블, 업로드 시 `kb_id` payload 주입)은 이미 완성됐지만, `/agent-builder`의 내부문서검색 설정은 여전히 물리 컬렉션 목록만 노출한다. 새 구조로 올린 문서를 에이전트가 대상 지정해 검색할 방법이 UI에 없다. |
| **Solution** | `RagToolConfig`에 신규 opt-in 필드 `kb_id`를 추가하고, 프론트 `RagConfigPanel`에 "검색 대상 지식베이스" 드롭다운을 **기존 컬렉션 드롭다운과 병행** 추가한다. ToolFactory가 `kb_id`를 metadata_filter로 병합하고 KB의 물리 컬렉션을 해석해 검색을 배선한다. KB scope(개인/부서/공개)에 따른 에이전트 공개범위 자동 제한(clamp)도 컬렉션과 동일하게 적용한다. |
| **Function/UX Effect** | 에이전트 제작자가 물리 컬렉션을 몰라도 "지식베이스 이름"만 골라 검색 범위를 지정할 수 있다. 개인/부서 KB를 고르면 에이전트 공개범위가 자동 제한되어 격리 정책이 유지된다. 기존 에이전트(컬렉션 지정)는 아무 영향 없이 동작한다. |
| **Core Value** | knowledge-base-scoping에서 만든 논리 KB 계층이 에이전트 검색까지 관통 — "단일 컬렉션 + 메타데이터 격리" 전환의 마지막 소비자 연결 고리를 완성한다. |

---

## 1. Overview

### 1.1 Purpose

에이전트 빌더의 내부문서검색 도구가 논리 지식베이스를 검색 대상으로 지정할 수 있게 한다.

- **선택**: 프론트에서 접근 가능한 KB 목록을 조회해 드롭다운으로 선택
- **검색**: `kb_id` payload 필터로 Qdrant/ES 하이브리드(및 라우팅) 검색 격리
- **격리 정책**: KB scope → 에이전트 공개범위 자동 제한(기존 컬렉션 clamp와 동일 정책)
- **호환**: 기존 `collection_name` 선택 경로는 무수정 보존 (독립 opt-in 원칙)

### 1.2 Background — 현재 구조 (2026-07-09 코드 확인)

**백엔드 KB 계층은 완성, 소비자만 부재**
- `GET /api/v1/knowledge-bases` — 인증 사용자 기준 KB 목록 조회 존재 (`src/api/routes/knowledge_base_router.py:213`). 응답(`KbInfoResponse`)에 `kb_id`, `name`, `scope`, `collection_name`, `department_id` 포함.
- 업로드 경로가 청크 payload에 `kb_id`/`kb_name` 주입 → Qdrant/ES 양쪽 저장 (knowledge-base-scoping 구현 완료).

**검색 배선도 이미 절반 존재**
- `RagToolConfig.metadata_filter` → ToolFactory → `InternalDocumentSearchTool` → hybrid search로 필터 전달 (`src/infrastructure/agent_builder/tool_factory.py:90`).
- 라우팅 검색(D4)은 `metadata_filter["kb_id"]`를 이미 `RoutedScope.kb_id`로 특별 취급 (`src/application/rag_agent/tools.py:37,185`). 즉 **kb_id를 metadata_filter에 실어주기만 하면 hybrid/routed 양쪽 다 동작 가능한 구조**.

**프론트는 물리 컬렉션만 인식**
- `RagConfigPanel.tsx` — `useCollections()`(물리 컬렉션 목록)로 "검색 대상 컬렉션" 드롭다운 렌더. KB 관련 코드는 idt_front에 0건 (`kb_id` grep 무일치).
- `types/ragToolConfig.ts`의 `RagToolConfig`에 `kb_id` 없음.

**공개범위 자동 제한(clamp)은 컬렉션 전용**
- `create_agent_use_case.py:332-353` — worker `tool_config["collection_name"]` 수집 → `collection_permissions` scope 조회 → `VisibilityPolicy.clamp_visibility`. `update_agent_use_case.py:203-209` 동일. **kb_id는 수집하지 않음** → KB scope 격리가 에이전트 공개범위에 반영 안 됨.

### 1.3 사용자 결정 사항 (2026-07-09 확인)

| 질문 | 결정 |
|------|------|
| UI 방식 | **지식베이스 드롭다운 신규 추가, 기존 컬렉션 드롭다운 유지** (독립 opt-in, 기존 설정 보존 — 교차검증 기준선) |
| 저장 방식 | **`RagToolConfig`에 first-class `kb_id: str \| None` 필드 신설** (metadata_filter 재사용 아님 — 의미 명시적, scope 검증 배선 용이) |
| scope 연동 | **이번 범위에 포함** — KB scope에 따른 에이전트 공개범위 자동 제한을 컬렉션과 동일하게 적용 |
| 프론트 범위 | **agent-builder 선택 UI만** — KB 목록/생성/문서 업로드 관리 화면은 별도 PDCA |

---

## 2. Scope

### 2.1 In Scope — 백엔드 (idt/)

**A. 도메인: RagToolConfig 확장**
- [ ] `RagToolConfig`에 `kb_id: str | None = None` 필드 추가 (`src/domain/agent_builder/rag_tool_config.py`) — 기본 None이면 기존 동작 완전 동일
- [ ] `RagToolConfigPolicy` 검증: kb_id 형식(UUID) 검증 여부는 Design에서 확정 (과검증 지양)

**B. ToolFactory / 검색 배선**
- [ ] `_parse_rag_config`가 `tool_config["kb_id"]` 수용
- [ ] `kb_id` 설정 시 effective `metadata_filter`에 `kb_id` 병합 후 `InternalDocumentSearchTool`로 전달 — hybrid(payload 필터)·routed(`RoutedScope.kb_id`) 양쪽 기존 경로 재사용, 도구 내부 무수정이 목표
- [ ] **물리 컬렉션 해석**: kb_id 설정 시 검색 대상 컬렉션은 KB의 `collection_name`이어야 함(기본 컬렉션과 다르면 빈 결과). 해석 시점(도구 생성 시 KB 조회 vs 프론트 저장 시 고정)은 Design에서 확정 — 초안은 백엔드 해석(단일 진실원, KB 컬렉션 변경에 안전)

**C. 공개범위 자동 제한(clamp) 확장**
- [ ] `create_agent_use_case`: `_extract_collection_names`와 병렬로 `tool_config["kb_id"]` 수집 → `KnowledgeBaseRepository`로 scope 조회 → 기존 scopes 목록에 합류해 `clamp_visibility`
- [ ] `update_agent_use_case`: 동일 로직 적용
- [ ] KB 미존재/삭제된 kb_id 참조 시 처리(에러 vs PERSONAL 간주)는 Design에서 확정

**D. API 스키마**
- [ ] agent_builder 요청/응답 스키마에 `kb_id` 노출 (`src/application/agent_builder/schemas.py` 등 RagToolConfig 직렬화 경로 전수 확인)
- [ ] `GET /api/v1/knowledge-bases` 재사용 — 신규 엔드포인트 없음. 단, 목록 응답이 에이전트 빌더 드롭다운에 필요한 필드(scope, name)를 이미 제공하는지 Design에서 재확인

### 2.2 In Scope — 프론트 (idt_front/)

**E. 타입/서비스/훅** (API 계약 동기화 규칙 준수)
- [ ] `types/ragToolConfig.ts`: `RagToolConfig.kb_id?: string` 추가, `KnowledgeBaseInfo` 타입 신설
- [ ] `constants/api.ts`: `/api/v1/knowledge-bases` 엔드포인트 상수
- [ ] `services/knowledgeBaseService.ts` + `hooks/useKnowledgeBases.ts` (TanStack Query, 컬렉션 훅과 동일 패턴)

**F. RagConfigPanel UI**
- [ ] "검색 대상 지식베이스" 드롭다운 신설 — 기존 "검색 대상 컬렉션" 섹션 위 또는 아래 병행 배치, scope 배지([개인]/[부서]/[공개]) 표시
- [ ] KB 선택 시 개인/부서 scope 안내문 표시 (컬렉션과 동일한 "에이전트 공개 범위가 자동 제한됩니다" 패턴)
- [ ] KB와 컬렉션 동시 지정 시 UX 규칙(예: KB 선택 시 컬렉션 드롭다운 비활성 + 안내) — Design에서 확정
- [ ] 도구함 요약(카드 배지 등)에 KB 이름 노출 여부 확인 — `LeftConfigPanel` 등 RagToolConfig 요약 표시 지점 전수 확인

### 2.3 Out of Scope (후속 PDCA)

| 항목 | 사유/연결 |
|------|----------|
| KB 목록/생성/삭제/문서 업로드 관리 화면 | 프론트 범위 결정에 따라 별도 사이클 |
| 기존 컬렉션 선택 UI 제거 및 데이터 이관 | 신규 경로 검증 후 교체 (독립 opt-in 원칙) |
| KB 삭제 시 이를 참조하는 에이전트 정리/알림 | 고아 kb_id 참조는 빈 결과로 동작 — Design에서 완화책만 명시 |
| 복수 KB 동시 선택(멀티 필터) | 단일 선택 우선, 수요 확인 후 확장 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | 에이전트 빌더 내부문서검색 설정에서 접근 가능한 지식베이스 목록을 조회·선택할 수 있다 | High |
| FR-02 | 선택한 KB는 `RagToolConfig.kb_id`로 저장되고, 미선택(None) 시 기존 동작과 완전히 동일하다 | High |
| FR-03 | `kb_id` 설정 시 내부문서검색이 해당 KB 문서로 격리된다 — hybrid(metadata_filter)·routed(RoutedScope) 양쪽 | High |
| FR-04 | `kb_id` 설정 시 검색이 KB의 물리 컬렉션을 대상으로 수행된다 (기본 컬렉션 오배선으로 빈 결과 금지) | High |
| FR-05 | 개인/부서 scope KB 선택 시 에이전트 공개범위가 자동 제한(clamp)된다 — 생성·수정 양쪽 | High |
| FR-06 | 기존 컬렉션 선택·metadata_filter 경로는 무수정 보존된다 | High |
| FR-07 | KB 선택 UI에 scope 배지와 공개범위 제한 안내가 표시된다 | Medium |

### 3.2 Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-01 | TDD — 백엔드 pytest(VO/ToolFactory/clamp), 프론트 Vitest(패널/훅) 테스트 선행 |
| NFR-02 | 레이어 규칙 준수 — KB scope 조회는 UseCase에서 Repository 인터페이스 경유, domain은 무의존 유지 |
| NFR-03 | API 계약 동기화 — 백엔드 스키마 변경분을 `idt_front/src/types`에 즉시 반영 |

---

## 4. 설계 시 확정할 결정 사항 (Design 이월)

1. **물리 컬렉션 해석 시점** — 초안: ToolFactory(도구 생성 시) KB 조회로 `collection_name` 결정. 대안: 에이전트 저장 시 고정. 트레이드오프: 매 실행 조회 비용 vs KB 컬렉션 변경 추적.
2. **kb_id + collection_name 동시 지정 규칙** — 초안: `kb_id` 우선, UI에서 동시 지정 차단. `metadata_filter`에 수동 `kb_id` 입력 시 신규 필드가 우선(경계 규칙 명문화).
3. **고아 kb_id 처리** — 에이전트 생성/수정 시 KB 존재 검증 여부, 실행 시 KB 삭제된 경우의 강등 동작.
4. **KB 목록 API의 권한 필터** — `list_knowledge_bases`가 요청자 접근 가능 KB만 반환하는지 확인, 아니면 필터 추가.
5. **kb_id 형식 검증 수준** — UUID 패턴 검증 vs 존재 검증만.

---

## 5. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| kb_id 필터 + 기본 컬렉션 오배선 → 항상 빈 결과 | 기능 무용 | FR-04를 인수 조건에 명시, E2E 시나리오로 검증 |
| clamp 확장 누락(생성만 하고 수정 미적용 등) | 격리 우회 | create/update 양쪽 테스트 필수 |
| 문서 0건 KB 선택 시 빈 결과를 버그로 오인 | UX 혼란 | 드롭다운에 문서 수 표시 검토(Design), 안내문 |
| routed 검색과 병용 시 회귀 | 교차검증 신뢰 훼손 | 기존 D4 매핑 테스트 재실행 + kb_id 병용 케이스 추가 |
| 사전 실패 테스트(tests/api 28건 등)와 신규 회귀 혼동 | 검증 오판 | 기준선 메모리 참조, 신규 테스트 격리 실행 |

---

## 6. 완료 기준 (Acceptance)

- [ ] KB 선택한 에이전트 실행 시 해당 KB 문서만 검색 결과에 등장 (Qdrant payload `kb_id` 일치 확인)
- [ ] `kb_id=None` 에이전트(기존 전체)의 검색 결과·설정 화면이 변경 전과 동일
- [ ] 개인 KB 선택 + 공개 범위 요청 → 에이전트 공개범위가 자동 제한되고 UI에 안내 노출 (생성·수정 모두)
- [ ] 백엔드 신규 테스트 전부 통과 + 기존 agent_builder 테스트 무회귀 (사전 실패분 제외)
- [ ] 프론트 `RagConfigPanel`/`useKnowledgeBases` 테스트 통과 (MSW per-file listen 규칙 준수)

---

## 7. 후속 과제

1. **kb-management-ui**: 프론트 KB 목록/생성/문서 업로드 화면 (지식 관리 페이지 개편)
2. **collection-picker-retirement**: 신규 경로 검증 후 컬렉션 선택 UI 제거 + 기존 에이전트 kb_id 이관
3. **kb-orphan-cleanup**: KB 삭제 시 참조 에이전트 처리 + 벡터 정리(knowledge-base-scoping 이월 항목과 병합)
