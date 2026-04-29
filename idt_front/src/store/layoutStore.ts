import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface LayoutState {
  isChatPanelOpen: boolean;
  selectedAgentId: string | null;
  toggleChatPanel: () => void;
  setChatPanelOpen: (open: boolean) => void;
  selectAgent: (id: string | null) => void;
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set) => ({
      isChatPanelOpen: false,
      selectedAgentId: 'super-ai',
      toggleChatPanel: () => set((s) => ({ isChatPanelOpen: !s.isChatPanelOpen })),
      setChatPanelOpen: (open) => set({ isChatPanelOpen: open }),
      selectAgent: (id) => set({ selectedAgentId: id }),
    }),
    { name: 'layout-preferences' }
  )
);
