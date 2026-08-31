# Runtime Datetime Context Planning Document

> **Summary**: 에이전트 런타임 시스템 프롬프트에 **현재 날짜(+요일) 블록**을 공용 헬퍼로 prepend하여, "오늘/최신/최근" 류 질의에서 LLM이 날짜를 모른 채 검색·해석하는 문제를 해소한다. 수퍼바이저뿐 아니라 **실제 검색 쿼리를 작문하는 워커·서브에이전트**까지 날짜가 닿도록 하고, 일반 채팅·RAG 채팅·엑셀 분석 경로에도 동일 블록을 적용한다. 타임존은 config 단일 키(`Asia/Seoul` 기본)로 고정한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-25
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 코드 전체에서 LLM에게 현재 날짜를 알려주는 지점이 **한 곳도 없다**(스케줄 실행의 `{today}` 치환만 사용자 질의 텍스트에 존재). 사용자가 "천안 오늘 날씨 알려줘"라고 하면 웹검색 워커는 날짜 없이 `천안 오늘 날씨`로 검색하고(`tavily_tool.py`는 LLM 쿼리를 무가공 전달), 결과 중 어느 문서가 "오늘"인지 판별할 수 없어 **이전 날짜 정보를 오늘 것으로 답할 가능성**이 크다. 뉴스·환율·공지·"이번 달 집계" 등 날짜 상대 표현을 쓰는 모든 질의가 같은 결함을 공유한다 |
| **Solution** | `render_user_context_block`과 같은 이음매에 `render_datetime_block()`을 신설해 `[현재 날짜] 2026-08-25 (화)` + 짧은 해석 지침을 런타임 시스템 프롬프트에 prepend. 수퍼바이저(=final_answer·analysis 포함)뿐 아니라 **시스템 프롬프트가 없던 일반 워커**(`create_agent(model, tools=[tool])`)와 depth>0 서브에이전트에도 주입. 일반 채팅·RAG 채팅·엑셀 분석 경로 동일 적용. 타임존은 `config.agent_timezone`(기본 `Asia/Seoul`) 단일 출처, 빌드타임 프롬프트(`PromptAssemblyPolicy.assemble` — 결정론 계약)에는 **절대 넣지 않는다** |
| **Function/UX Effect** | "오늘 날씨/오늘 환율/최근 공지/이번 달 매출" 질의에서 검색어에 실제 날짜가 포함되고(예: `천안 날씨 2026-08-25`), 결과의 날짜를 오늘 기준으로 판별해 답한다. 미인증 사용자·시스템 봇(`include_user_context=False`)도 날짜는 받는다 |
| **Core Value** | 에이전트가 "지금이 언제인지"를 아는 것은 특정 도구가 아닌 **플랫폼 공통 기반 능력**(USER-SCENARIOS 일반화 우선 원칙). 한 헬퍼·한 config 키로 모든 실행 경로에 보급하여 향후 도구(캘린더·스케줄·뉴스)가 각자 날짜를 끼워 넣는 중복을 사전에 차단한다 |

---

## Context Anchor

> Auto-generated from Executive Summary. Propagated to Design/Do documents for context continuity.

| Key | Value |
|-----|-------|
| **WHY** | 런타임 LLM이 현재 날짜를 알 방법이 전혀 없어 "오늘/최신" 질의에서 날짜 없는 검색·과거 정보 오답이 발생 |
| **WHO** | P2 에이전트 소유자/KB 운영자(에이전트 품질), 최종 사용자(P1) 전원 — 날짜 상대 표현을 쓰는 모든 질의 |
| **RISK** | ① 수퍼바이저에만 넣고 워커에 안 닿아 검색 쿼리는 여전히 날짜 없음(무효 구현) ② 빌드타임 composer에 잘못 주입 → 결정론 계약(FR-08) 위반 + DB 버전에 날짜 고착 ③ 서버 로컬시간 의존 → UTC 컨테이너에서 날짜 어긋남 |
| **SUCCESS** | 날짜 블록이 6개 실행 경로 전부의 시스템 프롬프트에 존재(테스트로 고정), 빌드타임 산출물에는 부재(AST/문자열 테스트), `agent_timezone` 변경 시 렌더 날짜가 따라감, 기존 테스트 회귀 0(FAILED 목록 diff) |
| **SCOPE** | 1단계: 공용 헬퍼 + config 키 + 커스텀 에이전트(수퍼바이저·워커·서브에이전트) / 2단계: general_chat·rag_agent·excel_analysis 적용 / 3단계: SchedulePolicy 타임존 단일화 (선택) |

---

## 1. Overview

### 1.1 Purpose

에이전트 런타임에서 LLM이 호출되는 모든 시스템 프롬프트에 **현재 날짜와 요일**을 표준 형식으로 제공하고, "오늘/최근/최신" 표현의 해석·검색어 구성에 대한 짧은 지침을 함께 준다. 목적은 두 가지다.

1. **검색 정확도**: 웹검색 워커가 검색어에 날짜를 포함하고, 결과의 날짜를 오늘 기준으로 판별한다.
2. **해석 일관성**: "이번 달", "지난주", "최근 공지" 같은 상대 표현이 실행 경로(커스텀 에이전트/일반 채팅/RAG/엑셀 분석)마다 다르게 해석되지 않는다.

### 1.2 Background (2026-08-25 코드 추적 결과)

**결함 확정 근거**

| 사실 | 위치 |
|------|------|
| 시스템 프롬프트에 날짜를 넣는 코드 없음 (`datetime.now`/`today`/`ZoneInfo` grep 전수) | `src/` 전체 |
| 유일한 날짜 치환은 스케줄 실행의 `{today}/{now}/{weekday}` — **사용자 질의 텍스트** 대상 | `src/domain/agent_schedule/policies.py:127-142` |
| 웹검색 도구는 LLM 쿼리를 무가공 전달, 날짜/recency 보정 없음 | `src/infrastructure/web_search/tavily_tool.py:84,116` |
| 일반 워커는 **시스템 프롬프트 없이** 생성, 대화 메시지만 전달 | `src/application/agent_builder/workflow_compiler.py:391` |
| 워커 진입 시 `ensure_user_tail`은 마지막이 human이면 no-op → 첫 턴에는 지시 주입 통로 없음 | `src/application/agent_builder/message_normalization.py:22-37` |
| config에 timezone 키 없음, `SchedulePolicy.DEFAULT_TIMEZONE="Asia/Seoul"`만 도메인에 산재 | `src/config.py`, `policies.py:31` |
| 빌드타임 프롬프트 조립은 "시간·UUID·랜덤 미사용" 명시 계약 + DB 버전 저장 | `src/domain/prompt_composer/policies.py:5,100` |

**기존 prepend 패턴 (재사용 대상)**

`render_user_context_block(auth_ctx)` (`src/application/agent_run/prompt_rendering.py:19`)이 이미 런타임 컨텍스트를 시스템 프롬프트 앞에 붙이는 공용 헬퍼로 존재하며, 아래 경로에서 소비된다:

| 경로 | 조립 지점 | 현재 prepend |
|------|-----------|-------------|
| 커스텀 에이전트 수퍼바이저·final_answer | `workflow_compiler.py:235` `effective_supervisor_prompt = user_context_block + wiki_toc_block + workflow.supervisor_prompt` | user + wiki toc |
| 커스텀 에이전트 analysis 노드 | `workflow_compiler.py:1394` | user |
| 일반 워커 (웹검색 등) | `workflow_compiler.py:391` | **없음 (system_prompt 미지정)** |
| wiki 워커 | `workflow_compiler.py:387` | wiki toc |
| 서브에이전트 (depth>0) | `workflow_compiler.py:594` `_compile_sub_agent` → `compile()` 재귀 | user(부모 플래그 승계) |
| 일반 채팅 | `general_chat/use_case.py:278` `user_block + memory_block + _SYSTEM_PROMPT` | user + memory |
| RAG 채팅 | `rag_agent/use_case.py:69` 정적 `_SYSTEM_PROMPT` | **없음** |
| 엑셀 분석 | `excel_analysis_workflow.py:200,311` `_build_analysis_prompt(user_block=...)` | user |

### 1.3 Related Documents

- 유저 시나리오: `docs/USER-SCENARIOS.md` (일반화 우선 원칙)
- 위키: `docs/wiki/conventions/config-single-source-at-consumption.md` (config 키 신설 규칙)
- 위키: `docs/wiki/backend/patterns/supervisor-graph-contracts.md` (수퍼바이저 프롬프트 수정 전 필수)
- 위키: `docs/wiki/conventions/false-green-quality-gates.md` (회귀 증명 방식)
- 선행 기능: agent-user-context (사용자 컨텍스트 prepend 패턴 원형), supervisor-overblock-fix (prepend 블록 프레이밍 교훈)
- 관련 기능: prompt-depth / prompt-composer (빌드타임 조립 — **본 기능 적용 금지 영역**)

---

## 2. Scope

### 2.1 In Scope

- [x] **공용 헬퍼** `render_datetime_block(now_utc=None, tz=None) -> str` 신설 (`src/application/agent_run/prompt_rendering.py`)
  - 형식: `[현재 날짜]\n- 2026-08-25 (화)\n` + 짧은 지침 2~3줄 + `\n---\n\n` 구분자 (기존 블록 규약 동일)
  - 지침 내용: "'오늘/최근/최신/이번 주·달' 표현은 위 날짜를 기준으로 해석한다", "웹 검색 시 검색어에 날짜를 포함한다", "검색 결과의 날짜가 위 날짜와 다르면 그 사실을 답변에 명시한다"
  - `now_utc` 주입 가능(테스트 결정성), 미지정 시 UTC 현재 시각
- [x] **config 키** `agent_timezone: str = "Asia/Seoul"` 신설 (`src/config.py`) — docstring에 소비 지점 파일:라인 명기
- [x] **커스텀 에이전트 전 경로 적용**
  - 수퍼바이저·final_answer·analysis: `effective_supervisor_prompt` 조립에 날짜 블록 추가
  - 일반 워커: `create_agent(..., system_prompt=datetime_block)` — 현재 시스템 프롬프트 없는 워커에 최초 부여
  - wiki 워커: 기존 `wiki_toc_block + instruction` 앞에 추가
  - 서브에이전트(depth>0): 재귀 compile에서 동일 적용 (`include_user_context`와 **무관**하게 항상 주입)
- [x] **일반 채팅** `general_chat/use_case.py:278` — `datetime_block + user_block + memory_block + _SYSTEM_PROMPT`
- [x] **RAG 채팅** `rag_agent/use_case.py:69` — system 메시지 content 앞에 추가
- [x] **엑셀 분석** `excel_analysis_workflow.py:311` — `_build_analysis_prompt`에 날짜 블록 전달 (state 명시 주입 우선 패턴 유지)
- [x] **테스트**: 헬퍼 단위 테스트(형식·요일·타임존·주입 시각), 6개 경로별 "시스템 프롬프트에 날짜 블록 포함" 테스트, 빌드타임 산출물 **미포함** 테스트
- [ ] **SchedulePolicy 타임존 단일화** (선택, 3단계): `DEFAULT_TIMEZONE`이 `config.agent_timezone`을 기본값으로 쓰도록 — 스케줄별 timezone 필드는 유지

### 2.2 Out of Scope

- 시각(HH:MM) 제공 — 사용자 결정: 날짜+요일만 (프롬프트 캐시 안정성)
- 에이전트별·사용자별 타임존 — config 고정 (필요 시 후속 사이클, DB 마이그레이션 동반)
- 빌드타임 프롬프트(`prompt_composer`, `agent_composer`, `planner`)에 날짜 주입 — 결정론 계약 위반
- 웹검색 도구 내부에서 쿼리를 자동 재작성(날짜 append) — LLM 지침으로 해결, 도구는 무가공 유지
- 검색 결과의 발행일 파싱·필터링(`days`/`topic=news` 자동 설정)
- 대화 메모리·요약 정책 변경
- 프론트엔드 변경 (API 계약 무변경)
- 합성 노드(document_extractor / document_generator / presentation_generator / excel_generator)의 LLM 호출 — 상류 워커 산출물을 소비하는 노드라 D5 범위 밖. 필요 시 후속 사이클 (Check Gap 7)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `render_datetime_block()`이 `[현재 날짜]` 헤더 + `YYYY-MM-DD (요일)` + 해석 지침 + `---` 구분자를 반환한다. 요일은 한국어 한 글자(월~일) | High | Implemented |
| FR-02 | 날짜는 `config.agent_timezone` 기준 로컬 날짜다. UTC 23:30에 KST는 다음날이어야 한다 (경계 테스트) | High | Implemented |
| FR-03 | `now_utc` 인자로 시각을 주입할 수 있고, 미지정 시 현재 UTC를 사용한다 (테스트 결정성) | High | Implemented |
| FR-04 | 커스텀 에이전트 수퍼바이저·final_answer·analysis 노드의 시스템 프롬프트에 날짜 블록이 포함된다 | High | Implemented |
| FR-05a | search 카테고리 워커(`tavily_search` 등 → `create_search_pipeline_node`)의 rewrite/validate/compress system prompt에 날짜 블록이 포함된다 — 검색어를 실제로 작성하는 지점 (Design 조사로 정정, v0.2) | High | Implemented |
| FR-05b | search 외 일반 워커(`create_agent(model, tools=[tool])`)에 날짜 블록을 시스템 프롬프트로 부여한다 | High | Implemented |
| FR-06 | wiki 워커·서브에이전트(depth>0)에도 날짜 블록이 포함된다. `include_user_context=False`(시스템 봇)여도 날짜는 주입된다 | High | Implemented |
| FR-07 | 일반 채팅(`general_chat`) 시스템 프롬프트에 날짜 블록이 포함된다 (순서: 날짜 → 사용자 → 메모리 → 규칙) | High | Implemented |
| FR-08 | RAG 채팅(`rag_agent`) system 메시지에 날짜 블록이 포함된다 | Medium | Implemented |
| FR-09 | 엑셀 분석 프롬프트에 날짜 블록이 포함된다 (state 명시 주입 우선, ContextVar 폴백 패턴 유지) | Medium | Implemented |
| FR-10 | 빌드타임 `PromptAssemblyPolicy.assemble()` 결과 및 `ComposedPrompt.assembled`에는 날짜 블록이 **포함되지 않는다** | High | Implemented |
| FR-11 | 날짜 블록 렌더링 실패(잘못된 tz 문자열 등)는 빈 문자열 폴백 + warning 로그(`exception=e`)로 degraded 처리 — 에이전트 실행을 중단시키지 않는다 | Medium | Implemented |
| FR-12 | (선택) `SchedulePolicy`의 기본 타임존이 `config.agent_timezone`을 따른다 — 스케줄별 timezone 필드 우선 | Low | Partial (D13 위임만 — 기본 tz 단일화는 후속) |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 블록 렌더링은 순수 문자열 연산(LLM/DB/네트워크 호출 없음), 요청당 추가 지연 < 1ms | 단위 테스트 + 코드 리뷰 (I/O 부재 확인) |
| Token Cost | 블록 크기 ≤ 200자 (약 100 토큰). 워커 수 N개에 각각 부여되므로 크기 상한 강제 | 단위 테스트에서 `len(block) <= 200` 단언 |
| Cache Stability | 블록은 하루 단위로만 변한다(시각 미포함) — 프롬프트 캐시 프리픽스 안정성 | 같은 날짜 두 시각에 렌더 결과 동일 테스트 |
| Determinism | 빌드타임 산출물 무영향 (`assemble()` 시간 미사용 계약 유지) | FR-10 테스트 |
| Layer Rule | 헬퍼는 application 레이어, config 읽기는 소비 지점 1곳에서만 | `/verify-architecture` |
| Logging | 폴백 경로는 `logger.warning(..., exception=e)` | `/verify-logging` |
| Regression | 기존 테스트 FAILED 목록 diff = 0건 (baseline 대비) | `pytest -q` 전후 FAILED 목록 정렬 비교 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-11 구현 및 각 FR에 대응하는 테스트 존재 (TDD: Red → Green)
- [ ] 6개 실행 경로(수퍼바이저·일반 워커·서브에이전트·일반 채팅·RAG·엑셀 분석) 각각 "시스템 프롬프트에 `[현재 날짜]` 포함" 테스트 통과
- [ ] 빌드타임 산출물 미포함 테스트 통과 (FR-10)
- [ ] `config.agent_timezone` 변경 시 렌더 날짜가 따라감을 증명하는 테스트 통과 (FR-02)
- [ ] `.env.example`(존재 시)에 `AGENT_TIMEZONE` 항목 추가
- [ ] 기존 테스트 회귀 0건 — 작업 전/후 `FAILED` 목록 diff로 증명 (baseline 상시 실패분 제외)
- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과
- [ ] 수동 E2E 1회: 웹검색 워커 보유 에이전트에 "천안 오늘 날씨" 질의 → LangSmith/로그에서 tavily 쿼리에 날짜 포함 확인 (`ops/e2e-carryover-checklist.md`에 이월 가능)

### 4.2 Quality Criteria

- [ ] 함수 40줄 이하, if 중첩 2단계 이하
- [ ] config 하드코딩 없음 (`"Asia/Seoul"` 리터럴은 `config.py` 기본값 한 곳에만)
- [ ] print() 없음, 예외 삼킴 시 스택 트레이스 로그
- [ ] Design 문서에 FR 역추적 표 존재 (`intermediate-artifact-verification` 규칙)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 수퍼바이저에만 주입하고 워커에 안 닿음 → 검색어에 날짜 없음(**무효 구현**) | High | Medium | FR-05를 별도 요구사항으로 분리, 일반 워커 `create_agent` 호출에 `system_prompt` 전달 여부를 테스트로 고정. Design에서 워커 프롬프트 부여가 기존 워커 동작(툴 호출 성향)에 미치는 영향 검토 |
| 빌드타임 composer에 잘못 주입 → 결정론 계약 위반, DB 버전에 날짜 고착 | High | Low | FR-10 음성 테스트 + Design에 "적용 금지 영역" 명시. 헬퍼를 `agent_run/` 패키지에 두어 `prompt_composer/`가 import하지 않음을 AST 테스트로 강제 가능 |
| 서버 로컬시간 의존 → UTC 컨테이너에서 자정 전후 날짜 어긋남 | High | High(미대응 시) | `datetime.now(UTC)` + `ZoneInfo(config.agent_timezone)` 변환만 허용. UTC 23:30 → KST 익일 경계 테스트 |
| 워커 N개 × 블록 크기 → 토큰 증가 | Low | High | 블록 ≤ 200자 상한 테스트. 시각 미포함으로 하루 단위 캐시 안정 |
| 지침 문구가 수퍼바이저 라우팅에 부작용(과차단·과검색) | Medium | Low | supervisor-overblock-fix 교훈: 게이트/심사 프레이밍 금지, 사실+해석 지침만. 지침은 "검색 결과의 날짜가 다르면 명시" 수준으로 제한. 워커 라우팅 테스트 회귀 확인 |
| Windows/컨테이너에 tzdata 부재 → `ZoneInfo` 예외 | Medium | Low | FR-11 degraded 폴백(빈 블록 + warning). `tzdata` 패키지 의존 여부를 Design에서 확인(pyproject) |
| 프론트 없이 백엔드만 변경했는데 사용자가 날짜 반영 여부를 알 수 없음 | Low | Medium | 스코프 밖. 필요 시 후속에서 실행 트레이스에 블록 노출 여부 검토 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/config.py` `Settings` | Config | `agent_timezone: str = "Asia/Seoul"` 추가 |
| `src/application/agent_run/prompt_rendering.py` | Module | `render_datetime_block()` 추가 (기존 함수 무변경) |
| `src/application/agent_builder/workflow_compiler.py` | Application | `compile()` 프롬프트 조립 3곳(:235 수퍼바이저, :387 wiki 워커, :391 일반 워커) + `_analyze_context`(:1394)에 날짜 블록 추가 |
| `src/application/general_chat/use_case.py` | Application | `:278` prompt 조립에 날짜 블록 추가 |
| `src/application/rag_agent/use_case.py` | Application | `:69` system 메시지 content에 날짜 블록 prepend |
| `src/application/workflows/excel_analysis_workflow.py` | Application | `:200` / `_build_analysis_prompt` 에 날짜 블록 전달 |
| `src/domain/agent_schedule/policies.py` | Domain (선택) | `DEFAULT_TIMEZONE` → config 기본값 참조로 단일화. **domain은 config를 직접 import하지 않음** — 호출자(application)가 주입하는 방식으로 Design에서 결정 |
| `.env.example` | Config | `AGENT_TIMEZONE=Asia/Seoul` |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `compile()` 수퍼바이저 프롬프트 | READ | `supervisor_nodes.py:229` decision_prompt, `_create_final_answer_node:726` | 프리픽스에 날짜 블록 추가 — 라우팅 지시·워커 목록 무변경 (Needs verification: 라우팅 테스트) |
| `compile()` 일반 워커 | CREATE | `workflow_compiler.py:391` `create_agent(model, tools=[tool])` | **system_prompt 최초 부여** — 워커 도구 호출 성향 변화 여부 확인 필요 (Needs verification) |
| `compile()` wiki 워커 | CREATE | `workflow_compiler.py:387` | 프리픽스 추가, `_WIKI_FOLDER_WORKER_INSTRUCTION` 무변경 (None) |
| `compile()` 재귀 | CREATE | `_compile_sub_agent:594` → `compile(depth+1)` | 자동 승계 (None) |
| `compile()` 호출자 | CALL | `run_agent_use_case.py:571`, `agent_definition_repository.py` | 시그니처 무변경 (None) |
| `render_user_context_block` | READ | 5개 경로 | 무변경 — 새 함수 병렬 추가 (None) |
| `general_chat` 프롬프트 | READ | `test_memory_injection.py` 메모리 순서 테스트 | 순서 단언이 절대 인덱스면 조정 필요 (Needs verification) |
| `SchedulePolicy.DEFAULT_TIMEZONE` | READ | `agent_schedule` use case / schemas 기본값 | 3단계 선택 항목 — 값 동일(`Asia/Seoul`)이라 동작 무변경 (None) |
| 빌드타임 `PromptAssemblyPolicy.assemble` | — | `compose_prompt_use_case.py:114` | **변경 금지** — 음성 테스트로 보호 (None) |
| 프론트엔드 | — | — | API 계약 무변경 (None) |
| DB 스키마 | — | — | 마이그레이션 없음 (None) |

### 6.3 Verification

- [ ] 위 소비자 전부 테스트로 확인 (특히 일반 워커 system_prompt 부여, general_chat 순서 테스트)
- [ ] 인증/권한 동작 무변경 (날짜 블록은 auth_ctx와 독립)
- [ ] 응답 스키마·API 계약 무변경 → `/api-contract-sync` 불필요

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps, SaaS MVPs | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic, complex architectures | ☑ (기존 Thin DDD) |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 주입 시점 | 빌드타임(composer) / **런타임(prepend)** | 런타임 | 빌드 산출물은 DB 버전 저장 + 결정론 계약. 날짜는 요청마다 달라야 함 |
| 헬퍼 위치 | domain / **application `agent_run/prompt_rendering.py`** / infrastructure | application | 기존 `render_user_context_block`과 동일 파일·동일 규약(`---` 구분자). LLM 프롬프트 텍스트는 application 책임 |
| 타임존 출처 | 서버 로컬 / **config 단일 키** / 에이전트별 / 사용자별 | config `agent_timezone` | 사용자 결정. `config-single-source-at-consumption` 규칙: 소비 지점 docstring 명기 |
| 시각 주입 | 내부 `datetime.now()` / **`now_utc` 인자(기본 None)** | 인자 주입 | 테스트 결정성. `SchedulePolicy.render_instruction(…, now_utc)`과 동일 관례 |
| 정보 범위 | 날짜만 / **날짜+요일** / 날짜+요일+시각 | 날짜+요일 | 사용자 결정. 하루 단위 변화로 캐시 안정 |
| 지침 포함 | 사실만 / **사실+짧은 지침** | 사실+지침 | 사용자 결정. 게이트 프레이밍 금지(overblock 교훈) |
| 워커 주입 통로 | `ensure_user_tail` 지시 / **`create_agent(system_prompt=)`** | system_prompt | `ensure_user_tail`은 human-last에 no-op → 첫 턴 미주입. 시스템 프롬프트가 유일하게 확실한 통로 |
| 블록 순서 | 날짜→사용자→(wiki/메모리)→본문 | Design에서 확정 | 날짜는 사용자 인증과 무관하므로 맨 앞이 자연스러움. `include_user_context=False`여도 날짜는 존재 |
| 폴백 | 예외 전파 / **빈 문자열 + warning** | degraded | `degradation-vs-failure-boundary`: 날짜 없이도 쓸 수 있는 결과 존재 → degraded |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD — 기존 구조 유지, 레이어 이동 없음)

application/agent_run/prompt_rendering.py
  ├─ render_user_context_block(ctx)        (기존)
  ├─ render_wiki_toc_block(items, …)       (기존)
  └─ render_datetime_block(now_utc, tz)    (신설) ← config.agent_timezone 소비 지점

소비자 (application 레이어):
  agent_builder/workflow_compiler.py       수퍼바이저·워커·서브에이전트
  general_chat/use_case.py                 일반 채팅
  rag_agent/use_case.py                    RAG 채팅
  workflows/excel_analysis_workflow.py     엑셀 분석

적용 금지:
  domain/prompt_composer/policies.py       (빌드타임, 결정론 계약)
  application/agent_composer/*             (빌드타임)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` 코딩 규칙 (40줄/중첩 2단계/config 하드코딩 금지/logger)
- [x] `docs/rules/logging.md`, `docs/rules/testing.md`, `docs/rules/db-session.md`
- [x] 위키 `config-single-source-at-consumption`, `false-green-quality-gates`, `degradation-vs-failure-boundary`
- [ ] `.env.example` 존재 여부 확인 (Design 단계)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 프롬프트 블록 형식 | `[헤더]` + 본문 + `\n---\n\n` 규약 존재 | 날짜 블록도 동일 규약 준수 | High |
| 요일 표기 | `SchedulePolicy._WEEKDAY_KO` 존재(domain) | 재사용 vs 복제 — Design에서 결정 (domain→application 참조는 허용 방향) | Medium |
| config 키 명명 | snake_case, 섹션 주석 | `# Agent Runtime` 섹션 신설, 소비 지점 명기 | High |
| 시각 주입 관례 | `now_utc: datetime` 인자 (schedule) | 동일 관례 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `AGENT_TIMEZONE` | 날짜 블록 렌더 기준 타임존 (IANA), 기본 `Asia/Seoul` | Server | ☑ |

### 8.4 Pipeline Integration

해당 없음 (단일 기능 PDCA 사이클).

---

## 9. Next Steps

1. [ ] `/pdca design runtime-datetime-context` — 설계안 3종 비교 (워커 주입 통로·블록 순서·요일 헬퍼 재사용·SchedulePolicy 단일화 방식 확정), FR 역추적 표 작성
2. [ ] Design 승인 후 `/pdca do runtime-datetime-context` — TDD (헬퍼 단위 테스트 → 경로별 통합 테스트 → 구현)
3. [ ] `/pdca analyze` — 6개 경로 포함 + 빌드타임 미포함 검증
4. [ ] 수동 E2E: 웹검색 에이전트 "천안 오늘 날씨" → tavily 쿼리 로그 확인

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.2 | 2026-08-25 | Design 조사 반영: 웹검색(`tavily_search`)은 category=search → `create_search_pipeline_node`(rewrite LLM) 경로로 확인, FR-05는 Design에서 5a(search 파이프라인)/5b(create_agent 워커)로 분할. tzdata 전이 의존 확인 → 명시 추가 결정 | 배상규 |
| 0.1 | 2026-08-25 | Initial draft — 코드 추적 기반 결함 확정, 사용자 결정 4건(타임존 config 고정·날짜+요일·사실+지침·적용 경로 6종) 반영 | 배상규 |
