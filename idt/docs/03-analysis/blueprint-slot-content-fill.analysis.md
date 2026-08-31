# blueprint-slot-content-fill Gap Analysis

> **Project**: idt (sangplusbot 백엔드)
> **Author**: 배상규
> **Date**: 2026-08-26
> **Phase**: Check
> **Plan**: [blueprint-slot-content-fill.plan.md](../01-plan/features/blueprint-slot-content-fill.plan.md) (v0.2)
> **Design**: [blueprint-slot-content-fill.design.md](../02-design/features/blueprint-slot-content-fill.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 좌표·폰트를 고쳤어도 목차·카드가 비어 있으면 산출물로 쓸 수 없다 |
| **WHO** | P2 — 골든 샘플로 실제 보고서를 만들려는 KB 운영자 |
| **RISK** | 슬롯 분할이 id를 바꿔 writer 프롬프트·정책에 연쇄 파급 |
| **SUCCESS** | 목차 4항목 채워지고, 카드 3장 모두 소제목+본문 |
| **SCOPE** | 분할(추출) + 목차(생성) + 길이 폴백(정책) |

---

## 0. 분석 방법 고지

**gap-detector 서브에이전트를 호출하지 않았습니다.** 이 세션은 사용자가 명시 요청하지 않은 에이전트 호출을 금지하므로, 아래는 전부 **제가 직접 수행한 정적 검증과 실행 측정**입니다. 독립적인 제3자 검증 관점은 반영되지 않았습니다.

---

## 1. Strategic Alignment

| 질문 | 판정 | 근거 |
|------|:----:|------|
| Plan의 핵심 문제(WHY)를 해결했는가 | ✅ | p6 슬롯 4개로 분할, 목차 4항목 생성, 길이 초과 내용 생존 |
| **결함 B 잔여 항목을 해소했는가** | ✅ | 전 패턴 부분 겹침 **3건 → 0건** |
| 설계 결정(DR-1~10)을 따랐는가 | ✅ | 10/10 — §4 |
| 범위를 넘지 않았는가 | ✅ | **렌더러 변경 0건**(커밋 b70c4b5 이후 diff 없음), 마이그레이션 0건 |

### 1.1 핵심 증거 — 실측

```
SC-3  p6 텍스트 슬롯: ['title', 'bullets', 'bullets2', 'bullets3']
SC-4  전 패턴 부분 겹침: 0건  (직전 사이클 3건)
      패턴별 텍스트 슬롯: p1:2 p2:2 p3:3 p4:2 p5:2 p6:4 → 합계 15 (과분할 0건)
SC-1  목차 항목 4개 (표지·목차 자신 제외), 경고 0건
```

---

## 2. Success Criteria 평가

| SC | 내용 | 판정 | 증거 |
|:--:|------|:----:|------|
| SC-1 | 목차 4항목, 실제 제목과 일치 | ✅ | `test_toc_bullets_are_filled_from_other_slide_titles` — 계획 제목과 **완전 일치** 단언 |
| SC-2 | 카드 3장 모두 소제목+본문 | ✅ | `test_cards_each_have_their_own_slot` — 슬롯 3개, 서로 다른 위치. **단, 실제 내용 충전은 writer LLM 의존이라 구조까지만 검증** |
| SC-3 | p6 텍스트 슬롯 3개 분할 | ✅ | `test_multi_card_pattern_is_split_into_one_slot_per_card` |
| SC-4 | **결함 B 잔여 겹침 3건 → 0건** | ✅ | `test_sc2_no_partial_overlap_in_any_pattern` — 전 패턴 검사, 예외 제거 |
| SC-5 | 길이 초과 내용 생존 + 경고 | ✅ | 정책 레벨 3건 + **렌더 레벨** `test_over_max_chars_content_survives_to_render` |
| SC-6 | 목차 LLM 호출 0회 | ✅ | `test_toc_slide_skips_writer_and_uses_planned_titles` — `writer.calls`에 `toc` 없음 |
| SC-7 | 설계 시나리오 **전건** 자동화 | ✅ | **42 / 42** — Checkpoint 5에서 공백 2건 보완, 모순 1건 삭제 (§5.1·§5.2) |
| SC-8 | 기존 테스트 회귀 0건 | ✅ | 337 passed / **0 failed** |

**Success Rate: 8 / 8 (100%)**

---

## 3. Gap Analysis

### 3.1 Structural Match — 100%

| 설계 명시 항목 | 실제 위치 | 판정 |
|---------------|----------|:----:|
| `SlotSplitPolicy` | `policies.py:893` | ✅ |
| `_split_slots` | `policies.py:927` | ✅ |
| `_decoration_groups` | `policies.py:941` | ✅ |
| `_contains` | `policies.py:956` | ✅ |
| `_split_id` | `policies.py:965` | ✅ |
| `_SPLIT_MIN_GROUPS` | `policies.py:890` | ✅ |
| `TocContentPolicy` | `policies.py:976` | ✅ |
| `_toc_items` | `policies.py:1010` | ✅ |
| `_TOC_MAX_ITEMS` | `policies.py:972` | ✅ |
| `_TOC_EXCLUDED_KINDS` | `policies.py:973` | ✅ |
| `_advisory` | `policies.py:650` | ✅ |
| `_split_and_snap_slots` 결선 | `extraction_use_case.py:303` | ✅ |
| TOC 생성 결선 | `generation_use_case.py:238` | ✅ |

**13/13 = 100%**

### 3.2 Functional Depth — 100%

| FR | 구현 | 판정 |
|:--:|------|:----:|
| FR-01 장식 N개 → 슬롯 N개 | `_decoration_groups` + `_split_slots` | ✅ |
| FR-02 결정론적 id + 속성 승계 | `_split_id` + `replace(slot, ...)` | ✅ |
| FR-03 소제목/본문 구분 | BULLETS + `heading` (DR-2, 렌더러 기존 구현) | ✅ |
| FR-04 목차 결정론 생성 | `TocContentPolicy` + 결선 | ✅ |
| FR-05 길이 초과 유지 + 경고 | `_advisory` 분리 | ✅ |
| FR-06 분할 불가 시 원본 유지 | `_decoration_groups` → `None` | ✅ |

- **Placeholder 0건** (신규 코드 구간 검색)
- **Shallow 파일 0건**

### 3.3 Test Scenario Coverage — 42/42 = 100%

| 계층 | 설계 시나리오 | 자동화 | 판정 |
|------|:------------:|:------:|:----:|
| L1 `SlotSplitPolicy` | 1~12 | 12 (테스트 15건) | ✅ |
| L1 `TocContentPolicy` | 13~20 | 8 (테스트 9건) | ✅ |
| L1 `SlotContentPolicy` | 21~27 | 7 (+ 방어 1건) | ✅ |
| L2 Application | 28~33 | 6 (28 간접, 30 보완) | ✅ |
| L3 Golden | 34~38 | 5 | ✅ |
| L4 Render E2E | 39~42 | 4 (42 보완) | ✅ |

Checkpoint 5 결정에 따라 공백 2건을 보완하고 모순 1건을 삭제해 **전건 자동화**를 달성했다. 경위는 §5.1·§5.2 참조.

### 3.4 API Contract — 100%

설계 §4의 "계약 변경 없음"이 지켜졌다.

- `SlotSchema` 필드 구조 무변경, `slots` 배열 **길이**만 변동
- 관리 API 3개 엔드포인트 응답 스키마 무변경
- `idt_front` 타입 동기화 불필요

### 3.5 Runtime — 100%

```
337 passed, 1 deselected, 0 failed   (blueprint 관련 전체)
```

실행 실패 0건, 시나리오 공백 0건.

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

| DR | 결정 | 준수 | 검증 방법 |
|:--:|------|:----:|----------|
| DR-1 | 두 정책을 `policies.py`에 배치 | ✅ | 신규 파일 0개 |
| DR-2 | 카드 = BULLETS + `heading`, **렌더러 변경 0** | ✅ | `git diff b70c4b5 -- renderer/` **출력 없음** |
| DR-3 | 분할 조건 = 완전 포함 + 미소속 0 | ✅ | `_decoration_groups`가 미소속 시 `None` |
| DR-4 | 기존 suffix id 규칙 | ✅ | `_split_id` — `bullets`, `bullets2`, `bullets3` |
| DR-5 | 분할 → 스냅 순서 | ✅ | `extraction_use_case.py:321` → `:324` |
| DR-6 | 목차 항목에 번호 미포함 | ✅ | `_toc_items`가 `p.title.strip()` 그대로. `test_toc_rendered_numbers_are_not_duplicated` |
| DR-7 | 표지·목차 자신 제외 | ✅ | `_TOC_EXCLUDED_KINDS` |
| DR-8 | 목차 상한 12 + 경고 | ✅ | `test_items_over_cap_are_truncated_with_warning` |
| DR-9 | `max_rows`는 치명 유지 | ✅ | `test_table_over_max_rows_stays_fatal` |
| DR-10 | 예외 없이 원본 유지 | ✅ | 신규 코드에 `raise` **0건** |

**10/10 = 100%**

---

## 5. 발견 사항

### 5.1 ✅ 해소 — 설계 §8.3 시나리오 31이 구현과 모순이었다 (설계 결함)

설계가 **자기 자신과 어긋나 있었다.**

| 설계 절 | 내용 |
|--------|------|
| §6.1 오류 정책 | 분할 실패 3가지 상황(장식 그룹 1개 이하 / 미소속 span / 장식 없음) 모두 **경고 ✕** |
| §8.3 시나리오 31 | "분할 경고 전파 — `blueprint.warnings`에 누적" |

`SlotSplitPolicy.apply`는 **모든 반환 경로에서 `()` 를 돌려준다**(경고를 만들지 않는다). §6.1을 따른 결과다. 따라서 시나리오 31은 **검증할 대상이 존재하지 않는다.**

**판정**: 구현 결함이 아니라 **설계 문서의 내부 불일치**다. 결선부는 `split_warnings`를 전파하도록 되어 있어 향후 경고가 추가되면 그대로 동작한다.

**조치 (완료)**: Checkpoint 5 결정에 따라 설계 §8.3에서 시나리오 31을 **삭제**하고 이후 번호를 재정렬했다(설계 v0.3). §6.1에 경고를 추가하는 대안은 정상 케이스마다 경고가 발생해 채택하지 않았다. 결선부는 `split_warnings`를 전파하도록 되어 있어 향후 경고가 추가되면 그대로 동작한다.

### 5.2 ✅ 해소 — 자동화 공백 2건이었다

| # | 시나리오 | 상태 | 영향 |
|:-:|----------|------|------|
| 30 | 장식 판정이 분할 전후로 동일 | **보완 완료** | 설계 §2.3이 논증만 하고 고정하는 테스트가 없었다. `_CONTENT_SLOT_KINDS`에 텍스트 종류가 추가되면 조용히 깨질 수 있었다 |
| 42 | 길이 초과 내용이 **렌더에** 살아남음 | **보완 완료** | 정책 레벨(시나리오 21·22)만 검증돼 SC-5의 실질 검증이 아니었다 |

**조치 (완료)**: Checkpoint 5 결정에 따라 테스트 2건을 추가했다.

| 시나리오 | 추가한 테스트 | 검증 내용 |
|:--:|------|------|
| 30 | `test_decoration_output_is_unaffected_by_slot_split` | 최종(분할된) 패턴으로 `DecorationPolicy`를 재계산해도 저장된 장식과 동일 |
| 42 | `test_over_max_chars_content_survives_to_render` | `max_chars+50`자 불릿이 정책을 통과하고 **렌더 결과에 실제로 존재** |

시나리오 28(분할→스냅 순서)은 골든 통합 테스트가 실제 파이프라인을 통과하므로 **간접 검증**됐다 — 순서가 뒤집혔다면 분할 자체가 일어나지 않는다.

### 5.3 ℹ️ Info — SC-2의 검증 한계

SC-2("카드 3장 모두 소제목과 본문을 갖는다")는 **슬롯 구조까지만** 검증했다. 실제 내용 충전은 writer LLM이 각 슬롯을 채우는지에 달려 있고, 골든 회귀는 LLM을 호출하지 않는다(비결정성 제거).

구조가 갖춰졌으므로 writer가 슬롯 3개를 인식하고 채울 수 있게 됐다는 것까지가 이번 사이클의 보장 범위다.

### 5.4 ℹ️ Info — Do 단계 테스트 단언 오류 2건

구현이 아닌 **테스트가 틀렸던** 사례.

| 테스트 | 오류 | 수정 |
|--------|------|------|
| `test_unassigned_span_blocks_split` | 떠 있는 span을 슬롯 박스 **밖**에 두어 배정 자체가 안 됨 | 슬롯 안·장식 밖 좌표로 이동 |
| `test_toc_bullets_are_filled_from_other_slide_titles` | 이중 부정으로 의미가 사라진 단언 | 계획 제목과의 완전 일치 단언으로 교체 |

직전 두 사이클에서도 각 2건씩 발생했다 — §6.2 참조.

---

## 6. 품질 지표

### 6.1 커버리지

| 파일 | 커버리지 | 미커버 |
|------|:--------:|--------|
| `domain/blueprint/policies.py` | 98% | 8줄 — **전부 893행 이전의 기존 코드.** 신규 `SlotSplitPolicy`·`TocContentPolicy`(893~1030행)는 **100%** |
| `application/blueprint/generation_use_case.py` | 99% | 1줄 (`_has_renderable`, 기존) |

Do 단계에서 `_advisory` 방어 분기 1줄이 미커버로 남아 테스트를 추가해 덮었다.

### 6.2 코딩 규칙 (`idt/CLAUDE.md`)

| 규칙 | 판정 | 확인 |
|------|:----:|------|
| 함수 40줄 이하 | ✅ | AST 검사 — 3개 파일 전부 위반 0건 |
| if 중첩 2단계 이하 | ✅ | 최대 2단계 |
| `print()` 금지 | ✅ | 0건 |
| 명시적 타입 | ✅ | 전 함수 시그니처 명시 |
| config 하드코딩 금지 | ✅ | `_SPLIT_MIN_GROUPS`·`_TOC_MAX_ITEMS`·`_TOC_EXCLUDED_KINDS` 상수 |
| domain → infrastructure 금지 | ✅ | `test_layer_contract.py` 통과 |
| application에 규칙 금지 | ✅ | 기하·목차 규칙 전부 domain, application은 결선만 |
| ruff lint | ✅ | 변경 8개 파일 All checks passed |
| **변경 파일에만 린트** | ✅ | 디렉토리 전체 `--fix` 미사용 |

### 6.3 변경 규모

```
src   3 파일  +215 / -21   (policies +201, extraction +14, generation +21)
test  5 파일  +294 + 신규 2 파일
```

---

## 7. 종합

| 항목 | 결과 |
|------|:----:|
| Match Rate | **100%** (기준 90%) |
| Success Criteria | **8/8 (100%)** |
| Decision Record 준수 | **10/10 (100%)** |
| 설계 시나리오 자동화 | **42/42 (100%)** |
| 회귀 | **0건** (337 passed) |
| Critical 이슈 | **0건** |
| Important 이슈 | **0건** — 2건 모두 Checkpoint 5에서 해소 |

**종합 점수: 99/100**

**결함 B가 이월한 항목을 완전히 해소한 것**이 이번 사이클의 가장 큰 성과다(겹침 3건 → 0건). Check 단계에서 발견한 설계 모순 1건과 테스트 공백 2건은 Checkpoint 5 결정에 따라 모두 해소했다. 남은 1점은 §5.3(SC-2의 LLM 의존 검증 한계)이다.

---

## 8. Next Steps

**Checkpoint 5 결정 (2026-08-26): 「공백 2건 메우고 진행」** — 시나리오 30·42 테스트를 추가하고 설계 §8.3의 모순 시나리오 31을 삭제했다. 그 결과 Match Rate 97% → **100%**, SC 7.5/8 → **8/8**.

- [x] Checkpoint 5 — 공백 보완 완료
- [x] 설계 §8.3 시나리오 31 삭제 (설계 v0.3)
- [x] 시나리오 30·42 테스트 추가
- [ ] 완료 보고서 (`/pdca report blueprint-slot-content-fill`)
- [ ] **결함 D 착수** — 차트 데이터 레이블·단위, 표 테두리, 문단 여백

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-26 | 최초 작성 — Match Rate 97%, SC 7.5/8, DR 10/10 | 배상규 |
| 0.2 | 2026-08-26 | Checkpoint 5 반영 — 공백 2건 보완, 모순 1건 삭제 → 100% / 8/8 | 배상규 |
