import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import {
  useMcpServers,
  useCreateMcpServer,
  useUpdateMcpServer,
  useDeleteMcpServer,
  useTestMcpConnection,
} from '@/hooks/useMcpServers';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useMcpServers', () => {
  it('MCP-1: 서버 목록 조회 성공', async () => {
    const { result } = renderHook(() => useMcpServers(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].name).toBe('Naver Search');
    expect(result.current.data?.total).toBe(1);
  });
});

describe('useCreateMcpServer', () => {
  it('MCP-2: 등록 성공', async () => {
    const { result } = renderHook(() => useCreateMcpServer(), { wrapper: createWrapper() });
    result.current.mutate({
      user_id: '1',
      name: 'New',
      description: 'd',
      endpoint: 'https://e/mcp',
      transport: 'sse',
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe('srv-new');
  });
});

describe('useUpdateMcpServer', () => {
  it('MCP-3: 수정 성공', async () => {
    const { result } = renderHook(() => useUpdateMcpServer(), { wrapper: createWrapper() });
    result.current.mutate({ id: 'srv-1', data: { name: '바뀐이름' } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.name).toBe('바뀐이름');
  });
});

describe('useDeleteMcpServer', () => {
  it('MCP-4: 삭제 성공', async () => {
    const { result } = renderHook(() => useDeleteMcpServer(), { wrapper: createWrapper() });
    result.current.mutate('srv-1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});

describe('useTestMcpConnection', () => {
  it('MCP-5: 연결 테스트 성공 — 도구 목록 반환', async () => {
    const { result } = renderHook(() => useTestMcpConnection(), { wrapper: createWrapper() });
    result.current.mutate('srv-1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.ok).toBe(true);
    expect(result.current.data?.tools?.[0].name).toBe('search');
  });

  it('MCP-6: 연결 실패 — ok:false 본문', async () => {
    server.use(
      http.post('*/api/v1/mcp-registry/:id/test', () =>
        HttpResponse.json({ ok: false, error: 'connection refused' }),
      ),
    );
    const { result } = renderHook(() => useTestMcpConnection(), { wrapper: createWrapper() });
    result.current.mutate('srv-1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.ok).toBe(false);
    expect(result.current.data?.error).toContain('connection refused');
  });
});

// API_ENDPOINTS 상수 무결성 (계약 동기화 확인)
describe('MCP 엔드포인트 상수', () => {
  it('MCP-7: 경로 구성', () => {
    expect(API_ENDPOINTS.MCP_SERVERS).toBe('/api/v1/mcp-registry');
    expect(API_ENDPOINTS.MCP_SERVER_DETAIL('x')).toBe('/api/v1/mcp-registry/x');
    expect(API_ENDPOINTS.MCP_SERVER_TEST('x')).toBe('/api/v1/mcp-registry/x/test');
  });
});
