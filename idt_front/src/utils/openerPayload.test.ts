import { describe, it, expect } from 'vitest';
import { buildOpenersForSave } from './openerPayload';

describe('buildOpenersForSave', () => {
  it('strip 후 빈 항목을 제거하고 순서를 보존한다', () => {
    expect(buildOpenersForSave([' a ', '', '  ', 'b'])).toEqual(['a', 'b']);
  });

  it('빈 배열은 빈 배열', () => {
    expect(buildOpenersForSave([])).toEqual([]);
  });

  it('중복은 제거하지 않는다 (서버 422 책임)', () => {
    expect(buildOpenersForSave(['a', 'a'])).toEqual(['a', 'a']);
  });
});
