# approval-gate-run-termination Planning Document

> **Summary**: 승인 게이트가 걸린 런의 **종료·응답·라우팅·보호 기본값**을 결정적으로 만든다. 게이트가 도구 호출을 막은 뒤에도 supervisor 가 같은 워커를 반복 호출하고, 워커 LLM 이 지어낸 "성공 JSON" 이 채팅 답변으로 저장되는 문제(실측)를 없앤다. 동시에 "등록해줘" 에도 호출하지 않던 라우팅, 게이트 미설정 에이전트의 무승인 DB 변경 가능성, react 워커의 본문 키 부재(수정 후 승인 불가), 부작용 도구의 본문 즉흥 작성 구조를 함께 정리한다.
>
> **Project**: sangplusbot (idt, 일부 idt_front)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-29
> **Status**: Draft (v0.1)
> **Depends on**: approval-gate, approval-gate-phase2-mcp-executor, action-category-compose-node, approval-edit-before-approve

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 실측(2026-09-29, 문의 답변 에이전트): ① 게이트 차단 후에도 런이 끝나지 않아 `submit_reply_worker` 가 한 런에서 최대 5회 반복 호출됨 ② 두 번째 호출의 워커 LLM 이 실제 결과가 아닌 **가짜 성공 JSON**(`status: ok`)을 출력, 승인 대기 런은 마지막 메시지를 그대로 답변으로 저장해 채팅에 "등록 성공" 처럼 노출(실제 63116 은 `reply: null`) ③ 도구 설명의 "승인 전에 호출하지 마십시오" 때문에 "등록해줘" 에도 호출하지 않음(비결정) ④ 에이전트에 게이트 미들웨어가 없으면 `requires_approval` 도구도 **무승인 실행** ⑤ react 워커는 본문 키를 지정할 수 없어 `reply_content` 도구의 초안이 JSON 전체 → 수정 후 승인 불가 ⑥ 고객 답변 본문이 라우터의 1~3문장 `task` + 워커 LLM 의 도구 인자 채우기로 즉흥 작성됨. |
| **Solution** | A 게이트 신호가 state 에 오르면 라우팅 함수가 **즉시 END** / B 승인 대기 런의 채팅 답변을 **고정 템플릿 + 초안 미리보기**로 생성(LLM 미사용) / C supervisor 워커 목록에 게이트 워커 **자동 안내** / D react 워커 `tool_config.draft_arg_key` 로 **본문 키 지정** / E 게이트 미설정이어도 승인 필요 도구는 **카탈로그 기본 config 로 게이트 적용**(명시적 off 는 존중) / F 승인 필요 도구는 본문 키가 확정되면 **action(초안 작성 노드) 경로를 기본**으로. |
| **Function/UX Effect** | "63116 답변 등록해줘" → 조회 → 초안 작성(에이전트 지침 반영) → 승인함 등록 → 채팅에 "승인함에 올렸습니다 + 초안 미리보기" 가 **항상 같은 형태**로 표시. 반복 호출·허위 성공 보고 0. 승인 화면에서 본문이 보이고 수정 후 승인 가능. |
| **Core Value** | 금융 데이터 변경 경로에서 **"시스템이 말하는 상태 = 실제 상태"** 를 보장하고, 부작용 도구는 설정 누락과 무관하게 **기본적으로 사람 승인 아래** 둔다(fail-closed). 특화 로직 없이 모든 부작용 도구에 일반 적용. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 게이트는 막았는데 런이 안 끝나고, 채팅엔 가짜 "등록 성공" 이 나가며, 게이트 미설정 에이전트는 무승인 DB 변경이 가능하다 — 사용자가 본 상태와 실제 상태가 어긋난다. |
| **WHO** | P2 — 부작용 도구(문의 답변 등록·메일 발송 등)를 가진 에이전트의 소유자/승인자, 그리고 그 채팅 사용자. |
| **RISK** | 즉시 종료·action 기본화가 기존 게이트/비게이트 에이전트 라우팅을 바꿀 수 있음 → 비게이트 경로 바이트 동일 회귀 테스트. fail-closed 기본 적용이 기존 에이전트 동작을 바꿈(승인 대기로 전환) → 명시적 mode=off 존중 + 릴리스 노트. |
| **SUCCESS** | 게이트 런에서 게이트 워커 호출 정확히 1회·supervisor 재진입 0 / 승인 대기 런 채팅 답변 = 템플릿(LLM 텍스트 0) / "등록해줘" 류 요청 시 게이트 워커 라우팅 / 게이트 미설정 + 승인 필요 도구 → 승인 대기 생성(무승인 실행 0) / `reply_content` 도구 초안 = 본문, 수정 후 승인 가능 / 비게이트 에이전트 회귀 0. |
| **SCOPE** | A 종료 → B 응답 템플릿 → E fail-closed → C 워커 안내 → D react 본문 키 → F action 기본 (+ 프론트: D 설정 입력). DB 스키마 변경 없음. |

---

## 1. Overview

### 1.1 Purpose

승인 게이트가 걸린 런을 **LLM 판단에 기대지 않고** 종료·보고되게 하고, 부작용 도구가 설정 누락·도구 설명 문구·워커 방식에 상관없이 일관되게 "초안 작성 → 승인함 → 사람 승인 → 집행" 을 타게 한다.

### 1.2 Background (실측 근거)

로컬 DB·MCP 실측, 에이전트 `8421828f…`(상상인플러스저축은행 문의 답변):

| 런 | 요청 | 관측 |
|----|------|------|
| `d69702ff`, `7e81e6ee` (07:32) | "작성 가능한가?", "DB 등록하려면?" | 게이트 미들웨어 **없음**. supervisor 가 도구 설명("승인 전에 호출하지 마십시오")을 근거로 호출 회피 — 호출했다면 **무승인 DB 기록** |
| `67e157e3` (07:51, 게이트 적용 후) | "등록해줄수 있나?" | `submit_reply_worker` **5회** 반복 호출(step 5·8·11·14·17). supervisor: "실제 호출 결과 객체가 없다" → 재호출. approval 1건만 적재(정상 집행) |
| `a2170154` (07:58) | "63116 … 답변까지 등록해줘" | 호출 없이 FINISH — "실제 등록은 담당자가 submit_reply_worker로 처리" (비결정) |
| `ed0de9d4` (08:04) | "… 등록해줘 승인함까지" | 게이트 워커 2회 호출 → 두 번째 워커 출력이 **가짜 성공 JSON** → supervisor "status=ok 정상 처리" FINISH → 채팅 답변으로 저장. **MCP 직접 조회: 63116 `reply: null`** (승인 건 pending) |

코드 원인:
- `route_to_worker_or_final`(supervisor_nodes.py:660) 은 `next_worker=="__end__"` **이고** approval_pending 일 때만 END — 워커 직후엔 항상 supervisor 로 돌아간다.
- 승인 대기 런은 final_answer 를 건너뛰고 `_parse_result` 가 **마지막 메시지**를 답변으로 저장(run_agent_use_case.py:1411) — 워커 LLM 텍스트가 그대로 노출.
- 게이트 발동 = 도구 축(`requires_approval`) AND 에이전트 축(게이트 적용 목록). 적용 목록에 없으면 `_gate_settings` → None → 무게이트(workflow_compiler.py:152).
- 게이트 초안 추출은 관례 키(`draft/body/content/본문`)만 탐색 — `reply_content` 미해당, react 워커는 본문 키 지정 수단 없음.
- 워커는 에이전트 시스템 프롬프트를 보지 못한다 — react 부작용 워커의 본문은 supervisor `task`(1~3문장) + 대화 원문으로 즉흥 작성.

### 1.3 Related Documents

- `docs/01-plan/features/approval-gate.plan.md`, `approval-gate-phase2-mcp-executor.plan.md`, `approval-edit-before-approve.plan.md`
- action-category-compose-node (PR #61) — action 워커 = 초안 작성 노드 + 도구 1회
- `docs/rules/tool-and-mcp.md`, `docs/wiki/_INDEX.md` (supervisor-graph-contracts, mcp-runtime-tool-shape)

---

## 2. Scope

### 2.1 In Scope

- [ ] **A 즉시 종료**: 게이트 워커(react·action 공통)가 approval_pending 을 state 에 올리면 다음 라우팅이 **END** — supervisor·final_answer·quality_gate 재진입 없음
- [ ] **B 응답 템플릿**: 승인 대기 런의 답변 = 도메인 정책이 만드는 고정 문구(승인함 안내 + 도구 표시명 + 초안 미리보기 N자). 채팅 저장·스트림 answer 이벤트 모두 이 문구
- [ ] **C 워커 안내**: supervisor 워커 목록에서 게이트 워커 설명 앞에 "[승인 필요] 호출하면 즉시 실행되지 않고 담당자 승인함에 등록됩니다. 사용자가 실행·등록을 요청하면 호출하세요." 자동 부착
- [ ] **D react 본문 키**: react 워커 `tool_config.draft_arg_key`(기존 ActionToolConfig 필드 재사용) → 게이트 초안 추출이 이 키를 우선 사용(래퍼 해제 후). 빌더 UI 에 입력 필드
- [ ] **E fail-closed**: 에이전트 적용 목록에 approval_gate 가 없어도 `requires_approval` 도구 워커가 있으면 **카탈로그 default_config 로 게이트 적용**. 에이전트가 명시적으로 `mode=off` 한 경우는 존중(관리자 강제 시엔 강제 우선). 적재(compile)·승인(decide) 해석이 같은 단일 출처
- [ ] **F action 기본**: `requires_approval` 도구이고 카테고리 미지정이면, 본문 키가 확정될 때(D 설정 또는 스키마 관례 후보) **action 경로로 컴파일**. 확정 불가면 react + 게이트로 폴백(격리하지 않음) + 경고 로그
- [ ] 관측: 게이트 종료·템플릿 응답·fail-closed 적용·action 기본화 각각 구조화 로그

### 2.2 Out of Scope

- MCP 서버 측 도구 설명 문구 변경(C 로 플랫폼에서 해소 — 서버 문구는 별도 판단)
- 한 런에서 여러 부작용 도구를 연속 승인 대기로 묶기(런당 pending 1건 불변식 유지)
- LangGraph interrupt/checkpointer 기반 재설계
- 역할 기반 승인자, 도구별 편집 금지 필드
- 재개(resume) 이후 답변 생성 방식 변경(기존 final_answer 경로 유지)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 워커 노드 출력에 approval_pending 이 비어있지 않으면 그 다음 라우팅은 END (supervisor·quality_gate 미경유). react 래퍼·action 노드 공통 | High | Pending |
| FR-02 | FR-01 로 종료된 런은 해당 게이트 워커를 정확히 1회만 실행한다 (반복 호출 0) | High | Pending |
| FR-03 | 승인 대기 런의 최종 답변은 `ApprovalPendingNoticePolicy`(domain)가 approval_pending(tool_id·draft)으로 만든 고정 문구. LLM 출력·워커 텍스트는 답변에 쓰지 않는다 | High | Pending |
| FR-04 | 템플릿 문구: 승인함 등록 사실 / 아직 실행되지 않았음 / 작업함 › 승인 대기에서 확인·수정·승인 시 실제 집행 / 초안 미리보기(상한 N자, 초과 시 절단 표시) | High | Pending |
| FR-05 | 채팅 저장 메시지·스트림 answer 이벤트·동기 응답이 같은 템플릿 문구를 쓴다 (approval_pending=true 페이로드 유지) | High | Pending |
| FR-06 | supervisor 워커 목록에서 게이트 적용 워커 설명 앞에 승인 안내 접두를 자동 부착. 비게이트 워커 설명은 바이트 동일 | High | Pending |
| FR-07 | react 워커 `tool_config.draft_arg_key` 지원: 게이트 초안 추출이 (래퍼 해제 후) 이 키 값을 우선 사용. 미지정이면 기존 관례 키 탐색 | High | Pending |
| FR-08 | 에이전트 적용 목록에 approval_gate 가 없고 `requires_approval` 도구 워커가 존재하면 **도메인 기본 게이트**(`GateSettings.from_config({})`)를 적용한다 — 승인 측 해석과 자동 일치 (Design D-01) | High | Pending |
| FR-09 | 에이전트가 approval_gate 를 명시적으로 `mode=off` 로 둔 경우 FR-08 을 적용하지 않는다. 관리자 is_enforced 는 기존대로 off 를 이긴다 | Medium | Pending |
| FR-10 | 카탈로그 approval_gate 의 활성/부재와 무관하게 FR-08 은 도메인 기본으로 적용 (fail-closed). 카탈로그 default_config 는 명시 적용 시에만 의미 (Design D-01) | Medium | Pending |
| FR-11 | `requires_approval` 이고 category 미지정인 도구 워커는 본문 키 확정 시 action 경로로 컴파일. 확정 불가 시 react+게이트 폴백 + `gated worker fallback to react` 경고 | Medium | Pending |
| FR-12 | 빌더 UI(에이전트 도구 설정)에 본문 키(draft_arg_key) 입력 — 승인 필요 도구에만 노출, 스키마 키 후보 제시 | Medium | Pending |
| FR-13 | 관측 로그: `run ended on approval gate`(worker_id, tool_id), `approval gate applied by default`(agent_id, tool_ids), `gated worker compiled as action` / fallback | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 회귀 | 게이트 도구가 없는 에이전트: 그래프·프롬프트·답변 바이트 동일 | 기존 agent_builder·approval 테스트 전량 + 비게이트 스냅샷 테스트 |
| 결정성 | 승인 대기 런 답변은 입력(approval_pending)만의 함수 | 단위 테스트 |
| 안전 | 무승인 부작용 실행 경로 0 (게이트 미설정 포함) | FR-08~10 테스트 + 실런 L3 |
| 아키텍처 | 문구·판정은 domain, 라우팅 배선은 application | verify-architecture |
| 비용 | 게이트 런 LLM 호출 수 감소(반복 supervisor·final_answer 제거) | ai_run.llm_call_count 실측 비교 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 게이트 런에서 게이트 워커 실행 1회, 이후 supervisor/final_answer 노드 실행 0 (그래프 통합 테스트 + 실런 트레이스)
- [ ] SC-2: 승인 대기 런의 채팅 저장 답변·스트림 answer = 템플릿 문구 (워커가 가짜 JSON 을 출력해도)
- [ ] SC-3: "63116 답변 등록해줘" 실런에서 게이트 워커가 호출되고 승인함에 1건 생성 (C 효과, 3회 반복 실측 중 3회)
- [ ] SC-4: 게이트 미들웨어 없는 에이전트 + requires_approval 도구 → 승인 대기 생성, MCP 미호출
- [ ] SC-5: `draft_arg_key=reply_content` 설정 시 approval draft = 본문, 상세 `editable=true`
- [ ] SC-6: 카테고리 미지정 승인 필요 도구가 action 경로로 컴파일(본문 키 확정 시) / 확정 불가 시 react+게이트 폴백
- [ ] SC-7: 비게이트 에이전트 회귀 0, 기존 테스트 상시 실패 목록 외 실패 0

### 4.2 Quality Criteria

- [ ] TDD, 함수 40줄 / if 중첩 2단계
- [ ] verify-architecture, verify-logging, verify-tdd 통과
- [ ] 프론트 변경 파일 eslint 0, tsc 기준선 유지

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| E fail-closed 로 기존 에이전트가 갑자기 승인 대기로 바뀜 | High | Medium | `requires_approval` 도구 보유 에이전트만 영향. 명시적 mode=off 존중(FR-09). 릴리스 노트 + 적용 로그(FR-13) |
| F action 기본화가 기존 react 부작용 워커 동작(인자 채우기) 변경 | Medium | Medium | 본문 키 확정 시에만 전환, 불가 시 폴백. 카테고리를 명시한 도구는 불변 |
| A 즉시 종료가 "게이트 후 추가 작업" 시나리오를 막음 | Medium | Low | 런당 pending 1건 불변식(FR-06, approval-gate) 과 일치 — 후속 작업은 재개 런에서 수행 |
| C 안내 문구가 과호출 유발(질문만 해도 호출) | Medium | Low | 문구에 "사용자가 실행·등록을 요청하면" 조건 명시. 호출돼도 승인함에서 거절 가능(무해) |
| 템플릿 답변이 대화 맥락과 동떨어져 보임 | Low | Medium | 도구 표시명·초안 미리보기 포함. 재개 후 답변은 기존 final_answer 가 맥락 반영 |
| 재개(resume) 경로가 FR-01 라우팅 변경에 영향 | High | Low | `_restore_state` 가 approval_pending·next_worker 를 비우므로 재개 런은 게이트 신호 없음 — 테스트로 고정 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change |
|----------|------|--------|
| `route_to_worker_or_final` / 워커→다음 노드 엣지 | Graph routing | approval_pending 시 END |
| `RunAgentUseCase` 답변 결정(`_parse_result`, 스트림 answer) | UseCase | 승인 대기 시 템플릿 |
| `ApprovalPendingNoticePolicy` (신규) | Domain | 템플릿 문구 |
| supervisor 워커 목록 조립 | Prompt | 게이트 워커 접두 |
| `_gate_settings` / `_resolve_approval_gate_config` | Gate resolution | fail-closed 기본 적용 (단일 출처화) |
| 게이트 초안 추출(`ApprovalEditPolicy.extract_draft`) 호출부 | Domain/App | draft_arg_key 우선 |
| workflow_compiler 워커 카테고리 결정 | Compile | 승인 필요 도구 action 기본 |
| 빌더 도구 설정 UI | Front | draft_arg_key 입력 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| approval_pending state | READ | supervisor_nodes.route_to_worker_or_final, run_agent_use_case._persist_approval_if_pending | Needs verification |
| 답변 문자열 | READ | 채팅 저장, SSE/WS answer 이벤트, 동기 RunAgentResponse, webhook outbound, background job 결과 | Needs verification (모든 소비자가 템플릿을 받게) |
| 게이트 해석 | READ | WorkflowCompiler(적재), DecideApprovalUseCase(승인, execute_after) | Breaking if 불일치 — 단일 출처 필수 |
| worker_descriptions | READ | supervisor 프롬프트 | None (비게이트 바이트 동일) |
| `_restore_state` (재개) | READ | approval_pending 초기화 | None — 테스트로 고정 |
| action 노드 | CREATE | `_create_action_worker_node` (D-09 격리) | Needs verification (폴백 경로 신설) |

### 6.3 Verification

- [ ] 위 소비자 전부 변경 후 동작 확인 (특히 webhook·background job 답변)
- [ ] 비게이트 에이전트 그래프 스냅샷 동일
- [ ] 적재·승인 게이트 해석 일치 테스트

---

## 7. Architecture Considerations

### 7.1 Project Level

Enterprise (Thin DDD) — 문구·판정은 domain, 라우팅·컴파일 배선은 application.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 종료 방식 | supervisor FINISH 강제 / 워커 직후 END | **워커 직후 END** | 사용자 결정. LLM 재진입 자체를 없애 반복·허위 보고 차단 |
| 채팅 답변 | LLM 요약 / 고정 템플릿 | **고정 템플릿 + 초안 미리보기** | 사용자 결정. 결정적, 허위 보고 불가 |
| fail-closed | 저장 차단 / 실행 시 기본 적용 | **실행 시 기본 적용** | 사용자 결정. 기존 에이전트 즉시 보호 |
| 본문 키 | 새 컬럼 / 기존 tool_config.draft_arg_key | **기존 필드 재사용** | 스키마 변경 없음, action 경로와 같은 설정 |
| action 기본화 | 카탈로그 일괄 변경 / 컴파일 시 판정 | **컴파일 시 판정 + 폴백** | 데이터 마이그레이션 없이 모든 부작용 도구에 일반 적용 |

### 7.3 Layer Mapping (예상)

```
domain/approval/        ApprovalPendingNoticePolicy, (GateDefaultPolicy: fail-closed 판정)
domain/agent_builder/   게이트 워커 안내 접두, 승인 필요 도구 카테고리 결정 규칙
application/agent_builder/ supervisor_nodes(라우팅·워커 목록), workflow_compiler(게이트 해석·카테고리), run_agent_use_case(답변)
application/approval/   gate_middleware(draft_arg_key)
api/main.py             _resolve_approval_gate_config 단일 출처 정리
idt_front               에이전트 도구 설정 draft_arg_key 입력
```

---

## 8. Convention Prerequisites

- [x] CLAUDE.md 3종 + `docs/rules/` (tool-and-mcp, logging, testing)
- [x] 위키: supervisor-graph-contracts (워커 산출물 = AIMessage(name) 1건), mcp-runtime-tool-shape
- [x] 상시 실패 목록(백엔드 53, 프론트 9) — 회귀 판정 기준
- 환경변수: 없음 (템플릿 미리보기 길이는 domain 상수 또는 settings — Design 에서 결정)

---

## 9. Next Steps

1. [ ] `/pdca design approval-gate-run-termination` — 라우팅 엣지 위치, 템플릿 문구 확정, fail-closed 단일 출처, action 기본화 판정식, 프론트 입력 위치
2. [ ] 실런 L3 재현 시나리오 확정(문의 답변 에이전트, "63116 답변 등록해줘" ×3)
3. [ ] TDD 구현

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-29 | Initial draft — 실측 근거(런 4건 + MCP 조회), A·B·C·D·E·F 범위 확정 | 배상규 |
| 0.2 | 2026-09-30 | FR-08/FR-10 기본 게이트 = 도메인 기본값 (Design D-01) | 배상규 |
