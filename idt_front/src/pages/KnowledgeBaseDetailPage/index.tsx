import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  useDeleteKbDocument,
  useKnowledgeBase,
  useKbDocuments,
} from '@/hooks/useKnowledgeBases';
import { ApiError } from '@/services/api/ApiError';
import { SCOPE_LABELS } from '@/types/collection';
import type { KbDocumentInfo } from '@/types/knowledgeBase';
import DeleteKbDocumentDialog from '@/components/knowledge-base/DeleteKbDocumentDialog';
import KbChunkingSettingsCard from '@/components/knowledge-base/KbChunkingSettingsCard';
import KbDocumentContentPanel from '@/components/knowledge-base/KbDocumentContentPanel';
import KbDocumentTable from '@/components/knowledge-base/KbDocumentTable';
import KbSearchSection from '@/components/knowledge-base/KbSearchSection';
import KbStatusCards from '@/components/knowledge-base/KbStatusCards';
import KbUploadDocumentModal from '@/components/knowledge-base/KbUploadDocumentModal';

// 403·404 서버 메시지는 영문이라 화면 문구로 바꾼다. 409·503은 서버 한국어 메시지를 쓴다.
const DOCUMENT_DELETE_ERROR_MAP: Record<number, string> = {
  403: '이 문서를 삭제할 권한이 없습니다',
  404: '이미 삭제되었거나 찾을 수 없는 문서입니다',
};

const getDeleteError = (error: Error | null): string | null => {
  if (!error) return null;
  if (error instanceof ApiError && DOCUMENT_DELETE_ERROR_MAP[error.status]) {
    return DOCUMENT_DELETE_ERROR_MAP[error.status];
  }
  return error.message || '문서를 삭제하지 못했습니다';
};

const KnowledgeBaseDetailPage = () => {
  const { kbId } = useParams<{ kbId: string }>();
  const navigate = useNavigate();
  const [uploadOpen, setUploadOpen] = useState(false);
  // kb-content-browser: 문서 행 클릭 드릴다운 (재클릭 시 닫기)
  const [selectedDoc, setSelectedDoc] = useState<KbDocumentInfo | null>(null);
  // kb-retrieval-test D10: 검색 스코프 — 드릴다운 선택과 독립
  const [searchScopeDoc, setSearchScopeDoc] = useState<{
    document_id: string;
    filename: string;
  } | null>(null);

  // kb-document-management FR-11·12: 삭제 대상과 성공 후 상태 해제
  const [deleteTarget, setDeleteTarget] = useState<KbDocumentInfo | null>(
    null,
  );

  const kbQuery = useKnowledgeBase(kbId);
  const docsQuery = useKbDocuments(kbId);
  const deleteMutation = useDeleteKbDocument(kbId ?? '');

  const openDeleteDialog = (doc: KbDocumentInfo) => {
    deleteMutation.reset();
    setDeleteTarget(doc);
  };

  const closeDeleteDialog = () => {
    if (deleteMutation.isPending) return;
    setDeleteTarget(null);
  };

  const confirmDelete = () => {
    if (!deleteTarget || deleteMutation.isPending) return;
    const deletedId = deleteTarget.document_id;
    deleteMutation.mutate(deletedId, {
      onSuccess: () => {
        setSelectedDoc((prev) =>
          prev?.document_id === deletedId ? null : prev,
        );
        setSearchScopeDoc((prev) =>
          prev?.document_id === deletedId ? null : prev,
        );
        setDeleteTarget(null);
      },
    });
  };

  if (!kbId) {
    navigate('/knowledge-bases');
    return null;
  }

  const kb = kbQuery.data;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <Link
          to="/knowledge-bases"
          className="text-[13px] text-zinc-400 hover:text-zinc-600"
        >
          ← 지식베이스 목록
        </Link>

        {kbQuery.isLoading ? (
          <p className="mt-6 text-[14px] text-zinc-400">불러오는 중...</p>
        ) : kbQuery.isError || !kb ? (
          <p className="mt-6 text-[14px] text-red-500">
            지식베이스를 불러오지 못했습니다 (권한이 없거나 삭제되었을 수
            있습니다)
          </p>
        ) : (
          <>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <h1 className="text-3xl font-bold tracking-tight text-zinc-900">
                {kb.name}
              </h1>
              <span
                className={`inline-flex items-center rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${SCOPE_LABELS[kb.scope].bg} ${SCOPE_LABELS[kb.scope].color}`}
              >
                {SCOPE_LABELS[kb.scope].label}
              </span>
            </div>
            {kb.description && (
              <p className="mt-2 text-[14px] text-zinc-500">
                {kb.description}
              </p>
            )}
            <p className="mt-1 font-mono text-[12px] text-zinc-400">
              컬렉션: {kb.collection_name}
              {kb.use_clause_chunking && ' · 조항 단위 청킹'}
              {kb.use_custom_chunking && ' · 커스텀 청킹'}
            </p>

            <KbChunkingSettingsCard kb={kb} />

            <KbStatusCards
              documents={docsQuery.data?.documents ?? []}
              total={docsQuery.data?.total ?? 0}
            />

            <div className="mt-8 flex items-center justify-between">
              <h2 className="text-[17px] font-semibold text-zinc-900">
                문서{' '}
                <span className="text-zinc-400">
                  {docsQuery.data?.total ?? 0}
                </span>
              </h2>
              <button
                onClick={() => setUploadOpen(true)}
                className="rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
              >
                + 문서 업로드
              </button>
            </div>

            <div className="mt-4">
              <KbDocumentTable
                documents={docsQuery.data?.documents ?? []}
                isLoading={docsQuery.isLoading}
                isError={docsQuery.isError}
                onRetry={() => docsQuery.refetch()}
                onRowClick={(doc) =>
                  setSelectedDoc((prev) =>
                    prev?.document_id === doc.document_id ? null : doc,
                  )
                }
                selectedId={selectedDoc?.document_id ?? null}
                onSearchInDocument={(doc) =>
                  setSearchScopeDoc({
                    document_id: doc.document_id,
                    filename: doc.filename,
                  })
                }
                onDeleteDocument={openDeleteDialog}
              />
            </div>

            {selectedDoc && (
              <KbDocumentContentPanel
                kbId={kbId}
                document={selectedDoc}
                onClose={() => setSelectedDoc(null)}
              />
            )}

            <KbSearchSection
              kbId={kbId}
              scopeDoc={searchScopeDoc}
              onClearScope={() => setSearchScopeDoc(null)}
            />

            <KbUploadDocumentModal
              isOpen={uploadOpen}
              onClose={() => setUploadOpen(false)}
              kbId={kbId}
              kbName={kb.name}
            />

            <DeleteKbDocumentDialog
              isOpen={deleteTarget !== null}
              filename={deleteTarget?.filename ?? ''}
              onClose={closeDeleteDialog}
              onConfirm={confirmDelete}
              isPending={deleteMutation.isPending}
              error={getDeleteError(deleteMutation.error)}
            />
          </>
        )}
      </div>
    </div>
  );
};

export default KnowledgeBaseDetailPage;
