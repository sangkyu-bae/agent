import { renderHook, waitFor, act } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import {
  useCollectionList,
  useCreateCollection,
  useDeleteCollection,
  useRenameCollection,
  useUpdateScope,
  useActivityLogs,
  useCollectionDocuments,
  useDocumentChunks,
} from '@/hooks/useCollections';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useCollectionList', () => {
  it('C1: 목록 조회 성공 — 3개 컬렉션 반환', async () => {
    const { result } = renderHook(() => useCollectionList(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.collections).toHaveLength(3);
    expect(result.current.data?.total).toBe(3);
  });

  it('C2: 빈 목록 응답 처리', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.COLLECTIONS}`, () =>
        HttpResponse.json({ collections: [], total: 0 }),
      ),
    );

    const { result } = renderHook(() => useCollectionList(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.collections).toHaveLength(0);
    expect(result.current.data?.total).toBe(0);
  });

  it('C3: 서버 에러 시 isError', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.COLLECTIONS}`, () =>
        HttpResponse.json({ detail: 'server error' }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useCollectionList(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useCreateCollection', () => {
  it('C4: 생성 성공', async () => {
    const { result } = renderHook(() => useCreateCollection(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        name: 'new-collection',
        vector_size: 1536,
        distance: 'Cosine',
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.message).toContain('successfully');
  });

  it('C4b: embedding_model 기반 생성 성공', async () => {
    const { result } = renderHook(() => useCreateCollection(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        name: 'embed-collection',
        embedding_model: 'text-embedding-3-small',
        distance: 'Cosine',
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.message).toContain('successfully');
  });

  it('C5: 409 충돌', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.COLLECTIONS}`, () =>
        HttpResponse.json(
          { detail: 'Collection already exists' },
          { status: 409 },
        ),
      ),
    );

    const { result } = renderHook(() => useCreateCollection(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        name: 'documents',
        vector_size: 1536,
        distance: 'Cosine',
      });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useDeleteCollection', () => {
  it('C6: 삭제 성공', async () => {
    const { result } = renderHook(() => useDeleteCollection(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate('test-collection');
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.message).toContain('successfully');
  });

  it('C7: 403 보호된 컬렉션', async () => {
    const { result } = renderHook(() => useDeleteCollection(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate('documents');
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useRenameCollection', () => {
  it('C8: 이름변경 성공', async () => {
    const { result } = renderHook(() => useRenameCollection(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({ name: 'test-collection', newName: 'renamed' });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.new_name).toBe('renamed');
  });
});

describe('useUpdateScope', () => {
  it('C8b: scope 변경 성공', async () => {
    const { result } = renderHook(() => useUpdateScope(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        name: 'test-collection',
        data: { scope: 'PUBLIC' },
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.message).toContain('successfully');
  });

  it('C8c: scope 변경 403 에러', async () => {
    server.use(
      http.patch('*/api/v1/collections/:name/permission', () =>
        HttpResponse.json(
          { detail: 'Not authorized' },
          { status: 403 },
        ),
      ),
    );

    const { result } = renderHook(() => useUpdateScope(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({
        name: 'test-collection',
        data: { scope: 'PUBLIC' },
      });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useCollectionDocuments', () => {
  it('D1: 문서 목록 정상 조회 — 3건 반환', async () => {
    const { result } = renderHook(
      () => useCollectionDocuments('test-collection'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.documents).toHaveLength(3);
    expect(result.current.data?.total_documents).toBe(3);
    expect(result.current.data?.collection_name).toBe('test-collection');
  });

  it('D2: offset/limit 파라미터 전달', async () => {
    const { result } = renderHook(
      () => useCollectionDocuments('test-collection', { offset: 0, limit: 10 }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.documents).toHaveLength(3);
  });

  it('D3: 빈 컬렉션일 때 빈 배열', async () => {
    server.use(
      http.get('*/api/v1/collections/:name/documents', () =>
        HttpResponse.json({
          collection_name: 'empty',
          documents: [],
          total_documents: 0,
          offset: 0,
          limit: 20,
        }),
      ),
    );

    const { result } = renderHook(
      () => useCollectionDocuments('empty'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.documents).toHaveLength(0);
  });

  it('D4: collectionName 빈 문자열이면 enabled=false', async () => {
    const { result } = renderHook(
      () => useCollectionDocuments(''),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useDocumentChunks', () => {
  it('D5: 청크 목록 정상 조회', async () => {
    const { result } = renderHook(
      () => useDocumentChunks('test-collection', 'doc-1'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.chunks).toHaveLength(4);
    expect(result.current.data?.chunk_strategy).toBe('parent_child');
    expect(result.current.data?.total_chunks).toBe(4);
  });

  it('D6: include_parent=true 시 parents 필드 포함', async () => {
    const { result } = renderHook(
      () => useDocumentChunks('test-collection', 'doc-1', { include_parent: true }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.parents).not.toBeNull();
    expect(result.current.data?.parents).toHaveLength(1);
    expect(result.current.data?.parents![0].children).toHaveLength(3);
  });

  it('D7: documentId가 null이면 enabled=false', async () => {
    const { result } = renderHook(
      () => useDocumentChunks('test-collection', null),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useActivityLogs', () => {
  it('C9: 이력 조회 성공 — 5개 로그', async () => {
    const { result } = renderHook(
      () => useActivityLogs({ limit: 50, offset: 0 }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.logs).toHaveLength(5);
    expect(result.current.data?.total).toBe(5);
  });

  it('C10: 필터 적용 조회', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.COLLECTION_ACTIVITY_LOG}`, ({ request }) => {
        const url = new URL(request.url);
        const collectionName = url.searchParams.get('collection_name');
        return HttpResponse.json({
          logs: [
            {
              id: 1,
              collection_name: collectionName ?? 'documents',
              action: 'CREATE',
              user_id: 'system',
              detail: null,
              created_at: '2026-04-22T10:00:00Z',
            },
          ],
          total: 1,
          limit: 50,
          offset: 0,
        });
      }),
    );

    const { result } = renderHook(
      () =>
        useActivityLogs({
          collection_name: 'documents',
          limit: 50,
          offset: 0,
        }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.logs).toHaveLength(1);
    expect(result.current.data?.logs[0].collection_name).toBe('documents');
  });
});
