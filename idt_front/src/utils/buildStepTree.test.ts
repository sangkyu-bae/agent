// subagent-step-observability Design §5.2 / §8.3 F1~F3
import { describe, it, expect } from 'vitest';
import { buildStepTree, countDescendants } from './buildStepTree';
import type { StepDto } from '@/types/agentRunAdmin';

const step = (
  id: string,
  step_index: number,
  parent_step_id: string | null = null,
  depth = 0,
): StepDto => ({
  id,
  step_index,
  node_name: `node-${id}`,
  node_type: 'WORKER',
  status: 'SUCCESS',
  input_summary: null,
  output_summary: null,
  started_at: '2026-10-06T07:32:16Z',
  ended_at: null,
  latency_ms: 10,
  error_text: null,
  llm_calls: [],
  tool_calls: [],
  parent_step_id,
  depth,
});

const ids = (nodes: ReturnType<typeof buildStepTree>) => nodes.map((n) => n.step.id);

describe('buildStepTree', () => {
  it('F1: parent 가 모두 null 이면 평면 루트 목록', () => {
    const tree = buildStepTree([step('a', 1), step('b', 2), step('c', 3)]);
    expect(ids(tree)).toEqual(['a', 'b', 'c']);
    expect(tree.every((n) => n.children.length === 0)).toBe(true);
  });

  it('F2: 서브에이전트 아래 자식, 손자까지 중첩하고 step_index 순서를 지킨다', () => {
    const tree = buildStepTree([
      step('s1', 1),
      step('w1', 2),
      step('c1', 3, 'w1', 1),
      step('w2', 4, 'w1', 1),
      step('g1', 5, 'w2', 2),
      step('c2', 6, 'w1', 1),
      step('s2', 7),
    ]);
    expect(ids(tree)).toEqual(['s1', 'w1', 's2']);
    const w1 = tree[1];
    expect(ids(w1.children)).toEqual(['c1', 'w2', 'c2']);
    expect(ids(w1.children[1].children)).toEqual(['g1']);
  });

  it('F2: 입력 순서가 섞여 있어도 step_index 로 정렬한다', () => {
    const tree = buildStepTree([step('c1', 3, 'w1', 1), step('w1', 2), step('s1', 1)]);
    expect(ids(tree)).toEqual(['s1', 'w1']);
    expect(ids(tree[1].children)).toEqual(['c1']);
  });

  it('F3: 부모가 목록에 없으면 최상위로 승격한다', () => {
    const tree = buildStepTree([step('s1', 1), step('orphan', 2, 'missing', 1)]);
    expect(ids(tree)).toEqual(['s1', 'orphan']);
  });

  it('자기 자신을 부모로 가리키는 이상 데이터도 최상위로 둔다', () => {
    const tree = buildStepTree([step('x', 1, 'x', 1)]);
    expect(ids(tree)).toEqual(['x']);
  });

  it('G-2: 두 노드 이상의 순환(A→B→A)도 유실 없이 최상위로 승격한다', () => {
    const tree = buildStepTree([
      step('s1', 1),
      step('a', 2, 'b', 1),
      step('b', 3, 'a', 1),
      step('c', 4, 'a', 2),
    ]);
    const all: string[] = [];
    const walk = (nodes: ReturnType<typeof buildStepTree>) =>
      nodes.forEach((n) => {
        all.push(n.step.id);
        walk(n.children);
      });
    walk(tree);
    expect(all.sort()).toEqual(['a', 'b', 'c', 's1']);
    expect(ids(tree)).toContain('a');
  });

  it('countDescendants: 직속과 모든 하위를 센다', () => {
    const tree = buildStepTree([
      step('w1', 1),
      step('c1', 2, 'w1', 1),
      step('w2', 3, 'w1', 1),
      step('g1', 4, 'w2', 2),
    ]);
    expect(countDescendants(tree[0])).toBe(3);
    expect(countDescendants(tree[0].children[0])).toBe(0);
  });
});
