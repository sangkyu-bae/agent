// Design Ref: source-passage-viewer §5.4 — 렌더된 DOM(pdf 텍스트 레이어·docx) 위 음영. 원본·텍스트 뷰어가 같은 매칭 규칙을 쓴다.
import { describe, expect, it } from 'vitest';

import { highlightPassages, setCurrentPassage } from './domHighlight';

const root = (html: string) => {
  const el = document.createElement('div');
  el.innerHTML = html;
  return el;
};

const marked = (el: HTMLElement, i: number) =>
  [...el.querySelectorAll(`mark[data-spv-passage="${i}"]`)].map((m) => m.textContent).join('');

describe('highlightPassages', () => {
  it('여러 노드에 걸친 구절을 노드별 mark 로 감싼다', () => {
    const el = root('<p>제1조 이 규정은</p><p><span>여신 심사</span>의 기준을 정한다.</p>');
    const result = highlightPassages(el, ['이 규정은 여신 심사의 기준']);
    expect(result[0]).not.toBeNull();
    expect(marked(el, 0)).toBe('이 규정은여신 심사의 기준');
    expect(el.textContent).toBe('제1조 이 규정은여신 심사의 기준을 정한다.');
  });

  it('PDF 텍스트 레이어처럼 줄끝 하이픈으로 끊긴 단어를 찾는다', () => {
    const el = root('<span>신용-</span>\n<span>평가란 차주의 상환능력</span>');
    highlightPassages(el, ['신용평가란 차주의']);
    expect(marked(el, 0)).toBe('신용-평가란 차주의');
  });

  it('못 찾은 구절은 null 이고 DOM 을 바꾸지 않는다', () => {
    const el = root('<p>본문</p>');
    const before = el.innerHTML;
    expect(highlightPassages(el, ['없는 문장'])).toEqual([null]);
    expect(el.innerHTML).toBe(before);
  });

  it('구절마다 번호를 단다', () => {
    const el = root('<p>가나다 라마바 사아자</p>');
    const result = highlightPassages(el, ['가나다', '사아자']);
    expect(result.map((r) => r?.length)).toEqual([1, 1]);
    expect(marked(el, 0)).toBe('가나다');
    expect(marked(el, 1)).toBe('사아자');
  });

  // module-7 라이브 실측: parent·child 청크가 함께 검색되면 child 가 parent 안에 완전히 포함된다.
  // "앞 구절이 먼저 차지"하면 child 는 자기 mark 가 0개라 이동해도 아무것도 강조되지 않았다.
  it('겹치는 구절은 경계에서 잘라 조각을 두 구절이 함께 가진다', () => {
    const el = root('<p>0123456789</p>');
    const result = highlightPassages(el, ['234567', '456789']);
    expect(el.textContent).toBe('0123456789');
    expect(result[0]?.map((m) => m.textContent).join('')).toBe('234567');
    expect(result[1]?.map((m) => m.textContent).join('')).toBe('456789');
    expect(el.querySelectorAll('mark')).toHaveLength(3);
  });

  it('다른 구절 안에 완전히 포함된 구절도 자기 mark 를 가진다', () => {
    const el = root('<p>가나다라마바사</p>');
    const result = highlightPassages(el, ['가나다라마바사', '다라마']);
    expect(result[1]?.map((m) => m.textContent).join('')).toBe('다라마');
    expect(result[0]?.map((m) => m.textContent).join('')).toBe('가나다라마바사');
  });
});

describe('setCurrentPassage', () => {
  it('현재 구절 mark 에만 aria-current 를 달고 첫 mark 를 돌려준다', () => {
    const el = root('<p>가나다 라마바</p>');
    const marks = highlightPassages(el, ['가나다', '라마바']);
    const first = setCurrentPassage(marks, 1);
    expect(first?.textContent).toBe('라마바');
    expect(marks[1]?.[0].getAttribute('aria-current')).toBe('true');
    expect(marks[0]?.[0].hasAttribute('aria-current')).toBe(false);
    setCurrentPassage(marks, 0);
    expect(marks[1]?.[0].hasAttribute('aria-current')).toBe(false);
  });

  it('포함된 구절로 이동하면 공유 조각이 현재 표시를 유지한다', () => {
    const el = root('<p>가나다라마바사</p>');
    const marks = highlightPassages(el, ['가나다라마바사', '다라마']);
    const first = setCurrentPassage(marks, 1);
    expect(first?.textContent).toBe('다라마');
    const current = [...el.querySelectorAll('mark[aria-current]')].map((m) => m.textContent).join('');
    expect(current).toBe('다라마');
  });
});
