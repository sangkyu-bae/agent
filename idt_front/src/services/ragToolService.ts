import apiClient from '@/services/api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type { CollectionInfo, MetadataKeyInfo } from '@/types/ragToolConfig';

interface CollectionsResponse {
  collections: CollectionInfo[];
}

interface MetadataKeysResponse {
  keys: MetadataKeyInfo[];
}

const ragToolService = {
  getCollections: async (): Promise<CollectionInfo[]> => {
    const { data } = await apiClient.get<CollectionsResponse>(
      API_ENDPOINTS.RAG_TOOL_COLLECTIONS,
    );
    return data.collections;
  },

  getMetadataKeys: async (collectionName?: string): Promise<MetadataKeyInfo[]> => {
    const { data } = await apiClient.get<MetadataKeysResponse>(
      API_ENDPOINTS.RAG_TOOL_METADATA_KEYS,
      { params: collectionName ? { collection_name: collectionName } : undefined },
    );
    return data.keys;
  },
};

export default ragToolService;
