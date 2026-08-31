# blueprint-render-style-fidelity 완료 보고서

> **Project**: idt (sangplusbot 백엔드)
> **Author**: 배상규
> **Date**: 2026-08-29
> **Phase**: Report (사이클 종료)
> **Match Rate**: **100%** (기준 90%)

---

## 작성 방법 고지

- **report-generator 서브에이전트를 호출하지 않았습니다.** 이 세션은 사용자가 명시 요청하지 않은 에이전트 호출을 금지합니다. 아래는 제가 직접 작성했습니다.
- `templates/report.template.md` 이 플러그인 캐시에 **존재하지 않아** 직전 3개 사이클(`blueprint-font-mapping-migration`·`blueprint-slot-box-snap`·`blueprint-slot-content-fill`)과 동일한 구조를 따랐습니다.

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

## Executive Summary

### 1.1 Project Overview

사용자가 생성된 PPTX에서 신고한 네 번째 결함 — **"4번째 페이지의 표스타일과 %는 표현부분도 각 그래프마다 제대로 안나와 있고 옆에 설명 부분도 자간과 스타일이 그냥 기본으로 적혀져 있습니다"** — 을 해소한 사이클.

원인은 **정보가 없어서가 아니라 렌더러가 쓰지 않아서**였다. `ChartSpec.unit`·`TableStyle.border`는 이미 추출·저장되고 있었는데 소비되는 코드가 없었고, zebra 색과 줄간격은 렌더러에 하드코딩돼 있었다.

### 1.2 Results Summary

| 항목 | 결과 |
|------|:----:|
| Match Rate | **100%** (Structural 100 / Functional 100 / Contract 100 / Runtime 100) |
| Success Criteria | **8 / 8** |
| Decision Record 준수 | **10 / 10** |
| 설계 시나리오 자동화 | **34 / 34** + 보완 2건 |
| 회귀 | **0건** — 381 passed / 0 failed |
| 신규 코드 커버리지 | **100%** (`chart_builder` · `table_borders` · `schemas/blueprint`) |
| Iteration | **0회** (Check 1회로 기준 충족) |

### 1.3 Value Delivered

| 관점 | 전달된 가치 | 근거 |
|------|------------|------|
| **문제 해결** | 사용자 신고 4개 증상이 **기본 산출물에서 전부 해소** | 골든 PDF → 추출 → 렌더 실측: 데이터 레이블·축 % ·표 테두리 모두 존재 |
| **기능** | 렌더러가 소비하지 않던 스타일 정보 4종을 살림 | `unit`·`border`가 처음으로 출력에 도달 |
| **UX 효과** | 신규 추출 블루프린트가 원본 양식을 닮은 상태로 시작 | `_DEFAULT_*` 상수 4개 + `chart_label_size_pt=caption` |
| **핵심 가치** | 렌더러의 하드코딩이 **토큰으로 이동** — 양식마다 다른 값을 가질 수 있게 됨 | `#F3F4F6`·`1.0` 제거, `zebra_bg`·`body_line_spacing` 도입 |

---

## 1.4 Success Criteria Final Status

| SC | 내용 | 상태 | 증거 |
|:--:|------|:----:|------|
| SC-1 | 데이터 레이블 존재, 값 일치 | ✅ | `test_golden_style_applies_chart_labels_and_unit` — `<c:dLbls>`. 레이블은 시리즈 값을 그대로 표시하므로 값 불일치가 구조적으로 불가능 |
| SC-2 | 축 서식에 `%` 반영 | ✅ | `<c:numFmt formatCode="0.0&quot;%&quot;"/>` |
| SC-3 | 표 테두리 존재, 색 일치 | ✅ | `a:lnL` 의 `srgbClr val` == `TableStyle.border` |
| SC-4 | zebra 데이터 2·4행 | ✅ | `test_zebra_paints_second_and_fourth_data_rows_from_token` |
| SC-5 | 문단 줄간격·`space_after` | ✅ | `line_spacing==1.45`, `space_after==33.2pt` |
| SC-6 | v1 스냅샷 수정 없이 로드·렌더 | ✅ | `test_v1_snapshot_loads_with_new_field_defaults` + 6슬라이드 렌더 |
| SC-7 | 설계 시나리오 **전건** 자동화 | ✅ | 34 / 34 |
| SC-8 | 기존 테스트 회귀 0건 | ✅ | 381 passed / 0 failed |

**Success Rate: 8 / 8 (100%)**

### 품질 기준

| 기준 | 상태 | 확인 |
|------|:----:|------|
| 함수 40줄 이하 / if 중첩 2단계 이하 | ✅ | AST 검사, 위반 0건 |
| `print()` 없음, 명시적 타입 | ✅ | 0건 / 전 함수 시그니처 |
| **렌더러에 새 하드코딩 금지** | ✅ | 값은 토큰, 나머지는 명명 상수(`_EMU_PER_POINT`·`_LABEL_POSITIONS`) |
| ruff lint 0건 (변경 파일만) | ✅ | 12개 파일 All checks passed |
| 신규·변경 코드 커버리지 95%+ | ✅ | **100%** |

---

## 1.5 Decision Record Summary

| DR | 결정 | 따랐나 | 결과 |
|:--:|------|:------:|------|
| DR-1 | 기존 VO 평평 확장 (Option C) | ✅ | 신규 파일 1개로 끝. `schema_version` 승격 불필요 — 의도대로 작동 |
| DR-2 | 기본값 = 현행 동작 | ✅ | 구현 1단계부터 회귀 0건. **다만 이 원칙이 §5.1 문제의 한 축이 됨** |
| DR-3 | oxml 은 전용 모듈에 격리 | ✅ | `src/` 내 oxml 사용 파일 2개로 고정, AST 계약으로 강제 |
| DR-4 | `unit` 리터럴 서식 | ✅ | `'0.00"%"'` — `'0.00%'` 였다면 값이 100배로 표시됐다 |
| DR-5 | pie 는 축 대신 레이블 | ✅ | pie 렌더 시 `ValueError` 없음. **이 결정이 설계 §3.2 문구의 오류를 드러냄** |
| DR-6 | 레이블 위치 종류별 매핑 | ✅ | `_LABEL_POSITIONS` |
| DR-7 | 문단 토큰은 비-TOC 불릿만 | ✅ | TOC 1.5·소제목 6pt 보존 |
| DR-8 | `unit` 큰따옴표 제거 | ✅ | LLM 출력이 서식 문자열을 깨뜨리지 못함 |
| DR-9 | `add_chart` 시그니처 `palette`→`style` | ✅ | 호출부 1곳만 수정 |
| DR-10 | ~~`zebra` 추출 기본값 `False` 유지~~ → **v2: 추출이 골든 실측값으로 켠다** | ⚠️ **변경** | **Checkpoint 5에서 뒤집음.** 원안대로면 토큰만 생기고 사용자가 보는 결과는 그대로였다 — §5.3 |

**9/10 준수 + 1건 의도적 변경.**

---

## 2. Related Documents

| 단계 | 문서 |
|------|------|
| Plan | `docs/01-plan/features/blueprint-render-style-fidelity.plan.md` (v0.2) |
| Design | `docs/02-design/features/blueprint-render-style-fidelity.design.md` (v0.2) |
| Analysis | `docs/03-analysis/blueprint-render-style-fidelity.analysis.md` (v0.2) |
| Report | 이 문서 |

**선행 사이클** (같은 사용자 신고에서 파생된 4개 결함 중 A·B·C):

| 결함 | Feature | Match Rate |
|:----:|---------|:----------:|
| A | `blueprint-font-mapping-migration` | 99% |
| B | `blueprint-slot-box-snap` | 98% |
| C | `blueprint-slot-content-fill` | 100% |
| **D** | **`blueprint-render-style-fidelity`** | **100%** |

---

## 3. Completed Items

### 3.1 Functional Requirements

| FR | 내용 | 구현 |
|:--:|------|------|
| FR-01 | 차트 데이터 레이블 | `chart_builder._data_labels` |
| FR-02 | 단위 서식 (축·레이블) | `_number_format` + `_axis_format` |
| FR-03 | 표 셀 테두리 | `table_borders.apply_borders` |
| FR-04 | zebra 색을 토큰에서 | `pptx_renderer._table` → `ts.zebra_bg` |
| FR-05 | 불릿 줄간격·문단 여백 | `pptx_renderer._bullets` |
| FR-06 | 신규 필드 하위호환 | 6개 필드 전부 기본값 + `.get(default)` |
| FR-07 | 값 0 → 현행 동작 | 각 함수 조기 반환 |
| FR-08 | `unit` 주입 방어 | `unit.replace('"', "").strip()` |

### 3.2 Non-Functional Requirements

- **하위호환**: `schema_version` 승격 없이 v1·v2 스냅샷 로드·렌더
- **레이어 격리**: oxml 사용을 2개 파일로 제한, AST 계약 테스트로 강제
- **API 계약**: `StyleSchema`·`TableStyleSchema` 에 선택 필드만 추가 — 기존 클라이언트 무영향
- **프론트 동기화**: 불필요 (스타일 편집 UI 미구현 — §4.2)

### 3.3 Deliverables

```
src   신규 1 (table_borders.py, 45줄) / 수정 6
test  신규 2 (232줄) / 수정 6
────────────────────────────────────────────
사이클 D 순변경: 666 insertions, 24 deletions (수정분)
                + 277줄 (신규 3파일)
```

| 파일 | 성격 |
|------|------|
| `src/infrastructure/blueprint/renderer/table_borders.py` | **신규** — oxml 격리 |
| `src/domain/blueprint/value_objects.py` | `TableStyle` +2, `StyleTokens` +4 |
| `src/domain/blueprint/serialization.py` | 신규 6필드 `.get(default)` |
| `src/infrastructure/blueprint/renderer/chart_builder.py` | 데이터 레이블·단위 서식 |
| `src/infrastructure/blueprint/renderer/pptx_renderer.py` | zebra 토큰화·테두리 호출·문단 여백 |
| `src/interfaces/schemas/blueprint.py` | 선택 필드 6개 |
| `src/application/blueprint/extraction_use_case.py` | **Checkpoint 5** — `_DEFAULT_*` 상수 4개 |

---

## 4. Incomplete Items

### 4.1 다음 사이클 이월

| 항목 | 사유 | 이월 횟수 |
|------|------|:--------:|
| **실사용 PDF 확보 후 과적합 교차 검증** | 골든 샘플 1건에만 맞춰 검증했다. `_DEFAULT_*` 상수 4개는 **이 문서의 실측값**이라 다른 양식에서 어긋날 수 있다 | **4회 연속** (A·B·C·D) |
| 차트 내부 텍스트 폰트 | Plan에서 Out of Scope 명시. 레이블 폰트는 넣었으나 축·범례는 미적용 | 1회 |
| `_snap_slot_boxes` 방어 분기 테스트 1건 | 사이클 B 잔여 | 3회 |

> **⚠️ 4회 연속 이월은 신호다.** 골든 샘플 1건으로 4개 사이클을 검증했고, 이제 그 샘플의 실측값이 **추출 기본값으로 코드에 박혔다**. 두 번째 실사용 PDF를 넣어보기 전까지 이 기본값들이 일반적으로 타당한지 알 수 없다.

### 4.2 이번 범위에서 명시 제외

| 항목 | 사유 |
|------|------|
| **스타일 편집 관리 UI** | 설계 §4.3에서 제외. 그 결과 사용자가 값을 조정할 수단이 없다 — 기본값을 잘 잡는 것으로 대체했다(§5.3) |
| 차트 축·범례 폰트 | Plan Out of Scope |
| 표 셀 개별 스타일 | Plan Out of Scope — 표 전체 단위만 |

### 4.3 취소/보류

없음.

---

## 5. Quality Metrics

### 5.1 최종 분석 결과

| 축 | 점수 | 가중 |
|----|:----:|:----:|
| Structural | 100% | ×0.15 |
| Functional | 100% | ×0.25 |
| Contract | 100% | ×0.25 |
| Runtime | 100% | ×0.35 |
| **Overall** | **100%** | |

### 5.2 Do 단계에서 발생하고 해결한 것

| 이슈 | 원인 | 해결 |
|------|------|------|
| **`StyleSchema` `extra="forbid"` 회귀 8건** | VO에 필드를 추가하면 `blueprint_to_dict`가 그것을 내보내는데 스키마가 거부. **구현 1단계부터 깨져 있었고 제가 회귀 확인에서 `tests/api`를 빼고 돌려 못 봤다** | `TableStyleSchema`·`StyleSchema` 에 선택 필드 추가 |
| 시나리오 7 테스트 누락 | 설계 §11.1에 있었으나 작성 누락 | Do 9단계 시나리오↔테스트 대조에서 발견 후 보완 |
| 테스트 단언 오류 2건 | ① `formatCode`가 python-pptx 캐시 기본값 `General` 과 겹쳐 느슨했다 ② 스타일 비교에서 에셋을 맞추지 않아 도형 수가 달랐다 | 단언을 `<c:numFmt` 로 좁힘 / 베이스라인도 `{}` 에셋으로 통일 |

### 5.3 Check 단계에서 발견하고 해소한 것

**⚠️ 이 사이클의 핵심 사건.** SC 8/8, DR 10/10, 시나리오 34/34 를 전부 통과하고도 **사용자가 보는 결과는 변하지 않은 상태였다.**

기본 추출 값을 실측해서 드러났다:

```
Check 시점 추출 직후:  chart_label_size_pt=0.0   body_line_spacing=1.0
                       body_space_after_pt=0.0   zebra=False   border_width_pt=0.0

기본 산출물:  데이터 레이블 있음 · 축 % 있음 · 표 테두리 없음 · 문단 여백 없음
```

| 사용자 신고 | Check 시점 | 조치 후 |
|------------|:---------:|:------:|
| 막대 위 값 없음 | ✅ | ✅ |
| 축에 % 없음 | ✅ | ✅ |
| **표 테두리 없음** | ❌ | ✅ |
| **문단 여백 없음** | ❌ | ✅ |

**원인은 개별로는 전부 타당한 결정 셋의 합이다.**

```
Checkpoint 2  "상수를 토큰으로 이동"        (추출 실측은 범위 밖)
DR-10         "zebra 추출 기본값 False 유지"
DR-2          "기본값 = 현행 동작"
──────────────────────────────────────────────
합계          기본 산출물이 변하지 않는다
```

**조치**: DR-10 을 v2로 뒤집어 **추출이 골든 실측값으로 스타일을 켜게** 했다. VO 기본값(꺼짐)은 **하위호환용으로 유지** — 기존 저장 블루프린트는 저장된 값을 쓰고, 신규 추출분부터 원본을 닮는다.

**함께 해소한 2건**:

| 항목 | 내용 |
|------|------|
| 설계 §3.2 D-1 가드 조건 | 설계는 `size<=0 → 아무것도 안 함` 이었으나 그러면 `size=0` 인 pie 차트에서 단위를 표시할 수 없어 **DR-5와 모순**. 구현(`size<=0 AND unit 없음`)이 옳아 **문서를 정정** |
| 설계 §3.1 `border_width_pt = 0.75` | 같은 검토에서 발견. DR-2("기본값 = 현행 동작")와 어긋나 `0.0` 으로 정정 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

1. **설계 단계의 API 사전 검증이 리스크 판단을 뒤집었다.** Plan은 "차트 API 한계"를 최대 리스크로 봤는데, 실제로 python-pptx를 두드려 보니 차트는 네이티브 지원이고 **표 테두리에 API가 없었다.** 구현 전에 알았기에 `table_borders.py` 격리 설계가 나왔다.

2. **직전 사이클의 재발 방지 절차가 작동했다.** 사이클 C에서 시나리오 2건이 조용히 누락된 뒤 설계에 넣은 "Do 9단계 시나리오↔테스트 대조"가 이번에 시나리오 7 누락을 잡았다.

3. **Check가 형식 검증에서 멈추지 않았다.** 지표가 전부 만점인 상태에서 "그래서 사용자가 뭘 보는가"를 한 번 더 물은 것이 §5.3을 드러냈다. 이것이 이번 사이클에서 가장 값진 판단이었다.

4. **DR-4(리터럴 서식)가 조용한 버그를 막았다.** `'0.00%'` 로 썼다면 OOXML이 백분율 변환을 해서 1.62가 162%로 표시됐을 것이다. 테스트가 이 함정을 명시적으로 고정했다.

### 6.2 What Needs Improvement (Problem)

1. **성공 기준을 "구현했는가"로 썼지 "사용자가 보는가"로 쓰지 않았다.** SC-1~SC-5가 전부 "토큰을 설정했을 때"를 검증한다. 그래서 8/8 만점과 "사용자 신고 미해소"가 공존할 수 있었다. **이번엔 Check에서 잡았지만, 잡지 못했으면 만점 보고서를 쓰고 결함을 남길 뻔했다.**

2. **회귀 확인 범위를 임의로 좁혔다.** `tests/api` 를 제외하고 돌려서 `extra="forbid"` 파손을 구현 1단계부터 8단계까지 못 봤다. 레이어 간 계약은 정확히 그 경계 테스트에서만 드러난다.

3. **회귀 결과를 확인하기 전에 문서에 수치를 적었다.** 백그라운드 실행에서 `| tail -3` 이 pytest 출력을 잘라내고 파이프라인이 종료코드까지 가렸는데, 그 상태로 "381 passed" 를 먼저 기록했다. 재실행해 수치는 맞았지만 순서가 틀렸다 — **측정 없이 결과를 쓴 것.**

4. **설계 문서에 내부 모순이 2건 있었다.** §3.2 가드 조건이 DR-5와, §3.1 기본값이 DR-2와 각각 어긋났다. 사이클 C에서도 §6.1↔§8.3 모순이 있었으니 **2사이클 연속**이다.

### 6.3 What to Try Next (Try)

1. **SC 작성 규칙: 최소 1건은 "사용자 기본 경로"로 쓴다.** "토큰을 설정하면 X가 나온다"와 별개로 "**아무 설정 없이 기능을 쓰면** 사용자가 X를 본다"를 반드시 포함한다.
2. **회귀는 항상 전체 범위.** 시간이 아까우면 백그라운드로 돌리되 범위는 좁히지 않는다.
3. **파이프라인으로 테스트 결과를 자르지 않는다.** 파일로 받고 종료코드를 별도 확인한 뒤 문서에 적는다.
4. **설계 작성 후 DR↔본문 교차 검증 1회.** 각 DR을 본문에서 되짚어 모순을 찾는다. 2사이클 연속 발생했으므로 절차로 만든다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA 프로세스

| 제안 | 근거 |
|------|------|
| **Plan 단계 SC에 "기본 경로" 항목 의무화** | §5.3 — 만점과 미해소가 공존할 수 있었다 |
| **Design 완료 후 DR↔본문 교차 검증 단계 추가** | C·D 2사이클 연속 설계 내부 모순 |
| Check 단계에 "사용자 기본 경로 실측" 고정 항목 | 이번엔 재량으로 했고, 그래서 잡혔다. 재량에 맡기면 다음엔 놓친다 |

### 7.2 도구/환경

| 항목 | 상태 |
|------|------|
| `report.template.md` **부재** | bkit 2.1.35 캐시에 파일이 없다. plan/design/analysis 템플릿은 있다. 플러그인 이슈로 보고할 만하다 |
| MySQL (포트 3308) | 사이클 A부터 계속 미가동. 저장 경로 검증은 여전히 테스트 대역으로만 확인 |
| 골든 샘플 1건 의존 | 4사이클 연속. 이제 실측값이 코드 상수가 됐으므로 교차 검증 시급도가 올라갔다 |

---

## 8. Next Steps

### 8.1 즉시

- [ ] **사이클 C·D 커밋** — `b70c4b5` 는 A·B만 담고 있어 C와 D가 함께 미커밋 상태다
- [ ] `/pdca archive blueprint-render-style-fidelity`

### 8.2 다음 PDCA 사이클

- [ ] **두 번째 실사용 PDF로 과적합 교차 검증** (4회 연속 이월 — 우선순위 상향)
- [ ] 스타일 편집 관리 UI (백엔드 필드는 준비됨, 프론트 미구현)
- [ ] 차트 축·범례 폰트 (이번 Out of Scope)
- [ ] `_snap_slot_boxes` 방어 분기 테스트 1건 (사이클 B 잔여)

---

## 9. Changelog

### 2026-08-29

**Added**
- `renderer/table_borders.py` — 표 셀 테두리 oxml 조작 (python-pptx 미지원 영역)
- `TableStyle.zebra_bg` / `TableStyle.border_width_pt`
- `StyleTokens.body_line_spacing` / `body_space_after_pt` / `chart_label_size_pt` / `chart_label_bold`
- `chart_builder._data_labels` / `_axis_format` / `_number_format`
- `extraction_use_case._DEFAULT_ZEBRA` 외 3개 — 추출이 골든 실측값으로 스타일을 켠다
- 테스트 41건 (신규 파일 2개 포함)

**Changed**
- `add_chart` 시그니처 `palette` → `style: StyleTokens` (DR-9)
- `_table` 의 zebra 색이 하드코딩 `#F3F4F6` → `ts.zebra_bg`
- `_bullets` 의 줄간격 하드코딩 `1.0` → `style.body_line_spacing`
- `StyleSchema` / `TableStyleSchema` 에 선택 필드 6개

**Fixed**
- `StyleSchema` `extra="forbid"` 가 신규 VO 필드를 거부하던 회귀 (API 테스트 8건)
- 설계 §3.2 D-1 가드 조건이 DR-5와 모순되던 문제 (문서 정정)
- 설계 §3.1 `border_width_pt` 기본값이 DR-2와 어긋나던 문제 (문서 정정)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-29 | 사이클 완료 — Match Rate 100%, SC 8/8, DR 9/10+1변경 | 배상규 |
