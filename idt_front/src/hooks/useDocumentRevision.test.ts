// document-revision §4.2 — 개정 훅: 엔드포인트 호출 + KB 캐시 무효화
import { createElement, type ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { API_ENDPOINTS } from '@/constants/api';
import { queryKeys } from '@/lib/queryKeys';
import {
  useCheckKbRevision,
  useDocumentVersions,
  useLinkRevision,
  useRetryRevisionSync,
  useRollbackRevision,
  useUpdateRevisionMeta,
} from './useDocumentRevision';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const setup = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return { wrapper, invalidate };
};

const version = (doc: string, no: number) => ({
  document_id: doc, filename: `${doc}.pdf`, lineage_id: 'v1', version_no: no,
  version_label: null, effective_date: null, revision_status: 'active',
  sync_state: 'synced', superseded_by: null, superseded_at: null,
  revised_by: null, created_at: null,
});

describe('useCheckKbRevision', () => {
  it('파일 점검 결과를 돌려주고 캐시는 건드리지 않는다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_CHECK(':kbId')}`, () =>
        HttpResponse.json({
          check_id: 'chk', verdict: 'revision_candidate', duplicate_of: null,
          suggested_document_id: 'old', candidates: [], llm_status: 'ok',
          elapsed_ms: 10,
        }),
      ),
    );
    const { wrapper, invalidate } = setup();
    const { result } = renderHook(() => useCheckKbRevision('kb-1'), { wrapper });
    let data: unknown;
    await act(async () => {
      data = await result.current.mutateAsync(new File(['x'], 'a.pdf'));
    });
    expect(data).toMatchObject({ check_id: 'chk', verdict: 'revision_candidate' });
    expect(invalidate).not.toHaveBeenCalled();
  });
});

describe('useDocumentVersions', () => {
  it('계보 버전을 조회한다', async () => {
    server.use(
      http.get(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_VERSIONS(':kbId', ':docId')}`,
        ({ params }) =>
          HttpResponse.json({
            lineage_id: 'v1',
            versions: [version(String(params.docId), 2), version('v1', 1)],
          }),
      ),
    );
    const { wrapper } = setup();
    const { result } = renderHook(() => useDocumentVersions('kb-1', 'v2'), {
      wrapper,
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.versions.map((v) => v.version_no)).toEqual([2, 1]);
  });

  it('enabled=false 면 요청하지 않는다', () => {
    const { wrapper } = setup();
    const { result } = renderHook(
      () => useDocumentVersions('kb-1', 'v2', { enabled: false }),
      { wrapper },
    );
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('개정 관리 mutation', () => {
  const ok = (body: object) => () => HttpResponse.json(body);

  it('되돌리기·연결·메타·재반영 모두 성공 후 KB 캐시를 무효화한다', async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_ROLLBACK(':kbId', ':docId')}`,
        async ({ request }) => {
          bodies.push(await request.json());
          return HttpResponse.json({
            restored_document_id: 'v1', detached_document_id: 'v2',
            deleted_document_id: null, sync_state: 'synced',
          });
        },
      ),
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_LINK(':kbId', ':docId')}`,
        ok({ document: version('n', 2), sync_state: 'synced' }),
      ),
      http.patch(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_META(':kbId', ':docId')}`,
        ok(version('d', 1)),
      ),
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_SYNC(':kbId', ':docId')}`,
        ok({ document_id: 'd', revision_status: 'superseded', sync_state: 'synced' }),
      ),
    );
    const { wrapper, invalidate } = setup();
    const { result } = renderHook(
      () => ({
        rollback: useRollbackRevision('kb-1'),
        link: useLinkRevision('kb-1'),
        meta: useUpdateRevisionMeta('kb-1'),
        sync: useRetryRevisionSync('kb-1'),
      }),
      { wrapper },
    );

    await act(async () => {
      await result.current.rollback.mutateAsync({ documentId: 'v2', mode: 'detach' });
      await result.current.link.mutateAsync({
        documentId: 'n', supersedesDocumentId: 'o',
      });
      await result.current.meta.mutateAsync({
        documentId: 'd', body: { version_label: 'L', effective_date: null },
      });
      await result.current.sync.mutateAsync('d');
    });

    expect(bodies).toEqual([{ mode: 'detach' }]);
    expect(invalidate).toHaveBeenCalledTimes(4);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: queryKeys.knowledgeBases.all });
  });
});
