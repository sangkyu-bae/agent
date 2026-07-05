import type { Node, Edge } from '@xyflow/react';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';
import { DEFAULT_LAYOUT, EDGE_COLOR, NODE_ID, type ResourceKind } from './constants';

/**
 * 폼 상태 → React Flow 노드/엣지 변환 순수 함수.
 * agent-builder-visual-canvas Design §2.2.
 */

export interface AgentNodeData extends Record<string, unknown> {
  name: string;
  description: string;
  systemPrompt: string;
  onEditInForm?: () => void;
}

export interface ResourceNodeData extends Record<string, unknown> {
  kind: ResourceKind;
  /** 표시 항목 (도구명/서브에이전트명, 모델은 [라벨]). */
  items: string[];
  /** 플레이스홀더(스킬/미들웨어)는 액션 비활성. */
  disabled: boolean;
  onAction?: () => void;
}

/** model_name → "provider:model_name" 라벨. 미매칭 시 raw, 빈값 시 "모델 미선택". */
export function buildModelLabel(model: string, models?: LlmModel[]): string {
  const matched = models?.find((m) => m.model_name === model);
  if (matched) return `${matched.provider}:${matched.model_name}`;
  return model || '모델 미선택';
}

export function buildNodes(
  form: AgentBuilderFormData,
  catalogTools?: CatalogTool[],
  models?: LlmModel[],
): Node[] {
  const toolNames = (catalogTools ?? [])
    .filter((t) => form.tools.includes(t.tool_id))
    .map((t) => t.name);
  const subNames = (form.subAgents ?? []).map((s) => s.name);

  const agentData: AgentNodeData = {
    name: form.name,
    description: form.description,
    systemPrompt: form.systemPrompt,
  };

  const resource = (kind: ResourceKind, items: string[], disabled: boolean): Node => ({
    id: NODE_ID[kind],
    type: 'resource',
    position: { ...DEFAULT_LAYOUT[kind] },
    data: { kind, items, disabled } satisfies ResourceNodeData,
  });

  return [
    { id: NODE_ID.agent, type: 'agent', position: { ...DEFAULT_LAYOUT.agent }, data: agentData },
    resource('skill', [], true),
    resource('tool', toolNames, false),
    resource('subagent', subNames, false),
    resource('middleware', [], true),
    resource('model', [buildModelLabel(form.model, models)], false),
  ];
}

export function buildEdges(): Edge[] {
  const kinds: ResourceKind[] = ['skill', 'tool', 'subagent', 'middleware', 'model'];
  return kinds.map((kind) => ({
    id: `agent-${kind}`,
    source: NODE_ID.agent,
    target: NODE_ID[kind],
    type: 'default',
    animated: false,
    style: { stroke: EDGE_COLOR[kind], strokeWidth: 1.5, strokeDasharray: '6 6' },
  }));
}
