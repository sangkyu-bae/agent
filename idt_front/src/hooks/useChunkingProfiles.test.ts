/**
 * useActiveChunkingProfiles 테스트 (kb-profile-selector Design §8.3)
 */
import { renderHook, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import type { ChunkingProfile } from '@/types/chunkingProfile';
import {
  useActiveChunkingProfiles,
  useDeleteChunkingProfile,
} from './useChunkingProfiles';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const profile: ChunkingProfile = {
  profile_id: 'prof-1',
  name: '금융 조항 기본',
  description: null,
  boundary_rules: [],
  parent_chunk_size: 2000,
  chunk_size: 500,
  chunk_overlap: 50,
  is_default: true,
  summary_llm_model_id: null,
  created_at: null,
  updated_at: null,
};

const countListCalls = () => {
  const counter = { calls: 0 };
  server.use(
    http.get('*/api/v1/chunking/profiles', () => {
      counter.calls += 1;
      return HttpResponse.json({ profiles: [profile], total: 1 });
    }),
  );
  return counter;
};

describe('useActiveChunkingProfiles', () => {
  it('H1: profiles 배열을 반환한다', async () => {
    countListCalls();
    const { result } = renderHook(() => useActiveChunkingProfiles(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([profile]);
  });

  it('H2: enabled=false면 호출하지 않는다', async () => {
    const counter = countListCalls();
    const { result } = renderHook(
      () => useActiveChunkingProfiles({ enabled: false }),
      { wrapper: createWrapper() },
    );

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(result.current.fetchStatus).toBe('idle');
    expect(counter.calls).toBe(0);
  });

  it('H3: 관리자 프로파일 변경 시 일반 목록도 다시 조회한다', async () => {
    const counter = countListCalls();
    server.use(
      http.delete('*/api/v1/admin/chunking/profiles/:id', () =>
        HttpResponse.json({ profile_id: 'prof-1', message: 'deleted' }),
      ),
    );
    const { result } = renderHook(
      () => ({
        list: useActiveChunkingProfiles(),
        remove: useDeleteChunkingProfile(),
      }),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

    result.current.remove.mutate('prof-1');

    await waitFor(() => expect(counter.calls).toBe(2));
  });
});
