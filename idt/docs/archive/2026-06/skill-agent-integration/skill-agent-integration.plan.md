# Plan: skill-agent-integration

> Feature: 에이전트가 Skill을 참조·주입해 동작 (`agent + skill` 결합, Claude Code형 확장)
> Created: 2026-06-25
> Status: Plan
> Priority: High
> Related: `skill-builder`(완료, Match Rate 97%), `agent_builder`(구현됨), `mcp-server-registry`(구현됨)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | `skill-builder`로 Skill(지시문+스크립트)을 저장·관리할 수 있게 됐지만, 정작 **에이전트가 그 Skill을 참조·주입해 실제로 활용하는 경로가 없다**. Skill은 아직 "저장된 텍스트"일 뿐이다. |
| **Solution** | 기존 에이전트 워커 부착 모델(`agent_tool` + `WorkerDefinition` + `ToolFactory` + `WorkflowCompiler`)을 재사용해, 에이전트에 Skill을 부착하는 `agent_skill` 연결을 신설한다. **2단계로 분리**: ①Skill **instruction을 시스템 프롬프트에 주입**(실행 없음, 저위험) → ②Skill **script를 샌드박스에서 실행하는 도구화**(고위험, 별도 phase). |
| **Function/UX Effect** | 에이전트 빌더에서 Skill을 선택해 부착하면, 에이전트 실행 시 해당 Skill의 지시문이 프롬프트에 합쳐져 동작이 확장된다. (Phase B 완료 시) script를 가진 Skill은 에이전트가 호출 가능한 도구로 노출된다. |
| **Core Value** | `skill-builder`가 만든 데이터 기반 위에 **실제 실행 결합**을 얹어 Claude Code형 `agent + skill` 확장을 완성한다. 단, 코드 실행 리스크는 Phase B로 격리해 안전하게 단계적 도입한다. |

---

## 1. 목적 (Why)

`skill-builder`(완료)는 Skill을 **저장·관리**하는 데까지였다. 본 plan은 그 후속으로, **에이전트가 Skill을 참조/주입해 동작하도록** 결합한다.

최종 목표는 Claude Code의 `agent + skill` 모델이다. 이를 위해 두 가지 결합 메커니즘이 필요하다:

1. **지시문 주입(instruction injection)** — Skill의 `instruction`을 에이전트 `system_prompt`에 합쳐 행동을 확장 (텍스트 결합, 실행 없음)
2. **스크립트 실행(script execution)** — Skill의 `script_content`를 에이전트가 호출 가능한 **도구**로 노출 (코드 실행 → 샌드박스 필수)

> 두 메커니즘은 리스크가 크게 다르므로 **Phase A(주입) / Phase B(실행)** 로 명확히 분리한다. 본 plan의 In Scope는 **Phase A + 부착 인프라**이며, Phase B(샌드박스 런타임)는 설계 방향만 제시하고 별도 plan으로 분리한다.

---

## 2. 현재 상태 분석 (As-Is)

### 재사용 가능한 기존 인프라

| 구분 | 상태 | 파일/위치 |
|------|------|----------|
| Skill 도메인/CRUD/Repository | ✅ (skill-builder) | `src/domain/skill_builder/`, `src/application/skill_builder/`, `src/infrastructure/skill_builder/` |
| 에이전트 워커 부착 모델 | ✅ | `agent_tool` 테이블, `WorkerDefinition`(`worker_type`: tool\|sub_agent, `tool_id`, `ref_agent_id`) — `domain/agent_builder/schemas.py` |
| tool_id → BaseTool 변환 | ✅ | `ToolFactory.create_async()` — `mcp_` 접두사로 MCPToolLoader 분기 (`infrastructure/agent_builder/tool_factory.py`) |
| 워크플로우 컴파일 | ✅ | `WorkflowCompiler`(`supervisor_prompt + workers + flow_hint` → LangGraph StateGraph) — `application/agent_builder/workflow_compiler.py` |
| 프롬프트 prepend 선례 | ✅ | `include_user_context` 플래그 + `render_user_context_block` (사용자 컨텍스트를 system_prompt 앞에 합침) |
| 서브에이전트 부착 선례 | ✅ | `worker_type='sub_agent'` + `ref_agent_id` + 순환참조/중첩깊이 정책 (`CircularReferencePolicy`, `NestingDepthPolicy`) |

### 누락된 부분 (이번에 신설)

| 구분 | 상태 |
|------|------|
| 에이전트 ↔ Skill 부착(연결) 모델 | ❌ 없음 |
| Skill instruction을 system_prompt에 주입하는 컴파일 로직 | ❌ 없음 |
| 에이전트 빌더 UI에서 Skill 선택/부착 | ❌ 없음 |
| (Phase B) script 실행 샌드박스 런타임 | ❌ 없음 |

---

## 3. 핵심 설계 결정 (✅ 2026-06-25 확정)

> **확정**: D-1 = **옵션 B(별도 `agent_skill` 테이블)**, D-2 = **Phase A만(instruction 주입)**. 아래 분석을 근거로 Design 단계에서 이 결정을 전제로 진행한다.

### D-1. 부착 모델: `worker_type='skill'` 확장 vs 별도 `agent_skill` 테이블

| 옵션 | 장점 | 단점 |
|------|------|------|
| **A. `worker_type='skill'` 추가** (agent_tool 재사용) | 기존 워커 파이프라인·UI 최대 재사용, `WorkerDefinition`에 `ref_skill_id` 추가만 | agent_tool 스키마/제약 변경, worker 개념에 "주입형 skill"이 섞임 |
| **B. 별도 `agent_skill` 조인 테이블** | 관심사 분리(워커=실행단위 / skill=주입단위), 명확한 모델 | 새 테이블·Repository·조회 경로 추가, 컴파일러에서 별도 병합 |

> **추천: B (별도 `agent_skill` 테이블)** — Phase A의 skill은 "실행 워커"가 아니라 "프롬프트 주입"이므로 worker와 성격이 다르다. 다만 Phase B에서 script-skill을 도구화하면 worker 성격이 생기므로, B로 시작하되 Phase B에서 도구 노출 시 ToolFactory `skill_` 접두사로 연결한다.

### D-2. 스크립트 실행(Phase B) 포함 여부

- 본 plan In Scope는 **Phase A(instruction 주입)만**. `script_content` 실행은 **샌드박스(서브프로세스 격리/리소스 제한/타임아웃)** 설계가 선행돼야 하므로 별도 plan(`skill-script-runtime`)으로 분리.
- 이번 단계에서 script를 가진 Skill을 부착해도 **instruction만 주입**되고 script는 무시(또는 "실행 미지원" 표기)된다.

---

## 4. 기능 범위 (Scope)

### In Scope (Phase A + 부착 인프라)

**A. DB**
- [ ] `V034__create_agent_skill.sql` — `agent_skill`(agent_id, skill_id, sort_order, created_at) 조인 테이블 (D-1 옵션 B 기준)

**B. 백엔드**
- [ ] domain: `AgentSkillLink` VO, `AgentSkillRepositoryInterface`, 부착 정책(`SkillAttachPolicy` — 접근권한·최대 개수·중복)
- [ ] application: AttachSkill / DetachSkill / ListAttachedSkills UseCase + Skill instruction 병합 로직
- [ ] infrastructure: `AgentSkillRepository`(조인 CRUD), `SkillDefinitionModel` 조회 재사용
- [ ] **WorkflowCompiler 확장**: 부착된 Skill들의 `instruction`을 `supervisor_prompt`에 병합(주입). `include_user_context`/`render_user_context_block` 선례 차용
- [ ] interface: `agent_builder_router`에 `POST/DELETE /{agent_id}/skills` + `GET /{agent_id}/skills` 추가, main.py DI 연결

**C. 프론트엔드**
- [ ] 에이전트 빌더(`AgentBuilderPage` 또는 부착 UI)에서 Skill 목록 조회 + 부착/해제
- [ ] `types`/`services`/`hooks` — agent-skill 부착 API 계약
- [ ] 부착된 Skill 표시 + "script는 현재 실행되지 않고 instruction만 주입됨" 안내

### Out of Scope (별도 후속 plan)

- ❌ **Phase B: `script_content` 실제 실행 / 샌드박스 런타임** (`skill-script-runtime` plan으로 분리)
- ❌ ToolFactory `skill_` 접두사 도구화 (Phase B에서)
- ❌ Skill 버전/리비전, A/B, 실행 로그·관측
- ❌ LLM 기반 Skill 자동 추천/매칭(`trigger` 기반 자동 선택)

---

## 5. 통합 메커니즘 설계 (개요)

### 5.1 Instruction 주입 흐름 (Phase A)

```
RunAgentUseCase
  → AgentDefinition 로드 + 부착 Skill 목록 로드(agent_skill JOIN skill_definition, status='active')
  → WorkflowCompiler.compile(agent.to_workflow_definition(), attached_skills)
        supervisor_prompt = [skill_1.instruction, ..., skill_n.instruction, agent.system_prompt] 병합
        (render_user_context_block 선례와 동일하게 블록 구분자로 prepend)
  → LangGraph StateGraph 컴파일 → 실행
```

> Skill `instruction` 길이 상한(현 20,000자) × 부착 개수로 프롬프트가 비대해질 수 있으므로 **부착 최대 개수(예: 3) + 총 길이 가드**를 정책으로 둔다.

### 5.2 Script 도구화 흐름 (Phase B — 설계 방향만)

```
script_type != 'none' 인 부착 Skill
  → ToolFactory.create_async("skill_<id>")  # mcp_ 분기와 동형
  → SandboxRunner(script_content, args) 실행 (서브프로세스 격리·타임아웃·리소스 제한)
  → BaseTool 로 노출 → 에이전트가 호출
```

---

## 6. TDD 계획 (Phase A)

> CLAUDE.md §4-4: 테스트 먼저.

### 백엔드 (pytest)
| 테스트 | 대상 |
|--------|------|
| `tests/domain/agent_skill/test_policies.py` | 부착 권한(접근 가능 skill만), 최대 개수, 중복 차단 |
| `tests/application/agent_skill/test_attach_detach_use_cases.py` | 부착/해제/목록, 비접근 skill 거부, 삭제된 skill 차단 |
| `tests/application/agent_builder/test_compiler_skill_injection.py` | 부착 instruction이 supervisor_prompt에 병합되는지(순서·구분자·길이 가드) |
| `tests/infrastructure/agent_skill/test_repository.py` | agent_skill 조인 CRUD, skill_definition 매핑 |

### 프론트 (Vitest + RTL + MSW, `--pool=threads`)
| 테스트 | 대상 |
|--------|------|
| 부착 훅/서비스 | 목록·부착·해제 |
| 빌더 UI | Skill 선택, 부착 표시, script 미실행 안내 |

> ⚠️ 메모리 노트: idt pytest 격리 실행, idt_front `--pool=threads`, `npm install --legacy-peer-deps`. 사전 실패(tests/api 28·infra 30 / 프론트 8)는 신규 회귀로 오인 금지.

---

## 7. CLAUDE.md 규칙 체크

- [ ] domain → infrastructure 무참조 (interface 역전)
- [ ] **대화 메모리/Parent-Child 문서 구조 변경 금지** — 본 작업은 무관(에이전트 프롬프트 합성만)
- [ ] WorkflowCompiler는 application 계층 흐름제어 — 비즈니스 규칙(주입 정책)은 domain Policy로
- [ ] router 비즈니스 로직 없음, Repository commit/rollback 금지(세션 DI)
- [ ] 한 UseCase 내 동일 세션 사용 (agent_skill + skill_definition 조회를 같은 세션으로)
- [ ] print() 금지, LoggerInterface + request_id
- [ ] API 계약 동기화(백엔드 스키마 ↔ 프론트 타입)

---

## 8. 리스크 및 대응

| 리스크 | 영향 | 대응 |
|--------|------|------|
| **script 실행 = 코드 실행 보안 리스크** | 높음 | Phase B로 격리. 본 plan은 instruction 주입만 → 실행 위험 제로 |
| 프롬프트 비대화(instruction × N) | 중 | 부착 최대 개수 + 총 길이 가드 정책 |
| WorkflowCompiler 회귀 | 중 | 주입은 옵션 경로(부착 0개면 기존과 동일), 컴파일러 테스트로 가드 |
| 부착 모델 선택(D-1) 번복 비용 | 중 | Design 전 사용자와 D-1/D-2 확정 후 진행 |
| 순환/중첩(skill이 다시 agent를 부르는 구조) | 낮 | Phase A는 텍스트 주입이라 순환 불가. Phase B 도구화 시 기존 NestingDepthPolicy 재사용 |

---

## 9. 완료 기준 (Definition of Done — Phase A)

- [ ] `V034__create_agent_skill.sql` 적용 가능
- [ ] 에이전트에 Skill 부착/해제/목록 API 동작 (접근권한·최대개수·중복 정책 적용)
- [ ] 부착 Skill의 instruction이 에이전트 실행 시 system_prompt에 병합됨 (부착 0개면 기존 동작 불변)
- [ ] script를 가진 Skill 부착 시 instruction만 주입되고 script는 실행되지 않음(명시)
- [ ] 빌더 UI에서 Skill 부착/해제 + script 미실행 안내
- [ ] 백엔드/프론트 신규 테스트 통과(격리/threads)
- [ ] API 계약 동기화

---

## 10. 구현 순서 (Phase A)

| 순서 | 작업 | 레이어 |
|------|------|--------|
| 1 | D-1/D-2 사용자 확정 | 결정 |
| 2 | `V034__create_agent_skill.sql` | DB |
| 3 | domain: AgentSkillLink VO + 부착 정책 + interface + 테스트 | 백엔드 domain |
| 4 | infra: `AgentSkillRepository` + 테스트 | 백엔드 infra |
| 5 | application: Attach/Detach/List UseCase + 테스트 | 백엔드 app |
| 6 | **WorkflowCompiler instruction 주입** + 컴파일러 테스트 | 백엔드 app |
| 7 | interface: agent_builder_router 부착 엔드포인트 + main.py DI | 백엔드 interface |
| 8 | 프론트 types/service/hooks + 빌더 부착 UI + 테스트 | 프론트 |
| 9 | 통합 확인(부착 → 실행 시 프롬프트 반영) | 풀스택 |

---

## 11. 다음 단계

1. [x] 본 plan 검토 + **D-1(부착 모델)·D-2(Phase 경계) 확정** ✅ D-1=별도 agent_skill 테이블, D-2=Phase A만
2. [ ] Design 문서 작성 (`/pdca design skill-agent-integration`) — agent_skill 스키마·주입 정책·컴파일러 병합 지점·API 상세화
3. [ ] 구현 시작 (TDD)
4. [ ] (별도 plan) `skill-script-runtime` — script 샌드박스 실행 런타임(Phase B)
