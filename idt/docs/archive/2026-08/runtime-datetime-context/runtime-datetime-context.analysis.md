# Runtime Datetime Context — Gap Analysis Report

> **Feature**: runtime-datetime-context
> **Analysis Date**: 2026-08-25
> **Analyst**: gap-detector (bkit) + 수동 교차 검증 (배상규)
> **Plan**: `docs/01-plan/features/runtime-datetime-context.plan.md`
> **Design**: `docs/02-design/features/runtime-datetime-context.design.md`
> **Match Rate**: 초기 **96.0%** → Act-1 후 **98.0%** (static-only — 서버 미기동) · Critical 0 · 잔여 Important 1(수동 E2E, 서버 필요) · 잔여 Minor 2(의도된 이월)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 런타임 LLM이 현재 날짜를 알 방법이 전혀 없어 "오늘/최신" 질의에서 날짜 없는 검색·과거 정보 오답이 발생 |
| **WHO** | P2 에이전트 소유자/KB 운영자(에이전트 품질), 최종 사용자(P1) 전원 — 날짜 상대 표현을 쓰는 모든 질의 |
| **RISK** | ① 수퍼바이저에만 넣고 워커에 안 닿아 검색 쿼리는 여전히 날짜 없음(무효 구현) ② 빌드타임 composer에 잘못 주입 → 결정론 계약 위반 + DB 버전에 날짜 고착 ③ 서버 로컬시간 의존 → UTC 컨테이너에서 날짜 어긋남 |
| **SUCCESS** | 날짜 블록이 6개 실행 경로 전부의 시스템 프롬프트에 존재(테스트로 고정), 빌드타임 산출물에는 부재(AST/문자열 테스트), `agent_timezone` 변경 시 렌더 날짜가 따라감, 기존 테스트 회귀 0(FAILED 목록 diff) |
| **SCOPE** | 1단계: 공용 헬퍼 + config 키 + 커스텀 에이전트 / 2단계: general_chat·rag_agent·excel_analysis / 3단계: SchedulePolicy 타임존 단일화 (선택) |

---

## Strategic Alignment Check

### Plan 문제 정의(WHY) 대응

| 질문 | 판정 | 근거 |
|------|:----:|------|
| 검색어를 실제로 작성하는 지점에 날짜가 닿는가 (RISK ①) | ✅ | `search_pipeline.py:313` `context_block = datetime_block + user_context_block` → `_rewrite_query`(:322)·`_validate_result`(:326)·`_compress_result`(:334). `test_datetime_block_prepended_to_all_llm_stages` |
| 빌드타임 산출물이 오염되지 않는가 (RISK ②) | ✅ | `test_assembled_prompt_has_no_datetime_marker` + AST import 가드 통과, 실제 위반 0 (가드 범위는 Gap 1) |
| 서버 로컬시간 의존이 없는가 (RISK ③) | ✅ | `clock.to_local`(UTC aware/naive → ZoneInfo), `test_utc_2330_renders_next_day_in_kst` (같은 시각에서 KST=08-25, UTC=08-24 동시 단언) |
| 일반화 우선(특정 도구가 아닌 플랫폼 능력) | ✅ | 헬퍼 1개·config 키 1개로 6개 경로 보급. 합성 노드(문서 추출/생성·발표자료·엑셀 내보내기)는 D5 범위 밖 — Gap 7로 명시 |

### Success Criteria Status (Plan §4.1 DoD)

| # | 항목 | 상태 | 근거 |
|---|------|:----:|------|
| 1 | FR-01~FR-11 구현 + FR별 테스트 (TDD) | ✅ Met | 11/11 전용 테스트 존재 (FR-10 가드는 범위 협소 — Gap 1) |
| 2 | 6개 경로 "시스템 프롬프트에 `[현재 날짜]`" 테스트 | ✅ Met | 수퍼바이저·일반 워커·서브에이전트·general_chat·RAG·excel 각 1건 이상 |
| 3 | 빌드타임 미포함 테스트 (FR-10) | ⚠️ Partial | 통과하나 planner 패키지 미포함·비재귀 glob (Gap 1) |
| 4 | `agent_timezone` 변경 시 렌더 날짜 추종 (FR-02) | ✅ Met | `test_prompt_rendering.py` tz 비교 + `test_agent_timezone_env_override` + AST 배선 테스트 |
| 5 | `.env.example` `AGENT_TIMEZONE` | ✅ Met | `.env.example:43-44` |
| 6 | 회귀 0 — FAILED 목록 diff | ✅ Met | baseline 58 failed/8005 passed → 58 failed/8046 passed, FAILED 목록 동일(NO DIFF) |
| 7 | `/verify-architecture`·`/verify-logging`·`/verify-tdd` 통과 | ⚠️ 미실행 | 정적 대체 검증은 통과: application→`src.config` import 0건, 폴백 `exception=` kwarg, 헬퍼 33줄/if 1단계. 스킬 자체는 미호출 |
| 8 | 수동 E2E 1회 ("천안 오늘 날씨" → tavily 쿼리에 날짜) | ❌ Not Met | 미실행. 이월 대상 문서 `docs/wiki/ops/e2e-carryover-checklist.md`는 **루트 위키에 존재**(gap-detector의 "부재" 판정은 `idt/` 내부만 검색한 오탐). 항목 추가는 위키 규칙상 `/wiki update` 명시 호출 시에만 가능 |

### Decision Record Verification

| 결정 | 준수 | 근거 |
|------|:----:|------|
| [Plan] 런타임 prepend, 빌드타임 금지 | ✅ | FR-10 테스트 2건, composer 패키지 import 0 |
| [Plan] config 고정 `Asia/Seoul`, 날짜+요일, 사실+짧은 지침 | ✅ | `config.py:86`, 블록 §4.2 문자 단위 일치(≈169자), 금지어 테스트 |
| [Design] Option C — 순수 함수 + kwarg 주입 | ✅ (Minor) | 4개 생성자 `agent_timezone: str \| None = None`; D3의 "keyword-only(`*`)"는 미적용 — 모든 호출부가 키워드 형식이라 실질 영향 없음 (Gap 5) |
| [Design] 순서 날짜→사용자→wiki/메모리→본문 | ✅ | `workflow_compiler.py:247-250`, `:402`, `general_chat:290-291`, `rag:77`, `excel:218`, `wc:1419` |
| [Design] 웹검색은 search 파이프라인 경로(FR-05 a/b 분할) | ✅ | `wc:371` → `search_pipeline` 3단계 |
| [Design] tzdata 명시 | ✅ | `pyproject.toml:64` |
| [Design] D13 스케줄 위임만, 기본 tz 단일화 후속 | ✅ (의도된 Partial) | `policies.py:13,18,21-23` 위임; `DEFAULT_TIMEZONE` 리터럴 유지 |

---

## 1. Analysis Overview

### 1.1 Purpose
Design(D1~D13, §4.1 인터페이스, §4.2 블록 형식, §8.2 FR 역추적)과 구현·테스트의 일치도를 3축(구조·기능·계약)으로 측정하고, Plan DoD 충족 여부를 증거와 함께 판정한다.

### 1.2 Scope
- 구현: `config.py`, `.env.example`, `pyproject.toml`, `domain/agent_run/clock.py`, `application/agent_run/prompt_rendering.py`, `agent_builder/{workflow_compiler,search_pipeline}.py`, `general_chat/use_case.py`, `rag_agent/use_case.py`, `workflows/excel_analysis_workflow.py`, `api/main.py`, `domain/agent_schedule/policies.py`
- 테스트: 11개 파일 (+41 테스트)
- 런타임(L1~L3): 서버 미기동 → static-only 공식 적용

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints
외부 API 변경 없음 — 해당 없음.

### 2.2 Data Model
DB 변경 없음 — 해당 없음. domain 헬퍼 `clock.py`(`to_local`, `weekday_ko`, `WEEKDAY_KO`) Design §3.1과 일치.

### 2.3 Component Structure (Structural — 98%)

| Design §11.1 항목 | 존재 | 비고 |
|------|:----:|------|
| `src/domain/agent_run/clock.py` (신규) | ✅ | |
| `render_datetime_block` in `prompt_rendering.py` | ✅ | 시그니처 §4.1 일치 |
| `WorkflowCompiler(agent_timezone)` | ✅ | |
| `create_search_pipeline_node(datetime_block="")` | ✅ | |
| `GeneralChatUseCase` / `RAGAgentUseCase` / `ExcelAnalysisWorkflow` kwarg | ✅ | |
| `Settings.agent_timezone`, `.env.example`, `tzdata` | ✅ | |
| `tests/domain/agent_run/test_clock.py`, `tests/api/test_datetime_wiring.py` (신규) | ✅ | |
| `tests/application/workflows/…excel…` (수정 예정) | ⚠️ | 실제 위치 `tests/application/test_analyze_user_context.py:298-347` (Gap 9) |
| `tests/unit/test_config_agent_timezone.py` | ⚠️ | 신규 파일이나 §11.1 신규 목록에 없음 (Gap 9) |

### 2.4 Functional Depth Analysis (Functional — 95%)

직접 확인(테스트 이름이 아니라 코드·단언 본문 기준):

| 결정 | 구현 확인 |
|------|-----------|
| D1 블록 형식 §4.2 | `prompt_rendering.py:60-65` 헤더·날짜줄·지침 3줄·`\n---\n\n` 문자 단위 일치, ≈169자 ≤ 200, 금지어 없음. `tz=None → ""`(:52-53), 잘못된 tz → `""` + `logger.warning(..., exception=e)`(:56-59) |
| D2 clock | naive→UTC 간주, aware 변환, 예외 전파 |
| D3 kwarg 주입 | 4개 생성자 기본값 None; `main.py` 5개 호출(981, 998, 1196, 2389, 2696) 전부 `settings.agent_timezone`; 그 외 인스턴스화 지점 없음 |
| D4 search 3단계 | `context_block` → rewrite/validate/compress 전부 |
| D5 워커 | 일반 워커 `worker_kwargs` 조건부(:408-410) — 빈 블록이면 `system_prompt` 미전달; wiki 워커 날짜+목차+지시(:402) |
| D6 수퍼바이저 계열 | `effective_supervisor_prompt`(:247-250) → supervisor·final_answer 공유; `_analyze_context`(:1419) |
| D7 서브에이전트 | 렌더(:234)가 `include_user_context` 게이트(:228-230)보다 앞·독립; 재귀 `self.compile`(:653) |
| D8/D9/D10 chat 경로 | 순서 준수; excel은 state 키 미추가(노드 내 렌더 후 `user_block=` 합성) |
| D11 설정·의존 | `config.py:80-86` 소비 지점 주석, `pyproject:64` |
| D12 빌드타임 가드 | 통과하나 **planner 3개 패키지 미포함 + 비재귀 glob** (Gap 1) |
| D13 스케줄 위임 | 위임 완료, 기본 tz 리터럴 유지(의도) |

### 2.5 Page UI Checklist
해당 없음 (백엔드 전용).

### 2.6 Contract Verification (Contract — 96%)

| 계약 | 판정 |
|------|:----:|
| §4.1 시그니처·기본값 | ✅ (keyword-only `*` 미적용 — Gap 5) |
| application → `src.config` import 0건 | ✅ |
| `prompt_composer`/`agent_composer` → `prompt_rendering`/`clock` import 0건 | ✅ |
| main.py 배선 AST 테스트 | ✅ (bare-name 호출·`settings` 식별자 하드코딩 — Gap 10) |

### 2.7 Runtime Verification Results
서버 미기동 → L1/L2/L3 미실행. 대신 단위/통합 테스트 8046 passed, FAILED 목록 baseline 동일. 수동 E2E 계획은 §8 참조.

### 2.8 Match Rate Summary

| 축 | 가중치 | 점수 | 기여 |
|----|:-----:|:----:|:----:|
| Structural | 0.2 | 98 | 19.6 |
| Functional | 0.4 | 95 | 38.0 |
| Contract | 0.4 | 96 | 38.4 |
| **Overall (static)** | | | **96.0%** ✅ (≥ 90) |

---

## 3. Gap List

| # | 심각도 | 확신 | 위치 | 문제 → 조치 |
|---|:-----:|:---:|------|-------------|
| 1 | **Important** | 95% | `tests/application/prompt_composer/test_use_case.py:443-456` | 독스트링은 "composer/**planner**"를 말하지만 `packages`에 `src/{domain,application,infrastructure}/planner` 없음, `glob("*.py")` 비재귀. 실제 위반 0 — 가드 범위 문제. **조치**: planner 3개 추가 + `rglob` |
| 2 | **Important** | 100% | Design §8.2 | FR 역추적 표의 약 9행이 실제와 다른 테스트 이름 인용(FR-01/05a/06/07/08/09/10/11/NFR배선). **조치**: 실제 식별자로 동기화 |
| 3 | **Important** | 80% | Plan §4.1 #8 | 수동 E2E 미실행. (gap-detector의 "체크리스트 파일 부재"는 오탐 — `docs/wiki/ops/e2e-carryover-checklist.md` 루트 위키에 존재.) **조치**: 실서버에서 R2 수행 또는 `/wiki update`로 이월 항목 추가 |
| 4 | Minor | 95% | `test_prompt_rendering.py:226-232` | "스냅샷" 테스트가 `startswith/endswith`+부분 문자열만 단언 — 지침 3번째 줄은 미단언. **조치**: 전체 문자열 동등 단언 |
| 5 | Minor | 100% | 4개 생성자 | D3 "keyword-only" 미적용(`*` 없음). 호출부 전부 키워드 형식 + AST 테스트로 고정. **조치**: `*,` 추가 또는 D3 완화 |
| 6 | Minor | 90% | `workflow_compiler.py:518-526` | final_answer 경로는 간접 커버(effective prompt 공유). **조치**: 직접 단언 테스트 1건 |
| 7 | Minor | 85% | `workflow_compiler.py:294-346` | 합성 노드(document_extractor/generator, presentation, excel_export)에는 날짜 블록 없음 — D5 범위 밖. **조치**: Out of Scope 명시 또는 후속 |
| 8 | Minor | 100% | `policies.py:35`, `schemas.py:51`, `models.py:30` | `"Asia/Seoul"` 리터럴 3곳 잔존 — FR-12 의도된 이월 |
| 9 | Minor | 100% | Design §11.1/§8.1 | 테스트 파일 위치 드리프트 2건 |
| 10 | Minor | 85% | `tests/api/test_datetime_wiring.py:29-40` | bare-name 호출만 매칭, `settings` 식별자 하드코딩 — 변수명 변경 시 조용히 통과 |

**Critical: 0건.**

---

## 4. Test Coverage

| 영역 | 테스트 | 상태 |
|------|--------|:----:|
| clock | `test_clock.py` 6 | ✅ |
| render_datetime_block | `TestRenderDatetimeBlock` 9 | ✅ (Gap 4) |
| config | `test_config_agent_timezone.py` 2 | ✅ |
| search pipeline | `TestDatetimeBlockInjection` 3 | ✅ |
| compiler | `TestDatetimeContext` 8 | ✅ (Gap 6) |
| general_chat / RAG / excel | 3 / 2 / 2 | ✅ |
| 빌드타임 음성 | 2 | ⚠️ (Gap 1) |
| 배선 | `test_datetime_wiring.py` 4 | ✅ (Gap 10) |
| 미커버 | final_answer 직접 단언, 합성 노드(범위 밖), 수동 E2E | — |

---

## 5. Clean Architecture Compliance

| 규칙 | 판정 | 근거 |
|------|:----:|------|
| domain → stdlib만 (`clock.py`) | ✅ | `datetime`, `zoneinfo`만 import |
| application → config 미참조 | ✅ | grep 0건 |
| 빌드타임 패키지 → 런타임 헬퍼 미참조 | ✅ | AST 테스트 |
| 레이어 배치 Design §9.3 | ✅ | 전 파일 일치 |

---

## 6. Convention Compliance

| 항목 | 판정 |
|------|:----:|
| 함수 ≤ 40줄, if ≤ 2단계 | ✅ (`render_datetime_block` 33줄/1단계) |
| config 하드코딩 금지 | ⚠️ FR-12 이월분 3곳 (Gap 8) |
| print() 금지·스택 트레이스 | ✅ `exception=e` |
| 로그 규칙 (`structured-logger-warning-exception`) | ✅ |
| ruff — 추가 라인 기준 | ✅ 0건 |

---

## 7. Overall Score

| 항목 | 점수 |
|------|:----:|
| Match Rate (static) | **96.0%** |
| Critical / Important / Minor | 0 / 3 / 7 |
| DoD | 6 Met · 2 Partial(미실행) · 1 Not Met(수동 E2E) |
| 판정 | **90% 게이트 통과** — Important 3건은 검증 계층(가드 범위·문서 동기·E2E)이며 코드 결함 아님 |

---

## 8. Runtime Verification Plan (수동 E2E — 서버 기동 시)

전제: `AGENT_TIMEZONE=Asia/Seoul`, 컨테이너 `TZ`는 UTC 유지(FR-02 위험 재현).

| # | 확인 | 방법 | 통과 기준 |
|---|------|------|-----------|
| R1 | 수퍼바이저가 날짜를 본다 | 임의 커스텀 에이전트 실행, LangSmith `decision_prompt` | 첫 줄 `[현재 날짜]\n- <오늘 KST> (<요일>)` |
| **R2** | **핵심 가치 — 검색어에 날짜** | `tavily_search` 에이전트에 "천안 오늘 날씨 알려줘", `_rewrite_query` 출력·tavily 입력 확인 | 쿼리에 오늘 `YYYY-MM-DD` 포함, tavily에 무가공 전달 |
| R3 | UTC 자정 경계 | 23:30~00:30 UTC 사이 R1 반복 | 컨테이너 날짜가 아닌 **KST** 날짜 |
| R4 | 일반(비검색) 워커 | MCP/action 도구 에이전트 워커 system prompt | 블록 1회 존재 |
| R5 | 시스템 봇/서브에이전트 | `include_user_context=False` + `sub_agent` 워커 | 자식 수퍼바이저·워커 전부 블록 보유, `[현재 사용자 정보]` 부재 |
| R6 | chat 경로 | general/RAG/excel 각 1턴 | 프리픽스 존재, general 순서 날짜→사용자→메모리→규칙 |
| R7 | degraded (FR-11) | `AGENT_TIMEZONE=Mars/Olympus`로 기동 | 정상 응답 + 렌더마다 `datetime block render failed` warning(exception 포함), 블록 부재 |
| R8 | 빌드타임 불변 (FR-10) | composer로 프롬프트 생성·저장 후 익일 재열람 | `assembled` 바이트 동일, 날짜 텍스트 없음 |
| R9 | 슬림 이미지 tzdata | 컨테이너 내 `ZoneInfo('Asia/Seoul')` | `ZoneInfoNotFoundError` 없음 |

R2가 결정적 검증 — 나머지는 단위 테스트로 이미 고정됨.

---

## 9. Act-1 재검증 (2026-08-25, 사용자 결정 "지금 모두 수정")

| Gap | 조치 | 결과 |
|-----|------|:----:|
| 1 | 빌드타임 import 가드에 `planner` 3층 추가 + `rglob` | ✅ 해소 (`test_buildtime_packages_do_not_import_runtime_datetime_helpers` 통과, 실제 위반 0) |
| 2 | Design §8.2 테스트 식별자 13건 실제와 동기화, §11.1 파일 목록 정정 (Gap 9 포함) | ✅ 해소 |
| 3 | 수동 E2E | ⏸ 서버 필요 — §8 R2로 이월. 체크리스트 등재는 `/wiki update` 호출 시 |
| 4 | 스냅샷 테스트 → 전체 문자열 동등 단언 | ✅ 해소 |
| 5 | 4개 생성자 `*,` 추가 → D3 keyword-only 준수 | ✅ 해소 |
| 6 | `test_final_answer_node_receives_datetime_prompt` 추가 | ✅ 해소 |
| 7 | Plan §2.2 Out of Scope에 합성 노드 명시 | ✅ 문서화 |
| 8 | FR-12 이월 리터럴 3곳 | ⏸ 의도된 이월 (후속 사이클) |
| 10 | 배선 테스트: `mod.Cls(...)` 호출 인식 + `settings`가 `src.config` 출처임을 단언 | ✅ 해소 |

**재산정**: Structural 100 (§11.1 정합) · Functional 97 (가드 범위·직접 단언 보강, 잔여 = E2E 미실행) · Contract 98 (keyword-only 준수, 잔여 = FR-12 리터럴) → **Overall 98.0%**. 회귀: FAILED 목록 baseline 동일(NO DIFF), 8047+ passed.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.2 | 2026-08-25 | Act-1 반영 — Gap 1·2·4·5·6·9·10 해소, 7 문서화, 3·8 이월. 98.0% | 배상규 |
| 0.1 | 2026-08-25 | 초기 분석 — 96.0%, Critical 0 / Important 3 / Minor 7. Gap 3 "체크리스트 부재" 오탐 정정(루트 위키에 존재) | 배상규 |
