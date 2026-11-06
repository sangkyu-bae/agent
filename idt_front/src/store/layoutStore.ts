import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { SIDEBAR_AGENT_GROUP, type SidebarAgentGroupKey } from '@/types/agent';

const STORAGE_KEY = 'layout-preferences';
const VALID_GROUP_KEYS: readonly unknown[] = Object.values(SIDEBAR_AGENT_GROUP);

interface LayoutState {
  isChatPanelOpen: boolean;
  selectedAgentId: string | null;
  // Design Ref: ui-redesign-chat §3.1 — 사이드바 접기 상태. persist 키는 기존 그대로 유지한다.
  isSidebarCollapsed: boolean;
  // Design Ref: sidebar-agent-list §3.2 — 접힌 에이전트 그룹 키 목록. 기본 [] = 모두 펼침
  collapsedAgentGroups: SidebarAgentGroupKey[];
  toggleChatPanel: () => void;
  setChatPanelOpen: (open: boolean) => void;
  selectAgent: (id: string | null) => void;
  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleAgentGroup: (key: SidebarAgentGroupKey) => void;
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set) => ({
      isChatPanelOpen: false,
      selectedAgentId: 'super',
      isSidebarCollapsed: false,
      collapsedAgentGroups: [],
      toggleChatPanel: () => set((s) => ({ isChatPanelOpen: !s.isChatPanelOpen })),
      setChatPanelOpen: (open) => set({ isChatPanelOpen: open }),
      selectAgent: (id) => set({ selectedAgentId: id }),
      toggleSidebar: () => set((s) => ({ isSidebarCollapsed: !s.isSidebarCollapsed })),
      setSidebarCollapsed: (collapsed) => set({ isSidebarCollapsed: collapsed }),
      // Plan SC: FR-06 — persist로 저장되어 새로고침 후에도 유지된다
      toggleAgentGroup: (key) =>
        set((s) => ({
          collapsedAgentGroups: s.collapsedAgentGroups.includes(key)
            ? s.collapsedAgentGroups.filter((k) => k !== key)
            : [...s.collapsedAgentGroups, key],
        })),
    }),
    {
      name: STORAGE_KEY,
      // Design Ref: sidebar-agent-list §6 — 타입이 틀린 저장값이 초기값을 덮어써 사이드바가 깨지지 않도록 유효한 키만 남긴다
      merge: (persisted, current) => {
        const saved = (persisted ?? {}) as Partial<LayoutState>;
        const raw: unknown = saved.collapsedAgentGroups;
        return {
          ...current,
          ...saved,
          collapsedAgentGroups: Array.isArray(raw)
            ? raw.filter((k): k is SidebarAgentGroupKey => VALID_GROUP_KEYS.includes(k))
            : current.collapsedAgentGroups,
        };
      },
    }
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
