# PDCA Completion Report: agent-collection-visibility-sync

> Feature: 에이전트 생성 시 컬렉션 scope 기반 visibility 자동 상속
> Completed: 2026-04-26
> Match Rate: **93%** (13/14)
> PDCA Iterations: 1

---

## 1. Executive Summary

에이전트의 `visibility`가 참조하는 컬렉션의 `scope`보다 넓을 수 없도록 **생성/수정 시점에 자동 상속 규칙을 적용**하는 기능을 구현했다. 백엔드는 설계 대비 100% 완성, 프론트엔드는 API 통합 의존 toast 1건을 제외하고 완성되어 전체 Match Rate 93%를 달성했다.

### 핵심 성과

- 에이전트 생성 시 컬렉션 scope 기반 visibility **자동 clamp** 적용
- 에이전트 수정 시 scope 초과 visibility 변경 **명시적 거부**
- 컬렉션 목록 API에 **사용자 권한 필터 + scope 정보** 추가
- 프론트엔드 컬렉션 선택 UI에 **scope 뱃지 및 안내문** 표시

---

## 2. Problem → Solution 매핑

| 문제 (Plan) | 해결 (Do) |
|------------|----------|
| PUBLIC 에이전트 + PERSONAL 컬렉션 → RAG 접근 거부 | `CreateAgentUseCase`에서 `clamp_visibility()` 자동 적용 |
| 에이전트 수정 시 scope 불일치 가능 | `UpdateAgentUseCase`에서 scope 초과 시 `ValueError` |
| 컬렉션 목록이 권한 무관하게 전체 반환 | `rag_tool_router`에 `get_accessible_collection_names()` 필터 추가 |
| UI에서 컬렉션 scope 정보 없이 선택 | `RagConfigPanel`에 scope 뱃지 + 제한 안내문 |

---

## 3. 구현 상세

### 3.1 Domain Layer — `VisibilityPolicy` 확장

**파일**: `src/domain/agent_builder/policies.py`

```
SCOPE_TO_VISIBILITY: PERSONAL→private, DEPARTMENT→department, PUBLIC→public
VISIBILITY_RANK: private(0) < department(1) < public(2)

max_visibility_for_scopes(scopes) → 가장 제한적인 scope를 visibility로 변환
clamp_visibility(requested, scopes) → requested가 max 초과 시 max로 조정
```

- 순수 도메인 로직, 외부 의존성 없음
- `Visibility` Enum 추가 (기존 문자열 상수 → 타입 안전)

### 3.2 Application Layer — UseCase 변경

**CreateAgentUseCase** (`create_agent_use_case.py`)
- DI에 `CollectionPermissionRepositoryInterface` 추가
- Step 2.5: `_resolve_visibility()` → 컬렉션 scope 조회 → `clamp_visibility()` 적용
- 자동 조정 시 `visibility_clamped=True`, `max_visibility` 응답에 포함
- RAG 도구 미사용 에이전트는 제한 없이 요청값 그대로 사용

**UpdateAgentUseCase** (`update_agent_use_case.py`)
- DI에 `CollectionPermissionRepositoryInterface` 추가
- visibility 변경 요청 시에만 scope 검증 수행
- 초과 시 `ValueError` (생성=자동조정, 수정=명시적 거부 — 설계 의도)

**Schemas** (`schemas.py`)
- `CreateAgentResponse`에 `visibility_clamped: bool`, `max_visibility: str | None` 추가

### 3.3 Infrastructure Layer — rag_tool_router

**파일**: `src/api/routes/rag_tool_router.py`

- `CollectionInfo`에 `scope: str | None` 필드 추가
- `list_collections`에 `get_current_user`, `get_collection_permission_service` DI 추가
- admin은 전체, 일반 사용자는 `get_accessible_collection_names()`로 필터
- 각 컬렉션별 `find_permission()` → scope 포함

### 3.4 DI 연결 — main.py

- `CreateAgentUseCase` → `perm_repo` (CollectionPermissionRepository)
- `UpdateAgentUseCase` → `perm_repo` (CollectionPermissionRepository)
- `rag_tool_router` → `perm_service` (CollectionPermissionService)

### 3.5 Frontend 변경

**타입** (`idt_front/src/types/ragToolConfig.ts`)
- `CollectionScope` 타입 추가: `'PERSONAL' | 'DEPARTMENT' | 'PUBLIC'`
- `CollectionInfo.scope?: CollectionScope` 추가

**RagConfigPanel** (`idt_front/src/components/agent-builder/RagConfigPanel.tsx`)
- `SCOPE_LABELS` 매핑: PERSONAL→보라색, DEPARTMENT→파란색, PUBLIC→초록색
- 컬렉션 드롭다운 옵션에 `[개인]`/`[부서]`/`[공개]` 뱃지 표시
- 비PUBLIC 컬렉션 선택 시 인라인 안내문 표시

**MSW Handler** (`idt_front/src/__tests__/mocks/handlers.ts`)
- 컬렉션 mock 데이터에 `scope` 필드 추가 (API 계약 동기화)

---

## 4. 테스트 현황

### 4.1 Backend — 54 tests PASSED

| 테스트 파일 | 건수 | 커버리지 |
|-----------|:----:|---------|
| `test_visibility_policy.py` | 17 | can_access/edit/delete + max_visibility_for_scopes(8) + clamp_visibility(8) |
| `test_create_agent_use_case.py` | 11 | 기본 생성(6) + visibility clamping(5) |
| `test_update_agent_use_case.py` | 8 | 기본 수정(5) + scope 검증(3) |
| `test_rag_tool_router.py` | 8 | 컬렉션 목록(3) + 메타데이터(3) + scope/필터(2) |
| **소계** | **44** | feature 관련 |

### 4.2 Frontend — 10 tests PASSED

| 테스트 파일 | 건수 | 커버리지 |
|-----------|:----:|---------|
| `useRagToolConfig.test.ts` | 5 | hook 동작 검증 |
| `RagConfigPanel.test.tsx` | 5 | scope 뱃지 렌더링 + 안내문 표시/미표시 |

### 4.3 전체 테스트 결과

```
Backend:  54 passed / 0 failed (3.21s)
Frontend: 10 passed / 0 failed (3.46s)
Total:    64 passed / 0 failed
```

---

## 5. API 계약 변경 (하위 호환)

### GET /api/v1/rag-tools/collections

| 변경 | 내용 |
|------|------|
| 추가 | `scope` 필드 (nullable) |
| 변경 | 권한 필터 적용 (비인가 컬렉션 제외) |
| 호환 | 기존 필드 유지, scope는 optional |

### POST /api/v1/agents (CreateAgent)

| 변경 | 내용 |
|------|------|
| 추가 | 응답에 `visibility_clamped`, `max_visibility` 필드 |
| 동작 | visibility가 scope 상한 초과 시 자동 clamp |
| 호환 | Request 변경 없음, 기존 필드 유지 |

### PATCH /api/v1/agents/{id} (UpdateAgent)

| 변경 | 내용 |
|------|------|
| 동작 | visibility가 scope 상한 초과 시 400 에러 |
| 호환 | visibility 미변경 시 기존 동작 유지 |

---

## 6. 아키텍처 준수

| CLAUDE.md 규칙 | 상태 | 근거 |
|---------------|:----:|------|
| domain → infrastructure 참조 금지 | ✅ | VisibilityPolicy는 순수 문자열 처리 |
| router에 비즈니스 로직 금지 | ✅ | rag_tool_router는 perm_service 호출만 |
| TDD 필수 (RED→GREEN→REFACTOR) | ✅ | 모든 구현 코드에 테스트 선행 |
| 함수 40줄 미만 | ✅ | 최대 메서드 14줄 (_resolve_visibility) |
| API 계약 동기화 | ✅ | BE/FE CollectionInfo.scope 동시 반영 |
| Repository 내 commit/rollback 금지 | ✅ | 조회만 수행 |
| print() 금지 | ✅ | logger 패턴 유지 |
| config 하드코딩 금지 | ✅ | SCOPE_TO_VISIBILITY 상수 사용 |

---

## 7. PDCA 사이클 요약

| Phase | 상태 | 산출물 |
|-------|:----:|--------|
| **Plan** | ✅ | `docs/01-plan/features/agent-collection-visibility-sync.plan.md` |
| **Design** | ✅ | `docs/02-design/features/agent-collection-visibility-sync.design.md` |
| **Do** | ✅ | 14개 파일 수정/생성 (BE 10 + FE 4) |
| **Check** | ✅ | 초기 86% → Act-1 후 93% |
| **Act** | ✅ | 1회 iteration (RagConfigPanel 테스트 + MSW handler scope 추가) |
| **Report** | ✅ | 이 문서 |

### PDCA 효율

| 메트릭 | 값 |
|--------|-----|
| 총 iteration 횟수 | 1 |
| 초기 Match Rate | 86% |
| 최종 Match Rate | 93% |
| 잔여 Gap | 1건 (API 통합 의존) |
| 아키텍처 위반 | 0건 |
| 총 테스트 | 64개 (54 BE + 10 FE) |

---

## 8. 변경 파일 전체 목록

### Backend (idt/)

| 파일 | 변경 유형 |
|------|:--------:|
| `src/domain/agent_builder/policies.py` | 수정 |
| `src/application/agent_builder/create_agent_use_case.py` | 수정 |
| `src/application/agent_builder/update_agent_use_case.py` | 수정 |
| `src/application/agent_builder/schemas.py` | 수정 |
| `src/api/routes/rag_tool_router.py` | 수정 |
| `src/api/main.py` | 수정 |
| `tests/domain/agent_builder/test_visibility_policy.py` | 수정 |
| `tests/application/agent_builder/test_create_agent_use_case.py` | 수정 |
| `tests/application/agent_builder/test_update_agent_use_case.py` | 수정 |
| `tests/api/test_rag_tool_router.py` | 수정 |

### Frontend (idt_front/)

| 파일 | 변경 유형 |
|------|:--------:|
| `src/types/ragToolConfig.ts` | 수정 |
| `src/components/agent-builder/RagConfigPanel.tsx` | 수정 |
| `src/components/agent-builder/RagConfigPanel.test.tsx` | **신규** |
| `src/__tests__/mocks/handlers.ts` | 수정 |

---

## 9. 잔여 항목 및 향후 과제

| 항목 | 우선순위 | 의존성 |
|------|:--------:|--------|
| AgentBuilderPage `visibility_clamped` toast | P3 | AgentBuilderPage API 통합 |
| 기존 에이전트 scope 불일치 마이그레이션 | P4 | 운영 데이터 조사 |
| 컬렉션 scope 변경 시 에이전트 visibility 연쇄 업데이트 | P5 | 이벤트 시스템 설계 |

---

## 10. 결론

`agent-collection-visibility-sync` 기능이 PDCA 사이클을 완주했다.
핵심 도메인 규칙(visibility ≤ collection scope)이 백엔드에서 완전히 적용되며,
프론트엔드 컬렉션 선택 UI에서도 scope 기반 안내가 제공된다.
64개 테스트가 전체 통과하며 아키텍처 위반 없이 설계 대비 93% 일치를 달성했다.
