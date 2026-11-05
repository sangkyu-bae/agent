# agent-token-limit Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt 백엔드 + idt_front)
> **Author**: 배상규
> **Completion Date**: 2026-11-05
> **PDCA Cycle**: #1 (Act-1 1회)
> **Branch**: `feature/agent-token-limit` (worktree `wt/agent-token-limit`), 커밋 61914f5 → 95964aa, 55 files / +2363 −95

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | agent-token-limit — 에이전트별 supervisor 토큰 예산을 DB로 관리하고 한도 도달 동작을 반복 한도와 통일 |
| Start Date | 2026-11-05 (LangSmith 런 01a1a939 원인 분석에서 출발) |
| End Date | 2026-11-05 |
| Duration | 1일 (Plan → Design → Do 5모듈 → Check → Act-1 → Report) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100% (FR 11/11)            │
├─────────────────────────────────────────────┤
│  ✅ Complete:     11 / 11 FR                 │
│  ✅ Success Criteria: 7 / 7                  │
│  Final Match Rate: 95.8% (Act-1 후)          │
│  이월(Minor·결정 필요): 4건                  │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | `SupervisorConfig.token_limit`이 코드 상수 8000으로 전 에이전트에 고정되어, 스크랩 1회(글자 수 ÷ 4 = 8869)로 두 번째 supervisor에서 즉시 종료됐다. 분석·발표자료 워커는 실행되지 못했고 사용자는 왜 짧게 끝났는지 알 수 없었다(LangSmith 01a1a939). |
| **Solution** | `agent_definition.token_limit`(V085, 기본 50000, 8000~500000)을 단일 소스로 두고 생성/수정/조회/포크 API·Studio 설정 탭·실행 경로(대화·승인 재개·서브 에이전트)에 배선. 토큰 가드가 `limit_reached` + `limit_reason`을 세워 반복 한도와 같은 final_answer 안내·payload·채팅 배지 경로를 탄다. 서브 에이전트는 자기 정의 값(부모 절반 상속 폐기). |
| **Function/UX Effect** | 같은 질의의 실런이 기본값으로 **스크랩 → 분석(+차트) → 발표자료 → 최종 답변**까지 완주(run 77a01a91, 264s, supervisor 결정 4회). 한도 도달 강제 런(99718ab3)은 payload `limit_reached: true, limit_reason: "token"`과 답변 본문의 한도 언급, 채팅 배지로 사용자에게 전달된다. 설정 탭에서 에이전트별 토큰 예산 입력·clamp·복원. |
| **Core Value** | 반복·토큰 한도가 같은 단일 소스(`agent_definition`)·같은 종료 경로를 가져 실행 예산이 예측 가능해졌고, 한 번의 긴 수집이 전체 작업을 무효화하던 결함이 제거됐다. 비용 상한은 반복 한도와 범위 상한 500000이 유지한다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 재현 시나리오가 기본값 50000으로 토큰 가드 없이 완주 | ✅ Met | 실런 77a01a91: 워커 체인 완주, payload에 `limit_reached` 없음. Analysis §2.7 L3-1 |
| SC-2 | 생성→조회→수정→조회→포크 왕복 보존 | ✅ Met | L1 인프로세스 10/10 (create 50000 → patch 60000 → get 60000 → None 유지). 포크·자동포크 유스케이스 테스트 |
| SC-3 | 토큰 도달 시 final_answer 안내 + 플래그·사유, 워커 미실행도 답변 | ✅ Met | 실런 99718ab3: 가드 로그 → final_answer → payload token 사유, 답변 "한도로 인해 … 진행하지 못해". 워커 미실행 경로는 `TestRouteWithLimitReached` |
| SC-4 | 서브 에이전트 초기 state `token_limit` = 서브 정의 값 | ✅ Met | `workflow_compiler.py` `_compile_sub_agent`→`_wrap_sub_agent(token_limit=sub_agent.token_limit)`, 테스트 3건 |
| SC-5 | 범위 밖 값 API 422, 도메인 ValueError | ✅ Met | L1 #2/#3/#6 422, `test_token_limit_policy.py` |
| SC-6 | 설정 탭 입력·저장·재진입·clamp | ✅ Met (RTL) | `LimitNumberField` 6, `SettingsPanel` 3, `AgentBuilderPage` create/edit 전송 2. 브라우저 수동 확인은 미실시 |
| SC-7 | 기존 테스트 통과(상시 실패 제외) | ✅ Met | 백엔드 `agent_builder` 1326 passed, `tests/api` 실패 25건 = master 동일. 프론트 실패 4파일 = master 동일 |

**Success Rate**: 7/7 (100%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 기본 50000 / 범위 8000~500000 | ✅ | 재현 런 완주. 상한은 정책 상수로 캡 |
| [Plan] | 집계 방식(워커 산출 글자 수 ÷ 4) 유지 | ✅ | 범위 최소화 달성. 실측으로 **같은 질의도 런마다 사용량이 다름**(8000 그대로는 가드 미발동, 강제로만 재현) — 집계 정확도는 별도 사이클 후보 |
| [Plan] | 한도 도달 동작을 반복 한도와 통일 | ✅ | 구 D5("토큰 가드는 limit_reached 미설정") 폐기, 테스트 4건 기대값 갱신 |
| [Plan] | 서브 에이전트는 자기 DB 값 | ✅ | 부모 절반 상속 제거, 사용량 합산 유지 |
| [Plan] | 포크·자동 포크 복사 | ✅ | — |
| [Design] | Option C (배선 복제 + 독립 정책 + `limit_reason` additive) | ✅ | 재개 스냅샷·기존 계약 무영향 |
| [Design] D10 | payload latch | ✅ + Act-1 | 서브 그래프 이벤트 누수(G-2)를 실험으로 확인하고 최상위 이벤트(`parent_ids` ≤ 1)로 한정 |
| [Design] D11/D12 | 배지 UI·공용 숫자 입력 | ✅ | `StudioLayout` 패스스루가 Design 목록에서 빠져 있어 Do에서 발견·v0.2 정정 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [agent-token-limit.plan.md](../01-plan/features/agent-token-limit.plan.md) | ✅ Finalized |
| Design | [agent-token-limit.design.md](../02-design/features/agent-token-limit.design.md) | ✅ v0.2 (Check 정정) |
| Check | [agent-token-limit.analysis.md](../03-analysis/agent-token-limit.analysis.md) | ✅ v0.2 (Act-1 반영) |
| Act | 본 문서 | ✅ |
| 선행 | `docs/archive/2026-07/agent-recursion-limit/` | 참조 |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | V085 `token_limit INT NOT NULL DEFAULT 50000` + COMMENT | ✅ | V084는 kb-quick-setup 선점 → V085 |
| FR-02 | `TokenLimitPolicy` 범위 검증, API 422 | ✅ | |
| FR-03 | 생성 기본 50000, 수정 None=변경 없음, 응답 포함 | ✅ | Create/Get 응답. PATCH 응답은 기존 구조대로 미포함 |
| FR-04 | 대화 실행·승인 재개 주입 | ✅ | 두 지점 테스트 |
| FR-05 | 서브 에이전트 독립 값 | ✅ | |
| FR-06 | 토큰 가드 `limit_reached` + final_answer 안내 | ✅ | 사유별 3종 문구 |
| FR-07 | payload `limit_reached` + 사유 | ✅ | `limit_reason` additive, Act-1 깊이 필터 |
| FR-08 | 포크·자동 포크 복사 | ✅ | |
| FR-09 | Studio 설정 탭 입력 | ✅ | `LimitNumberField` 공용화 |
| FR-10 | API 계약 동기화 | ✅ | 타입 4종·WS payload, URL 변경 없음 |
| FR-11 | 되물음 무한 루프 미재발 | ✅ | `_challenge_reset` 유지, Gap-06 테스트 기대값 갱신 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 호환성 | 필드 미전달 시 기본값 동작 | L1 #1, 구 서버 payload 부재 시 프론트 기본값 | ✅ |
| 안전성 | 모든 조기 return이 `_challenge_reset` 포함 | 가드 2곳 유지 | ✅ |
| 레이어 규칙 | verify-architecture 5항목 | 본 변경 0건 위반(기존 11건은 master 동일) | ✅ |
| DDL 규칙 | V085 COMMENT | `test_migration_ddl_comments` 통과 | ✅ |
| TDD | Red→Green | 모듈마다 테스트 선행, 신규·갱신 약 70건 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| 마이그레이션 | `idt/db/migration/V085__alter_agent_definition_add_token_limit.sql` | ✅ (로컬 DB 적용 2026-11-05) |
| 도메인 | `src/domain/agent_builder/policies.py` `TokenLimitPolicy`, `schemas.py` | ✅ |
| API/유스케이스 | `src/application/agent_builder/{schemas,create,update,get,fork}_*`, `auto_fork_service.py` | ✅ |
| 실행 경로 | `run_agent_use_case.py`, `supervisor_nodes.py`, `supervisor_state.py`, `workflow_compiler.py` | ✅ |
| 프론트 설정 | `settings/LimitNumberField.tsx`, `SettingsPanel.tsx`, `AgentTestPanel.tsx`, `StudioLayout.tsx`, `AgentBuilderPage/index.tsx`, `constants/agentSettings.ts`, 타입 | ✅ |
| 프론트 배지 | `utils/limitNotice.ts`, `hooks/useAgentRunStream.ts`, `pages/ChatPage/index.tsx`, `chat/MessageBubble.tsx`, `types/{websocket,chat}.ts` | ✅ |
| 테스트 | `tests/domain/agent_builder/test_token_limit_policy.py`, `tests/application/agent_builder/test_agent_token_limit_runtime.py` 외 보강 | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority | Note |
|------|--------|----------|------|
| G-3 마이그레이션 순서 | V085가 kb-quick-setup의 V084보다 먼저 머지될 수 있음. 로컬은 Flyway 이력 없이 SQL 직접 적용이라 영향 없음 | High (배포 전 결정) | 머지 순서 조율 또는 Flyway outOfOrder. 운영 적용 절차 확인 필요 |
| G-5 pytest HTTP 왕복 | 인프로세스 스모크로 실측했으나 회귀 테스트로 남기지 않음 | Low | `max_iterations`도 동일 상태 |
| G-7 ChatPage `limitReason` 매핑 테스트 | RTL 범위 밖 | Low | |
| G-8 복원 버튼 aria-label 2개 동일 | 접근성 | Low | 기존 테스트 선택자 갱신 동반 |
| 집계 정확도 | 글자 수 ÷ 4가 워커 LLM 요약 길이에 의존 → 런마다 변동 | Medium (별도 사이클) | `usage_metadata` 실측으로 교체 시 집계 9곳·기본값 의미 재검토 |

### 4.2 Cancelled/On Hold

| Item | Reason |
|------|--------|
| 서브 에이전트 "자기 값과 부모 절반 중 작은 값" 캡 | 사용자가 독립 구조 결정 |
| 히스토리 재조회 시 배지 | `excluded_tools`와 동일하게 실시간 전용 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Note |
|--------|--------|-------|------|
| Design Match Rate | 90% | 95.8% | Act-1 전 93.2% |
| Structural / Functional / Contract | — | 97 / 93 / 92 | gap-detector |
| Runtime (L1/L2/L3) | — | 100 / 100 / 100 (Act-1 후) | L3 #2는 조건 미충족으로 제외 |
| 회귀 | 0 | 0 | 백엔드·프론트 실패 목록 master 동일 |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| G-2 서브 에이전트 한도 신호가 부모 payload에 누수 | `_map_event`가 `parent_ids` 길이로 `nested` 판정, latch는 최상위만 | ✅ 테스트 2건 |
| V084 번호 충돌 | kb-quick-setup worktree 미커밋 파일 확인 → V085 | ✅ |
| 구 D5 테스트 고정("토큰 가드 limit_reached 미설정") | 결정 폐기 근거를 주석·docstring에 남기고 기대값 갱신 | ✅ |
| `StudioLayout` 누락 | 페이지→패널 패스스루 배선, Design v0.2 추가 | ✅ |
| 프론트 폼 픽스처 `tokenLimit` 누락(tsc) | 2곳 보강. 기존 미완 픽스처 2곳은 master 동일로 유지 | ✅ |

---

## 6. Lessons Learned

### 6.1 Keep

- 선행 사이클(agent-recursion-limit)의 배선 지점을 grep으로 전수 대조하는 방식이 누락 없이 통했다. 단, Design 작성 시 중간 계층(`StudioLayout`)까지 grep해야 한다.
- 실런(인프로세스 TestClient + WS)이 단위 테스트가 못 보는 것을 잡았다. 집계가 워커 요약 길이에 의존해 같은 질의도 런마다 사용량이 다르다는 사실, 그리고 서브 그래프 이벤트 누수(G-2)는 LangGraph 소형 실험으로만 확정됐다.
- 정책 하한(8000) 때문에 재현이 안 될 때 `build_initial_state`를 감싸 state만 낮추는 방식은 코드를 건드리지 않고 경로를 검증한다(quality_gate 선례와 동일).

### 6.2 Problem

- 반복 한도 사이클에서 "토큰 가드는 limit_reached를 세우지 않는다"를 테스트로 고정해 두어 이번에 결정을 뒤집는 비용이 생겼다. 임시 결정은 테스트 docstring에 "왜·언제 바꿔도 되는지"를 함께 적어야 한다.
- gap-detector 에이전트가 30턴 한도에서 보고 없이 멈췄다. 브리핑에 "n턴 안에 보고"를 명시해야 한다.
- 백그라운드 pytest 결과를 grep으로 추출할 때 cp949 출력 때문에 `LC_ALL=C`·`grep -a` 없이는 줄이 사라진다(기존 메모와 동일 함정 재현).

### 6.3 Try

- 토큰 집계를 `usage_metadata` 실측으로 바꾸는 사이클을 열 때, 이번 실런 3건(77a01a91·cbf34be6·99718ab3)을 기준 데이터로 쓴다.
- 마이그레이션 번호는 착수 시 다른 worktree의 미커밋 파일까지 `ls wt/*/idt/db/migration`으로 확인한다(이번에 V084 충돌을 그렇게 잡았다).

---

## 7. Process Improvement Suggestions

| Phase | Current | Suggestion |
|-------|---------|------------|
| Design | 수정 파일 목록을 grep 기반으로 작성 | 프롭 드릴링 경로(페이지→레이아웃→패널)는 호출 체인을 따라 전부 나열 |
| Check | gap-detector + 수동 실런 | 실런 스크립트(`smoke_token_limit.py`)를 `tests/manual/`로 커밋해 재사용 — 단, LLM 비용 발생이라 기본 수집 제외 |
| 배포 | Flyway 순서 미확인 | 병렬 feature가 마이그레이션을 가질 때 머지 순서를 PR 본문에 명시 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] `git push -u origin feature/agent-token-limit` → `gh pr create --base master` (PR 본문에 V085·V084 머지 순서, 로컬 DB 적용 사실 기재)
- [ ] 머지 후 junction 제거 → `git worktree remove ../wt/agent-token-limit` → 브랜치 삭제
- [ ] 운영 DB에 V085 적용 절차 확인(Flyway 사용 여부·outOfOrder)

### 8.2 Next PDCA Cycle 후보

| Item | Priority |
|------|----------|
| 토큰 집계 실측(`usage_metadata`) 교체 | Medium |
| G-5/G-7/G-8 후속 테스트·접근성 | Low |

---

## 9. Changelog

| Commit | 내용 |
|--------|------|
| 61914f5 | docs: Plan·Design |
| 2514ebf | feat(module-1): V085, `TokenLimitPolicy`, 엔티티·Config·repository |
| 1ad6191 | feat(module-2): 스키마 4종, create/update/get/fork/auto_fork |
| ff8d901 | feat(module-3): 실행 경로 주입, 서브 독립값, 가드 `limit_reason`, final_answer 안내, payload |
| 414899e | feat(module-4/5): 설정 패널·공용 입력, 채팅 배지 |
| 95964aa | fix(Act-1): latch 최상위 한정 + Analysis·Design v0.2 |
