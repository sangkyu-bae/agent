import { create } from 'zustand';

/**
 * excel-preview Design §5.3 — 모달 상태 소유 확정 사항.
 * 모달 열림 상태를 memo된 react-markdown 트리 밖에서 소유한다.
 * MarkdownRenderer는 open()만 호출하고, 모달은 ChatPage에 1회 마운트된다.
 */
export interface ExcelPreviewTarget {
  fileId: string;
  filename: string;
}

interface ExcelPreviewState {
  /** null이면 모달 닫힘 */
  target: ExcelPreviewTarget | null;
  open: (target: ExcelPreviewTarget) => void;
  close: () => void;
}

export const useExcelPreviewStore = create<ExcelPreviewState>()((set) => ({
  target: null,
  open: (target) => set({ target }),
  close: () => set({ target: null }),
}));
