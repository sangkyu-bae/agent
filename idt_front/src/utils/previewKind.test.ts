// Design Ref: document-file-preview §5.3 — 파일명 확장자 → 미리보기 종류
import { describe, expect, it } from 'vitest';

import { previewKindOf } from './previewKind';

describe('previewKindOf', () => {
  it.each([
    ['수집결과.xlsx', 'xlsx'],
    ['보고서.docx', 'docx'],
    ['보고서.pdf', 'pdf'],
    ['RESULT.XLSX', 'xlsx'],
    ['Report.DocX', 'docx'],
    ['a.b.PDF', 'pdf'],
  ])('%s → %s', (filename, kind) => {
    expect(previewKindOf(filename)).toBe(kind);
  });

  it.each(['보고서.hwp', '메모.txt', 'docx', 'archive.docx.zip', '', '보고서.doc'])(
    '미리보기 대상이 아니면 null (%s)',
    (filename) => {
      expect(previewKindOf(filename)).toBeNull();
    },
  );
});
