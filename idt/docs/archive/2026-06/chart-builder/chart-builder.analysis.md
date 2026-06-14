# Chart Builder 설계-구현 Gap 분석 보고서

> **Feature**: chart-builder (General Chat 연동)
> **분석일**: 2026-06-06
> **Match Rate**: 98% → (Gap-1 설계 정정 후) **100%**
> **Agent**: bkit:gap-detector

| 항목 | 내용 |
|------|------|
| 설계 문서 | `docs/02-design/features/chart-builder.design.md` |
| Plan 문서 | `docs/01-plan/features/chart-builder.plan.md` |
| 구현 경로 | `src/domain/visualization/`, `src/infrastructure/visualization/`, `src/application/general_chat/`, `src/api/main.py` |

---

## 1. 종합 스코어

| 항목 | 스코어 | 상태 |
|------|:------:|:----:|
| 설계 일치도 (Design Match) | 98% → 100%* | 정상 |
| 아키텍처 준수 (DDD 레이어) | 100% | 정상 |
| 설계 결정 D1~D4 반영 | 100% | 정상 |
| 테스트 커버리지 (계획 대비) | 100% | 정상 |
| **Overall Match Rate** | **98% → 100%*** | **정상 (>=90%)** |

\* Gap-1을 설계 정정(의도된 단순화 확정)으로 해소 → 100%.

---

## 2. 파일 단위 대조 (설계 §10.1)

### 신규 파일
| 설계 명세 | 구현 파일 | 상태 |
|-----------|-----------|------|
| chart_schemas.py (ChartType/Dataset/Data/Config) | `src/domain/visualization/chart_schemas.py` | ✅ 일치 |
| chart_policy.py (ChartSeriesDraft/Draft/DraftList/StylePolicy) | `src/domain/visualization/chart_policy.py` | ✅ 일치 |
| llm_chart_builder.py (LangChainChartBuilder) | `src/infrastructure/visualization/llm_chart_builder.py` | ✅ 일치 |

### 수정 파일
| 설계 명세 | 구현 위치 | 상태 |
|-----------|-----------|------|
| interfaces.py +ChartBuilderInterface | `interfaces.py` | ✅ 일치 |
| GeneralChatResponse.charts | `general_chat/schemas.py:44` | ✅ 일치 |
| config.chart_max_count | `config.py:81` =3 | ✅ 일치 |
| use_case `_maybe_build_charts`/stream/execute | `use_case.py:103-119, 202-326` | ⚠️ Gap-1 (Minor) |
| main.py DI 조립 | `create_general_chat_use_case_factory` | ✅ 일치 |

### 테스트 (설계 §8)
| 명세 | 구현 | 상태 |
|------|------|------|
| test_chart_schemas.py | 존재 (5) | ✅ |
| test_chart_policy.py | 존재 (6) | ✅ |
| test_llm_chart_builder.py | 존재 (6, `test_caps_to_max_count` 포함) | ✅ |
| test_chart_integration.py | 존재 (8) | ✅ |

총 25개 신규 테스트 GREEN.

---

## 3. 설계 결정 D1~D4 검증

| 결정 | 결과 |
|------|------|
| **D1** chart_max_count=3 + 상한 절단 | ✅ `config.py:81`=3, `llm_chart_builder.build()` `[:max_count]` 절단, `test_caps_to_max_count` 검증 |
| **D2** title/축→options, 색상 백엔드 | ✅ `ChartStylePolicy._build_options`(title→plugins.title, bar/line→scales.x/y.title), `_build_dataset`(pie/doughnut/radar=list[str], 그외 단일+borderColor) |
| **D3** sources 컨텍스트 build() 전달 | ✅(본질 충족) `_build_chart_context(sources)`→build(context). 단 tools_used는 미사용 → Gap-1 |
| **D4** 공유 팩토리 조립(REST+WS) | ✅ `create_general_chat_use_case_factory` 내 builder/classifier/policy 조립, REST·WS 동일 팩토리 |

## 4. 계약 / Graceful / DDD 검증

| 포인트 | 결과 |
|--------|------|
| ChartConfig ↔ 프론트 ChartPayload `{type,data,options}` 1:1 | ✅ |
| 화이트리스트 bar/line/pie/doughnut/scatter/radar | ✅ ChartType 6종 정확 일치 |
| Graceful (실패/비-visualize/미주입 → charts=[]) | ✅ builder 예외→[], 미주입/빈답변→[], classifier 미주입/예외→text, 빈 datasets 제거 |
| DDD domain→infra 참조 없음 | ✅ infra→domain, app→domain(port), main→infra 주입. 방향 정상 |
| WS 패스스루 | ✅ ws_adapter payload 전체→data, charts 자동 도달 |

---

## 5. Gap 목록

### Gap-1 (Minor / 해소됨): `_build_chart_context` tools_used 미사용

| 항목 | 설계 §5.2 (초안) | 구현 |
|------|-----------------|------|
| 시그니처 | `_build_chart_context(sources, tools_used)` | `_build_chart_context(sources)` |
| 동작 | sources content + 도구 출력 요약 결합 | sources.content만 결합(2000자) |

**판정: 의도된 단순화로 확정 → 설계 정정.**
- 근거: General Chat의 `tools_used`는 `_parse_agent_output`에서 **도구 이름 문자열 리스트**(출력 아님). 수치 추출 컨텍스트로 도구 이름은 무의미하고, 실제 데이터는 `sources.content`에 담긴다. sources-only가 D3 의도("수치 근거 보강 컨텍스트")에 더 부합.
- 조치: 설계 §5.2/§4.1(D3)의 `_build_chart_context(sources, tools_used)` → `(sources)`로 정정, "도구 출력" 문구를 "sources 컨텍스트"로 조정 (본 분석과 함께 적용).
- 영향도: 낮음. 핵심 흐름·graceful·계약 무영향.

> Missing/Added/Changed 그 외 항목 없음. 설계 §11 Out of Scope(Excel/Supervisor, agent_answer_completed.charts) 미구현은 정상.

---

## 6. 후속 단계

- Match Rate 98%(→정정 후 100%) ≥ 90% → **Act(iterate) 불필요**.
- 잔여 검증 메모(보고서 기록 권장):
  - `tests/api/test_general_chat_router.py` 7건 실패 = **사전 존재**(get_auth_context DI placeholder, chart-builder 무관, git stash로 검증).
  - `test_use_case.py` ERROR = Windows 이벤트 루프 teardown flakiness, 격리 실행 시 통과(메모리 노트 backend-test-eventloop-flakiness).
- 다음: `/api-contract-sync`(프론트 REST 타입 charts 동기화) → `/pdca report chart-builder`.

---

## Version History
| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-06-06 | gap-detector 분석, Match Rate 98%, Gap-1 설계 정정으로 해소 |
