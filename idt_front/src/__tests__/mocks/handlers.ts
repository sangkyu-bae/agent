import { http, HttpResponse } from 'msw';
import { API_ENDPOINTS } from '@/constants/api';
import type { ScheduleResponse } from '@/types/agentSchedule';

// ── Agent Schedule (agent-schedule) — stateful in-memory store ──
const scheduleStore = new Map<string, ScheduleResponse[]>();
let scheduleSeq = 0;

export const resetScheduleStore = () => {
  scheduleStore.clear();
  scheduleSeq = 0;
};

export const seedSchedules = (agentId: string, items: ScheduleResponse[]) => {
  scheduleStore.set(agentId, [...items]);
};

export const mockSchedule = (
  overrides: Partial<ScheduleResponse> = {},
): ScheduleResponse => ({
  id: `sch-${++scheduleSeq}`,
  agent_id: 'agent-1',
  name: '매일 09:00 실행',
  spec: {
    schedule_type: 'cron',
    run_date: null,
    time_of_day: null,
    days_of_week: null,
    cron_expr: '0 9 * * *',
  },
  instruction: '{today} 기준 주요 뉴스를 요약해줘',
  enabled: true,
  timezone: 'Asia/Seoul',
  next_run_at: '2026-07-04T00:00:00Z',
  last_run_at: null,
  created_at: '2026-07-03T00:00:00Z',
  updated_at: '2026-07-03T00:00:00Z',
  ...overrides,
});

export const handlers = [
  http.post(`*${API_ENDPOINTS.GENERAL_CHAT}`, () =>
    HttpResponse.json({
      user_id: 'user-001',
      session_id: 'session-abc',
      answer: '테스트 답변입니다.',
      tools_used: ['hybrid_document_search'],
      sources: [
        { content: '청크 내용', source: 'doc.pdf', chunk_id: 'c-001', score: 0.92 },
      ],
      was_summarized: false,
      request_id: 'req-001',
    })
  ),

  // CHAT-HIST-001: 사용자 세션 목록
  http.get(`*${API_ENDPOINTS.CONVERSATION_SESSIONS}`, ({ request }) => {
    const url = new URL(request.url);
    const userId = url.searchParams.get('user_id');
    return HttpResponse.json({
      user_id: userId,
      sessions: [
        {
          session_id: 's1',
          message_count: 4,
          last_message: '안녕',
          last_message_at: '2026-04-17T10:00:00Z',
        },
        {
          session_id: 's2',
          message_count: 2,
          last_message: '이전 질문',
          last_message_at: '2026-04-16T12:00:00Z',
        },
      ],
    });
  }),

  // TOOL-CATALOG-001: 도구 카탈로그 조회
  http.get(`*${API_ENDPOINTS.TOOL_CATALOG}`, () =>
    HttpResponse.json({
      tools: [
        { tool_id: 'internal:excel_export', source: 'internal', name: 'Excel 파일 생성', description: 'pandas로 데이터를 Excel(.xlsx) 파일로 저장합니다.', mcp_server_id: null, mcp_server_name: null, requires_env: [] },
        { tool_id: 'mcp:srv1:search', source: 'mcp', name: 'search', description: 'MCP 서버의 검색 도구', mcp_server_id: 'srv1', mcp_server_name: 'Search', requires_env: [] },
      ],
    })
  ),

  // MCP-REG-UI-001: MCP 서버 레지스트리 CRUD + 연결 테스트
  http.get(`*${API_ENDPOINTS.MCP_SERVERS}`, () =>
    HttpResponse.json({
      items: [
        {
          id: 'srv-1',
          user_id: '1',
          name: 'Naver Search',
          description: '네이버 검색 MCP',
          endpoint: 'https://server.smithery.ai/@x/y/mcp',
          transport: 'streamable_http',
          input_schema: null,
          is_active: true,
          tool_id: 'mcp_srv-1',
          created_at: '2026-06-18T00:00:00Z',
          updated_at: '2026-06-18T00:00:00Z',
          auth_config: { api_key: '****' },
          server_config: null,
        },
      ],
      total: 1,
    })
  ),
  http.post(`*${API_ENDPOINTS.MCP_SERVERS}`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(
      {
        id: 'srv-new',
        tool_id: 'mcp_srv-new',
        is_active: true,
        input_schema: null,
        created_at: '2026-06-18T00:00:00Z',
        updated_at: '2026-06-18T00:00:00Z',
        auth_config: null,
        server_config: null,
        ...body,
      },
      { status: 201 },
    );
  }),
  http.put('*/api/v1/mcp-registry/:id', async ({ request, params }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({
      id: params.id,
      user_id: '1',
      name: 'updated',
      description: 'd',
      endpoint: 'https://e/mcp',
      transport: 'sse',
      input_schema: null,
      is_active: true,
      tool_id: `mcp_${params.id}`,
      created_at: '2026-06-18T00:00:00Z',
      updated_at: '2026-06-18T01:00:00Z',
      auth_config: null,
      server_config: null,
      ...body,
    });
  }),
  http.delete('*/api/v1/mcp-registry/:id', () => new HttpResponse(null, { status: 204 })),
  http.post('*/api/v1/mcp-registry/:id/test', () =>
    HttpResponse.json({
      ok: true,
      tools: [{ name: 'search', description: '웹 검색' }],
      elapsed_ms: 42,
    })
  ),

  // SKILL-001: Skill Builder
  http.post(`*${API_ENDPOINTS.SKILLS_LIST}`, () =>
    HttpResponse.json({
      skills: [
        {
          id: 'skill-1',
          name: '환율 계산기',
          description: '통화 환율 변환',
          script_type: 'python',
          visibility: 'private',
          owner_user_id: '1',
          forked_from: null,
          can_edit: true,
          can_delete: true,
          created_at: '2026-06-20T00:00:00Z',
        },
        {
          id: 'skill-2',
          name: '공용 요약기',
          description: '문서 요약',
          script_type: 'none',
          visibility: 'public',
          owner_user_id: '2',
          forked_from: null,
          can_edit: false,
          can_delete: false,
          created_at: '2026-06-20T00:00:00Z',
        },
      ],
      total: 2,
      page: 1,
      size: 50,
    })
  ),
  http.get('*/api/v1/skills/:id', ({ params }) =>
    HttpResponse.json({
      id: params.id,
      user_id: '1',
      name: '환율 계산기',
      description: '통화 환율 변환',
      instruction: '환율 변환 요청 시 ...',
      trigger: '환율',
      script_type: 'python',
      script_content: 'def convert(): ...',
      status: 'active',
      visibility: 'private',
      department_id: null,
      forked_from: null,
      forked_at: null,
      created_at: '2026-06-20T00:00:00Z',
      updated_at: '2026-06-20T00:00:00Z',
    })
  ),
  http.post(`*${API_ENDPOINTS.SKILLS}`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json(
      {
        id: 'skill-new',
        user_id: '1',
        status: 'active',
        trigger: null,
        script_content: null,
        department_id: null,
        forked_from: null,
        forked_at: null,
        created_at: '2026-06-20T00:00:00Z',
        updated_at: '2026-06-20T00:00:00Z',
        ...body,
      },
      { status: 201 },
    );
  }),
  http.put('*/api/v1/skills/:id', async ({ request, params }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({
      id: params.id,
      user_id: '1',
      status: 'active',
      forked_from: null,
      forked_at: null,
      created_at: '2026-06-20T00:00:00Z',
      updated_at: '2026-06-20T01:00:00Z',
      ...body,
    });
  }),
  http.delete('*/api/v1/skills/:id', () => new HttpResponse(null, { status: 204 })),
  http.post('*/api/v1/skills/:id/fork', ({ params }) =>
    HttpResponse.json(
      {
        id: 'skill-forked',
        user_id: '1',
        name: '공용 요약기',
        description: '문서 요약',
        instruction: 'i',
        trigger: null,
        script_type: 'none',
        script_content: null,
        status: 'active',
        visibility: 'private',
        department_id: null,
        forked_from: params.id,
        forked_at: '2026-06-21T00:00:00Z',
        created_at: '2026-06-21T00:00:00Z',
        updated_at: '2026-06-21T00:00:00Z',
      },
      { status: 201 },
    )
  ),

  // LLM-MODEL-FRONT-001: LLM 모델 목록 조회 (llm-register: include_inactive 지원 + 가격 필드)
  http.get(`*${API_ENDPOINTS.LLM_MODELS}`, ({ request }) => {
    const includeInactive =
      new URL(request.url).searchParams.get('include_inactive') === 'true';
    const models = [
      {
        id: 'uuid-1',
        provider: 'openai',
        model_name: 'gpt-4o',
        display_name: 'GPT-4o',
        description: 'OpenAI GPT-4o model',
        max_tokens: null,
        is_active: true,
        is_default: true,
        base_url: null,
        input_price_per_1k_usd: '0.0025',
        output_price_per_1k_usd: '0.0100',
        pricing_updated_at: '2026-07-01T00:00:00',
      },
      {
        id: 'uuid-2',
        provider: 'anthropic',
        model_name: 'claude-sonnet-4-6',
        display_name: 'Claude Sonnet 4.6',
        description: 'Anthropic Claude Sonnet',
        max_tokens: null,
        is_active: true,
        is_default: false,
        base_url: null,
        input_price_per_1k_usd: null,
        output_price_per_1k_usd: null,
        pricing_updated_at: null,
      },
    ];
    if (includeInactive) {
      models.push({
        id: 'uuid-3',
        provider: 'ollama',
        model_name: 'llama-3-8b',
        display_name: 'Llama 3 8B',
        description: null,
        max_tokens: 4096,
        is_active: false,
        is_default: false,
        base_url: 'http://vllm.internal:8000/v1',
        input_price_per_1k_usd: null,
        output_price_per_1k_usd: null,
        pricing_updated_at: null,
      });
    }
    return HttpResponse.json({ models });
  }),

  // llm-register: 모델 등록 (dup-model → 409)
  http.post(`*${API_ENDPOINTS.LLM_MODELS}`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    if (body.model_name === 'dup-model') {
      return HttpResponse.json(
        { detail: '이미 등록된 모델입니다' },
        { status: 409 },
      );
    }
    return HttpResponse.json(
      {
        id: 'uuid-new',
        provider: body.provider,
        model_name: body.model_name,
        display_name: body.display_name,
        description: body.description ?? null,
        max_tokens: body.max_tokens ?? null,
        is_active: body.is_active ?? true,
        is_default: body.is_default ?? false,
        base_url: body.base_url ?? null,
        input_price_per_1k_usd: null,
        output_price_per_1k_usd: null,
        pricing_updated_at: null,
      },
      { status: 201 },
    );
  }),

  // llm-register: 가격 변경 (:id 매처보다 먼저 등록)
  http.patch('*/api/v1/llm-models/:id/pricing', async ({ params, request }) => {
    if (params.id === 'not-found') {
      return HttpResponse.json({ detail: '모델을 찾을 수 없습니다' }, { status: 404 });
    }
    const body = (await request.json()) as {
      input_price_per_1k_usd: number;
      output_price_per_1k_usd: number;
    };
    return HttpResponse.json({
      id: params.id,
      provider: 'openai',
      model_name: 'gpt-4o',
      display_name: 'GPT-4o',
      description: null,
      max_tokens: null,
      is_active: true,
      is_default: true,
      base_url: null,
      input_price_per_1k_usd: String(body.input_price_per_1k_usd),
      output_price_per_1k_usd: String(body.output_price_per_1k_usd),
      pricing_updated_at: '2026-07-11T00:00:00',
    });
  }),

  // llm-register: 모델 수정
  http.patch('*/api/v1/llm-models/:id', async ({ params, request }) => {
    if (params.id === 'not-found') {
      return HttpResponse.json({ detail: '모델을 찾을 수 없습니다' }, { status: 404 });
    }
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({
      id: params.id,
      provider: 'openai',
      model_name: 'gpt-4o',
      display_name: body.display_name ?? 'GPT-4o',
      description: body.description ?? null,
      max_tokens: body.max_tokens ?? null,
      is_active: body.is_active ?? true,
      is_default: body.is_default ?? false,
      base_url: body.base_url ?? null,
      input_price_per_1k_usd: '0.0025',
      output_price_per_1k_usd: '0.0100',
      pricing_updated_at: '2026-07-01T00:00:00',
    });
  }),

  // llm-register: 모델 비활성화 (soft delete)
  http.delete('*/api/v1/llm-models/:id', ({ params }) => {
    if (params.id === 'not-found') {
      return HttpResponse.json({ detail: '모델을 찾을 수 없습니다' }, { status: 404 });
    }
    return HttpResponse.json({
      id: params.id,
      provider: 'openai',
      model_name: 'gpt-4o',
      display_name: 'GPT-4o',
      description: null,
      max_tokens: null,
      is_active: false,
      is_default: false,
      base_url: null,
      input_price_per_1k_usd: '0.0025',
      output_price_per_1k_usd: '0.0100',
      pricing_updated_at: '2026-07-01T00:00:00',
    });
  }),

  // RAG-TOOL: 컬렉션 목록
  http.get(`*${API_ENDPOINTS.RAG_TOOL_COLLECTIONS}`, () =>
    HttpResponse.json({
      collections: [
        { name: 'documents', display_name: '전체 문서', vectors_count: 500, scope: 'PUBLIC' },
        { name: 'finance_docs', display_name: '금융 문서', vectors_count: 200, scope: 'DEPARTMENT' },
        { name: 'tech_manuals', display_name: '기술 매뉴얼', vectors_count: 150, scope: 'PERSONAL' },
      ],
    })
  ),

  // KB (kb-rag-filter): 지식베이스 목록
  http.get(`*${API_ENDPOINTS.KNOWLEDGE_BASES}`, () =>
    HttpResponse.json({
      knowledge_bases: [
        {
          kb_id: 'kb-public-1', name: '전사 규정', description: '전사 공통 규정',
          scope: 'PUBLIC', department_id: null, collection_name: 'admin-coll-01',
          owner_id: 1, created_at: '2026-07-01T00:00:00Z',
        },
        {
          kb_id: 'kb-dept-1', name: '여신 심사 기준', description: null,
          scope: 'DEPARTMENT', department_id: 'dept-1', collection_name: 'admin-coll-01',
          owner_id: 2, created_at: '2026-07-02T00:00:00Z',
        },
        {
          kb_id: 'kb-personal-1', name: '내 메모', description: null,
          scope: 'PERSONAL', department_id: null, collection_name: 'admin-coll-02',
          owner_id: 3, created_at: '2026-07-03T00:00:00Z',
        },
      ],
      total: 3,
    })
  ),

  // KB (kb-management-ui): 상세
  http.get(`*${API_ENDPOINTS.KNOWLEDGE_BASE_DETAIL(':kbId')}`, ({ params }) =>
    HttpResponse.json({
      kb_id: params.kbId, name: '전사 규정', description: '전사 공통 규정',
      scope: 'PUBLIC', department_id: null, collection_name: 'admin-coll-01',
      owner_id: 1, use_clause_chunking: false, created_at: '2026-07-01T00:00:00Z',
    })
  ),

  // KB (kb-management-ui): 문서 목록
  http.get(
    `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(':kbId')}`,
    ({ params }) =>
      HttpResponse.json({
        kb_id: params.kbId,
        kb_name: '전사 규정',
        documents: [
          {
            document_id: 'doc-1', filename: '여신규정.pdf', chunk_count: 12,
            chunking_strategy: 'clause_aware', created_at: '2026-07-09T10:00:00Z',
          },
          {
            document_id: 'doc-2', filename: '내규집.pdf', chunk_count: 8,
            chunking_strategy: 'parent_child', created_at: '2026-07-08T09:00:00Z',
          },
        ],
        total: 2, offset: 0, limit: 20,
      })
  ),

  // KB (kb-management-ui): 생성
  http.post(`*${API_ENDPOINTS.KNOWLEDGE_BASES}`, () =>
    HttpResponse.json(
      {
        kb_id: 'kb-new-1', name: '신규 KB', scope: 'PERSONAL',
        collection_name: 'admin-coll-01',
        message: 'Knowledge base created successfully',
      },
      { status: 201 }
    )
  ),

  // KB (kb-management-ui): 삭제
  http.delete(`*${API_ENDPOINTS.KNOWLEDGE_BASE_DETAIL(':kbId')}`, ({ params }) =>
    HttpResponse.json({
      kb_id: params.kbId,
      message: 'Knowledge base deleted. Stored vectors remain until cleanup.',
    })
  ),

  // KB (kb-management-ui): 문서 업로드
  http.post(
    `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(':kbId')}`,
    ({ params }) =>
      HttpResponse.json({
        kb_id: params.kbId, kb_name: '전사 규정',
        collection_name: 'admin-coll-01',
        document_id: 'doc-new-1', filename: 'uploaded.pdf',
        total_pages: 3, chunk_count: 15, chunking_strategy: 'parent_child',
        qdrant: { status: 'success', error: null },
        es: { status: 'success', error: null },
        status: 'completed',
        section_summary: null,
      })
  ),

  // RAG-TOOL: 메타데이터 키
  http.get(`*${API_ENDPOINTS.RAG_TOOL_METADATA_KEYS}`, () =>
    HttpResponse.json({
      keys: [
        { key: 'department', sample_values: ['finance', 'tech', 'hr'], value_count: 3 },
        { key: 'category', sample_values: ['policy', 'manual', 'guide'], value_count: 3 },
        { key: 'year', sample_values: ['2024', '2025', '2026'], value_count: 3 },
      ],
    })
  ),

  // EMBEDDING-MODEL: 임베딩 모델 목록
  http.get(`*${API_ENDPOINTS.EMBEDDING_MODELS}`, () =>
    HttpResponse.json({
      models: [
        {
          id: 1,
          provider: 'openai',
          model_name: 'text-embedding-3-small',
          display_name: 'OpenAI Embedding 3 Small',
          vector_dimension: 1536,
          description: '가성비 좋은 범용 임베딩 모델',
        },
        {
          id: 2,
          provider: 'openai',
          model_name: 'text-embedding-3-large',
          display_name: 'OpenAI Embedding 3 Large',
          vector_dimension: 3072,
          description: '고품질 임베딩 모델',
        },
      ],
      total: 2,
    }),
  ),

  // COLLECTION-MGMT: 컬렉션 목록
  http.get(`*${API_ENDPOINTS.COLLECTIONS}`, () =>
    HttpResponse.json({
      collections: [
        { name: 'documents', vectors_count: 150, points_count: 150, status: 'green', scope: 'PUBLIC', owner_id: 1 },
        { name: 'test-collection', vectors_count: 50, points_count: 50, status: 'green', scope: 'PERSONAL', owner_id: 10 },
        { name: 'embeddings', vectors_count: 200, points_count: 200, status: 'green', scope: 'DEPARTMENT', owner_id: 10 },
      ],
      total: 3,
    }),
  ),

  // COLLECTION-MGMT: 컬렉션 생성
  http.post(`*${API_ENDPOINTS.COLLECTIONS}`, async ({ request }) => {
    const body = (await request.json()) as { name: string };
    return HttpResponse.json(
      { name: body.name, message: 'Collection created successfully' },
      { status: 201 },
    );
  }),

  // COLLECTION-MGMT: 컬렉션 삭제
  http.delete('*/api/v1/collections/:name', ({ params }) => {
    if (params.name === 'documents') {
      return HttpResponse.json(
        { detail: 'Cannot delete protected collection' },
        { status: 403 },
      );
    }
    return HttpResponse.json({
      name: params.name as string,
      message: 'Collection deleted successfully',
    });
  }),

  // COLLECTION-MGMT: 컬렉션 이름변경
  http.patch('*/api/v1/collections/:name', async ({ params, request }) => {
    const body = (await request.json()) as { new_name: string };
    return HttpResponse.json({
      old_name: params.name as string,
      new_name: body.new_name,
      message: 'Collection alias updated successfully',
    });
  }),

  // COLLECTION-MGMT: scope 변경
  http.patch('*/api/v1/collections/:name/permission', async ({ params }) =>
    HttpResponse.json({
      name: params.name as string,
      message: 'Collection scope updated successfully',
    }),
  ),

  // COLLECTION-MGMT: 전체 이력
  http.get(`*${API_ENDPOINTS.COLLECTION_ACTIVITY_LOG}`, () =>
    HttpResponse.json({
      logs: [
        { id: 1, collection_name: 'documents', action: 'CREATE', user_id: 'system', detail: null, created_at: '2026-04-22T10:00:00Z' },
        { id: 2, collection_name: 'test-collection', action: 'SEARCH', user_id: 'user-1', detail: { query: 'test' }, created_at: '2026-04-22T11:00:00Z' },
        { id: 3, collection_name: 'documents', action: 'SEARCH', user_id: 'user-1', detail: null, created_at: '2026-04-22T12:00:00Z' },
        { id: 4, collection_name: 'embeddings', action: 'CREATE', user_id: 'system', detail: null, created_at: '2026-04-22T13:00:00Z' },
        { id: 5, collection_name: 'documents', action: 'DELETE', user_id: 'admin', detail: null, created_at: '2026-04-22T14:00:00Z' },
      ],
      total: 5,
      limit: 50,
      offset: 0,
    }),
  ),

  // COLLECTION-DOC: 컬렉션 문서 목록
  http.get('*/api/v1/collections/:name/documents', ({ request }) => {
    const url = new URL(request.url);
    const offset = Number(url.searchParams.get('offset') ?? '0');
    const limit = Number(url.searchParams.get('limit') ?? '20');
    return HttpResponse.json({
      collection_name: 'test-collection',
      documents: [
        { document_id: 'doc-1', filename: '금융정책_2026.pdf', category: 'finance', chunk_count: 15, chunk_types: ['parent', 'child'], user_id: 'user-1' },
        { document_id: 'doc-2', filename: '세금가이드.pdf', category: 'tax', chunk_count: 8, chunk_types: ['full'], user_id: 'user-1' },
        { document_id: 'doc-3', filename: '보험약관.pdf', category: 'insurance', chunk_count: 22, chunk_types: ['semantic'], user_id: 'user-2' },
      ],
      total_documents: 3,
      offset,
      limit,
    });
  }),

  // COLLECTION-DOC: 문서 청크 상세
  http.get('*/api/v1/collections/:name/documents/:docId/chunks', ({ request }) => {
    const url = new URL(request.url);
    const includeParent = url.searchParams.get('include_parent') === 'true';
    return HttpResponse.json({
      document_id: 'doc-1',
      filename: '금융정책_2026.pdf',
      chunk_strategy: 'parent_child',
      total_chunks: 4,
      chunks: [
        { chunk_id: 'c-0', chunk_index: 0, chunk_type: 'parent', content: '부모 청크 내용입니다.', metadata: { page: 1 } },
        { chunk_id: 'c-1', chunk_index: 1, chunk_type: 'child', content: '자식 청크 1 내용입니다.', metadata: { page: 1, parent_id: 'c-0' } },
        { chunk_id: 'c-2', chunk_index: 2, chunk_type: 'child', content: '자식 청크 2 내용입니다.', metadata: { page: 2, parent_id: 'c-0' } },
        { chunk_id: 'c-3', chunk_index: 3, chunk_type: 'child', content: '자식 청크 3 내용입니다.', metadata: { page: 2, parent_id: 'c-0' } },
      ],
      parents: includeParent
        ? [
            {
              chunk_id: 'c-0',
              chunk_index: 0,
              chunk_type: 'parent',
              content: '부모 청크 내용입니다.',
              children: [
                { chunk_id: 'c-1', chunk_index: 1, chunk_type: 'child', content: '자식 청크 1 내용입니다.', metadata: { page: 1, parent_id: 'c-0' } },
                { chunk_id: 'c-2', chunk_index: 2, chunk_type: 'child', content: '자식 청크 2 내용입니다.', metadata: { page: 2, parent_id: 'c-0' } },
                { chunk_id: 'c-3', chunk_index: 3, chunk_type: 'child', content: '자식 청크 3 내용입니다.', metadata: { page: 2, parent_id: 'c-0' } },
              ],
            },
          ]
        : null,
    });
  }),

  // 에이전트별 세션 목록
  http.get('*/api/v1/conversations/agents/:agentId/sessions', ({ params, request }) => {
    const url = new URL(request.url);
    const userId = url.searchParams.get('user_id');
    return HttpResponse.json({
      user_id: userId,
      agent_id: params.agentId as string,
      sessions: [
        {
          session_id: 's1',
          message_count: 4,
          last_message: '안녕',
          last_message_at: '2026-04-17T10:00:00Z',
        },
        {
          session_id: 's2',
          message_count: 2,
          last_message: '이전 질문',
          last_message_at: '2026-04-16T12:00:00Z',
        },
      ],
    });
  }),

  // 에이전트별 세션 메시지 조회
  http.get('*/api/v1/conversations/agents/:agentId/sessions/:sessionId/messages', ({ params, request }) => {
    const url = new URL(request.url);
    return HttpResponse.json({
      user_id: url.searchParams.get('user_id'),
      agent_id: params.agentId as string,
      session_id: params.sessionId,
      messages: [
        {
          id: 1,
          role: 'user',
          content: '이전 질문입니다',
          turn_index: 1,
          created_at: '2026-04-17T10:00:00Z',
          charts: null,
        },
        {
          id: 2,
          role: 'assistant',
          content: '이전 답변입니다',
          turn_index: 1,
          created_at: '2026-04-17T10:00:03Z',
          charts: null,
        },
      ],
    });
  }),

  // CHAT-HIST-001: 세션 메시지 조회
  http.get('*/api/v1/conversations/sessions/:sessionId/messages', ({ params, request }) => {
    const url = new URL(request.url);
    return HttpResponse.json({
      user_id: url.searchParams.get('user_id'),
      session_id: params.sessionId,
      messages: [
        {
          id: 1,
          role: 'user',
          content: '이전 질문입니다',
          turn_index: 1,
          created_at: '2026-04-17T10:00:00Z',
          charts: null,
        },
        {
          id: 2,
          role: 'assistant',
          content: '이전 답변입니다',
          turn_index: 1,
          created_at: '2026-04-17T10:00:03Z',
          charts: null,
        },
      ],
    });
  }),

  // AGENT-STORE: 내 에이전트 목록 (static path — must precede :agentId)
  http.get(`*${API_ENDPOINTS.AGENT_STORE_MY}`, () =>
    HttpResponse.json({
      agents: [
        {
          agent_id: 'my-1',
          name: '내 에이전트',
          description: '내가 만든 에이전트',
          source_type: 'owned',
          visibility: 'private',
          temperature: 0.5,
          owner_user_id: 'user-me',
          forked_from: null,
          is_pinned: false,
          created_at: '2026-04-20T10:00:00Z',
        },
      ],
      total: 1,
      page: 1,
      size: 20,
    }),
  ),

  // AGENT-STORE: 포크/구독 통계 (sub-path — must precede :agentId)
  http.get('*/api/v1/agents/:agentId/forks', ({ params }) =>
    HttpResponse.json({
      agent_id: params.agentId as string,
      fork_count: 5,
      subscriber_count: 12,
    }),
  ),

  // AGENT-STORE: 에이전트 목록
  http.get(`*${API_ENDPOINTS.AGENT_STORE_LIST}`, ({ request }) => {
    const url = new URL(request.url);
    const search = url.searchParams.get('search');
    const agents = [
      {
        agent_id: 'agent-1',
        name: '문서 분석가',
        description: '문서를 분석하는 AI 에이전트',
        visibility: 'public',
        department_name: null,
        owner_user_id: 'user-1',
        owner_email: 'owner@test.com',
        temperature: 0.7,
        can_edit: false,
        can_delete: false,
        created_at: '2026-04-20T10:00:00Z',
      },
      {
        agent_id: 'agent-2',
        name: '코드 리뷰어',
        description: '코드를 리뷰하는 AI 에이전트',
        visibility: 'public',
        department_name: 'IT부서',
        owner_user_id: 'user-2',
        owner_email: 'dev@test.com',
        temperature: 0.3,
        can_edit: false,
        can_delete: false,
        created_at: '2026-04-21T10:00:00Z',
      },
    ];
    const filtered = search
      ? agents.filter((a) => a.name.includes(search))
      : agents;
    return HttpResponse.json({
      agents: filtered,
      total: filtered.length,
      page: Number(url.searchParams.get('page') ?? '1'),
      size: Number(url.searchParams.get('size') ?? '20'),
    });
  }),

  // AGENT-STORE: 에이전트 상세
  http.get('*/api/v1/agents/:agentId', ({ params }) =>
    HttpResponse.json({
      agent_id: params.agentId as string,
      name: '문서 분석가',
      description: '문서를 분석하는 AI 에이전트',
      system_prompt: '당신은 문서 분석 전문가입니다.',
      tool_ids: ['tool-1'],
      workers: [
        { tool_id: 'tool-1', worker_id: 'w-1', description: '검색 도구', sort_order: 1, tool_config: null },
      ],
      flow_hint: 'sequential',
      llm_model_id: 'gpt-4o',
      status: 'active',
      visibility: 'public',
      department_id: null,
      department_name: null,
      temperature: 0.7,
      owner_user_id: 'user-1',
      can_edit: true,
      can_delete: true,
      created_at: '2026-04-20T10:00:00Z',
      updated_at: '2026-04-20T10:00:00Z',
    }),
  ),

  // AGENT-STORE: 구독
  http.post('*/api/v1/agents/:agentId/subscribe', ({ params }) =>
    HttpResponse.json({
      subscription_id: 'sub-1',
      agent_id: params.agentId as string,
      agent_name: '문서 분석가',
      is_pinned: false,
      subscribed_at: '2026-04-22T10:00:00Z',
    }),
  ),

  // AGENT-STORE: 구독 해제
  http.delete('*/api/v1/agents/:agentId/subscribe', () =>
    new HttpResponse(null, { status: 204 }),
  ),

  // AGENT-SUBSCRIPTION: 구독 설정 변경 (pin toggle)
  http.patch('*/api/v1/agents/:agentId/subscribe', async ({ params, request }) => {
    const body = (await request.json()) as { is_pinned: boolean };
    return HttpResponse.json({
      subscription_id: 'sub-1',
      agent_id: params.agentId as string,
      agent_name: 'test',
      is_pinned: body.is_pinned,
      subscribed_at: '2026-05-01T00:00:00Z',
    });
  }),

  // AGENT-STORE: 포크
  http.post('*/api/v1/agents/:agentId/fork', ({ params }) =>
    HttpResponse.json({
      agent_id: 'forked-1',
      name: '문서 분석가 (포크)',
      forked_from: params.agentId as string,
      forked_at: '2026-04-22T10:00:00Z',
      system_prompt: '당신은 문서 분석 전문가입니다.',
      workers: [],
      visibility: 'private',
      temperature: 0.7,
      llm_model_id: 'gpt-4o',
    }),
  ),

  // ── Agent-Skill 부착 (skill-agent-integration Phase A) ──
  http.get('*/api/v1/agents/:agentId/skills', ({ params }) =>
    HttpResponse.json({
      agent_id: params.agentId as string,
      skills: [
        {
          skill_id: 'skill-1',
          name: '환율 계산기',
          description: '통화 변환',
          script_type: 'python',
          sort_order: 0,
          has_script: true,
        },
      ],
      total: 1,
      max_attachable: 3,
    }),
  ),
  http.post('*/api/v1/agents/:agentId/skills', async ({ request }) => {
    const body = (await request.json()) as { skill_id: string };
    return HttpResponse.json(
      {
        skill_id: body.skill_id,
        name: '문서 요약',
        description: '요약',
        script_type: 'none',
        sort_order: 1,
        has_script: false,
      },
      { status: 201 },
    );
  }),
  http.delete('*/api/v1/agents/:agentId/skills/:skillId', () =>
    new HttpResponse(null, { status: 204 }),
  ),

  // ── Agent Composer (fix-agent-composer) ─────────────────
  http.post(`*${API_ENDPOINTS.AGENT_COMPOSE}`, () =>
    HttpResponse.json({
      coverage: 'partial',
      name_suggestion: '재무 리포터',
      system_prompt: '당신은 재무 데이터 수집·보고 에이전트입니다.',
      tool_ids: ['tavily_search', 'mcp_srv-1'],
      workers: [
        {
          tool_id: 'tavily_search',
          worker_id: 'search_worker',
          description: '웹에서 재무 데이터 검색',
          sort_order: 0,
          tool_config: null,
          worker_type: 'tool',
          ref_agent_id: null,
          ref_agent_name: null,
          instruction: '최신 재무 정보가 필요할 때 사용. 핵심 키워드로 검색.',
        },
      ],
      flow_hint: 'tavily_search → mcp_srv-1',
      llm_model_id: 'model-default',
      temperature: 0.7,
      missing_capabilities: [
        {
          capability: '사내 ERP 조회',
          reason: '매칭되는 내부/MCP 도구 없음',
          suggestion: 'ERP MCP 서버 등록 필요',
        },
      ],
      notes: '웹 수집은 Tavily로 대체했습니다.',
    }),
  ),

  // ── Agent Schedule (agent-schedule) ─────────────────────
  http.get('*/api/v1/agents/:agentId/schedules', ({ params }) =>
    HttpResponse.json(scheduleStore.get(params.agentId as string) ?? []),
  ),
  http.post('*/api/v1/agents/:agentId/schedules', async ({ params, request }) => {
    const agentId = params.agentId as string;
    const list = scheduleStore.get(agentId) ?? [];
    if (list.length >= 10) {
      return HttpResponse.json(
        { detail: '에이전트당 스케줄은 최대 10개까지 등록할 수 있습니다.' },
        { status: 400 },
      );
    }
    const body = (await request.json()) as Record<string, unknown>;
    const created = mockSchedule({
      agent_id: agentId,
      ...(body as Partial<ScheduleResponse>),
    });
    scheduleStore.set(agentId, [...list, created]);
    return HttpResponse.json(created, { status: 201 });
  }),
  http.put('*/api/v1/agents/:agentId/schedules/:scheduleId', async ({ params, request }) => {
    const agentId = params.agentId as string;
    const list = scheduleStore.get(agentId) ?? [];
    const target = list.find((s) => s.id === params.scheduleId);
    if (!target) return HttpResponse.json({ detail: 'not found' }, { status: 404 });
    const body = (await request.json()) as Partial<ScheduleResponse>;
    const updated = { ...target, ...body, updated_at: '2026-07-03T01:00:00Z' };
    scheduleStore.set(agentId, list.map((s) => (s.id === updated.id ? updated : s)));
    return HttpResponse.json(updated);
  }),
  http.delete('*/api/v1/agents/:agentId/schedules/:scheduleId', ({ params }) => {
    const agentId = params.agentId as string;
    const list = scheduleStore.get(agentId) ?? [];
    if (!list.some((s) => s.id === params.scheduleId)) {
      return HttpResponse.json({ detail: 'not found' }, { status: 404 });
    }
    scheduleStore.set(agentId, list.filter((s) => s.id !== params.scheduleId));
    return new HttpResponse(null, { status: 204 });
  }),
  http.patch('*/api/v1/agents/:agentId/schedules/:scheduleId/enabled', async ({ params, request }) => {
    const agentId = params.agentId as string;
    const list = scheduleStore.get(agentId) ?? [];
    const target = list.find((s) => s.id === params.scheduleId);
    if (!target) return HttpResponse.json({ detail: 'not found' }, { status: 404 });
    const body = (await request.json()) as { enabled: boolean };
    const updated = { ...target, enabled: body.enabled };
    scheduleStore.set(agentId, list.map((s) => (s.id === updated.id ? updated : s)));
    return HttpResponse.json(updated);
  }),
  http.get('*/api/v1/agents/:agentId/schedules/:scheduleId/runs', ({ params }) =>
    HttpResponse.json([
      {
        id: 'run-1',
        schedule_id: params.scheduleId as string,
        status: 'success',
        scheduled_for: '2026-07-03T00:00:00Z',
        started_at: '2026-07-03T00:00:01Z',
        finished_at: '2026-07-03T00:00:14Z',
        session_id: 'sess-1',
        run_id: 'airun-1',
        error_message: null,
      },
      {
        id: 'run-2',
        schedule_id: params.scheduleId as string,
        status: 'failed',
        scheduled_for: '2026-07-02T00:00:00Z',
        started_at: '2026-07-02T00:00:01Z',
        finished_at: '2026-07-02T00:00:05Z',
        session_id: null,
        run_id: null,
        error_message: 'LLM timeout',
      },
    ]),
  ),

  // ── Wiki (LLM-WIKI-001) ─────────────────────────────────
  http.post(`*${API_ENDPOINTS.WIKI_DISTILL}`, async () =>
    HttpResponse.json({
      agent_id: 'agent-1',
      created_count: 2,
      items: [mockWikiArticle('w1'), mockWikiArticle('w2')],
    }),
  ),
  http.get(`*${API_ENDPOINTS.WIKI_LIST}`, ({ request }) => {
    const url = new URL(request.url);
    const status = url.searchParams.get('status');
    const items = status
      ? [mockWikiArticle('w1', status)]
      : [mockWikiArticle('w1'), mockWikiArticle('w2', 'approved')];
    return HttpResponse.json({ items, total: items.length });
  }),
  http.get('*/api/v1/wiki/:id', ({ params }) =>
    HttpResponse.json(mockWikiArticle(String(params.id))),
  ),
  http.patch('*/api/v1/wiki/:id/approve', ({ params }) =>
    HttpResponse.json(mockWikiArticle(String(params.id), 'approved')),
  ),
  http.patch('*/api/v1/wiki/:id/reject', ({ params }) =>
    HttpResponse.json(mockWikiArticle(String(params.id), 'deprecated')),
  ),
  http.patch('*/api/v1/wiki/:id/deprecate', ({ params }) =>
    HttpResponse.json(mockWikiArticle(String(params.id), 'deprecated')),
  ),
  http.patch('*/api/v1/wiki/:id/restore', ({ params }) =>
    HttpResponse.json(mockWikiArticle(String(params.id), 'approved')),
  ),
  http.put('*/api/v1/wiki/:id', ({ params }) =>
    HttpResponse.json({ ...mockWikiArticle(String(params.id)), version: 2 }),
  ),
];

function mockWikiArticle(id: string, status = 'draft') {
  return {
    id,
    agent_id: 'agent-1',
    title: `위키-${id}`,
    content: '정제된 본문',
    source_type: 'distilled',
    source_refs: ['doc:1'],
    status,
    confidence: 0.8,
    valid_until: null,
    version: 1,
    editor_id: null,
    reviewer_id: null,
    created_at: '2026-06-30T00:00:00Z',
    updated_at: '2026-06-30T00:00:00Z',
  };
}
