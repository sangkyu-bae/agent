// agent-kb-quick-setup Design §3.1 — 순수 유틸 (FR-06/FR-07/FR-08)
import { describe, expect, it } from 'vitest';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import { RAG_CATALOG_TOOL_ID } from '@/utils/agentDetailMapping';
import {
  attachKbToForm,
  detachKbFromForm,
  kbNameForAgent,
  quickKbProgressSteps,
  scopeForVisibility,
} from './kbQuickSetup';
import { hasAdvancedRagConfig } from './ragConfigAdvanced';

const FORM: AgentBuilderFormData = {
  name: '여신 상담봇',
  description: '',
  model: '',
  systemPrompt: '',
  tools: ['internal:web_search'],
  temperature: 0.7,
  toolConfigs: {},
  subAgents: [],
  skills: [],
  schedules: [],
  excludedBuiltinTools: [],
  excludedBuiltinMiddlewares: [],
  middlewares: [],
  maxIterations: 25,
  openers: [],
};

describe('kbNameForAgent', () => {
  it('에이전트명 + " 지식"', () => {
    expect(kbNameForAgent('여신 상담봇')).toBe('여신 상담봇 지식');
  });
  it('빈 이름은 폴백', () => {
    expect(kbNameForAgent('   ')).toBe('새 에이전트 지식');
  });
  it('100자를 넘지 않게 절단', () => {
    const name = kbNameForAgent('x'.repeat(200));
    expect(name.length).toBeLessThanOrEqual(100);
    expect(name.endsWith(' 지식')).toBe(true);
  });
});

describe('scopeForVisibility', () => {
  it.each([
    ['private', 'PERSONAL'],
    ['department', 'DEPARTMENT'],
    ['public', 'PUBLIC'],
  ] as const)('%s → %s', (v, s) => {
    expect(scopeForVisibility(v)).toBe(s);
  });
});

describe('attachKbToForm / detachKbFromForm', () => {
  it('RAG 도구가 없으면 추가하고 기본 설정 + kb_id 로 세팅한다', () => {
    const next = attachKbToForm(FORM, 'kb-1');
    expect(next.tools).toEqual(['internal:web_search', RAG_CATALOG_TOOL_ID]);
    expect(next.toolConfigs[RAG_CATALOG_TOOL_ID]).toEqual({
      ...DEFAULT_RAG_CONFIG,
      kb_id: 'kb-1',
      collection_name: undefined,
      metadata_filter: {},
    });
  });

  it('이미 RAG 도구가 있으면 중복 추가 없이 kb_id 만 갱신하고 나머지 설정은 유지한다', () => {
    const withRag: AgentBuilderFormData = {
      ...FORM,
      tools: [RAG_CATALOG_TOOL_ID],
      toolConfigs: {
        [RAG_CATALOG_TOOL_ID]: {
          ...DEFAULT_RAG_CONFIG,
          top_k: 9,
          collection_name: 'old',
          metadata_filter: { a: 'b' },
        },
      },
    };
    const next = attachKbToForm(withRag, 'kb-2');
    expect(next.tools).toEqual([RAG_CATALOG_TOOL_ID]);
    expect(next.toolConfigs[RAG_CATALOG_TOOL_ID].top_k).toBe(9);
    expect(next.toolConfigs[RAG_CATALOG_TOOL_ID].kb_id).toBe('kb-2');
    expect(next.toolConfigs[RAG_CATALOG_TOOL_ID].collection_name).toBeUndefined();
    expect(next.toolConfigs[RAG_CATALOG_TOOL_ID].metadata_filter).toEqual({});
  });

  it('detach 는 도구를 남기고 kb_id 만 푼다', () => {
    const next = detachKbFromForm(attachKbToForm(FORM, 'kb-1'));
    expect(next.tools).toContain(RAG_CATALOG_TOOL_ID);
    expect(next.toolConfigs[RAG_CATALOG_TOOL_ID].kb_id).toBeUndefined();
  });

  it('원본 폼을 변경하지 않는다', () => {
    attachKbToForm(FORM, 'kb-1');
    expect(FORM.tools).toEqual(['internal:web_search']);
  });
});

describe('quickKbProgressSteps', () => {
  it('pending: 1·2단계 진행중, 3단계 대기', () => {
    const steps = quickKbProgressSteps('pending', null, 3);
    expect(steps.map((s) => s.status)).toEqual(['in_progress', 'in_progress', 'pending']);
    expect(steps[1].badgeLabel).toBe('0/3');
  });

  it('done + 일부 성공: 전부 완료, n/m 배지', () => {
    const steps = quickKbProgressSteps(
      'done',
      {
        kb_id: 'k', kb_name: 'n', collection_name: 'c', scope: 'PERSONAL',
        documents: [
          { filename: 'a.pdf', status: 'uploaded', document_id: 'd', chunk_count: 1, error: null },
          { filename: 'b.pdf', status: 'failed', document_id: null, chunk_count: 0, error: 'x' },
        ],
        uploaded_count: 1, failed_count: 1,
      },
      2,
    );
    expect(steps.map((s) => s.status)).toEqual(['completed', 'completed', 'completed']);
    expect(steps[1].badgeLabel).toBe('1/2');
  });

  it('done + 전부 실패: 업로드·도구 연결 실패', () => {
    const steps = quickKbProgressSteps(
      'done',
      {
        kb_id: 'k', kb_name: 'n', collection_name: 'c', scope: 'PERSONAL',
        documents: [{ filename: 'a.pdf', status: 'failed', document_id: null, chunk_count: 0, error: 'x' }],
        uploaded_count: 0, failed_count: 1,
      },
      1,
    );
    expect(steps.map((s) => s.status)).toEqual(['completed', 'error', 'error']);
  });

  it('error: 1단계 실패', () => {
    expect(quickKbProgressSteps('error', null, 1)[0].status).toBe('error');
  });
});

describe('hasAdvancedRagConfig', () => {
  it('기본값이면 false', () => {
    expect(hasAdvancedRagConfig({ ...DEFAULT_RAG_CONFIG })).toBe(false);
    expect(hasAdvancedRagConfig({ ...DEFAULT_RAG_CONFIG, kb_id: 'kb-1' })).toBe(false);
  });
  it.each([
    ['collection_name', { collection_name: 'c' }],
    ['metadata_filter', { metadata_filter: { a: 'b' } }],
    ['search_mode', { search_mode: 'bm25_only' as const }],
    ['top_k', { top_k: 7 }],
    ['use_wiki_first', { use_wiki_first: true }],
    ['use_routed_search', { use_routed_search: true }],
    ['tool_name', { tool_name: '다른 이름' }],
  ])('%s 가 기본값과 다르면 true', (_k, over) => {
    expect(hasAdvancedRagConfig({ ...DEFAULT_RAG_CONFIG, ...over })).toBe(true);
  });
  it('KB 를 골라 컬렉션이 자동 고정된 경우는 고급이 아니다', () => {
    expect(hasAdvancedRagConfig({ ...DEFAULT_RAG_CONFIG, kb_id: 'kb-1', collection_name: 'c' })).toBe(false);
  });
});
