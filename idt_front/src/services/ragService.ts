import apiClient from './api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type { Document, DocumentChunk, UploadDocumentResponse, RetrieveRequest, RetrievedChunk } from '@/types/rag';
import type { ApiResponse, PaginatedResponse } from '@/types/api';

export const ragService = {
  getDocuments: () =>
    apiClient.get<PaginatedResponse<Document>>(API_ENDPOINTS.DOCUMENTS),

  uploadDocument: (file: File, metadata?: Record<string, string>) => {
    const form = new FormData();
    form.append('file', file);
    if (metadata) form.append('metadata', JSON.stringify(metadata));
    return apiClient.post<ApiResponse<UploadDocumentResponse>>(
      API_ENDPOINTS.DOCUMENT_UPLOAD,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
  },

  deleteDocument: (docId: string) =>
    apiClient.delete(API_ENDPOINTS.DOCUMENT_DELETE(docId)),

  retrieve: (payload: RetrieveRequest) =>
    apiClient.post<ApiResponse<RetrievedChunk[]>>(API_ENDPOINTS.RETRIEVE, payload),

  getDocumentChunks: (docId: string) =>
    apiClient.get<ApiResponse<DocumentChunk[]>>(API_ENDPOINTS.DOCUMENT_CHUNKS(docId)),
};
