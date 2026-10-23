import { describe, expect, it } from 'vitest';

import { cn } from './cn';

describe('cn', () => {
  it('문자열을 공백으로 합친다', () => {
    expect(cn('a', 'b', 'c')).toBe('a b c');
  });

  it('false·null·undefined·빈 문자열을 제거한다', () => {
    expect(cn('a', false, null, undefined, '', 'b')).toBe('a b');
  });

  it('조건식 결과를 그대로 받는다', () => {
    const active = true;
    const disabled = false;
    expect(cn('base', active && 'on', disabled && 'off')).toBe('base on');
  });

  it('인자가 없으면 빈 문자열을 반환한다', () => {
    expect(cn()).toBe('');
  });
});
