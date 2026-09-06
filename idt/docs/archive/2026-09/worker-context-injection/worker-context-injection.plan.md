# worker-context-injection Planning Document

> **Summary**: 커스텀 에이전트의 워커 노드가 에이전트 프롬프트·역할·작업 지시를 잃어버려 도구를 근거 없이 호출하는 문제를, 정적 컨텍스트 주입 + 동적 작업 지시 + 환각 인자 하드가드로 해결한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: -
> **Author**: 배상규
> **Date**: 2026-09-03
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 워커 react agent가 `system_prompt=datetime_block`만 받고 생성되어(`workflow_compiler.py:450-460`), 에이전트 시스템 프롬프트·자신의 역할·현재 작업 지시를 모른 채 대화 원문만 보고 도구를 호출한다. 그 결과 스크래핑 MCP 도구에 `https://www.example.com/financial-market-2026-09-03` 같은 환각 URL이 전달된다. |
| **Solution** | ① 모든 tool 워커의 `system_prompt`에 [에이전트 프롬프트 + 워커 역할 + 도구 사용 규범] 컨텍스트 블록을 정적 주입, ② `SupervisorDecision`에 `task` 필드를 추가해 supervisor가 매 라우팅마다 구체적 작업 지시를 워커에 내려보냄, ③ MCP 도구 실행 직전 플레이스홀더 인자를 차단하는 하드가드 + 구조화 관측. |
| **Function/UX Effect** | 워커가 "어떤 에이전트의 어떤 작업인지"를 알고 도구를 호출한다. 근거 없는 URL 호출이 실행 전에 차단되고, 사용자는 조작된 결과 대신 "실제 대상을 확보하지 못했다"는 정직한 응답을 받는다. |
| **Core Value** | 컨텍스트 유실로 인한 도구 환각 제거 — MCP 서버가 무엇을 스크래핑해야 하는지 판단할 재료를 프롬프트 유실 없이 온전히 전달한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | supervisor만 에이전트 프롬프트를 보고, 워커는 못 봐서 도구 인자를 지어낸다 |
| **WHO** | P2(KB 운영자/에이전트 소유자) — 커스텀 에이전트를 만들어 MCP 도구를 붙여 쓰는 사용자 |
| **RISK** | 워커 프롬프트 확대에 따른 토큰 증가 / `SupervisorDecision` 스키마 변경이 기존 라우팅 품질에 주는 회귀 |
| **SUCCESS** | 재현 시나리오("현재 분기 리포트 작성해주세요")에서 example.com류 더미 URL 호출 0건, 워커 system_prompt에 에이전트 프롬프트·역할 포함 100% |
| **SCOPE** | M1 정적 컨텍스트 주입 → M2 동적 task 전달 → M3 환각 인자 가드·관측 |

---

## 1. Overview

### 1.1 Purpose

커스텀 에이전트 실행 시 워커 노드가 상위 컨텍스트(에이전트 시스템 프롬프트, 자신의 역할, 현재 수행할 작업)를 잃어버리는 구조적 결함을 제거한다.

### 1.2 Background

**현상**: 스크래핑 MCP 서버를 도구로 가진 커스텀 에이전트에게 "현재 분기 리포트 작성해주세요"라고 요청하면, `mcp_081c6fe7-...._worker` 워커가 실재하지 않는 `https://www.example.com/financial-market-2026-09-03` 을 인자로 넘겨 MCP 서버를 호출한다.

**코드로 확인된 원인** — 컨텍스트가 세 겹으로 유실된다.

| # | 유실 대상 | 근거 코드 | 결과 |
|---|-----------|-----------|------|
| ① | 에이전트 시스템 프롬프트 | `supervisor_nodes.py:230` — `supervisor_prompt`는 supervisor 노드의 `decision_prompt`에만 들어간다 | 워커 LLM은 어떤 에이전트인지 모름 |
| ② | 워커 역할 설명 | `supervisor_nodes.py:191-193` — `worker_def.description`은 supervisor 라우팅 목록 문자열로만 소비된다 | 워커 LLM은 자기 역할도 모름 |
| ③ | 현재 작업 지시 | `supervisor_nodes.py:172-178` — `SupervisorDecision`에 `next`/`reasoning`/`answer`만 존재. `workflow_compiler.py:1554-1560` — `_wrap_worker`는 원문 메시지 + "당신의 역할에 해당하는 작업을 수행하세요" 범용 문구만 전달 | 워커는 대화 원문에서 작업을 재추론해야 함 |

```python
# workflow_compiler.py:450-460 — 일반(MCP 포함) 워커 생성 경로
worker_kwargs = ({"system_prompt": datetime_block} if datetime_block else {})
worker_agent = create_agent(
    model=llm, tools=worker_tools, name=worker_def.worker_id,
    middleware=_instantiate(middleware_plan),
    **worker_kwargs,   # ← 날짜 블록이 전부
)
```

결과적으로 워커 LLM에게 남은 유일한 단서는 "현재 분기 리포트 작성해주세요"라는 사용자 발화뿐이고, MCP 도구 스키마가 URL을 요구하면 그럴듯한 URL을 합성한다.

**부수 확인**: `tool_config`는 MCP 경로에서 사실상 소비되지 않는다(`tool_factory.py:217-233`의 MCP 분기는 `tool_config`를 쓰지 않음). 다만 이번 결정("MCP 서버가 URL을 알아서 해석")에 따라 tool_config로 URL을 고정하는 방향은 채택하지 않으며, 별도 이슈로 남긴다.

### 1.3 Related Documents

- 규칙: `idt/docs/rules/tool-and-mcp.md` (도구/MCP 개발 필수 확인)
- 선행 작업: `fix-mcp-tool-call-not-reaching-server` (도구 바인딩·실행 로그 체인)
- 선행 작업: `worker-toolmessage-leak-fix` (워커 출력 규약: 최종 AIMessage 1건)

---

## 2. Scope

### 2.1 In Scope

- [ ] M1: 모든 `worker_type="tool"` 워커의 `system_prompt`에 워커 컨텍스트 블록(에이전트 프롬프트 + 워커 역할 + 도구 사용 규범) 주입
- [ ] M2: `SupervisorDecision`에 `task` 필드 추가 → `SupervisorState`에 보관 → 워커 진입 지시문으로 사용
- [ ] M3: MCP 도구 실행 직전 플레이스홀더/환각 인자 하드가드 + 소프트 가드(프롬프트 지침) + 차단 이벤트 구조화 관측
- [ ] 기존 자체 프롬프트 보유 노드(search / wiki_read / analysis / document_extractor / document_generator / presentation_generator / excel_export)의 동작 보존 검증

### 2.2 Out of Scope

- `tool_config`를 통한 스크래핑 대상 URL 고정 (이번 결정: URL 해석은 MCP 서버 책임)
- MCP 서버 측 코드 변경
- 에이전트 빌더 UI 변경 (워커 `description` 작성 가이드 등)
- 검색 워커 → 스크래핑 워커 간 URL 인계 규약 (별도 기능)
- 프론트엔드 변경 (API 계약 변화 없음)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 워커 컨텍스트 블록 렌더러를 신설한다. 입력: 에이전트 시스템 프롬프트, 워커 `description`, 바인딩된 도구 이름 목록. 출력: 워커 `system_prompt`에 붙일 문자열 블록 | High | Pending |
| FR-02 | 모든 tool 워커 생성 시 `system_prompt = datetime_block + worker_context_block` 순으로 주입한다 (빈 값이면 기존 형태 보존) | High | Pending |
| FR-03 | 자체 프롬프트를 이미 갖는 노드(wiki_read, search, analysis, document_*)도 컨텍스트 블록을 앞단에 동일하게 받되, 기존 지시문은 그대로 뒤에 유지한다 | High | Pending |
| FR-04 | `SupervisorDecision`에 `task: str` 필드를 추가한다. supervisor는 선택한 워커가 지금 수행할 작업을 한국어 1~3문장으로 구체적으로 기술한다 | High | Pending |
| FR-05 | supervisor 노드가 `task`를 `SupervisorState["worker_task"]`로 반환하고, `_wrap_worker`는 이를 `ensure_user_tail(instruction=...)`로 전달한다. `task`가 비면 기존 범용 문구로 폴백한다 | High | Pending |
| FR-06 | 컨텍스트 블록에 소프트 가드 지침을 포함한다: "도구 인자로 URL·식별자를 추측해 만들지 말 것. 대화·이전 단계 결과·도구 응답에 근거가 없으면 도구를 호출하지 말고 무엇이 부족한지 답할 것" | High | Pending |
| FR-07 | `MCPToolAdapter._arun`은 서버 호출 전 인자를 검증한다. 예약/플레이스홀더 도메인(`example.com`, `example.org`, `example.net`, `localhost`, `127.0.0.1`, `your-domain`, `test.com`)이 포함된 URL 값이 있으면 도구를 호출하지 않고, 워커 LLM이 재시도할 수 있는 오류 메시지를 반환한다 | High | Pending |
| FR-08 | 차단 발생 시 `MCP tool call blocked (placeholder argument)` 구조화 로그를 `request_id`/`tool_id`/`server`/`tool`/차단 사유와 함께 기록한다 | High | Pending |
| FR-09 | 차단 사유를 run step 추적에 반영해 실행 이력에서 재발을 추적할 수 있게 한다 | Medium | Pending |
| FR-10 | 플레이스홀더 도메인 목록은 도메인 레이어 정책으로 분리하고 하드코딩하지 않는다 (config 하드코딩 금지 규칙) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|--------------------|
| 토큰 | 워커 1회 호출당 추가 프롬프트 토큰 증가 ≤ 600 tokens (에이전트 프롬프트 길이에 비례) | `token-ledger` / usage callback 비교 |
| 회귀 | 기존 agent_builder 테스트 전량 통과 | `pytest tests/application/agent_builder tests/infrastructure` |
| 아키텍처 | 플레이스홀더 정책은 `domain/`, 검증 실행은 `infrastructure/mcp/` — domain → infrastructure 참조 금지 | `/verify-architecture` |
| 로깅 | 차단 경로에 print 없음, logger 필수, 예외는 스택 트레이스 포함 | `/verify-logging` |
| 하위호환 | `task` 미제공(구 모델·구조화 출력 실패) 시에도 그래프가 기존과 동일하게 동작 | 단위 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-10 구현 완료
- [ ] TDD 사이클 준수(테스트 선작성 → 실패 확인 → 구현 → 통과)
- [ ] 재현 시나리오 검증: 스크래핑 MCP 도구를 가진 커스텀 에이전트에 "현재 분기 리포트 작성해주세요" 입력 시 ① 워커 프롬프트에 에이전트 프롬프트·역할이 포함되고 ② example.com 계열 URL이 MCP 서버로 전달되지 않음
- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과
- [ ] 기존 회귀 없음

### 4.2 Quality Criteria

- [ ] 신규/변경 모듈 단위 테스트 존재
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수
- [ ] 로그에 예약 키 충돌 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| `SupervisorDecision` 필드 추가로 구조화 출력 실패율·라우팅 품질 변동 | High | Medium | `task`에 `default=""` 부여, 파싱 실패/빈 값 시 기존 범용 문구로 폴백. supervisor 기존 테스트(`test_supervisor_nodes.py`, `test_supervisor_overblock.py`) 전량 통과 확인 |
| 워커 프롬프트 확대에 따른 토큰·지연 증가 | Medium | High | 에이전트 프롬프트를 그대로 복사하지 않고 컨텍스트 블록으로 정형화, 상한 길이 정책 적용 |
| 자체 프롬프트 보유 노드(wiki/search/analysis)에 블록을 덧붙이며 기존 지시 우선순위가 깨짐 | High | Medium | 블록을 **앞단**에만 배치하고 기존 지시문 문자열은 무변경. `test_workflow_compiler_wiki_toc.py`, `test_search_node.py`로 순서 검증 |
| 하드가드 오탐 — 사내 테스트 환경에서 localhost MCP 대상을 실제로 쓰는 경우 | Medium | Medium | 플레이스홀더 정책을 도메인 정책 객체로 분리하고 설정으로 완화 가능하게 설계. 차단은 도구 인자의 URL 값에만 적용하고 서버 접속 주소에는 적용하지 않음 |
| 차단 후 워커가 무한 재시도 | Medium | Low | 차단 응답은 예외가 아닌 지시성 오류 문자열로 반환하고, 기존 `IterationLimitPolicy`가 상한을 담당 |
| function 노드(search 등)는 `_wrap_worker`를 우회하므로 `task` 전달이 누락됨 | Medium | High | M2에서 function 노드 경로에도 `worker_task` 전달 여부를 명시적으로 설계(전달하거나, 미적용을 문서화) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/application/agent_builder/workflow_compiler.py` | Application | 워커 생성 시 컨텍스트 블록 주입(FR-02/03), `_wrap_worker`의 지시문을 `worker_task` 기반으로 변경(FR-05) |
| `src/application/agent_builder/supervisor_nodes.py` | Application | `SupervisorDecision.task` 추가, supervisor 반환값에 `worker_task` 포함(FR-04/05) |
| `src/application/agent_builder/supervisor_state.py` | Application | `SupervisorState`에 `worker_task` 키 추가 |
| `src/application/agent_run/prompt_rendering.py` | Application | 워커 컨텍스트 블록 렌더러 신설(FR-01) — 기존 `render_datetime_block`/`render_user_context_block`와 동거 |
| `src/domain/mcp/policy.py` | Domain | 플레이스홀더 인자 판정 정책 추가(FR-07/10) |
| `src/infrastructure/mcp/tool_adapter.py` | Infrastructure | `_arun` 서버 호출 전 인자 검증·차단·로그(FR-07/08) |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `workflow_compiler.compile` | 그래프 컴파일 | `run_agent_use_case.py` → 에이전트 실행 전체 | Needs verification — 모든 커스텀 에이전트 실행 경로 |
| 워커 생성 경로 | tool 워커 | MCP 워커 / 내부 도구 워커 / wiki_read / search / analysis / document_extractor / document_generator / presentation_generator / excel_export | Needs verification — FR-03 순서 규약으로 기존 동작 보존 |
| `_wrap_worker` | 워커 실행 | `worker-toolmessage-leak-fix` 규약(최종 AIMessage 1건) | Needs verification — 출력 규약은 무변경, 입력 지시문만 변경 |
| `SupervisorDecision` | 구조화 출력 | `supervisor_node` → `route_to_worker` / `route_to_worker_or_final` | Needs verification — 필드 추가는 후방호환이나 프롬프트 길이·모델 응답 변동 |
| `SupervisorState` | 상태 | `supervisor_nodes`, `workflow_compiler`, `search_pipeline`, `supervisor_hooks` | None — 키 추가만 |
| `MCPToolAdapter._arun` | MCP 실행 | 모든 MCP 도구 호출 | Needs verification — 정상 인자는 무영향, 플레이스홀더만 차단 |
| `AttachmentRoutingHooks.force_worker` | 강제 라우팅 | `supervisor_hooks.py:65` | Needs verification — 강제 경로는 `SupervisorDecision`을 거치지 않으므로 `task`가 비고 폴백 문구를 사용 |

### 6.3 Verification

- [ ] 위 소비자 전부가 변경안에서 정상 동작
- [ ] 강제 라우팅(첨부/분석) 경로에서 `task` 부재 폴백 확인
- [ ] MCP 정상 호출(플레이스홀더 아님)이 차단되지 않음 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter | ☐ |
| Dynamic | ☐ |
| **Enterprise** (Thin DDD: domain / application / infrastructure / interfaces) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 컨텍스트 전달 방식 | 정적 주입만 / 동적 task만 / 둘 다 | **둘 다** | 정적 주입은 "어떤 에이전트의 어떤 역할인가"(불변 맥락), 동적 task는 "지금 무엇을 하는가"(가변 맥락)를 담당 — 두 유실 축이 서로 다르므로 하나로는 부족 |
| 스크래핑 URL 결정 주체 | tool_config 고정 / 검색 인계 / 사용자 입력 / MCP 서버 해석 | **MCP 서버 해석** | 클라이언트는 의도·키워드·맥락 전달에만 책임을 지고, 대상 결정은 서버 책임으로 둔다 |
| 환각 가드 수준 | 소프트만 / 하드만 / 둘 다 + 관측 | **둘 다 + 관측** | 프롬프트만으로는 보장 불가, 실행 차단만으로는 원인 파악 불가 |
| 적용 범위 | 스크래핑 도구만 / MCP 워커만 / 모든 tool 워커 | **모든 tool 워커** | 동일 유실이 내부 도구 워커에서도 발생 중이므로 근본 수정 |
| 블록 배치 순서 | 앞단 / 뒤단 | **앞단(datetime → context → 기존 지시)** | 기존 노드별 지시문의 우선순위를 건드리지 않기 위함 |
| 플레이스홀더 정책 위치 | infrastructure 상수 / domain 정책 | **domain 정책** | config 하드코딩 금지 + 규칙은 domain 레이어 소유 |

### 7.3 Clean Architecture Approach

```
domain/mcp/policy.py                    ← 플레이스홀더 인자 판정 규칙 (FR-07/10)
application/agent_run/prompt_rendering  ← 워커 컨텍스트 블록 렌더러 (FR-01)
application/agent_builder/
    supervisor_nodes.py                 ← task 생성·전달 (FR-04/05)
    supervisor_state.py                 ← worker_task 상태 키
    workflow_compiler.py                ← 주입 지점·워커 진입 지시문 (FR-02/03/05)
infrastructure/mcp/tool_adapter.py      ← 실행 전 검증·차단·로그 (FR-07/08)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` 코딩 규칙 (레이어 책임, 함수 40줄, print 금지)
- [x] `idt/docs/rules/tool-and-mcp.md` — 도구/MCP 변경 시 필수 확인
- [x] `idt/docs/rules/logging.md` — 로깅·에러 추적
- [x] `idt/docs/rules/testing.md` — TDD 절차

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 워커 프롬프트 조립 순서 | 암묵적(datetime → 노드별 지시) | `datetime → worker_context → 노드별 지시` 로 명문화 | High |
| 도구 인자 검증 책임 | 없음 | domain 정책 판정 + infrastructure 실행 차단 | High |
| 차단 로그 필드 | 없음 | `request_id`/`tool_id`/`server`/`tool`/`reason` | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (없음) | 신규 환경변수 불필요 — 플레이스홀더 정책은 코드 내 domain 정책으로 관리 | - | ☐ |

---

## 9. Next Steps

1. [ ] `/pdca design worker-context-injection` — 설계안 3종 비교 후 선택
2. [ ] 재현 케이스 확보: 문제 에이전트의 `agent_id`, 워커 `description`, MCP 도구 스키마(URL 인자 이름) 확인
3. [ ] M1 → M2 → M3 순서로 TDD 구현

> **Design 단계 전 확인이 필요한 항목**
> - 문제의 스크래핑 MCP 도구가 받는 인자 스키마(URL을 직접 받는지, 키워드만 받는지) — FR-07의 검증 대상 필드 결정에 필요
> - 해당 에이전트의 워커 `description`이 실제로 채워져 있는지 — 비어 있다면 정적 주입 효과가 반감되므로 빌더 측 가이드가 별도 필요

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-03 | 초안 — 코드 근거 기반 원인 분석 및 3축 해결안 | 배상규 |
