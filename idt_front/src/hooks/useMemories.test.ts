// agent-memory: 사용자 메모리 훅 계약 테스트 (MSW).
import { renderHook, waitFor } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import {
  useApproveMemory,
  useCreateMemory,
  useCreateOrgMemory,
  useDeleteMemory,
  useMemories,
  useOrgMemories,
  usePromoteMemory,
  useRejectMemory,
  useUpdateMemory,
} from '@/hooks/useMemories';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useMemories', () => {
  it('목록과 total·max_count를 조회한다', async () => {
    const { result } = renderHook(() => useMemories(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total).toBe(2);
    expect(result.current.data?.max_count).toBe(30);
    expect(result.current.data?.items[0].mem_type).toBe('profile');
  });
});

describe('useMemories(pending) — agent-memory-extraction', () => {
  it('승인 대기 목록과 pending 상한을 조회한다', async () => {
    const { result } = renderHook(() => useMemories('pending'), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.max_count).toBe(20);
    expect(result.current.data?.items[0].content).toBe('여신 기획팀으로 이동');
  });
});

describe('useApproveMemory / useRejectMemory', () => {
  it('승인하면 갱신된 메모리를 반환한다', async () => {
    const { result } = renderHook(() => useApproveMemory(), {
      wrapper: createWrapper(),
    });
    result.current.mutate(9);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(9);
  });

  it('거부가 성공한다', async () => {
    const { result } = renderHook(() => useRejectMemory(), {
      wrapper: createWrapper(),
    });
    result.current.mutate(9);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('org 스코프 (agent-memory-org-scope)', () => {
  it('부서 공유 메모리 목록과 상한을 조회한다', async () => {
    const { result } = renderHook(() => useOrgMemories(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.max_count).toBe(50);
    expect(result.current.data?.items[0].content).toBe("'한도'는 동일인 여신한도");
  });

  it('부서 메모리를 작성한다', async () => {
    const { result } = renderHook(() => useCreateOrgMemory(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ dept_id: 'd1', mem_type: 'domain_term', content: '부서 용어' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.content).toBe('부서 용어');
  });

  it('개인 메모리를 부서로 승격한다', async () => {
    const { result } = renderHook(() => usePromoteMemory(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ id: 5, deptId: 'd1' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.content).toBe('승격됨');
  });
});

describe('useCreateMemory', () => {
  it('등록하면 생성된 메모리를 반환한다', async () => {
    const { result } = renderHook(() => useCreateMemory(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ mem_type: 'domain_term', content: "'한도'는 동일인 여신한도" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.mem_type).toBe('domain_term');
    expect(result.current.data?.content).toBe("'한도'는 동일인 여신한도");
  });
});

describe('useUpdateMemory', () => {
  it('수정하면 갱신된 메모리를 반환한다', async () => {
    const { result } = renderHook(() => useUpdateMemory(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ id: 1, data: { content: '수정된 내용' } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.content).toBe('수정된 내용');
  });
});

describe('useDeleteMemory', () => {
  it('삭제가 성공한다 (204)', async () => {
    const { result } = renderHook(() => useDeleteMemory(), {
      wrapper: createWrapper(),
    });
    result.current.mutate(1);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});
