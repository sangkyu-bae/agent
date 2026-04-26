import { renderHook, waitFor } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { useCollections, useMetadataKeys } from './useRagToolConfig';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('useCollections', () => {
  it('컬렉션 목록을 반환한다', async () => {
    const { result } = renderHook(() => useCollections(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(3);
    expect(result.current.data![0].name).toBe('documents');
    expect(result.current.data![1].name).toBe('finance_docs');
    expect(result.current.data![2].name).toBe('tech_manuals');
  });

  it('API 실패 시 isError가 true이다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.RAG_TOOL_COLLECTIONS}`, () =>
        HttpResponse.json({ message: 'Server Error' }, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useCollections(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe('useMetadataKeys', () => {
  it('컬렉션명 제공 시 키를 반환한다', async () => {
    const { result } = renderHook(() => useMetadataKeys('documents'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(3);
    expect(result.current.data![0].key).toBe('department');
  });

  it('컬렉션명 미제공 시 쿼리가 비활성이다', () => {
    const { result } = renderHook(() => useMetadataKeys(undefined), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
  });

  it('sample_values를 포함한다', async () => {
    const { result } = renderHook(() => useMetadataKeys('documents'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data![0].sample_values).toEqual(['finance', 'tech', 'hr']);
    expect(result.current.data![1].sample_values).toEqual(['policy', 'manual', 'guide']);
    expect(result.current.data![2].sample_values).toEqual(['2024', '2025', '2026']);
  });
});
