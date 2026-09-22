// approval-gate Check G12 — UTC 명시 시각의 로컬 표시
import { describe, expect, it } from 'vitest';
import { formatLocalDateTime } from './formatters';

describe('formatLocalDateTime', () => {
  it('빈 값은 빈 문자열', () => {
    expect(formatLocalDateTime(null)).toBe('');
    expect(formatLocalDateTime(undefined)).toBe('');
    expect(formatLocalDateTime('')).toBe('');
  });

  it('잘못된 값은 빈 문자열', () => {
    expect(formatLocalDateTime('not-a-date')).toBe('');
  });

  it('+00:00 과 Z 는 같은 순간으로 해석된다', () => {
    expect(formatLocalDateTime('2026-09-21T15:00:00+00:00')).toBe(
      formatLocalDateTime('2026-09-21T15:00:00Z'),
    );
  });

  it('UTC 명시 시각은 naive 문자열과 다르게 해석된다 (G12 의 원인)', () => {
    // naive 는 브라우저가 로컬로 읽는다. UTC 가 아닌 환경에서는 두 결과가 다르다.
    const offsetMin = new Date('2026-09-21T15:00:00').getTimezoneOffset();
    if (offsetMin !== 0) {
      expect(formatLocalDateTime('2026-09-21T15:00:00Z')).not.toBe(
        formatLocalDateTime('2026-09-21T15:00:00'),
      );
    }
  });
});
