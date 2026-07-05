# Plan: skill-builder

> Feature: 재사용 가능한 Skill(지시문 + 실행 스크립트) 생성·관리 (백엔드 CRUD + 관리 UI)
> Created: 2026-06-24
> Status: Plan
> Priority: High
> Related: `agent_builder`(구현됨), `mcp-server-registry`(구현됨, 커밋 3fc23d74)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 에이전트는 만들 수 있지만, 에이전트에 주입할 "재사용 가능한 능력 단위(Skill)"를 저장·관리할 방법이 없다. Claude Code처럼 `agent + skill` 조합으로 확장하려면 먼저 skill을 등록/관리하는 기반이 필요하다. |
| **Solution** | `agent_builder` / `mcp-server-registry`와 동일한 Thin DDD 4계층 구조로 `skill_definition` 도메인을 신설한다. Skill = **지시문(instruction) + 실행 스크립트(script)**를 저장하는 엔티티로 정의하고, 수동 폼 입력 기반 CRUD API + 관리 UI를 제공한다. |
| **Function/UX Effect** | 관리자가 화면에서 Skill을 생성(이름·설명·트리거·지시문·스크립트 입력)·조회·수정·삭제·Fork 할 수 있다. visibility(private/department/public)와 RBAC는 에이전트와 동일하게 적용된다. |
| **Core Value** | 추후 `agent + skill` 결합(Claude Code형 실행)의 **데이터 기반**을 확보한다. 이번 단계는 "저장·관리"까지이며, 스크립트 실제 실행/에이전트 주입은 후속 phase로 분리한다. |

---

## 1. 목적 (Why)

현재 플랫폼은 `agent_definition`(에이전트 빌더)으로 에이전트를 생성하고, `mcp_server_registry`로 외부 MCP 도구를 등록할 수 있다.
그러나 **"에이전트가 특정 상황에서 로드해 쓰는 재사용 능력 단위(Skill)"** 를 정의·저장하는 개념이 코드베이스에 전혀 없다.

최종 목표는 Claude Code처럼 **`agent + skill`** 조합으로 동작하는 것이지만, 이를 위해서는 먼저:

1. Skill을 **등록·관리**할 수 있는 도메인/테이블/API가 있어야 하고
2. 관리자가 화면에서 Skill을 **CRUD** 할 수 있어야 한다.

> **이번 범위는 "Skill 생성·관리"까지다.** 에이전트가 Skill을 참조/주입하거나 스크립트를 실제 실행하는 런타임은 본 plan에 포함하지 않는다(후속 phase).

---

## 2. Skill 정의 (What is a Skill)

사용자 확정 사항 기준:

| 항목 | 결정 | 비고 |
|------|------|------|
| **본질** | 지시문(instruction) + 실행 스크립트(script) | Claude Code SKILL.md 풀버전에 가까움 |
| **생성 방식** | 수동 폼 입력 | LLM 자동 생성 아님 (에이전트와 다름) |
| **소유/공유** | 에이전트와 동일 | visibility(private/department/public) + fork + RBAC |
| **이번 범위** | 백엔드 CRUD + 관리 UI | 에이전트 연동/스크립트 실행 제외 |

### Skill 구성 요소

```
Skill
├── name           : 스킬 이름 (예: "환율 계산기")
├── description    : 스킬 설명
├── trigger        : 언제 이 스킬을 쓰는지 (Claude Code의 description 매칭부 역할, 후속 에이전트 연동 대비)
├── instruction    : 지시문 본문 (SKILL.md 본문 — "이런 상황에 이렇게 하라")
├── script_type    : 스크립트 종류 ('none' | 'python' | 'shell' 등, v1은 'none'/'python')
└── script_content : 실행 스크립트 원문 (저장만, 이번 phase에선 실행하지 않음)
```

> **중요 전제**: `script_content`는 **콘텐츠로 저장만** 한다. 실제 실행 런타임/샌드박스는 본 plan의 Out of Scope이며 후속 phase에서 다룬다. 따라서 이번 단계에서 보안상 코드 실행 위험은 없다(저장된 텍스트일 뿐).

---

## 3. 현재 상태 분석 (As-Is)

### 참고 가능한 기존 인프라

| 구분 | 상태 | 파일/위치 |
|------|------|----------|
| 에이전트 도메인 (소유/visibility/fork 패턴) | ✅ | `src/domain/agent_builder/schemas.py`, `interfaces.py`, `policies.py` |
| 에이전트 CRUD UseCase | ✅ | `src/application/agent_builder/*_use_case.py` |
| 에이전트 Repository + ORM | ✅ | `src/infrastructure/agent_builder/agent_definition_repository.py` |
| MCP 레지스트리 (단순 CRUD 템플릿) | ✅ | `src/domain/mcp_registry/`, `src/application/mcp_registry/`, `src/infrastructure/mcp_registry/` |
| DI 팩토리 패턴 | ✅ | `src/api/main.py` (`create_mcp_registry_factories`, agent 팩토리) |
| RBAC / 권한 | ✅ | `CollectionPermissionRepositoryInterface`, 부서(department) 모델 |
| 최신 마이그레이션 | ✅ | `db/migration/V032__alter_mcp_server_registry_add_secrets.sql` |
| 프론트 관리 UI 패턴 | ✅ | `pages/AdminMcpServersPage/`, `services/mcpServerService.ts`, `hooks/useMcpServers.ts`, `types/mcpServer.ts`, `constants/adminNav.ts` |

### 누락된 부분 (이번에 신설)

| 구분 | 상태 |
|------|------|
| `skill_definition` 테이블 | ❌ 없음 (green-field) |
| skill 도메인/애플리케이션/인프라 레이어 | ❌ 없음 |
| `/api/v1/skills` API | ❌ 없음 |
| 프론트 Skill 관리 페이지/서비스/훅/타입 | ❌ 없음 |

> 코드베이스 전체에 "skill" 개념이 전무하다 (green-field). 단, `agent_builder` 규칙을 엄격히 따라 일관성을 확보한다.

---

## 4. 기능 범위 (Scope)

### In Scope

**A. DB (마이그레이션)**
- [ ] `db/migration/V033__create_skill_definition.sql` — `skill_definition` 테이블 생성

**B. 백엔드 (Thin DDD 4계층)**
- [ ] domain: `SkillDefinition` 엔티티, `SkillVisibility` enum, `SkillScriptType` enum, `SkillRepositoryInterface`, `SkillBuilderPolicy`
- [ ] application: Create / Get / List(my + accessible) / Update / Delete / Fork UseCase + 요청/응답 스키마
- [ ] infrastructure: `SkillDefinitionModel`(ORM), `SkillRepository`
- [ ] interfaces: `skill_builder_router.py` (`/api/v1/skills`)
- [ ] DI: `src/api/main.py`에 `create_skill_builder_factories()` 추가 및 override 연결

**C. 프론트엔드 (관리 UI)**
- [ ] `types/skill.ts` — API 계약 타입
- [ ] `constants/api.ts` — SKILLS 엔드포인트 상수
- [ ] `services/skillService.ts` — API 클라이언트
- [ ] `hooks/useSkills.ts` — TanStack Query 훅
- [ ] `pages/AdminSkillsPage/index.tsx` — 목록 + 생성/수정 폼 + 삭제
- [ ] `constants/adminNav.ts` — 관리자 네비게이션 메뉴 추가
- [ ] 라우팅 등록 (`AdminRoute` 하위)

### Out of Scope (후속 phase)

- ❌ **스크립트 실제 실행 / 샌드박스 런타임** — 이번엔 텍스트 저장만
- ❌ **에이전트 ↔ skill 연동** (에이전트가 skill을 참조/주입/호출하는 로직)
- ❌ ToolFactory의 `skill_*` 프리픽스 처리 / LangGraph 노드 연결
- ❌ LLM 기반 skill 자동 생성 (이번은 수동 폼 입력만)
- ❌ skill 다중 리소스/버전 관리 (단일 instruction + 단일 script로 시작)
- ❌ skill subscribe(구독) — fork만 우선 (에이전트의 subscribe는 후속 검토)

---

## 5. 데이터 모델 설계

### 5.1 `skill_definition` 테이블 (V033)

`agent_definition`의 소유/visibility/fork 컬럼 구조를 그대로 차용한다.

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `id` | VARCHAR(36) PK | UUID |
| `user_id` | VARCHAR(100), INDEX | 소유자 |
| `name` | VARCHAR(255) | 스킬 이름 |
| `description` | TEXT | 스킬 설명 |
| `trigger` | TEXT, NULL | 사용 시점 설명 (후속 에이전트 매칭 대비) |
| `instruction` | TEXT | 지시문 본문 (필수) |
| `script_type` | VARCHAR(20), default 'none' | 'none' \| 'python' \| 'shell' |
| `script_content` | TEXT, NULL | 실행 스크립트 원문 (저장 전용) |
| `status` | VARCHAR(20), default 'active' | soft-delete: 'active' \| 'deleted' (에이전트 방식) |
| `visibility` | VARCHAR(20), default 'private', INDEX | 'private' \| 'department' \| 'public' |
| `department_id` | FK → departments.id, NULL | 부서 공유 시 |
| `forked_from` | VARCHAR(36), NULL | Fork 원본 skill id |
| `forked_at` | DATETIME, NULL | Fork 시각 |
| `created_at` | DATETIME | |
| `updated_at` | DATETIME | |

> 자격증명/비밀값 저장 요구가 없으므로 MCP의 Fernet 암호화는 도입하지 않는다(필요 시 후속). 단순 텍스트 컬럼으로 관리.

### 5.2 도메인 엔티티 (`SkillDefinition`)

`agent_builder/schemas.py`의 dataclass 스타일을 따른다.

```python
@dataclass
class SkillDefinition:
    id: str
    user_id: str
    name: str
    description: str
    instruction: str
    trigger: str | None
    script_type: SkillScriptType   # Enum
    script_content: str | None
    status: str                     # 'active' | 'deleted'
    visibility: SkillVisibility     # Enum
    department_id: str | None
    forked_from: str | None
    forked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def apply_update(self, ...) -> "SkillDefinition": ...   # 부분 수정
    def soft_delete(self) -> None: ...                       # status='deleted'
    def fork_for(self, user_id: str) -> "SkillDefinition": ...
```

---

## 6. 파일 구조

### 신규 생성 — 백엔드

```
idt/
├── db/migration/
│   └── V033__create_skill_definition.sql
└── src/
    ├── domain/skill_builder/
    │   ├── __init__.py
    │   ├── schemas.py          # SkillDefinition, SkillVisibility, SkillScriptType
    │   ├── interfaces.py       # SkillRepositoryInterface
    │   └── policies.py         # SkillBuilderPolicy (validate_name/instruction/script/visibility)
    ├── application/skill_builder/
    │   ├── __init__.py
    │   ├── schemas.py          # Create/Update/Get/List 요청·응답 DTO
    │   ├── create_skill_use_case.py
    │   ├── get_skill_use_case.py
    │   ├── list_skills_use_case.py
    │   ├── update_skill_use_case.py
    │   ├── delete_skill_use_case.py
    │   └── fork_skill_use_case.py
    ├── infrastructure/
    │   ├── persistence/models/skill_builder/
    │   │   ├── __init__.py
    │   │   └── models.py       # SkillDefinitionModel
    │   └── skill_builder/
    │       ├── __init__.py
    │       └── skill_repository.py   # SkillRepository (Interface 구현)
    └── api/routes/
        └── skill_builder_router.py   # /api/v1/skills
```

### 수정 대상 — 백엔드

```
idt/src/api/main.py        # create_skill_builder_factories() 추가 + dependency_overrides 연결
```

### 신규 생성 — 프론트엔드

```
idt_front/src/
├── types/skill.ts
├── services/skillService.ts
├── hooks/useSkills.ts
└── pages/AdminSkillsPage/
    ├── index.tsx
    └── components/
        ├── SkillListTable.tsx
        └── SkillFormModal.tsx
```

### 수정 대상 — 프론트엔드

```
idt_front/src/
├── constants/api.ts        # SKILLS 엔드포인트 상수 추가
├── constants/adminNav.ts   # "Skill 관리" 메뉴 추가
└── (라우터 설정 파일)       # /admin/skills 라우트 등록
```

---

## 7. API 설계 (`/api/v1/skills`)

`agent_builder_router` 패턴을 따른다.

| 엔드포인트 | 메서드 | 요청 | 응답 | UseCase |
|-----------|--------|------|------|---------|
| `/` | POST | `CreateSkillRequest` | `CreateSkillResponse` (201) | CreateSkillUseCase |
| `/{skill_id}` | GET | — | `GetSkillResponse` | GetSkillUseCase |
| `/{skill_id}` | PUT | `UpdateSkillRequest` | `UpdateSkillResponse` | UpdateSkillUseCase |
| `/{skill_id}` | DELETE | — | 204 | DeleteSkillUseCase (soft-delete) |
| `/my` | GET | query: page, size | `ListSkillsResponse` | ListSkillsUseCase(my) |
| `/list` | POST | `ListSkillsRequest` | `ListSkillsResponse` | ListSkillsUseCase(accessible, RBAC) |
| `/{skill_id}/fork` | POST | `ForkSkillRequest` | `ForkSkillResponse` | ForkSkillUseCase |

### API 계약 동기화 (필수)

CLAUDE.md §4-1에 따라 백엔드 스키마 ↔ 프론트 타입을 함께 작성한다.

| 백엔드 (idt/) | 프론트엔드 (idt_front/) |
|---------------|------------------------|
| `application/skill_builder/schemas.py` | `types/skill.ts` |
| `api/routes/skill_builder_router.py` | `services/skillService.ts` + `hooks/useSkills.ts` |
| — | 엔드포인트 상수: `constants/api.ts` |

---

## 8. TDD 계획

> CLAUDE.md §4-4: 테스트 없이 구현 코드 먼저 작성 금지 (Red → Green → Refactor)

### 백엔드 (pytest)

| 테스트 파일 | 대상 |
|------------|------|
| `tests/domain/skill_builder/test_policies.py` | name/instruction/script/visibility 검증 규칙 |
| `tests/domain/skill_builder/test_schemas.py` | apply_update / soft_delete / fork_for 동작 |
| `tests/application/skill_builder/test_create_skill_use_case.py` | 생성 흐름, visibility 클램핑, 검증 실패 |
| `tests/application/skill_builder/test_update_skill_use_case.py` | 부분 수정, 권한 |
| `tests/application/skill_builder/test_list_skills_use_case.py` | my / accessible(RBAC) 분기 |
| `tests/application/skill_builder/test_fork_skill_use_case.py` | fork 시 소유자/원본 추적 |
| `tests/infrastructure/skill_builder/test_skill_repository.py` | save/find/update/soft_delete/list (model↔entity 매핑) |

> ⚠️ 메모리 노트: idt pytest는 Windows 이벤트 루프 teardown으로 교차 실행 시 산발 실패가 있으므로, 신규 테스트는 **격리 실행**으로 검증한다. (사전 실패 tests/api 28건·infra 30건은 신규 회귀로 오인 금지)

### 프론트엔드 (Vitest + RTL + MSW)

| 테스트 파일 | 대상 |
|------------|------|
| `src/__tests__/mocks/handlers.ts` | skills 엔드포인트 MSW 핸들러 추가 |
| `src/hooks/useSkills.test.ts` | 목록/생성/수정/삭제 훅 |
| `src/pages/AdminSkillsPage/index.test.tsx` | 목록 렌더, 폼 제출, 빈/에러 상태 |
| `src/pages/AdminSkillsPage/components/SkillFormModal.test.tsx` | 입력 검증, instruction/script 필드 |

> ⚠️ 메모리 노트: idt_front는 `--pool=threads`로 실행, `npm install`은 `--legacy-peer-deps` 필요. 사전 실패 8건 존재.

---

## 9. CLAUDE.md 규칙 체크

- [ ] domain → infrastructure 참조 없음 (interface로 역전)
- [ ] router에 비즈니스 로직 없음 (UseCase 위임)
- [ ] Repository 내부에서 commit()/rollback() 호출 금지 (flush만, 세션은 DI)
- [ ] 한 UseCase 내 동일 세션 사용 (`Depends(get_session)`)
- [ ] print() 금지, LoggerInterface 사용 + request_id 전파
- [ ] 명시적 타입 (pydantic/dataclass/typing), config 하드코딩 금지
- [ ] 함수 40줄 / if 중첩 2단계 제한
- [ ] TDD: 테스트 먼저
- [ ] API 계약 동기화 (백엔드 스키마 ↔ 프론트 타입)
- [ ] 아키텍처/레이어/스키마 임의 변경 아님 (기존 패턴 차용한 신규 도메인 추가)

---

## 10. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| "실행 스크립트" 저장이 곧 코드 실행으로 오해 | 중 | 본 phase는 **저장 전용**임을 문서·UI에 명시. 실행 런타임은 후속 phase 별도 설계 |
| 에이전트와 동일한 fork/visibility 도입으로 범위 팽창 | 중 | fork는 단순 복제로 한정, subscribe는 제외. RBAC는 기존 권한 인프라 재사용 |
| 후속 에이전트 연동 시 스키마 변경 필요 | 낮 | `trigger`/`script_type` 컬럼을 미리 두어 연동 대비. 연동 로직은 별도 plan |
| Windows pytest 교차 실행 산발 실패 | 낮 | 신규 테스트 격리 실행으로 검증 |
| 마이그레이션 번호 충돌 | 낮 | V032가 최신 → **V033** 사용 확정 |

---

## 11. 완료 기준 (Definition of Done)

- [ ] `V033__create_skill_definition.sql` 적용 가능
- [ ] `/api/v1/skills` CRUD + fork 동작 (생성·조회·수정·삭제·목록·fork)
- [ ] visibility(private/department/public) + RBAC 접근 제어 적용
- [ ] soft-delete 동작 (status='deleted')
- [ ] 백엔드 신규 테스트 통과 (격리 실행)
- [ ] 관리 UI에서 Skill 목록 조회 + 생성 폼 + 수정 + 삭제 동작
- [ ] 프론트 타입/서비스/훅이 백엔드 스키마와 일치 (API 계약 동기화)
- [ ] 프론트 컴포넌트/훅 테스트 통과
- [ ] `script_content`는 저장만 되고 실행되지 않음(전제 준수)

---

## 12. 구현 순서

| 순서 | 작업 | 레이어 |
|------|------|--------|
| 1 | `V033__create_skill_definition.sql` 작성 | DB |
| 2 | domain: schemas / interfaces / policies + 테스트 | 백엔드 domain |
| 3 | infrastructure: ORM model + repository + 테스트 | 백엔드 infra |
| 4 | application: DTO + Create/Get/List/Update/Delete/Fork UseCase + 테스트 | 백엔드 app |
| 5 | interfaces: `skill_builder_router.py` + main.py DI 연결 | 백엔드 interface |
| 6 | 백엔드 통합 검증 (격리 실행) | 백엔드 |
| 7 | 프론트 `types/skill.ts` + `constants/api.ts` (계약 동기화) | 프론트 |
| 8 | `services/skillService.ts` + `hooks/useSkills.ts` + MSW + 테스트 | 프론트 |
| 9 | `AdminSkillsPage`(목록/폼/삭제) + adminNav + 라우트 + 테스트 | 프론트 |
| 10 | 브라우저 통합 확인 (dev 서버) | 풀스택 |

---

## 13. 다음 단계

1. [ ] 본 plan 검토·확정
2. [ ] Design 문서 작성 (`/pdca design skill-builder`) — 엔티티 필드·정책·API 스키마 상세화
3. [ ] 구현 시작 (TDD, 위 구현 순서)
4. [ ] (후속 plan) `agent + skill` 연동 — 에이전트가 skill을 참조/주입, 스크립트 실행 런타임 설계
