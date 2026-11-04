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

describe('layoutStore — 에이전트 그룹 접기 (sidebar-agent-list)', () => {
  beforeEach(() => {
    useLayoutStore.setState({ collapsedAgentGroups: [] });
    localStorage.clear();
  });

  it('ST1: 기본값은 빈 배열(모두 펼침)이다', () => {
    expect(useLayoutStore.getState().collapsedAgentGroups).toEqual([]);
  });

  it('ST2: toggleAgentGroup은 키를 추가했다가 다시 제거한다', () => {
    useLayoutStore.getState().toggleAgentGroup('owned');
    expect(useLayoutStore.getState().collapsedAgentGroups).toEqual(['owned']);
    useLayoutStore.getState().toggleAgentGroup('pinned');
    expect(useLayoutStore.getState().collapsedAgentGroups).toEqual(['owned', 'pinned']);
    useLayoutStore.getState().toggleAgentGroup('owned');
    expect(useLayoutStore.getState().collapsedAgentGroups).toEqual(['pinned']);
  });

  it('ST3: 접기 상태가 layout-preferences에 저장된다', () => {
    useLayoutStore.getState().toggleAgentGroup('forked');
    const raw = localStorage.getItem('layout-preferences');
    expect(JSON.parse(raw!).state.collapsedAgentGroups).toEqual(['forked']);
  });

  it('ST4: 필드가 없는 구 저장값을 복원해도 빈 배열로 동작한다', async () => {
    localStorage.setItem(
      'layout-preferences',
      JSON.stringify({ state: { isSidebarCollapsed: true, selectedAgentId: 'super' }, version: 0 }),
    );
    await useLayoutStore.persist.rehydrate();
    expect(useLayoutStore.getState().collapsedAgentGroups).toEqual([]);
    expect(useLayoutStore.getState().isSidebarCollapsed).toBe(true);
  });

  it('ST5: 타입이 틀린 저장값(null·문자열·알 수 없는 키)은 무시하고 유효한 키만 남긴다', async () => {
    const restore = async (value: unknown) => {
      localStorage.setItem(
        'layout-preferences',
        JSON.stringify({ state: { collapsedAgentGroups: value }, version: 0 }),
      );
      await useLayoutStore.persist.rehydrate();
      return useLayoutStore.getState().collapsedAgentGroups;
    };
    expect(await restore(null)).toEqual([]);
    expect(await restore('owned')).toEqual([]);
    expect(await restore(['owned', 'bogus', 3])).toEqual(['owned']);
  });
});
