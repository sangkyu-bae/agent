// Design Ref: answer-citation-verification §5.3 FR-12 — 본문 [n] 을 위첨자 요소로 바꾸는 remark 플러그인.
// 인용 목록에 있는 번호만 바꾸고, 코드·링크 안은 건드리지 않는다(D-09). 목록 밖 [n] 은 글자 그대로.
// mdast 노드에 data.hName='sup' 을 달아 hast 로 넘기고, 렌더러의 sup 컴포넌트가 data-citation 으로 구분한다.
// 외부 순회 유틸(unist-util-visit)은 react-markdown 의 전이 의존이라 직접 순회한다.

interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
  data?: Record<string, unknown>;
}

const MARKER = /\[(\d{1,3})\]/g;
const SKIP = new Set(['code', 'inlineCode', 'link', 'linkReference', 'definition', 'html']);

const citationNode = (no: number): MdNode => ({
  type: 'emphasis',
  data: { hName: 'sup', hProperties: { dataCitation: String(no) } },
  children: [{ type: 'text', value: String(no) }],
});

const splitText = (value: string, known: Set<number>): MdNode[] => {
  const out: MdNode[] = [];
  let cursor = 0;
  for (const match of value.matchAll(MARKER)) {
    const no = Number(match[1]);
    if (!known.has(no)) continue;
    const at = match.index ?? 0;
    if (at > cursor) out.push({ type: 'text', value: value.slice(cursor, at) });
    out.push(citationNode(no));
    cursor = at + match[0].length;
  }
  if (cursor === 0) return [{ type: 'text', value }];
  if (cursor < value.length) out.push({ type: 'text', value: value.slice(cursor) });
  return out;
};

const visit = (node: MdNode, known: Set<number>): void => {
  if (!node.children) return;
  node.children = node.children.flatMap((child) => {
    if (SKIP.has(child.type)) return [child];
    if (child.type === 'text') return splitText(child.value ?? '', known);
    visit(child, known);
    return [child];
  });
};

/** 사용: remarkPlugins={[..., [remarkCitationRefs, { nos: [1, 2] }]]} */
export const remarkCitationRefs = (options: { nos: number[] }) => {
  const known = new Set(options.nos);
  return (tree: MdNode) => {
    visit(tree, known);
  };
};
