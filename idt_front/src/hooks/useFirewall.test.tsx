// firewall-admin-console module-3 — 훅 (Design §8.3 #1, §10.4).
// 훅을 vi.mock 하지 않고 MSW 로 실제 서비스·인터셉터 경로를 태운다
// (authApiClient 오류는 ApiError 로 바뀌므로 그 경로를 가리면 안 된다).
import type { ReactNode } from 'react';
import { renderHook, waitFor, act } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { http, HttpResponse } from 'msw';
import { queryKeys } from '@/lib/queryKeys';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import {
  FIREWALL_BLOCKS_TWO,
  FIREWALL_BLOCK_OK_DRY_RUN,
  FIREWALL_STATUS_DRY_RUN,
  FIREWALL_UNBLOCK_OK,
  firewallError,
} from '@/__tests__/mocks/firewallMocks';
import { ApiError } from '@/services/api/ApiError';
import { useAuthStore } from '@/store/authStore';
import { useAdminNavGroups } from './useAdminNavGroups';
import {
  firewallErrorMessage,
  useBlockIp,
  useFirewallBlocks,
  useFirewallStatus,
  useUnblockIp,
} from './useFirewall';

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  useAuthStore.setState({ user: null, isAuthenticated: false });
});
afterAll(() => server.close());

const STATUS = '*/api/v1/admin/firewall/status';
const BLOCKS = '*/api/v1/admin/firewall/blocks';

describe('useFirewallStatus', () => {
  it('켜져 있으면 status 를 그대로 돌려준다', async () => {
    server.use(http.get(STATUS, () => HttpResponse.json(FIREWALL_STATUS_DRY_RUN)));
    const { result } = renderHook(() => useFirewallStatus(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(FIREWALL_STATUS_DRY_RUN);
  });

  it('404(라우터 없음)는 오류가 아니라 enabled=false 다', async () => {
    server.use(http.get(STATUS, () => HttpResponse.json({ detail: 'Not Found' }, { status: 404 })));
    const { result } = renderHook(() => useFirewallStatus(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ enabled: false });
  });

  it('그 밖의 오류는 error 로 남는다', async () => {
    server.use(http.get(STATUS, () => HttpResponse.json({ detail: 'boom' }, { status: 500 })));
    const { result } = renderHook(() => useFirewallStatus(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.data).toBeUndefined();
  });

  it('enabled=false 옵션이면 요청하지 않는다', async () => {
    let calls = 0;
    server.use(
      http.get(STATUS, () => {
        calls += 1;
        return HttpResponse.json(FIREWALL_STATUS_DRY_RUN);
      }),
    );
    const { result } = renderHook(() => useFirewallStatus({ enabled: false }), {
      wrapper: createWrapper(),
    });
    await new Promise((r) => setTimeout(r, 30));
    expect(calls).toBe(0);
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useFirewallBlocks · 변경 훅', () => {
  it('차단 목록을 가져온다', async () => {
    server.use(http.get(BLOCKS, () => HttpResponse.json(FIREWALL_BLOCKS_TWO)));
    const { result } = renderHook(() => useFirewallBlocks(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items.map((i) => i.ip)).toEqual(['172.28.10.66', '203.0.113.9']);
  });

  it('차단 요청 본문에 actor 가 없고, 성공하면 목록을 다시 조회한다', async () => {
    let listCalls = 0;
    let posted: unknown = null;
    server.use(
      http.get(BLOCKS, () => {
        listCalls += 1;
        return HttpResponse.json(FIREWALL_BLOCKS_TWO);
      }),
      http.post(BLOCKS, async ({ request }) => {
        posted = await request.json();
        return HttpResponse.json(FIREWALL_BLOCK_OK_DRY_RUN, { status: 201 });
      }),
    );
    const wrapper = createWrapper();
    const list = renderHook(() => useFirewallBlocks(), { wrapper });
    const block = renderHook(() => useBlockIp(), { wrapper });
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true));
    expect(listCalls).toBe(1);

    let response;
    await act(async () => {
      response = await block.result.current.mutateAsync({
        ip: '172.28.10.66',
        ttl_seconds: 600,
        reason: 'R02 포트 스캔',
      });
    });
    expect(response).toEqual(FIREWALL_BLOCK_OK_DRY_RUN);
    expect(posted).toEqual({ ip: '172.28.10.66', ttl_seconds: 600, reason: 'R02 포트 스캔' });
    await waitFor(() => expect(listCalls).toBe(2));
  });

  it('차단 실패는 code 를 가진 ApiError 로 온다', async () => {
    server.use(
      http.post(BLOCKS, () =>
        HttpResponse.json(
          firewallError('FORBIDDEN_WHITELIST', 'protected', { matched: '172.28.10.10/32' }),
          { status: 403 },
        ),
      ),
    );
    const { result } = renderHook(() => useBlockIp(), { wrapper: createWrapper() });
    let caught: unknown;
    await act(async () => {
      try {
        await result.current.mutateAsync({ ip: '172.28.10.10', ttl_seconds: 60, reason: 'r' });
      } catch (e) {
        caught = e;
      }
    });
    expect(caught).toBeInstanceOf(ApiError);
    expect((caught as ApiError).code).toBe('FORBIDDEN_WHITELIST');
    expect((caught as ApiError).status).toBe(403);
  });

  it('해제는 IP 경로로 DELETE 하고 목록을 다시 조회한다', async () => {
    let deletedPath = '';
    let listCalls = 0;
    server.use(
      http.get(BLOCKS, () => {
        listCalls += 1;
        return HttpResponse.json(FIREWALL_BLOCKS_TWO);
      }),
      http.delete(`${BLOCKS}/:ip`, ({ request }) => {
        deletedPath = new URL(request.url).pathname;
        return HttpResponse.json(FIREWALL_UNBLOCK_OK);
      }),
    );
    const wrapper = createWrapper();
    const list = renderHook(() => useFirewallBlocks(), { wrapper });
    const unblock = renderHook(() => useUnblockIp(), { wrapper });
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true));
    await act(async () => {
      await unblock.result.current.mutateAsync('172.28.10.66');
    });
    expect(deletedPath).toBe('/api/v1/admin/firewall/blocks/172.28.10.66');
    await waitFor(() => expect(listCalls).toBe(2));
  });
});

describe('firewallErrorMessage', () => {
  it('코드별 문구가 있으면 그것을 쓴다', () => {
    expect(firewallErrorMessage(new ApiError('raw', 403, 'FORBIDDEN_WHITELIST'), 'fb')).toBe(
      '보호 대상 주소라 차단할 수 없습니다.',
    );
    expect(firewallErrorMessage(new ApiError('raw', 502, 'FWCTL_AUDIT_ERROR'), 'fb')).toContain(
      '감사 기록에 실패',
    );
  });

  it('코드별 문구가 없으면 서버 메시지를 쓴다 (INVALID_TTL 은 상한이 들어 있다)', () => {
    expect(
      firewallErrorMessage(new ApiError('유지 시간은 1~1800초입니다', 422, 'INVALID_TTL'), 'fb'),
    ).toBe('유지 시간은 1~1800초입니다');
  });

  it('ApiError 가 아니면 기본 문구', () => {
    expect(firewallErrorMessage(new Error('x'), '기본')).toBe('기본');
    expect(firewallErrorMessage(undefined, '기본')).toBe('기본');
  });
});

describe('useAdminNavGroups — 메뉴 조건부 노출 (Plan FR-16)', () => {
  const admin = { id: 1, email: 'a@t', role: 'admin' as const, status: 'approved' as const };
  const normal = { id: 2, email: 'u@t', role: 'user' as const, status: 'approved' as const };

  it('켜져 있으면 보안 운영 그룹이 포함된다', async () => {
    useAuthStore.setState({ user: admin, isAuthenticated: true });
    server.use(http.get(STATUS, () => HttpResponse.json(FIREWALL_STATUS_DRY_RUN)));
    const { result } = renderHook(() => useAdminNavGroups(), { wrapper: createWrapper() });
    // 응답 전에는 숨긴다
    expect(result.current.some((g) => g.key === 'security')).toBe(false);
    await waitFor(() => expect(result.current.some((g) => g.key === 'security')).toBe(true));
  });

  it('꺼져 있으면(404) 보안 운영 그룹이 없다', async () => {
    useAuthStore.setState({ user: admin, isAuthenticated: true });
    let calls = 0;
    server.use(
      http.get(STATUS, () => {
        calls += 1;
        return HttpResponse.json({ detail: 'Not Found' }, { status: 404 });
      }),
    );
    const { result } = renderHook(() => useAdminNavGroups(), { wrapper: createWrapper() });
    await waitFor(() => expect(calls).toBe(1));
    await new Promise((r) => setTimeout(r, 30));
    expect(result.current.some((g) => g.key === 'security')).toBe(false);
    expect(result.current).toHaveLength(4);
  });

  it('관리자가 아니면 status 를 묻지 않는다', async () => {
    useAuthStore.setState({ user: normal, isAuthenticated: true });
    let calls = 0;
    server.use(
      http.get(STATUS, () => {
        calls += 1;
        return HttpResponse.json(FIREWALL_STATUS_DRY_RUN);
      }),
    );
    const { result } = renderHook(() => useAdminNavGroups(), { wrapper: createWrapper() });
    await new Promise((r) => setTimeout(r, 30));
    expect(calls).toBe(0);
    expect(result.current.some((g) => g.key === 'security')).toBe(false);
  });

  it('메뉴는 주기 갱신하지 않고, 방화벽 페이지의 조회만 30초마다 갱신한다 (Check G5)', async () => {
    useAuthStore.setState({ user: admin, isAuthenticated: true });
    server.use(http.get(STATUS, () => HttpResponse.json(FIREWALL_STATUS_DRY_RUN)));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const intervals = () =>
      client
        .getQueryCache()
        .find({ queryKey: queryKeys.admin.firewallStatus() })!
        .observers.map((o) => {
          const interval = o.options.refetchInterval;
          return typeof interval === 'function' ? 'poll' : interval;
        });

    const nav = renderHook(() => useAdminNavGroups(), { wrapper });
    await waitFor(() => expect(nav.result.current.some((g) => g.key === 'security')).toBe(true));
    expect(intervals()).toEqual([false]);

    renderHook(() => useFirewallStatus(), { wrapper });
    expect(intervals()).toEqual([false, 'poll']);
  });
});
