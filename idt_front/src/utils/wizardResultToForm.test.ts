import { describe, expect, it } from 'vitest';
import { wizardResultToForm } from './wizardResultToForm';
import { applyToolsToForm } from './agentFormPrefill';
import { RAG_CATALOG_TOOL_ID } from './agentDetailMapping';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { WizardResult } from '@/store/agentDraftStore';
import type { CatalogTool } from '@/types/toolCatalog';

const FORM: AgentBuilderFormData = {
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
  excludedBuiltinTools: ['internal:builtin_x'],
  excludedBuiltinMiddlewares: [],
  middlewares: [],
  maxIterations: 25,
};

const tool = (id: string, isBuiltin = false): CatalogTool => ({
  tool_id: id,
  source: 'internal',
  name: id,
  description: '',
  mcp_server_id: null,
  mcp_server_name: null,
  requires_env: [],
  is_builtin: isBuiltin,
});

const CATALOG = [
  tool('internal:a'),
  tool('internal:builtin_x', true),
  tool(RAG_CATALOG_TOOL_ID),
];

const result = (overrides: Partial<WizardResult> = {}): WizardResult => ({
  systemPrompt: '당신은 문서를 찾는 에이전트입니다.',
  promptEdited: false,
  toolIds: ['internal:a'],
  suggestedName: '문서 봇',
  sessionId: 'ps1',
  versionId: 'pv1',
  ...overrides,
});

describe('wizardResultToForm', () => {
  it('이름과 지침을 프리필한다', () => {
    const form = wizardResultToForm(result(), FORM, { catalogTools: CATALOG });
    expect(form.name).toBe('문서 봇');
    expect(form.systemPrompt).toBe('당신은 문서를 찾는 에이전트입니다.');
  });

  it('확정 도구를 그대로 반영한다 (매핑 없음)', () => {
    const form = wizardResultToForm(result(), FORM, { catalogTools: CATALOG });
    expect(form.tools).toEqual(['internal:a']);
  });

  it('빌트인 도구는 form.tools 에서 제외한다', () => {
    // 서버가 주입하므로 칩이 중복된다 (builtin-tools D8).
    const form = wizardResultToForm(
      result({ toolIds: ['internal:a', 'internal:builtin_x'] }),
      FORM,
      { catalogTools: CATALOG },
    );
    expect(form.tools).toEqual(['internal:a']);
  });

  it('excludedBuiltinTools 는 건드리지 않는다', () => {
    const form = wizardResultToForm(result(), FORM, { catalogTools: CATALOG });
    expect(form.excludedBuiltinTools).toEqual(['internal:builtin_x']);
  });

  it('RAG 도구가 들어오면 기본 설정을 만든다', () => {
    const form = wizardResultToForm(
      result({ toolIds: [RAG_CATALOG_TOOL_ID] }),
      FORM,
      { catalogTools: CATALOG },
    );
    expect(form.toolConfigs[RAG_CATALOG_TOOL_ID]).toBeDefined();
  });

  it('RAG 도구가 빠지면 설정을 지운다', () => {
    const withConfig = {
      ...FORM,
      toolConfigs: { [RAG_CATALOG_TOOL_ID]: { top_k: 5 } as never },
    };
    const form = wizardResultToForm(result(), withConfig, {
      catalogTools: CATALOG,
    });
    expect(form.toolConfigs[RAG_CATALOG_TOOL_ID]).toBeUndefined();
  });

  it('모델과 온도는 건드리지 않는다', () => {
    // 위저드는 이름만 제안하고 모델·온도는 스튜디오 기본값을 쓴다.
    const form = wizardResultToForm(result(), FORM, { catalogTools: CATALOG });
    expect(form.model).toBe('gpt-4o');
    expect(form.temperature).toBe(0.7);
  });

  it('카탈로그가 아직 없으면 도구를 걸러내지 않는다', () => {
    // 호출부는 settled 후에 부르는 것이 원칙이지만(G5), 방어적으로 원본 유지.
    const form = wizardResultToForm(
      result({ toolIds: ['internal:a', 'internal:builtin_x'] }),
      FORM,
      {},
    );
    expect(form.tools).toEqual(['internal:a', 'internal:builtin_x']);
  });

  it('도구 0개도 유효하다', () => {
    const form = wizardResultToForm(result({ toolIds: [] }), FORM, {
      catalogTools: CATALOG,
    });
    expect(form.tools).toEqual([]);
  });
});

describe('applyToolsToForm — compose 경로와 공유되는 계약', () => {
  it('빌트인 필터·RAG 동기화를 한 번에 처리한다', () => {
    const slice = applyToolsToForm(
      ['internal:a', 'internal:builtin_x', RAG_CATALOG_TOOL_ID],
      FORM,
      CATALOG,
    );
    expect(slice.tools).toEqual(['internal:a', RAG_CATALOG_TOOL_ID]);
    expect(slice.toolConfigs[RAG_CATALOG_TOOL_ID]).toBeDefined();
  });

  it('입력 순서를 보존한다', () => {
    const slice = applyToolsToForm([RAG_CATALOG_TOOL_ID, 'internal:a'], FORM, CATALOG);
    expect(slice.tools).toEqual([RAG_CATALOG_TOOL_ID, 'internal:a']);
  });
});
