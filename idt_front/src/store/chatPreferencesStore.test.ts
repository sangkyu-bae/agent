import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useChatPreferencesStore } from './chatPreferencesStore';

describe('useChatPreferencesStore', () => {
  beforeEach(() => {
    // reset persisted state for each test
    useChatPreferencesStore.setState({ showToolPreview: true });
    localStorage.clear();
  });

  it('defaults to true (visible)', () => {
    const { result } = renderHook(() => useChatPreferencesStore());
    expect(result.current.showToolPreview).toBe(true);
  });

  it('setShowToolPreview sets explicit value', () => {
    const { result } = renderHook(() => useChatPreferencesStore());
    act(() => result.current.setShowToolPreview(false));
    expect(result.current.showToolPreview).toBe(false);
  });

  it('toggleShowToolPreview flips value', () => {
    const { result } = renderHook(() => useChatPreferencesStore());
    act(() => result.current.toggleShowToolPreview());
    expect(result.current.showToolPreview).toBe(false);
    act(() => result.current.toggleShowToolPreview());
    expect(result.current.showToolPreview).toBe(true);
  });
});
