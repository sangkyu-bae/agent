// Design Ref: source-passage-viewer §5.4 — 렌더된 DOM(pdf 텍스트 레이어·docx shadow DOM) 위 음영.
// 텍스트 노드를 이어 붙여 findPassage 로 범위를 찾고, 범위에 걸친 노드 조각만 <mark> 로 감싼다.
// 노드를 나누기만 하고 지우지 않아 문서 텍스트는 그대로 남는다.
//
// 겹침(Design §12 M21, module-7 라이브 실측): parent·child 청크가 함께 검색되면 child 가 parent 안에
// 완전히 포함된다. 모든 구절 경계에서 잘라 각 조각을 그 조각을 포함하는 모든 구절에 소속시킨다
// (텍스트 뷰어 toSegments 와 같은 규칙). mark 하나가 여러 구절 목록에 들어갈 수 있다.
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
  owners: number[];
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

/** 모든 구절 경계에서 자른 조각과, 각 조각을 포함하는 구절 번호들. */
const ownedSegments = (ranges: (TextRange | null)[]) => {
  const cuts = new Set<number>();
  ranges.forEach((r) => {
    if (r) {
      cuts.add(r.start);
      cuts.add(r.end);
    }
  });
  const points = [...cuts].sort((a, b) => a - b);
  const segments: { range: TextRange; owners: number[] }[] = [];
  for (let i = 0; i < points.length - 1; i += 1) {
    const range = { start: points[i], end: points[i + 1] };
    const owners = ranges.flatMap((r, idx) => (r && r.start <= range.start && range.end <= r.end ? [idx] : []));
    if (owners.length > 0) segments.push({ range, owners });
  }
  return segments;
};

const plansFor = (pieces: TextPiece[], range: TextRange, owners: number[]): WrapPlan[] =>
  pieces.flatMap(({ node, start }) => {
    const from = Math.max(range.start - start, 0);
    const to = Math.min(range.end - start, node.data.length);
    if (from >= to || WHITESPACE_ONLY.test(node.data.slice(from, to))) return [];
    return [{ node, from, to, owners }];
  });

const wrap = ({ node, from, to, owners }: WrapPlan): HTMLElement => {
  node.splitText(to);
  const middle = node.splitText(from);
  const mark = document.createElement('mark');
  // 스타일·선택자 기준은 첫 소유 구절. 소속 전체는 반환 목록이 가진다.
  mark.dataset.spvPassage = String(owners[0]);
  middle.replaceWith(mark);
  mark.appendChild(middle);
  return mark;
};

const inDocumentOrder = (a: Node, b: Node) =>
  a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;

/** needles 순서대로 구절 위치를 찾아 감싼다. 결과는 같은 순서의 mark 목록(못 찾으면 null). */
export const highlightPassages = (root: Node, needles: string[]): (HTMLElement[] | null)[] => {
  const { text, pieces } = collectText(root);
  const ranges = needles.map((needle) => findPassage(text, needle));
  const plans = ownedSegments(ranges).flatMap(({ range, owners }) => plansFor(pieces, range, owners));

  const byNode = new Map<Text, WrapPlan[]>();
  plans.forEach((p) => byNode.set(p.node, [...(byNode.get(p.node) ?? []), p]));
  const marks: HTMLElement[][] = needles.map(() => []);
  // 같은 노드는 뒤 조각부터 나눠야 앞 조각의 위치가 유지된다.
  byNode.forEach((list) =>
    [...list].sort((a, b) => b.from - a.from).forEach((plan) => {
      const mark = wrap(plan);
      plan.owners.forEach((owner) => marks[owner].push(mark));
    }),
  );
  marks.forEach((list) => list.sort(inDocumentOrder));
  return ranges.map((r, i) => (r ? marks[i] : null));
};

/** 현재 구절 mark 에만 aria-current 를 단다. 스크롤 기준이 될 첫 mark 를 돌려준다. */
export const setCurrentPassage = (
  marks: (HTMLElement[] | null)[],
  index: number,
): HTMLElement | null => {
  // mark 가 여러 구절에 속할 수 있어 먼저 모두 지운 뒤 현재 구절만 단다.
  marks.forEach((list) => list?.forEach((m) => m.removeAttribute('aria-current')));
  marks[index]?.forEach((m) => m.setAttribute('aria-current', 'true'));
  return marks[index]?.[0] ?? null;
};
