/**
 * TanStack Query 키 팩토리
 *
 * 모든 queryKey는 이 파일에서 중앙 관리합니다.
 * 계층적 구조로 정의하여 특정 도메인 전체 무효화가 가능합니다.
 *
 * 사용 예시:
 *   useQuery({ queryKey: queryKeys.chat.sessions() })
 *   queryClient.invalidateQueries({ queryKey: queryKeys.documents.all })
 */

export const queryKeys = {
  // ── Chat ───────────────────────────────────────────────
  chat: {
    /** 채팅 도메인 전체 키 — invalidateQueries 용 */
    all: ['chat'] as const,
    /** 세션 목록 */
    sessions: () => [...queryKeys.chat.all, 'sessions'] as const,
    /** 특정 세션 상세 */
    session: (sessionId: string) =>
      [...queryKeys.chat.sessions(), sessionId] as const,
    /** CHAT-HIST-001: 사용자별 대화 세션 목록 */
    history: (userId: string) =>
      [...queryKeys.chat.all, 'history', userId] as const,
    /** CHAT-HIST-001: 세션별 메시지 */
    sessionMessages: (sessionId: string, userId: string) =>
      [...queryKeys.chat.all, 'sessionMessages', sessionId, userId] as const,
  },

  // ── Documents ──────────────────────────────────────────
  documents: {
    /** 문서 도메인 전체 키 */
    all: ['documents'] as const,
    /** 문서 목록 */
    list: () => [...queryKeys.documents.all, 'list'] as const,
    /** 특정 문서 상세 */
    detail: (docId: string) =>
      [...queryKeys.documents.list(), docId] as const,
    /** 특정 문서의 청킹 결과 */
    chunks: (docId: string) =>
      [...queryKeys.documents.all, 'chunks', docId] as const,
    /** 벡터 검색 결과 */
    vectorSearch: (query: string, topK: number) =>
      [...queryKeys.documents.all, 'vectorSearch', query, topK] as const,
  },

  // ── Agent ──────────────────────────────────────────────
  agent: {
    /** Agent 도메인 전체 키 */
    all: ['agent'] as const,
    /** 특정 Agent 실행 상태 */
    run: (runId: string) =>
      [...queryKeys.agent.all, 'run', runId] as const,
    /** 내 에이전트 통합 목록 */
    my: (params?: import('@/types/agent').MyAgentsParams) =>
      [...queryKeys.agent.all, 'my', params] as const,
  },

  // ── Auth ───────────────────────────────────────────────
  auth: {
    /** 인증 도메인 전체 키 */
    all: ['auth'] as const,
    /** 현재 사용자 정보 */
    me: () => [...queryKeys.auth.all, 'me'] as const,
    /** 앱 초기 토큰 복원 */
    init: () => [...queryKeys.auth.all, 'init'] as const,
  },

  // ── Tool Catalog ───────────────────────────────────────
  toolCatalog: {
    all: ['toolCatalog'] as const,
    list: () => [...queryKeys.toolCatalog.all, 'list'] as const,
  },

  // ── LLM Models ─────────────────────────────────────────
  llmModels: {
    all: ['llmModels'] as const,
    list: (includeInactive?: boolean) =>
      [...queryKeys.llmModels.all, 'list', { includeInactive }] as const,
  },

  // ── RAG Tools ──────────────────────────────────────────
  ragTools: {
    all: ['ragTools'] as const,
    collections: () => [...queryKeys.ragTools.all, 'collections'] as const,
    metadataKeys: (collectionName?: string) =>
      [...queryKeys.ragTools.all, 'metadataKeys', collectionName] as const,
  },

  // ── Embedding Models ────────────────────────────────────
  embeddingModels: {
    all: ['embeddingModels'] as const,
    list: () => [...queryKeys.embeddingModels.all, 'list'] as const,
  },

  // ── Collections ────────────────────────────────────────
  collections: {
    all: ['collections'] as const,
    list: () => [...queryKeys.collections.all, 'list'] as const,
    detail: (name: string) =>
      [...queryKeys.collections.all, 'detail', name] as const,
    activityLog: (filters?: import('@/types/collection').ActivityLogFilters) =>
      [...queryKeys.collections.all, 'activityLog', filters] as const,
    collectionActivityLog: (name: string) =>
      [...queryKeys.collections.all, 'collectionActivityLog', name] as const,
    documents: (name: string, params?: import('@/types/collection').CollectionDocumentsParams) =>
      [...queryKeys.collections.all, 'documents', name, params] as const,
    chunks: (name: string, documentId: string, params?: import('@/types/collection').DocumentChunksParams) =>
      [...queryKeys.collections.all, 'chunks', name, documentId, params] as const,
    searchHistory: (name: string, params?: { limit?: number; offset?: number }) =>
      [...queryKeys.collections.all, 'searchHistory', name, params] as const,
  },

  // ── Agent Store ────────────────────────────────────────
  agentStore: {
    all: ['agentStore'] as const,
    list: (params: import('@/types/agentStore').AgentListParams) =>
      [...queryKeys.agentStore.all, 'list', params] as const,
    detail: (agentId: string) =>
      [...queryKeys.agentStore.all, 'detail', agentId] as const,
    my: (params: import('@/types/agentStore').MyAgentListParams) =>
      [...queryKeys.agentStore.all, 'my', params] as const,
    forkStats: (agentId: string) =>
      [...queryKeys.agentStore.all, 'forkStats', agentId] as const,
  },

  // ── Admin ──────────────────────────────────────────────
  admin: {
    /** 관리자 도메인 전체 키 */
    all: ['admin'] as const,
    /** 승인 대기 사용자 목록 */
    pendingUsers: () => [...queryKeys.admin.all, 'pendingUsers'] as const,
  },
} as const;
