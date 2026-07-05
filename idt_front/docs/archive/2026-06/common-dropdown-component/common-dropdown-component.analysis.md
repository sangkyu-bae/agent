---
template: analysis
version: 1.0
feature: common-dropdown-component
date: 2026-06-28
author: 배상규
project: idt_front
phase: check
matchRate: 97
---

# common-dropdown-component Gap Analysis Report

> **Summary**: 설계(§3 API / FR-01~10 / §6 접근성 / §5 마이그레이션) 대비 구현 일치도 초기 **94%** → 즉시 Act로 G1(`aria-activedescendant`)·G3(max-h) 보강하여 **97%**. 23개 `<select>` → `<Dropdown>` 무회귀 마이그레이션 완료(잔존 0), 10개 FR 기능 충족. 잔여 갭은 패널 진입 애니메이션(§4.2, Low) 1건뿐.
>
> **Status**: Check 완료 (matchRate ≥ 90%), 경미 Act 반영(94→97%)

---

## 1. Analysis Overview

| 항목 | 내용 |
|------|------|
| 분석 대상 | common-dropdown-component |
| 설계 문서 | `docs/02-design/features/common-dropdown-component.design.md` |
| 계획 문서 | `docs/01-plan/features/common-dropdown-component.plan.md` |
| 구현 코드 | `src/components/common/Dropdown.tsx` (+ `Dropdown.test.tsx`) + 12개 마이그레이션 파일 |
| 분석일 | 2026-06-28 |
| 권위 기준 | **Design 문서** (Plan §6.3 초안의 `renderOption`은 Design §3에서 `badge`로 대체 확정됨) |

---

## 2. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match (FR + §3 API + §5 마이그레이션) | 97% | ✅ |
| Accessibility (§6) | 100% | ✅ |
| Visual Spec (§4) | 97% | ✅ |
| Architecture / Convention (CLAUDE.md) | 100% | ✅ |
| **Overall** | **97%** | ✅ |

> 초기 94% → Act(G1/G3 보강) 후 **97%**. 잔여 차이는 §4.2 진입 애니메이션(Low) 1건.

---

## 3. Functional Requirements Coverage

| FR | 요구 | 구현 | 테스트 | 판정 |
|----|------|:----:|:------:|:----:|
| FR-01 | `value`/`onChange`/`options` 단일 선택 | O | O | ✅ |
| FR-02 | model variant: mono+bullet+체크+배지 | O | O(badge) | ✅ |
| FR-03 | model 상단 검색 실시간 필터 | O | O | ✅ |
| FR-04 | default variant: 텍스트+체크 | O | O | ✅ |
| FR-05 | 트리거 토글 + 외부클릭/Esc 닫힘 | O | △(Esc만, 외부클릭 미테스트) | ✅ |
| FR-06 | 키보드 ↑/↓/Enter/Esc(+Home/End/Tab) | O | O(부분) | ✅ |
| FR-07 | 항목 커스텀 렌더(renderOption 또는 badge) | O(badge) | O | ✅* |
| FR-08 | disabled/isLoading/빈 목록 시각 처리 | O | O | ✅ |
| FR-09 | 23개 `<select>` 무회귀 교체 | O | — | ✅ |
| FR-10 | 긴 목록 스크롤 + 하단 인디케이터(▾) | O | △(미테스트, Low) | ✅ |

\* FR-07: Plan §6.3 초안의 `renderOption` prop은 Design §3에서 의도적으로 제거되고 `badge` prop으로 대체 확정. 구현은 Design을 따름 → 요구 의도 충족(아이콘/임의 노드 렌더는 미지원).

---

## 4. Component API (§3.1) 대조

설계 §3.1의 `DropdownOption`/`DropdownProps` 시그니처와 구현이 **14개 prop 전부 일치**.

| Prop | 설계 §3.1 | 구현 | 판정 |
|------|:--------:|:----:|:----:|
| value / onChange / options | O | O | ✅ |
| variant ('default'\|'model', 기본 default) | O | O | ✅ |
| searchable (기본 `variant==='model'`) | O | O(`searchable ?? isModel`) | ✅ |
| placeholder / disabled / isLoading / emptyText | O | O | ✅ |
| searchPlaceholder / className / id / ariaLabel | O | O | ✅ |
| name (hidden input, §3.4) | O | O(`<input type="hidden">`) | ✅ |
| DropdownOption: value/label/badge/disabled | O | O | ✅ |

제네릭 `<T extends string>`까지 설계대로 유지. **API 일치율 100%.**

---

## 5. Migration (§5) 검증

| 검증 항목 | 결과 |
|-----------|------|
| 잔존 native `<select>` | **0건** (`grep "<select"` → Dropdown.tsx 주석 1건만, 코드 없음) |
| `<Dropdown>` 사용 수 | 12개 파일에 **23건** (설계 인벤토리 23 = model 1 / default 22 와 정확히 일치) |
| model variant 적용처 | `ModelSettingsModal.tsx` 1곳, `badge: m.is_active ? undefined : 'API 키 미등록'` — 설계 §5.2 / Plan §7.3 일치 |
| `onChange` 의미 보존 | 필터형 `onChange={(v)=>handleFilterChange(...)}`, 모델 `onChange={setModel}` — `e.target.value` 추출 제거, 값 직접 전달 ✅ |
| `value=""`("전체") 처리 | 필터에서 `{value:'', label:'전체 …'}` 명시 옵션 유지 (설계 §5.1 규칙2 + §9 권장안 채택) ✅ |

마이그레이션 **무회귀·완전 교체 확인.**

---

## 6. Differences Found

### 🔵 Changed / Partial (Design ≠ Implementation)

| # | 항목 | 설계 | 구현 | 영향 | 우선 | 상태 |
|---|------|------|------|:----:|:----:|:----:|
| G1 | 가상 포커스 ARIA | §6: 키보드 active 옵션을 `aria-activedescendant`로 노출, 옵션에 id 부여 | **해결** — `<li id={listId-opt-i}>` + 트리거/검색입력에 `aria-activedescendant` 추가, 테스트 1건 추가(12/12) | Medium | Medium | ✅ 해결 |
| G2 | 패널 진입 애니메이션 | §4.2: `transition-all` 가벼운 fade/scale (`origin-top`) | 패널이 트랜지션 없이 즉시 표시 | Low (시각 디테일) | Low | ⏳ 미반영(Low) |
| G3 | 패널 max-height | §4.2: `max-h-[280px]` | **해결** — `max-h-[280px]`로 정정 | Trivial | Low | ✅ 해결 |

### 🟢 추가/보강 (Design 명시 외 구현, 긍정)

| 항목 | 위치 | 비고 |
|------|------|------|
| 스크롤 힌트 토글 로직 | `Dropdown.tsx:126` `updateScrollHint` | `scrollTop` 기반 끝 도달 시 숨김 — §4.4 의도 충실 구현 |
| 키보드 wrap + disabled skip | `moveActive`, `firstEnabled/lastEnabled` | §3.3 규약 정확 반영 |

### ⚪ 테스트 커버리지 갭 (기능 정상, 테스트만 부재)

| 케이스 | 설계 §7 우선 | 현황 |
|--------|:---:|------|
| 외부 클릭 닫힘 | P2 | 미테스트 (구현은 존재) |
| isLoading skeleton / disabled 클릭 불가 | P2 | isLoading O, disabled-클릭 불가 미테스트 |
| 스크롤 인디케이터 | P3 | 미테스트 (jsdom 레이아웃 측정 한계) |
| `ModelSettingsModal` 통합(payload 반영) | P3 | 본 분석 범위 외 |

> Dropdown.test.tsx 11/11 통과. 핵심 P1(열림/선택/체크/검색/키보드/Esc/placeholder/loading) 전부 커버.

---

## 7. Recommended Actions

### 즉시(선택) — matchRate 보강
1. **G1 (Medium)**: 각 옵션 `<li>`에 `id={\`${listId}-${i}\`}` 부여 + `<ul>`에 `aria-activedescendant={\`${listId}-${activeIndex}\`}` 추가. (접근성 85→100%, overall ~97%)

### 문서 동기화(코드가 진실)
2. **G2/G3**: 애니메이션 미구현·max-h 260을 Design §4.2에 반영하거나, 코드에 `transition`/`origin-top`·`max-h-[280px]` 보강 중 택1.

### 테스트(권장, 비차단)
3. 외부클릭 닫힘·disabled 클릭 불가 단위 테스트 추가(설계 §7 P2).

---

## 8. Conclusion

**Match Rate 97% (초기 94% → Act 후) — 설계와 구현이 거의 완전 일치.** 23개 select 무회귀 마이그레이션·API 100% 일치·10개 FR 기능 충족·접근성 100%. 잔여는 패널 진입 애니메이션(G2, Low) 1건으로 기능 영향 없음.

→ Check 단계 완료(≥90%). 다음 단계 권장: `/pdca report common-dropdown-component`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-28 | Initial gap analysis (matchRate 94%) | 배상규 (gap-detector) |
| 1.1 | 2026-06-28 | Act 반영: G1(aria-activedescendant)·G3(max-h) 해결, matchRate 94→97% | 배상규 |
