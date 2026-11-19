// Design Ref: source-passage-viewer §5.4 — 정규화 매칭 → 앞뒤 앵커 매칭.
// 문자열 완전일치는 쓰지 않는다: 파서 추출본과 렌더 텍스트는 공백·줄바꿈·하이픈이 다르다
// (2026-07 문서추출기 하이라이트 실패 교훈).
import type { TextRange } from '@/types/sourceViewer';

/** 앵커 길이(정규화 문자 수). 구절이 앵커 2개보다 길 때만 앵커 매칭을 쓴다. */
const ANCHOR = 40;
/** 앵커 사이 길이가 구절 길이의 이 배수 범위를 벗어나면 다른 곳으로 본다. */
const SPAN_MIN = 0.5;
const SPAN_MAX = 1.5;

const WHITESPACE = /\s/;
const SOFT_HYPHEN = '­';

export interface NormalizedText {
  norm: string;
  /** map[i] = norm[i] 가 나온 원문 위치 */
  map: number[];
}

/** 하이픈 뒤에 공백만 이어지다 줄바꿈이 나오면 줄끝 하이픈이다. */
const isLineEndHyphen = (text: string, i: number): boolean => {
  for (let j = i + 1; j < text.length && WHITESPACE.test(text[j]); j += 1) {
    if (text[j] === '\n') return true;
  }
  return false;
};

export const normalizeWithMap = (text: string): NormalizedText => {
  let norm = '';
  const map: number[] = [];
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (WHITESPACE.test(c) || c === SOFT_HYPHEN) continue;
    if (c === '-' && isLineEndHyphen(text, i)) continue;
    for (const ch of c.normalize('NFKC')) {
      if (WHITESPACE.test(ch)) continue;
      norm += ch;
      map.push(i);
    }
  }
  return { norm, map };
};

const toRange = ({ map }: NormalizedText, start: number, end: number): TextRange => ({
  start: map[start],
  end: map[end - 1] + 1,
});

const anchorMatch = (hay: NormalizedText, needle: string): TextRange | null => {
  if (needle.length <= ANCHOR * 2) return null;
  const head = hay.norm.indexOf(needle.slice(0, ANCHOR));
  if (head < 0) return null;
  // 뒤 앵커는 허용 길이 안의 마지막 출현 — 반복 문자 구간에서 끝을 짧게 자르지 않는다.
  const limit = head + Math.floor(needle.length * SPAN_MAX) - ANCHOR;
  const tail = hay.norm.lastIndexOf(needle.slice(-ANCHOR), limit);
  if (tail < head + ANCHOR) return null;
  const span = tail + ANCHOR - head;
  if (span < needle.length * SPAN_MIN) return null;
  return toRange(hay, head, tail + ANCHOR);
};

/** haystack 원문에서 needle 이 차지하는 범위. 못 찾으면 null. */
export const findPassage = (haystack: string, needle: string): TextRange | null => {
  const target = normalizeWithMap(needle).norm;
  if (!target) return null;
  const hay = normalizeWithMap(haystack);
  const exact = hay.norm.indexOf(target);
  if (exact >= 0) return toRange(hay, exact, exact + target.length);
  return anchorMatch(hay, target);
};
