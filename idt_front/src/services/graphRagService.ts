// graph-rag-foundation Design §4.1 — 그래프 RAG 관리자 API. 컴포넌트는 이 서비스만 경유한다.
import authApiClient from '@/services/api/authClient';
import { ApiError } from '@/services/api/ApiError';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  EntityDetailResponse,
  EntityListParams,
  EntityListResponse,
  ExtractAcceptedResponse,
  ExtractMode,
  GraphHealthResponse,
  GraphRagCapabilities,
  GraphRagSettingsRequest,
  GraphRagSettingsResponse,
  IntegrityResponse,
  KbDocumentJobsResponse,
  ReviewListResponse,
  ReviewRejectRequest,
  SearchTestRequest,
  SearchTestResponse,
  StageChangeRequest,
  TopicCreateRequest,
  TopicItem,
  TopicListResponse,
  TopicUpdateRequest,
} from '@/types/graphRag';

/** 주제 판정(LLM)·하이브리드 비교까지 포함 — 서버 상한 5초 + 여유 */
const SEARCH_TEST_TIMEOUT_MS = 60_000;

export const graphRagService = {
  /** 모듈이 등록되지 않으면 404 → 보이지 않음으로 처리(Design §4.1) */
  getCapabilities: async (): Promise<GraphRagCapabilities> => {
    try {
      const { data } = await authApiClient.get<GraphRagCapabilities>(
        API_ENDPOINTS.GRAPH_RAG_CAPABILITIES
      );
      return data;
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return { visible: false };
      throw err;
    }
  },

  getSettings: async (): Promise<GraphRagSettingsResponse> => {
    const { data } = await authApiClient.get<GraphRagSettingsResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_SETTINGS
    );
    return data;
  },

  updateSettings: async (req: GraphRagSettingsRequest): Promise<GraphRagSettingsResponse> => {
    const { data } = await authApiClient.put<GraphRagSettingsResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_SETTINGS,
      req
    );
    return data;
  },

  changeStage: async (req: StageChangeRequest): Promise<GraphRagSettingsResponse> => {
    const { data } = await authApiClient.post<GraphRagSettingsResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_STAGE,
      req
    );
    return data;
  },

  getHealth: async (): Promise<GraphHealthResponse> => {
    const { data } = await authApiClient.get<GraphHealthResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_HEALTH
    );
    return data;
  },

  getKbDocuments: async (kbId: string): Promise<KbDocumentJobsResponse> => {
    const { data } = await authApiClient.get<KbDocumentJobsResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_KB_DOCUMENTS(kbId),
      { params: { limit: 200 } }
    );
    return data;
  },

  extract: async (documentId: string, mode: ExtractMode): Promise<ExtractAcceptedResponse> => {
    const { data } = await authApiClient.post<ExtractAcceptedResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_EXTRACT(documentId),
      { mode }
    );
    return data;
  },

  getReview: async (status = 'pending'): Promise<ReviewListResponse> => {
    const { data } = await authApiClient.get<ReviewListResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_REVIEW,
      { params: { status, limit: 200 } }
    );
    return data;
  },

  approveReview: async (id: string, note?: string | null): Promise<void> => {
    await authApiClient.post(API_ENDPOINTS.ADMIN_GRAPH_RAG_REVIEW_APPROVE(id), {
      note: note || null,
    });
  },

  rejectReview: async (id: string, req: ReviewRejectRequest): Promise<{ entity_id: string }> => {
    const { data } = await authApiClient.post<{ entity_id: string }>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_REVIEW_REJECT(id),
      req
    );
    return data;
  },

  getTopics: async (includeRetired = false): Promise<TopicListResponse> => {
    const { data } = await authApiClient.get<TopicListResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_TOPICS,
      { params: { include_retired: includeRetired } }
    );
    return data;
  },

  createTopic: async (req: TopicCreateRequest): Promise<TopicItem> => {
    const { data } = await authApiClient.post<TopicItem>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_TOPICS,
      req
    );
    return data;
  },

  updateTopic: async (id: string, req: TopicUpdateRequest): Promise<TopicItem> => {
    const { data } = await authApiClient.patch<TopicItem>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_TOPIC(id),
      req
    );
    return data;
  },

  getEntities: async (params: EntityListParams): Promise<EntityListResponse> => {
    const { data } = await authApiClient.get<EntityListResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_ENTITIES,
      { params: { ...params, q: params.q || undefined, type: params.type || undefined } }
    );
    return data;
  },

  getEntity: async (id: string): Promise<EntityDetailResponse> => {
    const { data } = await authApiClient.get<EntityDetailResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_ENTITY(id)
    );
    return data;
  },

  searchTest: async (req: SearchTestRequest): Promise<SearchTestResponse> => {
    const { data } = await authApiClient.post<SearchTestResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_SEARCH_TEST,
      req,
      { timeout: SEARCH_TEST_TIMEOUT_MS }
    );
    return data;
  },

  checkIntegrity: async (kbId?: string | null): Promise<IntegrityResponse> => {
    const { data } = await authApiClient.get<IntegrityResponse>(
      API_ENDPOINTS.ADMIN_GRAPH_RAG_INTEGRITY,
      { params: { kb_id: kbId || undefined } }
    );
    return data;
  },
};
