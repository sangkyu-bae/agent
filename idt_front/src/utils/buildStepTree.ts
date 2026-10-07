// subagent-step-observability Design §5.2 — 평면 step 목록을 parent_step_id 로 묶는다.
// API 는 평면 목록을 유지하고(D-06), 트리 조립은 표현 계층이 맡는다.
import type { StepDto, StepTreeNode } from '@/types/agentRunAdmin';

/**
 * 부모 체인을 거슬러 올라가다 자기 자신을 다시 만나면 순환이다.
 * 다른 곳의 순환에 갇히지 않도록 방문 집합으로 멈춘다 (Design §6).
 */
const closesCycle = (id: string, byId: Map<string, StepDto>): boolean => {
  const seen = new Set<string>();
  let cursor = byId.get(id)?.parent_step_id ?? null;
  while (cursor && !seen.has(cursor)) {
    if (cursor === id) return true;
    seen.add(cursor);
    cursor = byId.get(cursor)?.parent_step_id ?? null;
  }
  return false;
};

/**
 * steps → 트리. step_index 오름차순을 형제 순서로 쓴다.
 * 부모가 목록에 없거나(기록 실패) 순환(자기참조 포함)이면 최상위로 승격한다(D-07).
 */
export const buildStepTree = (steps: StepDto[]): StepTreeNode[] => {
  const ordered = [...steps].sort((a, b) => a.step_index - b.step_index);
  const byId = new Map(ordered.map((step) => [step.id, step]));
  const nodes = new Map<string, StepTreeNode>(
    ordered.map((step) => [step.id, { step, children: [] }]),
  );
  const roots: StepTreeNode[] = [];
  for (const step of ordered) {
    const node = nodes.get(step.id)!;
    const parentId = step.parent_step_id;
    const parent =
      parentId && !closesCycle(step.id, byId) ? nodes.get(parentId) : undefined;
    if (parent) {
      parent.children.push(node);
    } else {
      roots.push(node);
    }
  }
  return roots;
};

/** 직속 자식과 모든 하위 step 수 — "하위 N" 배지용 */
export const countDescendants = (node: StepTreeNode): number =>
  node.children.reduce((sum, child) => sum + 1 + countDescendants(child), 0);
