# Runtime Datetime Context Design Document

> **Summary**: 런타임 시스템 프롬프트에 `[현재 날짜] YYYY-MM-DD (요일)` + 해석 지침 블록을 prepend하는 순수 함수 `render_datetime_block(tz, now_utc)`를 신설하고, 4개 소비자(WorkflowCompiler·GeneralChat·RAG·ExcelAnalysis)에 `agent_timezone` kwarg로 주입한다. 검색어를 실제로 작성하는 search 파이프라인(rewrite)과 시스템 프롬프트가 없던 `create_agent` 워커에도 블록을 전달한다. 빌드타임 composer는 적용 금지(음성 테스트로 고정).
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-25
> **Status**: Draft
> **Plan**: `docs/01-plan/features/runtime-datetime-context.plan.md`
> **Selected Architecture**: Option C — Pragmatic Balance

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 런타임 LLM이 현재 날짜를 알 방법이 전혀 없어 "오늘/최신" 질의에서 날짜 없는 검색·과거 정보 오답이 발생 |
| **WHO** | P2 에이전트 소유자/KB 운영자(에이전트 품질), 최종 사용자(P1) 전원 — 날짜 상대 표현을 쓰는 모든 질의 |
| **RISK** | ① 수퍼바이저에만 넣고 워커에 안 닿아 검색 쿼리는 여전히 날짜 없음(무효 구현) ② 빌드타임 composer에 잘못 주입 → 결정론 계약 위반 + DB 버전에 날짜 고착 ③ 서버 로컬시간 의존 → UTC 컨테이너에서 날짜 어긋남 |
| **SUCCESS** | 날짜 블록이 6개 실행 경로 전부의 시스템 프롬프트에 존재(테스트로 고정), 빌드타임 산출물에는 부재(AST/문자열 테스트), `agent_timezone` 변경 시 렌더 날짜가 따라감, 기존 테스트 회귀 0(FAILED 목록 diff) |
| **SCOPE** | 1단계: 공용 헬퍼 + config 키 + 커스텀 에이전트(수퍼바이저·워커·서브에이전트) / 2단계: general_chat·rag_agent·excel_analysis 적용 / 3단계: SchedulePolicy 타임존 단일화 (선택) |

---

## 1. Overview

### 1.1 Design Goals

1. **한 함수, 한 형식**: 날짜 블록은 `render_datetime_block()` 단 한 곳에서 렌더되어 모든 경로가 동일 텍스트를 받는다.
2. **검색어에 닿는다**: 웹검색 워커의 검색어는 `search_pipeline._rewrite_query`의 LLM이 작성한다. 이 호출의 system prompt에 블록이 들어가야 목표가 달성된다 (Plan RISK ①).
3. **빌드타임 무오염**: `PromptAssemblyPolicy.assemble()`·`ComposedPrompt.assembled`에 날짜가 들어가지 않음을 테스트로 고정한다 (Plan RISK ②).
4. **타임존 단일 출처**: `config.agent_timezone` → `main.py` → 소비자 생성자 kwarg. application 레이어는 config를 import하지 않는다(현행 0건 유지).
5. **회귀 0**: 소비자 kwarg 기본값 `None` = 블록 생략. 기존 테스트 픽스처는 무수정으로 통과하고, 프로덕션 배선은 별도 wiring 테스트로 보증한다.

### 1.2 Design Principles

- **prepend 규약 준수**: 기존 `render_user_context_block`과 동일하게 `[헤더]` + 본문 + `\n---\n\n` 구분자.
- **사실 + 해석 지침만**: 게이트/심사 프레이밍 금지 (supervisor-overblock-fix 교훈). "거부/차단" 류 어휘 사용 안 함.
- **순수 함수 + 주입 시각**: `now_utc` 인자로 결정성 확보. `datetime.now()`는 기본값 경로 한 곳.
- **degraded, not failure**: 잘못된 tz 등 렌더 실패는 빈 문자열 + warning(`exception=e`) — 에이전트 실행을 중단시키지 않는다.
- **얇은 DDD**: Protocol·Provider 클래스 신설 없음. 요일/로컬 변환만 domain 공용 헬퍼로 승격.

### 1.3 Plan 대비 정정 사항

| Plan 기술 | 실제 (Design 조사) | 반영 |
|-----------|-------------------|------|
| "웹검색 워커는 `create_agent(model, tools=[tool])`로 생성" | `tavily_search`는 category=`search` → `create_search_pipeline_node` (rewrite→search→validate→compress). `create_agent` 경로는 search 외 action 도구(MCP 등) | FR-05를 **두 통로**로 분할: FR-05a search 파이프라인(rewrite 시스템 프롬프트), FR-05b create_agent 워커(system_prompt 부여) |
| tzdata 위험 "Likelihood Low" | 시스템 Python에서 `ZoneInfoNotFoundError` 재현. venv는 전이 의존으로만 설치 | pyproject에 `tzdata>=2024.1` 명시 (D11) |

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| 관점 | A — 최소 변경 | B — 클린 아키텍처 | **C — 실용 균형 (선택)** |
|---|---|---|---|
| 헬퍼 | 헬퍼 내부에서 `settings.agent_timezone` 직접 참조 | domain `Clock` Protocol + `DatetimeContextProvider` 클래스 | 순수 함수 `render_datetime_block(tz, now_utc=None, logger=None)` |
| 소비자 | 인자 없는 호출 추가 | Provider 생성자 주입 | `agent_timezone: str | None = None` kwarg 주입 |
| 레이어 규칙 | application→config import 선례 신설 | 완전 준수 | 준수 (기존 `search_compress_threshold` 주입 관례 동일) |
| 테스트 | settings monkeypatch | Clock fake | `now_utc`/`tz` 인자 |
| 변경 파일 | ~7 | ~13 + 픽스처 다수 | ~9 |
| 기각/선택 사유 | 전역 설정 결합 | 과도한 추상화(두꺼운 DDD 금지) | 기존 관례·회귀 0·순수 테스트 |

### 2.1 Component Diagram

```
config.py ──agent_timezone──▶ api/main.py (DI)
                                  │ agent_timezone=settings.agent_timezone
        ┌─────────────────────────┼─────────────────────────┬──────────────────────┐
        ▼                         ▼                         ▼                      ▼
 WorkflowCompiler          GeneralChatUseCase          RAGAgentUseCase     ExcelAnalysisWorkflow
 (compile / _analyze_context)  (_create_agent)            (run)              (analysis node)
        │                         │                         │                      │
        └──────────── render_datetime_block(tz, now_utc, logger) ◀─────────────────┘
                     application/agent_run/prompt_rendering.py
                                  │ uses
                     domain/agent_run/clock.py  (to_local, weekday_ko, WEEKDAY_KO)
                                  ▲ (선택) SchedulePolicy._to_local/_WEEKDAY_KO 위임

 WorkflowCompiler.compile() 내부 분배:
   datetime_block ─┬─▶ effective_supervisor_prompt = dt + user + wiki_toc + supervisor_prompt
                   ├─▶ create_search_pipeline_node(datetime_block=dt)  → rewrite/validate/compress system
                   ├─▶ create_agent(system_prompt=dt)                  (search 외 일반 워커)
                   ├─▶ create_agent(system_prompt=dt + wiki_toc + instruction)  (wiki 워커)
                   ├─▶ _compile_sub_agent → compile() 재귀 (self._agent_timezone 승계)
                   └─▶ _analyze_context: dt + user_block + system_prompt
```

### 2.2 Data Flow

```
request ─▶ UseCase/Compiler(self._agent_timezone)
        ─▶ render_datetime_block(tz)            # 요청당 1회 (compile 시점)
             now_utc = datetime.now(UTC)
             local   = to_local(now_utc, tz)     # ZoneInfo
             block   = "[현재 날짜]\n- 2026-08-25 (화)\n\n" + 지침 3줄 + "\n---\n\n"
        ─▶ system prompt prefix (경로별 조립)
        ─▶ LLM 호출 (수퍼바이저 라우팅 / rewrite 쿼리 / 워커 / 최종 답변)
```

- 렌더는 `compile()` 진입 시 1회 계산해 지역 변수로 배포한다(워커 N개에 재계산 없음). 자정 경계에서 한 요청 내 날짜가 갈리는 것을 방지.
- `_analyze_context`는 별도 호출 시점이므로 그 자리에서 다시 렌더한다 (서로 다른 요청 단위).

### 2.3 Dependencies

| 의존 | 종류 | 비고 |
|------|------|------|
| `zoneinfo` (stdlib) + `tzdata` (pypi) | 신규 명시 의존 | Windows·슬림 컨테이너에 OS tz DB 없음 |
| `src.domain.agent_run.clock` | 신규 domain 모듈 | 순수 계산, 외부 I/O 없음 |
| `LoggerInterface` | 기존 domain 인터페이스 | warning 폴백용 |

---

## 3. Data Model

### 3.1 Entity Definition

DB 엔티티 변경 없음. 도메인 헬퍼만 추가:

```python
# src/domain/agent_run/clock.py  (신규)
WEEKDAY_KO = "월화수목금토일"

def to_local(now_utc: datetime, tz: str) -> datetime:
    """UTC(aware 또는 naive=UTC 가정) → tz 로컬 aware datetime. ZoneInfoNotFoundError 전파."""

def weekday_ko(d: date) -> str:
    """date.weekday() → '월'..'일'."""
```

### 3.2 Entity Relationships

해당 없음.

### 3.3 Database Schema

마이그레이션 없음.

---

## 4. API Specification

외부 API 계약 변경 없음 (요청/응답 스키마 무변경, 프론트 무변경).

### 4.1 내부 인터페이스 변경 (application)

| 대상 | 변경 | 기본값 | 호환 |
|------|------|--------|------|
| `render_datetime_block(tz: str | None, now_utc: datetime | None = None, logger: LoggerInterface | None = None) -> str` | 신설 | `now_utc=None → datetime.now(UTC)` | — |
| `WorkflowCompiler.__init__(…, agent_timezone: str | None = None)` | kwarg 추가 | None → 블록 생략 | 기존 호출 무영향 |
| `create_search_pipeline_node(…, datetime_block: str = "")` | kwarg 추가 | "" | 기존 호출 무영향 |
| `GeneralChatUseCase.__init__(…, agent_timezone: str | None = None)` | kwarg 추가 | None | 무영향 |
| `RAGAgentUseCase.__init__(…, agent_timezone: str | None = None)` | kwarg 추가 | None | 무영향 |
| `ExcelAnalysisWorkflow.__init__(…, agent_timezone: str | None = None)` | kwarg 추가 | None | 무영향 |
| `Settings.agent_timezone: str = "Asia/Seoul"` | config 키 | `AGENT_TIMEZONE` env | — |

`tz=None`이면 `render_datetime_block`은 `""`를 반환한다(소비자 분기 불필요).

### 4.2 블록 형식 (고정 스냅샷)

```
[현재 날짜]
- 2026-08-25 (화)

'오늘', '최근', '최신', '이번 주/이번 달' 같은 표현은 위 날짜를 기준으로 해석하세요.
웹 검색이 필요하면 검색어에 위 날짜(연-월-일)를 포함하세요.
검색 결과나 문서의 날짜가 위 날짜와 다르면 그 날짜를 답변에 함께 밝히세요.

---

```

- 길이 상한 200자 (테스트 단언). 시각(HH:MM) 미포함 — 하루 단위 캐시 안정성.
- 게이트 어휘("거부", "차단", "권한") 미사용 — 테스트로 금지어 단언.

---

## 5. UI/UX Design

해당 없음 (백엔드 전용, 프론트 무변경).

---

## 6. Error Handling

### 6.1 Error Cases

| 상황 | 처리 | 근거 |
|------|------|------|
| `tz`가 잘못된 IANA 문자열 (`ZoneInfoNotFoundError`) | `""` 반환 + `logger.warning("datetime block render failed", tz=tz, exception=e)` | FR-11, `degradation-vs-failure-boundary`: 날짜 없이도 쓸 수 있는 결과 존재 → degraded |
| `tz=None` (미배선) | `""` 반환, 로그 없음 (정상 opt-out) | 테스트 픽스처·시스템 봇 |
| `logger=None`인데 렌더 실패 | `""` 반환(무로그) | 순수 함수 계약. 프로덕션 소비자는 항상 logger 전달 |
| `tzdata` 미설치 환경 | 위 첫 행과 동일 경로 + pyproject 명시로 예방 | D11 |

### 6.2 Error Response Format

외부 응답 변경 없음.

---

## 7. Security Considerations

- 블록은 서버 시각에서만 파생 — 사용자 입력·개인정보 미포함. `render_user_context_block`의 whitelist 계약과 독립.
- 프롬프트 인젝션 표면 증가 없음(고정 텍스트).
- 타임존은 서버 설정값이며 사용자 제어 불가.

---

## 8. Test Plan

### 8.1 Test Scope

| 계층 | 파일 | 목적 |
|------|------|------|
| 단위 | `tests/domain/agent_run/test_clock.py` (신규) | `to_local` 경계·naive/aware, `weekday_ko` |
| 단위 | `tests/application/agent_run/test_prompt_rendering.py` (확장) | 블록 형식·경계·주입·상한·금지어·폴백 |
| 통합 | `tests/application/agent_builder/test_workflow_compiler.py` (확장) | 수퍼바이저/워커/wiki/서브에이전트 prepend |
| 통합 | `tests/application/agent_builder/test_search_pipeline.py` (확장) | rewrite/validate/compress system에 블록 |
| 통합 | `tests/application/general_chat/test_memory_injection.py` (확장) | 순서: dt → user → memory → system |
| 통합 | `tests/application/rag_agent/…` (확장 또는 신규) | system 메시지 prefix |
| 통합 | `tests/application/test_analyze_user_context.py` (확장 — 기존 excel 사용자 컨텍스트 테스트 파일) | 분석 프롬프트 prefix |
| 음성 | `tests/application/prompt_composer/test_use_case.py` (확장) | assembled에 `[현재 날짜]` 부재 + AST import 금지 |
| 배선 | `tests/api/test_datetime_wiring.py` (신규, `test_blueprint_wiring.py` 선례) | main.py DI 4곳에 `settings.agent_timezone` 전달 |
| 설정 | `tests/test_config.py` 또는 기존 config 테스트 | 기본값 `Asia/Seoul`, env 오버라이드 |

### 8.2 FR 역추적 표 (`intermediate-artifact-verification` 규칙)

| FR | Design 결정 | 테스트 |
|----|-------------|--------|
| FR-01 형식·요일 | D1 §4.2 스냅샷 | `test_snapshot_2026_08_25_is_tuesday` |
| FR-02 tz 기준 날짜 | D2 `to_local` | `test_utc_2330_renders_next_day_in_kst` (2026-08-24T15:30Z → `2026-08-25 (화)`) |
| FR-03 `now_utc` 주입 | D1 시그니처 | `test_now_utc_default_uses_current_time` (freeze 없이 오늘 문자열 포함 확인) |
| FR-04 수퍼바이저·final·analysis | D6 | `test_supervisor_prompt_starts_with_datetime_block`, `test_final_answer_node_receives_datetime_prompt`, `test_analyze_context_prefix` |
| FR-05a search 파이프라인 | D4 | `test_datetime_block_prepended_to_all_llm_stages` (rewrite/validate/compress), `test_datetime_precedes_user_context`, `test_default_empty_keeps_prompts_identical`; validate/compress 동일 |
| FR-05b create_agent 워커 | D5 | `test_generic_worker_gets_datetime_system_prompt`, `test_generic_worker_without_tz_has_no_system_prompt` |
| FR-06 wiki 워커·서브에이전트·시스템 봇 | D5, D7 | `test_wiki_worker_prefix_order_datetime_then_toc`, `test_sub_agent_with_include_user_context_false_still_has_datetime` |
| FR-07 general_chat 순서 | D8 | `test_datetime_before_user_before_memory_before_system`, `test_datetime_without_auth_ctx_still_present`, `test_no_tz_keeps_prompt_unchanged` + 기존 3건 무수정 통과 |
| FR-08 RAG | D9 | `test_system_message_starts_with_datetime_block`, `test_no_tz_keeps_static_prompt` |
| FR-09 excel | D10 | `test_prompt_starts_with_datetime_then_user_block`, `test_no_tz_keeps_prompt_without_datetime` |
| FR-10 빌드타임 부재 | D12 | `test_assembled_prompt_has_no_datetime_marker`, `test_buildtime_packages_do_not_import_runtime_datetime_helpers` (AST, composer+planner, rglob) |
| FR-11 degraded 폴백 | D1 §6.1 | `test_invalid_tz_returns_empty_and_warns_with_exception`, `test_invalid_tz_without_logger_does_not_raise` (`exception=` kwarg 단언) |
| FR-12 (선택) 스케줄 tz 단일화 | D13 | `SchedulePolicy` 기존 테스트 무수정 통과 (위임 리팩터) |
| NFR 길이 상한 | D1 | `test_block_length_under_200` |
| NFR 캐시 안정 | D1 | `test_same_day_two_times_render_identical` |
| NFR 금지어 | D1 | `test_block_has_no_gate_vocabulary` |
| NFR 배선 | D3 | `test_main_wires_settings_agent_timezone[4 consumers]`, `test_main_imports_settings_from_config` |

### 8.3 L1/L2/L3

- L1(API): 외부 계약 무변경 → 회귀 스모크만 (`tests/api/test_main.py` 기존).
- L2/L3(UI/E2E): 해당 없음. 수동 E2E 1건은 `ops/e2e-carryover-checklist.md`에 이월: 웹검색 에이전트 "천안 오늘 날씨" → LangSmith에서 rewrite 출력 쿼리에 `2026-08-25` 포함 확인.

### 8.4 Seed Data

불필요.

---

## 9. Clean Architecture

### 9.1 Layer Structure

```
domain/agent_run/clock.py            순수 시각 계산 (신규)
application/agent_run/prompt_rendering.py   render_datetime_block (신규 함수)
application/agent_builder/workflow_compiler.py, search_pipeline.py   소비
application/general_chat/use_case.py, rag_agent/use_case.py, workflows/excel_analysis_workflow.py   소비
api/main.py                          settings.agent_timezone 주입
config.py                            agent_timezone 키
```

### 9.2 Dependency Rules

- domain(`clock.py`) → stdlib만. application → domain. api → application + config.
- **application은 `src.config`를 import하지 않는다** (현행 0건 유지). `agent_timezone`은 항상 kwarg로 받는다.
- `prompt_composer/`(빌드타임)는 `agent_run/prompt_rendering`을 import하지 않는다 — AST 테스트로 고정.

### 9.3 This Feature's Layer Assignment

| 파일 | 레이어 | 책임 |
|------|--------|------|
| `src/domain/agent_run/clock.py` | domain | `to_local`, `weekday_ko`, `WEEKDAY_KO` |
| `src/application/agent_run/prompt_rendering.py` | application | `render_datetime_block` |
| `src/application/agent_builder/workflow_compiler.py` | application | 블록 배포(수퍼바이저/워커/서브/analysis) |
| `src/application/agent_builder/search_pipeline.py` | application | `datetime_block` kwarg → 3단계 prepend |
| `src/application/general_chat/use_case.py` | application | prepend 순서 |
| `src/application/rag_agent/use_case.py` | application | system 메시지 prefix |
| `src/application/workflows/excel_analysis_workflow.py` | application | analysis 노드 prefix |
| `src/config.py`, `src/api/main.py` | config / interfaces | 키 + DI |
| `src/domain/agent_schedule/policies.py` | domain (선택) | `_to_local`/`_WEEKDAY_KO` → clock 위임 |

---

## 10. Coding Convention Reference

### 10.1 Naming

- 함수: `render_datetime_block` (기존 `render_user_context_block`, `render_wiki_toc_block` 동형)
- kwarg: `agent_timezone` (config 키와 동일 이름), 지역 변수 `datetime_block`
- 내부 속성: `self._agent_timezone`

### 10.2 Environment Variables

| Variable | Default | 소비 지점 |
|----------|---------|-----------|
| `AGENT_TIMEZONE` | `Asia/Seoul` | `src/api/main.py` → WorkflowCompiler / GeneralChatUseCase / RAGAgentUseCase / ExcelAnalysisWorkflow 생성 인자 |

`config.py` 주석에 위 소비 지점을 명기한다 (`config-single-source-at-consumption` 규칙).

### 10.3 This Feature's Conventions

- 코드 주석: `# Design Ref: runtime-datetime-context §D{n}` 형식으로 결정 번호 인용.
- 함수 40줄 이하 — `compile()`은 이미 길어 **블록 계산은 1줄 추가, 배포는 기존 표현식에 `datetime_block +` 접두만** 붙인다(신규 분기 금지).
- 로그: `logger.warning(..., exception=e)` (`structured-logger-warning-exception`).

---

## 11. Implementation Guide

### 11.0 Design Decisions (D1~D13)

| # | 결정 | 내용 |
|---|------|------|
| D1 | 헬퍼 시그니처 | `render_datetime_block(tz: str | None, now_utc: datetime | None = None, logger: LoggerInterface | None = None) -> str`. `tz=None → ""`. 형식 §4.2. 예외 → `""` + warning |
| D2 | domain clock | `src/domain/agent_run/clock.py`: `to_local(now_utc, tz)`(naive면 UTC 가정), `weekday_ko(date)`, `WEEKDAY_KO` |
| D3 | 주입 | 4개 소비자 `agent_timezone: str | None = None` keyword-only kwarg. `main.py`에서 `settings.agent_timezone` 전달. 배선 테스트로 보증 |
| D4 | search 파이프라인 | `create_search_pipeline_node(…, datetime_block="")`. 내부에서 `prefix = datetime_block + user_context_block`을 `_rewrite_query/_validate_result/_compress_result`의 `user_context` 인자로 전달(3함수 시그니처 무변경). `REWRITE_SYSTEM_PROMPT` 본문은 무수정 — 지침은 블록이 담당 |
| D5 | create_agent 워커 | 일반 워커: `datetime_block`이 비어있지 않을 때만 `system_prompt=datetime_block` 전달(빈 문자열 전달 금지 → 기존 동작 보존). wiki 워커: `system_prompt=datetime_block + wiki_toc_block + instruction` |
| D6 | 수퍼바이저 계열 | `effective_supervisor_prompt = datetime_block + user_context_block + wiki_toc_block + workflow.supervisor_prompt` (final_answer·supervisor_nodes decision_prompt는 이 값을 그대로 씀 → 자동 반영). `_analyze_context`: `f"{datetime_block}{user_block}{system_prompt}\n\n…"` |
| D7 | 서브에이전트 | `compile()` 재귀는 `self._agent_timezone`을 그대로 쓰므로 자동 승계. `include_user_context`와 **무관** — 시스템 봇도 날짜 수신 |
| D8 | general_chat | `prompt = datetime_block + render_user_context_block(auth_ctx) + memory_block + _SYSTEM_PROMPT`. `_create_agent` 내부에서 렌더(기존 테스트 patch 지점 유지) |
| D9 | RAG | `{"role": "system", "content": datetime_block + self._SYSTEM_PROMPT}` |
| D10 | Excel | `ExcelAnalysisWorkflow`가 `agent_timezone` 보유, analysis 노드(`:200` 부근)에서 `datetime_block + user_block`을 `_build_analysis_prompt(user_block=…)`에 전달. **state 키 추가 없음** (두 진입점 `analyze_excel_use_case:99`, `workflow_compiler:1354` 무수정) |
| D11 | 의존성·설정 | `pyproject.toml` dependencies에 `"tzdata>=2024.1"`. `config.py` `# Agent Runtime` 섹션에 `agent_timezone: str = "Asia/Seoul"` + 소비 지점 주석. `.env.example`에 `AGENT_TIMEZONE=Asia/Seoul` |
| D12 | 빌드타임 보호 | `tests/application/prompt_composer/test_use_case.py`에 (a) `assemble()` 결과에 `[현재 날짜]` 부재 (b) `src/domain/prompt_composer`, `src/application/prompt_composer`, `src/application/agent_composer`가 `prompt_rendering`을 import하지 않음(AST) |
| D13 | (선택) 스케줄 위임 | `SchedulePolicy._to_local` → `clock.to_local`(naive 입력 호환), `_WEEKDAY_KO` → `clock.WEEKDAY_KO` 재수출. 기본 tz(`DEFAULT_TIMEZONE`) 단일화는 **후속 사이클** — domain이 config를 볼 수 없고, 스케줄 요청 스키마 기본값(`schemas.py:51`)까지 얽혀 범위 초과 |

### 11.1 File Structure

```
신규
  src/domain/agent_run/clock.py
  tests/domain/agent_run/test_clock.py
  tests/api/test_datetime_wiring.py
  tests/unit/test_config_agent_timezone.py
수정
  src/config.py
  src/application/agent_run/prompt_rendering.py
  src/application/agent_builder/workflow_compiler.py
  src/application/agent_builder/search_pipeline.py
  src/application/general_chat/use_case.py
  src/application/rag_agent/use_case.py
  src/application/workflows/excel_analysis_workflow.py
  src/api/main.py
  src/domain/agent_schedule/policies.py        (선택 D13)
  pyproject.toml, .env.example
  tests/application/agent_run/test_prompt_rendering.py
  tests/application/agent_builder/test_workflow_compiler.py
  tests/application/agent_builder/test_search_pipeline.py
  tests/application/general_chat/test_memory_injection.py
  tests/application/rag_agent/test_use_case.py, tests/application/test_analyze_user_context.py (excel)
  tests/application/prompt_composer/test_use_case.py
```

### 11.2 Implementation Order (TDD: 각 단계 Red → Green)

1. `pyproject.toml` tzdata, `config.py` 키, `.env.example` — config 테스트
2. `domain/agent_run/clock.py` — `test_clock.py`
3. `render_datetime_block` — `test_prompt_rendering.py` (스냅샷·경계·상한·금지어·폴백)
4. `search_pipeline.py` `datetime_block` kwarg — `test_search_pipeline.py`
5. `workflow_compiler.py` (D5/D6/D7) — `test_workflow_compiler.py`
6. `general_chat` (D8) — `test_memory_injection.py`
7. `rag_agent` (D9), `excel_analysis_workflow` (D10) — 각 테스트
8. `prompt_composer` 음성 테스트 (D12)
9. `main.py` 배선 — `test_datetime_wiring.py`
10. (선택) D13 스케줄 위임 — 기존 스케줄 테스트 무수정 통과
11. 전체 `pytest -q` → FAILED 목록 diff = baseline과 동일

### 11.3 Session Guide

**Module Map**

| Scope key | 모듈 | 파일 | FR |
|-----------|------|------|----|
| `module-1` | Core: 설정·clock·헬퍼 | config.py, pyproject, .env.example, clock.py, prompt_rendering.py + 테스트 | FR-01/02/03/11, NFR |
| `module-2` | Custom agent: 컴파일러·search 파이프라인 | workflow_compiler.py, search_pipeline.py + 테스트 | FR-04/05a/05b/06 |
| `module-3` | Chat paths: general/rag/excel | 3개 use_case/workflow + 테스트 | FR-07/08/09 |
| `module-4` | Guard & wiring: 음성 테스트·main.py DI·(선택) 스케줄 위임 | prompt_composer 테스트, main.py, test_datetime_wiring.py, policies.py | FR-10/12, NFR 배선 |

**Recommended Session Plan**

- Session 1: `module-1` + `module-2` (헬퍼가 있어야 컴파일러 테스트가 의미 있음; 핵심 가치 경로 우선)
- Session 2: `module-3` + `module-4` (독립 경로 + 보호 테스트 + 배선 마무리, 전체 회귀 diff)

```
/pdca do runtime-datetime-context --scope module-1,module-2
/pdca do runtime-datetime-context --scope module-3,module-4
```

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.2 | 2026-08-25 | Check gap 반영: §8.2 테스트 식별자 실제와 동기화(Gap 2), §11.1 파일 위치 정정(Gap 9), D12 가드 planner 포함·rglob, D3 keyword-only(`*`) 적용, final_answer 직접 테스트 추가 | 배상규 |
| 0.1 | 2026-08-25 | Initial — Option C 선택, 블록 순서(날짜→사용자→wiki/메모리→본문), tzdata 명시. Plan 정정: 웹검색 워커는 search 파이프라인 경로(FR-05 a/b 분할) | 배상규 |
