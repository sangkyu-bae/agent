import { describe, it, expect } from 'vitest';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';
import { buildNodes, buildEdges, buildModelLabel } from './buildGraph';
import { EDGE_COLOR, NODE_ID } from './constants';

const FORM: AgentBuilderFormData = {
  name: '내 에이전트',
  description: '설명입니다',
  model: 'claude-haiku-4-5',
  systemPrompt: '너는 도우미야',
  tools: ['internal:web_search'],
  temperature: 0.7,
  toolConfigs: {},
  subAgents: [{ ref_agent_id: 'a1', name: '리서처', description: '' }],
};

const CATALOG: CatalogTool[] = [
  {
    tool_id: 'internal:web_search',
    source: 'internal',
    name: '웹 검색',
    description: '',
    mcp_server_id: null,
    mcp_server_name: null,
    requires_env: [],
  },
];

const MODELS: LlmModel[] = [
  {
    id: 'm1',
    provider: 'anthropic',
    model_name: 'claude-haiku-4-5',
    display_name: 'Haiku',
    description: null,
    max_tokens: null,
    is_active: true,
    is_default: true,
  },
];

describe('buildModelLabel', () => {
  it('매칭 시 provider:model_name 형식', () => {
    expect(buildModelLabel('claude-haiku-4-5', MODELS)).toBe('anthropic:claude-haiku-4-5');
  });
  it('미매칭 시 raw model 반환', () => {
    expect(buildModelLabel('unknown-x', MODELS)).toBe('unknown-x');
  });
  it('빈 값이면 "모델 미선택"', () => {
    expect(buildModelLabel('', MODELS)).toBe('모델 미선택');
  });
});

describe('buildNodes', () => {
  it('노드 6개 생성 (agent + 5 resource)', () => {
    const nodes = buildNodes(FORM, CATALOG, MODELS);
    expect(nodes).toHaveLength(6);
    expect(nodes.map((n) => n.id).sort()).toEqual(
      ['agent', 'middleware', 'model', 'skill', 'subagent', 'tool'].sort(),
    );
  });

  it('agent 노드는 form 메타를 data로 보유', () => {
    const agent = buildNodes(FORM, CATALOG, MODELS).find((n) => n.id === NODE_ID.agent)!;
    expect(agent.type).toBe('agent');
    expect(agent.data).toMatchObject({
      name: '내 에이전트',
      description: '설명입니다',
      systemPrompt: '너는 도우미야',
    });
  });

  it('tool 노드 items는 선택된 도구명', () => {
    const tool = buildNodes(FORM, CATALOG, MODELS).find((n) => n.id === NODE_ID.tool)!;
    expect(tool.data).toMatchObject({ kind: 'tool', items: ['웹 검색'], disabled: false });
  });

  it('subagent 노드 items는 서브에이전트 이름', () => {
    const sub = buildNodes(FORM, CATALOG, MODELS).find((n) => n.id === NODE_ID.subagent)!;
    expect(sub.data).toMatchObject({ kind: 'subagent', items: ['리서처'], disabled: false });
  });

  it('model 노드 items는 provider:model_name 라벨', () => {
    const model = buildNodes(FORM, CATALOG, MODELS).find((n) => n.id === NODE_ID.model)!;
    expect(model.data).toMatchObject({ kind: 'model', items: ['anthropic:claude-haiku-4-5'] });
  });

  it('skill/middleware는 disabled + 빈 items (플레이스홀더)', () => {
    const nodes = buildNodes(FORM, CATALOG, MODELS);
    const skill = nodes.find((n) => n.id === NODE_ID.skill)!;
    const mw = nodes.find((n) => n.id === NODE_ID.middleware)!;
    expect(skill.data).toMatchObject({ kind: 'skill', items: [], disabled: true });
    expect(mw.data).toMatchObject({ kind: 'middleware', items: [], disabled: true });
  });
});

describe('buildEdges', () => {
  it('엣지 5개, 모두 agent에서 출발', () => {
    const edges = buildEdges();
    expect(edges).toHaveLength(5);
    expect(edges.every((e) => e.source === NODE_ID.agent)).toBe(true);
  });

  it('각 엣지 색상은 EDGE_COLOR와 일치', () => {
    const edges = buildEdges();
    const tool = edges.find((e) => e.target === NODE_ID.tool)!;
    const sub = edges.find((e) => e.target === NODE_ID.subagent)!;
    expect((tool.style as { stroke: string }).stroke).toBe(EDGE_COLOR.tool);
    expect((sub.style as { stroke: string }).stroke).toBe(EDGE_COLOR.subagent);
  });
});
