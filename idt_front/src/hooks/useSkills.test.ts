import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import {
  useSkills,
  useSkill,
  useCreateSkill,
  useDeleteSkill,
  useForkSkill,
} from './useSkills';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useSkills hooks', () => {
  it('useSkills: 목록을 불러온다', async () => {
    const { result } = renderHook(() => useSkills({ scope: 'all' }), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total).toBe(2);
    expect(result.current.data?.skills[0].name).toBe('환율 계산기');
  });

  it('useSkill: id가 null이면 호출하지 않는다', async () => {
    const { result } = renderHook(() => useSkill(null), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('useSkill: 상세를 불러온다', async () => {
    const { result } = renderHook(() => useSkill('skill-1'), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.instruction).toBe('환율 변환 요청 시 ...');
  });

  it('useCreateSkill: 생성 성공', async () => {
    const { result } = renderHook(() => useCreateSkill(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      name: 'n',
      description: 'd',
      instruction: 'i',
      script_type: 'none',
      visibility: 'private',
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe('skill-new');
  });

  it('useDeleteSkill: 삭제 성공', async () => {
    let deleted = false;
    server.use(
      http.delete('*/api/v1/skills/:id', () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { result } = renderHook(() => useDeleteSkill(), {
      wrapper: createWrapper(),
    });
    result.current.mutate('skill-1');
    await waitFor(() => expect(deleted).toBe(true));
  });

  it('useForkSkill: 포크 성공', async () => {
    const { result } = renderHook(() => useForkSkill(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ id: 'skill-2', data: {} });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.forked_from).toBe('skill-2');
  });
});
