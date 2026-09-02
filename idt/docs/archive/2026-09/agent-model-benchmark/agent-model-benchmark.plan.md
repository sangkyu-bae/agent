# agent-model-benchmark Planning Document

> **Summary**: 동일 에이전트를 여러 LLM 모델로 순차 실행해 품질(RAGAS)·비용·지연·도구호출 정확도 4축을 한 표로 비교하는 **모델 스윕(sweep)** 기능을 기존 Eval Hub에 확장한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-31
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 지금 구조는 **1 run = 1 에이전트(에이전트에 저장된 고정 모델)** 이다. `evaluation_run`에는 모델 차원 자체가 없고(`target_id`=agent_id만 존재), `target_executor._run_agent()`는 `config.llm_model`을 **무시**한 채 에이전트 자신의 모델로 실행한다. 결과적으로 모델을 바꿔 비교하려면 에이전트 설정을 직접 고쳐 다시 돌려야 하고, 결과에 "어떤 모델이었는지"조차 기록되지 않아 **모델 간 비교가 원천적으로 불가능**하다. |
| **Solution** | (a) `RunAgentRequest`에 **모델·temperature 오버라이드**를 additive로 추가해 에이전트 정의를 건드리지 않고 모델만 갈아끼우고, (b) N개 run을 묶는 **`evaluation_sweep`** 개념을 신설해 `evaluation_run`에 `sweep_id`·`llm_model_id`를 부여하며, (c) 케이스별 `ai_run_id`를 연결해 **토큰·비용·지연을 실측**으로 회수하고, (d) 테스트셋 케이스의 `expected_tools`와 `RunAgentResponse.tools_used`를 대조해 **도구호출 F1**을 산출한다. Judge 모델은 화면에서 선택해 실행에 박제한다. |
| **Function/UX Effect** | Eval Hub에서 에이전트 1개 + 테스트셋 1개 + 모델 N개 + judge 모델을 고르면, **예상 비용을 먼저 보여주고 확인 후** 순차 실행한다. 완료 시 **행=모델 / 열=지표(품질·비용·지연·도구정확도)** 매트릭스 표에 최고값이 하이라이트되어, 어떤 모델로 갈지 한 화면에서 결정된다. |
| **Core Value** | P2(에이전트 소유자/KB 운영자)가 **"싼 모델로 내려도 품질이 유지되는가"를 감이 아니라 숫자로** 판단한다. NPU/self-host 전환 판단(`admin-default-llm-routing`의 원래 동기)에 필요한 실측 근거가 처음으로 확보된다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 평가 스택에 모델 차원이 없어 모델 간 성능·비용 트레이드오프를 수치로 비교할 수 없다 |
| **WHO** | P2 — 자기 에이전트의 품질과 운영비를 스스로 검증해야 하는 에이전트 소유자 / KB 운영자 |
| **RISK** | 모델 오버라이드가 `RunAgentRequest` 소비자 8곳(웹소켓·스케줄·웹훅·백그라운드잡 등)이 공유하는 실행 경로를 침습한다 |
| **SUCCESS** | 에이전트 1개 × 모델 N개 스윕 실행 → 4축 지표가 채워진 매트릭스 표가 뜨고, 같은 조건 재실행 시 품질 점수 편차 ≤ 5% |
| **SCOPE** | 백엔드: 모델 오버라이드 + sweep 도메인 + 지표 수집 3종 / 프론트: 스윕 생성 모달 + 매트릭스 표. 에이전트 생성·테스트셋 생성·차트 시각화는 제외 |

---

## 1. Overview

### 1.1 Purpose

동일한 에이전트와 동일한 골든셋을 고정한 채 **LLM 모델만 바꿔가며 N회 실행**하고, 그 결과를 **품질·비용·지연·도구호출 정확도** 4축으로 나란히 비교할 수 있게 한다. 목표는 "우리 업무에 어떤 모델이 가장 적합한가"를 재현 가능한 실험으로 답하는 것이다.

### 1.2 Background — 현황 조사 (완료)

| # | 확인 지점 | 결과 |
|---|-----------|------|
| 1 | `db/migration/V020__create_evaluation_tables.sql` | `evaluation_run`에 **모델 차원 없음**. `target_id`(agent_id)와 `config JSON`만 존재 |
| 2 | `src/infrastructure/ragas/target_executor.py:76-91` | `_run_agent()`는 `agent_runner(agent_id, question, user_id, request_id)`만 호출 → **`config.llm_model`을 무시**. 모델 오버라이드 경로 부재 |
| 3 | `src/application/ragas/schemas.py:14` | `BatchEvalRequest.llm_model` 필드는 **이미 존재**하나, rag 대상의 답변 생성 LLM으로만 쓰이고 agent 대상에는 미적용 |
| 4 | `src/infrastructure/ragas/ragas_adapter.py:24` | `RagasEvaluatorAdapter(llm_model="gpt-4o-mini")` — judge 모델이 **DI 시점 고정**(`main.py:3362`), 실행별 지정 불가 |
| 5 | `src/application/agent_builder/schemas.py:220` | `RunAgentRequest` = `query / user_id / session_id / attachments`. **모델·temperature 오버라이드 없음** |
| 6 | `src/application/agent_builder/schemas.py:229` | `RunAgentResponse`에 **`tools_used: list[str]`와 `run_id` 존재** → 도구 정확도·관측 연결의 재료가 이미 있음 |
| 7 | `db/migration/V021__create_agent_run_tables.sql` | `ai_run`에 `llm_model_id / prompt_tokens / completion_tokens / total_cost_usd / latency_ms` 보유 → **비용·지연 실측 가능** |
| 8 | `evaluation_result` | `metrics JSON`은 있으나 `ai_run` 연결 키가 없어 토큰·지연을 케이스에 붙일 수 없음 |
| 9 | `evaluation_testset.cases JSON` | `question / ground_truth / expected_contexts / metadata` 구조. **JSON이라 `expected_tools` 추가는 DDL 변경 불필요** |
| 10 | `idt_front/src/pages/EvalDatasetPage/` | 데이터셋·평가실행·평가기·대시보드 4탭 구현 완료(eval-hub) → 스윕 UI를 얹을 자리가 있음 |

**결론**: 평가 인프라·관측 인프라·모델 단가는 전부 갖춰져 있고, 빠진 것은 이 셋을 잇는 **모델 차원**과 **오버라이드 경로** 딱 두 가지다.

### 1.3 사용자 결정 사항 (확정)

| # | 항목 | 결정 |
|---|------|------|
| 1 | 비교 축 | **동일 에이전트 × 모델 N개 스윕** (에이전트 M개 매트릭스는 제외) |
| 2 | 측정 지표 | RAGAS 품질 + 비용 + 지연 + **도구호출 정확도** 4종 전부 |
| 3 | 구현 범위 | **기존 Eval Hub 확장** (별도 벤치마크 모듈 신설 안 함) |
| 4 | 테스트셋 | **기존 `evaluation_testset` 재사용** (신규 생성 경로 추가 없음) |
| 5 | Judge 모델 | **고정하지 않고 화면에서 선택 → 서버로 전달**, 실행에 기록 |
| 6 | 도구 정확도 정의 | `expected_tools` **집합 일치율**(precision/recall/F1). 순서 무시 |
| 7 | 실행 방식 | **순차 실행 + 사전 비용 추정 표시** 후 사용자 확인 |
| 8 | 결과 UI | **모델 × 지표 매트릭스 표** (케이스별 답변 비교·차트 제외) |
| 9 | 에이전트 준비 | **기존 Agent Builder로 미리 생성 → 드롭다운 선택만** |
| 10 | 재현성 | **temperature=0 고정** + 실행 스냅샷(에이전트/judge/테스트셋/모델목록) 기록 |

### 1.4 Related Documents

- 평가 테이블: `idt/db/migration/V020__create_evaluation_tables.sql`
- 관측 테이블: `idt/db/migration/V021__create_agent_run_tables.sql`
- 모델 레지스트리·단가: `idt/db/migration/V003`, `V022__add_llm_model_pricing.sql`
- 선행 기능: `idt/docs/archive/2026-08/eval-hub/eval-hub.design.md`
- 모델 라우팅 배경: `idt/docs/archive/2026-08/admin-default-llm-routing/admin-default-llm-routing.design.md`
- 도구 규칙: `idt/docs/rules/tool-and-mcp.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] `RunAgentRequest`에 `llm_model_id_override` / `temperature_override` **선택 필드 추가**(additive)
- [ ] `run_agent_use_case`에서 오버라이드 적용 — 미지정 시 기존 동작 100% 유지
- [ ] `evaluation_sweep` 테이블 신설 (스윕 = run N개의 부모)
- [ ] `evaluation_run`에 `sweep_id` / `llm_model_id`(피평가 모델) / `judge_llm_model_id` 컬럼 추가
- [ ] `evaluation_result`에 `ai_run_id` / `tools_used` 컬럼 추가 (비용·지연·도구 회수용)
- [ ] 스윕 생성 API — 에이전트 1 + 테스트셋 1 + 모델 N + judge 모델 → run N개 순차 실행
- [ ] **사전 비용 추정 API** — 모델 단가 × 테스트셋 케이스 수 기반 예상 USD 반환
- [ ] Judge 모델 실행별 주입 (`RagasEvaluatorAdapter`의 DI 고정 해소)
- [ ] 도구호출 정확도 산출 — `expected_tools` ∩ `tools_used` 기반 precision/recall/F1
- [ ] 스윕 상세 조회 API — 모델별 4축 집계값 반환
- [ ] 프론트: Eval Hub '평가 실행' 탭에 **스윕 생성 모달** + **모델 × 지표 매트릭스 표**
- [ ] 소유권 — 본인 스윕만 조회, 관리자는 전체 (기존 `_scope()` 선례 준수)

### 2.2 Out of Scope

- 에이전트 생성·복제 (기존 Agent Builder가 담당)
- 테스트셋 신규 생성 경로 (기존 Eval Hub 3종 그대로 사용)
- 에이전트 M개 × 모델 N개 풀 매트릭스
- 모델별 병렬 실행 (지연 측정 오염·rate limit 회피 위해 순차 고정)
- 케이스별 답변 나란히 비교(diff) 패널
- 레이더/막대 차트 시각화
- 예산 상한 초과 시 자동 중단 (이번엔 사전 추정 표시까지만)
- Judge 편향 교차검증 (judge 복수 실행)
- rag / retrieval 대상 스윕 (이번은 **agent 대상만**)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `RunAgentRequest`에 `llm_model_id_override`·`temperature_override`를 선택 필드로 추가하고, 미지정 시 기존 에이전트 설정을 그대로 사용한다 | High | Pending |
| FR-02 | 에이전트 실행 시 오버라이드된 모델·temperature가 실제 LLM 호출과 `ai_run.llm_model_id`에 반영된다 | High | Pending |
| FR-03 | `evaluation_sweep`을 신설해 스윕 1건이 run N건을 소유한다 (에이전트·테스트셋·judge·모델목록·temperature 스냅샷 포함) | High | Pending |
| FR-04 | 스윕 생성 API가 선택된 모델 수만큼 `evaluation_run`을 만들고 **순차** 실행한다 | High | Pending |
| FR-05 | 스윕 실행 전 예상 비용(USD)을 `llm_model` 단가 × 케이스 수로 추정해 반환하고, 사용자 확인 후 실행한다 | High | Pending |
| FR-06 | Judge 모델을 요청 파라미터로 받아 RAGAS 채점에 주입하고 `evaluation_run.judge_llm_model_id`에 기록한다 | High | Pending |
| FR-07 | 케이스 실행 결과에 `ai_run_id`를 연결해 토큰·비용·지연을 실측으로 회수한다 | High | Pending |
| FR-08 | 테스트셋 케이스의 `expected_tools`와 실행의 `tools_used`를 집합 비교해 precision/recall/F1을 산출·저장한다 | High | Pending |
| FR-09 | 스윕 상세 API가 모델별 집계(품질 평균, 총비용, latency p50/p95, 도구 F1)를 반환한다 | High | Pending |
| FR-10 | 스윕 실행 시 temperature를 0으로 고정한다 | Medium | Pending |
| FR-11 | 프론트에 스윕 생성 모달(에이전트·테스트셋·모델 다중선택·judge 선택·예상비용 확인)을 추가한다 | High | Pending |
| FR-12 | 프론트에 행=모델 / 열=지표 매트릭스 표를 렌더하고 지표별 최고값을 하이라이트한다 | High | Pending |
| FR-13 | 개별 run 실패가 스윕 전체를 중단시키지 않고, 해당 모델 행만 실패로 표시한다 | Medium | Pending |
| FR-14 | 일반 사용자는 본인 스윕만, 관리자는 전체를 조회한다 (미소유 시 404 은닉) | Medium | Pending |
| FR-15 | `expected_tools` 미기재 케이스는 도구 정확도 집계에서 제외한다 (0점 아님) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 재현성 | 동일 스윕 재실행 시 모델별 품질 평균 편차 ≤ 5%p | temperature=0 고정 + 동일 조건 2회 실행 비교 |
| 하위 호환 | 오버라이드 미지정 경로(웹소켓·스케줄·웹훅·백그라운드잡)의 동작 무변경 | `RunAgentRequest` 소비자 8곳 회귀 테스트 |
| 비용 안전 | 실행 전 예상 비용이 실제 비용의 ±30% 이내 | 추정치 vs `ai_run.total_cost_usd` 합계 대조 |
| 성능 | 스윕 실행은 비동기(202 Accepted), 진행 상태 폴링 가능 | 기존 `BatchEvalExecutor.kickoff` 패턴 준수 |
| 아키텍처 | domain → infrastructure 참조 없음, Repository 내부 commit/rollback 없음 | `/verify-architecture` 스킬 |
| DDL 규약 | 신규 마이그레이션(V067+) 테이블·전 컬럼 COMMENT 필수 | `tests/db/test_migration_ddl_comments.py` |
| 로깅 | 스윕/런 상태 전이마다 `request_id` 포함 구조화 로그, print() 금지 | `/verify-logging` 스킬 |
| TDD | 구현 전 테스트 작성 (Red → Green → Refactor) | `/verify-tdd` 스킬 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-15 전부 구현
- [ ] 에이전트 1개 × 모델 3개 × 케이스 10건 스윕이 끝까지 성공 실행
- [ ] 매트릭스 표에 4축 지표가 모두 채워짐 (빈칸·NaN 없음)
- [ ] 오버라이드 미지정 시 기존 에이전트 실행 동작이 바뀌지 않음을 회귀 테스트로 입증
- [ ] pytest 통과 (신규 모듈 단위 + 통합)
- [ ] 프론트 Vitest + MSW 통과
- [ ] `idt_front/src/types/` 타입과 백엔드 스키마 동기화 (`/api-contract-sync`)

### 4.2 Quality Criteria

- [ ] `/verify-architecture` 통과 (레이어 위반 0)
- [ ] `/verify-logging` 통과 (LOG-001)
- [ ] `/verify-tdd` 통과 (신규 프로덕션 모듈 전부 테스트 존재)
- [ ] `tests/db/test_migration_ddl_comments.py` 통과
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수
- [ ] lint 에러 0

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **R-1** 모델 오버라이드가 `RunAgentRequest` 공유 소비자 8곳(ws_router·스케줄·웹훅·백그라운드잡·첨부 resolver 등)을 깨뜨림 | High | Medium | 필드를 **Optional + 기본 None**으로만 추가하고 기존 시그니처·인자 제거 금지(additive 원칙). 소비자 8곳 전부 §6.2에 열거하고 회귀 테스트로 고정 |
| **R-2** Judge 모델이 실행마다 달라져 과거 실행과 점수 비교가 불가능해짐 | High | High | judge를 `evaluation_run.judge_llm_model_id`에 **박제**하고, 매트릭스 표에 judge 모델명을 항상 병기. 서로 다른 judge의 run은 같은 표에 섞지 않는다 |
| **R-3** 예상 비용이 실제와 크게 어긋나 사용자가 과금 폭탄을 맞음 | High | Medium | 추정에 judge 채점 호출분을 반드시 포함. 추정 근거(케이스 수 × 모델 수 × 평균 토큰 가정)를 화면에 노출하고 "추정치" 라벨 명시 |
| **R-4** 특정 모델이 도구 호출을 지원하지 않아 도구 F1이 0으로 찍혀 부당하게 낮게 평가됨 | Medium | Medium | 도구 미지원·미호출을 **실패가 아닌 "N/A"** 로 구분 표기. FR-15로 `expected_tools` 없는 케이스는 집계 제외 |
| **R-5** `expected_tools`가 기존 테스트셋에 없어 도구 정확도가 전부 N/A | Medium | High | JSON 필드라 추가는 무DDL. 테스트셋 편집 UI에 `expected_tools` 입력을 열어두되, 미기재여도 나머지 3축은 정상 동작하게 설계 |
| **R-6** 순차 실행이라 모델 5개 × 케이스 20건 = 100회 + judge 채점으로 스윕 시간이 매우 길어짐 | Medium | High | 비동기 202 + 진행률 폴링. 스윕 생성 시 예상 소요시간도 함께 표시. 모델 수 상한(예: 5)을 정책으로 강제 |
| **R-7** `ai_run` 연결 실패(스케줄·헤드리스 경로에서 run_id 미생성)로 비용·지연이 비게 됨 | Medium | Medium | `_run_agent_headless`가 `RunAgentResponse.run_id`를 반드시 반환하도록 확인. 누락 시 해당 지표만 N/A로 낙하시키고 품질 지표는 살린다 |
| **R-8** Eval Hub 대시보드의 기존 집계 쿼리가 sweep run까지 섞어 세어 통계가 왜곡됨 | Medium | Medium | 기존 대시보드 쿼리에 `sweep_id IS NULL` 필터를 넣을지 여부를 Design에서 결정. §6.2 소비자 목록에 명시 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `RunAgentRequest` | Schema | `llm_model_id_override: str \| None`, `temperature_override: float \| None` **추가**(선택) |
| `run_agent_use_case` | UseCase | 오버라이드 값이 있으면 LLM 생성 시 적용 |
| `evaluation_run` | DB Model | `sweep_id`, `llm_model_id`, `judge_llm_model_id` 컬럼 **추가** |
| `evaluation_result` | DB Model | `ai_run_id`, `tools_used` 컬럼 **추가** |
| `evaluation_sweep` | DB Model | **신규 테이블** |
| `evaluation_testset.cases` | JSON 구조 | `expected_tools: string[]` 키 **추가**(무DDL, 선택) |
| `RagasEvaluatorAdapter` | Adapter | judge 모델을 생성자 고정 → **호출별 주입**으로 변경 |
| `DefaultTargetExecutor._run_agent` | Adapter | `AgentRunner` 시그니처에 모델 오버라이드 인자 추가 |
| `/api/ragas/sweeps*` | API | **신규 엔드포인트** (생성·비용추정·목록·상세) |
| `idt_front/src/types/` | Type | 스윕 관련 타입 신규 |
| `idt_front/src/constants/api.ts` | Config | 스윕 엔드포인트 상수 추가 |

### 6.2 Current Consumers

**`RunAgentRequest` 소비자 (Optional 필드 추가이므로 전부 무영향 예상 — 검증 필요)**

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `RunAgentRequest` | 생성 | `src/api/routes/agent_builder_router.py` — 에이전트 실행 REST | None (필드 미전달) |
| `RunAgentRequest` | 생성 | `src/api/routes/ws_router.py` — 웹소켓 스트리밍 실행 | Needs verification |
| `RunAgentRequest` | 생성 | `src/application/agent_schedule/trigger_due_schedules_use_case.py` | Needs verification |
| `RunAgentRequest` | 생성 | `src/application/agent_webhook/invoke_webhook_agent_use_case.py` | Needs verification |
| `RunAgentRequest` | 생성 | `src/application/background_job/worker.py` | Needs verification |
| `RunAgentRequest` | 생성 | `src/application/agent_attachment/resolver.py` | Needs verification |
| `RunAgentRequest` | 생성 | `src/api/main.py:3371` `_run_agent_headless` (평가용) | **Breaking — 오버라이드 전달하도록 수정 대상** |
| `RunAgentRequest` | 소비 | `src/application/agent_builder/run_agent_use_case.py` | **Breaking — 오버라이드 적용 로직 추가** |

**`evaluation_run` 소비자**

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `evaluation_run` | CREATE | `src/application/ragas/batch_eval_use_case.py:68` | Needs verification (신규 컬럼 nullable) |
| `evaluation_run` | UPDATE | `src/application/ragas/batch_executor.py` (`update_run`) | None |
| `evaluation_run` | READ | `src/api/routes/ragas_router.py` `/runs`, `/runs/{id}` | Needs verification (응답 스키마 확장) |
| `evaluation_run` | READ | `src/api/routes/admin_ragas_router.py` `/dashboard`, `/runs` | **Needs verification — sweep run 혼입 시 통계 왜곡(R-8)** |
| `evaluation_run` | DELETE | `src/api/routes/ragas_router.py` `DELETE /runs/{id}` | Needs verification (sweep FK 정합성) |
| `evaluation_run` | READ | `idt_front/src/pages/EvalDatasetPage/RunsTab.tsx`, `DashboardTab.tsx` | Needs verification |

**`RagasEvaluatorAdapter` 소비자**

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `RagasEvaluatorAdapter` | 생성 | `src/api/main.py:3362` (DI 배선) | **Breaking — judge 주입 방식 변경** |
| `RagasEvaluatorAdapter` | 호출 | `src/application/ragas/batch_executor.py:_evaluate_case` | **Breaking — judge 인자 전달 추가** |
| `RagasEvaluatorAdapter` | 호출 | `src/application/ragas/realtime_eval_use_case.py` | Needs verification (기존 기본값 유지) |

### 6.3 Verification

- [ ] `RunAgentRequest` 소비자 8곳이 오버라이드 미전달 시 기존과 동일하게 동작
- [ ] 웹소켓·스케줄·웹훅·백그라운드잡 실행 경로 회귀 테스트 통과
- [ ] `evaluation_run` 신규 컬럼이 전부 nullable이라 기존 row 조회가 깨지지 않음
- [ ] 관리자 RAGAS 대시보드 통계에 sweep run 혼입 여부를 확인하고 정책 결정
- [ ] 실시간 평가(`/realtime/evaluate`)의 judge 기본 동작 무변경
- [ ] `evaluation_sweep` 삭제 시 자식 run 정합성(CASCADE 여부) 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 구조 | 정적 사이트 | ☐ |
| **Dynamic** | 기능 단위 모듈, BaaS | 웹앱 MVP | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DI | 복잡한 아키텍처 | ☑ |

기존 프로젝트가 Thin DDD(domain / application / infrastructure / interfaces)를 이미 채택하고 있으므로 동일 규약을 따른다.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 스윕 저장 구조 | run에 sweep 컬럼만 추가 / **부모 테이블 신설** | **`evaluation_sweep` 신설** | 예상비용·judge·temperature·모델목록 스냅샷을 run마다 중복 저장하지 않고 한 곳에 박제 — 재현성 기록의 단일 지점 |
| 모델 오버라이드 위치 | 에이전트 정의 복제 / **요청 파라미터** | **요청 파라미터(additive)** | 에이전트 정의를 건드리지 않아 원본 오염·`agent_definition` 난립이 없다 |
| Judge 주입 | DI 고정 유지 / **호출별 주입** | **호출별 주입** | 사용자 결정 #5. 기본값은 현행 유지해 실시간 평가 경로 무영향 |
| 실행 동시성 | 병렬 / **순차** | **순차** | 지연 측정 오염 방지 + provider rate limit 회피 (사용자 결정 #7) |
| 지표 저장 | 집계 컬럼 신설 / **per-case JSON + 조회 시 집계** | **per-case + 조회 집계** | `evaluation_result.metrics` JSON 기존 패턴 재사용, 스키마 변경 최소화 |
| 비용·지연 출처 | 자체 계측 / **`ai_run` 조인** | **`ai_run` 조인** | V021 관측 스택이 이미 토큰·비용·지연을 정확히 적재 중 — 중복 계측 금지 |
| 도구 정확도 | 시퀀스 일치 / **집합 F1** | **집합 F1** | 사용자 결정 #6. 동등한 대안 경로를 오답 처리하지 않는다 |
| 프론트 상태관리 | Context / **TanStack Query + Zustand** | 기존 규약 준수 | `idt_front/CLAUDE.md` |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

idt/
├── domain/eval_sweep/          # SweepPolicy(모델 수 상한·temperature 고정),
│                               # ToolAccuracyPolicy(집합 F1), 엔티티, 인터페이스
├── application/eval_sweep/     # CreateSweepUseCase, EstimateSweepCostUseCase,
│                               # GetSweepDetailUseCase, SweepExecutor(순차 오케스트레이션)
├── infrastructure/eval_sweep/  # SweepRepository, ORM 모델
├── interfaces/schemas/         # 요청·응답 스키마
└── api/routes/                 # ragas_router 확장 (/sweeps*)

idt_front/src/
├── pages/EvalDatasetPage/      # CreateSweepModal.tsx, SweepMatrixPanel.tsx
├── hooks/                      # useSweeps.ts
├── services/                   # sweepService.ts
└── types/                      # sweep.ts
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규약 존재 (루트 + `idt/` + `idt_front/`)
- [x] `idt/docs/rules/` 세부 규칙 6종 (db-session, logging, tool-and-mcp, testing 등)
- [x] Flyway 마이그레이션 규약 (`db/migration/VNNN__*.sql`)
- [x] DDL COMMENT 강제 테스트 (`tests/db/test_migration_ddl_comments.py`)
- [x] 프론트 상수 export 규칙 (`as const`는 `src/types/*.ts`)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **마이그레이션 번호** | V066까지 존재 | 신규는 **V067부터**, 테이블·전 컬럼 COMMENT 필수 | High |
| **지표 키 네이밍** | `metrics JSON` 자유 형식 | `latency_ms`, `cost_usd`, `tool_precision/recall/f1` 키 규약 확정 | High |
| **N/A 표현** | 미정 | 측정 불가 지표는 `null`(0 아님), 프론트는 "N/A" 렌더 | High |
| **모델 수 상한** | 미정 | 스윕당 모델 수 상한값 확정 (제안: 5) | Medium |
| **소유권 404 은닉** | `eval_router.py` 선례 존재 | 동일 패턴 재사용 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| — | 신규 환경변수 없음 (모델·단가·judge 전부 DB `llm_model`에서 조회) | — | ☐ |

> 참고: `UTILITY_LLM_MODEL_NAME`이 설정돼 있으면 보조 LLM이 관리자 기본 모델을 무시한다. 스윕의 judge는 **요청 파라미터로 명시 주입**하므로 이 환경변수의 영향을 받지 않아야 한다 — Design에서 확인할 것.

### 8.4 Pipeline Integration

| Phase | Status | Document Location | Command |
|-------|:------:|-------------------|---------|
| Phase 1 (Schema) | ☑ | 기존 스키마 확장이라 신규 문서 불필요 | — |
| Phase 2 (Convention) | ☑ | `idt/CLAUDE.md` + `idt/docs/rules/` | — |

---

## 9. Next Steps

1. [ ] 설계 문서 작성 — `/pdca design agent-model-benchmark`
   - 3가지 아키텍처 옵션 비교 (특히 **모델 오버라이드 주입 지점**: UseCase vs LLM Factory vs Graph 빌드 시점)
   - `evaluation_sweep` DDL 확정 (V067)
   - 지표 키 네이밍 + N/A 규약 확정
   - 관리자 대시보드 sweep run 혼입 정책 결정 (R-8)
2. [ ] 미결 항목 확인
   - 스윕당 모델 수 상한값
   - 예상 비용 추정에 쓸 평균 토큰 가정치 산출 방법
3. [ ] TDD 구현 — `/pdca do agent-model-benchmark`
4. [ ] Gap 분석 — `/pdca analyze agent-model-benchmark`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1.0 | 2026-08-31 | 최초 작성 — 현황 조사 10건 + 사용자 결정 10건 반영 | 배상규 |
