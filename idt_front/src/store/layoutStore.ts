import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const STORAGE_KEY = 'layout-preferences';

interface LayoutState {
  isChatPanelOpen: boolean;
  selectedAgentId: string | null;
  // Design Ref: ui-redesign-chat §3.1 — 사이드바 접기 상태. persist 키는 기존 그대로 유지한다.
  isSidebarCollapsed: boolean;
  toggleChatPanel: () => void;
  setChatPanelOpen: (open: boolean) => void;
  selectAgent: (id: string | null) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set) => ({
      isChatPanelOpen: false,
      selectedAgentId: 'super',
      isSidebarCollapsed: false,
      toggleChatPanel: () => set((s) => ({ isChatPanelOpen: !s.isChatPanelOpen })),
      setChatPanelOpen: (open) => set({ isChatPanelOpen: open }),
      selectAgent: (id) => set({ selectedAgentId: id }),
      toggleSidebar: () => set((s) => ({ isSidebarCollapsed: !s.isSidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ isSidebarCollapsed: collapsed }),
    }),
    { name: STORAGE_KEY }
  )
);

/**
 * 사용자가 사이드바 접기 상태를 한 번이라도 저장했는지.
 * Plan SC: FR-12 — 768 이하 최초 진입 시 기본 접힘은 저장값이 없을 때만 적용한다.
 */
export const hasPersistedSidebarPreference = (): boolean => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const parsed = JSON.parse(raw) as { state?: Record<string, unknown> };
    return typeof parsed.state?.isSidebarCollapsed === 'boolean';
  } catch {
    return false;
  }
};
