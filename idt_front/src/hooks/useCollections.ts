import { useQuery, useMutation } from '@tanstack/react-query';
import { collectionService } from '@/services/collectionService';
import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import type {
  CreateCollectionRequest,
  UpdateScopeRequest,
  ActivityLogFilters,
  CollectionDocumentsParams,
  DocumentChunksParams,
  CollectionSearchRequest,
} from '@/types/collection';

export const useCollectionList = () =>
  useQuery({
    queryKey: queryKeys.collections.list(),
    queryFn: collectionService.getCollections,
  });

export const useCollectionDetail = (name: string) =>
  useQuery({
    queryKey: queryKeys.collections.detail(name),
    queryFn: () => collectionService.getCollection(name),
    enabled: !!name,
  });

export const useCreateCollection = () =>
  useMutation({
    mutationFn: (data: CreateCollectionRequest) =>
      collectionService.createCollection(data),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.collections.all,
      }),
  });

export const useRenameCollection = () =>
  useMutation({
    mutationFn: ({ name, newName }: { name: string; newName: string }) =>
      collectionService.renameCollection(name, { new_name: newName }),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.collections.all,
      }),
  });

export const useDeleteCollection = () =>
  useMutation({
    mutationFn: (name: string) => collectionService.deleteCollection(name),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.collections.all,
      }),
  });

export const useUpdateScope = () =>
  useMutation({
    mutationFn: ({ name, data }: { name: string; data: UpdateScopeRequest }) =>
      collectionService.updateScope(name, data),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.collections.all,
      }),
  });

export const useActivityLogs = (
  filters: ActivityLogFilters,
  options?: { enabled?: boolean },
) =>
  useQuery({
    queryKey: queryKeys.collections.activityLog(filters),
    queryFn: () => collectionService.getActivityLogs(filters),
    enabled: options?.enabled ?? true,
  });

export const useCollectionActivityLogs = (name: string) =>
  useQuery({
    queryKey: queryKeys.collections.collectionActivityLog(name),
    queryFn: () => collectionService.getCollectionActivityLogs(name),
    enabled: !!name,
  });

export const useCollectionDocuments = (
  collectionName: string,
  params?: CollectionDocumentsParams,
) =>
  useQuery({
    queryKey: queryKeys.collections.documents(collectionName, params),
    queryFn: () => collectionService.getDocuments(collectionName, params),
    enabled: !!collectionName,
  });

export const useDocumentChunks = (
  collectionName: string,
  documentId: string | null,
  params?: DocumentChunksParams,
) =>
  useQuery({
    queryKey: queryKeys.collections.chunks(collectionName, documentId ?? '', params),
    queryFn: () => collectionService.getDocumentChunks(collectionName, documentId!, params),
    enabled: !!collectionName && !!documentId,
  });

export const useCollectionSearch = () =>
  useMutation({
    mutationFn: ({ collectionName, data }: {
      collectionName: string;
      data: CollectionSearchRequest;
    }) => collectionService.searchCollection(collectionName, data),
    onSuccess: (_, { collectionName }) =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.collections.searchHistory(collectionName),
      }),
  });

export const useSearchHistory = (
  collectionName: string,
  params?: { limit?: number; offset?: number },
) =>
  useQuery({
    queryKey: queryKeys.collections.searchHistory(collectionName, params),
    queryFn: () => collectionService.getSearchHistory(collectionName, params),
    enabled: !!collectionName,
  });

export const useDeleteDocument = () =>
  useMutation({
    mutationFn: ({ collectionName, documentId }: {
      collectionName: string;
      documentId: string;
    }) => collectionService.deleteDocument(collectionName, documentId),
    onSuccess: (_, { collectionName }) =>
      queryClient.invalidateQueries({
        queryKey: [...queryKeys.collections.all, 'documents', collectionName],
      }),
  });

export const useDeleteDocuments = () =>
  useMutation({
    mutationFn: ({ collectionName, documentIds }: {
      collectionName: string;
      documentIds: string[];
    }) => collectionService.deleteDocuments(collectionName, { document_ids: documentIds }),
    onSuccess: (_, { collectionName }) =>
      queryClient.invalidateQueries({
        queryKey: [...queryKeys.collections.all, 'documents', collectionName],
      }),
  });
