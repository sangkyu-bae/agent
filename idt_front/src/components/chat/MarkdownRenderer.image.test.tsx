// image-generation-tool Design §5.3 / §8.3 L2 #4 — 산출 파일 경로 img 는 AuthenticatedImage, 외부 URL 은 기본 img
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MarkdownRenderer from './MarkdownRenderer';

const fetchGeneratedFileBlob = vi.fn();
vi.mock('@/services/documentExtractorService', () => ({
  documentExtractorService: {
    fetchGeneratedFileBlob: (...args: unknown[]) => fetchGeneratedFileBlob(...args),
    downloadGeneratedFile: vi.fn(),
  },
}));

beforeEach(() => {
  fetchGeneratedFileBlob.mockReset();
  Object.assign(globalThis.URL, {
    createObjectURL: vi.fn(() => 'blob:generated'),
    revokeObjectURL: vi.fn(),
  });
});

describe('MarkdownRenderer 생성 이미지', () => {
  it('산출 파일 경로 이미지는 인증 fetch 로 렌더한다', async () => {
    fetchGeneratedFileBlob.mockResolvedValue(new Blob(['x'], { type: 'image/png' }));
    render(<MarkdownRenderer content={'![generated-1.png](/api/v1/document-extractor/files/abc123)'} />);

    const img = await screen.findByRole('img', { name: 'generated-1.png' });
    expect(img).toHaveAttribute('src', 'blob:generated');
    expect(fetchGeneratedFileBlob).toHaveBeenCalledWith('abc123');
  });

  it('외부 URL 이미지는 기본 img 로 두고 서비스를 호출하지 않는다', () => {
    render(<MarkdownRenderer content={'![b](https://example.com/b.png)'} />);
    expect(screen.getByRole('img', { name: 'b' })).toHaveAttribute('src', 'https://example.com/b.png');
    expect(fetchGeneratedFileBlob).not.toHaveBeenCalled();
  });
});
