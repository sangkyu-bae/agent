# Plan: layout-scroll-fix

> 전체 레이아웃 스크롤 잘림 현상 수정

---

## 1. 현상

- 콘텐츠가 뷰포트 높이를 초과하면 **스크롤바 없이 잘려서 보이지 않음**
- 영향받는 페이지: CollectionPage, CollectionDocumentsPage, AdminUsersPage, DocumentPage 등
  자체 스크롤 컨테이너를 갖지 않는 모든 페이지

---

## 2. 근본 원인 분석

### 2-1. 높이 체인 (Viewport Lock)

```
html { height: 100% }           ← index.css
  body { height: 100% }         ← index.css
    #root { height: 100% }      ← index.css
      AuthenticatedLayout        ← App.tsx (height: 100%)
        TopNav                   ← 52px 고정
        ContentArea              ← flex: 1, overflow: hidden  ← ★ 핵심 원인
          <Outlet />             ← 페이지 컴포넌트
```

- `html → body → #root → Layout` 전체가 `height: 100%`로 뷰포트 높이에 고정
- TopNav 52px을 제외한 나머지 영역이 ContentArea
- **ContentArea에 `overflow: 'hidden'`** 이 설정되어 있어, 콘텐츠가 넘쳐도 스크롤바가 생성되지 않고 잘림

### 2-2. 페이지별 스크롤 처리 현황

| 페이지 | 자체 스크롤 관리 | 현상 |
|--------|:---:|------|
| ChatPage | O | 정상 — `height: 100%` + 내부 `overflowY: auto` |
| AgentBuilderPage | O | 정상 — 동일 패턴 |
| EvalDatasetPage | O | 정상 — 동일 패턴 |
| ToolAdminPage | O | 정상 — 동일 패턴 |
| ToolConnectionPage | O | 정상 — 동일 패턴 |
| WorkflowDesignerPage | O | 정상 — 동일 패턴 |
| WorkflowBuilderPage | O | 정상 — 동일 패턴 |
| **CollectionPage** | **X** | **잘림** — `max-w-5xl px-4 py-8` 만 사용 |
| **CollectionDocumentsPage** | **X** | **잘림** — 동일 |
| **AdminUsersPage** | **X** | **잘림** — `max-w-3xl px-6 py-8` 만 사용 |
| **DocumentPage** | △ | `overflowY: auto` 있으나 다른 패턴 |

### 2-3. 원인 코드 위치

**`src/App.tsx:28-34`** — AuthenticatedLayout:
```tsx
const AuthenticatedLayout = () => (
  <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
    <TopNav />
    <div style={{ flex: 1, overflow: 'hidden' }}>  // ← 여기가 원인
      <Outlet />
    </div>
  </div>
);
```

---

## 3. 수정 방안

### 방안: AuthenticatedLayout의 `overflow: 'hidden'` → `overflow: 'auto'` 변경

**변경 파일**: `src/App.tsx` (1줄 수정)

```tsx
// Before
<div style={{ flex: 1, overflow: 'hidden' }}>

// After
<div style={{ flex: 1, overflow: 'auto' }}>
```

**동작 원리**:
- 자체 스크롤 관리 페이지 (ChatPage 등): 루트에 `height: 100%` + `overflow: hidden` 설정 → 부모 영역에 딱 맞게 들어가므로 **레이아웃 스크롤 발생하지 않음** → 기존과 동일
- 비관리 페이지 (CollectionPage 등): 콘텐츠가 넘치면 레이아웃 ContentArea에 **스크롤바 자동 생성** → 문제 해결

**장점**: 수정 범위 최소 (1줄), 기존 페이지 영향 없음, 새 페이지 추가 시 자동 스크롤 지원
**위험**: 없음 — 자체 스크롤 관리 페이지는 `height: 100%`로 자기 크기를 제한하므로 이중 스크롤바 불가

---

## 4. 영향 범위

- `src/App.tsx` — AuthenticatedLayout 컴포넌트 (1줄 수정)
- 모든 페이지 컴포넌트 — 수정 불필요 (기존 코드 그대로)

---

## 5. 검증 체크리스트

- [ ] CollectionPage: 컬렉션이 많을 때 스크롤 동작 확인
- [ ] CollectionDocumentsPage: 문서 목록이 길 때 스크롤 동작 확인
- [ ] AdminUsersPage: 사용자 목록이 길 때 스크롤 동작 확인
- [ ] ChatPage: 기존 채팅 스크롤 정상 동작 확인 (이중 스크롤바 없음)
- [ ] AgentBuilderPage: 기존 스크롤 정상 동작 확인
- [ ] 브라우저 리사이즈 시 레이아웃 깨짐 없음 확인
