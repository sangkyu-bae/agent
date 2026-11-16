import { create } from 'zustand';

import type { DocumentPreviewKind } from '@/types/filePreview';

/**
 * Design Ref: document-file-preview §5.3 — excelPreviewStore와 같은 구조.
 * memo된 react-markdown 트리 밖에서 모달 상태를 소유한다.
 * MarkdownRenderer는 open()만 호출하고, DocumentPreviewModal은 ChatPage에 1회 마운트된다.
 */
export interface DocumentPreviewTarget {
  fileId: string;
  filename: string;
  kind: DocumentPreviewKind;
}

interface DocumentPreviewState {
  /** null이면 모달 닫힘 */
  target: DocumentPreviewTarget | null;
  open: (target: DocumentPreviewTarget) => void;
  close: () => void;
}

export const useDocumentPreviewStore = create<DocumentPreviewState>()((set) => ({
  target: null,
  open: (target) => set({ target }),
  close: () => set({ target: null }),
}));
