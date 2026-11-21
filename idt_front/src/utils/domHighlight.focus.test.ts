// answer-citation-verification §5.2 FR-14 — 근거 문장은 진하게(data-spv-focus), 청크 나머지는 옅게.
import { describe, expect, it } from 'vitest';

import { highlightWithFocus, setCurrentWithFocus } from './domHighlight';

const root = (html: string) => {
  const el = document.createElement('div');
  el.innerHTML = html;
  return el;
};
const text = (marks: HTMLElement[] | null) => (marks ?? []).map((m) => m.textContent).join('');

describe('highlightWithFocus', () => {
  const html = '<p>가계대출 총량 목표를 경상성장률 이내로 관리한다. 은행은 분기별로 제출한다.</p>';

  it('청크 mark 와 근거 문장 mark 를 따로 돌려주고 근거 mark 에 data-spv-focus', () => {
    const el = root(html);
    const { marks, focusMarks } = highlightWithFocus(
      el,
      ['가계대출 총량 목표를 경상성장률 이내로 관리한다. 은행은 분기별로 제출한다.'],
      ['경상성장률 이내로 관리한다'],
    );
    expect(text(marks[0])).toContain('은행은 분기별로');
    expect(text(focusMarks[0])).toBe('경상성장률 이내로 관리한다');
    expect(focusMarks[0]!.every((m) => m.dataset.spvFocus === 'true')).toBe(true);
    expect(el.textContent).toBe('가계대출 총량 목표를 경상성장률 이내로 관리한다. 은행은 분기별로 제출한다.');
  });

  it('focus 가 없거나 못 찾으면 그 구절의 focusMarks 는 null', () => {
    const { focusMarks } = highlightWithFocus(root(html), ['가계대출', '은행은'], [null, '없는 문장']);
    expect(focusMarks).toEqual([null, null]);
  });
});

describe('setCurrentWithFocus', () => {
  it('근거 문장이 있으면 그 mark 에만 aria-current(청크는 옅게 유지)', () => {
    const el = root('<p>청크 앞부분 근거 문장 청크 뒷부분</p>');
    const { marks, focusMarks } = highlightWithFocus(el, ['청크 앞부분 근거 문장 청크 뒷부분'], ['근거 문장']);
    const first = setCurrentWithFocus(marks, focusMarks, 0);
    expect(first?.textContent).toBe('근거 문장');
    const current = [...el.querySelectorAll('mark[aria-current]')].map((m) => m.textContent).join('');
    expect(current).toBe('근거 문장');
  });

  it('근거 문장이 없으면 기존처럼 청크 전체가 현재 구절', () => {
    const el = root('<p>청크 전체 본문</p>');
    const { marks, focusMarks } = highlightWithFocus(el, ['청크 전체 본문'], [null]);
    expect(setCurrentWithFocus(marks, focusMarks, 0)?.textContent).toBe('청크 전체 본문');
  });
});
