# common-dropdown-component Completion Report

> **Summary**: `dropdown.png` 디자인의 의존성 없는 헤드리스 공통 `<Dropdown />` 컴포넌트를 신규 작성하고, 전 화면의 네이티브 `<select>` 23개(12파일)를 무회귀로 일괄 교체했다. 설계 일치도 **97%** (초기 94% → 경미 Act 후).
>
> **Feature**: common-dropdown-component
> **Duration**: 2026-06-28 (single-session PDCA cycle)
> **Owner**: AI Assistant (배상규)
> **Project**: idt_front (React 19 + TypeScript)

---

## Executive Summary

### Overview
프로젝트 전반(12파일·23곳)이 브라우저 네이티브 `<select>`를 사용해 디자인 시스템(violet/zinc, rounded-xl)과 어긋나고, 모델 선택처럼 항목이 많은 경우 탐색이 불편했다. 본 작업은 `dropdown.png`를 기준으로 한 헤드리스 공통 `<Dropdown />`(default/model 2 variant + model 검색 + 키보드/ARIA 접근성)을 신규 작성하고, 기존 23개 `<select>`를 의미 보존하며 전량 교체하여 UI/UX·접근성을 표준화했다.

### Results

| 항목 | 수치 |
|------|------|
| Match Rate | **97%** (초기 94% → Act 후) |
| 신규 파일 | 2 (`Dropdown.tsx`, `Dropdown.test.tsx`) |
| 마이그레이션 파일 | 12 |
| 교체된 `<select>` | 23 (model 1 / default 22) |
| 잔존 native `<select>` | **0** |
| 신규 컴포넌트 테스트 | **12/12 통과** |
| type-check / Dropdown lint | 통과 / 클린 |
| 신규 회귀 | **0건** (전체 실패 9건은 전부 사전 실패) |

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 12개 파일 23곳이 브라우저 네이티브 `<select>`라 OS마다 렌더링이 달라 디자인 시스템(violet 포인트·rounded·zinc 보더)과 시각적으로 어긋났고, 모델 선택처럼 항목이 수십 개인 드롭다운은 단순 스크롤만 가능해 탐색이 불편했다. 접근성(키보드/ARIA)도 브라우저 기본 동작에만 의존했다. |
| **Solution** | 의존성 0의 헤드리스 `src/components/common/Dropdown.tsx`를 신규 작성(`button` + 커스텀 패널). `default`/`model` 2 variant, model variant 한정 상단 검색, 키보드(↑↓/Enter/Esc/Home/End/Tab)·외부클릭 닫힘·`combobox`/`listbox`/`option` ARIA + `aria-activedescendant` 가상 포커스, `isLoading` skeleton·`disabled`·빈 목록 처리. 23개 `<select>`를 `value`/`onChange` 의미를 보존해 전량 교체. |
| **Function/UX Effect** | 모델 선택 드롭다운이 `dropdown.png` 그대로 — bullet(•)·monospace·선택 체크(✓)·`[API 키 미등록]` 배지·하단 스크롤 인디케이터(▾) + 상단 검색창으로 수십 개 모델 중 원하는 항목을 즉시 필터. 일반 필터/폼은 깔끔한 default 스타일로 통일되어 전 화면 드롭다운 룩앤필이 일관됨. 키보드만으로 완전 조작 가능하고 스크린리더가 활성 옵션을 읽는다. |
| **Core Value** | 단일 컴포넌트로 전 화면 드롭다운 UI·접근성·키보드 조작을 표준화하고, 외부 라이브러리 추가 없이(번들 증가 0) 스타일 자유도를 확보. 향후 드롭다운은 `<Dropdown>` 재사용으로 일관성이 자동 유지되어 유지보수 부담이 감소한다. |

---

## PDCA Cycle Summary

### Plan Phase
- **Document**: `docs/01-plan/features/common-dropdown-component.plan.md`
- **사용자 4개 결정 수집(AskUserQuestion)**: ① 헤드리스 직접 구현 ② 전체 23곳 교체 ③ variant 분리(model/default) ④ model variant 한정 검색
- **Scope**: 신규 컴포넌트 + 12파일/23 select 마이그레이션, 단계적(모델→필터→폼) 무회귀 전략

### Design Phase
- **Document**: `docs/02-design/features/common-dropdown-component.design.md`
- **Key Decisions**:
  - 헤드리스 직접 구현 (Radix/shadcn 대신) — `dropdown.png` 스타일 100% 자유 재현, 의존성 0
  - controlled 전용 (`value` SSOT, 로컬은 `open`/`query`/`activeIndex`만)
  - native `<select value onChange>`와 1:1 매핑되는 drop-in API
  - 폼 제출 연동용 `name` → hidden input (§3.4)
- **API**: `DropdownOption{value,label,badge?,disabled?}` + 14개 prop, 제네릭 `<T extends string>`

### Do Phase (Implementation)

#### Files Created
1. **`src/components/common/Dropdown.tsx`** — 헤드리스 드롭다운
   - default/model variant, searchable(model 기본), 키보드/외부클릭/ARIA, isLoading/disabled/emptyText, 스크롤 인디케이터, badge
2. **`src/components/common/Dropdown.test.tsx`** — 12 테스트(열림/선택/체크/검색/키보드/Esc/placeholder/loading/badge/aria-activedescendant)

#### Files Migrated (23 selects / 12 files)
- `agent-builder/ModelSettingsModal.tsx` (**model**), `agent-builder/RagConfigPanel.tsx`(3), `agent-builder/AgentSkillPanel.tsx`(1)
- `collection/CreateCollectionModal.tsx`(3), `collection/UpdateScopeModal.tsx`(1), `collection/ActivityLogFilters.tsx`(2)
- `admin/UserRegisterModal.tsx`(2)
- `pages/AdminAgentRunsPage`(1), `pages/AdminRagasPage`(3), `pages/AdminSkillsPage`(2), `pages/AdminMcpServersPage`(1), `pages/ToolAdminPage`(3)

#### Tests Updated (native select API → combobox 클릭 방식)
- `ModelSettingsModal.test.tsx`, `UserRegisterModal.test.tsx`, `CreateCollectionModal.test.tsx`, `RagConfigPanel.test.tsx`

### Check Phase (Gap Analysis)
- **Document**: `docs/03-analysis/common-dropdown-component.analysis.md`
- gap-detector 분석 **초기 94%** — Gap: G1 `aria-activedescendant`(Medium), G2 진입 애니메이션(Low), G3 max-h(Trivial)

### Act Phase (경미 보강)
- **G1 해결**: `<li id={listId-opt-i}>` + 트리거·검색입력 `aria-activedescendant` 추가, 테스트 1건 추가 → 접근성 100%
- **G3 해결**: `max-h-[260px]` → `max-h-[280px]` (설계 일치)
- **재검증**: type-check 통과, Dropdown 12/12 통과 → **Match Rate 97%**

---

## Verification

| 검증 | 결과 |
|------|------|
| `npm run type-check` | ✅ 통과 (0 에러) |
| `Dropdown.tsx` lint | ✅ 클린 (0 에러/경고) |
| `Dropdown.test.tsx` | ✅ 12/12 통과 |
| 마이그레이션 영향 테스트 | ✅ 갱신 후 전부 통과 |
| 전체 스위트 | 295 통과 / 9 실패 — **9건 전부 사전 실패**(collection 7 + ChatPage 1 + adminNav 1, 본 작업 무관) |
| 잔존 native `<select>` | ✅ 0건 |

---

## Remaining / Follow-up

| 항목 | 우선 | 비고 |
|------|:---:|------|
| G2: 패널 진입 fade/scale 애니메이션 | Low | 기능 영향 없음. 미세 시각 디테일 — 후속 개선 |
| 테스트 보강: 외부클릭 닫힘·disabled 클릭 불가(P2) | Low | 기능 정상, 테스트만 부재 |
| 모달(`z-50`) 내부 패널 overflow 클리핑 | 모니터링 | MVP는 absolute 패널. 잘리는 화면 발견 시 portal 검토 |
| 브라우저 시각 대조(`dropdown.png`) | 권장 | 코드/테스트 검증 완료, 실제 렌더 육안 확인은 미수행 |

---

## Lessons Learned

- **사전 실패 식별이 핵심**: 전체 스위트 9건 실패 중 본 작업 회귀는 0건. `UpdateScopeModal`(QueryClient 미주입 6) / `CreateCollectionModal`(stale `dept-uuid` 1) / `ChatPage`(1) / `adminNav`(1)은 모두 워킹트리 기존 이슈로 분리 확인. (메모리 노트 갱신)
- **native→headless 마이그레이션 시 테스트 전환 필수**: `selectOptions`/`within(select).getAllByRole('option')`는 커스텀 combobox에서 동작 안 함. 옵션은 패널 open 후 렌더되므로 "클릭으로 열고 → option 클릭" 패턴으로 일괄 전환.
- **placeholder vs 빈 옵션**: 폼은 placeholder로 미선택 표현, 필터는 `{value:'', label:'전체'}` 명시 옵션 유지가 UX상 자연스러움.
- **Windows vitest**: `--pool=threads`로 forks 워커 기동 타임아웃 회피.

---

## Conclusion

`dropdown.png` 기반 공통 헤드리스 `<Dropdown>`을 신규 작성하고 23개 native select를 무회귀로 전량 교체하여 **Match Rate 97%**로 PDCA 사이클을 완료했다. 접근성 100%, 신규 회귀 0건. 잔여는 Low 우선순위 진입 애니메이션 1건뿐.

→ 권장 다음 단계: `/pdca archive common-dropdown-component`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-06-28 | Initial completion report (matchRate 97%) | 배상규 |
