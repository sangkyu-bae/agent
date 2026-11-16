// Design Ref: document-file-preview §8.1 — 문서 미리보기 스토어 open/close (analysis G-09)
import { beforeEach, describe, expect, it } from 'vitest';

import { useDocumentPreviewStore } from './documentPreviewStore';

beforeEach(() => useDocumentPreviewStore.setState({ target: null }));

describe('documentPreviewStore', () => {
  it('처음에는 닫혀 있다', () => {
    expect(useDocumentPreviewStore.getState().target).toBeNull();
  });

  it('open은 target을 설정하고, 다른 파일로 다시 열면 교체한다', () => {
    const { open } = useDocumentPreviewStore.getState();
    open({ fileId: 'a', filename: 'a.docx', kind: 'docx' });
    open({ fileId: 'b', filename: 'b.pdf', kind: 'pdf' });
    expect(useDocumentPreviewStore.getState().target).toEqual({
      fileId: 'b',
      filename: 'b.pdf',
      kind: 'pdf',
    });
  });

  it('close는 target을 비운다', () => {
    useDocumentPreviewStore.getState().open({ fileId: 'a', filename: 'a.docx', kind: 'docx' });
    useDocumentPreviewStore.getState().close();
    expect(useDocumentPreviewStore.getState().target).toBeNull();
  });
});
