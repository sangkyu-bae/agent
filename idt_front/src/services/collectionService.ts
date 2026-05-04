import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  CollectionListResponse,
  CollectionDetail,
  CreateCollectionRequest,
  RenameCollectionRequest,
  CollectionMessageResponse,
  RenameCollectionResponse,
  ActivityLogListResponse,
  ActivityLogFilters,
  UpdateScopeRequest,
  UpdateScopeResponse,
  CollectionDocumentsResponse,
  CollectionDocumentsParams,
  DocumentChunksResponse,
  DocumentChunksParams,
  CollectionSearchRequest,
  CollectionSearchResponse,
  SearchHistoryResponse,
  DeleteDocumentResponse,
  BatchDeleteDocumentsRequest,
  BatchDeleteDocumentsResponse,
} from '@/types/collection';

export const collectionService = {
  getCollections: async (): Promise<CollectionListResponse> => {
    const res = await authApiClient.get<CollectionListResponse>(
      API_ENDPOINTS.COLLECTIONS,
    );
    return res.data;
  },

  getCollection: async (name: string): Promise<CollectionDetail> => {
    const res = await authApiClient.get<CollectionDetail>(
      API_ENDPOINTS.COLLECTION_DETAIL(name),
    );
    return res.data;
  },

  createCollection: async (
    data: CreateCollectionRequest,
  ): Promise<CollectionMessageResponse> => {
    const res = await authApiClient.post<CollectionMessageResponse>(
      API_ENDPOINTS.COLLECTIONS,
      data,
    );
    return res.data;
  },

  renameCollection: async (
    name: string,
    data: RenameCollectionRequest,
  ): Promise<RenameCollectionResponse> => {
    const res = await authApiClient.patch<RenameCollectionResponse>(
      API_ENDPOINTS.COLLECTION_RENAME(name),
      data,
    );
    return res.data;
  },

  deleteCollection: async (
    name: string,
  ): Promise<CollectionMessageResponse> => {
    const res = await authApiClient.delete<CollectionMessageResponse>(
      API_ENDPOINTS.COLLECTION_DELETE(name),
    );
    return res.data;
  },

  updateScope: async (
    name: string,
    data: UpdateScopeRequest,
  ): Promise<UpdateScopeResponse> => {
    const res = await authApiClient.patch<UpdateScopeResponse>(
      API_ENDPOINTS.COLLECTION_PERMISSION(name),
      data,
    );
    return res.data;
  },

  getActivityLogs: async (
    params: ActivityLogFilters,
  ): Promise<ActivityLogListResponse> => {
    const res = await authApiClient.get<ActivityLogListResponse>(
      API_ENDPOINTS.COLLECTION_ACTIVITY_LOG,
      { params },
    );
    return res.data;
  },

  getCollectionActivityLogs: async (
    name: string,
    params?: { limit?: number; offset?: number },
  ): Promise<ActivityLogListResponse> => {
    const res = await authApiClient.get<ActivityLogListResponse>(
      API_ENDPOINTS.COLLECTION_ACTIVITY_LOG_BY_NAME(name),
      { params },
    );
    return res.data;
  },

  getDocuments: async (
    collectionName: string,
    params?: CollectionDocumentsParams,
  ): Promise<CollectionDocumentsResponse> => {
    const res = await authApiClient.get<CollectionDocumentsResponse>(
      API_ENDPOINTS.COLLECTION_DOCUMENTS(collectionName),
      { params },
    );
    return res.data;
  },

  getDocumentChunks: async (
    collectionName: string,
    documentId: string,
    params?: DocumentChunksParams,
  ): Promise<DocumentChunksResponse> => {
    const res = await authApiClient.get<DocumentChunksResponse>(
      API_ENDPOINTS.COLLECTION_DOCUMENT_CHUNKS(collectionName, documentId),
      { params },
    );
    return res.data;
  },

  searchCollection: async (
    collectionName: string,
    data: CollectionSearchRequest,
  ): Promise<CollectionSearchResponse> => {
    const res = await authApiClient.post<CollectionSearchResponse>(
      API_ENDPOINTS.COLLECTION_SEARCH(collectionName),
      data,
    );
    return res.data;
  },

  getSearchHistory: async (
    collectionName: string,
    params?: { limit?: number; offset?: number },
  ): Promise<SearchHistoryResponse> => {
    const res = await authApiClient.get<SearchHistoryResponse>(
      API_ENDPOINTS.COLLECTION_SEARCH_HISTORY(collectionName),
      { params },
    );
    return res.data;
  },

  deleteDocument: async (
    collectionName: string,
    documentId: string,
  ): Promise<DeleteDocumentResponse> => {
    const res = await authApiClient.delete<DeleteDocumentResponse>(
      API_ENDPOINTS.COLLECTION_DOCUMENT_DELETE(collectionName, documentId),
    );
    return res.data;
  },

  deleteDocuments: async (
    collectionName: string,
    data: BatchDeleteDocumentsRequest,
  ): Promise<BatchDeleteDocumentsResponse> => {
    const res = await authApiClient.delete<BatchDeleteDocumentsResponse>(
      API_ENDPOINTS.COLLECTION_DOCUMENTS_BATCH_DELETE(collectionName),
      { data },
    );
    return res.data;
  },
};
