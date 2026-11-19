// Design Ref: source-passage-viewer §5.4 — 렌더된 DOM(pdf 텍스트 레이어·docx shadow DOM) 위 음영.
// 텍스트 노드를 이어 붙여 findPassage 로 범위를 찾고, 범위에 걸친 노드 조각만 <mark> 로 감싼다.
// 노드를 나누기만 하고 지우지 않아 문서 텍스트는 그대로 남는다.
import type { TextRange } from '@/types/sourceViewer';

import { findPassage } from './passageMatch';

const SKIP_PARENTS = new Set(['STYLE', 'SCRIPT']);
const WHITESPACE_ONLY = /^\s*$/;

interface TextPiece {
  node: Text;
  start: number;
}

interface WrapPlan {
  node: Text;
  from: number;
  to: number;
  passage: number;
}

const collectText = (root: Node) => {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const pieces: TextPiece[] = [];
  let text = '';
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const node = n as Text;
    if (node.parentElement && SKIP_PARENTS.has(node.parentElement.tagName)) continue;
    pieces.push({ node, start: text.length });
    text += node.data;
  }
  return { text, pieces };
};

/** range 에서 이미 다른 구절이 차지한 부분을 뺀다. */
const subtract = (range: TextRange, taken: TextRange[]): TextRange[] => {
  let parts = [range];
  for (const t of taken) {
    parts = parts.flatMap((p) => {
      if (t.end <= p.start || p.end <= t.start) return [p];
      const rest: TextRange[] = [];
      if (p.start < t.start) rest.push({ start: p.start, end: t.start });
      if (t.end < p.end) rest.push({ start: t.end, end: p.end });
      return rest;
    });
  }
  return parts;
};

const plansFor = (pieces: TextPiece[], range: TextRange, passage: number): WrapPlan[] =>
  pieces.flatMap(({ node, start }) => {
    const from = Math.max(range.start - start, 0);
    const to = Math.min(range.end - start, node.data.length);
    if (from >= to || WHITESPACE_ONLY.test(node.data.slice(from, to))) return [];
    return [{ node, from, to, passage }];
  });

const wrap = ({ node, from, to, passage }: WrapPlan): HTMLElement => {
  node.splitText(to);
  const middle = node.splitText(from);
  const mark = document.createElement('mark');
  mark.dataset.spvPassage = String(passage);
  middle.replaceWith(mark);
  mark.appendChild(middle);
  return mark;
};

/**
 * needles 순서대로 구절 위치를 찾아 감싼다. 결과는 같은 순서의 mark 목록(못 찾으면 null).
 * 겹치는 부분은 앞 구절이 먼저 차지한다.
 */
export const highlightPassages = (root: Node, needles: string[]): (HTMLElement[] | null)[] => {
  const { text, pieces } = collectText(root);
  const taken: TextRange[] = [];
  const plans: WrapPlan[] = [];
  const found = needles.map((needle, passage) => {
    const range = findPassage(text, needle);
    if (!range) return false;
    subtract(range, taken).forEach((part) => plans.push(...plansFor(pieces, part, passage)));
    taken.push(range);
    return true;
  });
  const byNode = new Map<Text, WrapPlan[]>();
  plans.forEach((p) => byNode.set(p.node, [...(byNode.get(p.node) ?? []), p]));
  const marks: HTMLElement[][] = needles.map(() => []);
  // 같은 노드는 뒤 조각부터 나눠야 앞 조각의 위치가 유지된다.
  byNode.forEach((list) =>
    [...list].sort((a, b) => b.from - a.from).forEach((plan) => marks[plan.passage].push(wrap(plan))),
  );
  const inDocumentOrder = (a: Node, b: Node) =>
    a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
  marks.forEach((list) => list.sort(inDocumentOrder));
  return found.map((ok, i) => (ok ? marks[i] : null));
};

/** 현재 구절 mark 에만 aria-current 를 단다. 스크롤 기준이 될 첫 mark 를 돌려준다. */
export const setCurrentPassage = (
  marks: (HTMLElement[] | null)[],
  index: number,
): HTMLElement | null => {
  marks.forEach((list, i) =>
    list?.forEach((m) => (i === index ? m.setAttribute('aria-current', 'true') : m.removeAttribute('aria-current'))),
  );
  return marks[index]?.[0] ?? null;
};
