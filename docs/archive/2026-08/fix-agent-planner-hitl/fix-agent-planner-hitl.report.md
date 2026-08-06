# fix-agent-planner-hitl Completion Report

> **Feature**: Fix 에이전트 탭 Planner 2단계 파이프라인 + Stateless HITL
> **Project**: sangplusbot (idt + idt_front)
> **Period**: 2026-08-06 (Plan → Act-1 단일 세션)
> **Final Match Rate**: **100%** (최초 Check 95.2% → Act-1 후 100%, Iteration 1/5)
> **Author**: 배상규 + Claude (PDCA)

---

## Executive Summary

`/agent-builder` Fix 탭의 채팅 기반 에이전트 생성/수정 경로(compose)를 **Planner → Composer 2단계 모듈 파이프라인**으로 재구성했다. Planner가 요구를 분석해 빌드 계획(BuildPlan)을 세우고, confidence가 낮으면 선택지가 달린 **구조화 질문 카드**로 사용자에게 되묻는다(HITL). 상태는 서버 무저장 — 질문/답변이 요청 페이로드로 왕복한다. DB 마이그레이션 0, 기존 API 계약 additive 확장, 기존 테스트 전부 무수정 통과.

### 1.3 Value Delivered

| Perspective | Delivered |
|-------------|-----------|
| **Problem → 해소** | LLM 1회 추측 초안으로 인한 시행착오 반복 → 모호 요청 시 최대 3문항×2라운드 질문으로 의도 확정 후 초안 생성. 계획 요약(plan_summary)이 초안 카드에 노출되어 판단 근거가 보임 |
| **Solution 실측** | 백엔드 신규 2모듈+4파일 수정, 프론트 신규 1컴포넌트+4파일 수정. 테스트 신규 43건(백엔드 32·프론트 11), 전체 회귀 그린: 백엔드 86 passed·프론트 33 passed·tsc 클린 |
| **Function/UX Effect** | create/edit 모두 동작. 부분 답변 허용(미답변→"무응답"→Planner가 기본값 가정), 질문 무시하고 새 문장 입력 시 새 요청 처리, Planner 장애 시 기존 단발 compose 폴백 — Fix 탭 가용성 무손실 |
| **Core Value** | Planner가 `PlannerInterface` Protocol 뒤 독립 모듈 — LangGraph interrupt 기반 정식 HITL로 **DI 교체만으로 전환 가능**한 경계 확보. 질문 상한·라운드 상한이 도메인 정책(PlannerPolicy)으로 계약화 |

---

## PDCA Cycle Summary

### Plan (`docs/01-plan/features/fix-agent-planner-hitl.plan.md`)

- 현황 조사로 **Fix 탭의 실제 백엔드가 `auto_agent_builder`(질문 루프 보유)가 아니라 `POST /api/v1/agents/compose`(단발·무저장)임을 확정** — 유사 기능의 존재가 스코프 오판을 유발할 뻔한 지점
- 사용자 결정 4건: ① Stateless HITL(세션/DB 0) ② Planner→Composer 2단계 ③ 구조화 질문 카드 ④ create+edit 모두
- FR-01~FR-10, 하위호환(additive 계약)을 회귀 기준선으로 명시

### Design (`docs/02-design/features/fix-agent-planner-hitl.design.md`)

- 설계 결정 D1~D10 기록. 핵심: D7(needs_clarification을 coverage="none"+빈 초안으로도 표현 → status 모르는 구형 소비자 안전 강하), D8(질문 텍스트 에코백 — 무세션 서버가 요청만으로 Q/A 맥락 재구성), D9(PlannerInterface를 application 레이어에 배치 — domain이 application DTO를 참조하는 역전 방지)
- 설계 단계 사용자 확정 4건: 도구는 방향 힌트만(D5)·부분 답변 허용·plan_summary 별도 섹션·동일 LLM 재사용(D6)

### Do

- TDD 순서: PlannerPolicy(도메인) → AgentPlanner → UseCase 오케스트레이션 → Composer plan 주입 → DI → 프론트 타입/카드/패널
- `build_candidates_block`을 모듈 함수로 추출해 Composer/Planner가 동일 후보 포맷 공유
- 기존 `ComposeAgentUseCase` 생성자에 `planner`를 **optional 마지막 인자**로 추가 — 기존 테스트 13건이 무수정으로 하위호환을 증명하는 구조

### Check (`docs/03-analysis/fix-agent-planner-hitl.analysis.md`)

- gap-detector 94항목 가중 채점 → **95.2%**. Gap 7건(Medium 1·Low 6)
- 완전 일치: 도메인 VO·정책·인터페이스·DI·프론트 전체·D1~D10·아키텍처 규칙(역참조 0, 라우터 무변경)

### Act-1 (Gap 전량 해소 → 100%)

| Gap | 조치 |
|-----|------|
| G1 (M) | `plan(round_=...)` 파라미터 추가 — LangSmith `metadata["round"]`+로그로 FR-10 라운드 관측 완결 |
| G2 (L) | 폴백 경고 `error=str(e)` → `exception=e` (StructuredLogger `_log`가 exc_info로 스택 트레이스 기록) |
| G3 (L) | Planner `_to_result`에 `clamp_questions` 적용 — 질문 상한을 교체 지점 계약으로 보장 |
| G7 (L) | Composer `[빌드 계획]` 블록 부착/미부착 직접 검증 테스트 2건 |
| G4·G5·G6 (L) | 구현이 더 합리적 → 설계 문서를 구현 사실로 정정 |

---

## 주요 산출물 파일 목록

### 백엔드 (idt/)

**신규**
- `src/application/agent_composer/interfaces.py` — PlannerInterface(Protocol)·PlanResult
- `src/application/agent_composer/planner.py` — AgentPlanner(LLM structured output, `plan:*` 추적)
- `tests/domain/agent_composer/test_planner_policy.py` (11)
- `tests/application/agent_composer/test_agent_planner.py` (13)
- `tests/application/agent_composer/test_compose_use_case_planner.py` (8)

**수정**
- `src/domain/agent_composer/schemas.py` — BuildPlan·ToolDirectionHint·ClarifyingQuestion·ClarificationAnswer VO
- `src/domain/agent_composer/policies.py` — PlannerPolicy(0.8/2라운드/3문항)
- `src/application/agent_composer/composer.py` — build_candidates_block 추출, plan 파라미터+_PLAN_BLOCK
- `src/application/agent_composer/compose_agent_use_case.py` — _try_plan/_maybe_clarification 분기, 폴백
- `src/application/agent_composer/schemas.py` — DTO additive 확장(status/questions/plan_summary/clarification_*)
- `src/api/main.py` — AgentPlanner DI(동일 LLM 인스턴스)
- `tests/application/agent_composer/test_agent_composer.py` — 계획 블록 검증 2건 추가

### 프론트엔드 (idt_front/)

**신규**
- `src/components/agent-builder/fix/ClarifyQuestionCard.tsx` (+ test 6건)

**수정**
- `src/types/agentComposer.ts` — 백엔드 스키마 동기화(신규 응답 필드는 optional로 구형 호환)
- `src/components/agent-builder/fix/FixAgentPanel.tsx` — sendCompose 공통화·pendingClarify 라운드 관리·답변 재호출 (+ test HITL 4건)
- `src/components/agent-builder/fix/ComposeDraftCard.tsx` — "빌드 계획" 섹션

**변경 없음**: 라우터·엔드포인트·인증·DB — `auto_agent_builder` 경로 무변경

---

## Lessons Learned

### 1. 유사 기능의 존재를 먼저 확정하라 — "질문 루프는 이미 있다"의 함정
`auto_agent_builder`에 세션 기반 clarification 루프가 이미 있었지만 Fix 탭과 무관한 별개 경로였다. Plan 현황 조사에서 프론트 훅(`useComposeAgent`)부터 역추적해 실제 소비 경로를 확정한 것이 스코프 오판(기존 루프 재활용 대 신규 설계)을 막았다.

### 2. optional 마지막 인자 주입 = 하위호환의 구조적 증명
`planner: PlannerInterface | None = None`으로 추가하니 기존 테스트 13건이 **수정 없이** 통과하며 그 자체로 하위호환 증거가 됐다. 설계상 "필수 인자"보다 이 형태가 우월해 설계 문서를 역정정(G4) — 문서와 코드가 어긋나면 더 합리적인 쪽으로 수렴시키되 기록을 남긴다.

### 3. Stateless HITL의 관건은 에코백 계약
세션이 없으므로 서버는 질문을 기억하지 못한다. 답변 DTO에 질문 텍스트를 실어 되돌리는 에코백(D8)과, 라운드 번호를 클라이언트 신고+서버 clamp로 처리하는 이중 방어가 상태 저장 없이 다회 왕복을 성립시켰다.

### 4. `warning`에도 exception kwarg가 통한다 — 로거 구현을 먼저 읽어라
LoggerInterface 시그니처만 보면 warning에 exception 파라미터가 없지만, StructuredLogger `_log`가 명시 파라미터로 받아 exc_info를 기록한다. G2를 고치기 전 구현을 확인해 "동작하는 척하는 수정"을 피했다.

---

## 차기 과제 (Next Steps)

1. **E2E 수동 검증** (이월): 서버 기동 후 모호 요청→질문 카드→답변→계획 반영 초안→적용, create/edit 각 1회. venv 인터프리터로 기동([[idt-server-must-run-on-venv]] 선례)
2. **지연 실측**: 질문 생략 경로도 LLM 2회(Planner+Composer) — LangSmith `plan:*`/`compose:*` run 시간으로 +5s 이내 목표 확인. 초과 시 Planner 경량 모델 분리(settings 한 줄 여지 확보됨)
3. **LangGraph interrupt 전환** (후속 PDCA 후보): PlannerInterface 계약 유지한 채 checkpointer 기반 구현체 교체
4. **커밋/PR**: 미수행 — 변경 파일 백엔드 12·프론트 6 (분석/보고 문서 포함)

---

## 커밋 & PR 상태

- 브랜치: `feature/pdca-batch-2026-08-2` (기존 작업분과 공존)
- 커밋: **미수행** — 사용자 지시 대기
- 배포 전 체크: 마이그레이션 없음, 서버 재기동만 필요

---

## 관련 문서

- Plan: `docs/01-plan/features/fix-agent-planner-hitl.plan.md`
- Design: `docs/02-design/features/fix-agent-planner-hitl.design.md`
- Analysis: `docs/03-analysis/fix-agent-planner-hitl.analysis.md`
- 선례: fix-agent-composer(증분 수정 compose)·nl-agent-composer(초안 조합)·mutation-pending-guard(isPending 가드)
