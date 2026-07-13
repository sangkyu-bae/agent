import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  useKnowledgeBase,
  useKbDocuments,
} from '@/hooks/useKnowledgeBases';
import { SCOPE_LABELS } from '@/types/collection';
import KbDocumentTable from '@/components/knowledge-base/KbDocumentTable';
import KbUploadDocumentModal from '@/components/knowledge-base/KbUploadDocumentModal';

const KnowledgeBaseDetailPage = () => {
  const { kbId } = useParams<{ kbId: string }>();
  const navigate = useNavigate();
  const [uploadOpen, setUploadOpen] = useState(false);

  const kbQuery = useKnowledgeBase(kbId);
  const docsQuery = useKbDocuments(kbId);

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
            </p>

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
              />
            </div>

            <KbUploadDocumentModal
              isOpen={uploadOpen}
              onClose={() => setUploadOpen(false)}
              kbId={kbId}
              kbName={kb.name}
            />
          </>
        )}
      </div>
    </div>
  );
};

export default KnowledgeBaseDetailPage;
