import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/**
 * ws-chat-streaming Design §5.4 — Plan Q4 답변:
 * ToolPreviewPanel 표시 여부를 사용자 선호로 영구 저장한다.
 */
interface ChatPreferencesState {
  showToolPreview: boolean;
  setShowToolPreview: (next: boolean) => void;
  toggleShowToolPreview: () => void;
}

export const useChatPreferencesStore = create<ChatPreferencesState>()(
  persist(
    (set) => ({
      showToolPreview: true, // default: 노출 (Q4: "일단 ui 노출")
      setShowToolPreview: (next) => set({ showToolPreview: next }),
      toggleShowToolPreview: () =>
        set((s) => ({ showToolPreview: !s.showToolPreview })),
    }),
    { name: 'chat-preferences' },
  ),
);
