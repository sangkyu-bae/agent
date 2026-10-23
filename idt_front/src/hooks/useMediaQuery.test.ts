import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useMediaQuery } from './useMediaQuery';

type Listener = (e: MediaQueryListEvent) => void;

const installMatchMedia = (initial: boolean) => {
  const listeners = new Set<Listener>();
  // matchMedia는 호출마다 새 객체를 돌려주므로 matches를 공유하는 단일 객체를 반환한다
  const mql = {
    matches: initial,
    media: '',
    addEventListener: (_: string, l: Listener) => listeners.add(l),
    removeEventListener: (_: string, l: Listener) => listeners.delete(l),
  };
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue(mql));
  return {
    fire: (matches: boolean) => {
      mql.matches = matches;
      listeners.forEach((l) => l({ matches } as MediaQueryListEvent));
    },
    listeners,
  };
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useMediaQuery', () => {
  it('matchMedia가 없으면 false를 반환한다', () => {
    vi.stubGlobal('matchMedia', undefined);
    const { result } = renderHook(() => useMediaQuery('(max-width: 768px)'));
    expect(result.current).toBe(false);
  });

  it('초기 matches를 반영하고 change 이벤트에 따라 갱신한다', () => {
    const mm = installMatchMedia(true);
    const { result, unmount } = renderHook(() => useMediaQuery('(max-width: 768px)'));
    expect(result.current).toBe(true);
    act(() => mm.fire(false));
    expect(result.current).toBe(false);
    unmount();
    expect(mm.listeners.size).toBe(0);
  });
});
