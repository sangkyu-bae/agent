# fix-agent-planner-hitl Planning Document

> **Summary**: `/agent-builder` Fix 에이전트 탭의 단발 compose(LLM 1회) 경로에 **Planner 모듈**을 앞단으로 신설 — 요구를 분석해 빌드 계획을 세우고, 정보가 부족하면 **구조화 질문 카드(HITL)** 로 사용자에게 되물은 뒤, 확정된 계획을 Composer에 넘겨 더 정확한 초안을 만든다. 상태는 서버 무저장(stateless) 원칙을 유지한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-08-06
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | Fix 탭은 사용자의 한 문장을 받아 `AgentComposer` LLM 1회 호출로 즉시 초안을 만든다. 요청이 모호해도(대상 문서 범위·검색 방식·출력 형태 미지정) 질문 없이 추측으로 초안을 내므로, 사용자는 여러 번 고쳐 말하며 시행착오를 반복한다. 별도 경로(`auto_agent_builder`)에 질문 루프가 있으나 Fix 탭과 연결되어 있지 않다. |
| **Solution** | compose 파이프라인을 **Planner → Composer 2단계 모듈**로 재구성한다. Planner가 요구를 역량 단위로 분석해 빌드 계획(BuildPlan)을 수립하고, confidence가 낮으면 선택지가 달린 **구조화 질문**을 반환한다(HITL). 프론트는 질문 카드를 렌더링하고, 답변을 모아 같은 엔드포인트로 재호출한다 — 서버 세션·DB 없이 요청 페이로드로 왕복하는 stateless HITL. 확정된 계획은 Composer 프롬프트에 주입되어 초안 정확도를 높인다. |
| **Function/UX Effect** | 사용자가 "여신 규정 문서로 답하는 봇 만들어줘"라고 치면, 봇이 "어느 부서 문서 범위인가요? ①여신심사 ②전체 ③직접 입력" 같은 카드로 되묻고, 답을 반영한 계획 요약과 함께 초안 카드를 제시한다. 질문은 최대 2라운드로 제한되어 무한 되물음이 없다. create(신규)·edit(기존 수정) 모두 동일하게 동작한다. |
| **Core Value** | P2(에이전트 소유자)가 **한 번의 대화 왕복으로 의도에 맞는 에이전트**를 얻는다. Planner/Composer가 인터페이스로 분리된 독립 모듈이므로, 추후 LangGraph interrupt 기반 정식 HITL·계획 단계 추가(critic 등)로 갈아끼우기 쉽다. |

---

## 1. Overview

### 1.1 Purpose

Fix 에이전트 탭(생성/수정 채팅)의 백엔드에 계획 수립 단계(Planner)를 추가해 초안 품질을 높이고, 정보가 부족할 때 사용자에게 구조화 질문으로 되묻는 Human-in-the-Loop 왕복을 지원한다. 각 단계는 교체 가능한 모듈로 분리한다.

### 1.2 Background — 현황 조사 (완료)

| # | 확인 지점 | 결과 |
|---|-----------|------|
| 1 | `idt_front/src/components/agent-builder/fix/FixAgentPanel.tsx` | 채팅 입력 → `useComposeAgent` → 초안 카드(`ComposeDraftCard`) → "적용" 시 폼 프리필. 대화는 로컬 state(무저장), history 최근 6턴을 매 요청에 동봉 |
| 2 | `idt/src/api/routes/agent_composer_router.py` | `POST /api/v1/agents/compose` 단일 엔드포인트, `get_current_user` 인증, 무저장 |
| 3 | `idt/src/application/agent_composer/compose_agent_use_case.py` | 후보 수집(내부 TOOL_REGISTRY+MCP 카탈로그) → `AgentComposer` LLM 1회 → 서버 보정(drop/매핑/clamp) → 초안 응답. **질문/계획 단계 없음** |
| 4 | `idt/src/application/agent_composer/composer.py` | structured output 1회 호출(역량 분해·워커·system_prompt·flow_hint 통합). current_config 블록으로 증분 수정 지원 |
| 5 | `idt/src/application/auto_agent_builder/*` (`/api/v3/agents/auto`) | 세션 기반 clarification 루프(질문→답변→재추론→**직접 생성**)가 이미 존재하나 Fix 탭과 무관한 별개 경로. 질문은 자유 텍스트 배열, 구조화 없음 |
| 6 | `idt/src/domain/auto_agent_builder/policies.py` | CONFIDENCE_THRESHOLD 0.8, MAX_ATTEMPTS 3, MAX_QUESTIONS_PER_TURN 3 — 정책 상수 패턴 선례 |
| 7 | `idt_front/src/types/agentComposer.ts` | `ComposeAgentDraftResponse`에 status/questions 개념 없음 — 응답 확장 시 프론트 타입 동기화 필요 |

결론: 백엔드는 compose 파이프라인 내부에 Planner 모듈 신설 + 응답 스키마 additive 확장, 프론트는 질문 카드 UI + 답변 재호출 흐름 추가가 핵심이다. DB·마이그레이션 변경은 없다.

### 1.3 사용자 결정 사항 (확정)

1. **HITL 상태 관리**: **Stateless 확장** — compose 응답에 `needs_clarification` 상태+질문을 추가하고, 프론트가 답변을 요청 페이로드에 실어 재호출. 서버 세션·DB 변경 0
2. **파이프라인 깊이**: **2단계 Planner→Composer** — 각 단계를 독립 모듈(인터페이스)로 분리해 교체 용이. 3단계+(critic 등)는 후속
3. **질문 UX**: **구조화 질문 카드** — 질문마다 선택지(옵션)+자유 입력을 가진 카드, 답변을 모아 한 번에 제출
4. **적용 범위**: **Fix 탭 create+edit 모두** — `current_config` 유무로 생성 계획/수정 계획 분기. `auto_agent_builder` 통합은 범위 외

### 1.4 Related Documents

- 기존 compose 설계 선례: `docs/archive/*/nl-agent-composer*`, `fix-agent-composer` (아카이브)
- 질문 루프 선례: `idt/src/application/auto_agent_builder/` (세션 기반 — 이번엔 stateless로 재해석)
- 정책 상수 선례: `idt/src/domain/auto_agent_builder/policies.py`, `idt/src/domain/agent_composer/policies.py`
- 유저 시나리오 SoT: `docs/USER-SCENARIOS.md` (주인공 P2, 일반화>특화)
- 아키텍처 규칙: `idt/CLAUDE.md` (Thin DDD, TDD 필수), `idt/docs/rules/db-session.md`(해당 없음 — DB 무변경)

---

## 2. Scope

### 2.1 In Scope

**백엔드 (idt/)**

- [ ] **도메인 스키마**: `domain/agent_composer/schemas.py`에 `BuildPlan`(요구 요약·역량 목록·도구 방향·계획 노트·confidence), `ClarifyingQuestion`(id·question·options[]·allow_free_text), `ClarificationAnswer`(question_id·answer) 추가
- [ ] **PlannerPolicy**: `domain/agent_composer/policies.py` 확장 — `CONFIDENCE_THRESHOLD`(기본 0.8), `MAX_CLARIFICATION_ROUNDS`(기본 2), `MAX_QUESTIONS_PER_ROUND`(기본 3), 라운드 초과 시 강제 진행(force-proceed) 판정. 값은 config 주입 가능(하드코딩 금지)
- [ ] **Planner 모듈**: `application/agent_composer/planner.py` — `AgentPlanner`(LLM structured output 1회): 요청+후보 도구+current_config+이전 Q/A를 받아 `BuildPlan`+`clarifying_questions` 산출. **도메인 인터페이스(`PlannerInterface`) 뒤에 구현**해 교체 가능하게
- [ ] **UseCase 오케스트레이션**: `ComposeAgentUseCase` 확장 — ① Planner 호출 → ② 질문 필요·라운드 여유 시 `status="needs_clarification"` 응답 반환 → ③ 아니면 BuildPlan을 Composer 프롬프트에 주입해 초안 조합. **Planner 실패 시 기존 단발 compose로 폴백**(graceful degradation)
- [ ] **요청 스키마 확장(additive)**: `ComposeAgentRequest`에 `clarification_answers: list[ClarificationAnswer] | None`, `clarification_round: int = 0` 추가 — 미전송 시 기존 동작과 동일한 opt-in 계약. 라운드 수는 서버가 정책 상한으로 clamp
- [ ] **응답 스키마 확장(additive)**: `ComposeAgentDraftResponse`에 `status: "draft" | "needs_clarification"`(기본 "draft"), `questions: list[ClarifyingQuestionDto]`, `plan_summary: str` 추가 — 기존 필드·coverage 의미 불변
- [ ] **Composer 프롬프트 확장**: `AgentComposer.compose()`에 `plan: BuildPlan | None` 파라미터 추가 — 계획 블록([빌드 계획])을 시스템 프롬프트에 부착. plan=None이면 기존과 동일
- [ ] **관측**: Planner LLM 호출에 LangSmith tracer 부착(`make_composer_tracer` 재사용, run_name `plan:{...}`), 라운드·confidence 로깅
- [ ] 테스트: pytest TDD — PlannerPolicy 단위, AgentPlanner 파싱/프롬프트, UseCase 분기(질문/강제진행/폴백/기존 호환) 

**프론트엔드 (idt_front/)**

- [ ] **타입 동기화**: `types/agentComposer.ts` — status·questions·plan_summary·clarification_answers·clarification_round 추가
- [ ] **질문 카드 컴포넌트**: `components/agent-builder/fix/ClarifyQuestionCard.tsx` — 질문별 선택지 버튼+자유 입력, 전체 답변 모아 제출. 제출 후 카드 비활성(답변 완료 표시)
- [ ] **FixAgentPanel 흐름 확장**: 응답 `status==="needs_clarification"`이면 질문 카드 렌더 → 답변 제출 시 원 요청+`clarification_answers`+`clarification_round+1`로 재호출. 답변 내용은 history에도 텍스트로 요약 반영(기존 6턴 절단 정책 유지)
- [ ] **초안 카드에 plan_summary 표시**: 초안이 어떤 계획으로 만들어졌는지 1~3문장 노출
- [ ] 테스트: Vitest+MSW(파일별 server.listen 3종 훅, `--pool=threads`), 질문 카드 렌더·답변 제출·재호출 페이로드 검증

### 2.2 Out of Scope

- **LangGraph interrupt/checkpointer 기반 정식 HITL** — 인터페이스만 호환되게 설계하고 전환은 후속 PDCA
- **`auto_agent_builder`(`/api/v3/agents/auto`) 통합·리팩토링** — 별개 경로 그대로 유지, 변경 없음
- **3단계+ 파이프라인(자체 검증 critic, 도구 매칭 전용 단계)** — 후속
- **질문/계획의 서버 영속화**(세션·DB 저장, 이어하기) — 무저장 원칙 유지
- **Fix 탭 외 소비처**(생성 폼 직접 진입, 워크스페이스 등)로의 planner 노출
- **WS 스트리밍 전환** — 기존 HTTP 단건 요청 유지
- **DB 마이그레이션** — 신규 테이블/컬럼 없음

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | compose 요청 시 Planner가 요구를 분석해 BuildPlan(요약·역량·도구 방향·confidence)을 산출한다 | High | Pending |
| FR-02 | confidence < 임계값이고 라운드 여유가 있으면 `needs_clarification` 상태와 구조화 질문(선택지+자유입력 허용 플래그, 최대 3개)을 반환한다 | High | Pending |
| FR-03 | 프론트는 질문 카드를 렌더링하고, 사용자의 답변을 모아 `clarification_answers`로 같은 엔드포인트에 재호출한다 | High | Pending |
| FR-04 | 질문 라운드는 최대 2회로 제한되며, 초과 시 Planner는 질문 없이 best-effort 계획으로 강제 진행한다 | High | Pending |
| FR-05 | 확정된 BuildPlan이 Composer 프롬프트에 주입되어 초안이 계획과 일관되게 조합되고, 응답 `plan_summary`로 노출된다 | High | Pending |
| FR-06 | create(빈 폼)·edit(current_config 있음) 모두 동작하며, edit에서는 기존 설정 유지 원칙(증분 수정 규칙)이 계획에 반영된다 | High | Pending |
| FR-07 | `clarification_*` 필드를 보내지 않는 기존 요청은 종전과 동일하게 동작한다(하위호환, additive 계약) | High | Pending |
| FR-08 | Planner LLM 호출 실패 시 기존 단발 compose로 폴백하고 경고 로그를 남긴다 — 사용자 관점 기능 저하 없음 | Medium | Pending |
| FR-09 | Planner/Composer는 각각 인터페이스 뒤의 독립 모듈로, DI 교체만으로 구현을 갈아끼울 수 있다 | Medium | Pending |
| FR-10 | Planner 호출이 LangSmith에 `plan:*` run으로 추적되고, 라운드·confidence가 로깅된다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | Thin DDD 유지 — 스키마·정책은 domain, LLM 호출·오케스트레이션은 application, 라우터는 변환만. domain→infrastructure 참조 금지 | verify-architecture |
| 하위호환 | 기존 compose 소비 계약(필드·의미) 불변, 신규 필드는 전부 optional/기본값 | 기존 pytest·Vitest 무수정 통과 |
| 지연 | 질문 불필요 시 LLM 2회(Planner+Composer)로 증가 — 총 지연 목표 기존 대비 +5s 이내, confidence 높은 단순 요청은 Planner 결과만으로 질문 생략 | 수동 계측(LangSmith run 시간) |
| 비용 | Planner 프롬프트는 후보 도구 요약만 포함(기존 max_candidates 절단 재사용), 질문 라운드 상한으로 호출 수 bound | 코드 리뷰 |
| 상태 관리 | 서버 세션·DB 쓰기 0 — 모든 왕복 상태는 요청/응답 페이로드와 프론트 로컬 state | 코드 리뷰 |
| 설정 | 임계값·라운드 상한·질문 수 상한은 정책 상수(+config 주입 가능), 하드코딩 금지 | 코드 리뷰 |
| 테스트 | TDD — 실패 테스트 먼저. 프론트 MSW 핸들러로 needs_clarification 시나리오 재현 | pytest / Vitest 통과 |

---

## 4. 설계 방향 (Design 단계 입력)

### 4.1 모듈 구조

```
domain/agent_composer/
  schemas.py      + BuildPlan, ClarifyingQuestion, ClarificationAnswer
  policies.py     + PlannerPolicy (threshold, rounds, force-proceed 판정)
  interfaces.py   + PlannerInterface (신규 — 교체 지점)

application/agent_composer/
  planner.py      + AgentPlanner(PlannerInterface 구현, LLM structured output 1회)
  composer.py     ~ compose(plan=...) 파라미터 추가, [빌드 계획] 블록 부착
  compose_agent_use_case.py ~ Planner→분기(질문/강제진행)→Composer 오케스트레이션 + 폴백
  schemas.py      ~ 요청/응답 additive 확장

api/routes/agent_composer_router.py  변경 없음(스키마만 통과) 또는 최소
api/main.py     ~ AgentPlanner DI 배선
```

### 4.2 HITL 왕복 시퀀스 (stateless)

```
[1차] user_request ──▶ Planner ──▶ confidence 낮음
      ◀── status=needs_clarification, questions[3], (round=0)
[2차] user_request + clarification_answers + round=1
      ──▶ Planner(답변 반영) ──▶ confidence 충족 ──▶ Composer(plan 주입)
      ◀── status=draft, plan_summary, 초안 필드들
(라운드 상한 도달 시: 질문 생략, best-effort 강제 진행)
```

- 재호출 시 프론트는 **원 요청 문장을 그대로** 보내고, Q/A는 구조화 필드로 동봉 — 서버가 세션 없이 전체 맥락 재구성
- `clarification_round`는 클라이언트 신고값이지만 서버가 정책 상한으로 clamp하므로 조작해도 라운드만 소진됨

### 4.3 열린 설계 결정 (Design 단계에서 확정)

1. Planner 출력에 도구 후보 pre-selection을 포함할지(Composer 후보 절단에 활용) vs 순수 계획만
2. 질문 카드 제출 시 미답변 질문 허용 여부(부분 답변 제출)
3. plan_summary의 초안 카드 내 표시 위치(notes 병합 vs 별도 섹션)
4. Planner LLM 모델: Composer와 동일 모델 재사용 vs 경량 모델 분리 배정

---

## 5. 구현 순서 (Do 단계 가이드)

1. **[BE] 도메인**: BuildPlan·ClarifyingQuestion 스키마 + PlannerPolicy (pytest 먼저)
2. **[BE] Planner 모듈**: AgentPlanner 프롬프트·structured output·인터페이스 (pytest)
3. **[BE] UseCase 오케스트레이션**: 분기·강제진행·폴백 + 요청/응답 스키마 확장 (pytest)
4. **[BE] Composer plan 주입** + DI 배선 (pytest)
5. **[FE] 타입·서비스 동기화** (/api-contract-sync 체크리스트)
6. **[FE] ClarifyQuestionCard + FixAgentPanel 흐름** (Vitest+MSW)
7. **[공통] 회귀 확인**: 기존 compose 테스트 무수정 통과, E2E 수동 시나리오(질문→답변→초안→적용)

---

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Planner가 사소한 요청에도 과잉 질문 → UX 악화 | 중 | confidence 임계값 튜닝 + "질문은 초안 품질을 실질적으로 바꿀 정보만" 프롬프트 규칙 + 라운드 상한 2 |
| LLM 2회 호출로 지연 증가 | 중 | 단순 요청은 질문 생략(1왕복 내 완료), 후보 블록 재사용으로 프롬프트 경량화. 모델 분리는 설계 결정 4 |
| 응답 스키마 확장이 기존 프론트 흐름 파손 | 고 | additive-only(기본값 "draft") + 기존 테스트 무수정 통과를 회귀 기준선으로 |
| 질문 텍스트가 history 절단(6턴·500자)으로 유실 | 중 | Q/A는 history가 아닌 구조화 필드로 왕복 — history는 보조 요약만 |
| Planner 장애 시 Fix 탭 전체 불능 | 고 | try/except 폴백으로 기존 단발 compose 경로 보존 (FR-08) |

---

## 7. Completion Criteria

- [ ] FR-01~FR-10 구현 및 테스트 통과 (pytest + Vitest)
- [ ] 기존 compose 관련 테스트 무수정 통과 (하위호환 증명)
- [ ] verify-architecture 통과 (레이어 규칙)
- [ ] E2E 수동: 모호 요청→질문 카드→답변→계획 반영 초안→적용, create/edit 각 1회
- [ ] Gap 분석(Match Rate) ≥ 90%
