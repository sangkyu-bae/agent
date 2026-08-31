# blueprint-render-style-fidelity Gap Analysis

> **Project**: idt (sangplusbot 백엔드)
> **Author**: 배상규
> **Date**: 2026-08-29
> **Phase**: Check
> **Plan**: [blueprint-render-style-fidelity.plan.md](../01-plan/features/blueprint-render-style-fidelity.plan.md) (v0.2)
> **Design**: [blueprint-render-style-fidelity.design.md](../02-design/features/blueprint-render-style-fidelity.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 스타일 정보가 이미 있는데 렌더러가 쓰지 않아 산출물이 밋밋하다 |
| **WHO** | P2 — 골든 샘플로 자사 양식의 보고서를 만들려는 KB 운영자 |
| **RISK** | 표 테두리 oxml 조작 (설계 사전검증에서 차트→표로 이동) |
| **SUCCESS** | 데이터 레이블·축 %·표 테두리·문단 여백이 렌더 결과에 존재 |
| **SCOPE** | 렌더러 4개 항목 + 하드코딩 상수의 토큰화 |

---

## 0. 분석 방법 고지

**gap-detector 서브에이전트를 호출하지 않았습니다.** 이 세션은 사용자가 명시 요청하지 않은 에이전트 호출을 금지하므로, 아래는 전부 **제가 직접 수행한 정적 검증과 실행 측정**입니다.

---

## 1. Strategic Alignment

| 질문 | 판정 | 근거 |
|------|:----:|------|
| 네 항목이 렌더러에서 실제로 소비되는가 | ✅ | 토큰을 켜면 4개 전부 렌더 결과에 나타남 |
| 하드코딩 상수가 토큰으로 이동했는가 | ✅ | `#F3F4F6` → `ts.zebra_bg`, `spacing=1.0` → `style.body_line_spacing` |
| 하위호환이 유지되는가 | ✅ | v1 스냅샷 수정 없이 로드·렌더, 회귀 0건 |
| 설계 결정(DR-1~10)을 따랐는가 | ✅ | 10/10 — §4 |
| **사용자 신고 증상이 기본 산출물에서 해소됐는가** | ✅ | Checkpoint 5에서 추출 기본값을 골든 실측값으로 전환 → **4건 전부 해소** (§5.1) |

---

## 2. Success Criteria 평가

| SC | 내용 | 판정 | 증거 |
|:--:|------|:----:|------|
| SC-1 | 데이터 레이블 존재, 값 일치 | ✅ | `test_golden_style_applies_chart_labels_and_unit` — `<c:dLbls>` 존재. 레이블은 시리즈 값을 그대로 표시하므로 값 불일치가 구조적으로 불가능 |
| SC-2 | 축 서식에 `%` 반영 | ✅ | `<c:numFmt formatCode="0.0&quot;%&quot;"/>` |
| SC-3 | 표 테두리 존재, 색 일치 | ✅ | `a:lnL` 의 `srgbClr val` 이 `TableStyle.border` 와 일치 |
| SC-4 | zebra 데이터 2·4행 | ✅ | `test_zebra_paints_second_and_fourth_data_rows_from_token` |
| SC-5 | 문단 줄간격·`space_after` | ✅ | `line_spacing==1.45`, `space_after==33.2pt` |
| SC-6 | v1 스냅샷 수정 없이 로드·렌더 | ✅ | `test_v1_snapshot_loads_with_new_field_defaults` + 렌더 6슬라이드 |
| SC-7 | 설계 시나리오 **전건** 자동화 | ✅ | **34 / 34** — §3.3 |
| SC-8 | 기존 테스트 회귀 0건 | ✅ | **381 passed / 0 failed** (Checkpoint 5 조치 후 재실행) |

**Success Rate: 8 / 8 (100%)**

> **다만 성공 기준 자체가 "토큰을 켰을 때"만 검증한다.** 기본 산출물에서 사용자가 무엇을 보는지는 어느 SC도 묻지 않았다. Check에서 이를 발견해 Checkpoint 5에서 조치했다 — §5.1.

---

## 3. Gap Analysis

### 3.1 Structural Match — 100%

| 설계 §11.1 명시 항목 | 실제 | 판정 |
|---------------------|------|:----:|
| `renderer/table_borders.py` (신규) | 존재 (45줄) | ✅ |
| `apply_borders` / `_set_cell_borders` / `_replace_line` | `table_borders.py` | ✅ |
| `_data_labels` / `_axis_format` / `_number_format` | `chart_builder.py` | ✅ |
| `_LABEL_POSITIONS` / `_AXIS_KINDS` | `chart_builder.py` | ✅ |
| `TableStyle` +2 (`zebra_bg`, `border_width_pt`) | `value_objects.py` | ✅ |
| `StyleTokens` +4 | `value_objects.py` | ✅ |
| `serialization._style` `.get(default)` | 6개 필드 | ✅ |
| `StyleSchema`·`TableStyleSchema` 선택 필드 | `schemas/blueprint.py` | ✅ |

**전 항목 존재 = 100%**

### 3.2 Functional Depth — 100%

| FR | 구현 | 판정 |
|:--:|------|:----:|
| FR-01 데이터 레이블 | `_data_labels` | ✅ (설계 문구를 구현에 맞게 정정 — §5.2) |
| FR-02 단위 서식 | `_number_format` + `_axis_format` | ✅ |
| FR-03 표 테두리 | `apply_borders` | ✅ |
| FR-04 zebra 토큰 | `ts.zebra_bg` | ✅ |
| FR-05 문단 줄간격·여백 | `_bullets` | ✅ |
| FR-06 기본값 하위호환 | 전 필드 기본값 보유 | ✅ |
| FR-07 값 0 → 현행 유지 | 각 함수 조기 반환 | ✅ |
| FR-08 `unit` 주입 방어 | `unit.replace('"', "")` | ✅ |

- **Placeholder 0건**
- 설계-구현 불일치는 Checkpoint 5에서 **설계 문서 정정**으로 해소 (§5.2)

### 3.3 Test Scenario Coverage — 34/34 = 100%

| 계층 | 시나리오 | 매칭 테스트 | 판정 |
|------|:--------:|:----------:|:----:|
| L1 VO | 1~3 | 4 | ✅ |
| L1 직렬화 | 4~6 | 4 | ✅ |
| L1 API 스키마 | 7 | 2 | ✅ |
| L2 차트 | 8~14 | 10 | ✅ |
| L2 표 테두리 | 15~16 | 5 | ✅ |
| L2 표·문단 | 17~25 | 8 | ✅ |
| L3 골든 | 26~32 | 6 | ✅ |
| L4 아키텍처 | 33~34 | 2 | ✅ |

**시나리오 7은 Do 9단계 대조에서 누락을 발견해 보완했다** — 직전 사이클의 재발 방지 절차가 작동했다.

### 3.4 API Contract — 100%

- `StyleSchema`·`TableStyleSchema`에 **선택 필드만** 추가, 구조 무변경
- `interfaces/schemas/blueprint.py` 커버리지 **100%**
- 기존 클라이언트가 신규 필드 없이 보내도 기본값 수용 (`test_style_schema_accepts_payload_without_new_fields`)
- `idt_front` 타입 동기화 불필요 (편집 UI 미구현)

### 3.5 Runtime — 100%

```
381 passed, 1 deselected, 0 failed   (blueprint 관련 전체, tests/api 포함)
```

실행 실패 0건, 미커버 0줄 (§5.3 보완 완료).

### 3.6 Match Rate

```
Overall = 100×0.15 + 100×0.25 + 100×0.25 + 100×0.35
        = 15 + 25 + 25 + 35
        = 100%
```

| 축 | 점수 |
|----|:----:|
| Structural | 100% |
| Functional | 100% |
| Contract | 100% |
| Runtime | 100% |
| **Overall** | **100%** |

---

## 4. Decision Record 준수 검증

| DR | 결정 | 준수 | 검증 |
|:--:|------|:----:|------|
| DR-1 | 기존 VO 평평 확장 (Option C) | ✅ | 신규 파일 1개(`table_borders.py`)뿐, 중첩 VO 없음 |
| DR-2 | 기본값 = 현행 동작 | ✅ | `zebra_bg=#F3F4F6`, `border_width_pt=0.0` 실측. **구현 1단계에서 회귀 0건** |
| DR-3 | oxml 은 전용 모듈에 격리 | ✅ | `src/` 내 `pptx.oxml` 사용 파일이 `run_fonts.py`·`table_borders.py` **둘뿐** — AST 계약으로 고정 |
| DR-4 | `unit` 리터럴 서식 | ✅ | `chart_builder.py:115` `f'{base}"{safe}"'` — `formatCode="0.00&quot;%&quot;"` 확인 |
| DR-5 | pie 는 축 대신 레이블 | ✅ | `_AXIS_KINDS = ("bar", "line")` — pie 렌더 시 `ValueError` 없음 |
| DR-6 | 레이블 위치 종류별 매핑 | ✅ | `_LABEL_POSITIONS` |
| DR-7 | 문단 토큰은 비-TOC 불릿만 | ✅ | `pptx_renderer.py:309`. TOC 1.5·소제목 6pt 유지 확인 |
| DR-8 | `unit` 큰따옴표 제거 | ✅ | `chart_builder.py:112` |
| DR-9 | `add_chart` 시그니처 `palette`→`style` | ✅ | `chart_builder.py:53` |
| DR-10 | ~~`zebra` 추출 기본값 `False`~~ → **v2: 추출이 골든 실측값으로 켠다** | ✅ | Checkpoint 5에서 결정 변경(§5.1). `extraction_use_case` 의 `_DEFAULT_*` 상수 5개, `test_extraction_enables_render_style_with_golden_defaults` 로 고정 |

**10/10 = 100%**

---

## 5. 발견 사항

### 5.1 ✅ 해소 — 기본 산출물에서 사용자 신고 증상 2건이 남아 있었다

**Check 시점의 이번 사이클은 "능력"을 만들었지만 "변화"를 만들지 않았다.** 추출 직후 값을 실측한 결과다.

```
추출 직후:  chart_label_size_pt=0.0   body_line_spacing=1.0
            body_space_after_pt=0.0   zebra=False   border_width_pt=0.0
```

그 상태로 렌더한 결과:

| 사용자 신고 | 기본 산출물 | 이유 |
|------------|:----------:|------|
| 막대 위 값 없음 | ✅ **해소** | `unit`이 레이블을 트리거한다(§5.2) |
| 축에 % 없음 | ✅ **해소** | `ChartSpec.unit` 이 살아났다 |
| **표 테두리 없음** | ❌ **미해소** | `border_width_pt=0.0` 기본값이 막는다 |
| **설명 문단 여백 없음** | ❌ **미해소** | `body_space_after_pt=0.0` 기본값이 막는다 |

**원인은 결정의 연쇄다.** Checkpoint 2에서 "상수를 토큰으로 이동"(추출 실측 제외)을 택했고, DR-10이 `zebra=False` 유지를 정했으며, DR-2가 "기본값 = 현행 동작"을 원칙으로 삼았다. 셋 다 각각 타당하지만 **합쳐지면 기본 산출물이 변하지 않는다.**

**게다가 값을 켤 수단이 현재 없다.** 관리 UI에 편집 필드를 만들지 않았고(설계 §4.3), 추출도 기본값만 넣는다.

**Plan·Design·SC 어디에서도 이 결과를 묻지 않았다.** SC-1~SC-5가 전부 "토큰을 설정했을 때"를 검증한다. 성공 기준을 그렇게 쓴 것이 이번 사이클의 설계 결함이다 — 조치로 결과는 해소했지만 **교훈은 남는다**(§7).

**조치 (완료)** — Checkpoint 5에서 **A안(추출 기본값을 골든 실측값으로)** 을 선택했다. DR-10을 v2로 변경하고 `extraction_use_case`에 실측 상수를 넣었다.

```
추출 직후 (변경 후):  chart_label_size_pt=9.0   body_line_spacing=1.45
                      body_space_after_pt=33.2  zebra=True  border_width_pt=0.75

기본 산출물:          데이터 레이블 있음 · 축 단위 서식 있음 · 표 테두리 있음
```

| 사용자 신고 | 변경 전 | 변경 후 |
|------------|:------:|:------:|
| 막대 위 값 없음 | ✅ | ✅ |
| 축에 % 없음 | ✅ | ✅ |
| 표 테두리 없음 | ❌ | ✅ |
| 문단 여백 없음 | ❌ | ✅ |

**핵심 구분**: VO 기본값(꺼짐)은 **하위호환용**으로 그대로 두고, **추출만** 켠 값을 넣는다. 기존 저장 블루프린트는 저장된 값을 유지하고, 신규 추출분부터 원본을 닮는다. `test_extraction_enables_render_style_with_golden_defaults` 가 이를 고정한다.

### 5.2 ✅ 해소 — 설계 §3.2와 구현의 가드 조건이 달랐다

| | 조건 |
|---|------|
| 설계 §3.2 D-1 | `chart_label_size_pt <= 0` → **아무것도 하지 않는다** |
| 구현 `_data_labels` | `size <= 0` **AND** `unit_format is None` → 아무것도 하지 않는다 |

즉 **크기가 0이어도 `unit`이 있으면 레이블이 생긴다.**

**구현 쪽이 맞다.** DR-5가 "pie 는 축이 없으니 레이블에 단위를 적용한다"고 정했는데, 설계 문구대로면 `chart_label_size_pt=0`인 pie 차트에서 단위를 표시할 방법이 없다. 설계 §3.2 문구가 DR-5와 모순됐다.

**부수 효과**: §5.1에서 데이터 레이블이 기본 산출물에 나타난 이유가 이것이다 — 골든 `_slides()`의 `unit="%"`가 레이블을 트리거했다. 의도한 동작이지만 설계에 기술되지 않았다.

**조치 (완료)**: 설계 §3.2 D-1의 가드 조건을 `chart_label_size_pt <= 0 AND unit 없음` 으로 정정했다(설계 v0.2). 같은 검토에서 **§3.1 코드 블록의 `border_width_pt = 0.75` 도 DR-2와 어긋남**을 발견해 `0.0` 으로 정정했다 — VO 기본값은 꺼짐이고 켜는 것은 추출의 몫이다.

### 5.3 ✅ 해소 — 방어 분기 1줄 미커버였다

```python
# chart_builder.py:114
safe = unit.replace('"', "").strip()
if not safe:
    return None      # ← 미커버: unit 이 따옴표·공백뿐인 경우
```

시나리오 12가 `unit='크"기'`(제거 후 `크기`)를 검증하지만, 제거 후 빈 문자열이 되는 경우는 설계 시나리오에 없었다.

**조치 (완료)**: `test_unit_made_only_of_quotes_leaves_format_unset` 추가 → `chart_builder.py` 커버리지 **100%**.

### 5.4 ℹ️ Info — Do 단계에서 제가 놓쳤다가 잡은 것

| 항목 | 경위 |
|------|------|
| **`StyleSchema` `extra="forbid"` 회귀** | VO에 필드를 추가하면 `blueprint_to_dict`가 그것을 내보내는데 스키마가 거부한다. **구현 1단계 이후 계속 깨져 있었고, 제가 회귀 확인에서 `tests/api`를 뺀 채로 돌려 못 봤다.** 시나리오 7 테스트를 쓸 때 8건 실패로 드러났다 |
| **시나리오 7 누락** | 설계 §11.1에 있었는데 테스트를 쓰지 않았다. Do 9단계의 시나리오↔테스트 대조에서 발견 |
| 테스트 단언 오류 2건 | `formatCode`가 python-pptx 캐시 기본값과 겹쳐 느슨했던 것 / 스타일 비교에서 에셋을 안 맞춰 도형 수가 달랐던 것 |

**교훈**: 회귀 확인은 항상 `tests/api`를 포함한 전체 범위로 돌려야 한다. 범위를 좁히면 레이어 간 계약 파괴가 숨는다.

---

## 6. 품질 지표

### 6.1 커버리지

| 파일 | 커버리지 | 미커버 |
|------|:--------:|--------|
| `renderer/table_borders.py` | **100%** | 0줄 |
| `interfaces/schemas/blueprint.py` | **100%** | 0줄 |
| `renderer/chart_builder.py` | 99% | 1줄 (114 — §5.3) |

### 6.2 코딩 규칙 (`idt/CLAUDE.md`)

| 규칙 | 판정 | 확인 |
|------|:----:|------|
| 함수 40줄 이하 | ✅ | AST 검사 — 4개 파일 위반 0건 |
| if 중첩 2단계 이하 | ✅ | 최대 2단계 |
| `print()` 금지 | ✅ | 0건 |
| 명시적 타입 | ✅ | 전 함수 시그니처 |
| **렌더러에 새 하드코딩 금지** | ✅ | `#F3F4F6`·`1.0` 제거, 신규 상수는 `_LABEL_POSITIONS`·`_EMU_PER_POINT` 등 명명 상수 |
| oxml 격리 | ✅ | AST 계약 테스트 통과 |
| ruff lint | ✅ | 변경 15개 파일 All checks passed |
| **변경 파일에만 린트** | ✅ | 중간에 `src/` 전체를 린트해 2385건이 나왔으나 **수정하지 않고** 변경 파일 범위로 되돌림 |

### 6.3 변경 규모

```
src   신규 1 / 수정 6
test  신규 2 / 수정 6
```

---

## 7. 종합

| 항목 | 결과 |
|------|:----:|
| Match Rate | **100%** (기준 90%) |
| Success Criteria | **8/8 (100%)** |
| Decision Record 준수 | **10/10 (100%)** |
| 설계 시나리오 자동화 | **34/34 (100%)** + 보완 2건 |
| 회귀 | **0건** (379 passed) |
| Critical 이슈 | **0건** |
| Important 이슈 | **0건** — 2건 모두 Checkpoint 5에서 해소 |

**종합 점수: 98/100**

코드 품질·테스트·하위호환에 결함이 없고, Check에서 드러난 Important 2건도 Checkpoint 5에서 해소했다.

남은 2점은 **성공 기준이 사용자가 실제로 보는 결과를 묻지 않았다는 사실 자체**다. §5.1은 결과적으로 해소됐지만, Plan 단계에서 "기본 산출물에서 무엇이 보이는가"를 SC로 세웠다면 Do 단계에서 잡혔을 문제다. 이 교훈은 보고서 §6에 남긴다.

---

## 8. Next Steps

**Checkpoint 5 결정 (2026-08-29): 「추출 기본값을 골든 실측값으로」 + 「나머지 2건 지금 처리」** — Match Rate 98% → **100%**, Important 2건 → 0건.

- [x] Checkpoint 5 — 추출 기본값 전환 (DR-10 v2)
- [x] 설계 §3.2 D-1 가드 조건 정정 + §3.1 `border_width_pt` 정정 (설계 v0.2)
- [x] `chart_builder.py:114` 방어 분기 테스트 추가 → 커버리지 100%
- [ ] 완료 보고서 (`/pdca report blueprint-render-style-fidelity`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-29 | 최초 작성 — Match Rate 98%, SC 8/8, DR 10/10 | 배상규 |
| 0.2 | 2026-08-29 | Checkpoint 5 반영 — 추출 기본값 전환, 설계 정정 2건, 방어 테스트 → 100% | 배상규 |
