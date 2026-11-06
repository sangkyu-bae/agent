import { createElement, type ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { queryKeys } from '@/lib/queryKeys';
import { ApiError } from '@/services/api/ApiError';
import { useDeleteKbDocument, useKnowledgeBases } from './useKnowledgeBases';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useKnowledgeBases', () => {
  it('지식베이스 목록을 반환한다', async () => {
    const { result } = renderHook(() => useKnowledgeBases(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(3);
    expect(result.current.data![0].kb_id).toBe('kb-public-1');
    expect(result.current.data![0].scope).toBe('PUBLIC');
    expect(result.current.data![1].collection_name).toBe('admin-coll-01');
  });

  it('API 실패 시 isError가 true이다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.KNOWLEDGE_BASES}`, () =>
        HttpResponse.json({ message: 'Server Error' }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useKnowledgeBases(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

// kb-document-management Design §5.3 — 성공·실패 모두 KB 캐시 무효화
describe('useDeleteKbDocument', () => {
  const setup = () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);
    const { result } = renderHook(() => useDeleteKbDocument('kb-1'), {
      wrapper,
    });
    return { result, invalidate };
  };

  it('문서 삭제 엔드포인트를 호출하고 KB 캐시를 무효화한다', async () => {
    const calls: string[] = [];
    server.use(
      http.delete(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_DETAIL(':kbId', ':docId')}`,
        ({ params }) => {
          calls.push(`${params.kbId}/${params.docId}`);
          return HttpResponse.json({
            kb_id: params.kbId,
            document_id: params.docId,
            filename: 'a.pdf',
            deleted_qdrant_chunks: 3,
            deleted_es_chunks: 3,
            status: 'deleted',
          });
        },
      ),
    );
    const { result, invalidate } = setup();

    let response: unknown;
    await act(async () => {
      response = await result.current.mutateAsync('doc-9');
    });

    expect(calls).toEqual(['kb-1/doc-9']);
    expect(response).toMatchObject({ document_id: 'doc-9', status: 'deleted' });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.knowledgeBases.all,
    });
  });

  it('실패해도 목록이 실제 상태를 따르도록 무효화하고 ApiError를 전달한다', async () => {
    server.use(
      http.delete(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_DETAIL(':kbId', ':docId')}`,
        () =>
          HttpResponse.json(
            { detail: '섹션 요약이 진행 중인 문서는 삭제할 수 없습니다.' },
            { status: 409 },
          ),
      ),
    );
    const { result, invalidate } = setup();

    await act(async () => {
      await result.current.mutateAsync('doc-9').catch(() => undefined);
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toBeInstanceOf(ApiError);
    expect((result.current.error as ApiError).status).toBe(409);
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.knowledgeBases.all,
    });
  });
});
