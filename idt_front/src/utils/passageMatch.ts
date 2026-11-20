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
/**
 * 정규화에서 버리는 문자.
 * - 하이픈 계열(-, soft hyphen, U+2010/2011): 줄바꿈 유무가 추출기마다 달라 "줄끝 하이픈"만
 *   지우면 한쪽만 지워진다(module-7 실측: 청크 "- 1 -\nI." vs pdf.js "- 1 -I."). 위치와 무관하게 지운다.
 * - U+FFFD: 토큰 단위 청킹이 한글을 바이트 중간에서 잘라 생긴 깨진 문자. 원문에는 없다.
 */
const DROPPED = new Set(['-', '­', '‐', '‑', '�']);

export interface NormalizedText {
  norm: string;
  /** map[i] = norm[i] 가 나온 원문 위치 */
  map: number[];
}

export const normalizeWithMap = (text: string): NormalizedText => {
  let norm = '';
  const map: number[] = [];
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (WHITESPACE.test(c) || DROPPED.has(c)) continue;
    for (const ch of c.normalize('NFKC')) {
      if (WHITESPACE.test(ch) || DROPPED.has(ch)) continue;
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
