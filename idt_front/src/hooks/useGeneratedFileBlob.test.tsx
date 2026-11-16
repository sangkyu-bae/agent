// Design Ref: document-file-preview §5.3 — blob 조회 훅: enabled·4xx 무재시도·재오픈 캐시
import { afterEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

import { ApiError } from '@/services/api/ApiError';
import { documentExtractorService } from '@/services/documentExtractorService';
import { useGeneratedFileBlob } from './useGeneratedFileBlob';

vi.mock('@/services/documentExtractorService', () => ({
  documentExtractorService: { fetchGeneratedFileBlob: vi.fn() },
}));

const fetchBlob = vi.mocked(documentExtractorService.fetchGeneratedFileBlob);

const makeWrapper = () => {
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
};

afterEach(() => vi.clearAllMocks());

describe('useGeneratedFileBlob', () => {
  it('fileId가 null이면 조회하지 않는다', () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useGeneratedFileBlob(null), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
    expect(fetchBlob).not.toHaveBeenCalled();
  });

  it('fileId가 있으면 blob을 돌려준다', async () => {
    const blob = new Blob(['abc']);
    fetchBlob.mockResolvedValue(blob);
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useGeneratedFileBlob('f1'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBe(blob);
    expect(fetchBlob).toHaveBeenCalledWith('f1');
  });

  it('4xx는 재시도하지 않는다', async () => {
    fetchBlob.mockRejectedValue(new ApiError('gone', 404));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useGeneratedFileBlob('f1'), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(fetchBlob).toHaveBeenCalledTimes(1);
  });

  it('같은 파일을 다시 열면 캐시를 쓴다 (Plan FR-03)', async () => {
    fetchBlob.mockResolvedValue(new Blob(['abc']));
    const { wrapper } = makeWrapper();
    const first = renderHook(() => useGeneratedFileBlob('f1'), { wrapper });
    await waitFor(() => expect(first.result.current.isSuccess).toBe(true));
    first.unmount();

    const second = renderHook(() => useGeneratedFileBlob('f1'), { wrapper });
    expect(second.result.current.isSuccess).toBe(true);
    expect(fetchBlob).toHaveBeenCalledTimes(1);
  });
});
