// agent-builder-edit-mapping Design §5-1
import { describe, it, expect } from 'vitest';
import { mapDetailToForm, RAG_CATALOG_TOOL_ID } from './agentDetailMapping';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import type { AgentDetail, WorkerInfo } from '@/types/agentStore';
import type { LlmModel } from '@/types/llmModel';
import type { CatalogTool } from '@/types/toolCatalog';

const makeDetail = (over: Partial<AgentDetail> = {}): AgentDetail => ({
  agent_id: 'agent-1',
  name: '테스트 봇',
  description: '설명',
  system_prompt: '지침',
  tool_ids: [],
  skill_ids: [],
  workers: [],
  flow_hint: '',
  llm_model_id: 'model-uuid-1',
  status: 'active',
  visibility: 'private',
  department_id: null,
  department_name: null,
  temperature: 0.7,
  owner_user_id: 'u1',
  can_edit: true,
  can_delete: true,
  created_at: '2026-07-13T00:00:00Z',
  updated_at: '2026-07-13T00:00:00Z',
  ...over,
});

const makeModel = (over: Partial<LlmModel> = {}): LlmModel => ({
  id: 'model-uuid-1',
  provider: 'openai',
  model_name: 'gpt-4o',
  display_name: 'GPT-4o',
  description: null,
  max_tokens: null,
  is_active: true,
  is_default: true,
  ...over,
});

const makeCatalogTool = (over: Partial<CatalogTool> = {}): CatalogTool => ({
  tool_id: 'internal:internal_document_search',
  source: 'internal',
  name: '내부 문서 검색',
  description: '',
  mcp_server_id: null,
  mcp_server_name: null,
  requires_env: [],
  ...over,
});

const makeWorker = (over: Partial<WorkerInfo> = {}): WorkerInfo => ({
  tool_id: 'internal_document_search',
  worker_id: 'w0',
  description: '',
  sort_order: 0,
  tool_config: null,
  worker_type: 'tool',
  ...over,
});

describe('mapDetailToForm — 모델 역매핑', () => {
  it('llm_model_id가 models에 있으면 model_name으로 역매핑한다', () => {
    const form = mapDetailToForm(makeDetail(), [makeModel()], []);
    expect(form.model).toBe('gpt-4o');
  });

  it('models에 없는 id면 raw id를 유지한다', () => {
    const form = mapDetailToForm(
      makeDetail({ llm_model_id: 'ghost-id' }),
      [makeModel()],
      [],
    );
    expect(form.model).toBe('ghost-id');
  });

  it('models가 undefined(로딩 실패)여도 raw id를 유지한다', () => {
    const form = mapDetailToForm(makeDetail(), undefined, []);
    expect(form.model).toBe('model-uuid-1');
  });
});

describe('mapDetailToForm — 도구 형식 변환', () => {
  it('internal 저장 형식을 카탈로그 형식으로 변환한다', () => {
    const form = mapDetailToForm(
      makeDetail({ tool_ids: ['internal_document_search'] }),
      [makeModel()],
      [makeCatalogTool()],
    );
    expect(form.tools).toEqual(['internal:internal_document_search']);
  });

  it('mcp_{server} 저장 형식을 해당 서버의 카탈로그 도구들로 확장한다', () => {
    const mcpTools = [
      makeCatalogTool({
        tool_id: 'mcp:srv1:search',
        source: 'mcp',
        mcp_server_id: 'srv1',
      }),
      makeCatalogTool({
        tool_id: 'mcp:srv1:fetch',
        source: 'mcp',
        mcp_server_id: 'srv1',
      }),
    ];
    const form = mapDetailToForm(
      makeDetail({ tool_ids: ['mcp_srv1'] }),
      [makeModel()],
      mcpTools,
    );
    expect(form.tools).toEqual(['mcp:srv1:search', 'mcp:srv1:fetch']);
  });

  it('카탈로그에 없는 id는 원본을 유지한다 (저장 가능성 보존)', () => {
    const form = mapDetailToForm(
      makeDetail({ tool_ids: ['unknown_tool'] }),
      [makeModel()],
      [makeCatalogTool()],
    );
    expect(form.tools).toEqual(['unknown_tool']);
  });

  it('catalogTools가 undefined(로딩 실패)면 원본 유지 폴백이 동작한다', () => {
    const form = mapDetailToForm(
      makeDetail({ tool_ids: ['internal_document_search', 'mcp_srv1'] }),
      [makeModel()],
      undefined,
    );
    expect(form.tools).toEqual(['internal_document_search', 'mcp_srv1']);
  });
});

describe('mapDetailToForm — RAG 설정 복원', () => {
  it('RAG worker의 tool_config를 DEFAULT 머지로 복원한다', () => {
    const form = mapDetailToForm(
      makeDetail({
        workers: [
          makeWorker({
            tool_config: { collection_name: 'my-docs', top_k: 10 },
          }),
        ],
      }),
      [makeModel()],
      [makeCatalogTool()],
    );
    const cfg = form.toolConfigs[RAG_CATALOG_TOOL_ID];
    expect(cfg.collection_name).toBe('my-docs');
    expect(cfg.top_k).toBe(10);
    // 서버 저장분에 없는 필드는 DEFAULT 값 보장
    expect(cfg.search_mode).toBe(DEFAULT_RAG_CONFIG.search_mode);
    expect(cfg.use_wiki_first).toBe(DEFAULT_RAG_CONFIG.use_wiki_first);
  });

  it('RAG worker가 없으면 toolConfigs는 빈 객체다', () => {
    const form = mapDetailToForm(
      makeDetail({
        workers: [makeWorker({ tool_id: 'tavily_search' })],
      }),
      [makeModel()],
      [],
    );
    expect(form.toolConfigs).toEqual({});
  });

  it('sub_agent 워커의 tool_config는 RAG 설정으로 오인하지 않는다', () => {
    const form = mapDetailToForm(
      makeDetail({
        workers: [
          makeWorker({
            tool_id: 'internal_document_search',
            worker_type: 'sub_agent',
            ref_agent_id: 'sub-1',
            tool_config: { collection_name: 'x' },
          }),
        ],
      }),
      [makeModel()],
      [],
    );
    expect(form.toolConfigs).toEqual({});
  });
});

describe('mapDetailToForm — 서브에이전트/스킬 회귀 고정', () => {
  it('sub_agent 워커를 subAgents로 매핑한다 (ref_agent_name 우선)', () => {
    const form = mapDetailToForm(
      makeDetail({
        workers: [
          makeWorker({
            tool_id: 'sub_agent_x',
            worker_type: 'sub_agent',
            ref_agent_id: 'sub-1',
            ref_agent_name: '서브봇',
            description: '역할',
          }),
        ],
      }),
      [makeModel()],
      [],
    );
    expect(form.subAgents).toEqual([
      { ref_agent_id: 'sub-1', name: '서브봇', description: '역할' },
    ]);
  });

  it('ref_agent_name이 없으면 ref_agent_id로 폴백한다', () => {
    const form = mapDetailToForm(
      makeDetail({
        workers: [
          makeWorker({
            tool_id: 'sub_agent_x',
            worker_type: 'sub_agent',
            ref_agent_id: 'sub-1',
            ref_agent_name: null,
          }),
        ],
      }),
      [makeModel()],
      [],
    );
    expect(form.subAgents[0].name).toBe('sub-1');
  });

  it('skill_ids를 skills로 매핑하고, 없으면 빈 배열이다', () => {
    expect(
      mapDetailToForm(makeDetail({ skill_ids: ['s1', 's2'] }), [], []).skills,
    ).toEqual(['s1', 's2']);
    expect(
      mapDetailToForm(makeDetail({ skill_ids: undefined }), [], []).skills,
    ).toEqual([]);
  });

  it('기본 필드와 edit 모드 스케줄 정책(빈 배열)을 유지한다', () => {
    const form = mapDetailToForm(makeDetail(), [makeModel()], []);
    expect(form.name).toBe('테스트 봇');
    expect(form.systemPrompt).toBe('지침');
    expect(form.temperature).toBe(0.7);
    expect(form.schedules).toEqual([]);
  });
});
