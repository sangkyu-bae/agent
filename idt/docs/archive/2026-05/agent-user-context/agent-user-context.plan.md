# Agent User Context Planning Document

> **Summary**: 로그인한 사용자의 신원/부서/권한 정보를 Agent 런타임에 주입하여, LLM 프롬프트에는 최소 정보를 노출하고 보안은 Tool/Repository 계층에서 강제하는 구조를 도입한다.
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-05-27
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 Agent 실행 경로(`run_agent`, `general_chat`)는 `user_id` 문자열 하나만 들고 다니며, 이름/직급/부서/권한 정보가 LLM·Tool·Retriever 어디에도 전달되지 않는다. "나의 연차는?" 같은 자연어 질의를 처리할 수 없고, Tool/DB 단계에서 권한 강제도 불가능하다. |
| **Solution** | ① `user_profiles` + permissions 마스터 3종 테이블 신설, ② `AuthContext` ValueObject + ContextVar로 Agent 실행 전 구간 전파, ③ LLM에는 자동 prepend 되는 **최소 정보 블록**(이름·부서·권한 라벨)만 노출, ④ Tool/Repository 시그니처에 `auth_ctx: AuthContext` 명시화하여 실제 권한 검증/필터링은 백엔드가 책임진다. |
| **Function/UX Effect** | 사용자가 "나", "내", "본인"으로 질문해도 Agent가 본인을 식별. 권한 없는 데이터는 LLM이 결정하는 게 아니라 Tool이 검색 결과 자체에서 배제하여 일관된 응답을 제공한다. |
| **Core Value** | "LLM은 의도 해석, 백엔드는 권한 집행" 원칙 확립 → 향후 사내 데이터(연차/공지/HR 등) 도구를 안전하게 추가할 수 있는 **확장 기반** 마련. |

---

## 1. Overview

### 1.1 Purpose

현재 시스템은 "사용자가 누구인가"를 Agent 런타임이 거의 모른다.

| 계층 | 현재 보유 정보 |
|------|-----------|
| FastAPI Router | `User(id, email, role)` — Depends(get_current_user) 결과 |
| UseCase 호출 시 | `viewer_user_id: str` 만 전달 (router에서 풀어서 넘김) |
| LangGraph State | `messages`, `iteration_count`, `token_usage`, ... — user 정보 0 |
| Tool 호출 | `request_id`만 받음, user 정보 0 |
| LLM System Prompt | 고정 문자열, 사용자 정보 동적 주입 메커니즘 0 |
| `RunContext` (이미 존재) | `run_id, user_id, agent_id, callback, step_id` — **관측성 전용** |

이 Plan은 위 빈 슬롯을 **단일 ValueObject `AuthContext`**로 채우고, ContextVar + 명시적 시그니처 **양방향**으로 전파하여,
LLM에는 자연어 친화 텍스트만 노출하고 권한 강제는 백엔드 코드에 두는 구조를 정립한다.

### 1.2 Background

- **사용자 요구사항 원문 핵심**:
  > "권한정보를 LLM에게 알려준다"와 "권한을 LLM이 판단하게 한다"는 다름.
  > LLM: 사용자의 의도를 해석한다. 서버/Tool: 실제 권한을 검증한다. DB/Retriever: 권한에 맞는 데이터만 반환한다.
- **현재 부족한 점**:
  1. `users` 테이블에 **이름이 없음** → "배상규입니다"라고 표시할 데이터 자체가 없음.
  2. 권한 모델이 `role(user/admin)` + 에이전트 `visibility(private/department/public)`로 양분되어 있고, **세부 권한 라벨**(READ_PUBLIC_DOCS 등)이 없음.
  3. `RunContext`는 이미 ContextVar 기반으로 잘 만들어져 있지만 **관측성용 데이터(run_id 등)만** 들고 있음. 비즈니스 컨텍스트는 미포함.
  4. 모든 LLM 호출 경로(agent_builder, general_chat, multi_query 등)가 system_prompt를 **각자 다른 방식**으로 조립 → 공통 prepend 지점이 없음.
- **이미 잘 되어 있는 점**:
  - `Department`/`UserDepartment` (N:M, `is_primary`) 모델 존재 → 부서 정보 활용 즉시 가능.
  - `RunContext` + `ContextVar` 패턴이 자리잡혀 있어 **확장 패턴이 명확**함.
  - Agent visibility 정책(`VisibilityPolicy.can_access`)이 이미 부서 기반 권한 검증을 함 → 일관된 패턴.

### 1.3 Related Documents

- 기존 코드: `src/domain/auth/entities.py` — `User` 엔티티
- 기존 코드: `src/infrastructure/auth/models.py` — `UserModel`
- 기존 코드: `src/interfaces/dependencies/auth.py` — `get_current_user`, `require_role`
- 기존 코드: `src/domain/department/entity.py` — `Department`, `UserDepartment`
- 기존 코드: `src/application/agent_run/context.py` — `RunContext` (ContextVar)
- 기존 코드: `src/application/agent_builder/run_agent_use_case.py` — Agent 실행 진입점
- 기존 코드: `src/application/general_chat/use_case.py` — General Chat 진입점
- 기존 코드: `src/domain/agent_builder/policies.py` — `VisibilityPolicy` (참고 패턴)
- 규칙: `docs/rules/db-session.md`, `docs/rules/logging.md`, `docs/rules/testing.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] `user_profiles` 테이블 신설 (display_name, position, employee_no, joined_at)
- [ ] permissions 마스터 3종 테이블 신설 (`permissions`, `role_permissions`, `user_permissions`)
- [ ] 도메인 ValueObject 신설: `AuthContext`, `PermissionCode`
- [ ] 도메인 Policy: `PermissionResolver` (role + user grants → permission set)
- [ ] `ContextVar[AuthContext]` 신설 + RunContext와의 관계 정리 (별도 ContextVar)
- [ ] FastAPI Dependency: `get_auth_context()` — `get_current_user` 결과를 AuthContext로 변환
- [ ] UseCase 시그니처 확장: `RunAgentUseCase`, `GeneralChatUseCase` 가 `auth_ctx` 받기
- [ ] `_render_user_context_block(ctx)` 헬퍼 — system_prompt 자동 prepend용 텍스트 생성
- [ ] system_prompt 자동 prepend 적용 (agent_builder + general_chat)
- [ ] Tool 시그니처 가이드 + 1개 PoC Tool 적용 (`InternalDocumentSearchTool`) — `auth_ctx` 명시화
- [ ] Repository 메서드에 `viewer_user_id` 기반 필터링 1개 PoC (RAG metadata_filter에 사용자 부서 자동 주입)
- [ ] DB 마이그레이션 파일 4종 (`user_profiles`, `permissions`, `role_permissions`, `user_permissions`)
- [ ] 회원가입 API에 `display_name` 필드 추가 + 응답 스키마 확장
- [ ] 관리자용 Permission 부여 API 1세트 (POST/DELETE `/admin/users/{id}/permissions`)
- [ ] `agent_definitions`에 `include_user_context BOOLEAN DEFAULT TRUE` 확장 슬롯 (향후 opt-out 대비)
- [ ] 모든 신규 모듈 TDD 적용 (테스트 먼저)

### 2.2 Out of Scope

- 프론트엔드 회원가입/관리자 UI 구현 (별도 feature: `admin-user-permissions-ui`)
- 전체 Tool에 대한 권한 강제 일괄 적용 — 본 Plan은 **1개 PoC**(`InternalDocumentSearchTool`)까지만, 나머지 Tool은 후속 feature에서 점진 적용
- 부서 변경 시 자동 Permission 회수/부여 로직 — 명시적 부여만
- JWT payload 확장 (현재 `sub/role/token_type/exp` 그대로 유지 — DB 재조회 비용은 한 번/요청이므로 허용)
- 다중 테넌트(`tenant_id`) — 현재 단일 조직 가정. 컬럼 슬롯만 향후 확장 가능하도록 코멘트 표기
- mobile app, desktop app 영향 — API 응답 호환성만 유지

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `user_profiles` 테이블 신설 (PK=user_id FK, display_name NOT NULL, position, employee_no UNIQUE, joined_at) | High | Pending |
| FR-02 | `permissions` 마스터 테이블 (code PK, description) + 초기 시드 (READ_PUBLIC_DOCS, READ_INTERNAL_NOTICES, USE_RAG_SEARCH, READ_DEPARTMENT_DOCS 등 8~10개) | High | Pending |
| FR-03 | `role_permissions` (role, permission_code) — role 기반 기본 권한 | High | Pending |
| FR-04 | `user_permissions` (user_id, permission_code) — 추가 grant | High | Pending |
| FR-05 | `AuthContext` ValueObject — user_id, display_name, primary_department_id/name, department_ids, role, permissions(frozenset) | High | Pending |
| FR-06 | `PermissionResolver` 도메인 정책 — role + user grants → 최종 permission set 계산 | High | Pending |
| FR-07 | `auth_context: ContextVar[Optional[AuthContext]]` 신설 — RunContext와 독립 (관측성/비즈니스 분리) | High | Pending |
| FR-08 | FastAPI `get_auth_context()` Dependency — `get_current_user` + `user_profile_repo` + `department_repo` + `permission_resolver` 조합 | High | Pending |
| FR-09 | `RunAgentUseCase.execute/stream`이 `auth_ctx: AuthContext` 받고 ContextVar 세팅 | High | Pending |
| FR-10 | `GeneralChatUseCase.execute/stream`이 `auth_ctx: AuthContext` 받고 ContextVar 세팅 | High | Pending |
| FR-11 | `_render_user_context_block(ctx)` 헬퍼 — 표준 한국어 텍스트 생성 (이름/부서/권한 라벨) | High | Pending |
| FR-12 | agent_builder의 supervisor_prompt 앞에 자동 prepend (compile 단계에서) | High | Pending |
| FR-13 | general_chat의 `_SYSTEM_PROMPT` 앞에 자동 prepend (`_create_agent` 단계) | High | Pending |
| FR-14 | `agent_definitions`에 `include_user_context BOOLEAN DEFAULT TRUE` 컬럼 — 향후 opt-out용 슬롯 (FR-12에서 분기) | Medium | Pending |
| FR-15 | `InternalDocumentSearchTool`이 `auth_ctx` 받아 검색 시 `metadata_filter`에 부서 정보 자동 병합 (PoC) | High | Pending |
| FR-16 | `auth_ctx` 누락 시 동작 — 테스트/스크립트 호출 등 ContextVar 미설정 시 graceful fallback (LLM 블록 prepend 생략, Tool은 안전한 디폴트) | Medium | Pending |
| FR-17 | 회원가입 API `POST /api/v1/auth/signup`에 `display_name` 필드 추가 (필수) | High | Pending |
| FR-18 | 관리자 권한 부여 API `POST/DELETE /api/v1/admin/users/{id}/permissions` | Medium | Pending |
| FR-19 | 모든 신규 코드 TDD — 테스트 먼저 작성 후 구현 | High | Pending |
| FR-20 | 기존 회원/에이전트 회귀 없음 (기존 테스트 전수 통과) | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | AuthContext 조립 추가 비용 < 30ms/요청 (DB round-trip 2~3회: profile + departments + permissions) | 로그 타임스탬프, p95 측정 |
| Security | LLM 프롬프트에 `password_hash`, `employee_no` 등 민감 필드 절대 미포함 | `_render_user_context_block` 단위 테스트로 강제 검증 |
| Security | 권한 검증의 **최종 책임은 Tool/Repository 계층** — LLM 응답으로 차단 금지 | 통합 테스트: 권한 없는 사용자가 부서 외 문서 요청 시 검색 결과 자체가 비어야 함 |
| Reliability | AuthContext 누락 시 500 에러 X — 명시된 fallback 동작 | FR-16 단위 테스트 |
| Maintainability | 신규 Tool 추가 시 `auth_ctx` 시그니처 패턴 통일 — 가이드 문서 1쪽 작성 | `docs/rules/auth-context.md` 신설 |
| Layer | domain → application → infrastructure 의존 방향 유지 | 신규 모듈 import 검사 (`verify-architecture` skill) |
| Logging | AuthContext 세팅/리셋 로그 (LOG-001 준수) — user_id만 기록, display_name/permissions는 디버그 레벨 | `verify-logging` skill |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 4종 신규 테이블 마이그레이션 적용 완료 (`V0NN__create_user_profiles.sql` 등)
- [ ] 초기 permission 시드 데이터 10개 이내 적재
- [ ] `AuthContext` ValueObject + ContextVar + Dependency + PermissionResolver 단위 테스트 통과
- [ ] `RunAgentUseCase`/`GeneralChatUseCase` 통합 테스트에서 ContextVar 세팅/리셋 검증
- [ ] LLM 프롬프트 prepend 결과 스냅샷 테스트 (이름/부서/권한 라벨 모두 포함, 민감정보 미포함)
- [ ] `InternalDocumentSearchTool` PoC: 부서 외 문서가 결과에 포함되지 않음 (통합 테스트)
- [ ] 회원가입 API에 display_name 추가 후 기존 가입 흐름 회귀 없음
- [ ] 관리자 권한 부여 API 동작 + 권한 변경 즉시 반영 (다음 요청부터)
- [ ] 기존 테스트 전수 통과 (회귀 0건)
- [ ] `verify-architecture`, `verify-logging`, `verify-tdd` 모두 통과

### 4.2 Quality Criteria

- [ ] 신규 모듈 테스트 커버리지 ≥ 85%
- [ ] mypy strict 통과 (신규 코드)
- [ ] Domain → Infrastructure 직접 의존 0건
- [ ] LLM prepend 블록에 들어가는 필드는 **whitelist 방식** (코드에 명시된 필드만 허용)
- [ ] `auth_ctx` ContextVar는 finally 블록에서 반드시 reset (메모리 누수 방지)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 기존 회원에 `display_name` 없음 — NOT NULL 추가 시 마이그레이션 실패 | High | High | 1단계: nullable로 추가 + 백필 (email local-part 자동 채움). 2단계: 회원가입 API 필수화. 3단계(별도 PR): NOT NULL 전환 |
| 매 요청마다 DB 3회 추가 조회로 지연 증가 | Medium | Medium | (1) 단일 쿼리로 JOIN 묶기, (2) 향후 Redis 캐시(별도 feature) — 본 Plan은 측정만 |
| LLM이 permissions 라벨을 보고 자체 차단 응답 생성 → 사용자 혼란 | Medium | Medium | prepend 블록 문구를 "권한이 없는 정보는 도구가 자동으로 제외합니다. 검색 결과에 없으면 모른다고 답하세요" 형식으로 — 차단 판단을 LLM에 위임하지 않음 |
| Tool 시그니처 변경으로 기존 테스트/외부 호출 깨짐 | High | Medium | (1) 기본값 `auth_ctx=None` 허용, (2) Tool 내부에서 None이면 ContextVar fallback, (3) 둘 다 없으면 안전 디폴트(빈 부서 필터) |
| `agent_definitions.include_user_context` 컬럼 추가 시 ORM 매핑/캐시 미반영 | Low | Medium | 마이그레이션 후 ORM 모델 동시 업데이트, 캐시 무효화 단계 명시 |
| ContextVar 누수 — 비동기 task 종료 시 reset 누락 | Medium | Low | `set_current_auth_context` → Token 반환 → finally `reset` 강제 패턴. RunContext와 동일 패턴 재사용 |
| LLM 프롬프트 길이 증가로 토큰 비용↑ | Low | High | prepend 블록을 짧고 일관된 포맷 (~150~200 토큰 이내)으로 설계, 권한 라벨은 enum 코드 그대로 노출(요약 없음) |
| 권한 회수 후에도 진행 중인 stream에 옛 ctx 잔존 | Low | Medium | AuthContext는 요청 시작 시 조립 후 immutable (frozen dataclass). 다음 요청부터 새 ctx — 명시적으로 받아들임 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| **Starter** | Simple structure | ☐ |
| **Dynamic** | Feature-based modules, BaaS | ☐ |
| **Enterprise** | Strict layer separation, DI | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| **사용자 메타 저장 위치** | users 컬럼 확장 / user_profiles 분리 | **user_profiles 분리** | 인증과 사내 메타(직급/사번)의 책임 분리. users는 인증, profiles는 표시·HR 정보 |
| **권한 모델** | role enum만 / role + permissions 마스터 / 부서별까지 | **role + user 추가 grant** | 마스터 신설 — `role_permissions` 기본 + `user_permissions` 추가. 부서별은 향후 확장 슬롯 |
| **AuthContext 위치** | RunContext에 합치기 / 별도 ContextVar | **별도 ContextVar** | RunContext는 관측성 전용으로 잘 분리되어 있음. 비즈니스 컨텍스트와 책임 혼합 금지 |
| **전파 방식** | 시그니처 명시만 / ContextVar만 / 둘 다 | **둘 다 (Defense in Depth)** | UseCase·Tool 진입점은 명시적 파라미터, 내부 깊은 호출(예: Repository)은 ContextVar fallback. 누락 검출↑ |
| **프롬프트 주입 시점** | UseCase에서 messages 조립 시 / compile 단계에서 system_prompt 가공 | **compile 단계** | agent_builder는 supervisor_prompt가 워크플로우에 박혀 있어 compile 단계가 자연스럽다. general_chat은 `_create_agent`에서 prompt 인자에 prepend |
| **opt-out 방식** | 코드 분기 / agent_definitions 컬럼 | **컬럼 슬롯만 미리 추가** | 본 PR은 전역 자동 (DEFAULT TRUE). 컬럼은 미리 만들어 향후 변경 비용 최소화 |
| **LLM 노출 필드** | 전체 / whitelist | **whitelist** | `display_name, primary_department_name, role, permissions_labels` 만. employee_no/email/password_hash 등 절대 금지 |
| **권한 위치** | LLM 차단 / Tool 차단 / Retriever 차단 | **Tool + Retriever 이중 방어** | LLM은 안내 멘트만, Tool 진입에서 1차, Repository where절에서 2차 — 사용자 요구의 "좋은 구조" 따름 |
| **DB 마이그레이션 도구** | Alembic / Flyway 형식 SQL | **현재 프로젝트 패턴 유지** | `db/migration/` 폴더의 기존 V001~ 패턴 그대로 (db-migration skill 활용) |

### 6.3 Clean Architecture Approach

```
Enterprise (Thin DDD):

src/
├── domain/
│   ├── auth/                          # 기존 - 확장
│   │   ├── entities.py                # User (변경 없음 - 인증 전용 유지)
│   │   └── value_objects.py           # (변경 없음)
│   ├── user_profile/                  # ★ 신규
│   │   ├── entity.py                  # UserProfile (display_name, position, employee_no, joined_at)
│   │   └── interfaces.py              # UserProfileRepositoryInterface
│   ├── permission/                    # ★ 신규
│   │   ├── value_objects.py           # PermissionCode (Enum), Permission
│   │   ├── entity.py                  # RolePermission, UserPermission
│   │   ├── interfaces.py              # PermissionRepositoryInterface
│   │   └── resolver.py                # PermissionResolver (role + user grants → frozenset)
│   └── agent_run/                     # 기존 - 확장
│       └── auth_context.py            # ★ AuthContext ValueObject (frozen dataclass)
│
├── application/
│   ├── agent_run/
│   │   ├── context.py                 # 기존 RunContext (변경 최소)
│   │   └── auth_context.py            # ★ ContextVar + helpers (set/reset/get)
│   ├── user_profile/
│   │   └── use_cases.py               # GetUserProfile, UpdateUserProfile
│   ├── permission/
│   │   ├── assemble_auth_context.py   # ★ AssembleAuthContextUseCase (user → AuthContext 조립)
│   │   └── grant_revoke.py            # 관리자용 권한 부여/회수 UseCase
│   ├── agent_builder/
│   │   ├── run_agent_use_case.py      # ★ auth_ctx 파라미터 추가 + ContextVar 세팅
│   │   └── workflow_compiler.py       # ★ supervisor_prompt prepend
│   └── general_chat/
│       └── use_case.py                # ★ auth_ctx 파라미터 추가 + ContextVar 세팅
│
├── infrastructure/
│   ├── user_profile/
│   │   ├── models.py                  # UserProfileModel
│   │   └── repository.py
│   └── permission/
│       ├── models.py                  # PermissionModel, RolePermissionModel, UserPermissionModel
│       └── repository.py
│
└── interfaces/
    ├── dependencies/
    │   └── auth.py                    # ★ get_auth_context() Dependency 추가
    └── (api/routes/auth_router.py)    # ★ 회원가입 schema에 display_name 추가
        (api/routes/admin_user_router.py) # ★ 권한 부여/회수 엔드포인트
```

### 6.4 AuthContext 구조

```python
# src/domain/agent_run/auth_context.py
from dataclasses import dataclass
from typing import FrozenSet

@dataclass(frozen=True)
class AuthContext:
    """Agent 런타임 사용자 컨텍스트.

    - immutable (frozen) — 요청 시작 시 조립 후 변경 금지.
    - LLM 노출 시에는 `_render_user_context_block`을 거쳐 whitelist 필드만 노출.
    - 권한 검증의 단일 진실 공급원 (Single Source of Truth).
    """
    user_id: int
    display_name: str
    role: str                              # "user" | "admin"
    primary_department_id: str | None      # 대표 부서 (UserDepartment.is_primary=True)
    primary_department_name: str | None
    department_ids: tuple[str, ...]        # 사용자가 속한 모든 부서 (immutable)
    permissions: frozenset[str]            # 최종 권한 코드 집합 (role + user grants)
    # 향후 확장 슬롯 (현재 None)
    tenant_id: str | None = None
```

### 6.5 LLM 노출 텍스트 포맷 (whitelist)

```text
[현재 사용자 정보]
- 이름: 배상규
- 부서: DX팀
- 역할: 일반 사용자

사용자가 "나", "내", "본인"이라고 말하면 위 사용자를 의미합니다.

[허용된 정보 영역]
- 사내 공개 문서 조회
- 부서 내부 공지 조회
- RAG 문서 검색

⚠️ 권한이 없는 정보는 도구가 자동으로 제외합니다.
도구의 검색 결과에 없는 내용은 "확인되지 않습니다"라고 답하세요.
권한 여부를 직접 판단해서 차단하지 말고, 검색된 사실만 답변하세요.
```

### 6.6 ContextVar 관계도

```
[FastAPI Request]
    │
    ▼ Depends(get_auth_context)
    │  → User + UserProfile + Departments + Permissions 조회 → AuthContext 조립
    │
    ▼ Router → UseCase.execute(auth_ctx=...)
    │
    ▼ set_current_auth_context(auth_ctx) → Token
    │                                              │
    │   ┌──────────────────────────────────────────┘
    │   │
    │   ▼
    │ [ContextVar: _current_auth_context]
    │   │
    │   ├─→ WorkflowCompiler.compile()   ─→ supervisor_prompt prepend
    │   ├─→ LangGraph node 실행 중 Tool   ─→ get_current_auth_context() fallback
    │   └─→ Repository (RAG metadata_filter) ─→ 부서 필터 자동 주입
    │
    ▼ finally: reset_current_auth_context(token)


[RunContext] — 별도 ContextVar, 관측성 전용 (변경 없음)
    └─→ run_id, agent_id, step_id, callback ...
```

### 6.7 Tool 시그니처 가이드

```python
# 권장 패턴 (Defense in Depth)
class SomeTool(BaseTool):
    auth_ctx: AuthContext | None = None  # ★ 1차: 명시적 (생성 시 ToolFactory가 주입)

    async def _arun(self, query: str) -> str:
        ctx = self.auth_ctx or get_current_auth_context()  # 2차: ContextVar fallback
        if ctx is None:
            # 3차: 안전 디폴트 — 공용 데이터만 노출, 부서/개인 데이터 차단
            ctx = AuthContext.public_anonymous()

        # ★ 실제 권한 검증은 여기 (LLM이 아니라!)
        if PermissionCode.READ_DEPARTMENT_DOCS.value not in ctx.permissions:
            metadata_filter["department_id"] = "PUBLIC_ONLY"

        # 또는 repository 호출 시 viewer로 명시 전달
        result = await self.use_case.execute(
            request,
            request_id=self.request_id,
            viewer=ctx,  # ★ Repository 이하 계층까지 전파
        )
        return result
```

### 6.8 데이터 모델 (마이그레이션)

```sql
-- V0NN__create_user_profiles.sql
CREATE TABLE user_profiles (
    user_id BIGINT PRIMARY KEY,
    display_name VARCHAR(100) NOT NULL,            -- 1단계: NULL 허용 후 백필 → 2단계 NOT NULL
    position VARCHAR(50) NULL,                     -- 직급 (대리, 과장 등)
    employee_no VARCHAR(50) NULL UNIQUE,           -- 사번
    joined_at DATE NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_user_profiles_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- V0NN+1__create_permissions.sql
CREATE TABLE permissions (
    code VARCHAR(64) PRIMARY KEY,                  -- READ_PUBLIC_DOCS, USE_RAG_SEARCH 등
    description VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- V0NN+2__create_role_permissions.sql
CREATE TABLE role_permissions (
    role VARCHAR(20) NOT NULL,                     -- user / admin
    permission_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (role, permission_code),
    CONSTRAINT fk_role_perm FOREIGN KEY (permission_code) REFERENCES permissions(code) ON DELETE CASCADE
);

-- V0NN+3__create_user_permissions.sql
CREATE TABLE user_permissions (
    user_id BIGINT NOT NULL,
    permission_code VARCHAR(64) NOT NULL,
    granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    granted_by BIGINT NULL,                        -- 부여한 admin user_id
    PRIMARY KEY (user_id, permission_code),
    CONSTRAINT fk_user_perm_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_perm_code FOREIGN KEY (permission_code) REFERENCES permissions(code) ON DELETE CASCADE
);

-- V0NN+4__alter_agent_definitions_add_include_user_context.sql
ALTER TABLE agent_definitions
    ADD COLUMN include_user_context BOOLEAN NOT NULL DEFAULT TRUE;

-- V0NN+5__seed_permissions.sql
INSERT INTO permissions (code, description) VALUES
    ('READ_PUBLIC_DOCS',        '사내 공개 문서 조회'),
    ('READ_INTERNAL_NOTICES',   '내부 공지 조회'),
    ('READ_DEPARTMENT_DOCS',    '소속 부서 문서 조회'),
    ('USE_RAG_SEARCH',          'RAG 검색 도구 사용'),
    ('USE_WEB_SEARCH',          '웹 검색 도구 사용'),
    ('CREATE_AGENT',            '에이전트 생성'),
    ('MANAGE_USERS',            '사용자 관리 (관리자)'),
    ('MANAGE_PERMISSIONS',      '권한 관리 (관리자)');

INSERT INTO role_permissions (role, permission_code) VALUES
    ('user',  'READ_PUBLIC_DOCS'),
    ('user',  'READ_INTERNAL_NOTICES'),
    ('user',  'READ_DEPARTMENT_DOCS'),
    ('user',  'USE_RAG_SEARCH'),
    ('user',  'USE_WEB_SEARCH'),
    ('user',  'CREATE_AGENT'),
    ('admin', 'READ_PUBLIC_DOCS'),
    ('admin', 'READ_INTERNAL_NOTICES'),
    ('admin', 'READ_DEPARTMENT_DOCS'),
    ('admin', 'USE_RAG_SEARCH'),
    ('admin', 'USE_WEB_SEARCH'),
    ('admin', 'CREATE_AGENT'),
    ('admin', 'MANAGE_USERS'),
    ('admin', 'MANAGE_PERMISSIONS');
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `CLAUDE.md` Thin DDD 레이어 분리 명시
- [x] `docs/rules/db-session.md` 단일 세션 트랜잭션 규칙
- [x] `docs/rules/logging.md` LOG-001 구조화 로깅
- [x] `docs/rules/testing.md` TDD 사이클
- [x] `RunContext` + ContextVar 패턴 선례 존재

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **AuthContext 사용 규칙** | 없음 | `docs/rules/auth-context.md` 신설 — Tool/Repository 시그니처 패턴, ContextVar 사용 시점 | High |
| **Permission 코드 명명** | 없음 | UPPER_SNAKE, ACTION_RESOURCE 패턴 (READ_DOCS, MANAGE_USERS) | High |
| **LLM 노출 필드 whitelist** | 없음 | `_render_user_context_block` 단위 테스트로 강제 (snapshot) | High |
| **회원가입 display_name 처리** | 없음 | 기존 회원은 email local-part로 자동 백필 | Medium |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (추가 없음) | 기존 환경변수만 사용 | - | - |

---

## 8. Implementation Order

### Phase 1: Domain Layer (TDD 1)
1. `src/domain/permission/value_objects.py` — PermissionCode Enum, Permission VO
2. `src/domain/permission/entity.py` — RolePermission, UserPermission
3. `src/domain/permission/interfaces.py` — PermissionRepositoryInterface
4. `src/domain/permission/resolver.py` — PermissionResolver (role + grants → frozenset)
5. `src/domain/user_profile/entity.py` — UserProfile
6. `src/domain/user_profile/interfaces.py` — UserProfileRepositoryInterface
7. `src/domain/agent_run/auth_context.py` — AuthContext frozen dataclass + `public_anonymous()`

### Phase 2: Infrastructure Layer (TDD 2)
8. DB 마이그레이션 4종 + 시드 (db-migration skill 활용)
9. `src/infrastructure/user_profile/models.py` + `repository.py`
10. `src/infrastructure/permission/models.py` + `repository.py`

### Phase 3: Application Layer (TDD 3)
11. `src/application/agent_run/auth_context.py` — ContextVar + set/reset/get helpers
12. `src/application/permission/assemble_auth_context.py` — AssembleAuthContextUseCase
13. `src/application/user_profile/use_cases.py` — Get/Update profile
14. `src/application/permission/grant_revoke.py` — 관리자 권한 부여/회수

### Phase 4: Prompt Rendering & UseCase 통합 (TDD 4 — 핵심)
15. `src/application/agent_run/prompt_rendering.py` — `_render_user_context_block(ctx) -> str` (whitelist 강제, snapshot 테스트)
16. `src/application/agent_builder/workflow_compiler.py` 수정 — supervisor_prompt prepend (include_user_context flag 분기)
17. `src/application/agent_builder/run_agent_use_case.py` 수정 — `auth_ctx` 파라미터 + ContextVar 세팅/리셋
18. `src/application/general_chat/use_case.py` 수정 — `auth_ctx` 파라미터 + ContextVar 세팅/리셋 + `_create_agent` prepend

### Phase 5: Tool Layer PoC (TDD 5)
19. `src/infrastructure/agent_builder/tool_factory.py` 수정 — Tool 생성 시 `auth_ctx` 주입
20. `src/application/rag_agent/tools.py` 수정 — `InternalDocumentSearchTool` `auth_ctx` 필드 + metadata_filter 부서 자동 주입
21. 통합 테스트: 부서 외 문서 차단 검증

### Phase 6: API & Dependency (TDD 6)
22. `src/interfaces/dependencies/auth.py` — `get_auth_context()` Dependency 추가
23. `src/api/routes/auth_router.py` — 회원가입 schema에 display_name 추가
24. `src/api/routes/admin_user_router.py` (신규) — 권한 부여/회수 API
25. `src/api/main.py` — DI wiring 업데이트

### Phase 7: Migration & 회귀 검증
26. 기존 users 백필 스크립트 (email local-part → display_name)
27. 전체 테스트 회귀 검증 + verify-architecture / verify-logging / verify-tdd skill 실행

---

## 9. Open Questions (Design 단계에서 확정)

Plan 단계에서 결론을 내리지 않고 Design 문서에서 다룰 항목:

1. **PermissionResolver 캐싱 전략**: 매 요청 DB 3회 vs 메모리/Redis 캐시 — 측정 후 결정
2. **부서별 권한** (`department_permissions`): 본 Plan에서는 슬롯만, 실제 적용은 후속
3. **opt-out 기본값**: `agent_definitions.include_user_context DEFAULT TRUE` 가 맞는지, 일부 시스템 에이전트는 FALSE가 필요한지
4. **PermissionCode Enum의 위치**: domain 폴더 1개로 통합 vs 도구별 분산 — 통합 권장
5. **WebSocket/SSE 경로의 ContextVar 전파**: SSE 스트리밍 중간에 권한 변경 시 어떻게 — 본 Plan은 "요청 시작 시 스냅샷" 채택, 명시 필요

---

## 10. Next Steps

1. [ ] 본 Plan 리뷰 및 확정
2. [ ] Design 문서 작성 (`/pdca design agent-user-context`) — Open Questions 결론, 상세 ER 다이어그램, 시퀀스 다이어그램, 테스트 케이스 목록
3. [ ] TDD 사이클로 Phase 1부터 구현 시작
4. [ ] (옵션) `/plan-plus` 로 대안 비교를 더 깊게 하고 싶다면 재진행

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-05-27 | Initial draft — RunContext 별도 AuthContext 분리, permissions 마스터 신설, 자동 prepend + Tool 명시화 결정 | 배상규 |
