# Gap Analysis: chart-context-continuity (Phase 1)

> Date: 2026-06-10
> Phase: Check
> Design: `docs/02-design/features/chart-context-continuity.design.md` §3
> Scope: **Phase 1 한정** (General Chat 차트 참조 연속성). Phase 2/3은 의도된 미구현(deferred).

---

## Overall Scores (Phase 1 기준)

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match (§3.1–§3.8) | 100% | ✅ |
| 수치 상한 반영 | 100% | ✅ |
| Graceful Degrade / 폴백 | 100% | ✅ |
| **Overall (Phase 1)** | **100%** | ✅ |

설계와 구현이 항목 단위로 정확히 일치. 누락·역행 항목 없음. 발견된 차이는 "설계보다 강하게 구현한 안전망"(상향 호환) 2건뿐 — 감점 사유 아님.

---

## 1. 설계 항목별 검증 (D1~D5, D7-rev1, D8)

| 설계 항목 | 구현 위치 | 일치 | 비고 |
|----------|-----------|:----:|------|
| **D1** full config 미투입, 캡션만 | `chart_caption_policy.py` `build_caption` + use_case `_to_langchain_message` | ✅ | content 뒤 캡션 1줄, config JSON 미투입 |
| **D2** 휴리스틱 1차 + 보수적 폴백 | `followup_policy.py` `decide` (LLM 무의존) | ✅ | 애매 시 NONE. application 가드 이중 안전망 |
| **D3** 신규 포트 `ChartTransformerInterface` 분리 | `interfaces.py` (기존 `ChartBuilderInterface` 무변경) | ✅ | 책임 분리 준수 |
| **D4** ReAct 우회 전용 분기 + 실패 폴백 | use_case `stream` + `_try_chart_edit` | ✅ | `edited is None` → 일반 경로. 이벤트 시퀀스 유지 |
| **D5** 색상은 StylePolicy, 선택적 오버라이드 | `chart_policy.py` `ChartEditSeriesDraft.color` + `_build_dataset` | ✅ | per-point 타입은 오버라이드 무시·팔레트 유지 |
| **D7-rev1** 캡션 투입, 요약 본문 미포함 | `_to_langchain_message` + `entities.py` 주석 + `conversation-memory.md` | ✅ | summarizer 입력은 content만 |
| **D8** 응답 계약 무변경 | ANSWER_COMPLETED payload `charts: list[dict]` 유지 | ✅ | 프론트 작업 없음. `tools_used=["chart_transformer"]` |

---

## 2. 수치 상한 반영 검증

| 상한 항목 | 설계값 | 구현값 | 일치 |
|----------|--------|--------|:----:|
| 캡션 길이 | ≤ 200자 | `MAX_LEN = 200` | ✅ |
| 차트 표기 수 | 최대 2개 | `MAX_CHARTS = 2` | ✅ |
| labels 표기 수 | 최대 5개 | `MAX_LABELS = 5` | ✅ |
| Transformer 입력 직렬화 | ≤ 8KB | `_MAX_CHARTS_JSON = 8_000` | ✅ |
| 초과 시 데이터 절단 | 앞 100포인트 | `_MAX_DATA_POINTS = 100` | ✅ |
| 보조 컨텍스트 상한 | ≤ 2,000자 | `_MAX_CONTEXT = 2_000` | ✅ |

캡션 200자 절단 시 닫는 괄호 보존(`caption[:MAX_LEN-1] + "]"`) — 설계 미명시 디테일 합리적 보강.

---

## 3. Graceful Degrade / 폴백 경로 검증

| 시나리오 | 설계 기대 | 구현 | 일치 |
|----------|-----------|------|:----:|
| transformer 미주입 | 편집 분기 비활성(하위호환) | `_try_chart_edit` None 가드 | ✅ |
| 세션 저장 차트 없음 | 일반 경로 (오분류 안전망) | `if not recent_charts: return None` | ✅ |
| 의도 NONE | 일반 경로 | decision 가드 | ✅ |
| transform 빈 결과 | 일반 경로 폴백 | `if not result.charts: return None` | ✅ |
| transform 예외 | 빈 결과 + logger.error | `_transform_safe` (`_classify_safe` 동형) | ✅ |
| LLM 인프라 예외 | charts=[] + logger.error | `llm_chart_transformer` try/except | ✅ |
| 캡션 파싱 실패 | `""` 반환 | `chart_caption_policy` graceful | ✅ |
| caption/followup 미주입 | 기본값 활성 | `or ChartFollowupPolicy()/ChartCaptionPolicy()` | ✅ |

---

## 4. 발견된 차이

### 🔵 설계 대비 강화된 구현 (상향 호환, 영향 낮음)
| 항목 | 설계 | 구현 | 영향 |
|------|------|------|------|
| Transformer draft 유효성 | §3.6은 변환만 기술 | `labels/series` 빈 draft skip, 빈 datasets 제외 | 낮음 (방어적 필터) |
| followup `decide` None 입력 | `decide(question: str)` | `question: str | None`, None→NONE | 낮음 (널 안전) |

→ 설계 누락이 아닌 견고성 보강. 문서 갱신은 선택사항.

### 🔴 Missing / 🟡 역행
**없음.** Phase 1 설계 항목 전부 구현됨.

### ⏸️ 의도된 미구현 (deferred — Match Rate 계산 제외)
| Phase | 항목 | 차단 사유 |
|-------|------|----------|
| Phase 2 | `analysis_artifact` 엔티티/ORM/리포지토리/V032, 저장 훅 | 선행 `excel-chart-routing-dedup` 완료 대기 |
| Phase 3 | `NEW_FROM_DATA` 판정 활성화, Supervisor 경로 계약 | Phase 2 선행 (enum 값만 선점) |

---

## 5. 테스트 정합성

| 테스트 파일 | 케이스 | 설계 §7 매핑 |
|-------------|:------:|--------------|
| `test_chart_caption_policy.py` | 8 | §7.1 ✅ |
| `test_followup_policy.py` | 12 | §7.1 ✅ |
| `test_chart_edit_draft.py` | 6 | §7.1 ✅ |
| `test_llm_chart_transformer.py` | 7 | §7.3 ✅ |
| `test_use_case_chart_context.py` | 10 | §7.2 ✅ |

5개 파일 전부 존재, 설계 테스트 계획 7항목 모두 커버. (tests/api·infra 사전 실패 28/30건은 auth DI 이슈 — 본 feature 무관, 회귀 오인 금지.)

---

## Phase 1 Match Rate: **100%**

## Recommended Actions

### Immediate
- 없음. Phase 1 설계 완전 일치 — `/pdca report chart-context-continuity` 진행 가능 (Phase 1 범위 한정 명시).

### Documentation (선택)
1. 설계 §3.6에 Transformer 결과 유효성 필터 1줄 추가.
2. `decide()` 시그니처 `str | None`을 §3.3에 반영.

### Phase 2/3 진입 전
- 선행 `excel-chart-routing-dedup`(차트 파이프라인 일원화) 완료 확인 (Phase 2 전제).

---

> **전체 feature(3 Phase) 기준**: Phase 1만 완료(약 1/3), Phase 2/3은 의도된 deferred. 본 분석의 100%는 **Phase 1 범위 한정** Match Rate.
