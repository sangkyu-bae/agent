// graph-rag-foundation — MSW 기본 핸들러·픽스처. 테스트별 상황은 server.use 로 덮는다.
// capabilities 기본값은 visible=false(일반 화면 테스트에 토글이 끼어들지 않게).
import { http, HttpResponse } from 'msw';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  EntityDetailResponse,
  EntityListResponse,
  GraphHealthResponse,
  GraphRagSettingsResponse,
  KbDocumentJobsResponse,
  ReviewItem,
  SearchTestResponse,
  TopicItem,
} from '@/types/graphRag';

export const mockGraphSettings = (
  over: Partial<GraphRagSettingsResponse> = {}
): GraphRagSettingsResponse => ({
  rollout_stage: 'admin_only',
  extraction_enabled: true,
  jev_enabled: false,
  link_threshold: 0.85,
  new_threshold: 0.3,
  extraction_llm_model_id: 'uuid-1',
  rejudge_llm_model_id: null,
  concurrency: 2,
  max_llm_calls_per_doc: 300,
  candidate_top_k: 5,
  max_hops: 2,
  graph_rrf_weight: 0.5,
  retrieval_timeout_ms: 800,
  entity_types: ['상품·서비스', '조문', '기타'],
  relation_types: ['포함', '기타'],
  updated_at: '2026-11-17T09:00:00',
  ...over,
});

export const mockGraphHealth = (over: Partial<GraphHealthResponse> = {}): GraphHealthResponse => ({
  backend: 'neo4j',
  connected: true,
  external: true,
  node_count: 120,
  relationship_count: 340,
  node_limit: 200000,
  relationship_limit: 400000,
  error: null,
  ...over,
});

export const mockKbDocuments: KbDocumentJobsResponse = {
  total: 2,
  items: [
    {
      document_id: 'doc-1',
      filename: '여신취급규정.pdf',
      chunk_count: 4,
      job: {
        id: 'job-1', document_id: 'doc-1', kb_id: 'kb-public-1', collection_name: 'c',
        status: 'completed', mode: 'rebuild', trigger_source: 'manual',
        extractor_version: 'v3', total_chunks: 4, processed_chunks: 4, failed_chunks: 0,
        llm_calls: 6, judge_calls: 2, entities_created: 29, entities_linked: 3,
        relations_created: 24, error_message: null, requested_by: '1',
        started_at: '2026-11-17T09:00:00', finished_at: '2026-11-17T09:01:00',
        created_at: '2026-11-17T09:00:00',
      },
    },
    { document_id: 'doc-2', filename: '회의실 운영 안내.docx', chunk_count: 1, job: null },
  ],
};

export const mockReviewItem = (over: Partial<ReviewItem> = {}): ReviewItem => ({
  id: 'dec-1', job_id: 'job-1', document_id: 'doc-1', chunk_id: 'chunk-1',
  mention_text: '운전자금 한도', mention_type: '용어',
  candidates: [
    { label: 'A', entity_id: 'ent-1', name: '운전자금대출 한도', type: '용어' },
    { label: 'B', entity_id: 'ent-2', name: '시설자금 한도', type: '용어' },
  ],
  probabilities: { A: 0.62, B: 0.21, NEW: 0.17 },
  chosen_label: 'A', entity_id: 'ent-1', created_new: false,
  decided_by: 'llm_rejudge', band: 'ambiguous', probability: 0.62,
  llm_confidence: 'medium', llm_reason: '같은 한도 개념', review_status: 'pending',
  created_at: '2026-11-17T09:00:00', kind: 'entity',
  ...over,
});

export const mockTopics: TopicItem[] = [
  {
    id: 't-loan', name: '여신관리', level: 1, parent_id: null, description: '',
    status: 'active', origin: 'admin', created_by: '1', document_count: 1,
    created_at: null, updated_at: null,
  },
  {
    id: 't-corp', name: '기업대출 심사기준', level: 2, parent_id: 't-loan', description: '',
    status: 'pending', origin: 'auto', created_by: null, document_count: 1,
    created_at: null, updated_at: null,
  },
  {
    id: 't-ga', name: '총무', level: 1, parent_id: null, description: '',
    status: 'pending', origin: 'auto', created_by: null, document_count: 1,
    created_at: null, updated_at: null,
  },
];

export const mockEntities: EntityListResponse = {
  total: 2, page: 1, size: 20,
  items: [
    { id: 'ent-1', name: '운전자금대출', type: '상품·서비스', description: '',
      mention_count: 3, relation_count: 5 },
    { id: 'ent-2', name: '제3조', type: '조문', description: '', mention_count: 1,
      relation_count: 2 },
  ],
};

export const mockEntityDetail: EntityDetailResponse = {
  entity: mockEntities.items[0],
  aliases: ['운전자금 대출'],
  relations: [
    { id: 'r-1', direction: 'out', kind: 'RELATES', type: '한도', other_id: 'ent-9',
      other_name: '연매출액의 30%', evidence_chunk_id: 'chunk-1', evidence_text: '근거',
      document_id: 'doc-1' },
  ],
  mentions: [
    { chunk_id: 'chunk-1', document_id: 'doc-1', decision_id: 'dec-1',
      preview: '운전자금대출의 한도는 연매출액의 30% 이내로 한다.' },
  ],
};

const hit = (id: string, source: string, score: number) => ({
  chunk_id: id, document_id: 'doc-1', filename: '여신취급규정.pdf', score, source,
  content_preview: `${id} 본문 미리보기`,
});

export const mockSearchTest: SearchTestResponse = {
  scope: { topic_ids: ['t-loan'], topic_names: ['여신관리'], decided_by: 'llm', reason: null },
  linked_entities: [
    { id: 'ent-1', name: '운전자금대출', type: '상품·서비스', via: 'exact', score: 1 },
  ],
  paths: [{ hops: 1, path: ['운전자금대출', '한도→', '연매출액의 30%'], evidence_chunk_ids: ['chunk-1'] }],
  graph_hits: [hit('chunk-1', 'graph', 1.5)],
  hybrid_hits: [hit('chunk-2', 'bm25_only', 0.03)],
  fused_hits: [hit('chunk-1', 'graph', 0.02), hit('chunk-2', 'bm25_only', 0.016)],
  timings_ms: { route_link: 1700, traverse: 120, fetch: 60, hybrid: 300 },
  filtered_out: 1,
  skip_reason: null,
  hybrid_error: null,
};

export const graphRagHandlers = [
  http.get(`*${API_ENDPOINTS.GRAPH_RAG_CAPABILITIES}`, () =>
    HttpResponse.json({ visible: false })
  ),
  http.get(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_SETTINGS}`, () =>
    HttpResponse.json(mockGraphSettings())
  ),
  http.put(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_SETTINGS}`, async ({ request }) =>
    HttpResponse.json({ ...mockGraphSettings(), ...((await request.json()) as object) })
  ),
  http.post(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_STAGE}`, async ({ request }) => {
    const body = (await request.json()) as { to_stage: string };
    return HttpResponse.json(mockGraphSettings({ rollout_stage: body.to_stage as never }));
  }),
  http.get(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_HEALTH}`, () => HttpResponse.json(mockGraphHealth())),
  http.get('*/api/v1/admin/graph-rag/kbs/:kbId/documents', () =>
    HttpResponse.json(mockKbDocuments)
  ),
  http.post('*/api/v1/admin/graph-rag/documents/:id/extract', () =>
    HttpResponse.json({ job_id: 'job-9', status: 'pending' }, { status: 202 })
  ),
  http.get(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_REVIEW}`, () =>
    HttpResponse.json({ items: [mockReviewItem()], total: 1 })
  ),
  http.post('*/api/v1/admin/graph-rag/review/:id/approve', () =>
    new HttpResponse(null, { status: 204 })
  ),
  http.post('*/api/v1/admin/graph-rag/review/:id/reject', () =>
    HttpResponse.json({ entity_id: 'ent-new' })
  ),
  http.get(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_TOPICS}`, () =>
    HttpResponse.json({ items: mockTopics })
  ),
  http.post(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_TOPICS}`, async ({ request }) => {
    const body = (await request.json()) as Partial<TopicItem>;
    return HttpResponse.json(
      { ...mockTopics[0], id: 't-new', ...body, origin: 'admin', document_count: 0 },
      { status: 201 }
    );
  }),
  http.patch('*/api/v1/admin/graph-rag/topics/:id', async ({ params, request }) => {
    const body = (await request.json()) as Partial<TopicItem>;
    const base = mockTopics.find((t) => t.id === params.id) ?? mockTopics[0];
    return HttpResponse.json({ ...base, ...body });
  }),
  http.get(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_ENTITIES}`, () => HttpResponse.json(mockEntities)),
  http.get('*/api/v1/admin/graph-rag/entities/:id', () => HttpResponse.json(mockEntityDetail)),
  http.post(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_SEARCH_TEST}`, () =>
    HttpResponse.json(mockSearchTest)
  ),
  http.get(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_INTEGRITY}`, () =>
    HttpResponse.json({ checked: 4, missing: 0, missing_chunk_ids: [], missing_document_ids: [] })
  ),
];
