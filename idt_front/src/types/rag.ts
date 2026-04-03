export type DocumentStatus = 'uploading' | 'processing' | 'ready' | 'error';

export interface Document {
  id: string;
  name: string;
  size: number;
  mimeType: string;
  status: DocumentStatus;
  chunkCount?: number;
  uploadedAt: string;
  errorMessage?: string;
}

export interface UploadDocumentRequest {
  file: File;
  metadata?: Record<string, string>;
}

export interface UploadDocumentResponse {
  documentId: string;
  status: DocumentStatus;
}

export interface RetrieveRequest {
  query: string;
  topK?: number;
  documentIds?: string[];
}

export interface RetrievedChunk {
  documentId: string;
  documentName: string;
  chunkIndex: number;
  content: string;
  score: number;
}

/** 문서 청킹 결과 (관리자 뷰) */
export interface DocumentChunk {
  id: string;
  documentId: string;
  chunkIndex: number;
  content: string;
  tokenCount: number;
  metadata?: Record<string, unknown>;
}
