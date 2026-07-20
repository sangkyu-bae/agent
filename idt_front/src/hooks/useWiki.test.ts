import { renderHook, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import {
  useApproveArticle,
  useCreateWiki,
  useDistillWiki,
  useWikiList,
  useWikiTree,
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

describe('useWikiTree (wiki-user-facing)', () => {
  it('path 그룹 트리를 조회한다', async () => {
    const { result } = renderHook(() => useWikiTree('agent-1'), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total).toBe(2);
    expect(result.current.data?.groups[0].path).toBe('여신/한도');
    expect(result.current.data?.groups[1].path).toBeNull();
  });

  it('agentId가 비면 조회하지 않는다', () => {
    const { result } = renderHook(() => useWikiTree(''), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useCreateWiki (wiki-user-facing)', () => {
  it('작성하면 human/approved 문서가 생성된다', async () => {
    const { result } = renderHook(() => useCreateWiki(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      agent_id: 'agent-1', title: '용어 정의', content: '본문', path: '여신',
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.source_type).toBe('human');
    expect(result.current.data?.status).toBe('approved');
    expect(result.current.data?.path).toBe('여신');
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
