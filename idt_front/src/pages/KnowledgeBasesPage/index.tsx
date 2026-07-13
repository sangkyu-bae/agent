import { useState } from 'react';
import {
  useKnowledgeBases,
  useCreateKnowledgeBase,
  useDeleteKnowledgeBase,
} from '@/hooks/useKnowledgeBases';
import { useAuthStore } from '@/store/authStore';
import { ApiError } from '@/services/api/ApiError';
import KnowledgeBaseTable from '@/components/knowledge-base/KnowledgeBaseTable';
import CreateKnowledgeBaseModal from '@/components/knowledge-base/CreateKnowledgeBaseModal';
import DeleteKnowledgeBaseDialog from '@/components/knowledge-base/DeleteKnowledgeBaseDialog';

const KB_ERROR_MAP: Record<number, string> = {
  403: '권한이 없습니다',
  404: '지식베이스를 찾을 수 없습니다',
  409: '같은 이름의 지식베이스가 이미 있습니다',
  422: '입력값을 확인해주세요 (부서/컬렉션)',
};

const getMutationError = (error: Error | null): string | null => {
  if (!error) return null;
  if (error instanceof ApiError && KB_ERROR_MAP[error.status]) {
    return KB_ERROR_MAP[error.status];
  }
  return error.message || '요청 처리 중 오류가 발생했습니다';
};

const KnowledgeBasesPage = () => {
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const user = useAuthStore((s) => s.user);
  const kbList = useKnowledgeBases();
  const createMutation = useCreateKnowledgeBase();
  const deleteMutation = useDeleteKnowledgeBase();

  const knowledgeBases = kbList.data ?? [];
  const deleteTargetKb = knowledgeBases.find(
    (kb) => kb.kb_id === deleteTarget,
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900">
          지식베이스
        </h1>
        <p className="mt-2 text-[14px] text-zinc-500">
          문서를 지식베이스 단위로 모아두면 에이전트가 그 범위만 검색합니다.
        </p>

        <div className="mt-6">
          <KnowledgeBaseTable
            knowledgeBases={knowledgeBases}
            isLoading={kbList.isLoading}
            isError={kbList.isError}
            currentUserId={user?.id ?? null}
            currentUserRole={user?.role ?? null}
            onRefresh={() => kbList.refetch()}
            onCreate={() => {
              createMutation.reset();
              setCreateOpen(true);
            }}
            onDelete={(kbId) => {
              deleteMutation.reset();
              setDeleteTarget(kbId);
            }}
          />
        </div>

        <CreateKnowledgeBaseModal
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

        <DeleteKnowledgeBaseDialog
          isOpen={deleteTarget !== null}
          kbName={deleteTargetKb?.name ?? ''}
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
      </div>
    </div>
  );
};

export default KnowledgeBasesPage;
