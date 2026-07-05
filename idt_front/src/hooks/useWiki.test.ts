import { renderHook, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import {
  useApproveArticle,
  useDistillWiki,
  useWikiList,
} from '@/hooks/useWiki';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useWikiList', () => {
  it('위키 목록을 조회한다', async () => {
    const { result } = renderHook(() => useWikiList(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total).toBe(2);
    expect(result.current.data?.items[0].id).toBe('w1');
  });

  it('status 필터로 조회한다', async () => {
    const { result } = renderHook(() => useWikiList({ status: 'approved' }), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items.every((a) => a.status === 'approved')).toBe(
      true,
    );
  });
});

describe('useDistillWiki', () => {
  it('정제를 실행하고 생성 개수를 반환한다', async () => {
    const { result } = renderHook(() => useDistillWiki(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ agent_id: 'agent-1', collection_name: 'policy' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.created_count).toBe(2);
  });
});

describe('useApproveArticle', () => {
  it('승인하면 status가 approved가 된다', async () => {
    const { result } = renderHook(() => useApproveArticle(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ id: 'w1', data: { reviewer_id: 'admin' } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe('approved');
  });
});
