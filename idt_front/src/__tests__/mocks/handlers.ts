import { http, HttpResponse } from 'msw';
import { API_ENDPOINTS } from '@/constants/api';

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

  // LLM-MODEL-FRONT-001: LLM 모델 목록 조회
  http.get(`*${API_ENDPOINTS.LLM_MODELS}`, () =>
    HttpResponse.json({
      models: [
        {
          id: 'uuid-1',
          provider: 'openai',
          model_name: 'gpt-4o',
          display_name: 'GPT-4o',
          description: 'OpenAI GPT-4o model',
          max_tokens: null,
          is_active: true,
          is_default: true,
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
        },
      ],
    })
  ),

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
        },
        {
          id: 2,
          role: 'assistant',
          content: '이전 답변입니다',
          turn_index: 1,
          created_at: '2026-04-17T10:00:03Z',
        },
      ],
    });
  }),
];
