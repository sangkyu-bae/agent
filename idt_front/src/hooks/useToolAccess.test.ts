import { renderHook, waitFor, act } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import {
  useDefaultToolAccess,
  useDepartmentToolAccess,
  useReplaceToolAccess,
  useUserToolAccess,
} from './useToolAccess';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const A = 'internal:excel_export';

describe('useToolAccess', () => {
  it('기본 세트를 조회한다', async () => {
    server.use(
      http.get('*/api/v1/admin/tool-access/default', () => HttpResponse.json({ tool_ids: [A] })),
    );
    const { result } = renderHook(() => useDefaultToolAccess(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.tool_ids).toEqual([A]);
  });

  it('부서·사용자 조회는 대상이 없으면 요청하지 않는다', () => {
    const d = renderHook(() => useDepartmentToolAccess(null), { wrapper: createWrapper() });
    const u = renderHook(() => useUserToolAccess(null), { wrapper: createWrapper() });
    expect(d.result.current.fetchStatus).toBe('idle');
    expect(u.result.current.fetchStatus).toBe('idle');
  });

  it('부서 조회는 부서 id 경로로 요청한다', async () => {
    server.use(
      http.get('*/api/v1/admin/tool-access/departments/d1', () =>
        HttpResponse.json({ department_id: 'd1', department_name: '여신부', tool_ids: [A], default_tool_ids: [] }),
      ),
    );
    const { result } = renderHook(() => useDepartmentToolAccess('d1'), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.department_name).toBe('여신부');
  });

  it('교체는 대상별 PUT 경로와 tool_ids 본문으로 보낸다', async () => {
    const bodies: Record<string, unknown> = {};
    server.use(
      http.put('*/api/v1/admin/tool-access/default', async ({ request }) => {
        bodies.default = await request.json();
        return HttpResponse.json({ tool_ids: [A] });
      }),
      http.put('*/api/v1/admin/tool-access/departments/d1', async ({ request }) => {
        bodies.department = await request.json();
        return HttpResponse.json({ department_id: 'd1', department_name: 'x', tool_ids: [A], default_tool_ids: [] });
      }),
      http.put('*/api/v1/admin/tool-access/users/12', async ({ request }) => {
        bodies.user = await request.json();
        return HttpResponse.json({ user_id: 12, is_admin: false, tool_ids: [A], inherited: [] });
      }),
    );
    const { result } = renderHook(() => useReplaceToolAccess(), { wrapper: createWrapper() });
    await act(() => result.current.mutateAsync({ target: { kind: 'default' }, toolIds: [A] }));
    await act(() =>
      result.current.mutateAsync({ target: { kind: 'department', id: 'd1' }, toolIds: [A] }),
    );
    await act(() => result.current.mutateAsync({ target: { kind: 'user', id: 12 }, toolIds: [A] }));
    expect(bodies).toEqual({
      default: { tool_ids: [A] },
      department: { tool_ids: [A] },
      user: { tool_ids: [A] },
    });
  });
});
