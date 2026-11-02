// chat-image-attachment Design §5.4 / §8.3 #7 — 이미지 첨부 사전 검증 (순수 함수)
import { describe, expect, it } from 'vitest';
import {
  IMAGE_ATTACHMENT_LIMITS,
  IMAGE_REJECT_REASON,
} from '@/types/agentAttachment';
import {
  isExcelFile,
  isImageFile,
  rejectReasonMessage,
  validateImageFiles,
} from './imageAttachmentValidators';

const file = (name: string, type: string, bytes = 10) =>
  new File([new Uint8Array(bytes)], name, { type });

describe('isImageFile / isExcelFile', () => {
  it('MIME 또는 확장자로 이미지를 판별한다', () => {
    expect(isImageFile(file('a.png', 'image/png'))).toBe(true);
    expect(isImageFile(file('a.PNG', ''))).toBe(true); // MIME 비어도 확장자
    expect(isImageFile(file('a.gif', 'image/gif'))).toBe(false);
    expect(isImageFile(file('a.xlsx', 'application/vnd.ms-excel'))).toBe(false);
  });

  it('엑셀은 확장자로 판별한다', () => {
    expect(isExcelFile(file('s.xlsx', ''))).toBe(true);
    expect(isExcelFile(file('s.XLS', ''))).toBe(true);
    expect(isExcelFile(file('s.csv', ''))).toBe(false);
  });
});

describe('validateImageFiles', () => {
  it('허용 형식·크기·장수 이내면 전부 수락한다', () => {
    const files = [file('a.png', 'image/png'), file('b.jpg', 'image/jpeg'), file('c.webp', 'image/webp')];
    const out = validateImageFiles(files, 0);
    expect(out.accepted).toHaveLength(3);
    expect(out.rejected).toHaveLength(0);
  });

  it('미허용 형식은 사유와 함께 거절한다', () => {
    const out = validateImageFiles([file('a.gif', 'image/gif'), file('b.png', 'image/png')], 0);
    expect(out.accepted.map((f) => f.name)).toEqual(['b.png']);
    expect(out.rejected).toEqual([
      { file: expect.objectContaining({ name: 'a.gif' }), reason: IMAGE_REJECT_REASON.UNSUPPORTED_TYPE },
    ]);
  });

  it('장당 크기 초과는 거절한다', () => {
    const big = file('big.png', 'image/png', IMAGE_ATTACHMENT_LIMITS.maxBytes + 1);
    const out = validateImageFiles([big], 0);
    expect(out.accepted).toHaveLength(0);
    expect(out.rejected[0].reason).toBe(IMAGE_REJECT_REASON.TOO_LARGE);
  });

  it('현재 장수와 합쳐 상한을 넘는 파일은 거절한다 (앞에서부터 수락)', () => {
    const files = [file('1.png', 'image/png'), file('2.png', 'image/png'), file('3.png', 'image/png')];
    const out = validateImageFiles(files, IMAGE_ATTACHMENT_LIMITS.maxCount - 1);
    expect(out.accepted.map((f) => f.name)).toEqual(['1.png']);
    expect(out.rejected.map((r) => r.reason)).toEqual([
      IMAGE_REJECT_REASON.TOO_MANY,
      IMAGE_REJECT_REASON.TOO_MANY,
    ]);
  });

  it('빈 입력은 빈 결과', () => {
    expect(validateImageFiles([], 0)).toEqual({ accepted: [], rejected: [] });
  });
});

describe('rejectReasonMessage', () => {
  it('사유별 안내 문구를 돌려준다', () => {
    expect(rejectReasonMessage(IMAGE_REJECT_REASON.UNSUPPORTED_TYPE)).toContain('png');
    expect(rejectReasonMessage(IMAGE_REJECT_REASON.TOO_LARGE)).toContain('10MB');
    expect(rejectReasonMessage(IMAGE_REJECT_REASON.TOO_MANY)).toContain(
      String(IMAGE_ATTACHMENT_LIMITS.maxCount),
    );
  });
});
