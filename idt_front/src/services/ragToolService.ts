import authApiClient from '@/services/api/authClient';
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
    const { data } = await authApiClient.get<CollectionsResponse>(
      API_ENDPOINTS.RAG_TOOL_COLLECTIONS,
    );
    return data.collections;
  },

  getMetadataKeys: async (collectionName?: string): Promise<MetadataKeyInfo[]> => {
    const { data } = await authApiClient.get<MetadataKeysResponse>(
      API_ENDPOINTS.RAG_TOOL_METADATA_KEYS,
      { params: collectionName ? { collection_name: collectionName } : undefined },
    );
    return data.keys;
  },
};

export default ragToolService;
