// chat-image-attachment Design §5.4 / §8.3 #1~#6 — ChatInput 이미지 첨부(선택·붙여넣기·드롭·비활성·칩)
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import ChatInput from './ChatInput';
import type { PendingAttachment } from '@/types/agentAttachment';

const png = (name = 'shot.png') => new File([new Uint8Array([0x89, 0x50])], name, { type: 'image/png' });
const txt = () => new File(['x'], 'note.txt', { type: 'text/plain' });

const pending: PendingAttachment[] = [
  { id: 'f1', ref: { type: 'excel', file_id: 'f1' }, name: 'sales.xlsx' },
  { id: 'f2', ref: { type: 'image', file_id: 'f2' }, name: 'shot.png', previewUrl: 'blob:p' },
];

const renderInput = (over: Partial<React.ComponentProps<typeof ChatInput>> = {}) => {
  const onAttachFiles = vi.fn();
  const onRemoveAttachment = vi.fn();
  render(
    <ChatInput
      onSend={vi.fn()}
      attachmentEnabled
      imageAttachmentEnabled
      attachments={[]}
      onAttachFiles={onAttachFiles}
      onRemoveAttachment={onRemoveAttachment}
      {...over}
    />,
  );
  return { onAttachFiles, onRemoveAttachment };
};

const pasteWithFiles = (el: HTMLElement, files: File[]) =>
  fireEvent.paste(el, {
    clipboardData: { files, items: files.map((f) => ({ kind: 'file', type: f.type })), getData: () => '' },
  });

describe('ChatInput — 이미지 첨부', () => {
  it('이미지 버튼으로 파일을 고르면 onAttachFiles 가 호출된다', async () => {
    const { onAttachFiles } = renderInput();
    const input = screen.getByTestId('image-file-input') as HTMLInputElement;
    expect(input.accept).toBe('image/png,image/jpeg,image/webp');
    expect(input.multiple).toBe(true);
    await userEvent.upload(input, [png('a.png'), png('b.png')]);
    expect(onAttachFiles).toHaveBeenCalledTimes(1);
    expect(onAttachFiles.mock.calls[0][0].map((f: File) => f.name)).toEqual(['a.png', 'b.png']);
  });

  it('엑셀 버튼은 기존대로 단일 파일을 onAttachFiles 로 넘긴다', async () => {
    const { onAttachFiles } = renderInput();
    const input = screen.getByTestId('excel-file-input') as HTMLInputElement;
    const xlsx = new File(['x'], 's.xlsx', { type: 'application/vnd.ms-excel' });
    await userEvent.upload(input, xlsx);
    expect(onAttachFiles).toHaveBeenCalledWith([xlsx]);
  });

  it('클립보드에 이미지가 있으면 가로채 onAttachFiles 를 호출한다', () => {
    const { onAttachFiles } = renderInput();
    const textarea = screen.getByPlaceholderText('상플AI에게 메시지 보내기...');
    const ev = pasteWithFiles(textarea, [png()]);
    expect(onAttachFiles).toHaveBeenCalledTimes(1);
    expect(ev).toBe(false); // preventDefault 됨 → 텍스트 삽입 없음
  });

  it('텍스트만 붙여넣으면 가로채지 않는다', () => {
    const { onAttachFiles } = renderInput();
    const textarea = screen.getByPlaceholderText('상플AI에게 메시지 보내기...');
    const ev = fireEvent.paste(textarea, { clipboardData: { files: [], items: [], getData: () => 'hi' } });
    expect(onAttachFiles).not.toHaveBeenCalled();
    expect(ev).toBe(true);
  });

  it('드롭하면 모든 파일을 onAttachFiles 로 넘긴다 (분류·안내는 페이지 담당, G-I5)', () => {
    const { onAttachFiles } = renderInput();
    const zone = screen.getByTestId('chat-input-dropzone');
    fireEvent.dragOver(zone, { dataTransfer: { types: ['Files'] } });
    expect(screen.getByText('이미지를 놓으세요')).toBeInTheDocument();
    const dropped = fireEvent.drop(zone, { dataTransfer: { files: [png('a.png'), txt()], types: ['Files'] } });
    expect(dropped).toBe(false); // 브라우저 기본 동작(파일 열기) 차단
    expect(onAttachFiles).toHaveBeenCalledTimes(1);
    expect(onAttachFiles.mock.calls[0][0].map((f: File) => f.name)).toEqual(['a.png', 'note.txt']);
    expect(screen.queryByText('이미지를 놓으세요')).not.toBeInTheDocument();
  });

  it('비전 미지원이면 버튼이 비활성이고, 드롭은 기본 동작을 막은 뒤 페이지로 넘겨 사유를 안내하게 한다', () => {
    const { onAttachFiles } = renderInput({
      imageAttachmentEnabled: false,
      imageDisabledReason: '이 에이전트의 모델은 이미지 입력을 지원하지 않습니다',
    });
    const btn = screen.getByRole('button', { name: '이미지 첨부' });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute('title', '이 에이전트의 모델은 이미지 입력을 지원하지 않습니다');
    const zone = screen.getByTestId('chat-input-dropzone');
    fireEvent.dragOver(zone, { dataTransfer: { types: ['Files'] } });
    expect(screen.queryByText('이미지를 놓으세요')).not.toBeInTheDocument(); // 드롭 안내 없음
    const dropped = fireEvent.drop(zone, { dataTransfer: { files: [png()], types: ['Files'] } });
    expect(dropped).toBe(false); // G-I5(b): 브라우저가 파일을 열지 않는다
    expect(onAttachFiles).toHaveBeenCalledTimes(1); // 페이지가 VISION_DISABLED_REASON 안내
  });

  it('업로드 중에는 전송 버튼이 비활성이다 (G-I2)', async () => {
    renderInput({ attachmentUploading: true });
    const textarea = screen.getByPlaceholderText('상플AI에게 메시지 보내기...');
    await userEvent.type(textarea, '질문');
    expect(screen.getByRole('button', { name: '전송' })).toBeDisabled();
  });

  it('첨부 칩을 모두 보여주고 ✕ 로 id 를 넘긴다', async () => {
    const { onRemoveAttachment } = renderInput({ attachments: pending });
    expect(screen.getByText('sales.xlsx')).toBeInTheDocument();
    expect(screen.getByText('shot.png')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '첨부 제거: shot.png' }));
    expect(onRemoveAttachment).toHaveBeenCalledWith('f2');
  });

  it('안내 문구가 있으면 입력창 위에 표시한다', () => {
    renderInput({ attachmentNotice: '이미지는 최대 5장까지 첨부할 수 있습니다.' });
    expect(screen.getByRole('status')).toHaveTextContent('최대 5장');
  });

  it('attachmentEnabled=false 면 이미지 버튼도 숨긴다', () => {
    renderInput({ attachmentEnabled: false });
    expect(screen.queryByRole('button', { name: '이미지 첨부' })).not.toBeInTheDocument();
  });
});
