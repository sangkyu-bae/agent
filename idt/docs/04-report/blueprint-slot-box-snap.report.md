# blueprint-slot-box-snap Completion Report

> **Status**: Complete
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Completion Date**: 2026-08-25
> **PDCA Cycle**: 골든 샘플 충실도 — 결함 B 대응 (A → B 순)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | blueprint-slot-box-snap |
| Start Date | 2026-08-25 |
| End Date | 2026-08-25 |
| Duration | 1일 (단일 세션) |
| Trigger | 사용자 지적 — "3번째 페이지 스타일 박스 안에 글자가 제대로 안 들어가 있고 아래 설명은 좌표가 겹칩니다" |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 93%                        │
├─────────────────────────────────────────────┤
│  ✅ 완료:      FR-01 ~ FR-06   (6 / 6)       │
│  ✅ 성공기준:  SC-1,3,4,5,6,7  (6 / 7)       │
│  ⚠️ 부분충족:  SC-2            (5/6 패턴)    │
│  ✅ 설계결정:  DR-1 ~ DR-9     (9 / 9)       │
│  ✅ 테스트:    설계 시나리오   (30 / 30)     │
├─────────────────────────────────────────────┤
│  Match Rate: 98%      회귀: 0건 (297 passed) │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 장식 좌표는 서버가 PDF에서 **실측**하는데 슬롯 좌표는 비전 LLM이 **추정**했다. 둘을 한 번도 맞추지 않아 골든 샘플 **13개 텍스트 슬롯 전부**가 어긋났고(최대 1.83in), 하이라이트 박스 밖으로 글자가 나가고 아래 요소와 0.15in 겹쳤다 |
| **Solution** | 도메인 정책 `SlotBoxPolicy`가 비전 박스를 **배정 힌트로만** 쓰고 좌표는 실측 span union으로 대체한다. 위치·폭은 실측, 높이는 다음 경계까지 확장하되 포함 장식 하단으로 캡한다 |
| **Function/UX Effect** | **렌더된 PPTX 텍스트 위치가 원본 PDF와 오차 0.000in**(6/6 슬라이드). 표지 제목 1.83in 밀림 해소, 3페이지 겹침 해소, 6개 패턴 중 5개 겹침 0건 |
| **Core Value** | 블루프린트가 "대충 비슷한 레이아웃"에서 **"원본을 실제로 재현하는 템플릿"**이 됐다. 비전 모델의 강점(슬롯 분류)은 유지하고 약점(좌표)만 실측으로 대체하는 구조를 확립했다 |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 렌더 텍스트 위치가 원본 PDF와 0.1in 이내 | ✅ Met | **6/6 슬라이드 Δ=0.000in**. `test_rendered_textbox_position_matches_original_pdf` |
| SC-2 | 장식-슬롯 부분 겹침 0건 | ⚠️ **Partial** | **5/6 패턴 0건, p6만 3건.** 구조 한계 — §4.1 |
| SC-3 | 표지 제목 x 오차 1.83in → 0.1in 이하 | ✅ Met | x = 0.200 → **0.062**, 오차 0.000in |
| SC-4 | 매칭 0건 시 vision 좌표 보존 + 경고 | ✅ Met | `test_slot_without_assigned_span_keeps_vision_box_and_warns` |
| SC-5 | 푸터 span 미배정 | ✅ Met | 텍스트 슬롯 최대 y = **0.758** < 0.88 |
| SC-6 | 설계 시나리오 **전건** 자동화 | ✅ Met | **30 / 30** (+ 설계에 없던 추가 2건) |
| SC-7 | 기존 테스트 회귀 0건 | ✅ Met | 297 passed / **0 failed** |

**Success Rate: 6.5 / 7 (93%)**

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 스냅 대상 = **텍스트 슬롯만** | ✅ | 결과적으로 `DecorationPolicy` 결합에서 **구조적으로 격리**됐다 — `_CONTENT_SLOT_KINDS`가 CHART/IMAGE/TABLE뿐이라 장식 판정이 스냅 전후 동일 |
| [Plan] | 높이 = **위치·폭 스냅 + 확장** | ✅ | 생성물이 샘플보다 길어도 잘리지 않는다 |
| [Plan] | 적용 시점 = **추출만** | ✅ | 실측 span이 추출 때만 존재 — 기술적 유일 지점. 기존 블루프린트는 재추출 필요(§4.1) |
| [Design] DR-1 | `policies.py`에 `SlotBoxPolicy` (Option C) | ✅ | `DecorationPolicy`와 동형, 기하 헬퍼 이관 0건, 신규 파일 0개 |
| [Design] DR-2 | 비전 박스는 배정 힌트로만 | ✅ | 최종 좌표에 추정값(0.05 배수) 잔존 **0개** |
| [Design] DR-3 | 푸터 기준을 `FooterPolicy`와 공유 | ✅ | `_FOOTER_BAND_Y`를 391행·775행이 공유 — 이중 렌더 방지 |
| [Design] DR-4 | 경계 후보에 텍스트 아닌 슬롯 포함 | ✅ | **설계 시뮬레이션이 잡은 결함** — 누락 시 `p5 title` 높이가 0.676(표 전체 삼킴). 포함 후 0.119 |
| [Design] DR-5 | 포함 장식으로 높이 캡 | ✅ | 긴 텍스트가 하이라이트 박스 밖으로 새지 않는다 |
| [Design] DR-6 | 동점은 중심 거리 → id 사전순 | ✅ | 골든에선 미발동. 결정론 방어 규칙 |
| [Design] DR-7 | `DecorationPolicy` → `SlotBoxPolicy` 순서 | ✅ | `extraction_use_case.py:276` → `:296` |
| [Design] DR-8 | 출처(PDF/PPTX) 분기 없음 | ✅ | 신규 코드에 `source_kind`/`pdf`/`pptx` 참조 **0건** — PPTX span도 도형 실측이라 균일 적용이 더 단순 |
| [Design] DR-9 | 예외 없이 원본 유지 + 경고 | ✅ | 신규 코드에 `raise` **0건** |

**준수율: 12 / 12 (100%)**

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [blueprint-slot-box-snap.plan.md](../01-plan/features/blueprint-slot-box-snap.plan.md) | ✅ Finalized (v0.3) |
| Design | [blueprint-slot-box-snap.design.md](../02-design/features/blueprint-slot-box-snap.design.md) | ✅ Finalized (v0.2) |
| Check | [blueprint-slot-box-snap.analysis.md](../03-analysis/blueprint-slot-box-snap.analysis.md) | ✅ Complete (98%) |
| Act | 본 문서 | ✅ Complete |
| 선행 사이클 | [blueprint-font-mapping-migration.report.md](blueprint-font-mapping-migration.report.md) | 결함 A |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|:------:|-------|
| FR-01 | x·y·w를 실측 span union으로 | ✅ Complete | `_union` + `_snapped` |
| FR-02 | 배정 + 결정론적 타이브레이크 | ✅ Complete | 중심점 포함 → 중심 y 거리 → id 사전순 |
| FR-03 | 높이를 아래쪽 경계까지 확장 | ✅ Complete | `_bottom` — DR-4가 핵심 |
| FR-04 | 푸터 span 배제 | ✅ Complete | `FooterPolicy`와 동일 기준 |
| FR-05 | 매칭 0건 폴백 + 경고 | ✅ Complete | 골든에선 미발동 (경고 0건) |
| FR-06 | 슬라이드 경계 불변식 | ✅ Complete | `_snap_clamped` |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|:------:|
| 아키텍처 (domain 순수) | 위반 0건 | 0건 | ✅ |
| application에 규칙 금지 | 결선만 | 기하 규칙 전부 domain | ✅ |
| 결정론 (LLM 재호출 없음) | — | 순수 함수 | ✅ |
| 하위호환 (좌표 형식) | 무변경 | 무변경 | ✅ |
| 회귀 | 0건 | 0건 (297 passed) | ✅ |
| 신규 코드 커버리지 | 95% | `SlotBoxPolicy` **100%** | ✅ |
| 함수 40줄 이하 | 위반 0건 | 0건 (AST 검사) | ✅ |
| ruff lint | 0건 | All checks passed | ✅ |
| API 계약 | 변경 없음 | 변경 없음 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | 규모 | Status |
|-------------|----------|:----:|:------:|
| 스냅 정책 | `src/domain/blueprint/policies.py:726-862` | 138줄 | ✅ |
| 결선 | `src/application/blueprint/extraction_use_case.py:296-323` | ~30줄 | ✅ |
| 도메인 테스트 | `tests/domain/blueprint/test_slot_box_policy.py` | 304줄 / 21건 (신규) | ✅ |
| 결선 테스트 | `tests/application/blueprint/test_extraction_use_case.py` | +3건 | ✅ |
| 골든·E2E 테스트 | `tests/integration/blueprint/test_golden_sample_fidelity.py` | +8건 | ✅ |
| PDCA 문서 4종 | `docs/01-plan` ~ `docs/04-report` | — | ✅ |

**src 수정 2 (~168줄), 테스트 신규 1 / 수정 2 (~32건)**

---

## 4. Incomplete Items

### 4.1 다음 사이클 이월

| Item | Reason | Priority | 비고 |
|------|--------|:--------:|------|
| **p6 다중 카드 패턴 겹침 3건** | 비전 모델이 카드 3장을 `bullets` 슬롯 **하나**로 준 구조 문제 — 좌표로 풀 수 없다 | **High** | **결함 C와 동일 원인.** 슬롯 분할로 함께 해결 |
| **과적합 교차 검증** | 비전 좌표 문제를 재현하는 **독립 문서가 저장소에 없다** — `samples/`의 PPTX 3건은 우리 생성물이고 PPTX 경로는 비전을 타지 않는다 | Medium | 실사용 PDF 1~2건 확보 필요 |
| `_snap_slot_boxes` 방어 분기 테스트 | 설계 §8에 대응 시나리오 없음, 골든에서 미발동 | Low | 2줄 미커버 |
| **기존 저장 블루프린트 재추출 안내** | 실측 span이 추출 시점에만 존재 — 로드 경계 보정이 기술적으로 불가능 | Medium | 사이클 A와 달리 **재추출 필수** |

#### p6 구조 한계 상세

```
슬롯 bullets  0.266 ─────────────────────── 0.880   ← 하나
장식 deco2    0.241 ── 0.407
장식 deco1              0.444 ── 0.611
장식 deco3                        0.648 ── 0.815
```

union 자체(0.266~0.771)가 이미 세 카드를 가로지르므로 높이 확장 전에도 동일하게 3건 겹친다. `test_known_limitation_multi_card_pattern_still_overlaps`가 이를 고정하며, 결함 C에서 해소되면 실패해 이월 항목 정리를 유도한다.

### 4.2 이번 범위에서 명시 제외

| Item | 상태 |
|------|:----:|
| 표·차트·이미지 슬롯 스냅 | 미착수 (`find_tables` 오탐 우려) |
| 텍스트박스 inset 보정 | 미착수 (SC-1 오차 0.000in이라 불필요 확인됨) |
| 비전 프롬프트 변경 | 채택 안 함 (비결정적) |
| **결함 C** — 목차·카드 내용 폴백 | 미착수 |
| **결함 D** — 차트 레이블·단위, 표 테두리, 문단 여백 | 미착수 |

### 4.3 취소/보류

없음.

---

## 5. Quality Metrics

### 5.1 최종 분석 결과

| Metric | Target | Final | 판정 |
|--------|:------:|:-----:|:----:|
| Design Match Rate | 90% | **98%** | ✅ |
| — Structural | — | 100% (11/11) | ✅ |
| — Functional | — | 100% (6/6 FR) | ✅ |
| — Contract | — | 100% | ✅ |
| — Runtime | — | 95% | ✅ |
| Success Criteria | — | 6.5/7 (93%) | ⚠️ |
| Decision Record 준수 | — | 12/12 (100%) | ✅ |
| 설계 시나리오 자동화 | 100% | 30/30 (100%) | ✅ |
| `SlotBoxPolicy` 커버리지 | 95% | **100%** | ✅ |
| 회귀 | 0건 | 0건 | ✅ |
| Critical 이슈 | 0건 | 0건 | ✅ |
| **종합 점수** | — | **94 / 100** | ✅ |

### 5.2 해결한 이슈

| Issue | Resolution | Result |
|-------|------------|:------:|
| 텍스트 슬롯 13/13 좌표 어긋남 (최대 1.83in) | 실측 span union 스냅 | ✅ 오차 0.000in |
| 3페이지 하이라이트 박스 겹침 0.15in (사용자 신고) | 실측 스냅의 부수 효과 | ✅ 겹침 0건 |
| 표지 제목 1.83in 밀림 | 동상 | ✅ x 0.200 → 0.062 |
| 제목 박스가 표 영역을 삼킴 (설계 중 발견) | 경계 후보에 비텍스트 슬롯 포함 (DR-4) | ✅ h 0.676 → 0.119 |
| 긴 텍스트가 하이라이트 박스 밖으로 샐 위험 | 포함 장식 하단 캡 (DR-5) | ✅ 예방 |
| 푸터 이중 렌더 위험 | `FooterPolicy`와 동일 기준 공유 (DR-3) | ✅ 예방 |

### 5.3 Plan/Design 문서 정정 이력

이번 사이클은 **Plan의 판단 3건이 실측으로 뒤집혔다.** 정정을 기록해 둔다.

| 정정 | 최초 | 정정 후 | 발견 시점 |
|------|------|---------|:--------:|
| SC-1 정의 | "슬롯 좌표 오차 0.1in 이하" | **동어반복**(스냅 결과를 실측 union과 비교) → "렌더 텍스트가 원본 PDF와 0.1in 이내" | Design |
| 과적합 완화책 | "다른 PPTX 2건으로 교차 확인" | **불가능** — 우리 생성물이고 비전을 타지 않음 → 미완화 명시 | Design |
| SC-2 정의 | "겹침 0건" | 다중 카드 패턴 미고려 → "슬롯↔장식 1:1 패턴에서 0건" | Do |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **설계 단계 시뮬레이션이 규칙 결함을 잡았다.** 제안한 높이 경계 규칙을 문서로 확정하기 전에 골든 샘플로 돌려 봤더니 `p5 title` 높이가 표 영역 전체를 삼켰다. 코드를 쓰기 전에 규칙을 실행해 본 것이 DR-4를 낳았다.
- **"비전의 강점만 취한다"는 프레이밍이 설계를 단순하게 만들었다.** 매칭 실패 슬롯이 0건이라는 관찰 — 비전은 영역은 맞히고 정밀도만 틀린다 — 이 배정/좌표를 분리하는 2단계 구조로 바로 이어졌다.
- **선택한 범위가 우연히 결합을 끊어 줬다.** 텍스트 슬롯만 스냅하기로 한 결정 덕에 `DecorationPolicy`(CHART/IMAGE/TABLE만 참조)와의 순환이 구조적으로 사라져, 실행 순서를 단방향으로 확정할 수 있었다.
- **SC-1을 "렌더 결과 vs 원본"으로 정의한 것이 실질 검증을 만들었다.** 내부 값끼리 비교했다면 항상 통과했을 것이다.
- **직전 사이클의 교훈을 미리 적용했다.** "수정이 기존 저장 데이터에 닿는가"를 Plan 단계에서 물어, 재추출 필요를 처음부터 명시하고 진행했다.

### 6.2 What Needs Improvement (Problem)

- **Plan의 성공 기준 2개가 실측 없이 작성돼 나중에 정정됐다.** SC-1은 동어반복이었고 SC-2는 다중 카드 패턴을 몰랐다. 둘 다 골든 샘플을 한 번 훑었으면 Plan 단계에서 알 수 있었다.
- **과적합 리스크를 끝내 완화하지 못했다.** 완화책을 Plan에 적어 두고 Design에서 실행 불가로 판명됐다. 완화책이 실현 가능한지를 Plan 단계에서 확인하지 않았다.
- **검증 문서가 여전히 1건이다.** 2단 조판, 우측 정렬 제목, 세로 문서 같은 다른 레이아웃에서 스냅이 어떻게 동작하는지 모른다. 규칙을 일반 기하로 정의한 것은 방어책이지 검증이 아니다.
- **테스트 단언 오류 2건이 Red 단계에서 나왔다.** 하나는 높이 확장을 고려하지 않은 단언, 하나는 슬라이드 경계를 넘는 픽스처였다. 구현이 아니라 제 테스트가 틀렸다.

### 6.3 What to Try Next (Try)

- **Plan의 성공 기준마다 "무엇과 무엇을 비교하는가"를 명시한다.** SC-1의 동어반복은 비교 대상을 적지 않아서 생겼다.
- **완화책을 Plan에 적을 때 실행 가능성을 그 자리에서 확인한다.** "다른 샘플로 교차 확인"은 샘플 성격을 1분만 봤으면 불가능함을 알 수 있었다.
- **설계 시뮬레이션을 표준 절차로 승격한다.** 이번에 DR-4를 잡은 방식이다 — 규칙 초안을 실제 데이터에 돌려 보고 결과를 설계 문서에 남긴다.
- **결함 C 착수 시 p6를 첫 검증 대상으로 삼는다.** 슬롯 분할이 되면 이번 이월 항목과 "카드 3개 빈 상태"가 동시에 풀린다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA 프로세스

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 성공 기준·완화책을 실측 없이 기재 | **기준마다 비교 대상 명시 + 완화책 실행 가능성 즉시 확인** |
| Design | 시뮬레이션이 결함을 잡음 (이번 성과) | **표준 절차로 승격** — 규칙 초안을 데이터에 돌리고 결과를 문서화 |
| Do | TDD 9단계, Red에서 단언 오류 2건 | 픽스처가 도메인 불변식(`RelBox` 경계)을 만족하는지 먼저 확인 |
| Check | gap-detector 미사용 (세션 규칙) | 독립 검증 부재를 문서에 고지하는 관행 유지 |

### 7.2 도구/환경

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| 테스트 자산 | `samples/`에 **실사용 원본 PDF 1~2건** 확보 | 과적합 리스크 완화 — 현재 유일한 미해결 검증 공백 |
| 관리 UI | 블루프린트 상세에 "슬롯 좌표 출처(추정/실측)" 표시 | 재추출 필요 여부를 사용자가 판단 가능 |

---

## 8. Next Steps

### 8.1 즉시

- [ ] **기존 블루프린트 재추출** — 이번 수정은 신규 추출분에만 적용된다
- [ ] 재추출 후 PPT 생성해 좌표 정렬 육안 확인

### 8.2 다음 PDCA 사이클

| Item | Priority | 근거 |
|------|:--------:|------|
| **결함 C — 슬롯 분할 + 목차·카드 내용 폴백** | **High** | §4.1 이월 항목과 동일 원인. 목차가 통째로 비는 문제도 함께 해결 |
| **결함 D — 차트 레이블·단위, 표 테두리, 문단 여백** | Medium | 개별 영향은 작으나 건수가 많음 |
| 과적합 교차 검증 | Medium | 실사용 PDF 확보 후 |

---

## 9. Changelog

### 2026-08-25

**Added:**
- `SlotBoxPolicy` — 비전 추정 슬롯 좌표를 실측 span union으로 스냅하는 도메인 정책
- `_snap_slot_boxes` — 추출 파이프라인 결선 (`DecorationPolicy` 다음)
- 다중 카드 패턴 한계를 고정하는 회귀 테스트 (결함 C 이월 근거)

**Changed:**
- 텍스트 슬롯(title/text/bullets)의 `box`가 비전 추정값 → **실측 좌표**
- 슬롯 높이가 아래쪽 경계(슬롯·장식·푸터 중 최근접)까지 확장, 포함 장식 하단으로 캡

**Fixed:**
- 골든 샘플 13개 텍스트 슬롯 전부의 좌표 어긋남 (최대 1.83in → 0.000in)
- 3페이지 하이라이트 박스와 본문의 0.15in 겹침 (사용자 신고 원본)
- 표지 제목이 1.83in 밀려 렌더되던 문제

**Unchanged (의도적):**
- 표·차트·이미지·푸터 슬롯 — 스냅 대상 아님
- `pptx_renderer` — 좌표를 그대로 수신
- API 응답 스키마 / DB 스키마 / 마이그레이션

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-25 | 완료 보고서 작성 — Match Rate 98%, SC 6.5/7, DR 12/12 | 배상규 |
