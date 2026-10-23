import { beforeEach, describe, expect, it } from 'vitest';

import { hasPersistedSidebarPreference, useLayoutStore } from './layoutStore';

describe('layoutStore — 사이드바 접기', () => {
  beforeEach(() => {
    useLayoutStore.setState({ isSidebarCollapsed: false, isChatPanelOpen: false, selectedAgentId: 'super' });
    // setState가 persist를 통해 저장하므로 그 뒤에 비운다
    localStorage.clear();
  });

  it('기본값은 펼침(false)이다', () => {
    expect(useLayoutStore.getState().isSidebarCollapsed).toBe(false);
  });

  it('toggleSidebar가 값을 뒤집고 setSidebarCollapsed가 값을 지정한다', () => {
    useLayoutStore.getState().toggleSidebar();
    expect(useLayoutStore.getState().isSidebarCollapsed).toBe(true);
    useLayoutStore.getState().toggleSidebar();
    expect(useLayoutStore.getState().isSidebarCollapsed).toBe(false);
    useLayoutStore.getState().setSidebarCollapsed(true);
    expect(useLayoutStore.getState().isSidebarCollapsed).toBe(true);
  });

  it('기존 persist 키(layout-preferences)에 저장된다', () => {
    useLayoutStore.getState().setSidebarCollapsed(true);
    const raw = localStorage.getItem('layout-preferences');
    expect(raw).not.toBeNull();
    expect(JSON.parse(raw!).state.isSidebarCollapsed).toBe(true);
    expect(JSON.parse(raw!).state.selectedAgentId).toBe('super');
  });

  it('hasPersistedSidebarPreference는 저장값 유무를 알려준다', () => {
    expect(hasPersistedSidebarPreference()).toBe(false);
    // 구 버전 저장값(필드 없음)도 false
    localStorage.setItem('layout-preferences', JSON.stringify({ state: { isChatPanelOpen: true }, version: 0 }));
    expect(hasPersistedSidebarPreference()).toBe(false);
    useLayoutStore.getState().setSidebarCollapsed(false);
    expect(hasPersistedSidebarPreference()).toBe(true);
    localStorage.setItem('layout-preferences', '{not json');
    expect(hasPersistedSidebarPreference()).toBe(false);
  });
});
