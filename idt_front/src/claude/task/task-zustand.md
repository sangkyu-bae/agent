# ZUSTAND-001 — Zustand 공통 슬라이스

## 상태: 완료

## 목표
모든 Zustand 스토어에서 반복되는 로딩/에러, 리스트 CRUD, 선택 상태를
슬라이스 팩토리로 추출하여 재사용성 및 일관성 향상.

## 완료된 작업

### 공통 슬라이스 구현
- [x] `store/commonSlices.ts` — 슬라이스 팩토리 3종 + 공통 타입

### 기존 스토어 리팩토링 (commonSlices 적용)
- [x] `store/documentStore.ts` — LoadingSlice + ListSlice + SelectionSlice 적용
- [x] `store/agentStore.ts` — LoadingSlice 적용
- [x] `store/chatStore.ts` — LoadingSlice 적용

## 공통 타입

```typescript
// 비동기 작업 상태
type AsyncStatus = 'idle' | 'loading' | 'success' | 'error';

// id 필드를 가진 엔티티 기본 타입
interface BaseEntity { id: string; }
```

## 슬라이스 상세

### LoadingSlice — 비동기 로딩/에러 상태

```typescript
interface LoadingSlice {
  status: AsyncStatus;
  error: string | null;
  startLoading: () => void;   // status → 'loading', error → null
  finishLoading: () => void;  // status → 'success'
  failLoading: (error: string) => void;  // status → 'error'
  resetStatus: () => void;    // status → 'idle', error → null
}
```

**사용처**: chatStore, agentStore, documentStore

---

### ListSlice<T extends BaseEntity> — 리스트 CRUD

```typescript
interface ListSlice<T> {
  items: T[];
  setItems: (items: T[]) => void;        // 전체 교체
  addItem: (item: T) => void;            // 끝에 추가
  removeItem: (id: string) => void;      // id로 제거
  updateItem: (id: string, partial: Partial<T>) => void;  // 부분 수정
  clearItems: () => void;                // 전체 초기화
}
```

**사용처**: documentStore

---

### SelectionSlice — 다중 선택 상태

```typescript
interface SelectionSlice {
  selectedIds: string[];
  toggleSelection: (id: string) => void;   // 토글
  selectAll: (ids: string[]) => void;       // 전체 선택
  clearSelection: () => void;               // 선택 해제
  isSelected: (id: string) => boolean;      // 선택 여부 확인
}
```

**사용처**: documentStore

---

## 스토어 조합 패턴

```typescript
// 여러 슬라이스 조합 예시
import { create } from 'zustand';
import {
  createLoadingSlice,
  createListSlice,
  createSelectionSlice,
  type LoadingSlice,
  type ListSlice,
  type SelectionSlice,
} from './commonSlices';

type MyState = LoadingSlice & ListSlice<MyItem> & SelectionSlice;

const useMyStore = create<MyState>()((...args) => ({
  ...createLoadingSlice<MyState>()(...args),
  ...createListSlice<MyItem, MyState>()(...args),
  ...createSelectionSlice<MyState>()(...args),
}));
```

## 향후 확장 고려

- [ ] `createPaginationSlice` — 페이지네이션 상태 (page, pageSize, total, hasNext)
- [ ] `createSearchSlice` — 검색어 + 필터 상태
