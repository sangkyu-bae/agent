# blueprint-slot-box-snap Gap Analysis

> **Project**: idt (sangplusbot 백엔드)
> **Author**: 배상규
> **Date**: 2026-08-25
> **Phase**: Check
> **Plan**: [blueprint-slot-box-snap.plan.md](../01-plan/features/blueprint-slot-box-snap.plan.md) (v0.3)
> **Design**: [blueprint-slot-box-snap.design.md](../02-design/features/blueprint-slot-box-snap.design.md) (v0.2)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 슬롯은 추정 좌표, 장식은 실측 좌표 — 맞추지 않아 모든 슬라이드 정렬이 어긋난다 |
| **WHO** | P2 — 골든 샘플로 자사 문서 양식을 재현하려는 KB 운영자 |
| **RISK** | 샘플 1건 과적합 — 교차 확인용 독립 문서가 없어 **미완화** |
| **SUCCESS** | 렌더 텍스트 위치가 원본 PDF와 0.1in 이내, 장식-슬롯 겹침 0건 |
| **SCOPE** | 텍스트 슬롯(title/text/bullets) 좌표 스냅 |

---

## 0. 분석 방법 고지

**gap-detector 서브에이전트를 호출하지 않았습니다.** 이 세션은 사용자가 명시 요청하지 않은 에이전트 호출을 금지하므로, 아래는 전부 **제가 직접 수행한 정적 검증과 실행 측정**입니다. 독립적인 제3자 검증 관점은 반영되지 않았습니다.

---

## 1. Strategic Alignment

| 질문 | 판정 | 근거 |
|------|:----:|------|
| Plan의 핵심 문제(WHY)를 해결했는가 | ✅ | 텍스트 슬롯 13/13이 실측 좌표. 추정값(0.05 배수) 잔존 **0개** |
| 사용자가 신고한 3페이지 겹침이 해소됐는가 | ✅ | `test_reported_page3_overlap_is_resolved` — p3 부분 겹침 0건 |
| 표지 제목 1.83in 밀림이 해소됐는가 | ✅ | x = 0.200 → **0.062**, 이동량 1.83in |
| 설계 결정(DR-1~9)을 따랐는가 | ✅ | 9/9 — §4 |
| 범위를 넘지 않았는가 | ✅ | 표·차트·이미지 슬롯 무변경, 마이그레이션 0건, 렌더러 무변경 |

### 1.1 핵심 증거 — 렌더 E2E 실측

원본 PDF의 제목 위치와 렌더된 PPTX 도형 위치 비교(inch):

```
slide  렌더 좌표         원본 PDF          Δx      Δy
p1     (0.833, 2.958)   (0.833, 2.958)   0.000   0.000
p2     (0.833, 0.610)   (0.833, 0.610)   0.000   0.000
p3     (0.833, 0.610)   (0.833, 0.610)   0.000   0.000
p4     (0.833, 0.610)   (0.833, 0.610)   0.000   0.000
p5     (0.833, 0.610)   (0.833, 0.610)   0.000   0.000
p6     (0.833, 0.610)   (0.833, 0.610)   0.000   0.000
```

**전 슬라이드 오차 0.000in** (허용 0.1in). 이것이 SC-1의 실질 검증이다 — 설계 §14가 지적한 동어반복을 피하기 위해 렌더 결과를 원본과 직접 비교했다.

---

## 2. Success Criteria 평가

| SC | 내용 | 판정 | 증거 |
|:--:|------|:----:|------|
| SC-1 | 렌더 텍스트 위치가 원본 PDF와 0.1in 이내 | ✅ | §1.1 — 6/6 슬라이드 **Δ=0.000in**. `test_rendered_textbox_position_matches_original_pdf` |
| SC-2 | 장식-슬롯 부분 겹침 0건 | ⚠️ **Partial** | **5/6 패턴 0건, p6만 3건.** 구조 한계로 범위 조정(v0.3) — §5.1 |
| SC-3 | 표지 제목 x 오차 1.83in → 0.1in 이하 | ✅ | x=0.062, 오차 0.000in. `test_sc3_cover_title_x_is_snapped_from_vision_estimate` |
| SC-4 | 매칭 0건 시 vision 좌표 보존 + 경고 | ✅ | `test_slot_without_assigned_span_keeps_vision_box_and_warns` (골든에선 미발동 — 경고 0건) |
| SC-5 | 푸터 span 미배정 | ✅ | 텍스트 슬롯 최대 y = **0.758** < 0.88. `test_sc5_footer_spans_are_not_inside_any_text_slot` |
| SC-6 | 설계 시나리오 **전건** 자동화 | ✅ | **30/30** — §3.3 |
| SC-7 | 기존 테스트 회귀 0건 | ✅ | 297 passed / **0 failed** |

**Success Rate: 6.5 / 7 (93%)**

SC-2만 부분 충족이다. 감점 사유는 코드 결함이 아니라 **Plan이 예상하지 못한 구조적 한계**이며, 사용자 승인 아래 결함 C로 이월했다(§5.1).

---

## 3. Gap Analysis

### 3.1 Structural Match — 100%

| 설계 명시 항목 | 실제 위치 | 판정 |
|---------------|----------|:----:|
| `SlotBoxPolicy` | `policies.py:730` | ✅ |
| `_snappable_spans` | `policies.py:765` | ✅ |
| `_assign` | `policies.py:779` | ✅ |
| `_covers` | `policies.py:792` | ✅ |
| `_union` | `policies.py:796` | ✅ |
| `_snapped` | `policies.py:809` | ✅ |
| `_bottom` | `policies.py:821` | ✅ |
| `_encloses` | `policies.py:844` | ✅ |
| `_snap_clamped` | `policies.py:854` | ✅ |
| `_SNAP_TEXT_KINDS` | `policies.py:726` | ✅ |
| `_snap_slot_boxes` 결선 | `extraction_use_case.py:302` | ✅ |

**11/11 = 100%**

### 3.2 Functional Depth — 100%

| FR | 구현 | 판정 |
|:--:|------|:----:|
| FR-01 x·y·w를 실측 union으로 | `_union` + `_snapped` | ✅ |
| FR-02 배정 + 결정론적 타이브레이크 | `_assign` — 중심 y 거리 → id 사전순 | ✅ |
| FR-03 높이를 경계까지 확장 | `_bottom` | ✅ |
| FR-04 푸터 span 배제 | `_snappable_spans` | ✅ |
| FR-05 매칭 0건 폴백 + 경고 | `SlotBoxPolicy.apply` | ✅ |
| FR-06 경계 불변식 | `_snap_clamped` | ✅ |

- **Placeholder 0건** (`TODO`/`FIXME`/`NotImplementedError`/빈 `pass`)
- **Shallow 파일 0건**

### 3.3 Test Scenario Coverage — 30/30 = 100%

| 계층 | 설계 시나리오 | 테스트 함수 | 판정 |
|------|:------------:|:----------:|:----:|
| L1 Domain Unit | 1~19 (19건) | 21 (파라미터화 포함) | ✅ |
| L2 Application Integration | 20~23 (4건) | 3 | ✅ |
| L3 Golden Regression | 24~28 (5건) | 5 | ✅ |
| L4 Render E2E | 29~30 (2건) | 2 | ✅ |

설계에 없던 추가 테스트 2건(`test_reported_page3_overlap_is_resolved`, `test_known_limitation_multi_card_pattern_still_overlaps`)을 더 작성했다.

### 3.4 API Contract — 100%

설계 §4가 "계약 변경 없음"으로 못박았고 지켜졌다.

- `SlotSchema.box` 필드 구조 무변경, **값만** 정확해짐
- 관리 API 3개 엔드포인트 응답 스키마 무변경
- `idt_front` 타입 동기화 불필요 — 루트 CLAUDE.md §4-1 해당 없음

### 3.5 Runtime — 95%

```
297 passed, 1 deselected, 0 failed   (blueprint 관련 전체)
```

실행 실패 0건. 5점 감점은 §5.2(과적합 미완화)와 §5.3(방어 분기 2줄 미커버) 두 건이다.

### 3.6 Match Rate

```
Overall = Structural×0.15 + Functional×0.25 + Contract×0.25 + Runtime×0.35
        = 100×0.15 + 100×0.25 + 100×0.25 + 95×0.35
        = 15 + 25 + 25 + 33.25
        = 98.25  →  98%
```

| 축 | 점수 |
|----|:----:|
| Structural | 100% |
| Functional | 100% |
| Contract | 100% |
| Runtime | 95% |
| **Overall** | **98%** |

---

## 4. Decision Record 준수 검증

| DR | 결정 | 준수 | 검증 방법 |
|:--:|------|:----:|----------|
| DR-1 | `policies.py`에 `SlotBoxPolicy` 배치 | ✅ | `policies.py:730`, 신규 파일 0개 |
| DR-2 | 비전 박스는 배정 힌트로만 | ✅ | 최종 좌표에 0.05 배수 잔존 **0개** |
| DR-3 | 푸터 기준을 `FooterPolicy`와 공유 | ✅ | `_FOOTER_BAND_Y` 상수를 391행·775행이 공유 |
| DR-4 | 경계 후보에 텍스트 아닌 슬롯 포함 | ✅ | `_bottom`의 `for other in pattern.slots` — `test_height_extends_to_non_text_slot_top`이 고정 |
| DR-5 | 포함 장식으로 높이 캡 | ✅ | `_encloses` + `test_height_is_capped_by_enclosing_decoration` |
| DR-6 | 동점은 중심 거리 → id 사전순 | ✅ | `_assign`의 `min(..., key=lambda s: (abs(...), s.id))` |
| DR-7 | `DecorationPolicy` → `SlotBoxPolicy` 순서 | ✅ | `extraction_use_case.py:276` → `:296` |
| DR-8 | 출처(PDF/PPTX) 분기 없음 | ✅ | 신규 코드에 `source_kind`/`pdf`/`pptx` 참조 **0건** |
| DR-9 | 예외 없이 원본 유지 + 경고 | ✅ | 신규 코드에 `raise` **0건** |

**9/9 = 100%**

---

## 5. 발견 사항

### 5.1 ⚠️ Important — 다중 카드 패턴의 구조적 한계 (SC-2 부분 미달)

골든 6페이지(p6)는 카드 3장이고, 각 카드는 장식 박스 + 액센트 바 + 소제목(15pt) + 본문(13pt)이다. **비전 모델이 이 6개 텍스트를 `bullets` 슬롯 하나로 뭉쳤다.**

```
슬롯 bullets  0.266 ─────────────────────── 0.880   ← 하나
장식 deco2    0.241 ── 0.407
장식 deco1              0.444 ── 0.611
장식 deco3                        0.648 ── 0.815
```

슬롯 하나가 카드 3장을 가로지르므로 **좌표를 아무리 정확히 스냅해도 부분 겹침이 불가피**하다. 높이 확장 탓도 아니다 — union 자체(0.266~0.771)가 이미 세 카드에 걸쳐 있어 확장 전에도 동일하게 3건이다.

| 패턴 | 종류 | 부분 겹침 |
|------|------|:--------:|
| p1 | cover | 0건 |
| p2 | toc | 0건 |
| p3 | section_lead | **0건** ← 사용자 신고 원본, 해소 |
| p4 | chart_with_notes | 0건 |
| p5 | table | 0건 |
| p6 | section_lead (카드 3장) | **3건** |

**Plan의 SC-2 정의("겹침 0건")가 이 경우를 예상하지 못했다.** Checkpoint 판단으로 SC-2를 "슬롯↔장식이 1:1인 패턴에서 0건"으로 조정하고, p6는 **결함 C(슬롯 분할)로 이월**했다. 같은 페이지가 생성물에서 "카드 3개 전부 빈 상태"로 나온 것도 동일 원인이라 함께 풀어야 한다.

`test_known_limitation_multi_card_pattern_still_overlaps`가 겹침 3건을 고정한다 — 결함 C에서 해소되면 이 테스트가 실패해 이월 항목을 정리하도록 유도한다.

### 5.2 ⚠️ Important — 과적합 리스크 미완화 (미해결)

Plan §5 최상단 리스크의 완화책이 **불가능**으로 판명됐다(설계 §13.1).

- `samples/`의 PPTX 3건은 전부 **우리가 생성한 산출물**
- PPTX 추출 경로는 `render_png=None`(`pptx_style_extractor.py:106`)이라 **비전 분류를 타지 않는다**
- 즉 **비전 좌표 추정 문제를 재현하는 독립 문서가 저장소에 없다**

**확보한 완화 요소**: 골든 6페이지가 cover / toc / section_lead(×2) / chart_with_notes / table **5종 패턴**을 커버하고, 규칙을 문서 특성이 아닌 일반 기하로만 정의했으며(DR-2·4·5·6), 실패 시 폴백(DR-9)이 안전망이다.

**그래도 검증 문서는 1건뿐이다.** 다른 레이아웃(2단 조판, 우측 정렬 제목, 세로 문서 등)에서의 동작은 미지수다.

**권장**: 실사용 PDF 1~2건을 `samples/`에 확보해 후속 사이클에서 교차 확인.

### 5.3 ℹ️ Info — 방어 분기 2줄 미커버

```python
# extraction_use_case.py:314-316
if page is None:
    out.append(pattern)
    continue
```

`sample_page`가 `stats.pages`에 없는 경우의 방어 코드. 설계 §8에 대응 시나리오가 없었고 골든 샘플에서 발생하지 않는다. 커버리지 96%의 원인 중 하나다.

**조치**: 테스트 1건 추가면 해소된다. 우선순위 낮음.

### 5.4 ℹ️ Info — Do 단계에서 제 테스트 단언 오류 2건

구현이 아닌 **테스트가 틀렸던** 사례를 기록해 둔다.

| 테스트 | 오류 | 수정 |
|--------|------|------|
| `test_span_outside_every_slot_is_dropped` | 높이 확장을 고려하지 않고 `y+h`로 검증 | union 원점·폭으로 단언 변경 |
| `test_result_box_stays_inside_slide_bounds` | 픽스처가 `x+w=1.03`이라 `RelBox`가 먼저 거부 | 유효 좌표로 수정 |

---

## 6. 품질 지표

### 6.1 커버리지

| 파일 | 커버리지 | 미커버 |
|------|:--------:|--------|
| `domain/blueprint/policies.py` | 98% | 10줄 — **전부 730행 이전의 기존 `SlotContentPolicy`/`_check_*` 분기.** 신규 `SlotBoxPolicy`(730~868행)는 **100%** |
| `application/blueprint/extraction_use_case.py` | 96% | 7줄 — 그중 **2줄(315-316)이 이번 신규**(§5.3), 나머지 5줄은 기존 |

### 6.2 코딩 규칙 (`idt/CLAUDE.md`)

| 규칙 | 판정 | 확인 |
|------|:----:|------|
| 함수 40줄 이하 | ✅ | AST 검사 — 두 파일 모두 위반 0건 |
| if 중첩 2단계 이하 | ✅ | 최대 2단계 |
| `print()` 금지 | ✅ | 0건 |
| 명시적 타입 | ✅ | 전 함수 시그니처 명시 |
| config 하드코딩 금지 | ✅ | `_SNAP_TEXT_KINDS`·`_SNAP_MIN_SIDE` 모듈 상수, `_FOOTER_BAND_Y` 재사용 |
| domain → infrastructure 참조 금지 | ✅ | `test_layer_contract.py` 5 passed |
| application에 비즈니스 규칙 금지 | ✅ | 기하 규칙은 전부 domain, application은 결선만 |
| ruff lint | ✅ | 변경 5개 파일 All checks passed |
| **변경 파일에만 린트** | ✅ | 디렉토리 전체 `--fix` 미사용 |

### 6.3 추적성

`# Design Ref: blueprint-slot-box-snap DR-N` 주석이 `SlotBoxPolicy` docstring·`_snappable_spans`·`_bottom`·`_encloses`·`_snap_slot_boxes` 결선부에 삽입되어 코드→설계 역추적이 가능하다.

---

## 7. 종합

| 항목 | 결과 |
|------|:----:|
| Match Rate | **98%** (기준 90%) |
| Success Criteria | **6.5/7 (93%)** |
| Decision Record 준수 | **9/9 (100%)** |
| 설계 시나리오 자동화 | **30/30 (100%)** |
| 회귀 | **0건** (297 passed) |
| Critical 이슈 | **0건** |
| Important 이슈 | **2건** (§5.1 다중 카드 한계 / §5.2 과적합 미완화) |

**종합 점수: 94/100**

코드·테스트·문서 정합성에는 결함이 없다. 감점은 전부 **검증 범위의 한계**(단일 문서)와 **Plan이 예상하지 못한 구조적 제약**(다중 카드)에서 온다.

---

## 8. Next Steps

**Checkpoint 5 결정 (2026-08-25): 「그대로 진행」** — Match Rate 98%가 기준(90%)을 충족하고 Critical 0건이므로 수정 없이 report 단계로 진행한다. Important 2건은 코드 결함이 아닌 검증 범위 한계이므로 백로그로 이월한다.

- [x] Checkpoint 5 — 현 상태 수용
- [ ] (백로그) 실사용 PDF 확보 후 과적합 교차 확인 (§5.2)
- [ ] (백로그) `_snap_slot_boxes` 방어 분기 테스트 1건 (§5.3)
- [ ] 완료 보고서 (`/pdca report blueprint-slot-box-snap`)
- [ ] **결함 C 착수** — 다중 카드 슬롯 분할 + 목차·카드 내용 폴백 (§5.1과 결함 C가 동일 원인)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-25 | 최초 작성 — Match Rate 98%, SC 6.5/7, DR 9/9 | 배상규 |
