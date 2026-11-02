// image-generation-tool Design §5.3 / §8.3 L2 #1~#3 — 인증 fetch → object URL, 실패 폴백, 해제
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import AuthenticatedImage from './AuthenticatedImage';

const fetchGeneratedFileBlob = vi.fn();
const downloadGeneratedFile = vi.fn();
vi.mock('@/services/documentExtractorService', () => ({
  documentExtractorService: {
    fetchGeneratedFileBlob: (...args: unknown[]) => fetchGeneratedFileBlob(...args),
    downloadGeneratedFile: (...args: unknown[]) => downloadGeneratedFile(...args),
  },
}));

const createObjectURL = vi.fn(() => 'blob:generated');
const revokeObjectURL = vi.fn();

beforeEach(() => {
  fetchGeneratedFileBlob.mockReset();
  downloadGeneratedFile.mockReset();
  createObjectURL.mockClear();
  revokeObjectURL.mockClear();
  Object.assign(globalThis.URL, { createObjectURL, revokeObjectURL });
});
afterEach(() => vi.clearAllMocks());

describe('AuthenticatedImage', () => {
  it('#1 마운트 시 서비스로 blob 을 받아 스켈레톤 → img(blob:) 로 바꾼다', async () => {
    fetchGeneratedFileBlob.mockResolvedValue(new Blob(['x'], { type: 'image/png' }));
    render(<AuthenticatedImage fileId="f1" alt="generated-1.png" />);
    expect(screen.getByRole('status', { name: '이미지 불러오는 중' })).toBeInTheDocument();

    const img = await screen.findByRole('img', { name: 'generated-1.png' });
    expect(img).toHaveAttribute('src', 'blob:generated');
    expect(fetchGeneratedFileBlob).toHaveBeenCalledWith('f1');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('#1b 이미지 클릭 시 파일명을 유지해 다운로드한다', async () => {
    fetchGeneratedFileBlob.mockResolvedValue(new Blob(['x'], { type: 'image/png' }));
    downloadGeneratedFile.mockResolvedValue(undefined);
    render(<AuthenticatedImage fileId="f1" alt="generated-1.png" />);
    await userEvent.click(await screen.findByRole('img', { name: 'generated-1.png' }));
    expect(downloadGeneratedFile).toHaveBeenCalledWith('f1', 'generated-1.png');
  });

  it('#2 서비스 실패(401·404·네트워크) 시 다운로드 폴백 링크를 보여준다', async () => {
    fetchGeneratedFileBlob.mockRejectedValue(new Error('404'));
    downloadGeneratedFile.mockResolvedValue(undefined);
    render(<AuthenticatedImage fileId="f1" alt="generated-1.png" />);

    const link = await screen.findByRole('link', { name: /이미지를 불러오지 못했습니다/ });
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    await userEvent.click(link);
    expect(downloadGeneratedFile).toHaveBeenCalledWith('f1', 'generated-1.png');
  });

  it('#3 언마운트 시 object URL 을 해제한다', async () => {
    fetchGeneratedFileBlob.mockResolvedValue(new Blob(['x'], { type: 'image/png' }));
    const { unmount } = render(<AuthenticatedImage fileId="f1" alt="a.png" />);
    await screen.findByRole('img');
    unmount();
    await waitFor(() => expect(revokeObjectURL).toHaveBeenCalledWith('blob:generated'));
  });
});
