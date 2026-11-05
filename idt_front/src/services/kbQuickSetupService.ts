// agent-kb-quick-setup Design §4.1 — /quick, /kb-defaults, /admin/kb-defaults. 컴포넌트는 이 서비스만 경유한다.
import authApiClient from '@/services/api/authClient';
import knowledgeBaseService from '@/services/knowledgeBaseService';
import { API_ENDPOINTS } from '@/constants/api';
import {
  KB_QUICK_DOC_STATUS,
  type AdminKbDefaultsResponse,
  type AdminKbDefaultsUpdateRequest,
  type KbDefaultsInfo,
  type QuickKbDocumentResult,
  type QuickKbRequest,
  type QuickKbResponse,
} from '@/types/kbQuickSetup';

const failureMessage = (err: unknown): string =>
  err instanceof Error && err.message ? err.message : '올리지 못했습니다';

export const kbQuickSetupService = {
  /** multipart — 파일은 `files` 키로 반복 append (서버 `files: list[UploadFile]`) */
  quickCreate: async (req: QuickKbRequest): Promise<QuickKbResponse> => {
    const form = new FormData();
    form.append('name', req.name);
    form.append('scope', req.scope);
    if (req.departmentId) form.append('department_id', req.departmentId);
    for (const file of req.files) form.append('files', file);
    const { data } = await authApiClient.post<QuickKbResponse>(
      API_ENDPOINTS.KNOWLEDGE_BASE_QUICK,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300_000 },
    );
    return data;
  },

  /**
   * Check G1 — 이미 만들어진 KB 에 파일만 순차 재업로드한다(/quick 재호출 금지).
   * 파일 단위 실패는 서버 /quick 과 같은 규칙으로 status=failed 에 담는다.
   */
  retryUploadToKb: async (kb: QuickKbResponse, files: File[]): Promise<QuickKbResponse> => {
    const documents: QuickKbDocumentResult[] = [];
    for (const file of files) {
      try {
        const res = await knowledgeBaseService.uploadKbDocument(kb.kb_id, file);
        const failed = res.status === 'failed';
        documents.push({
          filename: file.name,
          status: failed ? KB_QUICK_DOC_STATUS.FAILED : KB_QUICK_DOC_STATUS.UPLOADED,
          document_id: res.document_id,
          chunk_count: res.chunk_count,
          error: failed ? (res.qdrant.error ?? res.es.error ?? '저장 실패') : null,
        });
      } catch (err) {
        documents.push({
          filename: file.name,
          status: KB_QUICK_DOC_STATUS.FAILED,
          document_id: null,
          chunk_count: 0,
          error: failureMessage(err),
        });
      }
    }
    const uploaded = documents.filter((d) => d.status === KB_QUICK_DOC_STATUS.UPLOADED).length;
    return {
      ...kb,
      documents,
      uploaded_count: uploaded,
      failed_count: documents.length - uploaded,
    };
  },

  getKbDefaults: async (): Promise<KbDefaultsInfo> => {
    const { data } = await authApiClient.get<KbDefaultsInfo>(API_ENDPOINTS.KB_DEFAULTS);
    return data;
  },

  getAdminKbDefaults: async (): Promise<AdminKbDefaultsResponse> => {
    const { data } = await authApiClient.get<AdminKbDefaultsResponse>(
      API_ENDPOINTS.ADMIN_KB_DEFAULTS,
    );
    return data;
  },

  updateAdminKbDefaults: async (
    req: AdminKbDefaultsUpdateRequest,
  ): Promise<AdminKbDefaultsResponse> => {
    const { data } = await authApiClient.put<AdminKbDefaultsResponse>(
      API_ENDPOINTS.ADMIN_KB_DEFAULTS,
      req,
    );
    return data;
  },
};
