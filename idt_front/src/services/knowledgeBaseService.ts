import authApiClient from '@/services/api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type { KnowledgeBaseInfo } from '@/types/ragToolConfig';
import type {
  CreateKnowledgeBaseRequest,
  DocumentVersion,
  DocumentVersionsResponse,
  KbCreateResponse,
  KbDocumentChunksParams,
  KbDocumentDeleteResponse,
  KbDocumentChunksResponse,
  KbDocumentListResponse,
  KbDocumentSummaryResponse,
  KbMessageResponse,
  KbSearchHistoryResponse,
  KbSearchRequest,
  KbSearchResponse,
  KbSectionSummaryListResponse,
  KbStoreSource,
  KbUploadResponse,
  RevisionCheckResponse,
  RevisionLinkResponse,
  RevisionMetaRequest,
  RevisionModeResponse,
  RevisionRollbackResponse,
  RevisionSyncResponse,
  RevisionUploadOptions,
  RollbackMode,
  SectionSummaryStatusResponse,
  UpdateKbChunkingRequest,
} from '@/types/knowledgeBase';

interface KnowledgeBasesResponse {
  knowledge_bases: KnowledgeBaseInfo[];
  total: number;
}

const knowledgeBaseService = {
  getKnowledgeBases: async (): Promise<KnowledgeBaseInfo[]> => {
    const { data } = await authApiClient.get<KnowledgeBasesResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASES,
    );
    return data.knowledge_bases;
  },

  getKnowledgeBase: async (kbId: string): Promise<KnowledgeBaseInfo> => {
    const { data } = await authApiClient.get<KnowledgeBaseInfo>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DETAIL(kbId),
    );
    return data;
  },

  createKnowledgeBase: async (
    body: CreateKnowledgeBaseRequest,
  ): Promise<KbCreateResponse> => {
    const { data } = await authApiClient.post<KbCreateResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASES,
      body,
    );
    return data;
  },

  // kb-custom-chunking D7: 청킹 설정 전체 교체 (신규 업로드부터 적용)
  updateKbChunking: async (
    kbId: string,
    body: UpdateKbChunkingRequest,
  ): Promise<KnowledgeBaseInfo> => {
    const { data } = await authApiClient.patch<KnowledgeBaseInfo>(
      API_ENDPOINTS.KNOWLEDGE_BASE_CHUNKING(kbId),
      body,
    );
    return data;
  },

  deleteKnowledgeBase: async (kbId: string): Promise<KbMessageResponse> => {
    const { data } = await authApiClient.delete<KbMessageResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DETAIL(kbId),
    );
    return data;
  },

  getKbDocuments: async (
    kbId: string,
    params?: { offset?: number; limit?: number },
  ): Promise<KbDocumentListResponse> => {
    const { data } = await authApiClient.get<KbDocumentListResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(kbId),
      { params },
    );
    return data;
  },

  deleteKbDocument: async (
    kbId: string,
    documentId: string,
    // document-revision §4.2 #9 — 미지정이면 서버 기본(이전 버전 복귀)
    options?: { restorePrevious?: boolean },
  ): Promise<KbDocumentDeleteResponse> => {
    const params =
      options?.restorePrevious === undefined
        ? undefined
        : { restore_previous: options.restorePrevious };
    const { data } = await authApiClient.delete<KbDocumentDeleteResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_DETAIL(kbId, documentId),
      { params },
    );
    return data;
  },

  // 동기 파싱+임베딩이라 수십 초 가능 — unifiedUploadService 선례의 timeout 상향(D6)
  uploadKbDocument: async (
    kbId: string,
    file: File,
    // document-revision §4.2 #2 — 개정 확정 입력 (빈 값은 보내지 않음)
    revision?: RevisionUploadOptions,
  ): Promise<KbUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const fields: [string, string | null | undefined][] = [
      ['supersedes_document_id', revision?.supersedesDocumentId],
      ['version_label', revision?.versionLabel],
      ['effective_date', revision?.effectiveDate],
      ['revision_check_id', revision?.revisionCheckId],
    ];
    for (const [key, value] of fields) {
      if (value) formData.append(key, value);
    }
    const { data } = await authApiClient.post<KbUploadResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(kbId),
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120_000,
      },
    );
    return data;
  },

  // ── KB 저장 내용 조회 (kb-content-browser) ─────────────────

  getKbDocumentSummary: async (
    kbId: string,
    documentId: string,
    source: KbStoreSource,
  ): Promise<KbDocumentSummaryResponse> => {
    const { data } = await authApiClient.get<KbDocumentSummaryResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_SUMMARY(kbId, documentId),
      { params: { source } },
    );
    return data;
  },

  getKbSectionSummaries: async (
    kbId: string,
    documentId: string,
    source: KbStoreSource,
  ): Promise<KbSectionSummaryListResponse> => {
    const { data } = await authApiClient.get<KbSectionSummaryListResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_SECTION_SUMMARIES(kbId, documentId),
      { params: { source } },
    );
    return data;
  },

  getKbDocumentChunks: async (
    kbId: string,
    documentId: string,
    params: KbDocumentChunksParams,
  ): Promise<KbDocumentChunksResponse> => {
    const { data } = await authApiClient.get<KbDocumentChunksResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_CHUNKS(kbId, documentId),
      { params },
    );
    return data;
  },

  getSectionSummaryStatus: async (
    kbId: string,
    documentId: string,
  ): Promise<SectionSummaryStatusResponse> => {
    const { data } = await authApiClient.get<SectionSummaryStatusResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_SECTION_SUMMARY_STATUS(kbId, documentId),
    );
    return data;
  },

  // ── KB 리트리버 테스트 (kb-retrieval-test) ─────────────────

  searchKb: async (
    kbId: string,
    body: KbSearchRequest,
  ): Promise<KbSearchResponse> => {
    const { data } = await authApiClient.post<KbSearchResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_SEARCH(kbId),
      body,
    );
    return data;
  },

  getKbSearchHistory: async (
    kbId: string,
    params?: { limit?: number; offset?: number },
  ): Promise<KbSearchHistoryResponse> => {
    const { data } = await authApiClient.get<KbSearchHistoryResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_SEARCH_HISTORY(kbId),
      { params },
    );
    return data;
  },

  retrySectionSummary: async (
    kbId: string,
    documentId: string,
  ): Promise<SectionSummaryStatusResponse> => {
    const { data } = await authApiClient.post<SectionSummaryStatusResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_SECTION_SUMMARY_RETRY(kbId, documentId),
    );
    return data;
  },

  // ── 문서 개정 (document-revision Design §4.2) ──────────────────
  /** 업로드 전 사전 점검 — 파싱·LLM 판정 포함이라 업로드와 같은 timeout */
  checkKbRevision: async (
    kbId: string,
    file: File,
  ): Promise<RevisionCheckResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await authApiClient.post<RevisionCheckResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_CHECK(kbId),
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120_000,
      },
    );
    return data;
  },

  getDocumentVersions: async (
    kbId: string,
    documentId: string,
  ): Promise<DocumentVersionsResponse> => {
    const { data } = await authApiClient.get<DocumentVersionsResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_VERSIONS(kbId, documentId),
    );
    return data;
  },

  rollbackRevision: async (
    kbId: string,
    documentId: string,
    mode: RollbackMode,
  ): Promise<RevisionRollbackResponse> => {
    const { data } = await authApiClient.post<RevisionRollbackResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_ROLLBACK(kbId, documentId),
      { mode },
    );
    return data;
  },

  linkRevision: async (
    kbId: string,
    documentId: string,
    supersedesDocumentId: string,
  ): Promise<RevisionLinkResponse> => {
    const { data } = await authApiClient.post<RevisionLinkResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_LINK(kbId, documentId),
      { supersedes_document_id: supersedesDocumentId },
    );
    return data;
  },

  updateRevisionMeta: async (
    kbId: string,
    documentId: string,
    body: RevisionMetaRequest,
  ): Promise<DocumentVersion> => {
    const { data } = await authApiClient.patch<DocumentVersion>(
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_META(kbId, documentId),
      body,
    );
    return data;
  },

  retryRevisionSync: async (
    kbId: string,
    documentId: string,
  ): Promise<RevisionSyncResponse> => {
    const { data } = await authApiClient.post<RevisionSyncResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_SYNC(kbId, documentId),
    );
    return data;
  },

  updateRevisionMode: async (
    kbId: string,
    revisionMode: string,
  ): Promise<RevisionModeResponse> => {
    const { data } = await authApiClient.patch<RevisionModeResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_MODE(kbId),
      { revision_mode: revisionMode },
    );
    return data;
  },
};

export default knowledgeBaseService;
