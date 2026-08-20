# agent-create-wizard Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: sangplusbot (`idt` + `idt_front`)
> **Version**: 0.1
> **Analyst**: 배상규 (gap-detector ×2 + 실측 검증)
> **Date**: 2026-08-20
> **Design Doc**: [agent-create-wizard.design.md](../02-design/features/agent-create-wizard.design.md)
> **구현 기준**: `feature/agent-create-wizard` 5커밋 (`ae45947`..`d293415`), 워킹트리 소스 변경 없음

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 자동 생성이 블랙박스여서 결과가 어긋나도 사용자가 어느 단계에서 틀렸는지 알 수 없고, 개입할 수도 없다 |
| **WHO** | P2 — KB 운영자 / 에이전트 소유자. 에이전트를 처음 만드는 비개발 실무자 |
| **RISK** | ① 파이프라인 2모드화로 계약 복잡도 상승 ② 미커밋 코드 + V061~V063 배포 선행조건 ③ prompt_session이 스튜디오 저장까지 생존해야 바인딩 성립 |
| **SUCCESS** | 설명 1문장 → 4스텝 완주 → 스튜디오 저장 → `GET /api/v1/agents/{id}` 일치. 기존 5경로 회귀 0건 |
| **SCOPE** | 백엔드 확장 + 프론트 위저드 전면 교체. R1 수렴은 범위 밖 |

---

## Strategic Alignment Check

PRD 없음 (pm 단계 미수행). Plan/Design 2층 기준으로 검증.

- **핵심 문제(WHY) 해소**: ✅ — LLM 판단 3곳(의도·도구·프롬프트) 각각에 정지·개입 지점이 실제로 구현됨. 단, **실패 경로에서 "어디서 끊겼는지"가 사라지는 결함**(Gap F-5: SSE 실패 시 진행바 error 미전환)이 WHY와 정면 충돌 — 우선 수정 대상.
- **Design 핵심 판단 준수**: Option C(Policy 계산) ✅ / D1 tools_confirmed short-circuit ✅ 100% / D2 intent 에코백 재검증 ✅ 100% (설계보다 한 발 더: questions=[] 폐기) / D3 정지 시 clamp ⚠️ 90% (응답은 clamp, 저장 버전 본문은 원본 — 실사용 영향 없음, 각주 대상).

### Success Criteria Status

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | 4스텝 완주 (MSW 통합 1본 + 수동 E2E 1회) | ❌ | **위저드 통합 테스트 미작성**(`agentCreateWizard.test.tsx` 부재), 수동 E2E 미실행 |
| SC-2 | `GET /agents/{id}` 일치 | ❌ | 실서버 E2E 미실행 (Check 잔여 항목, 파이프라인 이월 #15) |
| SC-3 | 도구 추가/해제 반영 (`required_ids` 보존) | ⚠️ | 백엔드 잠김: `test_use_case_stop_points.py:139`(부활 차단). 저장까지의 통합 검증은 SC-1에 종속 |
| SC-4 | 사람 버전 적재 + 세션 바인딩 | ⚠️ | V063 DB 적용 실측 ✅(`source varchar(10) NOT NULL DEFAULT 'llm'`), append 테스트 ✅. 실서버 바인딩 확인 미실행 |
| SC-5 | 논스톱 회귀 0 | ✅ | 위저드 관련 백엔드 187케이스 전량 통과(2026-08-20 실행) + `stages_to_run(None)` 동일성 구조 잠금 |
| SC-6 | 진행바 5단계 고정 + 상태 구분 | ✅ | `pipelineStepsToProgress.ts:69` 입력 무관 5행 + 테스트 16건. §5.5 표와 1:1 |
| SC-7 | 플래그 off 폴백 | ✅ | `PipelineUnavailableCard` + 404 시나리오 테스트 `index.test.tsx:598-628` |
| SC-8 | 신규 코드 TDD | ⚠️ | 백엔드 4계층 테스트 충실. 프론트 **단계 컴포넌트 단위 테스트 5종 부재** (페이지 테스트 27건이 대체 커버) |
| SC-9 | 기존 경로 회귀 0 (FAILED 목록 diff) | ✅ | 전체 스위트 **58 failed / 7459 passed** — baseline 58건과 개수 일치, 실패 전부 무관 모듈(parser·retriever·general_chat·agent_builder stream·ES). 위저드 영역 신규 FAILED **0건**. Fix 탭·구 진입 통합 테스트 7건도 통과 |

**Success Rate**: 4 Met / 3 Partial / 2 Not Met (SC-1·SC-2는 검증 수단 부재가 원인 — 구현 결함이 아니라 테스트 자산 결손)

---

## 2. Gap Analysis

### 2.1 백엔드 — FR-B01~B13: **11 Met / 2 Partial / 0 Not Met**

Partial 2건은 본 세션 런타임 검증으로 사실상 해소:
- FR-B09(논스톱 회귀 0): 187케이스 + 전체 스위트 diff로 **✅ 승격**
- FR-B10(활성화·마이그레이션·스모크): `.env` 플래그 ✅, V063 DB 적용 실측 ✅, 실서버 라우트 401 응답 실측 ✅ (`/agents/pipeline`, `/prompt-composer/sessions/{id}/versions` 모두 등록·활성 + 인증 계약 유지). 인증 포함 200 완주만 잔여(SC-2와 함께 소화)

### 2.2 프론트 — FR-F01~F18: **13 Met / 5 Partial / 0 Not Met**

Partial: F10(진행바 error 미전환) · F11(`llm_model_id` 핸드오프 누락) · F16(인앱 이탈 confirm 부재) · F17(런타임 상수 export 위반) · F18(step① LoadingButton 미사용)

### 2.6 API Contract — 3-way 대조

클라 `types/agentPipeline.ts` ↔ 서버 `interfaces/schemas/agent_pipeline.py` 전 항목 일치 (stop_after·tools_confirmed·intent 에코백 3필드·응답 17필드·append/bind 계약). 요청 왕복 R1/R3·session_id 재사용이 request-body 단언 테스트로 잠김. **단 Design 문서 §3.5의 `intent` 에코백 타입이 실제 계약과 어긋남** (문서 drift — 코드가 진실).

### 2.7 Runtime Verification (실측, 2026-08-20)

| 검증 | 결과 |
|------|------|
| 백엔드 위저드 관련 스위트 (domain/application/api/DDL) | **187 passed / 0 failed** |
| 백엔드 전체 스위트 | 58 failed / **7459 passed** — baseline 58건, 신규 FAILED 0 |
| 프론트 위저드 관련 (어댑터·변환·페이지 27 it) | **54 passed / 0 failed** |
| 프론트 구 통합 테스트 (Fix 탭 draft 경로) | 7 passed (회귀 없음) |
| 실서버 라우트 (무인증 프로브) | `/agents/pipeline` 401 · `/sessions/{id}/versions` 401 · `/agents/compose` 401 — 전부 등록·활성 |
| DB | `prompt_version.source` 컬럼 존재 (V063 적용 확인) |
| L3 위저드 통합/수동 E2E | **미실행** — 테스트 자산 부재 (Gap F-1) |

### 2.8 Match Rate Summary

**최초 분석 (v0.1)**: BE 98% / FE 80% / **Overall 89%** — 프론트 Structural 68%·Runtime 70%의 원인은 기능 결손이 아니라 테스트 자산 결손에 집중.

**Act 1회차 후 재산정 (v0.2, 2026-08-20)**:

```
┌──────────────────────┬─────────┬─────────┐
│ 축                    │ 백엔드   │ 프론트   │
├──────────────────────┼─────────┼─────────┤
│ Structural   (×0.15) │  100%   │   92%   │
│ Functional   (×0.25) │   97%   │   95%   │
│ Contract     (×0.25) │   97%   │   95%   │
│ Runtime      (×0.35) │   98%   │   90%   │
├──────────────────────┼─────────┼─────────┤
│ Overall              │   98%   │   93%   │
└──────────────────────┴─────────┴─────────┘
        Overall Match Rate: 95%  (목표 90% 달성 ✅)
```

### 2.9 Act 1회차 수정 결과 (2026-08-20)

Checkpoint 5에서 "지금 모두 수정" 선택 → pdca-iterator가 Critical 2 + Important 5 전건 수정.

| Gap | 조치 | 검증 |
|-----|------|------|
| F-1 | `agentCreateWizard.test.tsx` 신설 — §8.5 #1(완주 프리필)·#3(저장+바인딩)·#4(편집 저장 source=human)·#5(바인딩 409 내성) 커버 | 통과 |
| F-2 | `agentCreateEntry.test.tsx` 삭제 (회귀 가치는 F-1로 흡수) | — |
| F-3 | `DescriptionComposer.tsx` 런타임 export 제거, `types/agentPipeline.ts`의 `MAX_PIPELINE_USER_REQUEST_CHARS` 정본 단일화 | eslint 0 |
| F-4 | 헤더 "에이전트 만들기" + `[취소]`(진행 중 confirm) + 고정 헤더/스크롤 바디 패턴 A | 통과 |
| F-5 | 훅이 실패 시점 activeStage를 합성 `failed` step으로 반영 → 진행바 `error` 렌더. `useAgentPipelineStream.test.ts` 신설(서비스 모킹 경계) | 통과 |
| F-6 | ToolsStep `[이전]` → `[처음부터]` 라벨 정정 + confirm 게이트 (무상태 위저드라 step② 복귀 불가 — 주석으로 근거 명시) | 통과 |
| F-7 | 컴포넌트 테스트 5종 신설 (WizardProgress·DescriptionComposer·IntentStep·ToolsStep·PromptStep) | 통과 |

**재검증 실측**: 프론트 전체 **1,052 passed / 9 failed** — 실패 9건은 수정 전과 동일한 무관 모듈 baseline(ChatPage·collection 모달·EvalDataset), 신규 FAILED **0**. `tsc -b` 변경 파일 에러 0(기존 미변경 3파일 baseline 별도 기록). 변경 파일 12개 eslint 에러 0.

**잔여 (Minor, 명시 이월)**: B-2(tools 정지 시 unknown_tool_ids 미검증 — 계약 명시 or 구현 보완 택1), B-3(저장 버전 clamp 이전 원본), B-4/5(L1 테스트 2건), F-9(MSW 기본 핸들러), F-10(`llm_model_id` 핸드오프), F-12(step① LoadingButton/글자수), F-13(`MAX_CLARIFY_ROUNDS` 하드코딩), 문서 drift 4건(§10).

---

## Gap 목록 (severity 순)

| # | Sev. | Conf. | 내용 | 위치 |
|---|------|:----:|------|------|
| F-1 | 🔴 Critical | 100% | 위저드 L3 통합 테스트 부재 — SC-1 검증 수단 없음. 위저드→핸드오프→저장→append/bind 경로 무커버 | `__tests__/integration/agentCreateWizard.test.tsx` (미생성) |
| F-2 | 🔴 Critical | 100% | 구 `agentCreateEntry.test.tsx` 미제거 (Design §11.1 [제거] 대상) — R-08 diff 기준 흐려짐 | `__tests__/integration/agentCreateEntry.test.tsx` |
| F-3 | 🟡 Important | 95% | 컴포넌트 파일 런타임 상수 export (확립 규칙 위반) + `types/agentPipeline.ts:191` 정본 상수 사문화 — 상한 소스 3중화 | `DescriptionComposer.tsx:3` |
| F-4 | 🟡 Important | 90% | 헤더 "에이전트 만들기"+`[취소]`+인앱 이탈 confirm 전부 없음 — `beforeunload`만으로는 라우터 이동 무경고 소실 (FR-F16) | `AgentCreateEntryPage/index.tsx:103-108` |
| F-5 | 🟡 Important | 85% | SSE 실패 시 진행바 error 미전환 — 실패 단계가 '대기중'으로 회귀, WHY(불투명성 제거)와 정면 충돌 (FR-F10) | `useAgentPipelineStream.ts:135-143` |
| F-6 | 🟡 Important | 80% | ToolsStep `[이전]`에 `handleRestart`가 물려 있어 전체 상태 무경고 소실 — PromptStep의 `onBack`과 동작 불일치 | `index.tsx:384` |
| F-7 | 🟡 Important | 100% | 단계 컴포넌트 단위 테스트 5종 부재 (Design §11.1 `(+.test)`) | `components/*.test.tsx` |
| B-2 | 🟡 Important | 65% | `stop_after="tools"` 정지 시 `unknown_tool_ids` 항상 빈 배열 (검증이 compose 단계에만 존재) — Design §7 서술과 부분 불일치 | `use_case.py:349-351` |
| B-3 | 🟢 Minor | 80% | 저장된 `prompt_version.assembled`가 clamp 이전 원본 (D3 잔여, append 경로가 4000자 재제한하므로 실영향 없음) | `use_case.py:331-335` |
| B-4/5 | 🟢 Minor | 85% | L1 #3 API 테스트 부재 · L1 #10 이벤트 개수 단언 누락 | `test_agent_pipeline_router_stop.py` |
| F-9 | 🟢 Minor | 100% | MSW `handlers.ts` 파이프라인 기본 핸들러 미추가 | `mocks/handlers.ts` |
| F-10 | 🟢 Minor | 80% | `llm_model_id` 핸드오프 누락 (FR-F11) | `agentDraftStore.ts:16-24` |
| F-12 | 🟢 Minor | 90% | step① 실시간 글자수 미표시 + LoadingButton 미사용 | `DescriptionComposer.tsx:39-57` |
| F-13 | 🟢 Minor | 70% | `MAX_CLARIFY_ROUNDS=2` 페이지 하드코딩 — 서버 `SlotLimits` 변경 시 조용히 어긋남 | `index.tsx:35` |
| — | 🟢 Minor | 100% | 구조 편차(위반 아님): `promptComposerService.ts` → `agentPipelineService`에 통합, `DescriptionStep` → 기존 `DescriptionComposer` 재사용, 테스트가 신규 `*_stop.py` 파일로 분리(개선) | — |

---

## 10. Design Document Updates Needed (코드가 진실)

- [ ] §3.5 `AgentPipelineRequest.intent` 타입을 실제 에코백 계약(`{label, filled_slots, degraded}`)으로 수정 (D2와 문서 자신이 불일치)
- [ ] §5.1 레이아웃: sticky 사이드바 진행바 → 입력창 아래 단일 컬럼 (커밋 `d293415`, 사용자 결정)
- [ ] §11.1 `repositories.py` → `repository.py` 표기 수정
- [ ] §4.3/§7에 "tools 정지 시점에는 unknown_tool_ids 검증 미수행" 명시 또는 B-2 구현 보완 중 택1

---

## 11. Next Steps

- [x] Checkpoint 5 → "지금 모두 수정" → Act 1회차 완료 (95% 달성)
- [ ] SC-2 실서버 수동 E2E 1회 (파이프라인 이월 #15 동시 소화) — Report 전 권장
- [ ] 수정분 커밋 (`feature/agent-create-wizard`)
- [ ] `/pdca report agent-create-wizard`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | 최초 분석 — BE 98% / FE 80% / Overall 89%. 런타임 실측(테스트 7,700건 실행·실서버 프로브·DB 컬럼 확인) 포함 | 배상규 |
| 0.2 | 2026-08-20 | Act 1회차 반영 — Critical 2 + Important 5 전건 수정, 재검증(FE 1,052 passed·신규 FAILED 0·tsc/eslint 0). **Overall 95%** | 배상규 |
