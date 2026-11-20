import { create } from 'zustand';

import type { SourceViewerTarget } from '@/types/sourceViewer';

/**
 * Design Ref: source-passage-viewer §5.3 — documentPreviewStore 와 같은 구조.
 * 칩(SourceViewerButton)은 open()만 부르고, 패널은 ChatPage 의 SourceViewerMount 가 1회 마운트한다.
 */
interface SourceViewerState {
  /** null 이면 패널 닫힘 */
  target: SourceViewerTarget | null;
  /** 현재 구절 위치 (passages 기준) */
  index: number;
  open: (target: SourceViewerTarget) => void;
  close: () => void;
  next: () => void;
  prev: () => void;
}

export const useSourceViewerStore = create<SourceViewerState>()((set) => ({
  target: null,
  index: 0,
  open: (target) => set({ target, index: 0 }),
  close: () => set({ target: null, index: 0 }),
  next: () =>
    set((s) => {
      const last = (s.target?.viewer.passages.length ?? 1) - 1;
      return { index: Math.min(s.index + 1, Math.max(last, 0)) };
    }),
  prev: () => set((s) => ({ index: Math.max(s.index - 1, 0) })),
}));
