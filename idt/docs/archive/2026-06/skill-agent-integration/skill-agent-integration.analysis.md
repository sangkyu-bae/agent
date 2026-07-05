# skill-agent-integration — Gap Analysis (PDCA Check)

> **Feature**: skill-agent-integration (Phase A)
> **Date**: 2026-06-27
> **Analyzer**: bkit:gap-detector
> **Design**: [skill-agent-integration.design.md](../02-design/features/skill-agent-integration.design.md)
> **Plan**: [skill-agent-integration.plan.md](../01-plan/features/skill-agent-integration.plan.md)

---

## Overall Match Rate: **97%** ✅

90% 임계값을 충분히 상회 → **Report 단계 진행, iterate 불필요**.

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match (function/contract) | 98% | ✅ |
| Architecture Compliance (Thin DDD / 의존성 규칙) | 100% | ✅ |
| Convention Compliance (naming/layer/contract sync) | 95% | ✅ |

누락 기능 없음. 모든 Phase A 요구사항이 구현·테스트됨. 3% 갭은 전부 **문서-코드 표기 차이**이며 기능 결함이 아니다.

---

## Requirement Matrix

| Area | Status | Evidence | Note |
|------|:--:|----------|------|
| V034 migration (cols, FK CASCADE×2, uq_agent_skill, indexes) | ✅ | `db/migration/V034__create_agent_skill.sql:4-16` | §3.3와 일치 |
| ORM `AgentSkillModel` | ✅ | `infrastructure/persistence/models/agent_skill/models.py:10-17` | |
| `AgentSkillLink` frozen VO | ✅ | `domain/agent_skill/schemas.py:6-17` | |
| `SkillAttachPolicy` (MAX=3, dup, max) | ✅ | `domain/agent_skill/policies.py:9-23` | |
| `SkillInjectionPolicy.merge` (order/sep/header/40k guard/blank-skip/0=base) | ✅ | `domain/agent_skill/policies.py:35-65` | §7 정확 일치 |
| Repo interface (4 methods) | ✅ | `domain/agent_skill/interfaces.py:13-37` | |
| Repo attach/detach(idempotent)/list_links/list_attached_skills(JOIN, status='active', sort_order) | ✅ | `infrastructure/agent_skill/agent_skill_repository.py:47-97` | commit/rollback 없음; skill `_to_entity` 재사용 |
| Attach UC (404/403/404/403/409 + sort_order=len) | ✅ | `application/agent_skill/attach_skill_use_case.py:54-99` | 두 도메인 정책을 app 계층에서 조합 |
| Detach UC (404/403/idempotent) | ✅ | `application/agent_skill/detach_skill_use_case.py:31-37` | |
| List UC (404/403/max_attachable) | ✅ | `application/agent_skill/list_attached_skills_use_case.py:39-66` | |
| DTOs (§4.2) + `has_script` derive | ✅ | `application/agent_skill/schemas.py:7-40` | |
| **Injection D3**: app-layer merge, compiler untouched, 0=unchanged, repo optional | ✅ | `application/agent_builder/run_agent_use_case.py:17,454-455,485-512` | `dataclasses.replace`; user_context 최외곽 유지 |
| API 3 endpoints + 200/201/204 + 403/404/409/422 mapping + DI overrides | ✅ | `api/routes/agent_builder_router.py:599-684`; `api/main.py:2398-2445,2836-2841` | |
| run_uc factory `agent_skill_repo` wiring (same session) | ✅ | `api/main.py:1923-1924,1971-1972` | |
| Frontend types/service/hooks/constants/queryKeys/panel/page-mount/MSW | ✅ | `idt_front/src/{types,services,hooks,components,constants,lib,pages,__tests__}` | 패널: max-3 비활성 + "⚠ script 미실행" |
| Security: script never executed/injected, double-gate, 3+40k, RBAC | ✅ | `tests/application/agent_builder/test_run_agent_skill_injection.py:84-93` (`print(1)` not in prompt) | |
| Tests (domain/app/infra/run-injection + FE hooks/panel) | ✅ | 6개 테스트 파일 전부 존재·통과 | |

---

## Deviations (모두 진짜 갭 아님)

### 🔵 의도된/문서화된 결정 (감점 없음)
- **D3** — instruction 병합을 `RunAgentUseCase`(application)에서 수행, `WorkflowCompiler` 무수정. Plan §10 "WorkflowCompiler 확장" 표현과 차이나나 Design §2.4 D3에서 컴파일러 회귀 방지를 위해 명시적으로 선택. 올바름.
- **D4** — 서브에이전트 skill 주입은 Out of Scope; 최상위 에이전트만 주입. 문서화된 Phase A 한계, 갭 아님.

### 🟡 경미한 문서-코드 표기 불일치 (문서 갱신 권장, 코드가 source of truth)
- **D-F1** — `types/agentSkill.ts`가 snake_case(`skill_id`)이고 서비스가 그대로 전달 → Design §5.4 예시(camelCase + 매핑)와 표기 차이. end-to-end 내부 일관성 OK, 계약 자체는 정확. (실제 코드베이스 관례 = snake_case이므로 코드가 맞음)
- **D-B1** — Attach 권한이 `_can_edit_agent`(owner/admin) 인라인 구현, §2.2가 명시한 `VisibilityPolicy.can_edit` 미사용. D5(owner/admin)와 기능적 동일. List UC는 `VisibilityPolicy.can_access` 사용.
- **D-B2** — 라우터가 `viewer_role=current_user.role.value` 사용, §6.2의 `"admin" if is_admin else "user"`와 표기 차이. `UserRole.ADMIN="admin"`(`domain/auth/entities.py:10`)이라 결과 동일.

---

## Out-of-Scope 항목 (정상적으로 부재)

Phase B script 실행/샌드박스, ToolFactory `skill_` 접두사, skill 버전/관측, LLM trigger 자동매칭 — 설계대로 모두 부재. 코드 전역에 `eval`/`exec`/`subprocess` 없음.

---

## Recommendations

1. (문서) Design §5.4를 snake_case 미러 타입으로 정정 (D-F1).
2. (문서) Design §2.2/§6.2를 인라인 `_can_edit_agent` / `role.value` 구현에 맞춰 정렬 (D-B1, D-B2).
3. (백로그) 상세 감사 로깅 — 이미 Design §11에서 후속으로 deferred, Phase A 필수 아님.

**결론**: Match Rate 97%, 기능 갭 0건 → report-ready (`/pdca report skill-agent-integration`).
