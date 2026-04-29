import { useState } from 'react';
import {
  useCollectionList,
  useCreateCollection,
  useRenameCollection,
  useDeleteCollection,
  useUpdateScope,
  useActivityLogs,
} from '@/hooks/useCollections';
import { useAuthStore } from '@/store/authStore';
import { ApiError } from '@/services/api/ApiError';
import type { ActivityLogFilters } from '@/types/collection';
import CollectionTable from '@/components/collection/CollectionTable';
import CreateCollectionModal from '@/components/collection/CreateCollectionModal';
import RenameCollectionModal from '@/components/collection/RenameCollectionModal';
import DeleteCollectionDialog from '@/components/collection/DeleteCollectionDialog';
import UpdateScopeModal from '@/components/collection/UpdateScopeModal';
import ActivityLogFiltersPanel from '@/components/collection/ActivityLogFilters';
import ActivityLogTable from '@/components/collection/ActivityLogTable';

type Tab = 'collections' | 'activity';

const CollectionPage = () => {
  const [activeTab, setActiveTab] = useState<Tab>('collections');

  // Modals
  const [createOpen, setCreateOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [scopeTarget, setScopeTarget] = useState<string | null>(null);

  // Auth
  const user = useAuthStore((s) => s.user);

  // Activity log filters
  const [logFilters, setLogFilters] = useState<ActivityLogFilters>({
    limit: 50,
    offset: 0,
  });

  // Queries
  const collectionList = useCollectionList();
  const activityLogs = useActivityLogs(logFilters, {
    enabled: activeTab === 'activity',
  });

  // Mutations
  const createMutation = useCreateCollection();
  const renameMutation = useRenameCollection();
  const deleteMutation = useDeleteCollection();
  const scopeMutation = useUpdateScope();

  const COLLECTION_ERROR_MAP: Record<number, string> = {
    403: '권한이 없습니다',
    404: '컬렉션을 찾을 수 없습니다',
    409: '이미 존재하는 컬렉션입니다',
    422: '유효하지 않은 부서입니다',
  };

  const getMutationError = (error: Error | null): string | null => {
    if (!error) return null;
    if (error instanceof ApiError && COLLECTION_ERROR_MAP[error.status]) {
      return COLLECTION_ERROR_MAP[error.status];
    }
    return error.message || '요청 처리 중 오류가 발생했습니다';
  };

  const getScopeError = (error: Error | null): string | null => {
    if (!error) return null;
    if (error instanceof ApiError) {
      if (error.status === 403) return '권한 변경 권한이 없습니다';
      if (COLLECTION_ERROR_MAP[error.status]) return COLLECTION_ERROR_MAP[error.status];
    }
    return error.message || '요청 처리 중 오류가 발생했습니다';
  };

  const collectionNames =
    collectionList.data?.collections.map((c) => c.name) ?? [];

  return (
    <div className="h-full overflow-y-auto">
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <h1 className="text-3xl font-bold tracking-tight text-zinc-900">
        컬렉션 관리
      </h1>

      {/* Tabs */}
      <div className="mt-6 flex gap-6 border-b border-zinc-200">
        <button
          onClick={() => setActiveTab('collections')}
          className={`pb-3 text-[15px] font-semibold transition-all ${
            activeTab === 'collections'
              ? 'border-b-2 border-violet-500 text-violet-600'
              : 'text-zinc-400 hover:text-zinc-600'
          }`}
        >
          컬렉션 관리
        </button>
        <button
          onClick={() => setActiveTab('activity')}
          className={`pb-3 text-[15px] font-semibold transition-all ${
            activeTab === 'activity'
              ? 'border-b-2 border-violet-500 text-violet-600'
              : 'text-zinc-400 hover:text-zinc-600'
          }`}
        >
          사용 이력
        </button>
      </div>

      {/* Tab Content */}
      <div className="mt-6">
        {activeTab === 'collections' && (
          <CollectionTable
            collections={collectionList.data?.collections ?? []}
            isLoading={collectionList.isLoading}
            isError={collectionList.isError}
            currentUserId={user?.id ?? null}
            currentUserRole={user?.role ?? null}
            onRefresh={() => collectionList.refetch()}
            onCreate={() => {
              createMutation.reset();
              setCreateOpen(true);
            }}
            onRename={(name) => {
              renameMutation.reset();
              setRenameTarget(name);
            }}
            onDelete={(name) => {
              deleteMutation.reset();
              setDeleteTarget(name);
            }}
            onUpdateScope={(name) => {
              scopeMutation.reset();
              setScopeTarget(name);
            }}
          />
        )}

        {activeTab === 'activity' && (
          <>
            <ActivityLogFiltersPanel
              filters={logFilters}
              collections={collectionNames}
              onChange={setLogFilters}
            />
            <ActivityLogTable
              logs={activityLogs.data?.logs ?? []}
              total={activityLogs.data?.total ?? 0}
              limit={logFilters.limit ?? 50}
              offset={logFilters.offset ?? 0}
              isLoading={activityLogs.isLoading}
              isError={activityLogs.isError}
              onPageChange={(newOffset) =>
                setLogFilters((prev) => ({ ...prev, offset: newOffset }))
              }
              onRetry={() => activityLogs.refetch()}
            />
          </>
        )}
      </div>

      {/* Modals */}
      <CreateCollectionModal
        isOpen={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={(data) => {
          createMutation.mutate(data, {
            onSuccess: () => setCreateOpen(false),
          });
        }}
        isPending={createMutation.isPending}
        error={getMutationError(createMutation.error)}
      />

      <RenameCollectionModal
        isOpen={renameTarget !== null}
        currentName={renameTarget ?? ''}
        onClose={() => setRenameTarget(null)}
        onSubmit={(newName) => {
          if (!renameTarget) return;
          renameMutation.mutate(
            { name: renameTarget, newName },
            { onSuccess: () => setRenameTarget(null) },
          );
        }}
        isPending={renameMutation.isPending}
        error={getMutationError(renameMutation.error)}
      />

      <DeleteCollectionDialog
        isOpen={deleteTarget !== null}
        collectionName={deleteTarget ?? ''}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) return;
          deleteMutation.mutate(deleteTarget, {
            onSuccess: () => setDeleteTarget(null),
          });
        }}
        isPending={deleteMutation.isPending}
        error={getMutationError(deleteMutation.error)}
      />

      <UpdateScopeModal
        isOpen={scopeTarget !== null}
        collectionName={scopeTarget ?? ''}
        currentScope={
          collectionList.data?.collections.find((c) => c.name === scopeTarget)
            ?.scope ?? 'PERSONAL'
        }
        onClose={() => setScopeTarget(null)}
        onSubmit={(data) => {
          if (!scopeTarget) return;
          scopeMutation.mutate(
            { name: scopeTarget, data },
            { onSuccess: () => setScopeTarget(null) },
          );
        }}
        isPending={scopeMutation.isPending}
        error={getScopeError(scopeMutation.error)}
      />
    </div>
    </div>
  );
};

export default CollectionPage;
