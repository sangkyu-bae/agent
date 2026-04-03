/**
 * Zustand 공통 슬라이스 팩토리
 *
 * 사용법:
 *   import { create } from 'zustand';
 *   import { createLoadingSlice, createListSlice, createSelectionSlice } from './commonSlices';
 *
 *   const useMyStore = create<MyState>()((...args) => ({
 *     ...createLoadingSlice()(...args),
 *     ...createListSlice<MyItem, MyState>()(...args),
 *     ...createSelectionSlice()(...args),
 *   }));
 */

import type { StateCreator } from 'zustand';

// ─────────────────────────────────────────────
// 공통 타입
// ─────────────────────────────────────────────

/** 비동기 작업 상태 */
export type AsyncStatus = 'idle' | 'loading' | 'success' | 'error';

/** id 필드를 가진 엔티티 기본 타입 */
export interface BaseEntity {
  id: string;
}

// ─────────────────────────────────────────────
// LoadingSlice — 로딩 / 에러 상태
// ─────────────────────────────────────────────

export interface LoadingSlice {
  status: AsyncStatus;
  error: string | null;
  /** 로딩 시작 (status → 'loading', error → null) */
  startLoading: () => void;
  /** 성공 완료 (status → 'success') */
  finishLoading: () => void;
  /** 실패 처리 (status → 'error', error 메시지 저장) */
  failLoading: (error: string) => void;
  /** 상태 초기화 (status → 'idle', error → null) */
  resetStatus: () => void;
}

export const createLoadingSlice =
  <T extends LoadingSlice>(): StateCreator<T, [], [], LoadingSlice> =>
  (set) => ({
    status: 'idle',
    error: null,
    startLoading: () => set({ status: 'loading', error: null } as Partial<T>),
    finishLoading: () => set({ status: 'success' } as Partial<T>),
    failLoading: (error: string) => set({ status: 'error', error } as Partial<T>),
    resetStatus: () => set({ status: 'idle', error: null } as Partial<T>),
  });

// ─────────────────────────────────────────────
// ListSlice — 리스트 CRUD
// ─────────────────────────────────────────────

export interface ListSlice<T extends BaseEntity> {
  items: T[];
  /** 전체 교체 */
  setItems: (items: T[]) => void;
  /** 항목 추가 (끝에 append) */
  addItem: (item: T) => void;
  /** id로 항목 제거 */
  removeItem: (id: string) => void;
  /** id로 항목 부분 수정 */
  updateItem: (id: string, partial: Partial<T>) => void;
  /** 전체 초기화 */
  clearItems: () => void;
}

export const createListSlice =
  <T extends BaseEntity, S extends ListSlice<T>>(): StateCreator<S, [], [], ListSlice<T>> =>
  (set) => ({
    items: [],
    setItems: (items) => set({ items } as Partial<S>),
    addItem: (item) =>
      set((state) => ({ items: [...(state as ListSlice<T>).items, item] } as Partial<S>)),
    removeItem: (id) =>
      set(
        (state) =>
          ({
            items: (state as ListSlice<T>).items.filter((i) => i.id !== id),
          }) as Partial<S>,
      ),
    updateItem: (id, partial) =>
      set(
        (state) =>
          ({
            items: (state as ListSlice<T>).items.map((i) =>
              i.id === id ? { ...i, ...partial } : i,
            ),
          }) as Partial<S>,
      ),
    clearItems: () => set({ items: [] } as unknown as Partial<S>),
  });

// ─────────────────────────────────────────────
// SelectionSlice — 다중 선택 상태
// ─────────────────────────────────────────────

export interface SelectionSlice {
  selectedIds: string[];
  /** id 선택 토글 */
  toggleSelection: (id: string) => void;
  /** 여러 id 한번에 선택 */
  selectAll: (ids: string[]) => void;
  /** 전체 선택 해제 */
  clearSelection: () => void;
  /** 선택 여부 확인 */
  isSelected: (id: string) => boolean;
}

export const createSelectionSlice =
  <T extends SelectionSlice>(): StateCreator<T, [], [], SelectionSlice> =>
  (set, get) => ({
    selectedIds: [],
    toggleSelection: (id) =>
      set((state) => {
        const ids = (state as SelectionSlice).selectedIds;
        return {
          selectedIds: ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id],
        } as Partial<T>;
      }),
    selectAll: (ids) => set({ selectedIds: ids } as Partial<T>),
    clearSelection: () => set({ selectedIds: [] } as unknown as Partial<T>),
    isSelected: (id) => (get() as SelectionSlice).selectedIds.includes(id),
  });
