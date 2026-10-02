# approval-gate-run-termination Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: —
> **Author**: 배상규
> **Completion Date**: 2026-09-30
> **PDCA Cycle**: #1 (Act 2회)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | approval-gate-run-termination — 승인 게이트 런 종료·응답·라우팅·보호 기본값 |
| Start Date | 2026-09-29 |
| End Date | 2026-09-30 |
| Duration | 2일 (Plan → Design → Do 4모듈 → L3 → Act-1 → Check → Act-2) |
| Depends on | approval-gate, approval-gate-phase2-mcp-executor, action-category-compose-node, approval-edit-before-approve |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 94.1%  (84.6% → Act-2 → 94.1%) │
├─────────────────────────────────────────────┤
│  ✅ SC Met:          7 / 7                   │
│  ✅ L3 실런:         3 / 3 승인 대기 생성     │
│  ⏳ Minor carry:     6 (G4~G9)               │
│  ❌ Cancelled:       0                       │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 실측(2026-09-29): 게이트 차단 후 supervisor 가 등록 워커를 최대 5회 반복 호출, 워커 LLM 이 지어낸 "성공 JSON" 이 채팅에 저장(실제 63116 `reply: null`), 도구 설명("승인 전에 호출하지 마십시오") 때문에 "등록해줘" 에도 미호출, 게이트 미설정 에이전트는 승인 필요 도구를 **무승인 실행** 가능, react 워커 본문 키 부재로 수정 후 승인 불가. |
| **Solution** | 게이트 워커 직후 조건부 END / 승인 대기 답변 = 결정적 템플릿 / 게이트 미설정이어도 승인 필요 도구는 도메인 기본 게이트(fail-closed) / 미분류·search·collect 승인 필요 도구는 초안 작성 노드(action)로 승격(실패 시 react+게이트) / supervisor 게이트 안내(접두·접미·규칙 블록) / react·action 본문 키(`draft_arg_key`) + 빌더 입력 / 인자 조립에서 본문 제외 + 재시도 / 서브 에이전트 신호 전파. |
| **Function/UX Effect** | "63116 글을 읽고 답변까지 등록해줘" → 조회 → 초안 작성 → 승인함 1건 → 채팅 "요청하신 작업을 담당자 승인함에 올렸습니다. 아직 실행되지 않았습니다 + 초안 미리보기" — **L3 3/3 재현**. 초안 = `reply_content` 본문, 드로어 수정 가능. 빌더에 `승인 필요` 배지·`본문 인자` 입력. 신규 테스트 BE 50·FE 13. |
| **Core Value** | 금융 데이터 변경 경로에서 **"시스템이 말하는 상태 = 실제 상태"**. 부작용 도구는 설정 누락·도구 설명 문구·워커 분류와 무관하게 **기본적으로 사람 승인 아래**. 특정 도구·키 하드코딩 없이 일반 적용. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 게이트 워커 1회 실행, supervisor/final_answer 재진입 0 | ✅ Met | `test_gated_run_termination.py` B16(결정 1개로 종료), L3 로그 `run ended on approval gate` ×3 |
| SC-2 | 승인 대기 런 답변 = 템플릿 (워커 가짜 JSON 무관) | ✅ Met | B18(`_resolve_answer`), L3 3/3 `answer_is_template=true` |
| SC-3 | "63116 답변 등록해줘" → 게이트 워커 호출·승인함 1건 | ✅ Met (3/3) | L3 runs 68d8dc07 / fc86821f / 1556c37a |
| SC-4 | 게이트 미설정 + 승인 필요 도구 → 승인 대기, MCP 미호출 | ✅ Met (정적·단위) | `ApprovalPolicy.effective_gate`, `test_gated_compile.py::TestFailClosedGate` (L3 무미들웨어 시나리오는 미실행) |
| SC-5 | `draft_arg_key=reply_content` → 초안 = 본문, editable | ✅ Met | B9/B21, L3 `body_key=reply_content`, `editable=true` ×3 |
| SC-6 | 미분류 승인 필요 도구 action 컴파일 / 미확정 시 react+게이트 폴백 | ✅ Met | `test_gated_compile.py` B13/B14/B15 + G2 collect 케이스, L3 `gated worker compiled as action` ×3 |
| SC-7 | 비게이트 에이전트 회귀 0 | ✅ Met | BE 10150 passed / 53 상시 실패, FE 1327 / 9 상시 실패, tsc 210 기준선, B17 간선 불변 |

**Success Rate**: 7/7 (100%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 워커 직후 즉시 종료 | ✅ | 게이트 워커에만 조건부 간선 — 비게이트 그래프 불변 |
| [Plan] | 고정 템플릿 + 초안 미리보기 | ✅ | `ApprovalPendingNoticePolicy`, JSON 폴백 초안은 미리보기 생략 |
| [Plan] | fail-closed = 실행 시 기본 적용 | ✅ | D-01 도메인 기본값 → 적재·승인 해석 자동 일치 |
| [Plan] | C·D·E·F 전부 포함 | ✅ | C 는 Act-1 에서 보강(접미·규칙 블록) |
| [Design] | Option C (domain 정책 + 배선 + 단일 지점) | ✅ | 신규 domain 정책 3종, 답변 교체 `stream()` 1곳 |
| [Design] | D-03 암묵 action 폴백(격리 안 함) | ✅ | Act-2 G2 로 search/collect 까지 확장 |
| [Design] | D-04 기존 `draft_arg_key` 재사용 | ✅ | 스키마 변경 0. 프론트는 `draftArgKeys` 별도 필드(편차, 타입 파급 회피) |
| [Act-1] | 접두만으로 부족 → 접미 + supervisor 규칙 블록 | ✅ | L3 에서 미호출 → 호출로 전환 확인 |
| [Act-2] | 인자 조립에서 본문 제외 + 재시도 | ✅ | L3 3/3, 재시도 0 회 발생 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [approval-gate-run-termination.plan.md](../01-plan/features/approval-gate-run-termination.plan.md) | ✅ v0.2 |
| Design | [approval-gate-run-termination.design.md](../02-design/features/approval-gate-run-termination.design.md) | ✅ v0.1 (Act-1/편차 반영은 G9 이월) |
| Check | [approval-gate-run-termination.analysis.md](../03-analysis/approval-gate-run-termination.analysis.md) | ✅ 84.6% → 94.1% |
| Act | Current document | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01/02 | 게이트 신호 시 즉시 END, 게이트 워커 1회 | ✅ | react·action·서브에이전트(G3) |
| FR-03~05 | 승인 대기 답변 템플릿, 모든 소비자 동일 | ✅ | `_resolve_answer` 단일 지점 |
| FR-06 | supervisor 게이트 워커 안내 | ✅ | 접두 + 접미 + 규칙 블록(Act-1) |
| FR-07 | react 본문 키 | ✅ | `ApprovalGateMiddleware(draft_key)` |
| FR-08~10 | fail-closed 기본 게이트, 명시 off 존중 | ✅ | depth>0 은 기본 게이트(안전 방향 한계) |
| FR-11 | 승인 필요 도구 action 기본 + 폴백 | ✅ | 미분류·search·collect |
| FR-12 | 빌더 본문 인자 입력 | ⚠️ 부분 | 텍스트 입력 — 스키마 후보(G8) 이월 |
| FR-13 | 관측 로그 | ⚠️ 부분 | 종료 로그 run_id 누락(G5) 이월 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 비게이트 회귀 | 바이트 동일 | 간선·프롬프트 불변 테스트, 전체 회귀 상시 목록 동일 | ✅ |
| 결정성 | 승인 대기 답변 = 입력 함수 | NoticePolicy 순수 함수 | ✅ |
| 안전 | 무승인 부작용 경로 0 | fail-closed + search/collect 승격(G2) | ✅ |
| 비용 | 게이트 런 LLM 호출 감소 | supervisor 재진입·final_answer 제거 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| Domain | `domain/approval/notice_policy.py`(신규), `policies.py`(effective_gate), `edit_policy.py`(draft_key), `domain/agent_builder/policies.py`(GatedWorkerHintPolicy·GatedCategoryPolicy) | ✅ |
| Application | `workflow_compiler.py`(기본 게이트·승격·폴백·조건부 간선·서브에이전트), `supervisor_nodes.py`(안내·route), `run_agent_use_case.py`(`_resolve_answer`), `action_pipeline.py`(인자 조립), `approval/gate_middleware.py`·`gate_interface.py` | ✅ |
| Frontend | `utils/toolConfigPayload.ts`, `types/agentBuilder.ts`, `LeftConfigPanel.tsx`, `StudioLayout.tsx`, `AgentBuilderPage/index.tsx`, `utils/agentDetailMapping.ts` | ✅ |
| Tests | BE 50(신규 5파일) + 기존 게이트 미들웨어 2건 계약 갱신 / FE 13 | ✅ |
| Docs | Plan v0.2, Design v0.1, Analysis(Act-2 포함), 본 리포트 | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority | Effort |
|------|--------|----------|--------|
| G4 승인 적재 실패 시에도 템플릿 문구 | Minor | Medium | 0.5h |
| G5 종료 로그 run_id/request_id | Minor | Low | 10m |
| G6 내부 도구 draftArgKeys 키 형식 | Minor(MCP 무영향) | Low | 0.5h |
| G7 RAG 설정 + draft_arg_key 병합 덮어쓰기 | Minor | Low | 20m |
| G8 본문 인자 스키마 후보 UI | Minor | Low | 1h |
| G9 테스트 보강(B16 react·B18 stream 전체) + Design 문서 편차 반영 | Minor | Low | 1h |
| L3 게이트 미들웨어 제거 시나리오(SC-4 런타임) | 환경 변경 필요 | Medium | 0.5h |
| 근거 없는 수치 생성(1877-9900) | 별도 기능 | High | `draft-grounding-check` (Plan 완료) |

### 4.2 Known Limitations

| Item | Note |
|------|------|
| 서브 에이전트 명시 `mode=off` | depth>0 은 미들웨어 계획 미해석 → 기본 게이트(안전 방향) |
| 채팅 스트리밍 중 워커 토큰 | react 폴백 경로에서 잠깐 보였다가 템플릿으로 교체 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| Match Rate | 90% | 94.1% | +9.5 (Act-2) |
| Structural / Functional / Contract / Runtime | — | 97 / 93 / 92 / 95 | Runtime +25 |
| Success Criteria | 7/7 | 7/7 | SC-3 Partial → Met |
| L3 | 3/3 | 3/3 | Act-1 전 0/1, Act-1 후 1/2 |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| 게이트 후 supervisor 반복 호출(5회) | 게이트 워커 조건부 END | ✅ |
| 가짜 성공 JSON 채팅 저장 | 결정적 템플릿 | ✅ |
| "등록해줘" 에도 미호출(도구 설명 충돌) | 접두·접미·규칙 블록 (Act-1) | ✅ L3 3/3 |
| 게이트 미설정 무승인 실행 | fail-closed 기본 게이트 | ✅ |
| search/collect 승인 필요 도구 무승인 실행 (G2, 기존 결함) | action 승격 / react+게이트 폴백 | ✅ |
| 인자 조립 파싱 실패로 요청 소실 (G1) | 본문 제외 + 재시도 | ✅ |
| 서브 에이전트 신호 미전파 (G3) | 부모로 전파 + 조건부 간선 | ✅ |
| `reply_content` 초안 JSON(수정 불가) | draft_arg_key (react·action) + 빌더 입력 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **실측 먼저**: DB 트레이스 + MCP 직접 조회로 "가짜 성공" 을 확정한 뒤 설계했다 — 추측 기반 수정이 없었다.
- **L3 를 사이클 안에 넣은 것**: 단위 테스트가 모두 통과한 상태에서 L3 가 두 개의 실제 결함(안내 문구 패배, 인자 조립 파싱)을 드러냈다.
- 결정적 규칙(간선·템플릿·기본 게이트)으로 LLM 비결정성 의존을 줄였다.

### 6.2 What Needs Improvement (Problem)

- LLM 이 읽는 문구의 **충돌**(플랫폼 안내 vs 도구 원문)을 Design 에서 예측하지 못했다 — 접두만으로 충분하다고 가정.
- 게이트 부착 판정과 노드 종류(search/collect)의 교차 검증이 빠져, 기존 무승인 경로(G2)를 gap 분석에서야 발견.
- 보조 LLM 에 "하지 말라" 지시로 제약한 설계(본문 비우기)가 실패 — 입력에서 제거하는 편이 확실.

### 6.3 What to Try Next (Try)

- 프롬프트 계층 변경은 **L3 최소 3회**를 Do 완료 조건에 포함.
- "LLM 에게 X 하지 말라" 대신 **X 를 할 수 없게 입력에서 제거**하는 설계를 기본으로.
- 게이트·부작용 관련 변경 시 "모든 노드 종류 × 게이트 부착" 표를 Design 에 명시.

---

## 7. Process Improvement Suggestions

| Phase | Current | Suggestion |
|-------|---------|------------|
| Design | 프롬프트 문구 효과를 가정 | 경쟁 문구(도구 설명 등)와의 충돌을 Risk 에 명시 |
| Do | L3 는 마지막 모듈 후 | 프롬프트 변경 모듈마다 L3 1회 |
| Check | gap-detector 정적 + L3 근거 | 효과적 — 유지. 에이전트 턴 한도로 1회 중단 → 보고서 파일 출력 지시 유지 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 승인함 63116 중복 대기 건 정리(1건만 남기고 거절)
- [ ] 커밋 — 현재 `feature/approval-edit-before-approve` 브랜치(PR #63)에 미커밋. 이 기능을 PR #63 에 포함할지, 분리할지 결정
- [ ] 백엔드 서버 재시작 후 UI 로 1회 확인(채팅 템플릿·빌더 본문 인자)

### 8.2 Next PDCA Cycle

| Item | Priority |
|------|----------|
| `draft-grounding-check` (Plan 완료 → Design) | High |
| G4~G9 Minor 묶음 | Low |

---

## 9. Changelog

### v1.0.0 (2026-09-30)

**Added:**
- 승인 대기 런 결정적 안내 문구(`ApprovalPendingNoticePolicy`)
- 게이트 워커 supervisor 안내(접두·접미·`[승인 게이트 규칙]`)
- 빌더 `승인 필요` 배지·`본문 인자` 입력, 편집 모드 복원
- react 게이트 `draft_key`, 인자 조립 파싱 재시도

**Changed:**
- 게이트 워커·서브 에이전트 워커 뒤 조건부 END (supervisor 재진입 제거)
- 게이트 미설정 에이전트도 승인 필요 도구는 기본 게이트(fail-closed)
- 미분류·search·collect 승인 필요 도구는 초안 작성 노드(action) 기본
- 인자 조립 LLM 에 본문 키·초안 원문 미전달

**Fixed:**
- 게이트 후 같은 워커 반복 호출
- 워커 LLM 이 지어낸 성공 JSON 의 채팅 노출
- search/collect 승인 필요 도구 무승인 실행
- 서브 에이전트 승인 대기 신호 유실

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-30 | Completion report created | 배상규 |
