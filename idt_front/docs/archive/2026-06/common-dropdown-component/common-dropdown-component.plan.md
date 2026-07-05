# common-dropdown-component Planning Document

> **Summary**: 네이티브 `<select>`를 `dropdown.png` 스타일의 헤드리스 공통 Dropdown 컴포넌트로 교체 (variant 2종 + 검색 지원)
>
> **Project**: idt_front (RAG + AI Agent Frontend)
> **Author**: 배상규
> **Date**: 2026-06-28
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 전 화면(12개 파일·23곳)이 브라우저 네이티브 `<select>`를 사용해 디자인 시스템(violet/zinc, rounded-xl)과 동떨어지고, 모델 선택처럼 항목이 많은 경우 탐색이 불편하다 |
| **Solution** | 의존성 없는 헤드리스 공통 `<Dropdown />` 컴포넌트를 신규 작성하고(`model`/`default` 2 variant + 모델 variant 검색), 기존 23개 `<select>`를 일괄 마이그레이션 |
| **Function/UX Effect** | `dropdown.png` 그대로 — bullet(•)·monospace·선택 체크·`[API 키 미등록]` 배지·스크롤 인디케이터 + 모델 목록 상단 검색창으로 한 번에 원하는 항목을 찾는다 |
| **Core Value** | 단일 컴포넌트로 전 화면 드롭다운 UI를 통일하고, 외부 라이브러리 추가 없이 스타일·접근성·키보드 조작을 표준화 |

---

## 1. Overview

### 1.1 Purpose

프로젝트 전반에서 사용 중인 네이티브 `<select>`(23곳)를 `docs/img/dropdown.png` 디자인을 반영한 **공통 헤드리스 Dropdown 컴포넌트**로 교체하여, 일관된 UI/UX와 키보드 접근성을 확보한다.

### 1.2 Background

- 현재 모든 드롭다운이 브라우저 네이티브 `<select>`라 OS마다 렌더링이 다르고, 프로젝트 디자인 토큰(violet 포인트, rounded-xl, zinc 보더)과 시각적으로 어긋난다.
- `dropdown.png`의 대상은 `ModelSettingsModal.tsx:94`의 모델 선택 드롭다운으로, 항목명을 monospace로 표시하고 `[API 키 미등록]` 배지·선택 체크·스크롤 인디케이터를 갖춘 형태가 목표다.
- 모델 목록은 수십 개까지 늘어날 수 있어 단순 스크롤보다 **상단 검색 필터**가 UX에 유리하다.
- `components/common/`에 공통 UI 프리미티브 패턴이 이미 있으나(드롭다운은 부재), 신규 `Dropdown`을 같은 위치에 추가하면 자연스럽게 흡수된다.

### 1.3 결정 사항 (사용자 확인 완료)

| 항목 | 결정 |
|------|------|
| 구현 방식 | **직접 구현(headless)** — 외부 라이브러리 없이 `button` + 커스텀 패널 |
| 교체 범위 | **전체 교체** — 12개 파일 / 23개 `<select>` 일괄 마이그레이션 |
| 스타일 | **variant 분리** — `model`(mono+bullet+badge+검색) / `default`(일반 텍스트 필터) |
| 검색 | **model variant 한정** 상단 검색(필터) 입력 포함, `default`는 미포함 |

### 1.4 Related Documents

- 디자인 레퍼런스: `docs/img/dropdown.png`
- 유사 선행 plan: `docs/01-plan/features/collection-department-dropdown.plan.md`
- 디자인 시스템 규칙: `idt_front/CLAUDE.md` (색상 토큰, 컴포넌트 스타일 패턴, 타이포그래피)

---

## 2. Scope

### 2.1 In Scope

- [x] 신규 공통 컴포넌트 `src/components/common/Dropdown.tsx` (+ 단위 테스트)
- [x] `model` / `default` 2개 variant 지원
- [x] `model` variant: monospace 항목, bullet(•), 선택 체크, `[API 키 미등록]` 배지, 상단 검색 입력, 스크롤 인디케이터
- [x] `default` variant: 일반 텍스트 항목(필터/폼용), 선택 체크
- [x] 키보드 접근성(↑/↓/Enter/Esc), 외부 클릭 닫기, 포커스 관리, ARIA(listbox/option)
- [x] 기존 23개 `<select>` → `<Dropdown />` 마이그레이션 (12개 파일)
- [x] 로딩/비활성(disabled)/빈 목록 상태 처리

### 2.2 Out of Scope

- 다중 선택(multi-select) — 현재 사용처 전부 단일 선택이라 불필요
- `<optgroup>`(옵션 그룹) — 현재 사용처 없음
- 백엔드 API 변경 (순수 프론트 UI 작업)
- `PeriodFilter` 등 select가 아닌 기존 커스텀 필터 컴포넌트 (별도 영역)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `Dropdown` 컴포넌트가 `value`/`onChange`/`options`로 단일 선택 동작 | High | Pending |
| FR-02 | `variant="model"`: monospace + bullet + 선택 체크 + 배지 렌더 (`dropdown.png` 일치) | High | Pending |
| FR-03 | `variant="model"`: 상단 검색 입력으로 옵션 라벨 실시간 필터 | High | Pending |
| FR-04 | `variant="default"`: 일반 텍스트 항목 + 선택 체크 (필터/폼용) | High | Pending |
| FR-05 | 트리거 클릭 시 패널 토글, 외부 클릭/Esc 시 닫힘 | High | Pending |
| FR-06 | 키보드 조작: ↑/↓ 이동, Enter 선택, Esc 닫기, 포커스 트랩 | Medium | Pending |
| FR-07 | `renderOption`(또는 badge/icon props)로 항목 커스텀 렌더 지원 | Medium | Pending |
| FR-08 | `disabled`/`isLoading`/빈 목록 상태 시각 처리 | Medium | Pending |
| FR-09 | 23개 기존 `<select>`를 동작 동일하게 `<Dropdown />`로 교체 | High | Pending |
| FR-10 | 패널이 긴 목록일 때 스크롤 + 하단 스크롤 인디케이터(▾) 표시 | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 접근성 | ARIA role(listbox/option) + 키보드 완전 조작 | 수동 키보드 테스트 |
| 일관성 | 디자인 토큰(violet/zinc, rounded-xl) 준수 | 시각 검토 |
| 성능 | 의존성 추가 0, 리렌더 최소화 | 번들 diff / 프로파일 |
| 테스트 | 컴포넌트 60%+ / 핵심 로직(검색·선택·키보드) 커버 | `npm run coverage` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `Dropdown` 컴포넌트가 두 variant로 정상 동작
- [ ] `ModelSettingsModal` 모델 선택이 `dropdown.png`와 시각적으로 일치
- [ ] 모델 variant 검색으로 항목 필터링 동작
- [ ] 23개 `<select>` 전부 교체, 기존 onChange 동작 동일 유지
- [ ] 키보드/외부클릭/Esc/접근성 동작
- [ ] 로딩·비활성·빈 목록 상태 처리

### 4.2 Quality Criteria

- [ ] TypeScript 타입 에러 없음 (`npm run type-check`)
- [ ] Lint 통과 (`npm run lint`)
- [ ] 신규/기존 테스트 통과 (`npm run test:run --pool=threads`)
- [ ] 빌드 성공 (`npm run build`)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 23곳 일괄 교체 중 일부 onChange 시그니처 누락 → 회귀 | High | Medium | 마이그레이션을 파일 단위 단계로 쪼개고, 변경 후 해당 화면 수동 확인 + 기존 테스트(예: `ModelSettingsModal.test.tsx`) 갱신 |
| 폼 `<select>`(role/department 등)는 `<form>` 제출/필수값 검증과 결합 | Medium | Medium | `Dropdown`에 `name`/`required`/숨김 input 연동 옵션 제공 또는 제출 로직이 state 기반인지 사전 확인 |
| 헤드리스 직접 구현 → 포커스/스크롤/포지셔닝 엣지케이스 | Medium | Medium | MVP는 트리거 하단 고정 패널 + `max-height`+스크롤로 단순화, 뷰포트 넘침은 추후 개선(Out of Scope 표기) |
| `react-select` 등 미사용 → 접근성 직접 보장 부담 | Low | Medium | ARIA + 키보드 핸들링을 컴포넌트 테스트로 고정 |
| 모달 내부(`z-50`)에서 패널 z-index/overflow 클리핑 | Medium | Medium | 패널을 트리거 기준 `absolute`로 띄우고 모달 `overflow` 확인, 필요 시 portal 검토(추후) |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Selected |
|-------|-----------------|:--------:|
| **Dynamic** | Feature-based modules, TanStack Query, Zustand, shadcn/ui | **선택** |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 구현 방식 | 헤드리스 직접 구현 / shadcn(Radix) Select | **헤드리스 직접 구현** | `dropdown.png`의 mono·bullet·badge 스타일 100% 자유 재현, 의존성 0 (사용자 결정) |
| 스타일 전략 | 단일 스타일 / variant 분리 | **variant 분리(`model`,`default`)** | 짧은 필터에 monospace는 과함 → 용도별 스타일 (사용자 결정) |
| 검색 범위 | 전체 / model 한정 / 없음 | **model variant 한정** | 모델 목록만 항목이 많음 (사용자 결정) |
| 위치 | `components/common/` | `components/common/Dropdown.tsx` | 기존 공통 프리미티브와 동일 위치 |

### 6.3 컴포넌트 API (초안 — Design 단계 확정)

```tsx
interface DropdownOption<T extends string = string> {
  value: T;
  label: string;
  badge?: string;        // 예: 'API 키 미등록'
  disabled?: boolean;
}

interface DropdownProps<T extends string = string> {
  value: T;
  onChange: (value: T) => void;
  options: DropdownOption<T>[];
  variant?: 'model' | 'default';   // 기본 'default'
  searchable?: boolean;            // 기본: variant==='model'이면 true
  placeholder?: string;
  disabled?: boolean;
  isLoading?: boolean;
  emptyText?: string;
  className?: string;
  renderOption?: (opt: DropdownOption<T>, selected: boolean) => React.ReactNode;
}
```

---

## 7. Implementation Guide

### 7.1 마이그레이션 대상 인벤토리 (23곳 / 12파일)

| # | 파일 | select 수 | 용도 | 권장 variant |
|---|------|:---:|------|:---:|
| 1 | `components/agent-builder/ModelSettingsModal.tsx` | 1 | 모델 선택 (**dropdown.png 기준**) | `model` |
| 2 | `components/agent-builder/RagConfigPanel.tsx` | 3 | RAG 설정 셀렉트 | `default` |
| 3 | `components/agent-builder/AgentSkillPanel.tsx` | 1 | 스킬 선택 | `default` |
| 4 | `components/collection/CreateCollectionModal.tsx` | 3 | 스코프/부서/임베딩 모델 | `default` |
| 5 | `components/collection/UpdateScopeModal.tsx` | 1 | 접근 범위 | `default` |
| 6 | `components/collection/ActivityLogFilters.tsx` | 2 | 활동 로그 필터 | `default` |
| 7 | `components/admin/UserRegisterModal.tsx` | 2 | 역할/부서 | `default` |
| 8 | `pages/AdminAgentRunsPage/index.tsx` | 1 | 상태 필터 | `default` |
| 9 | `pages/AdminRagasPage/index.tsx` | 3 | 대상/유형/상태 필터 | `default` |
| 10 | `pages/AdminSkillsPage/index.tsx` | 2 | 스킬 필터 | `default` |
| 11 | `pages/AdminMcpServersPage/index.tsx` | 1 | MCP 서버 셀렉트 | `default` |
| 12 | `pages/ToolAdminPage/index.tsx` | 3 | 도구 관리 셀렉트 | `default` |

> 합계: **23개** (`model` 1 / `default` 22). 정확한 라인/옵션 구조는 Design 단계에서 파일별로 확정.

### 7.2 구현 순서 (단계별 — 안전 마이그레이션)

1. **컴포넌트 작성 (TDD)** — `Dropdown.tsx` + `Dropdown.test.tsx`
   - Red: 선택/검색/키보드/외부클릭 테스트 작성
   - Green: `default` variant 먼저 → `model` variant(검색·배지·체크) 추가
2. **모델 selector 교체 + 검증** — `ModelSettingsModal.tsx`를 `variant="model"`로 교체, `dropdown.png` 대조, `ModelSettingsModal.test.tsx` 갱신
3. **필터형 select 교체** — Admin 페이지/필터(8·9·10·11·12, 6) `variant="default"`
4. **폼형 select 교체** — 모달 폼(2·3·4·5·7), `<form>` 제출 연동 확인
5. **정리** — 잔존 native `<select>` 0 확인(grep), 타입/린트/테스트/빌드

### 7.3 변경 패턴 (Before → After)

**Before** (`ModelSettingsModal.tsx`):
```tsx
<select value={model} onChange={(e) => setModel(e.target.value)} className="...">
  {(models ?? []).map((m) => (
    <option key={m.id} value={m.model_name}>
      {m.provider}:{m.display_name}{m.is_active ? '' : ' [API 키 미등록]'}
    </option>
  ))}
</select>
```

**After**:
```tsx
<Dropdown
  variant="model"
  value={model}
  onChange={setModel}
  options={(models ?? []).map((m) => ({
    value: m.model_name,
    label: `${m.provider}:${m.display_name}`,
    badge: m.is_active ? undefined : 'API 키 미등록',
  }))}
  placeholder="모델 선택"
/>
```

### 7.4 의존성

- 신규 패키지 설치: **없음** (헤드리스 직접 구현)
- 활용: 기존 Tailwind 토큰 + `CLAUDE.md` 컴포넌트 스타일 패턴

---

## 8. Next Steps

1. [ ] Design 문서 작성 (`/pdca design common-dropdown-component`) — 컴포넌트 API/상태머신/파일별 라인 확정
2. [ ] `Dropdown.tsx` + 테스트 구현 (TDD)
3. [ ] 단계별 마이그레이션 (모델 → 필터 → 폼)
4. [ ] Gap 분석 (`/pdca analyze common-dropdown-component`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-28 | Initial draft (사용자 4개 결정 반영) | 배상규 |
