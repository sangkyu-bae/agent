// Design Ref: source-passage-viewer §5.4, §8.3 #1~3 — 정규화 매칭 (문자열 완전일치 금지, 2026-07 교훈)
import { describe, expect, it } from 'vitest';

import { findPassage, normalizeWithMap } from './passageMatch';

const slice = (text: string, range: { start: number; end: number } | null) =>
  range ? text.slice(range.start, range.end) : null;

describe('normalizeWithMap', () => {
  it('공백·줄바꿈을 지우고 원문 위치를 기억한다', () => {
    const { norm, map } = normalizeWithMap('가 나\n다');
    expect(norm).toBe('가나다');
    expect(map).toEqual([0, 2, 4]);
  });

  it('줄끝 하이픈을 지운다', () => {
    expect(normalizeWithMap('신용-\n평가').norm).toBe('신용평가');
  });

  // module-7 실측: 줄바꿈 유무는 추출기마다 달라(청크 "- 1 -\nI." vs pdf.js "- 1 -I.")
  // 줄끝 여부로 하이픈을 가르면 한쪽만 지워진다 → 하이픈 계열은 위치와 무관하게 양쪽 모두 지운다.
  it('하이픈 계열 문자는 위치와 무관하게 지운다', () => {
    expect(normalizeWithMap('A-1 등급').norm).toBe('A1등급');
    expect(normalizeWithMap('- 1 -\nI.').norm).toBe(normalizeWithMap('- 1 -I.').norm);
    expect(normalizeWithMap('a‐b‑c­d').norm).toBe('abcd');
  });

  // module-7 실측: 토큰 단위 청킹이 한글을 바이트 중간에서 잘라 � 가 섞인다(원문에는 없음).
  it('깨진 문자(U+FFFD)를 지운다', () => {
    expect(normalizeWithMap('�융감독원').norm).toBe('융감독원');
  });

  it('전각 문자를 반각으로 통일한다(NFKC)', () => {
    expect(normalizeWithMap('ＡＢ１２').norm).toBe('AB12');
  });
});

describe('findPassage', () => {
  const doc = '제1조(목적) 이 규정은 여신 심사의\n기준을 정한다.\n\n제2조(정의) 신용-\n평가란 차주의 상환능력을 판단하는 것을 말한다.';

  it('공백·줄바꿈이 달라도 찾고 원문 범위를 돌려준다', () => {
    const range = findPassage(doc, '이 규정은 여신 심사의 기준을 정한다.');
    expect(slice(doc, range)).toBe('이 규정은 여신 심사의\n기준을 정한다.');
  });

  it('줄끝 하이픈으로 끊긴 단어도 찾는다', () => {
    const range = findPassage(doc, '신용평가란 차주의');
    expect(slice(doc, range)).toBe('신용-\n평가란 차주의');
  });

  it('가운데 일부가 달라도 앞뒤 40자 앵커로 찾는다', () => {
    const head = '가'.repeat(45);
    const tail = '나'.repeat(45);
    const text = `서문 ${head}원문의가운데${tail} 끝`;
    const range = findPassage(text, `${head}추출본가운데${tail}`);
    expect(slice(text, range)).toBe(`${head}원문의가운데${tail}`);
  });

  it('앵커 사이 길이가 구절 길이와 너무 다르면 실패한다', () => {
    const head = '가'.repeat(45);
    const tail = '나'.repeat(45);
    const text = `${head}${'다'.repeat(400)}${tail}`;
    expect(findPassage(text, `${head}짧음${tail}`)).toBeNull();
  });

  it('청크 앞머리의 깨진 글자 조각이 있어도 나머지로 찾는다', () => {
    const range = findPassage(doc, '� 규정은 여신 심사의 기준을');
    expect(slice(doc, range)).toBe('규정은 여신 심사의\n기준을');
  });

  it('없는 구절은 null', () => {
    expect(findPassage(doc, '담보 평가 기준')).toBeNull();
  });

  it('빈 구절은 null', () => {
    expect(findPassage(doc, '  \n ')).toBeNull();
  });
});
