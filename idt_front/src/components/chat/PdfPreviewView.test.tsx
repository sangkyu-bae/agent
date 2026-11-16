// Design Ref: document-file-preview §8.2 #13 — blob URL 생성·해제
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import PdfPreviewView from './PdfPreviewView';

const createObjectURL = vi.fn<(blob: Blob) => string>(() => 'blob:mock-pdf');
const revokeObjectURL = vi.fn();

beforeEach(() => {
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }));
});
afterEach(() => {
  vi.clearAllMocks();
});

describe('PdfPreviewView', () => {
  it('application/pdf blob URL을 iframe에 넣고 unmount 시 해제한다', () => {
    const { unmount } = render(
      <PdfPreviewView blob={new Blob(['%PDF'])} filename="보고서.pdf" />,
    );

    const frame = screen.getByTitle('보고서.pdf 미리보기');
    expect(frame.tagName).toBe('IFRAME');
    expect(frame).toHaveAttribute('src', 'blob:mock-pdf');
    const passed = createObjectURL.mock.calls[0][0];
    expect(passed.type).toBe('application/pdf');

    unmount();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock-pdf');
  });
});
