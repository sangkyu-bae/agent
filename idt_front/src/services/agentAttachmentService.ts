import apiClient from '@/services/api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type { AgentAttachmentUploadResponse } from '@/types/agentAttachment';
import authApiClient from './api/authClient';

/**
 * Agent 첨부 업로드 서비스 — ws-agent-excel-attachment.
 * 엑셀을 multipart로 업로드해 file_id를 발급받는다.
 * 발급된 file_id는 useAgentRunStream의 subscribe attachments로 참조한다.
 */
const agentAttachmentService = {
  uploadExcel: async (file: File): Promise<AgentAttachmentUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await authApiClient.post<AgentAttachmentUploadResponse>(
      API_ENDPOINTS.AGENT_ATTACHMENT_UPLOAD,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120_000,
      },
    );
    return response.data;
  },
};

export default agentAttachmentService;
