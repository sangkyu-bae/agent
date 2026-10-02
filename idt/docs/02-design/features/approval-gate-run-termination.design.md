# approval-gate-run-termination Design Document

> **Summary**: 게이트 워커 직후 조건부 END, 승인 대기 런 답변의 고정 템플릿화, 게이트 워커 supervisor 안내, react 본문 키, 게이트 기본 적용(fail-closed), 승인 필요 도구의 action 기본화를 **domain 정책 3개 + 컴파일러 배선 + 답변 단일 지점**으로 구현한다. 게이트가 없는 에이전트는 그래프·프롬프트·답변이 바이트 동일하다.
>
> **Project**: sangplusbot (idt, idt_front)
> **Version**: —
> **Author**: 배상규
> **Date**: 2026-09-30
> **Status**: Draft (v0.1)
> **Planning Doc**: [approval-gate-run-termination.plan.md](../../01-plan/features/approval-gate-run-termination.plan.md)
> **Architecture**: Option C — Pragmatic Balance

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

## 0. Plan 대비 확정·변경 사항

| # | Plan | 코드 사실 | Design 결정 |
|---|------|-----------|-------------|
| D-01 | FR-08 "카탈로그 default_config 로 게이트 적용" | 승인 측(`DecideApprovalUseCase._resolve_gate`)은 미적용이면 `from_config({})` = **도메인 기본값**. 컴파일 측이 카탈로그 값을 쓰면 적재·승인 해석이 어긋난다(approval-gate Check G4 위반) | 미적용 기본 게이트는 **도메인 기본값**(`GateSettings.from_config({})` — mode=always, 168h, 즉시 집행). 양측이 자동으로 일치. 카탈로그 default 는 "명시 적용 시" 에만 의미 — Plan FR-08/FR-10 문구를 이에 맞춘다 |
| D-02 | FR-01 "다음 라우팅은 END" | 모든 워커는 `add_edge(worker, "quality_gate")` 무조건 간선. quality_gate 가 LLM 재시도 판정을 할 수 있다 | **게이트가 걸린 워커에만** 조건부 간선 `worker → {END, quality_gate}`. quality_gate·supervisor 둘 다 미경유. 비게이트 워커 간선 불변 |
| D-03 | FR-11 action 기본 | action 노드는 본문 키 미확정 시 격리(action-category-compose-node D-09) | **암묵 action**(카테고리 미지정 → 승인 필요로 승격)은 격리 대신 **react+게이트 폴백**. 명시 action 은 기존대로 격리 |
| D-04 | FR-07 react 본문 키 | 백엔드 `tool_configs[].draft_arg_key` 는 이미 저장됨(RagToolConfigRequest). 프론트 입력 없음 | react 게이트 미들웨어에 `draft_key` 전달, `ApprovalEditPolicy.extract_draft(args, draft_key=)` 우선 사용. 프론트 입력칸 신설 |
| D-05 | FR-03 템플릿 | 답변은 `stream()` 1곳(run_agent_use_case.py:335)에서 결정되고 동기 `run()`·웹훅·백그라운드가 stream 을 소비. 단, 워커 LLM 토큰이 TOKEN 이벤트(node_name=워커)로 이미 흘렀을 수 있음 | 답변 교체는 stream 단일 지점. TOKEN 표시는 Do 에서 프론트 확인 — 워커 노드 토큰을 채팅 본문에 누적한다면 ANSWER_COMPLETED 가 본문을 대체하는지 검증(§8 F3) |

---

## 1. Overview

### 1.1 Design Goals

1. 게이트 런의 **종료와 사용자 보고가 LLM 판단과 무관**하다.
2. 부작용 도구는 **설정 누락과 무관하게** 사람 승인 아래 있다.
3. 게이트 없는 에이전트는 **바이트 동일**(그래프 간선·supervisor 프롬프트·답변).
4. 규칙(문구·기본 게이트·안내·카테고리 승격)은 domain 에, 배선만 application 에.

### 1.2 Design Principles

- 런당 pending 1건 불변식(approval-gate FR-06) 유지 — 즉시 종료는 그 불변식의 구조적 강제다.
- 재개 런은 `_restore_state` 가 approval_pending 을 비우므로 새 간선에 걸리지 않는다.
- 특화 금지: 특정 도구(submit_reply)·키(reply_content) 하드코딩 없음.

---

## 2. Architecture

### 2.0 Architecture Comparison

| Criteria | A: Minimal | B: Clean | C: Pragmatic |
|---|:-:|:-:|:-:|
| Approach | route_after_quality 에 pending→END, 규칙 inline | GatedRunPolicy 통합 모듈 + 전용 엣지 빌더 + 전용 모달 | domain 정책 3개 + 게이트 워커 조건부 간선 + 답변 단일 지점 |
| New / Modified | ~1 / ~9 | ~8 / ~12 | ~4 / ~10 |
| quality_gate 경유 | 예(LLM 비용·재시도 위험) | 아니오 | 아니오 |
| 비게이트 바이트 동일 | 예 | 예 | 예 |

**Selected**: **Option C**.

### 2.1 Graph (depth=0)

```
supervisor ──route_to_worker_or_final──▶ worker_X (비게이트)  ──▶ quality_gate ──▶ supervisor
                                     └─▶ worker_G (게이트)    ──route_after_gated_worker──┬─ pending → END
                                                                                          └─ else    → quality_gate
```

`route_after_gated_worker(state) = END if state["approval_pending"] else "quality_gate"`.
analysis 워커(chart_router 경유)는 게이트 대상이 아니다(부작용 없음) — 기존 간선 유지.
depth>0(서브 에이전트 그래프)도 같은 규칙을 적용한다: 서브 그래프가 END 하면 부모 래퍼로 돌아가며, 부모 전파는 이번 범위 밖(§5 R-5).

### 2.2 Data Flow (게이트 런)

```
compile: effective_gate = ApprovalPolicy.effective_gate(applied_gate, has_gated_workers)   (E)
         category = _resolve_category(w) ; if None and gated → 암묵 action 시도 → 실패 시 react+gate   (F)
         react gate middleware(draft_key = tool_config.draft_arg_key)                          (D)
         supervisor workers = GatedWorkerHintPolicy.describe(w, gated_ids)                    (C)
         edges: gated worker → route_after_gated_worker                                       (A)
run:     supervisor → gated worker → approval_pending → END
stream():answer = ApprovalPendingNoticePolicy.render(pending) if state.approval_pending      (B)
         → 채팅 저장 / ANSWER_COMPLETED / approval_request 적재(기존)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `ApprovalPendingNoticePolicy` | `ApprovalEditPolicy.body_key`, `McpArgumentPolicy.unwrap` | 미리보기 본문 판정 |
| `ApprovalPolicy.effective_gate` | `GateSettings` | fail-closed 기본 게이트 |
| `GatedWorkerHintPolicy` | — | supervisor 워커 설명 접두 |
| `WorkflowCompiler` | 위 정책들 | 배선 |
| `RunAgentUseCase.stream` | `ApprovalPendingNoticePolicy` | 답변 교체 |

---

## 3. Domain Design

### 3.1 `ApprovalPendingNoticePolicy` — `src/domain/approval/notice_policy.py` (신규)

```python
class ApprovalPendingNoticePolicy:
    PREVIEW_MAX_CHARS: int = 300

    @classmethod
    def render(cls, *, tool_id: str, tool_args: dict, draft: str) -> str:
        """승인 대기 런의 사용자 답변. 입력만의 함수 — LLM·워커 텍스트 미사용."""
```

문구(확정):

```
요청하신 작업을 담당자 승인함에 올렸습니다. 아직 실행되지 않았습니다.
작업함 › 승인 대기에서 내용을 확인·수정한 뒤 승인하면 실제로 실행됩니다.

- 작업: {tool_label}
- 초안 미리보기:
{preview}
```

- `tool_label`: tool_id 의 마지막 `:` 세그먼트(`mcp:<uuid>:submit_reply` → `submit_reply`, `email_send` → 그대로).
- `preview`: `ApprovalEditPolicy.body_key(tool_args, draft)` 가 있으면 `draft[:300]` (초과 시 `…`), 없으면 `(본문은 승인 화면에서 확인하세요)` — JSON 원문을 채팅에 싣지 않는다.
- 각 줄 앞 공백 없이, 미리보기는 `> ` 인용 접두로 들여 Markdown 렌더.

### 3.2 `ApprovalPolicy.effective_gate` — `src/domain/approval/policies.py`

```python
@staticmethod
def effective_gate(applied: GateSettings | None, *, has_gated_workers: bool) -> GateSettings | None:
    """D-01: 적용 목록에 없어도 승인 필요 도구가 있으면 도메인 기본 게이트.
    applied 가 있으면(명시 off 포함) 그대로 — should_gate 가 off/enforced 를 판정."""
    if applied is not None or not has_gated_workers:
        return applied
    return GateSettings.from_config({}, is_enforced=False)
```

### 3.3 `GatedWorkerHintPolicy` — `src/domain/agent_builder/policies.py`

```python
class GatedWorkerHintPolicy:
    PREFIX = ("[승인 필요] 호출하면 즉시 실행되지 않고 담당자 승인함에 등록됩니다. "
              "사용자가 실행·등록을 요청하면 호출하세요. ")

    @classmethod
    def describe(cls, description: str, *, gated: bool) -> str:
        return f"{cls.PREFIX}{description}" if gated else description
```

### 3.4 `ApprovalEditPolicy.extract_draft(args, draft_key=None)` — 확장

`draft_key` 가 있고 unwrap 인자의 해당 값이 비어있지 않은 문자열이면 그 값을, 아니면 기존 관례 키 탐색 → JSON 폴백. (D-01 body_key 판정은 값 일치라 자동으로 편집 가능해진다.)

### 3.5 `ApprovalCategoryPolicy`(이름 확정: `GatedCategoryPolicy`) — `src/domain/agent_builder/policies.py`

```python
class GatedCategoryPolicy:
    @staticmethod
    def promote(category: str | None, *, gated: bool) -> tuple[str | None, bool]:
        """(effective_category, implicit). 미분류 + 게이트 → ("action", True). 그 외 불변."""
```

---

## 4. Application Wiring

### 4.1 `WorkflowCompiler.compile` (workflow_compiler.py)

| 위치 | 변경 |
|------|------|
| `:642` gate_settings | `gate_settings = ApprovalPolicy.effective_gate(_gate_settings(middleware_plan), has_gated_workers=_has_gated_workers(workflow.workers, gated_tool_ids))` + 기본 적용 시 `approval gate applied by default` info 로그(agent_id, tool_ids) |
| `:756` category | `gated = self._should_gate_worker(...)` 선계산 → `category, implicit = GatedCategoryPolicy.promote(self._resolve_category(...), gated=gated)` |
| `:827` action 분기 | `action_node is None and implicit` → 경고 `gated worker fallback to react` 후 react 경로로 진행(격리 안 함). 명시 action 은 기존대로 격리 |
| react 게이트 미들웨어 `:1305` | `build_for_worker(tool_id, worker_id, draft_key=ActionToolConfig.from_tool_config(worker_def.tool_config).draft_arg_key)` |
| supervisor 생성 `:994` | `gated_worker_ids=frozenset(...)` 전달 |
| 간선 `:1161` | `gated_worker_ids` 에 속한 워커(analysis 제외)는 `add_conditional_edges(worker_id, route_after_gated_worker, {"end": END, "quality_gate": "quality_gate"})` |

`gated_worker_ids` = 컴파일 중 `_should_gate_worker` 가 True 인 워커 id 집합(react·action 공통, 성공적으로 노드가 만들어진 것만).

### 4.2 `supervisor_nodes.py`

- `create_supervisor_node(..., gated_worker_ids: frozenset[str] = frozenset())` — `worker_descriptions` 조립에 `GatedWorkerHintPolicy.describe(w.description, gated=w.worker_id in gated_worker_ids)`. 기본값 빈 집합 → 바이트 동일.
- `route_after_gated_worker(state) -> str`: `"end" if state.get("approval_pending") else "quality_gate"`.

### 4.3 `gate_middleware.py`

`ApprovalGateMiddleware(tool_id, worker_id, draft_key=None)` → `_block` 에서 `ApprovalEditPolicy.extract_draft(args, draft_key=self._draft_key)`. `StatelessGate.build_for_worker` 에 `draft_key` 키워드 추가(기본 None). `ApprovalGateInterface` Protocol 시그니처 동기화.

### 4.4 `RunAgentUseCase.stream` (run_agent_use_case.py:335)

```python
answer, tools_used = self._parse_result({"messages": state.final_messages})
if state.approval_pending:
    # Plan FR-03/05: 승인 대기 런은 워커·LLM 텍스트를 답변으로 쓰지 않는다
    answer = ApprovalPendingNoticePolicy.render(
        tool_id=state.approval_pending.get("tool_id", ""),
        tool_args=state.approval_pending.get("tool_args") or {},
        draft=state.approval_pending.get("draft", ""),
    )
```

이후 채팅 저장·`_persist_approval_if_pending`·ANSWER_COMPLETED 는 기존 순서 그대로 → 모든 소비자(동기 run, 웹훅, 백그라운드 잡)가 같은 문구를 받는다. 강등 경로(:490 GraphRecursionError)는 pending 이 있을 수 없는 경로(즉시 종료)라 변경하지 않는다. 재개(`:944`)는 pending 이 비어 시작하므로 불변.

---

## 5. Frontend Design (D)

### 5.1 위치

`LeftConfigPanel` 선택 도구 행(`selectedTools.map`) — `tool.requires_approval === true` 인 도구 행 아래에 한 줄 입력:

```
┌ submit_reply  [MCP] [승인 필요]                        제거 ┐
│ 본문 인자  [ reply_content          ]  ⓘ 승인 화면에 본문으로 표시·수정할 인자 │
└────────────────────────────────────────────────────────────────┘
```

- 배지 `승인 필요`(amber). 입력은 선택(비우면 관례 키 자동 탐색).
- 값은 `form.toolConfigs[tool_id].draft_arg_key` 로 저장, 저장 시 기존 `tool_configs` 경로로 전송(백엔드 이미 수용).
- 타입: `RagToolConfig` 의존을 피해 `types/agentToolConfig.ts`(신규) `ActionToolConfig { draft_arg_key?: string | null }` 로 분리, `form.toolConfigs` 값 타입을 `RagToolConfig | ActionToolConfig` 유니온으로.

### 5.2 Page UI Checklist

#### AgentBuilder › 도구 목록
- [ ] Badge: `승인 필요` (requires_approval 도구만)
- [ ] Input: `본문 인자` (requires_approval 도구만, placeholder "비우면 body/content 등 자동")
- [ ] 저장 요청의 `tool_configs[tool_id].draft_arg_key` 반영, 빈 문자열은 null
- [ ] 비승인 도구 행 불변

#### 채팅 (에이전트 대화)
- [ ] 승인 대기 런의 최종 말풍선 = 템플릿 문구 (워커 토큰이 먼저 흘렀어도 최종 교체) — F3 검증

---

## 6. Error Handling / Logging

| Event | Level | Fields |
|-------|-------|--------|
| `approval gate applied by default` | info | agent_id, tool_ids |
| `gated worker compiled as action` | info | worker_id, tool_id, draft_key |
| `gated worker fallback to react` | warning | worker_id, tool_id, reason |
| `run ended on approval gate` | info | run_id, worker_id, tool_id |
| 기존 `approval gate attached` | info | 유지 |

값(본문·인자)은 로그에 싣지 않는다.

---

## 7. Security Considerations

- [ ] fail-closed: 승인 필요 도구는 에이전트 설정과 무관하게 게이트(명시 off 제외, enforced 는 off 를 이김)
- [ ] 즉시 종료로 게이트 이후 LLM 이 "성공" 을 서술할 경로 제거
- [ ] 템플릿 답변은 "아직 실행되지 않음" 을 명시 — 금융 데이터 상태 오인 방지
- [ ] 암묵 action 폴백 시에도 게이트는 부착(react+gate) — 무승인 경로 없음

---

## 8. Test Plan

### 8.1 Backend

| # | Target | Scenario | Expected |
|---|--------|----------|----------|
| B1 | NoticePolicy | body_key 있는 tool_args | 템플릿 + 인용 미리보기, 300자 절단 |
| B2 | NoticePolicy | JSON 폴백 초안 | 미리보기 대신 "(본문은 승인 화면에서 확인하세요)" |
| B3 | NoticePolicy | tool_label | `mcp:<uuid>:submit_reply` → `submit_reply` |
| B4 | effective_gate | applied None + gated | 도메인 기본(mode=always) |
| B5 | effective_gate | applied(off) + gated | applied 그대로 → should_gate False |
| B6 | effective_gate | applied None + 비게이트 | None |
| B7 | HintPolicy | gated / not | 접두 / 바이트 동일 |
| B8 | GatedCategoryPolicy | None+gated / "collect"+gated / None+not | ("action",True) / ("collect",False) / (None,False) |
| B9 | extract_draft | draft_key=reply_content, 래퍼 | 본문 |
| B10 | route_after_gated_worker | pending / 빈 dict | "end" / "quality_gate" |
| B11 | Compiler | 게이트 미들웨어 없음 + requires_approval 도구 | 게이트 부착(`approval gate attached`), 기본 적용 로그 |
| B12 | Compiler | 명시 off | 게이트 미부착 |
| B13 | Compiler | 미분류 게이트 도구 + draft_arg_key 설정 | action 노드 |
| B14 | Compiler | 미분류 게이트 도구 + 키 미확정 | react+게이트 폴백, 격리 안 됨 |
| B15 | Compiler | 명시 action + 키 미확정 | 기존대로 격리 |
| B16 | Graph 통합 | react 게이트 워커가 pending 반환 | 워커 실행 1회, supervisor·quality_gate·final_answer 재진입 0, END |
| B17 | Graph 통합 | 비게이트 에이전트 | 간선·supervisor 프롬프트 바이트 동일(스냅샷) |
| B18 | stream | pending + 워커가 가짜 JSON 출력 | 저장 답변·ANSWER_COMPLETED = 템플릿, approval_pending=true |
| B19 | stream | pending 없음 | 답변 기존과 동일 |
| B20 | Resume | `_restore_state` 후 재개 런 | 새 간선 영향 없음(pending 빈 상태) |
| B21 | react 게이트 미들웨어 | draft_key 전달 | 마커 draft = 본문 |

### 8.2 Frontend

| # | Target | Scenario | Expected |
|---|--------|----------|----------|
| F1 | LeftConfigPanel | requires_approval 도구 | `승인 필요` 배지 + `본문 인자` 입력 |
| F2 | 저장 payload | 입력 `reply_content` / 빈 값 | `tool_configs[id].draft_arg_key` = 값 / null |
| F3 | 채팅 렌더 | 워커 TOKEN 후 ANSWER_COMPLETED(템플릿) | 최종 말풍선 = 템플릿 (필요 시 수정) |
| F4 | 비승인 도구 | 렌더 | 기존과 동일 |

### 8.3 L3 실런 (문의 답변 에이전트 `8421828f…`)

1. 게이트 미들웨어 제거 상태에서 "63116 답변 등록해줘" → 승인함 1건, MCP 미호출(E)
2. `draft_arg_key=reply_content` 설정 → 같은 요청 ×3 → 매회 승인함 1건, 워커 1회, 채팅 = 템플릿, 초안 = 본문, 드로어 `수정` 활성
3. 승인 → 63116 `reply` 채워짐, 재개 답변 정상

---

## 9. Clean Architecture — Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `ApprovalPendingNoticePolicy` | Domain | `src/domain/approval/notice_policy.py` (신규) |
| `ApprovalPolicy.effective_gate` | Domain | `src/domain/approval/policies.py` |
| `ApprovalEditPolicy.extract_draft(draft_key)` | Domain | `src/domain/approval/edit_policy.py` |
| `GatedWorkerHintPolicy`, `GatedCategoryPolicy` | Domain | `src/domain/agent_builder/policies.py` |
| 간선·카테고리·게이트 배선 | Application | `workflow_compiler.py`, `supervisor_nodes.py` |
| react 게이트 draft_key | Application | `gate_middleware.py`, `gate_interface.py` |
| 답변 교체 | Application | `run_agent_use_case.py` |
| 본문 인자 입력 | Front | `LeftConfigPanel.tsx`, `types/agentToolConfig.ts`, `AgentBuilderPage` 매핑 |

---

## 10. Coding Convention Reference

- 함수 40줄 / if 중첩 2단계 — compile 루프는 헬퍼(`_gated_category`, `_gated_edges`)로 분리
- `# Design Ref: approval-gate-run-termination §N` 주석
- 프론트 상수는 `src/types/*.ts`

---

## 11. Implementation Guide

### 11.1 Order

1. Domain 정책 + 테스트 (B1–B10, B21 일부)
2. 게이트 해석·카테고리·미들웨어 draft_key (B11–B15, B21)
3. 간선·supervisor 안내 (B16, B17, B20)
4. 답변 템플릿 (B18, B19)
5. 프론트 (F1–F4) → L3

### 11.2 File Change Summary

| 구분 | 파일 |
|------|------|
| 신규 (BE) | `src/domain/approval/notice_policy.py`, `tests/domain/approval/test_notice_policy.py`, `tests/application/agent_builder/test_gated_run_termination.py` |
| 수정 (BE) | `domain/approval/{policies,edit_policy}.py`, `domain/agent_builder/policies.py`, `application/agent_builder/{workflow_compiler,supervisor_nodes,run_agent_use_case}.py`, `application/approval/{gate_middleware,gate_interface}.py` |
| 신규 (FE) | `src/types/agentToolConfig.ts` |
| 수정 (FE) | `components/agent-builder/LeftConfigPanel.tsx`(+test), `pages/AgentBuilderPage/index.tsx`, 필요 시 채팅 토큰 렌더 |

### 11.3 Session Guide

| Module | Scope Key | 내용 | 테스트 |
|--------|-----------|------|--------|
| 도메인 정책 | `module-1` | Notice / effective_gate / Hint / GatedCategory / extract_draft(draft_key) | B1–B10, B9 |
| 컴파일 배선 | `module-2` | fail-closed 게이트, 암묵 action + 폴백, react draft_key | B11–B15, B21 |
| 종료·안내·답변 | `module-3` | 조건부 간선, supervisor 안내, stream 답변 교체 | B16–B20 |
| 프론트 | `module-4` | 본문 인자 입력·배지, 채팅 최종 답변 확인 | F1–F4 |

| Session | Scope |
|---------|-------|
| 1 | `--scope module-1,module-2` |
| 2 | `--scope module-3` + 백엔드 전체 회귀 |
| 3 | `--scope module-4` + L3 실런 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-30 | Initial — Option C, D-01~D-05 | 배상규 |
