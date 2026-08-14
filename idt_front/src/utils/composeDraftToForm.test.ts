// agent-create-entry Design §3.2 — AgentBuilderPage.handleApplyDraft에서 추출한
// 초안→폼 변환의 계약 고정. Fix 탭과 진입 화면이 이 단일 구현을 공유하므로,
// 여기서 규칙이 깨지면 두 경로가 동시에 깨진다.
import { describe, it, expect } from 'vitest';
import { composeDraftToForm } from './composeDraftToForm';
import { RAG_CATALOG_TOOL_ID } from './agentDetailMapping';
import { DOCUMENT_EXTRACTOR_TOOL_ID } from '@/types/documentExtractor';
import { DOCUMENT_GENERATOR_TOOL_ID } from '@/types/documentGenerator';
import { MAX_ITERATIONS } from '@/constants/agentSettings';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';
import type { CatalogTool } from '@/types/toolCatalog';
import type { LlmModel } from '@/types/llmModel';

const baseForm: AgentBuilderFormData = {
  name: '',
  description: '',
  model: 'gpt-4o',
  systemPrompt: '',
  tools: [],
  temperature: 0.7,
  toolConfigs: {},
  subAgents: [],
  skills: [],
  schedules: [],
  excludedBuiltinTools: [],
  excludedBuiltinMiddlewares: [],
  middlewares: [],
  maxIterations: MAX_ITERATIONS.DEFAULT,
};

const tool = (tool_id: string, is_builtin = false): CatalogTool => ({
  tool_id,
  source: tool_id.startsWith('mcp:') ? 'mcp' : 'internal',
  name: tool_id,
  description: '',
  mcp_server_id: null,
  mcp_server_name: null,
  requires_env: [],
  is_builtin,
});

const catalogTools: CatalogTool[] = [
  tool('internal:tavily_search'),
  tool('internal:internal_document_search'),
  tool(DOCUMENT_EXTRACTOR_TOOL_ID),
  tool(DOCUMENT_GENERATOR_TOOL_ID),
  tool('internal:todo_write', true),
];

const models: LlmModel[] = [
  { id: 'model-1', model_name: 'gpt-4o' },
  { id: 'model-2', model_name: 'claude-sonnet-5' },
] as LlmModel[];

const makeDraft = (
  over: Partial<ComposeAgentDraftResponse> = {},
): ComposeAgentDraftResponse => ({
  status: 'draft',
  coverage: 'full',
  name_suggestion: '검색 봇',
  system_prompt: '너는 검색 도우미다.',
  tool_ids: ['tavily_search'],
  workers: [],
  flow_hint: '',
  llm_model_id: 'model-2',
  temperature: 0.4,
  missing_capabilities: [],
  notes: '',
  ...over,
});

const deps = { catalogTools, models };

describe('composeDraftToForm', () => {
  it('이름·지침·temperature를 초안 값으로 덮어쓴다', () => {
    const next = composeDraftToForm(makeDraft(), baseForm, deps);

    expect(next.name).toBe('검색 봇');
    expect(next.systemPrompt).toBe('너는 검색 도우미다.');
    expect(next.temperature).toBe(0.4);
  });

  it('저장 형식 tool_ids를 카탈로그 형식으로 변환한다', () => {
    const next = composeDraftToForm(makeDraft(), baseForm, deps);

    expect(next.tools).toEqual(['internal:tavily_search']);
  });

  // builtin-tools D8: 서버가 자동 주입하므로 폼에 넣으면 칩이 중복된다
  it('빌트인 도구는 form.tools에 섞이지 않는다', () => {
    const next = composeDraftToForm(
      makeDraft({ tool_ids: ['tavily_search', 'todo_write'] }),
      baseForm,
      deps,
    );

    expect(next.tools).toEqual(['internal:tavily_search']);
  });

  it('빌트인 수동 해제 목록은 건드리지 않는다', () => {
    const prev = { ...baseForm, excludedBuiltinTools: ['internal:todo_write'] };

    const next = composeDraftToForm(makeDraft(), prev, deps);

    expect(next.excludedBuiltinTools).toEqual(['internal:todo_write']);
    expect(next.excludedBuiltinMiddlewares).toEqual([]);
  });

  it('RAG 도구가 포함되면 기본 RAG 설정을 넣는다', () => {
    const next = composeDraftToForm(
      makeDraft({ tool_ids: ['internal_document_search'] }),
      baseForm,
      deps,
    );

    expect(next.tools).toContain(RAG_CATALOG_TOOL_ID);
    expect(next.toolConfigs[RAG_CATALOG_TOOL_ID]).toBeDefined();
  });

  it('기존 RAG 설정이 있으면 덮어쓰지 않는다', () => {
    const prev: AgentBuilderFormData = {
      ...baseForm,
      toolConfigs: {
        [RAG_CATALOG_TOOL_ID]: { ...DEFAULT_RAG_CONFIG, top_k: 99 },
      },
    };

    const next = composeDraftToForm(
      makeDraft({ tool_ids: ['internal_document_search'] }),
      prev,
      deps,
    );

    expect(next.toolConfigs[RAG_CATALOG_TOOL_ID]).toEqual(
      prev.toolConfigs[RAG_CATALOG_TOOL_ID],
    );
  });

  it('RAG 도구가 빠지면 RAG 설정을 제거한다', () => {
    const prev: AgentBuilderFormData = {
      ...baseForm,
      toolConfigs: { [RAG_CATALOG_TOOL_ID]: {} as never },
    };

    const next = composeDraftToForm(makeDraft(), prev, deps);

    expect(next.toolConfigs[RAG_CATALOG_TOOL_ID]).toBeUndefined();
  });

  it('문서 추출기/생성기 도구가 빠지면 해당 드래프트를 비운다', () => {
    const prev: AgentBuilderFormData = {
      ...baseForm,
      documentExtractorDraft: { any: 1 } as never,
      documentGeneratorDraft: { any: 1 } as never,
    };

    const next = composeDraftToForm(makeDraft(), prev, deps);

    expect(next.documentExtractorDraft).toBeNull();
    expect(next.documentGeneratorDraft).toBeNull();
  });

  it('문서 추출기 도구가 유지되면 드래프트도 유지한다', () => {
    const prev: AgentBuilderFormData = {
      ...baseForm,
      documentExtractorDraft: { any: 1 } as never,
    };

    const next = composeDraftToForm(
      makeDraft({ tool_ids: ['document_extractor'] }),
      prev,
      deps,
    );

    expect(next.documentExtractorDraft).toEqual(prev.documentExtractorDraft);
  });

  it('llm_model_id를 model_name으로 역매핑한다', () => {
    const next = composeDraftToForm(makeDraft(), baseForm, deps);

    expect(next.model).toBe('claude-sonnet-5');
  });

  it('역매핑 실패 시 기존 모델을 유지한다', () => {
    const next = composeDraftToForm(
      makeDraft({ llm_model_id: 'unknown-model' }),
      baseForm,
      deps,
    );

    expect(next.model).toBe('gpt-4o');
  });

  it('모델 목록 미로딩(undefined) 시에도 기존 모델을 유지한다', () => {
    const next = composeDraftToForm(makeDraft(), baseForm, {
      catalogTools,
      models: undefined,
    });

    expect(next.model).toBe('gpt-4o');
  });

  it('초안이 다루지 않는 폼 필드는 보존한다', () => {
    const prev: AgentBuilderFormData = {
      ...baseForm,
      skills: ['skill-1'],
      maxIterations: 40,
      middlewares: ['pii'],
    };

    const next = composeDraftToForm(makeDraft(), prev, deps);

    expect(next.skills).toEqual(['skill-1']);
    expect(next.maxIterations).toBe(40);
    expect(next.middlewares).toEqual(['pii']);
  });
});
