---
template: design
version: 1.0
feature: common-dropdown-component
date: 2026-06-28
author: 배상규
project: idt_front
version_project: 0.0.0
---

# common-dropdown-component Design Document

> **Summary**: 네이티브 `<select>`를 대체할 의존성 없는 헤드리스 공통 `<Dropdown />` 컴포넌트를 설계한다. `default`/`model` 2 variant, model variant 검색, 키보드/ARIA 접근성을 갖추며 기존 23개 `<select>`(12파일)를 무회귀로 마이그레이션한다.
>
> **Project**: idt_front
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-06-28
> **Status**: Draft
> **Planning Doc**: [common-dropdown-component.plan.md](../../01-plan/features/common-dropdown-component.plan.md)
> **Design Ref**: `docs/img/dropdown.png`, `idt_front/CLAUDE.md` (디자인 토큰/스타일 패턴)

---

## 1. Overview

### 1.1 Design Goals

- 단일 헤드리스 컴포넌트로 전 화면 드롭다운 UI/UX·접근성을 표준화한다.
- `dropdown.png`를 `variant="model"`로 1:1 재현한다 (mono·bullet·체크·`[API 키 미등록]` 배지·스크롤 인디케이터·상단 검색).
- 외부 라이브러리 추가 없이 `button` + 커스텀 패널로 구현한다 (번들 증가 0).
- 기존 23곳의 `value`/`onChange` 의미를 그대로 보존해 회귀를 차단한다.

### 1.2 Design Principles

- **Headless-first**: 동작(열림/검색/키보드)과 스타일(variant)을 분리, 스타일은 Tailwind 토큰 준수.
- **Drop-in 호환**: native `<select value onChange>`와 의미적으로 1:1 매핑되는 API (`value`/`onChange(value)`).
- **Controlled only**: 내부 선택 상태를 두지 않고 부모의 `value`를 단일 소스로 사용 (open/검색어만 로컬).
- **Progressive**: MVP는 트리거 하단 absolute 패널 + max-height 스크롤. 뷰포트 넘침/portal은 후속.
- **A11y by default**: `combobox`/`listbox`/`option` role + 완전 키보드 조작.

---

## 2. Architecture

### 2.1 Component Structure

```
src/components/common/Dropdown.tsx        ← 공통 컴포넌트 (단일 파일)
src/components/common/Dropdown.test.tsx   ← 단위/상호작용 테스트

┌──────────────────────────────────────────────┐
│ <Dropdown>  (controlled)                       │
│  ├─ Trigger (button[role=combobox])            │
│  │    선택값 라벨 + (model: bullet/badge) + ▾   │
│  └─ Panel (ul[role=listbox], open 시)          │
│       ├─ SearchInput (model & searchable)      │
│       ├─ Option*[role=option] (• / label /     │
│       │    badge / ✓)                          │
│       └─ ScrollIndicator (▾, 넘침 시)           │
└──────────────────────────────────────────────┘
```

> 내부 보조 컴포넌트(Trigger/Panel/Option)는 동일 파일 내 비공개 함수로 두어 파일 1개로 응집. 200줄 초과 시 `Dropdown/` 디렉토리로 분리 검토(CLAUDE.md 규칙).

### 2.2 State Model

| State | 위치 | 설명 |
|-------|------|------|
| `value` | 부모 (prop) | 선택된 값 (SSOT) |
| `open` | 로컬 `useState` | 패널 열림 여부 |
| `query` | 로컬 `useState` | 검색어 (model+searchable 한정) |
| `activeIndex` | 로컬 `useState` | 키보드 하이라이트 인덱스 |

상태 전이:

```
closed ──(트리거 클릭/Enter/Space/↓)──▶ open
open   ──(외부클릭/Esc/선택/Tab)──────▶ closed (선택 시 onChange 발생)
open   ──(↑/↓)──▶ activeIndex 이동 (필터된 목록 기준)
open   ──(타이핑)──▶ query 갱신 → 목록 필터 → activeIndex 0 리셋
열릴 때: query='' 초기화, activeIndex=현재 value의 인덱스(없으면 0)
```

---

## 3. Component API

### 3.1 Types

```tsx
// src/components/common/Dropdown.tsx
export interface DropdownOption<T extends string = string> {
  value: T;
  label: string;
  badge?: string;       // 예: 'API 키 미등록' → 항목/트리거에 [배지] 렌더
  disabled?: boolean;
}

export interface DropdownProps<T extends string = string> {
  value: T;
  onChange: (value: T) => void;
  options: DropdownOption<T>[];
  variant?: 'default' | 'model';   // 기본 'default'
  searchable?: boolean;            // 기본값: variant === 'model'
  placeholder?: string;            // 미선택/빈값 표시 (기본 '선택하세요')
  disabled?: boolean;
  isLoading?: boolean;             // 트리거를 skeleton/disabled 처리
  emptyText?: string;              // 옵션/검색결과 없음 (기본 '항목이 없습니다')
  searchPlaceholder?: string;      // 검색창 placeholder (기본 '검색...')
  className?: string;              // 트리거 wrapper 추가 클래스
  id?: string;                    // label htmlFor 연동용
  ariaLabel?: string;             // 시각적 label 없을 때
  name?: string;                  // 폼 제출 연동 시 hidden input name (3.4)
}
```

### 3.2 동작 규약

| 항목 | 규약 |
|------|------|
| 선택 | 옵션 클릭/Enter → `onChange(option.value)` 후 패널 닫힘 |
| 빈 값 | `value=''` 이고 매칭 옵션 없으면 `placeholder` 표시 (native의 `<option value="">전체</option>` 대응) |
| disabled 옵션 | 클릭/키보드 선택 불가, 시각적 흐림 |
| 검색 | `query`로 `label` 부분일치(대소문자 무시) 필터. `default`는 검색 미노출 |
| 로딩 | `isLoading` → 트리거 자리 `animate-pulse` skeleton, 클릭 불가 |
| 닫힘 | 외부 클릭(ref 밖) / Esc / 선택 / Tab 이동 |

### 3.3 Keyboard (FR-06)

| 키 | closed | open |
|----|--------|------|
| ↓ / ↑ | 열기 (↓) | activeIndex 이동 (disabled 건너뜀, wrap) |
| Enter / Space | 열기 | activeIndex 옵션 선택 |
| Esc | — | 닫기 (value 유지) |
| Home / End | — | 첫/마지막 옵션 |
| Tab | — | 닫고 포커스 이동 |
| 타이핑 | — | (searchable) 검색창 입력 |

### 3.4 폼 제출 연동 (Risk 대응)

대부분 사용처는 `useState` 기반 제출이라 `value`/`onChange`만으로 충분. 단, `<form>` 네이티브 제출에 의존하는 곳을 위해 `name`이 주어지면 컴포넌트가 `<input type="hidden" name={name} value={value} />`를 함께 렌더한다. → Do 단계에서 대상 파일별 제출 방식 확인 후 필요 시에만 `name` 전달.

---

## 4. Visual Specification

공통: 트리거/패널 모두 `rounded-xl`(트리거)·`rounded-2xl`(패널), `border-zinc-300`, `bg-white`, focus 시 `border-violet-400`. (CLAUDE.md 토큰)

### 4.1 Trigger

```
default:  [ 선택 라벨 ........................... ▾ ]   text-[13.5px] text-zinc-800
model:    [ • anthropic:claude-haiku-4-5 [API 키 미등록] ▾ ]  font-mono text-[13px]
```
- 패딩: `px-3.5 py-2.5`, full width, `outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100`
- `▾`: `h-4 w-4 text-zinc-400`, open 시 180° 회전(`transition-transform`)
- `model` 트리거 좌측 bullet(•)·우측 배지 inline 표시 (dropdown.png 상단 박스 일치)

### 4.2 Panel

- 위치: 트리거 기준 `absolute left-0 right-0 mt-1 z-50`
- 박스: `rounded-2xl border border-zinc-200 bg-white shadow-xl`, `max-h-[280px] overflow-y-auto`
- 진입: `transition-all`, 가벼운 fade/scale (`origin-top`)

### 4.3 Option

| 요소 | default | model |
|------|---------|-------|
| 폰트 | `text-[13.5px]` | `font-mono text-[13px]` |
| bullet | 없음 | `•` (text-zinc-300, 선택 시 violet) |
| 배지 | (옵션) | `[API 키 미등록]` `text-[11px] text-zinc-400` |
| 선택 체크 | 좌측 `✓` (violet-600) | 좌측 `✓` (violet-600) |
| hover/active | `bg-violet-50` | `bg-violet-50` |
| disabled | `text-zinc-300 cursor-not-allowed` | 동일 |

- 항목 패딩 `px-3 py-2`, 정렬은 dropdown.png처럼 좌측 체크 컬럼 + bullet + 라벨 + (우측/인라인 배지).

### 4.4 Search & ScrollIndicator (model)

- 검색창: 패널 상단 sticky, `🔍`(svg) + `<input>` `text-[13px]`, 하단 `border-b border-zinc-100`.
- 스크롤 인디케이터: 콘텐츠가 넘칠 때 패널 하단 중앙 `▾`(`text-zinc-300`), 끝까지 스크롤되면 숨김(`scrollTop` 기반) — dropdown.png 하단 chevron 재현. (Low 우선순위 FR-10)

---

## 5. Migration Design

### 5.1 매핑 원칙 (native → Dropdown)

```tsx
// Before
<select value={v} onChange={(e) => setV(e.target.value)}>
  <option value="">전체</option>
  {list.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
</select>

// After
<Dropdown
  value={v}
  onChange={setV}
  placeholder="전체"
  options={[
    // value="" 빈옵션은 placeholder로 흡수하거나 명시 옵션으로 유지
    ...list.map((x) => ({ value: x.id, label: x.name })),
  ]}
/>
```

규칙:
1. `onChange={(e)=>setV(e.target.value)}` → `onChange={setV}` (타입 캐스팅 필요 시 래퍼 `(val)=>setV(val as T)`).
2. `<option value="">…</option>` → `placeholder`로 변환(빈값=미선택) 또는 `{value:'',label:'전체'}` 옵션 유지(필터에서 "전체" 명시 선택이 의미 있을 때).
3. 정적 `<option>` 나열 → 컴포넌트 상단 `as const` 배열로 추출 후 `options`에 매핑.

### 5.2 대상 인벤토리 & variant

| # | 파일 | 수 | variant | 비고 |
|---|------|:--:|:--:|------|
| 1 | `components/agent-builder/ModelSettingsModal.tsx` | 1 | `model` | **dropdown.png 기준**, badge=API 키 미등록 |
| 2 | `components/agent-builder/RagConfigPanel.tsx` | 3 | `default` | collection(로딩/에러)·search mode·metadata key |
| 3 | `components/agent-builder/AgentSkillPanel.tsx` | 1 | `default` | |
| 4 | `components/collection/CreateCollectionModal.tsx` | 3 | `default` | scope/부서/임베딩, 폼 제출 확인 |
| 5 | `components/collection/UpdateScopeModal.tsx` | 1 | `default` | scope |
| 6 | `components/collection/ActivityLogFilters.tsx` | 2 | `default` | 필터 |
| 7 | `components/admin/UserRegisterModal.tsx` | 2 | `default` | role/department, 폼 제출 확인 |
| 8 | `pages/AdminAgentRunsPage/index.tsx` | 1 | `default` | status 필터 |
| 9 | `pages/AdminRagasPage/index.tsx` | 3 | `default` | target/eval/status 필터 |
| 10 | `pages/AdminSkillsPage/index.tsx` | 2 | `default` | |
| 11 | `pages/AdminMcpServersPage/index.tsx` | 1 | `default` | |
| 12 | `pages/ToolAdminPage/index.tsx` | 3 | `default` | |

합계 **23** (model 1 / default 22).

### 5.3 마이그레이션 단계 (무회귀)

1. `Dropdown.tsx` + 테스트 (TDD) — default→model 순.
2. `ModelSettingsModal` model 교체 → `dropdown.png` 대조 + `ModelSettingsModal.test.tsx` 갱신.
3. 필터형(6·8·9·10·11·12) default 교체.
4. 폼형(2·3·4·5·7) default 교체 + 제출 방식 확인.
5. `grep "<select"` 0건 확인 + type-check/lint/test/build.

---

## 6. Accessibility

| 항목 | 구현 |
|------|------|
| 트리거 | `role="combobox" aria-haspopup="listbox" aria-expanded aria-controls` |
| 패널 | `role="listbox" id` (+검색 시 `aria-activedescendant`) |
| 옵션 | `role="option" aria-selected aria-disabled` |
| 라벨 | `id`/`ariaLabel`로 외부 `<label htmlFor>` 또는 `aria-label` 연결 |
| 키보드 | §3.3 전체 지원, 포커스 비포함 옵션은 `aria-activedescendant`로 가상 포커스 |

---

## 7. Testing Strategy (TDD)

| 우선 | 케이스 |
|:--:|--------|
| P1 | 트리거 클릭 시 패널 open/close |
| P1 | 옵션 클릭 시 `onChange(value)` 호출 & 닫힘 |
| P1 | 선택값에 ✓ 표시, 트리거 라벨 갱신 |
| P1 | (model) 검색어 입력 시 목록 필터, 없음 시 `emptyText` |
| P1 | 키보드 ↑/↓/Enter/Esc 동작, disabled 옵션 스킵 |
| P2 | 외부 클릭 시 닫힘 |
| P2 | `isLoading` skeleton, `disabled` 클릭 불가 |
| P2 | (model) badge 렌더 (`[API 키 미등록]`) |
| P3 | `ModelSettingsModal` 통합: 모델 변경 → 저장 payload 반영 |

테스트 실행: `npm run test:run -- --pool=threads` (Windows forks 타임아웃 회피 — 메모리 노트).

---

## 8. Implementation Order (→ Do)

1. [ ] `Dropdown.tsx` 골격 + 타입 + `default` variant (open/close/select)
2. [ ] 키보드/외부클릭/ARIA + 테스트(P1)
3. [ ] `model` variant (bullet/badge/✓/검색/스크롤 인디케이터) + 테스트
4. [ ] `ModelSettingsModal` 교체 + 시각 대조 + 테스트 갱신
5. [ ] 필터형 6곳 교체
6. [ ] 폼형 5곳 교체 (제출 방식 확인, 필요 시 `name`)
7. [ ] 잔존 `<select>` 0 확인 + type-check/lint/test/build

---

## 9. Open Questions (Do 단계 확정)

- 폼형 select(4·7)가 native form submit에 의존하는가, state 기반인가 → 파일 확인 후 `name` 사용 여부 결정.
- 필터의 `value=""`("전체")를 placeholder로 흡수할지 명시 옵션으로 유지할지 → 사용처별 판단(필터는 "전체" 명시 옵션 유지 권장).

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-28 | Initial design draft | 배상규 |
