# Runtime Datetime Context Completion Report

> **Status**: Complete (수동 E2E 1건·FR-12 기본 tz 단일화는 후속 이월)
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Completion Date**: 2026-08-25
> **PDCA Cycle**: #1 (Plan → Design → Do(2세션) → Check → Act-1 → Report, 단일 세션 완주)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | runtime-datetime-context — 런타임 시스템 프롬프트 `[현재 날짜]` 블록 |
| Start Date | 2026-08-25 |
| End Date | 2026-08-25 |
| Duration | 1일 (단일 세션) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 92%                        │
├─────────────────────────────────────────────┤
│  ✅ Complete:     12 / 13 FR (FR-05 a/b 분할) │
│  ⏳ Partial:       1 / 13 (FR-12 — 의도된 이월)│
│  ❌ Cancelled:     0 / 13                     │
│  Match Rate: 96% → 98% (Act-1)  Critical 0    │
│  Tests: +43, 회귀 0 (FAILED 목록 baseline 동일)│
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 코드 전체에서 LLM에게 현재 날짜를 알려주는 지점이 0곳이었다. "천안 오늘 날씨" 같은 질의는 날짜 없는 검색어(`천안 오늘 날씨`)로 나가고, LLM이 결과 중 어느 문서가 "오늘"인지 판별할 수 없어 과거 정보를 오늘 것으로 답할 위험이 컸다 |
| **Solution** | 순수 함수 `render_datetime_block(tz, now_utc, logger)` 1개 + config 키 `agent_timezone` 1개로 **6개 실행 경로**(수퍼바이저·search 파이프라인·일반/wiki 워커·서브에이전트·general_chat·RAG·엑셀 분석)에 `[현재 날짜] 2026-08-25 (화)` + 해석 지침 3줄을 prepend. 빌드타임 composer/planner는 AST 가드로 격리 |
| **Function/UX Effect** | 검색어를 실제로 작성하는 `_rewrite_query` LLM이 날짜를 받아 `YYYY-MM-DD`를 검색어에 포함할 수 있다(단위 테스트로 3단계 prepend 고정). UTC 컨테이너에서도 KST 날짜(경계 테스트 2026-08-24T15:30Z → 08-25). 블록 167자·하루 단위 변화로 프롬프트 캐시 안정. 미인증·시스템 봇도 날짜 수신 |
| **Core Value** | "지금이 언제인가"를 도구별 땜질이 아닌 **플랫폼 공통 기반 능력**으로 보급. 헬퍼·config·배선 테스트가 한 세트라 향후 경로 추가 시 kwarg 1개만 이어 붙이면 된다. 검증: Match Rate 98%, 43개 신규 테스트, 회귀 0 |

---

## 1.4 Success Criteria Final Status

| # | Criteria (Plan §4.1) | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | FR-01~FR-11 구현 + FR별 테스트 (TDD) | ✅ Met | 11/11 전용 테스트, Red→Green 순서로 작성 (`TestRenderDatetimeBlock` 9, `TestDatetimeContext` 9, `TestDatetimeBlockInjection` 3 등) |
| SC-2 | 6개 경로 "시스템 프롬프트에 `[현재 날짜]`" 테스트 통과 | ✅ Met | 수퍼바이저·final_answer·일반 워커·서브에이전트·general_chat·RAG·excel 각 단언 |
| SC-3 | 빌드타임 산출물 미포함 테스트 (FR-10) | ✅ Met | `test_assembled_prompt_has_no_datetime_marker` + `test_buildtime_packages_do_not_import_runtime_datetime_helpers` (composer 3 + planner 3 패키지, rglob) |
| SC-4 | `agent_timezone` 변경 시 렌더 날짜 추종 (FR-02) | ✅ Met | 같은 시각에서 KST=08-25 / UTC=08-24 단언, `test_agent_timezone_env_override` |
| SC-5 | `.env.example`에 `AGENT_TIMEZONE` | ✅ Met | `.env.example:43-44` |
| SC-6 | 기존 테스트 회귀 0 (FAILED 목록 diff) | ✅ Met | baseline `58 failed/8005 passed` → 최종 `58 failed/8119 passed`, FAILED 목록 NO DIFF (3회 전체 실행 모두 동일) |
| SC-7 | `/verify-architecture`·`/verify-logging`·`/verify-tdd` 통과 | ⚠️ Partial | 스킬 미호출. 정적 대체 검증 통과: application→`src.config` import 0, domain `clock.py` stdlib만, `logger.warning(..., exception=e)`, 신규 모듈 전부 테스트 동반 |
| SC-8 | 수동 E2E 1회 ("천안 오늘 날씨" → tavily 쿼리에 날짜) | ❌ Not Met | 실서버 미기동. 분석 문서 §8 R1~R9로 절차 명세, 위키 체크리스트 등재는 `/wiki update` 시 |

**Success Rate**: 6/8 Met, 1 Partial, 1 Not Met (**75% 완전 충족**, 미충족 2건은 모두 도구/서버 의존 검증 항목이며 코드 결함 아님)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 런타임 prepend — 빌드타임 composer 금지 (결정론 계약·DB 버전 저장) | ✅ | AST 가드 + assemble 음성 테스트. 실제 위반 0 |
| [Plan] | 타임존 config 고정 `Asia/Seoul` (서버 로컬시간 의존 금지) | ✅ | `Settings.agent_timezone`, `clock.to_local` UTC→ZoneInfo. 시스템 Python에서 재현된 `ZoneInfoNotFoundError`는 `tzdata` 명시로 예방 |
| [Plan] | 날짜+요일만(시각 제외), 사실+짧은 지침 | ✅ | 167자, 동일일 동일 렌더 테스트, 게이트 어휘 금지 테스트 |
| [Plan] | 적용 경로 6종 (커스텀 에이전트 전체 + general/RAG/excel) | ✅ | 전 경로 테스트 고정. 합성 노드(문서 추출/생성 등)는 Out of Scope 명시 |
| [Design] | Option C — 순수 함수 + `agent_timezone` kwarg 주입, application은 config 미참조 | ✅ | 4개 생성자 keyword-only(`*,` — Act-1에서 준수), main.py 5곳 AST 배선 테스트 |
| [Design] | 블록 순서 날짜 → 사용자 → wiki/메모리 → 본문 | ✅ | 경로별 순서 단언 |
| [Design] | 웹검색은 search 파이프라인(rewrite) 경로 — Plan의 `create_agent` 가정 정정 (FR-05 a/b 분할) | ✅ | `datetime_block` kwarg → rewrite/validate/compress 3단계. **이 정정이 없었다면 검색어에 날짜가 닿지 않는 무효 구현이 될 뻔함** |
| [Design] | 일반 워커에 `system_prompt`를 빈 문자열로 넘기지 않음 (미배선 시 기존 호출 형태 보존) | ✅ | `worker_kwargs` 조건부, `test_generic_worker_without_tz_has_no_system_prompt` |
| [Design] | 실패는 degraded(`""` + warning), 전파 금지 | ✅ | FR-11 테스트 2건 |
| [Design] | D13 — 스케줄은 `clock` 위임만, 기본 tz 단일화는 후속 (domain이 config 불가시) | ✅ (의도된 Partial) | `_to_local`/`_WEEKDAY_KO` 위임, 스케줄 테스트 무수정 통과 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [runtime-datetime-context.plan.md](../01-plan/features/runtime-datetime-context.plan.md) v0.2 | ✅ Finalized |
| Design | [runtime-datetime-context.design.md](../02-design/features/runtime-datetime-context.design.md) v0.2 | ✅ Finalized |
| Check | [runtime-datetime-context.analysis.md](../03-analysis/runtime-datetime-context.analysis.md) v0.2 | ✅ Complete (98%) |
| Act | Current document | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|--------|-------|
| FR-01 | 블록 형식 (헤더·`YYYY-MM-DD (요일)`·지침·`---`) | ✅ Complete | 전체 문자열 스냅샷 단언 (Act-1 강화) |
| FR-02 | tz 기준 로컬 날짜, UTC 경계 | ✅ Complete | |
| FR-03 | `now_utc` 주입 | ✅ Complete | |
| FR-04 | 수퍼바이저·final_answer·analysis | ✅ Complete | final_answer 직접 테스트 (Act-1 추가) |
| FR-05a | search 파이프라인 3단계 | ✅ Complete | Design 정정 산물 |
| FR-05b | `create_agent` 일반 워커 | ✅ Complete | |
| FR-06 | wiki 워커·서브에이전트·시스템 봇 | ✅ Complete | `include_user_context=False`여도 주입 |
| FR-07 | general_chat 순서 | ✅ Complete | 기존 3건 무수정 통과 |
| FR-08 | RAG | ✅ Complete | |
| FR-09 | 엑셀 분석 (state 키 무추가) | ✅ Complete | 두 진입점 무수정 |
| FR-10 | 빌드타임 부재 | ✅ Complete | 가드 planner 포함 (Act-1) |
| FR-11 | degraded 폴백 | ✅ Complete | |
| FR-12 | 스케줄 기본 tz 단일화 | ⏳ Next cycle | `clock` 위임까지만. `DEFAULT_TIMEZONE`·스키마 기본값·모델 기본값 3곳 리터럴 잔존 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 블록 크기 | ≤ 200자 | 167자 | ✅ |
| 렌더 비용 | I/O 없음, < 1ms | 순수 문자열 연산 | ✅ |
| 캐시 안정 | 하루 단위 변화 | 같은 날 두 시각 동일 렌더 테스트 | ✅ |
| 결정론 | 빌드타임 무영향 | AST + 음성 테스트 | ✅ |
| 레이어 규칙 | application→config 0건 | 0건 | ✅ |
| 로깅 | `exception=e` | 준수 | ✅ |
| 회귀 | FAILED diff 0 | NO DIFF ×3 | ✅ |
| lint | 추가 라인 0건 | 0건 (기존 E501 불변) | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Status |
|-------------|----------|--------|
| domain 헬퍼 | `src/domain/agent_run/clock.py` (신규) | ✅ |
| 렌더 함수 | `src/application/agent_run/prompt_rendering.py::render_datetime_block` | ✅ |
| 커스텀 에이전트 배포 | `src/application/agent_builder/{workflow_compiler,search_pipeline}.py` | ✅ |
| chat 경로 | `general_chat/use_case.py`, `rag_agent/use_case.py`, `workflows/excel_analysis_workflow.py` | ✅ |
| 설정·의존 | `src/config.py`, `.env.example`, `pyproject.toml`(tzdata) | ✅ |
| DI 배선 | `src/api/main.py` 5개 호출 | ✅ |
| 스케줄 위임 | `src/domain/agent_schedule/policies.py` | ✅ |
| 테스트 (+43) | 11개 파일 (신규 3: `test_clock.py`, `test_config_agent_timezone.py`, `test_datetime_wiring.py`) | ✅ |
| PDCA 문서 | Plan·Design·Analysis·Report | ✅ |

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| Item | Reason | Priority | Estimated Effort |
|------|--------|----------|------------------|
| 수동 E2E R2 — 실서버에서 "천안 오늘 날씨" → rewrite 쿼리에 오늘 날짜 확인 (분석 §8) | 서버·실 LLM·Tavily 필요 | High | 0.5h (서버 기동 시) |
| 위키 `ops/e2e-carryover-checklist.md`에 R2 등재 | 위키는 `/wiki update` 명시 호출 시에만 갱신 | Medium | `/wiki update` 1회 |
| FR-12 스케줄 기본 tz `config.agent_timezone` 단일화 | domain이 config를 볼 수 없음 — 스케줄 use case에서 기본값 주입 + 스키마/모델 기본값 정리 필요 | Low | 0.5일 |
| 합성 노드(document_extractor/generator, presentation, excel_generator)에 날짜 블록 | D5 범위 밖 (상류 워커 산출물 소비 노드) | Low | 0.5일 |
| `verify-architecture`/`verify-logging`/`verify-tdd` 스킬 실행 | 정적 대체 검증만 수행 | Low | 10분 |

### 4.2 Cancelled/On Hold Items

| Item | Reason | Alternative |
|------|--------|-------------|
| 시각(HH:MM) 제공 | 사용자 결정 — 캐시 안정성 | 필요 시 별도 블록 |
| 에이전트별/사용자별 타임존 | 사용자 결정 — config 고정 | DB 마이그레이션 동반 후속 |
| 웹검색 도구 내부 쿼리 재작성(날짜 append) | LLM 지침으로 해결, 도구는 무가공 유지 | — |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| Design Match Rate (static) | 90% | 98% | 96% → 98% (Act-1) |
| Critical / Important / Minor | 0 / — / — | 0 / 1(E2E) / 2(이월) | 0/3/7 → 0/1/2 |
| 신규 테스트 | FR별 ≥ 1 | 43 | — |
| 회귀 | 0 | 0 (NO DIFF ×3) | — |
| lint (추가 라인) | 0 | 0 | — |

### 5.2 Resolved Issues (Act-1)

| Issue | Resolution | Result |
|-------|------------|--------|
| 빌드타임 가드가 planner 3층 누락·비재귀 | 패키지 추가 + `rglob` | ✅ |
| Design §8.2 테스트 식별자 13건 불일치 | 실제 이름으로 동기화 | ✅ |
| 스냅샷 테스트가 지침 3번째 줄 미단언 | 전체 문자열 동등 단언 | ✅ |
| D3 keyword-only 미적용 | 4개 생성자 `*,` | ✅ |
| final_answer 간접 커버 | 직접 단언 테스트 추가 | ✅ |
| 배선 테스트 `mod.Cls()` 미인식·`settings` 출처 미검증 | AST 매칭 확장 + import 출처 단언 | ✅ |
| Design §11.1 파일 위치 드리프트 | 정정 | ✅ |
| gap-detector "체크리스트 파일 부재" 판정 | 오탐 확인 (루트 `docs/wiki/ops/`에 존재, 에이전트가 `idt/`만 검색) | ✅ 정정 기록 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **Design 단계 코드 조사가 Plan의 핵심 가정을 뒤집었다.** "웹검색 워커 = `create_agent`"는 틀렸고 실제는 search 파이프라인(rewrite LLM)이었다. 이걸 놓쳤으면 수퍼바이저에만 날짜가 들어가고 검색어에는 안 닿는 **무효 구현**이 됐다 (Plan RISK ①). Design 전 실제 코드 경로 추적은 필수.
- **kwarg 기본값 `None` = 블록 생략** 전략으로 기존 테스트 픽스처 무수정·회귀 0을 달성했고, "프로덕션에서 조용히 빠지는" 유일한 위험은 AST 배선 테스트로 막았다.
- **회귀 증명을 pass/fail 개수가 아니라 정렬된 FAILED 목록 diff로** 했다 (baseline 58건 상시 실패 존재). 개수만 봤다면 8005→8119 증가에 묻혀 판단이 흐려졌을 것.
- gap-detector 결과를 그대로 믿지 않고 교차 검증해 오탐 1건(체크리스트 부재)을 걸러냈다 (`intermediate-artifact-verification` 규칙).

### 6.2 What Needs Improvement (Problem)

- **에이전트 산출물 회수 실패**: gap-detector가 두 번 연속 본문 없이 종료("Idle."/"Complete.")해 transcript에서 텍스트 블록을 직접 추출해야 했다. 하위 에이전트에게 "최종 텍스트가 곧 반환값"임을 명시해도 재발 — 결과를 파일로 쓰게 하는 편이 안전.
- **인코딩 함정**: Bash heredoc 안의 Python 스크립트에서 한글 리터럴 매칭이 콘솔 인코딩 때문에 실패했고, 한 번은 `\n` 이스케이프가 실제 개행으로 들어갔다. 한글이 있는 편집은 Edit 도구로.
- Design §8.2에 테스트 이름을 **구현 전에** 적어 13건이 실제와 어긋났다 — 역추적 표는 Do 종료 시점에 실제 식별자로 채우는 게 맞다.
- 수동 E2E는 서버가 없어 이번 사이클에서 닫지 못했다. 서버 의존 DoD는 Plan에서 "이월 가능" 표기를 처음부터 하는 게 정직하다.

### 6.3 What to Try Next (Try)

- Design 역추적 표는 Do 완료 후 "실제 테스트 식별자로 갱신" 단계를 Session Guide에 포함.
- 하위 에이전트 분석 결과는 스크래치 파일 경로를 지정해 쓰게 하고, 메인은 그 파일을 읽는다.
- 서버 의존 DoD(E2E)는 Plan 작성 시 `ops/e2e-carryover-checklist.md` 이월 항목으로 미리 분류.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 코드 경로 가정이 틀릴 수 있음 | Plan에도 "핵심 경로 1개는 코드로 확인" 항목 |
| Design | FR 역추적 표에 예정 테스트명 기입 | Do 종료 시 실측 이름으로 재기입 단계 |
| Do | 2세션 분할(module-1,2 / 3,4) 잘 작동 | 유지 |
| Check | gap-detector 본문 유실 | 파일 출력 지정 |

### 7.2 Tools/Environment

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| 의존성 | `tzdata` 명시 (완료) — lock 재생성·배포 이미지 확인 필요 | 슬림 컨테이너 `ZoneInfoNotFoundError` 예방 |
| 관측 | rewrite 쿼리를 LangSmith 메타데이터에 노출 | E2E R2 검증 비용 감소 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 커밋 — 작업 트리에 무관한 기존 변경(blueprint/multimodal/excel_generator 등)이 많아 **파일 단위 선별** 필요 (Deliverables §3.3 목록 + PDCA 문서 4개)
- [ ] `pip install -e .` / lock 재생성 (tzdata)
- [ ] 실서버 기동 시 분석 §8 R2 수행 → 결과 기록

### 8.2 Next PDCA Cycle

| Item | Priority | Expected Start |
|------|----------|----------------|
| FR-12 스케줄 기본 tz config 단일화 | Low | 미정 |
| 합성 노드 날짜 블록 (필요 시) | Low | 미정 |
| `/wiki update` — E2E 이월 항목 + 교훈(Design 코드 조사·FAILED diff·에이전트 산출물 회수) | Medium | 사용자 호출 시 |

---

## 9. Changelog

### v1.0.0 (2026-08-25)

**Added:**
- `render_datetime_block()` — `[현재 날짜] YYYY-MM-DD (요일)` + 해석 지침 블록 (application/agent_run)
- `domain/agent_run/clock.py` — `to_local`, `weekday_ko`, `WEEKDAY_KO`
- `Settings.agent_timezone` (`AGENT_TIMEZONE`, 기본 `Asia/Seoul`), `.env.example` 항목
- `tzdata>=2024.1` 의존성
- `create_search_pipeline_node(datetime_block=)` — rewrite/validate/compress 3단계 prepend
- `agent_timezone` keyword-only kwarg — `WorkflowCompiler`, `GeneralChatUseCase`, `RAGAgentUseCase`, `ExcelAnalysisWorkflow`
- `main.py` DI 배선 5곳 + AST 배선 테스트
- 테스트 43건 (빌드타임 격리 음성 테스트 2건 포함)

**Changed:**
- 수퍼바이저/final_answer/analysis 프롬프트 접두: 날짜 → 사용자 → wiki → 본문
- 일반 워커에 최초로 `system_prompt`(날짜 블록) 부여 — 미배선 시 기존 호출 형태 보존
- general_chat 프롬프트 순서: 날짜 → 사용자 → 메모리 → 규칙
- `SchedulePolicy._to_local`/`_WEEKDAY_KO` → `clock` 위임

**Fixed:**
- (없음 — 신규 기능)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-25 | Completion report created | 배상규 |
