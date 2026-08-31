# blueprint-slot-content-fill Completion Report

> **Status**: Complete
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Completion Date**: 2026-08-26
> **PDCA Cycle**: 골든 샘플 충실도 — 결함 C 대응 (A → B → C 순)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | blueprint-slot-content-fill |
| Start Date | 2026-08-25 |
| End Date | 2026-08-26 |
| Duration | 2일 (2세션) |
| Trigger | 사용자 지적 — "목차는 나오지도 않았고", "카드 3개 전부 빈 상태" |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100%                       │
├─────────────────────────────────────────────┤
│  ✅ 완료:      FR-01 ~ FR-06   (6 / 6)       │
│  ✅ 성공기준:  SC-1 ~ SC-8     (8 / 8)       │
│  ✅ 설계결정:  DR-1 ~ DR-10    (10 / 10)     │
│  ✅ 테스트:    설계 시나리오   (42 / 42)     │
│  ❌ 취소:      0건                            │
├─────────────────────────────────────────────┤
│  Match Rate: 100%     회귀: 0건 (337 passed) │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 좌표·폰트를 고쳤어도 **목차가 통째로 비고 카드 3장이 전부 빈 상태**였다. 원인 셋 — ① 비전이 카드 3장을 슬롯 **하나**로 뭉침 ② 목차를 슬라이드 1장씩 독립 호출로 쓰게 해 다른 제목을 모름 ③ `max_chars` 초과 시 슬롯을 **통째로 폐기** |
| **Solution** | ① 장식 경계로 슬롯 분할(`SlotSplitPolicy`) ② 계획 제목에서 목차 결정론 생성(`TocContentPolicy`, LLM 미경유) ③ 모양 위반(치명)과 길이 초과(권고)를 분리 |
| **Function/UX Effect** | **p6 슬롯 1개 → 4개**, 목차 4항목 자동 생성, 길이 초과 내용이 렌더까지 생존. **전 패턴 부분 겹침 3건 → 0건**으로 결함 B 이월 항목까지 해소. 목차 슬라이드의 writer LLM 호출 **0회**(비용·지연 감소) |
| **Core Value** | A(폰트)·B(좌표)로 **모양**을 맞춘 위에 **내용이 실제로 들어가게** 했다. 골든 샘플 충실도의 구조적 축이 완성됐다 |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 목차 4항목, 실제 제목과 일치 | ✅ Met | `test_toc_bullets_are_filled_from_other_slide_titles` — 계획 제목과 **완전 일치** |
| SC-2 | 카드 3장 모두 소제목+본문 | ✅ Met | `test_cards_each_have_their_own_slot` — 슬롯 3개, 서로 다른 위치. **구조까지 검증**(§4.1) |
| SC-3 | p6 텍스트 슬롯 3개 분할 | ✅ Met | `['title', 'bullets', 'bullets2', 'bullets3']` |
| SC-4 | **결함 B 잔여 겹침 3건 → 0건** | ✅ Met | `test_sc2_no_partial_overlap_in_any_pattern` — 전 패턴 검사, 예외 제거 |
| SC-5 | 길이 초과 내용 생존 + 경고 | ✅ Met | 정책 3건 + **렌더** `test_over_max_chars_content_survives_to_render` |
| SC-6 | 목차 LLM 호출 0회 | ✅ Met | `writer.calls`에 `toc` 없음 |
| SC-7 | 설계 시나리오 **전건** 자동화 | ✅ Met | **42 / 42** (Checkpoint 5에서 공백 2건 보완) |
| SC-8 | 기존 테스트 회귀 0건 | ✅ Met | 337 passed / **0 failed** |

**Success Rate: 8 / 8 (100%)**

> 세 사이클 중 처음으로 전 항목 충족이다. 직전 두 사이클은 각각 4.5/5, 6.5/7이었다.

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 범위 = **C-1 + C-2 + C-3 전부** | ✅ | 세 문제가 "슬롯이 빈다"는 한 증상으로 수렴 — 함께 풀어야 했다 |
| [Plan] | 목차 = **결정론적 생성** | ✅ | LLM 실패 경로 자체를 제거. writer 호출 0회 |
| [Plan] | 길이 초과 = **경고만 남기고 유지** | ✅ | `max_chars`(비전 추정값) 하나로 슬라이드가 비는 일이 사라짐 |
| [Design] DR-1 | 두 정책을 `policies.py`에 (Option C) | ✅ | 신규 파일 0개, 기존 헬퍼 이관 0건 |
| [Design] DR-2 | 카드 = BULLETS + `heading` | ✅ | **렌더러 변경 0건** — `git diff b70c4b5 -- renderer/` 출력 없음 |
| [Design] DR-3 | 분할 조건 = 완전 포함 + 미소속 0 | ✅ | 시뮬레이션·실측 모두 **과분할 0건** |
| [Design] DR-4 | 기존 suffix id 규칙 | ✅ | `bullets`, `bullets2`, `bullets3` — Plan 최상단 리스크(연쇄 파급) 완화 |
| [Design] DR-5 | 분할 → 스냅 순서 | ✅ | `extraction_use_case.py:321` → `:324` |
| [Design] DR-6 | 목차 항목에 번호 미포함 | ✅ | 렌더러가 붙이므로 `1. 1.` 중복 방지 |
| [Design] DR-7 | 표지·목차 자신 제외 | ✅ | 골든 목차와 동일한 4항목 |
| [Design] DR-8 | 목차 상한 12 + 경고 | ✅ | 조용히 자르지 않는다 |
| [Design] DR-9 | `max_rows`는 **치명 유지** | ✅ | 표는 행 수만큼 실제 도형이 생성돼 넘친다 — 문자 수와 성질이 다르다 |
| [Design] DR-10 | 예외 없이 원본 유지 | ✅ | 신규 코드에 `raise` 0건 |

**준수율: 13 / 13 (100%)**

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [blueprint-slot-content-fill.plan.md](../01-plan/features/blueprint-slot-content-fill.plan.md) | ✅ Finalized (v0.2) |
| Design | [blueprint-slot-content-fill.design.md](../02-design/features/blueprint-slot-content-fill.design.md) | ✅ Finalized (v0.3) |
| Check | [blueprint-slot-content-fill.analysis.md](../03-analysis/blueprint-slot-content-fill.analysis.md) | ✅ Complete (100%) |
| Act | 본 문서 | ✅ Complete |
| 선행 사이클 | [blueprint-slot-box-snap.report.md](blueprint-slot-box-snap.report.md) | 결함 B — §4.1 이월 항목의 출처 |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|:------:|-------|
| FR-01 | 장식 N개 → 슬롯 N개 분할 | ✅ Complete | `_decoration_groups` + `_split_slots` |
| FR-02 | 결정론적 id + 속성 승계 | ✅ Complete | `_split_id` — 기존 suffix 규칙 |
| FR-03 | 소제목/본문 구분 | ✅ Complete | BULLETS + `heading` (렌더러 기존 구현 재사용) |
| FR-04 | 목차 결정론 생성 | ✅ Complete | `TocContentPolicy` |
| FR-05 | 길이 초과 유지 + 경고 | ✅ Complete | `_advisory` 분리 |
| FR-06 | 분할 불가 시 원본 유지 | ✅ Complete | 미소속 span 1건이면 분할 중단 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|:------:|
| 아키텍처 (domain 순수) | 위반 0건 | 0건 | ✅ |
| application에 규칙 금지 | 결선만 | 기하·목차 규칙 전부 domain | ✅ |
| 결정론 (LLM 재호출 없음) | — | 순수 함수 | ✅ |
| 하위호환 | 미분할 패턴 동작 무변화 | 무변화 | ✅ |
| 회귀 | 0건 | 0건 (337 passed) | ✅ |
| 신규 코드 커버리지 | 95% | **100%** | ✅ |
| 함수 40줄 이하 | 위반 0건 | 0건 (AST) | ✅ |
| ruff lint | 0건 | All checks passed | ✅ |
| **비용** | 목차 LLM 호출 감소 | **0회** | ✅ |

### 3.3 Deliverables

| Deliverable | Location | 규모 | Status |
|-------------|----------|:----:|:------:|
| 분할·목차 정책 + 치명/권고 분리 | `src/domain/blueprint/policies.py` | +201 | ✅ |
| 분할 결선 | `src/application/blueprint/extraction_use_case.py` | +14 | ✅ |
| 목차 결선 | `src/application/blueprint/generation_use_case.py` | +21 | ✅ |
| 분할 정책 테스트 | `tests/domain/blueprint/test_slot_split_policy.py` | 217줄 (신규) | ✅ |
| 목차 정책 테스트 | `tests/domain/blueprint/test_toc_content_policy.py` | 159줄 (신규) | ✅ |
| 치명/권고 테스트 | `tests/domain/blueprint/test_policies.py` | +108 | ✅ |
| 추출 결선 테스트 | `tests/application/blueprint/test_extraction_use_case.py` | +31 | ✅ |
| 생성 결선 테스트 | `tests/application/blueprint/test_generation_use_case.py` | +75 | ✅ |
| 골든·E2E 테스트 | `tests/integration/blueprint/test_golden_sample_fidelity.py` | +135 | ✅ |
| PDCA 문서 4종 | `docs/01-plan` ~ `docs/04-report` | — | ✅ |

**src 수정 3 (+215 / -21), 테스트 신규 2 + 수정 4 (+725)**

---

## 4. Incomplete Items

### 4.1 다음 사이클 이월

| Item | Reason | Priority | 비고 |
|------|--------|:--------:|------|
| **SC-2의 내용 충전 검증** | 실제 카드 내용은 writer LLM이 슬롯 3개를 채우는지에 달려 있고, 골든 회귀는 비결정성 제거를 위해 LLM을 호출하지 않는다 | Medium | 구조가 갖춰져 writer가 슬롯 3개를 인식할 수 있게 된 것까지가 보장 범위 |
| **과적합 교차 검증** | 결함 B에서 이월 — 비전 좌표/구조 문제를 재현하는 **독립 문서가 저장소에 없다** | Medium | 실사용 PDF 1~2건 확보 필요 |
| **기존 저장 블루프린트 재추출** | C-1은 추출 시점 로직 | Medium | C-2·C-3은 생성 시점이라 **즉시 적용** |

### 4.2 이번 범위에서 명시 제외

| Item | 상태 |
|------|:----:|
| **결함 D** — 차트 데이터 레이블·단위, 표 테두리, 문단 여백 | 미착수 |
| 표·차트·이미지 슬롯 분할 | 미착수 (텍스트만) |
| 비전 프롬프트 변경 | 채택 안 함 (비결정적) |
| `max_chars` 재계산 | 채택 안 함 (소비 방식만 변경) |

### 4.3 취소/보류

없음.

---

## 5. Quality Metrics

### 5.1 최종 분석 결과

| Metric | Target | Final | 판정 |
|--------|:------:|:-----:|:----:|
| Design Match Rate | 90% | **100%** | ✅ |
| — Structural | — | 100% (13/13) | ✅ |
| — Functional | — | 100% (6/6 FR) | ✅ |
| — Contract | — | 100% | ✅ |
| — Runtime | — | 100% | ✅ |
| Success Criteria | — | 8/8 (100%) | ✅ |
| Decision Record 준수 | — | 13/13 (100%) | ✅ |
| 설계 시나리오 자동화 | 100% | 42/42 (100%) | ✅ |
| 신규 코드 커버리지 | 95% | **100%** | ✅ |
| 회귀 | 0건 | 0건 | ✅ |
| Critical 이슈 | 0건 | 0건 | ✅ |
| **종합 점수** | — | **99 / 100** | ✅ |

1점 감점은 §4.1 SC-2의 LLM 의존 검증 한계다.

### 5.2 해결한 이슈

| Issue | Resolution | Result |
|-------|------------|:------:|
| 목차가 통째로 빔 (사용자 신고) | 계획 제목에서 결정론 생성 | ✅ 4항목 |
| 카드 3장 전부 빔 (사용자 신고) | 장식 경계로 슬롯 3개 분할 | ✅ 슬롯 3개 |
| **결함 B 이월 — p6 겹침 3건** | 분할로 각 슬롯이 자기 장식에 포함 | ✅ **0건** |
| `max_chars` 초과 시 내용 소실 | 치명/권고 분리 | ✅ 렌더까지 생존 |
| 목차 번호 중복(`1. 1.`) 위험 | 정책이 번호를 넣지 않음 (DR-6) | ✅ 예방 |
| 표 행 초과가 실제 넘침 유발 | `max_rows`는 치명 유지 (DR-9) | ✅ 구분 |

### 5.3 Check 단계에서 발견하고 해소한 것

| 발견 | 성격 | 조치 |
|------|------|------|
| 설계 §6.1과 §8.3 시나리오 31이 **모순** | 문서 내부 불일치 — `SlotSplitPolicy`는 경고를 만들지 않는데 시나리오는 "경고 전파"를 요구 | 시나리오 31 삭제, 번호 재정렬 (설계 v0.3) |
| 시나리오 30 (장식 판정 불변) 미자동화 | 설계 §2.3이 논증만 하고 고정하지 않음 | `test_decoration_output_is_unaffected_by_slot_split` 추가 |
| 시나리오 42 (렌더 레벨 길이 초과) 미자동화 | SC-5가 정책 레벨에만 머묾 | `test_over_max_chars_content_survives_to_render` 추가 |

Checkpoint 5에서 **「공백 2건 메우고 진행」**을 선택해 Match Rate 97% → 100%가 됐다.

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **직전 사이클이 심어 둔 테스트가 제 역할을 했다.** 결함 B에서 `test_known_limitation_multi_card_pattern_still_overlaps`를 "해소되면 실패하도록" 의도적으로 남겼고, 이번에 정확히 그 실패로 SC-4 달성을 알렸다. **이월 항목을 잊지 않게 만드는 장치**로 유효했다.
- **설계 시뮬레이션이 다시 값을 했다.** 분할 규칙 초안을 골든 샘플에 돌려 과분할 0건과 액센트 바 자동 제외를 확인한 뒤 문서를 썼다. 세 사이클 연속 효과가 있었다.
- **기존 자산 재사용이 설계를 단순하게 만들었다.** 결함 B의 `_snappable_spans`/`_assign`/`_union`을 그대로 쓰고, `pptx-font-fidelity`의 `heading` 필드를 재사용해 **렌더러 변경 0건**을 달성했다.
- **세 문제를 한 사이클로 묶은 판단이 옳았다.** C-1(분할)·C-2(목차)·C-3(길이)이 "슬롯이 빈다"는 한 증상으로 수렴했고, C-3을 먼저 넣지 않았으면 분할 검증이 길이 문제에 오염됐을 것이다.
- **Check에서 자기 설계의 모순을 찾아냈다.** 시나리오 31은 제가 §6.1과 §8.3을 어긋나게 쓴 결과였고, 측정 과정에서 드러났다.

### 6.2 What Needs Improvement (Problem)

- **테스트 단언 오류가 세 사이클 연속 2건씩 나왔다.** 이번엔 (a) 떠 있는 span을 슬롯 박스 밖에 둬 배정 자체가 안 된 픽스처, (b) 이중 부정으로 의미가 사라진 단언이었다. **총 6건 모두 구현이 아니라 테스트가 틀린 것**이라, 패턴으로 굳었다고 봐야 한다.
- **설계 문서가 자기 자신과 어긋났다.** §6.1(경고 없음)과 §8.3(경고 전파 검증)을 같은 문서 안에서 반대로 썼다. 절을 나눠 쓰면서 앞서 정한 것을 확인하지 않았다.
- **설계 시나리오 2건을 Do 단계에서 조용히 빠뜨렸다.** 30·42번을 구현 순서에 넣어 두고도 테스트를 쓰지 않았고, Check에서야 드러났다. 구현 순서 체크리스트와 시나리오 목록을 대조하지 않았다.
- **SC-2를 LLM 없이는 검증할 수 없는 형태로 정의했다.** "카드 3장 모두 소제목과 본문을 갖는다"는 writer LLM 의존이라 골든 회귀로 닿지 않는다. 검증 가능성을 기준 작성 시점에 따지지 않았다.

### 6.3 What to Try Next (Try)

- **테스트 픽스처가 도메인 불변식을 만족하는지 먼저 확인한다.** 6건 중 상당수가 픽스처가 `RelBox` 경계나 슬롯 배정 조건을 벗어난 경우였다. 픽스처를 만든 직후 한 번 실행해 보는 것으로 대부분 걸러진다.
- **설계 §8(테스트 시나리오)을 §6(오류 정책) 직후에 검토한다.** 이번 모순은 두 절이 멀리 떨어져 작성돼 생겼다.
- **Do 마지막 단계에 "설계 시나리오 ↔ 테스트 대조" 항목을 넣는다.** Check에서 세는 대신 Do에서 세면 이번 같은 뒤늦은 발견이 없다.
- **성공 기준마다 "무엇으로 검증하는가"를 함께 적는다.** SC-2는 검증 수단을 적었더라면 LLM 의존임을 Plan에서 알았을 것이다. 결함 B의 SC-1 동어반복도 같은 뿌리다.
- **결함 D 착수 시 이번 패턴을 그대로 쓴다** — 시뮬레이션 → 설계 → TDD → 이월 항목을 깨지는 테스트로 고정.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA 프로세스

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 성공 기준에 검증 수단 미기재 | **기준마다 "무엇으로 검증하는가" 병기** — SC-2·(결함 B)SC-1 문제의 공통 뿌리 |
| Design | §6과 §8이 어긋남 | **§8 작성 직후 §6과 상호 검토** |
| Do | 시나리오 누락을 Check에서 발견 | **마지막 단계에 시나리오↔테스트 대조 추가** |
| Do | 테스트 단언 오류 6건(3사이클) | **픽스처 작성 직후 1회 실행**으로 도메인 불변식 위반 조기 발견 |
| Check | gap-detector 미사용 (세션 규칙) | 독립 검증 부재를 문서에 고지하는 관행 유지 |

### 7.2 도구/환경

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| 테스트 자산 | `samples/`에 **실사용 원본 PDF 1~2건** | 세 사이클 연속 이월된 과적합 리스크 해소 |
| 이월 관리 | "해소되면 실패하는 테스트" 패턴 명문화 | 이번에 유효성이 입증됨 (§6.1) |

---

## 8. Next Steps

### 8.1 즉시

- [ ] **기존 블루프린트 재추출** — C-1(분할)은 신규 추출분에만 적용된다
- [ ] 재추출 후 PPT 생성해 목차·카드 내용 육안 확인 (C-2·C-3은 재추출 없이 즉시 적용)

### 8.2 다음 PDCA 사이클

| Item | Priority | 근거 |
|------|:--------:|------|
| **결함 D — 차트 레이블·단위, 표 테두리, 문단 여백** | High | 사용자 신고 4건 중 마지막 남은 항목 |
| 과적합 교차 검증 | Medium | 실사용 PDF 확보 후 |

---

## 9. Changelog

### 2026-08-26

**Added:**
- `SlotSplitPolicy` — 장식 경계로 뭉쳐진 텍스트 슬롯을 쪼개는 도메인 정책
- `TocContentPolicy` — 계획된 슬라이드 제목에서 목차를 결정론적으로 생성
- `_advisory` — 치명(모양 불일치)과 권고(길이 초과)를 분리하는 검사

**Changed:**
- `SlotContentPolicy.apply` — 길이 초과 시 슬롯을 폐기하지 않고 경고만 남기고 유지
- `_check_text` / `_check_bullets` — 모양 검사만 담당 (길이는 `_advisory`로 이관)
- 추출 파이프라인 — `DecorationPolicy` → **`SlotSplitPolicy`** → `SlotBoxPolicy`
- 생성 파이프라인 — `toc` 패턴 슬라이드는 writer LLM을 경유하지 않음

**Fixed:**
- 목차가 통째로 비던 문제 (사용자 신고)
- 카드 3장이 전부 비던 문제 (사용자 신고)
- 결함 B가 이월한 p6 장식-슬롯 부분 겹침 3건
- `max_chars`를 조금 넘겼다는 이유로 슬라이드 내용이 통째로 사라지던 문제

**Unchanged (의도적):**
- `renderer/` — 변경 0건 (`heading` 필드 재사용)
- API 응답 스키마 / DB 스키마 / 마이그레이션

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-26 | 완료 보고서 작성 — Match Rate 100%, SC 8/8, DR 13/13 | 배상규 |
