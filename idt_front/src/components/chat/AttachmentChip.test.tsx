// chat-image-attachment Design §5.3 — 첨부 칩(엑셀/이미지) 단위
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import AttachmentChip from './AttachmentChip';
import type { PendingAttachment } from '@/types/agentAttachment';

const excel: PendingAttachment = {
  id: 'f1',
  ref: { type: 'excel', file_id: 'f1' },
  name: 'sales.xlsx',
};
const image: PendingAttachment = {
  id: 'f2',
  ref: { type: 'image', file_id: 'f2' },
  name: 'shot.png',
  previewUrl: 'blob:preview',
};

describe('AttachmentChip', () => {
  it('이미지는 썸네일과 파일명을 보여준다', () => {
    render(<AttachmentChip attachment={image} onRemove={vi.fn()} />);
    const img = screen.getByRole('img', { name: 'shot.png 미리보기' });
    expect(img).toHaveAttribute('src', 'blob:preview');
    expect(screen.getByText('shot.png')).toBeInTheDocument();
  });

  it('엑셀은 썸네일 없이 파일명을 보여준다', () => {
    render(<AttachmentChip attachment={excel} onRemove={vi.fn()} />);
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByText('sales.xlsx')).toBeInTheDocument();
  });

  it('제거 버튼은 파일명을 포함한 aria-label 로 id 를 넘긴다', async () => {
    const onRemove = vi.fn();
    render(<AttachmentChip attachment={image} onRemove={onRemove} />);
    await userEvent.click(screen.getByRole('button', { name: '첨부 제거: shot.png' }));
    expect(onRemove).toHaveBeenCalledWith('f2');
  });

  it('업로드 중에는 제거 버튼을 숨기고 상태를 표시한다', () => {
    render(<AttachmentChip attachment={image} uploading onRemove={vi.fn()} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText('업로드 중…')).toBeInTheDocument();
  });
});
