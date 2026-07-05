# skill-builder Analysis Report

> **Analysis Type**: Gap Analysis (PDCA Check)
>
> **Project**: sangplusbot — idt (FastAPI + LangGraph RAG/Agent)
> **Version**: V033 migration baseline
> **Analyst**: 배상규
> **Date**: 2026-06-25
> **Design Doc**: [skill-builder.design.md](../02-design/features/skill-builder.design.md)
> **Plan Doc**: [skill-builder.plan.md](../01-plan/features/skill-builder.plan.md)

---

## 1. Analysis Overview

### 1.1 Purpose

Design 문서(Plan/Design)와 실제 구현(백엔드 idt/ + 프론트 idt_front/)의 1:1 갭을 검출하여 PDCA Check 단계를 완료한다. Decision Log(D1~D6) 등 합의된 설계 결정은 갭이 아닌 의도된 차이로 처리한다.

### 1.2 Scope

- **Design**: `docs/02-design/features/skill-builder.design.md`
- **Backend Impl**: `idt/db/migration/`, `idt/src/{domain,application,infrastructure,api}/skill_builder/`
- **Frontend Impl**: `idt_front/src/{types,services,hooks,pages,constants}/`
- **Out of Scope (제외)**: 스크립트 실행/샌드박스, 에이전트↔skill 연동, ToolFactory prefix, LLM 자동생성, 다중 리소스/버전, subscribe — 갭 계산 제외

---

## 2. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 97% | ✅ |
| Architecture Compliance | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| **Overall** | **97%** | ✅ |

```
┌─────────────────────────────────────────────────────────┐
│  Overall Match Rate: 97%                                 │
├─────────────────────────────────────────────────────────┤
│  ✅ Match:                63 items (97%)                 │
│  ⚠️ Partial (조직 차이):   2 items (3%)                  │
│  ❌ Not implemented:        0 items (0%)                 │
└─────────────────────────────────────────────────────────┘
```

**산출 근거**: 검증 항목 65개 = V033 컬럼 16 + 엔티티 필드/메서드 18 + API 7 + Policy 규칙 9 + UseCase 6 + 프론트 계약/배선 9. 일치 63, 부분 2(테스트 파일 조직·UI 컴포넌트 분리 미적용), 누락 0. Match Rate = 63/65 = 96.9% → **97%**.

---

## 3. Gap Analysis (Design vs Implementation)

### 3.1 V033 Migration 컬럼 (Design §3.3)

| 컬럼 | Design | Impl (V033) | Status |
|------|--------|-------------|--------|
| id VARCHAR(36) PK | ✅ | ✅ | ✅ |
| user_id VARCHAR(100) NOT NULL + ix_skill_user | ✅ | ✅ | ✅ |
| name VARCHAR(255) NOT NULL | ✅ | ✅ | ✅ |
| description TEXT NOT NULL | ✅ | ✅ | ✅ |
| trigger_text TEXT NULL (예약어 처리) | ✅ | ✅ | ✅ (D-예약어) |
| instruction TEXT NOT NULL | ✅ | ✅ | ✅ |
| script_type VARCHAR(20) DEFAULT 'none' | ✅ | ✅ | ✅ |
| script_content TEXT NULL (저장 전용) | ✅ | ✅ | ✅ |
| status VARCHAR(20) DEFAULT 'active' | ✅ | ✅ | ✅ (D2) |
| visibility ENUM(private/department/public) | ✅ | ✅ | ✅ (D3) |
| department_id VARCHAR(36) NULL | ✅ | ✅ | ✅ |
| forked_from VARCHAR(36) NULL | ✅ | ✅ | ✅ (D6) |
| forked_at DATETIME NULL | ✅ | ✅ | ✅ |
| created_at / updated_at DATETIME NOT NULL | ✅ | ✅ | ✅ |
| FK fk_skill_dept ON DELETE SET NULL | ✅ | ✅ | ✅ |
| INDEX visibility / dept_vis / status | ✅ | ✅ | ✅ |

16/16 일치. Fernet 암호화 미도입(D1) 반영됨.

### 3.2 도메인 엔티티 (Design §3.1)

| 항목 | Design | Impl (`schemas.py`) | Status |
|------|--------|---------------------|--------|
| 15개 필드 (id~updated_at) | ✅ | ✅ | ✅ |
| SkillVisibility enum (3종) | ✅ | ✅ | ✅ |
| SkillScriptType enum (none/python/shell) | ✅ | ✅ | ✅ |
| `__post_init__` department 불변식 | ✅ | ✅ | ✅ |
| `apply_update` 부분수정 + 재검증 | ✅ | ✅ | ✅ |
| `soft_delete` status='deleted' | ✅ | ✅ | ✅ |
| `fork_for` private 강제 + forked_from | ✅ | ✅ | ✅ |

18/18 일치. ORM 모델(`models.py`)의 `trigger` 속성 ↔ `trigger_text` 컬럼 매핑(예약어 처리) 정확 반영.

### 3.3 API 엔드포인트 (Design §4.1)

| Method | Path | Design | Impl (`skill_builder_router.py`) | Status |
|--------|------|--------|----------------------------------|--------|
| POST | `/api/v1/skills` | 201 | `create_skill` 201 | ✅ |
| GET | `/api/v1/skills/my` | 200 | `list_my_skills` | ✅ |
| POST | `/api/v1/skills/list` | 200 (RBAC) | `list_skills` execute_accessible | ✅ |
| GET | `/api/v1/skills/{skill_id}` | 200 | `get_skill` | ✅ |
| PUT | `/api/v1/skills/{skill_id}` | 200 | `update_skill` | ✅ (D5: PUT) |
| DELETE | `/api/v1/skills/{skill_id}` | 204 | `delete_skill` 204 | ✅ |
| POST | `/api/v1/skills/{skill_id}/fork` | 201 | `fork_skill` 201 | ✅ (D6) |

7/7 일치. 라우트 등록 순서(`/my`·`/list` → `/{skill_id}` 앞) 준수. 에러 매핑(§6.1) 모두 구현: 422/404/400/403/401 분기 정확.

### 3.4 Domain Policy (Design §7)

| 규칙 | Design | Impl (`policies.py`) | Status |
|------|--------|----------------------|--------|
| validate_name / instruction / script / visibility | ✅ | ✅ | ✅ |
| script_type='none' + content 충돌 차단 | ✅ | ✅ | ✅ |
| 상수(MAX_*, ALLOWED_*) | ✅ | ✅ | ✅ |
| SkillVisibilityPolicy.can_access (소유/public/dept) | ✅ | ✅ | ✅ |
| can_edit (소유자만) | ✅ | ✅ | ✅ |
| can_delete (소유자 or admin) | ✅ | ✅ | ✅ |
| SkillForkPolicy.can_fork (접근가능 & 비소유) | ✅ | ✅ | ✅ |
| validate_source_status (삭제본 차단) | ✅ | ✅ | ✅ |
| agent 모듈 미import (도메인 격리) | ✅ | ✅ | ✅ |

9/9 일치. 추가로 `validate_description`(Design 미명시)이 구현됨 — Policy 상수 `MAX_DESCRIPTION_LENGTH`를 실제 사용하는 강화 항목(긍정적, 갭 아님).

### 3.5 UseCase (Design §4 / §9)

| UseCase | Design | Impl | Status |
|---------|--------|------|--------|
| CreateSkillUseCase | ✅ | ✅ | ✅ |
| GetSkillUseCase (가시성 접근제어) | ✅ | ✅ | ✅ |
| ListSkillsUseCase (execute_my + execute_accessible) | ✅ | ✅ | ✅ |
| UpdateSkillUseCase (부분수정 + 소유자) | ✅ | ✅ | ✅ |
| DeleteSkillUseCase (soft-delete + RBAC) | ✅ | ✅ | ✅ |
| ForkSkillUseCase (private + forked_from) | ✅ | ✅ | ✅ |

6/6 일치. ListSkillsUseCase의 `DepartmentRepositoryInterface` 주입으로 뷰어 부서 RBAC 적용(§2.3) 반영.

### 3.6 프론트엔드 계약 & 배선 (Design §5)

| 항목 | Design | Impl | Status |
|------|--------|------|--------|
| `types/skill.ts` 계약 미러 | ✅ | ✅ snake_case passthrough | ✅ (합의) |
| `constants/api.ts` SKILLS 상수 | ✅ | ✅ (5종 엔드포인트) | ✅ |
| `services/skillService.ts` (CRUD+fork, PUT) | ✅ | ✅ | ✅ |
| `hooks/useSkills.ts` TanStack Query + 캐시무효화 | ✅ | ✅ | ✅ |
| `AdminSkillsPage/index.tsx` 목록/검색/모달 | ✅ | ✅ | ✅ |
| `constants/adminNav.ts` "Skill 관리" 메뉴 | ✅ | ✅ | ✅ |
| `App.tsx` /admin/skills 라우트 | ✅ | ✅ | ✅ |
| `queryKeys.ts` skills/skill 키 | ✅ | ✅ | ✅ |
| "스크립트 저장 전용" UI 안내문 (§5.1) | ✅ | ✅ (amber 경고) | ✅ |

9/9 기능 일치. snake_case passthrough는 합의된 결정(Design §5.4 주석 — mcpServer.ts 관례). 단, 컴포넌트 분리는 아래 ⚠️ 참조.

---

## 4. 발견된 갭 (심각도 포함)

### 🔵 부분 일치 (조직적 차이, 기능 영향 없음)

| # | 항목 | Design | Implementation | 심각도 | 권장 조치 |
|---|------|--------|----------------|:------:|----------|
| G1 | 프론트 컴포넌트 분리 | §5.3: `SkillListTable.tsx` + `SkillFormModal.tsx` 별도 파일 | `AdminSkillsPage/index.tsx` 단일 파일에 인라인(SkillFormModal은 같은 파일 내 컴포넌트) | 🟢 Low | 기능 동일. 파일이 485줄로 다소 길어 향후 분리 권장. 또는 Design §5.3을 현 구조로 업데이트 |
| G2 | 테스트 파일 구성 | 백엔드 8개·프론트 4개 파일로 세분 | 백엔드: app 테스트가 `test_skill_use_cases.py` 1파일로 통합(6 UseCase 전부 커버) / 프론트: `SkillFormModal.test.tsx` 없이 `index.test.tsx`로 통합 | 🟢 Low | 커버리지는 동등(생성/검증/권한/fork/삭제 케이스 존재). Design Test Plan을 통합 구조로 업데이트 |

### 🟡 추가 구현 (Design X, Impl O — 긍정적)

| 항목 | 위치 | 설명 |
|------|------|------|
| `SkillBuilderPolicy.validate_description` | `domain/skill_builder/policies.py:27` | Design은 name/instruction/script/visibility만 명시. description 길이 검증을 추가로 구현(상수 활용 강화). Create UseCase에서 호출됨 |

> ❌ 누락(Design O, Impl X): **없음**. In-Scope 전 항목 구현 완료.

---

## 5. Clean Architecture / CLAUDE.md 규칙 준수

| 규칙 | 검증 | Status |
|------|------|--------|
| domain → infrastructure 참조 없음 | `domain/skill_builder/*`는 dataclass/ABC만, 외부 무참조. Repository는 Interface 역전 | ✅ |
| domain → agent_builder 미참조 (결합 방지) | `policies.py` 주석 명시 + import 없음 확인 | ✅ |
| router 비즈니스 로직 없음 | `skill_builder_router.py`는 HTTPException 매핑 + user_id 주입만, 로직은 UseCase 위임 | ✅ |
| Repository commit/rollback 호출 없음 | `skill_repository.py` save/update/soft_delete 모두 flush/merge만. base `save()`는 flush+refresh (commit 없음) | ✅ |
| 단일 세션 사용 | DI factory가 `Depends(get_session)`로 repo+dept_repo 동일 세션 주입 | ✅ |
| print() 금지, LoggerInterface + request_id | 전 UseCase·Repository에서 `self._logger.info/error` + request_id 전파 | ✅ |
| 명시적 타입 (dataclass/pydantic/typing) | domain dataclass, DTO pydantic, 전 시그니처 타입힌트 | ✅ |
| 함수 40줄 / if 중첩 2단계 | UseCase.execute 분할, `_apply_scope`/`_validate` 헬퍼 추출로 준수 | ✅ |
| API 계약 동기화 | 백엔드 schemas.py ↔ types/skill.ts 필드 일치(snake_case 합의) | ✅ |
| 레이어 배치 (§9.1) | domain/application/infrastructure/interface + Composition Root(main.py) 정확 배치 | ✅ |

**Architecture Score: 100%** — 위반 0건. DI 배선(`create_skill_builder_factories` + 6개 dependency_overrides + `include_router`) main.py에 완전 연결됨.

---

## 6. Decision Log 준수 확인 (합의된 결정 — 갭 아님)

| ID | 결정 | 구현 반영 |
|----|------|----------|
| D1 | Fernet 암호화 미도입, script_content 평문 TEXT | ✅ cipher 없음, 평문 저장 |
| D2 | soft-delete status='active'/'deleted' | ✅ soft_delete() + status 필터 |
| D3 | visibility ENUM 컬럼 | ✅ SAEnum + DB ENUM |
| D4 | MySQLBaseRepository 상속 + _to_model/_to_entity | ✅ 동형 구현 |
| D5 | PUT 사용 (agent의 PATCH 아님) | ✅ router PUT, service put |
| D6 | subscribe 제외, fork만 | ✅ fork만 구현 |
| 예약어 | trigger → trigger_text | ✅ DB 컬럼명 분리, 파이썬 속성 trigger |
| 프론트 | snake_case passthrough | ✅ types/skill.ts snake_case |

8/8 결정 정확 반영.

---

## 7. Recommended Actions

### 7.1 Immediate

없음 — Critical/High 갭 부재.

### 7.2 Short-term (선택)

| 우선순위 | 항목 | 위치 | 효과 |
|----------|------|------|------|
| 🟢 1 | `AdminSkillsPage/index.tsx`(485줄) → `SkillListTable.tsx`/`SkillFormModal.tsx` 분리 | idt_front | 재사용성·가독성 (Design §5.3 정합) |

### 7.3 Design Document Updates Needed

- [ ] §5.3: 컴포넌트 분리를 현 단일 파일 구조로 갱신하거나, 분리 작업으로 정합
- [ ] §8 Test Plan: 통합된 테스트 파일 구성(`test_skill_use_cases.py`, `index.test.tsx`)으로 갱신
- [ ] §7: `validate_description` 규칙을 Policy 명세에 추가(구현이 설계를 앞섬)

---

## 8. Next Steps

- [x] Gap 분석 완료 (Match Rate 97% ≥ 90%)
- [ ] Design 문서 minor 업데이트 (§5.3 / §8 / §7)
- [ ] 완료 보고서 작성 (`/pdca report skill-builder`)

> Match Rate 97% (≥ 90%) → **[Act] iterate 불필요**. 곧바로 Report 단계 진행 권장. 잔여 갭은 모두 🟢 Low(조직적 차이)이며 기능/아키텍처 영향 없음.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-25 | Initial gap analysis (PDCA Check) | 배상규 |
