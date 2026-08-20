# agent-create-wizard Planning Document

> **Summary**: `/agent-builder/new`를 「의도 수집 → 도구 추천 → 시스템 프롬프트 생성 → (스튜디오) 저장」 4단계 무상태 위저드로 교체하고, 공통 `ProgressCard`로 단계 진행을 노출한다.
>
> **Project**: sangplusbot (`idt` 백엔드 + `idt_front` 프론트엔드 — 풀스택 사이클)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-08-20
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 진입 화면(`/agent-builder/new`)은 구 `POST /api/v1/agents/compose` 1회 호출로 초안을 뽑는다 — 사용자가 **도구 선정·프롬프트 생성 과정을 보지도, 개입하지도 못한다**. 한편 이 흐름을 위해 만들어진 백엔드 3슬라이스(intent·prompt_composer·agent_create_pipeline)와 프론트 공통 컴포넌트 2종(ProgressCard·question-card)은 **미커밋·비활성·미배선**으로 떠 있다. |
| **Solution** | 파이프라인을 "1회 논스톱 실행"에서 **정지 지점 3곳을 갖는 무상태 위저드**로 확장(`stop_after` additive)하고, 진입 화면을 4스텝 위저드로 전면 교체한다. 위저드는 **프롬프트 생성까지만** 담당하고 DB 저장은 기존 계약대로 스튜디오 `[저장]`이 수행한다. |
| **Function/UX Effect** | 사용자는 ① 의도 질문에 카드뷰로 답하고 ② 추천된 도구를 확인·수정하고 ③ 생성된 시스템 프롬프트를 읽고 고친 뒤 저장한다. 5단계 진행바가 매 단계 실시간(SSE)으로 갱신되어 "지금 뭘 하고 있는지"가 항상 보인다. |
| **Core Value** | 자동 생성의 **불투명성 제거** — LLM이 내린 3개의 판단(의도·도구·프롬프트)마다 사람이 개입할 지점을 만들어, 자동화 편의와 통제권을 동시에 확보한다. 부수 효과로 5개 사이클치 미배선 자산이 첫 실사용 경로를 얻는다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 자동 생성이 블랙박스여서 결과가 어긋나도 사용자가 어느 단계에서 틀렸는지 알 수 없고, 개입할 수도 없다 |
| **WHO** | P2 — KB 운영자 / 에이전트 소유자 (`docs/USER-SCENARIOS.md` 주인공). 에이전트를 처음 만드는 비개발 실무자 |
| **RISK** | ① 정지 지점 추가로 파이프라인이 2개 모드를 갖게 되어 계약 복잡도 상승 ② 미커밋 코드 커밋 + V061~V063 마이그레이션이라는 배포 선행조건 ③ prompt_session이 스튜디오 저장까지 살아남아야 바인딩 성립 |
| **SUCCESS** | 설명 1문장 → 4스텝 완주 → 스튜디오 저장 → `GET /api/v1/agents/{id}`의 system_prompt·tool_ids가 위저드 확정값과 일치. 기존 5경로 회귀 0건 |
| **SCOPE** | 백엔드 확장(stop_after·human 프롬프트 버전·플래그/마이그레이션 활성화) + 프론트 위저드 전면 교체. **R1 수렴(구 compose·v3 auto 경로 통폐합)은 범위 밖** |

---

## 1. Overview

### 1.1 Purpose

`/agent-builder/new`에서 에이전트를 만드는 흐름을, 사용자가 **단계별로 확인·개입할 수 있는 위저드**로 바꾼다.

목표 흐름:

```
① 설명 입력   "여신 심사 문서를 찾아서 요약해주는 에이전트"
     ↓
② 의도 수집   ← HITL 정지 (question-card 카드뷰, 다회 왕복)
     ↓  answers 에코백
③ 도구 추천   ← 정지 (추천 토글 + 카탈로그에서 추가)
     ↓  확정 tool_ids
④ 프롬프트 생성 ← 정지 (읽고 편집 가능)
     ↓  [스튜디오로 보내기]
⑤ 스튜디오 프리필 → 사용자 [저장] → 에이전트 생성 + 프롬프트 세션 바인딩
```

### 1.2 Background

**핵심 배경: 필요한 백엔드 능력은 이미 전부 존재한다.** 최근 5개 사이클이 재료를 만들어 놓았고, 이번 사이클은 그것을 **정지 지점을 넣어 화면에 배선**하는 일이다.

| 능력 | 상태 | 위치 |
|------|------|------|
| 의도 분석 + 슬롯 되묻기 | ✅ 구현·등록됨 | `POST /api/v1/intent/analyze` |
| 도구 선별 (LLM) | ✅ 구현, **API 미노출** | `src/domain|infrastructure/tool_selection/` |
| 시스템 프롬프트 생성 + 버전 저장 | ✅ 구현, 조건부 등록 | `POST /api/v1/prompt-composer/compose` |
| **4단계 통합 파이프라인 + SSE** | ✅ 구현 (Match 97%) | `POST /api/v1/agents/pipeline`, `/stream` |
| 진행 표시 공통 컴포넌트 | ✅ 구현, **미배선** | `idt_front/src/components/common/ProgressCard.tsx` |
| HITL 질문 카드 | ✅ 구현, 배선됨 | `idt_front/src/components/common/question-card/` |

**미완 지점 (이번 사이클이 메운다)**:

1. `agent_create_pipeline`·`prompt_composer` 슬라이스가 **git 미커밋** (`7c3ffdd` 기준 untracked)
2. `AGENT_PIPELINE_ENABLED` 기본 `False` + `.env`에 키 없음 → **파이프라인 라우트가 현재 404**
3. 파이프라인은 의도 되묻기 1곳에서만 멈추고 tools→prompt→create→bind를 **논스톱** 실행 → 도구·프롬프트 개입 지점 없음
4. `ProgressCard`가 어떤 화면에도 연결돼 있지 않음 (progress-card 사이클 명시 이월: "백엔드 이벤트 스키마 → ProgressStep 매핑 어댑터부터 설계")
5. 프론트에 intent / tool-selection / prompt-composer / pipeline 타입·서비스·훅·엔드포인트 상수가 **전무**

agent-create-pipeline 완료 보고서 §8.2가 본 사이클을 **"프론트 배선 — 단계 진행 바 + 되묻기 폼, Priority High"** 로 이미 지정해 두었다.

### 1.3 Related Documents

| 구분 | 문서 |
|------|------|
| 선행 사이클 (백엔드) | `docs/archive/2026-08/agent-create-pipeline/` (Design §4 API 계약, §5 화면 계약, §6 실패 매트릭스) |
| 선행 사이클 (백엔드) | `docs/archive/2026-08/prompt-composer/`, `intent-analyzer/`, `intent-slot-elicitation/`, `tool-recommender/` |
| 선행 사이클 (프론트) | `docs/archive/2026-08/agent-create-entry/` (현행 화면 계약 FR-01~12, 핸드오프 G1~G5) |
| 선행 사이클 (프론트) | `idt_front/docs/archive/2026-08/progress-card/`, `question-card/` |
| 위키 (필독) | `docs/wiki/backend/patterns/sync-sse-dual-exposure.md` — 고정 5 steps + 공유 제너레이터 |
| 위키 (필독) | `docs/wiki/backend/patterns/stateless-hitl-clarification.md` — 에코백 + 서버 재clamp 2요소 |
| 위키 (필독) | `docs/wiki/frontend/patterns/common-card-components.md` — ProgressCard·question-card 재사용 강제 |
| 위키 (필독) | `docs/wiki/frontend/patterns/cross-route-draft-handoff.md` — G1~G5 핸드오프 계약 |
| 위키 | `docs/wiki/backend/patterns/detachable-module-seam.md` — tool_selection AST 경계 |
| 위키 | `docs/wiki/conventions/additive-contract-extension.md` — 계약 확장은 additive |
| 위키 | `docs/wiki/conventions/false-green-quality-gates.md` — 회귀는 FAILED 목록 diff로 증명 |
| 위키 | `docs/wiki/ops/migration-deploy-deps.md` — V061/V062 선행 의존 |

---

## 2. Scope

### 2.1 In Scope

**백엔드 (`idt/`)**

- [ ] 미커밋 슬라이스 3종 커밋 (`agent_create_pipeline`, `prompt_composer`, `intent-slot-elicitation` 변경분)
- [ ] `.env` 플래그 활성화 (`AGENT_PIPELINE_ENABLED`, `PROMPT_COMPOSER_ENABLED`) + V061/V062 마이그레이션 적용
- [ ] 파이프라인에 **정지 지점 2곳 추가** — 요청 `stop_after`, 응답 `status: tools_proposed | prompt_ready` (additive)
- [ ] 사람이 편집한 시스템 프롬프트를 **새 버전으로 저장** (`prompt_version.source` 컬럼 + V063 마이그레이션 + 엔드포인트)
- [ ] SSE 스트림이 정지 지점에서도 `pipeline_result` 1회 송출 후 정상 종료
- [ ] tool_selection AST 경계 테스트 `_DECLARED_CONSUMERS` 갱신 (신규 소비자 발생 시)

**프론트엔드 (`idt_front/`)**

- [ ] `/agent-builder/new` 4스텝 위저드로 전면 교체 (구 `compose` 호출 제거)
- [ ] 공통 `ProgressCard` 배선 — **5단계 고정 표시** + 백엔드 `steps[]`/SSE 이벤트 → `ProgressStep[]` 매핑 어댑터
- [ ] 의도 단계: 공통 `question-card/QuestionCardFlow` 재사용 + 스테일 카드 가드
- [ ] 도구 단계: 추천 도구 토글 + 기존 `ToolPickerModal` 재사용한 카탈로그 추가
- [ ] 프롬프트 단계: 편집 가능 textarea (4000자 카운터) + `[다시 생성]` + `[스튜디오로 보내기]`
- [ ] SSE(fetch-stream POST) 소비 훅 + 끊김 처리
- [ ] 핸드오프 확장 — 스튜디오 프리필에 `session_id`/`version_id` 동반
- [ ] **스튜디오 저장 성공 직후 프롬프트 세션 바인딩** (`PATCH /api/v1/prompt-composer/sessions/{id}`)
- [ ] 파이프라인 플래그 off / 404 시 폴백 안내 화면
- [ ] 타입·서비스·훅·엔드포인트 상수 신설 (API 계약 동기화 규칙 §4-1)

### 2.2 Out of Scope

| 제외 항목 | 사유 |
|-----------|------|
| **R1 수렴** — 구 `POST /api/v1/agents/compose`(Fix 탭)와 `POST /api/v3/agents/auto`(세션형)를 파이프라인으로 통폐합 | 신규 경로 실사용 검증이 선행. 별도 사이클 (파이프라인 report §8.2 Medium) |
| Fix 탭(`FixAgentPanel`) 흐름 변경 | 진입 화면만 교체. Fix 탭 compose는 그대로 유지 |
| 위저드 진행 상태의 영속화(새로고침 복원) | 사용자 결정 — 무상태 유지, `persist` 금지 계약(G1)과 정합 |
| 에이전트 이름·모델·온도·공개범위를 위저드에서 확정 | 사용자 결정 — 서버 제안값 핸드오프 후 스튜디오에서 수정 |
| 도구별 "왜 추천됐는지" 사유 표시 | `SelectionResult`에 도구별 reason 필드 부재. 백엔드 LLM 스키마 확장 비용 대비 후순위 |
| 중복 생성 방어용 멱등 키 | 위저드가 `create`를 호출하지 않으므로 이번 구조에선 위험 자체가 소멸 |
| `/agent-builder/new` 이외 진입점(스튜디오 3버튼, 스토어 포크 등) | 회귀 대상일 뿐 변경 없음 |

---

## 3. Requirements

### 3.1 Functional Requirements — 백엔드

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-B01 | 파이프라인 요청에 `stop_after: "tools" \| "prompt" \| null` 추가. **기본 `null` = 기존 논스톱 동작 완전 동일** (additive) | High | Pending |
| FR-B02 | 응답 `status`에 `tools_proposed`, `prompt_ready` 추가. 기존 `need_input` / `created` / `failed` 의미 불변 | High | Pending |
| FR-B03 | `tools_proposed` 응답: `intent{label, filled_slots, missing_slots, degraded}`, `recommended_tool_ids`, `unknown_tool_ids`, `steps[]`(5개 고정 — prompt 이후 `skipped` + reason) | High | Pending |
| FR-B04 | `prompt_ready` 응답: 위 + `session_id`, `version_id`, `assembled_prompt`, `suggested_name`(기존 `PipelinePolicy.resolve_agent_name` 재사용), `steps[]`(create/bind가 `skipped`) | High | Pending |
| FR-B05 | 3회 왕복 전부 **무상태** — 클라이언트가 `answers`+`round`+`questions`(의도), 확정 `tool_ids`(도구), `session_id`(프롬프트)를 에코백. 서버는 `round`를 `SlotLimits`(IntentConfig 단일 출처)로 재clamp | High | Pending |
| FR-B06 | 사용자가 편집한 프롬프트를 **새 버전으로 저장**. `prompt_version`에 출처 구분 컬럼 추가(V063) + 사람 버전 append 경로. DDL은 테이블·전 컬럼 COMMENT 필수 (CLAUDE.md §3) | High | Pending |
| FR-B07 | `/pipeline/stream`이 `stop_after` 지원 — 정지 시에도 `pipeline_result` 1회 송출 후 스트림 정상 종료. 동기/SSE 최종 payload 동일성(FR-15) 계약 유지 | High | Pending |
| FR-B08 | 도구 단계에서 사용자가 추가한 `tool_ids`는 `required_ids`로 전달해 셀렉터가 절대 떨어뜨리지 않음 (`ToolSelectorPort` 기존 계약) | High | Pending |
| FR-B09 | **기존 논스톱 파이프라인 경로 회귀 0** — `stop_after` 미지정 요청의 응답이 바이트 단위로 기존과 동일 | High | Pending |
| FR-B10 | 미커밋 슬라이스 커밋 + `.env` 플래그(`AGENT_PIPELINE_ENABLED=true`, `PROMPT_COMPOSER_ENABLED`) + V061/V062/V063 적용 + 실서버 스모크 | High | Pending |
| FR-B11 | `tests/infrastructure/tool_selection/test_module_boundaries.py`의 `_DECLARED_CONSUMERS`를 신규 소비자 발생 시 의식적으로 갱신 | Medium | Pending |
| FR-B12 | 라우터 등록 순서 유지 — `/api/v1/agents/pipeline`이 `agent_builder_router`의 `/agents/{agent_id}` 와일드카드보다 **먼저** include (기존 계약, 회귀 방지) | High | Pending |
| FR-B13 | 전 단계 인증 필수(401 고정) · `visibility` 미노출 · 로그에 요청 원문/프롬프트 본문 미기록 (기존 보안 계약 승계) | High | Pending |

### 3.2 Functional Requirements — 프론트엔드

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-F01 | `/agent-builder/new`를 4스텝 위저드로 교체 — ① 설명 입력 ② 의도 수집 ③ 도구 확인 ④ 프롬프트 검토 | High | Pending |
| FR-F02 | 공통 `ProgressCard`로 **5단계 고정 렌더** (의도 파악 / 도구 추천 / 프롬프트 생성 / 에이전트 생성 / 프롬프트 연결). 위저드 구간에서 하위 2개는 `pending` | High | Pending |
| FR-F03 | 백엔드 `steps[]`(`ok`/`degraded`/`failed`/`skipped`) 및 SSE 이벤트 → `ProgressStep[]`(`completed`/`in_progress`/`pending`/`error`) **매핑 어댑터를 단일 함수로** 구현. `degraded`는 완료 + `badgeLabel`로 사유 표기 | High | Pending |
| FR-F04 | 의도 단계는 공통 `question-card/QuestionCardFlow` 재사용 (신규 질문 UI 구현 금지). 사용처 쪽 **스테일 카드 가드** 필수 — 새 응답 도착 시 이전 라운드 카드 해제 (F10 재발 방지) | High | Pending |
| FR-F05 | 되묻기 클라이언트 상한을 서버 `SlotLimits.max_rounds`(현재 2)와 정합시키고, 소진 시 "이대로 진행" 경로 제공 | Medium | Pending |
| FR-F06 | 도구 단계: 추천 도구를 카드로 표시하고 개별 해제 가능 + `[도구 더 추가]`로 기존 `ToolPickerModal` 열어 전체 카탈로그에서 선택. 확정 목록을 다음 호출의 `tool_ids`로 전달 | High | Pending |
| FR-F07 | `unknown_tool_ids`(카탈로그에 없거나 비활성) 에코백을 화면에 안내 (조용히 사라지지 않게) | Medium | Pending |
| FR-F08 | 프롬프트 단계: `assembled_prompt`를 편집 가능한 textarea로 표시 + **4000자 카운터/초과 경고**(서버 `clamp_prompt` 상한). `[다시 생성]`(프롬프트 단계 재실행) / `[스튜디오로 보내기]` | High | Pending |
| FR-F09 | SSE 소비 — `POST /pipeline/stream`을 fetch-stream으로 읽어 `stage_started`/`stage_completed`/`stage_failed`/`pipeline_result` 처리. heartbeat 주석 라인 무시. 기존 `utils/streamParser.ts` 재사용 | High | Pending |
| FR-F10 | SSE 끊김·에러 시 진행바를 `error`로 전환하고 **해당 단계 재시도** 버튼 제공 (위저드는 `create`를 호출하지 않으므로 중복 생성 위험 없음) | High | Pending |
| FR-F11 | 핸드오프 확장 — `agentDraftStore`의 `AgentCreateIntent`에 위저드 결과 종류 추가: `system_prompt`(편집본), `tool_ids`(확정), `suggested_name`, `llm_model_id`, `session_id`, `version_id`. **`persist` 금지·원자적 consume·`getState()`만** (G1~G5 준수) | High | Pending |
| FR-F12 | 스튜디오 프리필 변환은 기존 `composeDraftToForm`을 **확장 또는 병행 함수로 단일화** — 변환 로직 중복 구현 금지 | High | Pending |
| FR-F13 | **스튜디오 `[저장]` 성공 직후** `PATCH /api/v1/prompt-composer/sessions/{session_id}` 로 `agent_id` 바인딩. 바인딩 실패는 **저장을 뒤집지 않음** (경고 로그/토스트만) | High | Pending |
| FR-F14 | 진입 화면의 구 `POST /api/v1/agents/compose` 호출 경로 제거. Fix 탭·기타 3개 진입 버튼은 불변 | High | Pending |
| FR-F15 | 파이프라인 비활성(404) 시 위저드 대신 안내 화면 + `[에이전트 직접 만들기]` 노출 (빈 화면·크래시 금지) | High | Pending |
| FR-F16 | 위저드 진행 중 이탈 시 confirm 경고. 상태는 어디에도 영속하지 않음 | Medium | Pending |
| FR-F17 | 타입(`src/types/agentPipeline.ts`) · 서비스(`src/services/agentPipelineService.ts`) · 훅(`src/hooks/useAgentPipeline.ts`) · 엔드포인트 상수(`src/constants/api.ts`) 신설. 컴포넌트 파일에 런타임 상수 export 금지 (TSX 함정 규칙) | High | Pending |
| FR-F18 | 각 단계 뮤테이션 버튼은 공통 `LoadingButton`(`isPending` 필수 prop) 사용 — 이중 제출 차단 | Medium | Pending |

### 3.3 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| **아키텍처** | 백엔드 Thin DDD 유지 — 단계 전이 규칙은 domain Policy 순수 함수, UseCase에 방어 try/except 추가 금지 | AST 소스 계약 테스트 + 코드 리뷰 |
| **계약 안정성** | 기존 파이프라인 소비자·기존 5경로 무변경 | `stop_after` 미지정 응답 동일성 테스트 + 전체 스위트 `FAILED` 목록 diff |
| **응답성** | 단계별 대기 중 UI 블로킹 없음. LLM 순차 3회 총 대기를 진행바로 가시화, 15초 heartbeat로 프록시 절단 방지 | 수동 E2E + SSE 이벤트 순서 테스트 |
| **접근성** | 진행바 `<ol>` 시맨틱 유지, 각 단계 상태 텍스트 병기(색상 단독 금지), 질문 카드 라벨 | RTL role/name 쿼리 단언 |
| **보안** | 전 요청 헤더 인증. `session_id` 타인 소유 시 404(존재 비노출). 로그에 프롬프트 본문 미기록 | 401/404 고정 단언 테스트 |
| **일관성** | violet-600 계열 · `rounded-2xl` · 기존 Tailwind 토큰 준수, 진행 표시 시각 언어는 `ProgressCard` 단일 소스 | 코드 리뷰 |
| **테스트** | 백엔드 TDD 4계층(domain/application/infra/API), 프론트 Red→Green + MSW 시나리오 | pytest / Vitest |

---

## 4. Success Criteria

### 4.1 Definition of Done

| # | Criteria | 검증 방법 |
|---|----------|-----------|
| SC-1 | 설명 1문장 → 의도 질문 답변 → 도구 확정 → 프롬프트 확인 → 스튜디오 저장까지 **완주** | MSW 통합 테스트 1본 + 실서버 수동 E2E 1회 |
| SC-2 | 저장된 에이전트를 `GET /api/v1/agents/{id}`로 조회했을 때 `system_prompt`(편집본)·`tool_ids`가 위저드 확정값과 **일치** | 실서버 E2E (파이프라인 이월 #15와 함께 소화) |
| SC-3 | 사용자가 도구를 추가/해제한 결과가 최종 저장에 그대로 반영 (`required_ids` 보존) | API 테스트 + 통합 테스트 |
| SC-4 | 편집한 프롬프트가 `prompt_version`에 사람 출처 새 버전으로 적재되고, 저장 후 `prompt_session.agent_id`가 바인딩됨 | DB 단언 테스트 + 실서버 확인 |
| SC-5 | `stop_after` 미지정 요청의 응답이 기존과 동일 — **기존 논스톱 파이프라인 회귀 0** | 기존 101케이스 전량 통과 + 응답 동일성 테스트 |
| SC-6 | 진행바가 항상 5단계로 고정 렌더되고, `degraded`/`failed`/`skipped`가 각각 구분 표기됨 | 컴포넌트 테스트 (상태 4종 × 매핑) |
| SC-7 | 파이프라인 플래그 off 시 안내 화면이 뜨고 `[직접 만들기]`가 동작 (크래시·빈 화면 없음) | MSW 404 시나리오 테스트 |
| SC-8 | 신규 코드 TDD 준수 — 테스트 선작성 → red 확인 → 구현 → green | 커밋 순서 / 세션 로그 |
| SC-9 | 기존 경로 회귀 0 — `AgentBuilderPage`·`FixAgentPanel`·스튜디오 3버튼·`agent_builder_router`·`agent_composer_router` | **정렬된 `FAILED` 목록 diff** (개수 비교 금지) |

### 4.2 Quality Criteria

> ⚠️ **거짓 초록 방지** (`conventions/false-green-quality-gates.md`): 전역 기준은 단일 사이클로 달성 불가하므로 **이 사이클이 변경한 파일 기준**으로 서술한다.

| # | Criteria |
|---|----------|
| QC-1 | **이 사이클 변경 파일**의 lint 에러 0건 (리포지토리 전역 기존 에러는 baseline으로 분리 기록) |
| QC-2 | **이 사이클 변경 파일**의 타입 에러 0건. 검증은 `tsc --noEmit`이 아니라 **`tsc -b`** 로 (project reference 미검사 함정) |
| QC-3 | 백엔드 전체 스위트에서 **baseline 58건 외 신규 `FAILED` 0건** |
| QC-4 | MSW 핸들러가 훅의 `select`와 어긋나지 않음 — 응답 형태를 실제 백엔드 스키마와 대조 |
| QC-5 | DDL COMMENT 검사 통과 (`tests/db/test_migration_ddl_comments.py`) — V063 테이블·전 컬럼 COMMENT, COMMENT 안에 **콤마 금지**(파서 오탐) |

---

## 5. Risks and Mitigation

| # | Risk | Impact | Likelihood | Mitigation |
|---|------|--------|------------|------------|
| R-01 | **파이프라인이 2개 모드(논스톱/단계정지)를 갖게 되어 계약·테스트 복잡도 상승** | High | High | `stop_after`를 순수 additive로(기본 `null`=기존 동작). 단계 전이 규칙은 domain Policy 순수 함수로 유지해 LLM 목 없이 검증. 기존 논스톱 응답 동일성 테스트를 회귀 잠금장치로 |
| R-02 | **미커밋 코드 커밋 + V061/V062/V063 마이그레이션**이라는 배포 선행조건 — 미적용 시 런타임 실패 | High | Medium | `docs/wiki/ops/migration-deploy-deps.md`에 V063 의존 추가. FR-B10을 다른 작업보다 **먼저** 수행하고 실서버 스모크로 확인 |
| R-03 | **prompt_session이 스튜디오 저장까지 살아남아야 바인딩 성립** — 핸드오프 후 새로고침하면 `session_id` 유실 → 프롬프트 버전이 고아가 됨 | Medium | Medium | 바인딩 실패를 **저장 실패로 취급하지 않음**(FR-F13). 고아 세션은 허용하고 경고만. `persist` 금지 계약과의 충돌을 Design에서 명시적으로 판정 |
| R-04 | **프롬프트 4000자 상한** — `assembled`가 넘으면 서버가 조용히 자름 | Medium | Medium | 편집 UI에 실시간 카운터 + 초과 경고(FR-F08). 서버 clamp 발생 시 `steps.create.reason`으로 표면화된 값을 화면에 노출 |
| R-05 | **LLM 3회 순차 호출로 총 대기 증가** (intent 10s + selector 5s + prompt 20s 타임아웃) | Medium | High | SSE 실시간 진행바로 체감 완화 + 15초 heartbeat. 각 단계가 사용자 개입으로 끊기므로 실제 연속 대기는 단계당 1회 |
| R-06 | **tool_selection AST 경계 테스트**가 신규 소비자에서 실패 | Low | Medium | `_DECLARED_CONSUMERS` 갱신을 FR-B11로 명시 (의도된 프로세스이지 우회 대상 아님) |
| R-07 | **위저드 이탈 시 LLM 비용·시간 손실** | Low | Medium | 사용자 결정으로 수용. 이탈 confirm 경고만 제공(FR-F16) |
| R-08 | **진입 화면 전면 교체로 기존 테스트 대량 폐기·재작성** (`AgentCreateEntryPage/index.test.tsx`, `__tests__/integration/agentCreateEntry.test.tsx`) | Medium | High | 교체 대상 테스트를 사전에 목록화하고, "삭제된 테스트"와 "회귀로 깨진 테스트"를 diff에서 구분 기록 |
| R-09 | **에이전트 생성 대화 경로 3종 공존** (`/agents/compose`, `/v3/agents/auto`, `/agents/pipeline`) — 유지보수 부담·사용자 혼선 | Medium | High | 이번 사이클은 진입 화면만 파이프라인으로. R1 수렴은 별도 사이클로 **명시 이월**(`conventions/explicit-gap-carryover.md`) |
| R-10 | **question-card 3번째 사용처 도달** — rule of three에 따라 어댑터 추출 시점 | Low | High | 위저드가 3번째 사용처가 되므로 Design에서 `ClarifyQuestionFlow` 어댑터 추출 여부를 먼저 판정 (question-card report §6.3) |
| R-11 | **`degraded` 상태의 시각 표현이 ProgressCard에 없음** (`ProgressStepStatus`는 4종: completed/in_progress/pending/error) | Low | High | 신규 상태값 추가 대신 `completed` + `badgeLabel`로 표현 — 공통 컴포넌트 계약 변경 최소화. Design에서 확정 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `POST /api/v1/agents/pipeline` (+`/stream`) | API 계약 | 요청에 `stop_after` 추가, 응답 `status`에 2값 추가 — **additive** |
| `src/interfaces/schemas/agent_pipeline.py` | Schema | 요청/응답 필드 추가 |
| `src/domain/agent_create_pipeline/{stages,policies}.py` | Domain | 정지 판정 규칙 추가 (`decide_after_tools`, `decide_after_prompt` 계열) |
| `src/application/agent_create_pipeline/use_case.py` | Application | async generator가 `stop_after` 도달 시 조기 종료 |
| `prompt_version` 테이블 | DB Model + Migration | 출처 구분 컬럼 추가 (V063) — 테이블·전 컬럼 COMMENT 필수 |
| `POST /api/v1/prompt-composer/sessions/{id}/versions` (신설 예상) | API | 사람 편집 프롬프트 버전 append |
| `.env` / `src/config.py` | Config | `AGENT_PIPELINE_ENABLED`, `PROMPT_COMPOSER_ENABLED` 활성화 |
| `idt_front/src/pages/AgentCreateEntryPage/` | Page | 전면 교체 |
| `idt_front/src/store/agentDraftStore.ts` | Store | `AgentCreateIntent` 종류 추가 (additive) |
| `idt_front/src/utils/composeDraftToForm.ts` | Util | 위저드 결과 변환 확장 (또는 병행 함수) |
| `idt_front/src/pages/AgentBuilderPage/index.tsx` | Page | 프리필 소비 분기 추가 + 저장 후 세션 바인딩 |
| `idt_front/src/constants/api.ts` | Const | 파이프라인·프롬프트컴포저 엔드포인트 추가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `/api/v1/agents/pipeline` | 실행 | (프론트 소비자 없음 — 현재 미배선) | **None** — 첫 소비자가 이번 사이클 |
| 파이프라인 UseCase | 논스톱 실행 | `tests/api/test_agent_pipeline_router.py` (101케이스) | **Needs verification** — `stop_after` 기본값이 기존 동작을 보존해야 전량 통과 |
| `prompt_version` | CREATE | `ComposePromptUseCase` (LLM 버전 append) | **Needs verification** — 신규 컬럼에 기본값 필요 |
| `prompt_version` | READ | `GET /api/v1/prompt-composer/sessions/{id}` | **Needs verification** — 응답 스키마에 신규 필드 노출 여부 판단 |
| `prompt_session` | UPDATE(bind) | 파이프라인 `bind` 단계 (논스톱 경로) | **None** — 위저드는 프론트에서 별도 PATCH |
| `agentDraftStore` | READ/WRITE | `AgentCreateEntryPage`(set), `AgentBuilderPage:111-138`(consume) | **Needs verification** — 새 kind 추가 시 소비 분기 누락되면 조용히 실패 |
| `composeDraftToForm` | 변환 | `AgentBuilderPage` 핸드오프 소비 + Fix 탭 `handleApplyDraft:409-412` | **Needs verification** — Fix 탭 경로가 깨지면 안 됨 |
| `POST /api/v1/agents/compose` | 실행 | `AgentCreateEntryPage`(제거 대상), `FixAgentPanel`(유지) | **Breaking(의도)** — 진입 화면 소비만 제거, Fix 탭 불변 |
| `question-card/QuestionCardFlow` | 렌더 | `FixAgentPanel`, `AgentCreateEntryPage` | **Needs verification** — 3번째 사용처 추가, 기존 2곳 무변경 |
| `ProgressCard` | 렌더 | (사용처 없음) | **None** — 첫 사용처 |
| `ToolPickerModal` | 렌더 | `AgentBuilderPage` 스튜디오 도구함 | **Needs verification** — 위저드에서 재사용 시 props 결합도 확인 |
| `POST /api/v1/agents` | CREATE | `AgentBuilderPage.handleSave` | **None** — 저장 경로 무변경 (바인딩 호출만 후속 추가) |
| 라우터 등록 순서 | — | `main.py` DI 블록 → `agent_builder_router` | **Needs verification** — `/agents/pipeline` 선등록 유지 필수 |
| `tool_selection` 모듈 경계 | import | `tests/infrastructure/tool_selection/test_module_boundaries.py` | **Needs verification** — 신규 소비자 시 AST 테스트 실패 |

### 6.3 Verification

- [ ] `stop_after` 미지정 시 기존 101케이스 전량 통과 확인
- [ ] `prompt_version` 신규 컬럼이 기존 CREATE/READ 경로를 깨지 않음 (기본값 + 응답 스키마 판단)
- [ ] `agentDraftStore` 새 kind 추가 후 기존 `draft`/`blank` 분기 회귀 없음
- [ ] `composeDraftToForm` 변경이 Fix 탭 `handleApplyDraft`를 깨지 않음
- [ ] 라우터 등록 순서 테스트가 여전히 통과 (`/agents/pipeline` vs `/agents/{agent_id}`)
- [ ] 인증 401 고정 단언 유지 (403 아님 — 실측으로 확정된 값)
- [ ] 스튜디오 3개 기존 진입 버튼 회귀 테스트 통과

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| Starter | 단순 구조 | 정적 사이트 | ☐ |
| Dynamic | 기능 모듈 + BaaS | 웹앱 MVP | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DI | 복잡 아키텍처 | **☑** |

기존 프로젝트 규약(Thin DDD + FastAPI DI 단일 집중)을 그대로 따른다.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 정지 지점 수 | 1곳(의도만) / 2곳 / **3곳** | **3곳 (의도·도구·프롬프트)** | 사용자 결정 — LLM 판단 3개 각각에 개입 지점 확보 |
| 저장 주체 | 파이프라인 자동 / **사용자 [저장]** | **스튜디오 `[저장]`** | 사용자 결정 — 기존 무저장 계약(FR-12) 유지, 중복 생성 위험 소멸 |
| 진행 표시 | 동기+스피너 / **SSE** | **SSE (`/pipeline/stream`)** | 사용자 결정 — LLM 대기 가시화, fetch-stream POST (EventSource 불가) |
| 진행 단계 수 | 3 / 4 / **5** | **5단계 고정** | 사용자 결정 — 백엔드 고정 5 steps 계약과 1:1, 미저장 상태가 시각적으로 드러남 |
| 프롬프트 편집 | 읽기전용 / 편집만 / **편집+새 버전** | **편집 + 새 버전 저장** | 사용자 결정 — LLM안 vs 사람안 이력 보존 |
| 도구 확인 범위 | 토글만 / **토글+카탈로그 추가** | **토글 + 카탈로그 추가** | 사용자 결정 — `required_ids` 포트 계약이 보존을 보장 |
| 상태 영속 | **없음** / sessionStorage / 서버 | **없음** | 사용자 결정 — `persist` 금지 계약(G1) 정합, 유령 초안 리스크 회피 |
| 이름·모델 확정 위치 | 위저드 / **스튜디오** | **스튜디오 (서버 제안값 프리필)** | 사용자 결정 — 위저드 단계 증가 억제 |
| 기존 경로 | 교체+안내 / 교체+폴백 / 전면수렴 | **진입 화면만 교체 + 플래그 off시 안내** | 사용자 결정 — 이중 유지보수 회피, R1 수렴은 별도 |

### 7.3 Design 단계에서 판정할 열린 질문

> Plan은 요구사항을 확정하고, 아래는 **Design 단계(Checkpoint 3)에서 3안 비교로 결정**한다.

| # | 열린 질문 | 후보 |
|---|-----------|------|
| A-1 | 위저드가 파이프라인 `create`/`bind`를 쓰지 않는데, **여전히 파이프라인 단일 엔드포인트를 쓸 것인가** | (a) `stop_after`로 파이프라인 확장 — steps/SSE/의도 스펙 서버 소유 유지 (b) 프론트가 `intent/analyze` + 신규 도구추천 API + `prompt-composer/compose`를 직접 오케스트레이션 — 단, 의도 슬롯 스펙이 클라로 새고 `tool_selection` API 노출이 필요해짐 |
| A-2 | 사람 편집 프롬프트 버전을 **어디서** 저장할 것인가 | (a) 신규 `POST /prompt-composer/sessions/{id}/versions` (b) 스튜디오 저장 시 함께 (c) 파이프라인 재호출에 `edited_prompt` 실어 보내기 |
| A-3 | `prompt_version`의 출처 구분 방식 | (a) `source` ENUM 컬럼(V063) (b) 기존 `schema_version`/JSON 필드 재활용 |
| A-4 | `degraded` 상태의 진행바 표현 | (a) `completed` + `badgeLabel` (b) `ProgressStepStatus`에 신규 값 추가(공통 컴포넌트 계약 변경) |
| A-5 | question-card **3번째 사용처** — `ClarifyQuestionFlow` 어댑터를 지금 추출할 것인가 | rule of three 도달 (question-card report §6.3) |
| A-6 | 위저드 페이지 구조 | (a) 단일 페이지 + 내부 step state (b) 중첩 라우트 `/agent-builder/new/:step` |
| A-7 | `session_id` 유실 시 바인딩 대책 | (a) 고아 세션 허용 (b) 스튜디오 저장 응답 후 재조회로 복구 |

### 7.4 Clean Architecture Approach

```
백엔드 (Thin DDD — 기존 구조 유지)
  domain/agent_create_pipeline/     stages·policies·spec  ← 정지 판정 규칙(순수 함수) 추가
  application/agent_create_pipeline/ use_case (async generator) ← stop_after 조기 종료
  infrastructure/                    adapters·config
  interfaces/schemas/                agent_pipeline.py  ← 요청/응답 additive
  api/routes/                        agent_pipeline_router.py (POST + SSE)

프론트 (기존 폴더 규약)
  pages/AgentCreateEntryPage/        위저드 셸 + 단계 컴포넌트
  components/common/ProgressCard     (재사용 — 신규 구현 금지)
  components/common/question-card/   (재사용 — 신규 구현 금지)
  components/agent-builder/ToolPickerModal (재사용)
  types/agentPipeline.ts             API 계약 타입
  services/agentPipelineService.ts   호출 (컴포넌트 직접 axios 금지)
  hooks/useAgentPipeline.ts          TanStack Query + SSE 훅
  utils/                             steps → ProgressStep 매핑 어댑터
  store/agentDraftStore.ts           핸드오프 (persist 금지)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] 루트 `CLAUDE.md` + `idt/CLAUDE.md` + `idt_front/CLAUDE.md` 3종
- [x] `idt/docs/rules/` 세부 규칙 (db-session, logging, testing, tool-and-mcp)
- [x] `docs/wiki/` 개발 위키 (설계 결정의 "왜")
- [x] ESLint / TypeScript 설정 존재
- [x] pytest / Vitest + MSW 테스트 관례

### 8.2 Conventions to Verify

| Category | Current State | To Verify | Priority |
|----------|---------------|-----------|:--------:|
| **API 계약 동기화** | 규칙 존재 (루트 CLAUDE.md §4-1) | 백엔드 스키마 변경 시 `idt_front/src/types` + `services` + `constants/api.ts` 동시 수정 | High |
| **DDL COMMENT** | 규칙 존재 + 검사 테스트 | V063에 테이블·전 컬럼 COMMENT, COMMENT 내 **콤마 금지** | High |
| **TSX 작성 함정** | 위키 approved | 컴포넌트 파일 런타임 상수 export 금지 → `types/`·`constants/`로 분리 | High |
| **공통 컴포넌트 재사용** | 위키 approved | 진행 표시·질문 UI 신규 구현 금지 | High |
| **뮤테이션 버튼** | 위키 approved | `LoadingButton` + `isPending` 필수 | Medium |
| **핸드오프 G1~G5** | 위키 draft | persist 금지·원자적 consume·의존 쿼리 settled 후 소비 | High |
| **환경변수** | 일부 누락 | `.env`에 파이프라인 플래그 신규 추가 필요 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `AGENT_PIPELINE_ENABLED` | 파이프라인 라우트 등록 킬스위치 (기본 `False` → `true`) | Server | ☑ |
| `PROMPT_COMPOSER_ENABLED` | 프롬프트 컴포저 라우트 (기본 `True`, 명시 필요) | Server | ☑ |
| `AGENT_PIPELINE_SELECTOR_TOP_K` | 도구 후보 상한 (기본 8) | Server | ☐ (기본값 사용) |
| `AGENT_PIPELINE_SELECTOR_TIMEOUT_SEC` | 셀렉터 타임아웃 (기본 5.0) | Server | ☐ (기본값 사용) |
| `TOOL_SELECTOR_PROVIDER` / `TOOL_SELECTOR_MODEL` | 셀렉터 LLM | Server | ☐ (기존 `.env` 확인) |
| `INTENT_MAX_CLARIFICATION_ROUNDS` | 되묻기 상한 (기본 2) | Server | ☐ (기본값 사용, 프론트 정합) |

### 8.4 Migration Prerequisites

| Migration | 대상 | 상태 |
|-----------|------|------|
| V061 | `prompt_session` | 파일 존재, **적용 여부 확인 필요** |
| V062 | `prompt_version` | 파일 존재, **적용 여부 확인 필요** |
| **V063** | `prompt_version` 출처 컬럼 (A-3 결정 후) | **신규 작성 필요** |

`docs/wiki/ops/migration-deploy-deps.md`에 V063 의존을 추가한다 (위키 갱신은 `/wiki update` 명시 호출 시에만).

---

## 9. Next Steps

1. [ ] **FR-B10 선행 실행** — 미커밋 슬라이스 커밋 + 플래그 활성화 + V061/V062 적용 → `POST /api/v1/agents/pipeline` 200 확인 (이게 안 되면 이후 전부 검증 불가)
2. [ ] Design 문서 작성 (`/pdca design agent-create-wizard`) — §7.3 열린 질문 A-1~A-7을 3안 비교로 판정
3. [ ] Design에 **Plan FR → Design 절 매핑 표** 포함 (G-04 요구 유실 재발 방지 — 파이프라인 사이클 교훈)
4. [ ] Do 단계 세션 분할 예상: ① 백엔드 활성화+`stop_after` ② 백엔드 프롬프트 버전 ③ 프론트 위저드 셸+진행바 ④ 프론트 단계 UI+핸드오프
5. [ ] 실서버 E2E 시 파이프라인 이월 #15(`GET /agents/{id}` 일치 확인)를 함께 소화

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-20 | 최초 작성 — 사용자 결정 9건(정지 3곳·스튜디오 저장·SSE·5단계·프롬프트 편집+버전·도구 카탈로그 추가·무영속·서버 제안 이름·진입화면 완전교체) 반영 | 배상규 |
