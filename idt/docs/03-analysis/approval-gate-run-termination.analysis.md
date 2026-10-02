# approval-gate-run-termination Gap Analysis

> **Date**: 2026-09-30 | **Phase**: Check | **Match Rate**: 84.6% (runtime 공식)
> **Plan**: [plan](../01-plan/features/approval-gate-run-termination.plan.md) · **Design**: [design](../02-design/features/approval-gate-run-termination.design.md)
> 분석: bkit:gap-detector (정적 + L3 실런 3회 근거) · 메인 세션 재확인: G1(실런 469872a7 재현), G2(collect/search 파이프라인에 게이트 코드 부재 확인)

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 게이트는 막았는데 런이 안 끝나고, 채팅엔 가짜 "등록 성공" 이 나가며, 게이트 미설정 에이전트는 무승인 DB 변경이 가능하다 — 사용자가 본 상태와 실제 상태가 어긋난다. |
| **WHO** | P2 — 부작용 도구(문의 답변 등록·메일 발송 등)를 가진 에이전트의 소유자/승인자, 그리고 그 채팅 사용자. |
| **RISK** | 즉시 종료·action 기본화가 기존 게이트/비게이트 에이전트 라우팅을 바꿀 수 있음 → 비게이트 경로 바이트 동일 회귀 테스트. fail-closed 기본 적용이 기존 에이전트 동작을 바꿈(승인 대기로 전환) → 명시적 mode=off 존중 + 릴리스 노트. |
| **SUCCESS** | 게이트 런에서 게이트 워커 호출 정확히 1회·supervisor 재진입 0 / 승인 대기 런 채팅 답변 = 템플릿(LLM 텍스트 0) / "등록해줘" 류 요청 시 게이트 워커 라우팅 / 게이트 미설정 + 승인 필요 도구 → 승인 대기 생성(무승인 실행 0) / `reply_content` 도구 초안 = 본문, 수정 후 승인 가능 / 비게이트 에이전트 회귀 0. |
| **SCOPE** | A 종료 → B 응답 템플릿 → E fail-closed → C 워커 안내 → D react 본문 키 → F action 기본 (+ 프론트: D 설정 입력). |

---

# approval-gate-run-termination — Gap Analysis (Check)

> Analysis Date: 2026-09-30 · Branch: feature/approval-edit-before-approve (uncommitted)
> Plan: idt/docs/01-plan/features/approval-gate-run-termination.plan.md
> Design: idt/docs/02-design/features/approval-gate-run-termination.design.md
> Formula (runtime): Structural×0.15 + Functional×0.25 + Contract×0.25 + Runtime×0.35

## Context Anchor

| Key | Value |
|-----|-------|
| WHY | 게이트는 막았는데 런이 안 끝나고, 채팅엔 가짜 "등록 성공"이 나가며, 게이트 미설정 에이전트는 무승인 DB 변경이 가능하다 |
| WHO | P2 — 부작용 도구를 가진 에이전트 소유자/승인자, 채팅 사용자 |
| RISK | 즉시 종료·action 기본화의 라우팅 회귀, fail-closed 기본 적용에 따른 동작 변화 |
| SUCCESS | 게이트 워커 1회·재진입 0 / 템플릿 답변 / "등록해줘" 라우팅 / 무승인 실행 0 / reply_content 초안 편집 가능 / 비게이트 회귀 0 |
| SCOPE | A 종료 → B 템플릿 → E fail-closed → C 안내 → D 본문 키 → F action 기본 (+FE D 입력) |

## 1. Scores

| Axis | Score | Notes |
|------|:-----:|-------|
| Structural | 97% | 설계 §11.2 파일 전부 존재. `src/types/agentToolConfig.ts` 미생성(의도된 편차 #1) |
| Functional | 90% | FR-01~11 구현. FR-12 부분(스키마 키 후보 미제시), FR-13 부분(`run ended on approval gate` 로그에 run_id 누락). 게이트 힌트가 게이트 없는 search/collect 워커에도 붙음(G2) |
| Contract | 92% | FE `tool_configs[id].draft_arg_key` ↔ BE `RagToolConfigRequest.draft_arg_key` 일치, 빈 값→null 삭제 OK, MCP 도구 수정모드 round-trip OK. internal 도구 키 형식 불일치(G6), RAG config 덮어쓰기(G7) |
| Runtime | 70% | 회귀 BE 10135 pass/53 known, FE 1327 pass/9 known, tsc 기준선, eslint 신규 0. L3: 수정 후 2런 중 1런 성공(0a4a2629), 1런 인자 조립 실패(469872a7) |
| **Overall Match Rate** | **84.6%** | 97×0.15 + 90×0.25 + 92×0.25 + 70×0.35 = 14.55 + 22.5 + 23.0 + 24.5 |

판정: 70% ≤ Overall < 90% → Act 반복 권장 (G1, G2 우선).

## 2. Success Criteria

| SC | Status | Evidence |
|----|:------:|----------|
| SC-1 게이트 워커 1회, supervisor/final_answer 재진입 0 | ✅ Met (depth=0) | workflow_compiler.py:1192-1198 조건부 간선, supervisor_nodes.py:690-698 `route_after_gated_worker`; test_gated_run_termination.py:53 (B16), :66 간선; L3 0a4a2629 워커 1회. 서브에이전트(depth>0) 경로는 미보장(G3) |
| SC-2 채팅 저장·스트림 answer = 템플릿 | ✅ Met | run_agent_use_case.py:336 `_resolve_answer` → :344 저장, :367 ANSWER_COMPLETED 단일 지점; :1410-1431; test :141 (B18, 가짜 JSON), :163 (B19); L3 0a4a2629 답변 == 템플릿 |
| SC-3 "63116 답변 등록해줘" 3/3 게이트 워커 호출·승인함 1건 | ⚠️ Partial | 1686f0c2(Act-1 전) 0건, 469872a7 action 인자 조립 실패 0건, 0a4a2629 성공 1건 → 수정 후 1/2. Act-1 SUFFIX/RULE_BLOCK으로 라우팅은 개선, 인자 조립 불안정(G1) |
| SC-4 게이트 미들웨어 없는 에이전트 + requires_approval → 승인 대기, MCP 미호출 | ✅ Met (정적) | policies.py:59-71 `effective_gate`; workflow_compiler.py:647, :1352-1371 (+`approval gate applied by default` 로그); test_gated_compile.py:62 (B11), test_notice_policy.py:63. 단, category=search/collect로 명시된 승인 필요 도구는 여전히 무게이트(G2), L3 §8.3-1(미들웨어 제거 실런) 별도 증거 없음 |
| SC-5 draft_arg_key=reply_content → draft = 본문, editable=true | ✅ Met | edit_policy.py:42-58, gate_middleware.py:69, workflow_compiler.py:1394-1402; test_gated_compile.py:143/157 (B21), test_notice_policy.py:82-91; L3 0a4a2629 draft=reply_content 본문, body_key=reply_content, editable=true |
| SC-6 미분류 승인 필요 도구 → action / 키 미확정 → react+게이트 폴백 | ✅ Met | policies.py:577-591 `GatedCategoryPolicy`; workflow_compiler.py:765-770, :852-857, :1327-1343; test_gated_compile.py:98 (B13), :112 (B14), :130 (B15); L3 로그 "gated worker compiled as action" |
| SC-7 비게이트 회귀 0, 상시 실패 목록 외 실패 0 | ✅ Met | 전체 회귀 결과(BE 53 / FE 9 모두 known list); test_gated_run_termination.py:76 (B17 간선), :112 (비게이트 프롬프트 바이트 동일), test_gated_worker_policies.py:20 |

Success Rate: 6/7 Met (SC-3 Partial).

## 3. Design Test Plan Coverage

| Test | Status | Location |
|------|:------:|----------|
| B1–B3 NoticePolicy | ✅ | tests/domain/approval/test_notice_policy.py:20-57 |
| B4–B6 effective_gate | ✅ | test_notice_policy.py:63-76 |
| B7 HintPolicy | ✅ | tests/domain/agent_builder/test_gated_worker_policies.py:13-23 |
| B8 GatedCategoryPolicy | ✅ | test_gated_worker_policies.py:40 |
| B9 extract_draft(draft_key) | ✅ | test_notice_policy.py:82-91 |
| B10 route_after_gated_worker | ✅ | test_gated_run_termination.py:38-44 |
| B11–B15 Compiler | ✅ | tests/application/agent_builder/test_gated_compile.py:62-139 |
| B16 Graph 통합 | ⚠️ | :53 — action 노드 경로만. Design은 react 게이트 워커 기준 |
| B17 비게이트 스냅샷 | ⚠️ | 간선+워커 설명만 검증, 전체 프롬프트 스냅샷 아님 |
| B18 stream | ⚠️ | `_resolve_answer` 단위만, stream()의 저장/ANSWER_COMPLETED 통합 미검증(L3로 보완) |
| B19–B21 | ✅ | :163, :172, test_gated_compile.py:143-169 |
| F1, F4 | ✅ | LeftConfigPanel.test.tsx:311-339 |
| F2 | ✅ | utils/toolConfigPayload.test.ts |
| F3 | ⏸ 의도적 미변경 | 편차 #2 — 스트리밍 중 워커 토큰 잠깐 노출 가능, 최종 말풍선은 ANSWER_COMPLETED로 교체 |
| L3 §8.3 | ⚠️ | ②만 부분 수행(1/2 성공), ①(미들웨어 제거)·③(승인→reply 채워짐) 미확인 |

## 4. Intentional Deviations — 평가

| # | Deviation | 평가 |
|---|-----------|------|
| 1 | `draftArgKeys` 별도 필드, 저장 시 병합 | 수용. 단 병합 시 키 형식·RAG config 덮어쓰기 부작용(G6, G7) |
| 2 | F3 채팅 토큰 미변경 | 수용(최종 답변은 교체). 수동 확인 1회 권장 |
| 3 | Act-1 SUFFIX + RULE_BLOCK | 수용(실측 근거). Design §3.3 미반영 → 문서 갱신 필요. RULE_BLOCK의 "반드시 호출하세요"가 G2와 결합하면 무승인 실행을 부추김 |

## 5. Gaps (confidence ≥ 80%)

### Critical

**G1 — action 인자 조립 LLM이 본문을 arguments_json에 넣어 파싱 실패 → 승인 0건 (SC-3 위반)**
- 위치: idt/src/application/agent_builder/action_pipeline.py:155-163 (`_argument_user_content`가 전체 draft와 draft_key가 포함된 전체 스키마를 전달), :182-189 (파싱 실패 즉시 종료, 재시도 없음)
- 증거: L3 469872a7 "발송 인자 생성 실패: 생성된 인자를 해석할 수 없습니다"
- F(암묵 action 기본화)로 모든 승인 필요 도구가 이 파이프라인을 타게 되어 이 기능의 핵심 경로가 됨. 실패는 fail-closed(무승인 실행 없음)이나 사용자 요청이 조용히 누락됨.
- Fix: (1) 조립 LLM에 넘기는 스키마에서 `properties[draft_key]`와 `required`의 draft_key 제거, (2) 프롬프트의 draft 원문을 `[초안: N자 — 본문 필드는 시스템이 채움]` 요약으로 대체, (3) 파싱 실패 시 1회 재시도 후 실패, (4) 반환 인자에 draft_key가 있으면 버리고 draft로 덮어쓰기. FakeLLM이 긴 본문 포함 깨진 JSON을 반환하는 회귀 테스트 추가.

### Important

**G2 — 게이트 없는 search/collect 워커에도 "[승인 필요]" 힌트·규칙 블록이 붙음 → 무승인 즉시 실행 유도**
- 위치: workflow_compiler.py:1014-1018 (`gated_worker_ids` = `_should_gate_worker` True인 모든 워커), :865-888 + :1485-1521 (search/collect 노드는 게이트 미들웨어 없음), policies.py:577-591 (`promote`는 category None일 때만 승격)
- 카탈로그에서 category=collect/search이면서 requires_approval=true인 도구는 supervisor에 "호출하면 승인함에 등록"·"반드시 호출하세요"라고 안내되지만 실제로는 승인 없이 즉시 실행됨. Design §4.1("react·action 공통")과 FR-08/보안 §7("무승인 경로 없음")에 어긋남. analysis 카테고리도 힌트가 붙음(부작용은 없음).
- Fix: `GatedCategoryPolicy.promote`에서 gated이고 category ∈ {search, collect}이면 ("action", True)로 승격(또는 react+gate), 그리고 `gated_worker_ids`는 컴파일 루프에서 실제 게이트가 부착된 워커(react+gate middleware / action gated=True)만 모으는 집합으로 계산.

**G3 — 서브에이전트(depth>0): 명시 off 무시 + approval_pending 미전파**
- 위치: workflow_compiler.py:630-634 (middleware_plan은 depth==0에서만 준비) → :647 `effective_gate(None, has_gated_workers=True)` = 항상 도메인 기본 게이트; :2481-2525 `_wrap_sub_agent`는 `approval_pending`을 반환하지 않음
- 결과: (a) 부모·자식 에이전트가 approval_gate mode=off여도 서브에이전트의 승인 필요 도구는 항상 게이트(FR-09 불일치), (b) 서브 그래프가 END해도 부모는 quality_gate→supervisor로 계속 진행(SC-1 구조적 보장이 서브에이전트에서 깨짐), (c) pending 적재는 중첩 chain_end 이벤트 캡처(run_agent_use_case.py:1071-1072)에 암묵적으로 의존하며, 스냅샷 worker_id가 부모 그래프에 없는 서브 워커임. Design §2.1은 "부모 전파는 범위 밖(§5 R-5)"이라 했지만 §5 R-5 항목은 존재하지 않음.
- Fix: 부모의 해석된 gate_settings(또는 서브에이전트 자신의 plan)를 `_compile_sub_agent`에 전달; `_wrap_sub_agent`가 `result.get("approval_pending")`을 반환하고, 게이트 워커를 가진 서브에이전트 워커는 부모의 `gated_worker_ids`에 포함해 END 간선을 태움. 또는 범위 밖으로 명시하고 가드 테스트 + Design 리스크 항목을 추가.

### Minor

**G4 — 템플릿 답변 저장이 승인 적재보다 먼저**: run_agent_use_case.py:344-357. 적재 실패(예외)나 미배선(:965-970에서 None 반환) 시 채팅에는 "승인함에 올렸습니다"가 남지만 승인 건이 없음 — 이 기능의 핵심 가치("말하는 상태 = 실제 상태")에 반함. Fix: `_persist_approval_if_pending`을 먼저 호출하고, approval_id가 있을 때만 notice를 쓰며 없으면 "승인 요청 등록에 실패했습니다" 폴백.

**G5 — FR-13 로그 필드 누락**: run_agent_use_case.py:1422-1425의 `run ended on approval gate`에 Design §6이 요구하는 run_id가 없고 request_id도 없음. Fix: `_resolve_answer(state, run_id=..., request_id=...)`로 넘겨 로그에 포함.

**G6 — FE 수정모드 본문 인자 키 형식 불일치(internal 도구)**: utils/agentDetailMapping.ts:68은 저장 형식 `X`로 키를 잡는데 LeftConfigPanel.tsx:432와 AgentBuilderPage/index.tsx:438은 카탈로그 형식 `internal:X`를 씀. 승인 필요 internal 도구는 프리필이 비어 보이고 제거 시 정리도 안 됨(MCP 도구는 두 형식이 같아 정상). Fix: `mapDraftToolIdsToCatalog([w.tool_id], catalogTools)[0]`로 키 변환.

**G7 — RAG config 덮어쓰기**: utils/toolConfigPayload.ts:17 `merged[toolId] = { draft_arg_key }`가 같은 도구의 RAG 설정을 대체 → 서버는 RagToolConfigRequest 기본값(top_k=5, kb_id=None…)으로 저장. RAG 도구에 requires_approval이 켜졌을 때만 발생. Fix: `{ ...(toolConfigs[toolId] ?? {}), draft_arg_key: raw.trim() || null }`.

**G8 — FR-12 "스키마 키 후보 제시" 미구현**: LeftConfigPanel.tsx:429-436이 일반 텍스트 입력. 오타 키 → 암묵 action 폴백 → react 게이트 JSON 초안(editable=false)으로 조용히 저하. Fix: 도구 input_schema properties 기반 datalist/셀렉트, 또는 저장 시 검증 경고.

**G9 — 테스트·문서 동기화**: B16(react 래퍼 경로), B17(전체 프롬프트 스냅샷), B18(stream 통합) 보강 필요; Design에 Act-1 SUFFIX/RULE_BLOCK, draftArgKeys 편차, agentToolConfig.ts 미생성, 존재하지 않는 §5 R-5 참조를 반영.

## 6. Recommended Actions

1. G1 (Critical): 인자 조립에서 본문 필드 제외 + 재시도 → L3 ×3 재실행(SC-3 3/3 목표)
2. G2: search/collect 승인 필요 도구 승격 + `gated_worker_ids`를 실제 부착 기준으로
3. G3: 서브에이전트 게이트 해석·pending 전파 결정(구현 또는 명시적 범위 제외 + 가드 테스트)
4. G4–G8 소규모 수정, G9 Design v0.2 갱신(`/pdca iterate` 후 재Check)

## 7. Runtime Verification Plan (next Check)

| # | Level | Scenario | Expected |
|---|-------|----------|----------|
| 1 | L3 | 8421828f, "63116 글을 읽고 답변까지 등록해줘" ×3 (G1 수정 후) | 매회 승인 1건, 워커 1회, 답변 == 템플릿, draft == reply_content |
| 2 | L3 | 같은 에이전트, approval_gate 미들웨어 제거 | 승인 1건, MCP submit_reply 미호출, 로그 `approval gate applied by default` |
| 3 | L3 | 승인 → 재개 | 63116 reply 채워짐, 재개 답변 정상 |
| 4 | Unit | collect 카테고리 + requires_approval 도구 | 게이트 부착 또는 힌트 미부착 (G2) |
| 5 | Unit | 서브에이전트에 게이트 도구 | 부모 런 END + pending 전파 (G3) |
| 6 | FE | 채팅: 워커 TOKEN 후 ANSWER_COMPLETED(템플릿) | 최종 말풍선 = 템플릿 (F3) |

---

## Act-2 (2026-09-30) — Critical + Important 수정

사용자 결정: "Critical+Important 수정" (Minor G4~G9 는 리포트 이월).

| Gap | 조치 | 증거 |
|-----|------|------|
| **G1** 인자 조립 파싱 실패 → 요청 소실 | 보조 LLM 에 넘기는 스키마에서 본문 키 제거(`_schema_without`), 프롬프트에 초안 원문 대신 "'{key}' 필드는 초안 N자가 자동 주입" 안내, 파싱 실패 시 1회 재시도(`_ARGUMENT_PARSE_RETRIES`). grounded=false 는 재시도 안 함 | `action_pipeline.py` · `tests/application/agent_builder/test_action_argument_assembly.py` 6건 |
| **G2** search/collect 승인 필요 도구 무승인 실행 | `GatedCategoryPolicy._PROMOTABLE = {None, search, collect}` → 암묵 action(실패 시 react+게이트 폴백). 안내 대상에서 analysis 제외 | `domain/agent_builder/policies.py`, `workflow_compiler.py` · `test_gated_worker_policies.py`(파라미터 7), `test_gated_compile.py::TestGatedCollectCategory` 2건 |
| **G3** 서브 에이전트 게이트 신호 미전파 | `_wrap_sub_agent` 가 `approval_pending` 을 부모 워커 id 로 올림, 서브 에이전트 워커는 항상 조건부 간선(신호 없으면 quality_gate — 기존과 동일) | `workflow_compiler.py` · `test_gated_run_termination.py::TestSubAgentGate` 3건 |

한계(문서화): depth>0 에서는 서브 에이전트 자신의 미들웨어 계획을 해석하지 않으므로 명시 `mode=off` 대신 도메인 기본 게이트가 적용된다 — 안전 방향(fail-closed)의 편차.

### L3 재확인 (문의 답변 에이전트, "63116 글을 읽고 답변까지 등록해줘" ×3, 에이전트 수정 없음)

| # | run_id | 채팅 = 템플릿 | 승인 건 | editable / body_key | 초안 1877-9900 |
|---|--------|:---:|:---:|:---:|:---:|
| 1 | 68d8dc07 | ✅ | 1 | ✅ / reply_content | 없음 |
| 2 | fc86821f | ✅ | 1 | ✅ / reply_content | 없음 |
| 3 | 1556c37a | ✅ | 1 | ✅ / reply_content | 없음 |

로그: `gated worker compiled as action` ×3, `run ended on approval gate` ×3, 인자 파싱 재시도 0 (본문 제외만으로 해소). **SC-3: 3/3 Met.**

회귀: 백엔드 10150 passed / 53 failed (상시 실패 목록과 파일·건수 동일). 프론트는 Act-2 변경 없음(직전 1327 passed / 9 상시 실패).

### 재산정

| Axis | Before | After | 근거 |
|------|:------:|:-----:|------|
| Structural | 97% | 97% | 변동 없음 |
| Functional | 90% | 93% | G1·G2·G3 해소. FR-12(스키마 키 후보)·FR-13(run_id 로그) 부분 — Minor |
| Contract | 92% | 92% | G6·G7 (Minor) 잔존 |
| Runtime | 70% | 95% | L3 3/3, 회귀 0. 미실행: 게이트 미들웨어 제거 L3(SC-4 런타임) |
| **Overall** | 84.6% | **94.1%** | 97×0.15 + 93×0.25 + 92×0.25 + 95×0.35 |

Success Criteria: **7/7 Met** (SC-3 3/3, SC-4 은 정적·단위 테스트 근거).

### 이월 (Minor)
- G4 승인 적재 실패 시에도 템플릿 문구 — 적재 성공 시에만 문구
- G5 종료 로그 run_id/request_id
- G6 내부 도구 draftArgKeys 키 형식(카탈로그 id 매핑)
- G7 RAG 설정과 draft_arg_key 병합 시 덮어쓰기
- G8 본문 인자 스키마 키 후보 UI
- G9 테스트 보강(B16 react, B18 stream 전체) + Design 문서에 Act-1 SUFFIX/RULE_BLOCK·draftArgKeys 편차 반영
