import type { DocumentSummary } from '@/types/collection';

interface DocumentTableProps {
  documents: DocumentSummary[];
  totalDocuments: number;
  offset: number;
  limit: number;
  isLoading: boolean;
  isError: boolean;
  selectedDocumentId: string | null;
  onSelect: (documentId: string) => void;
  onPageChange: (newOffset: number) => void;
  onRetry: () => void;
}

const SkeletonRows = () => (
  <>
    {[1, 2, 3].map((i) => (
      <tr key={i}>
        {[1, 2, 3, 4, 5].map((j) => (
          <td key={j} className="px-4 py-3">
            <div className="h-4 animate-pulse rounded bg-zinc-200" />
          </td>
        ))}
      </tr>
    ))}
  </>
);

const StatusBadge = ({ chunkCount }: { chunkCount: number }) => {
  if (chunkCount > 0) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-[11.5px] font-medium text-emerald-600">
        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
        </svg>
        준비
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-[11.5px] font-medium text-amber-600">
      <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182M2.985 19.644l3.182-3.182" />
      </svg>
      처리 중
    </span>
  );
};

const DocumentTable = ({
  documents,
  totalDocuments,
  offset,
  limit,
  isLoading,
  isError,
  selectedDocumentId,
  onSelect,
  onPageChange,
  onRetry,
}: DocumentTableProps) => {
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(totalDocuments / limit);
  const hasPrev = offset > 0;
  const hasNext = offset + limit < totalDocuments;

  if (isError) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-center">
        <p className="text-[15px] text-red-600">문서 목록을 불러올 수 없습니다</p>
        <button
          onClick={onRetry}
          className="mt-3 rounded-xl border border-red-200 bg-white px-4 py-2 text-[13.5px] font-medium text-red-600 transition-all hover:bg-red-50"
        >
          다시 시도
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white">
      <table className="w-full">
        <thead>
          <tr className="border-b border-zinc-100 bg-zinc-50/60">
            <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
              파일명
            </th>
            <th className="px-5 py-3 text-left text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
              카테고리
            </th>
            <th className="px-5 py-3 text-center text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
              상태
            </th>
            <th className="px-5 py-3 text-right text-[12px] font-semibold uppercase tracking-wider text-zinc-400">
              청크
            </th>
            <th className="w-10" />
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100">
          {isLoading ? (
            <SkeletonRows />
          ) : documents.length === 0 ? (
            <tr>
              <td
                colSpan={5}
                className="px-5 py-12 text-center text-[15px] text-zinc-400"
              >
                이 컬렉션에 문서가 없습니다
              </td>
            </tr>
          ) : (
            documents.map((doc) => {
              const isSelected = selectedDocumentId === doc.document_id;
              return (
                <tr
                  key={doc.document_id}
                  onClick={() => onSelect(doc.document_id)}
                  className={`cursor-pointer transition-colors ${
                    isSelected ? 'bg-violet-50' : 'hover:bg-zinc-50/70'
                  }`}
                >
                  <td className="px-5 py-3.5">
                    <div className="flex items-center gap-2.5">
                      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-zinc-100">
                        <svg className="h-4 w-4 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
                        </svg>
                      </div>
                      <span className="text-[13.5px] font-medium text-zinc-800">
                        {doc.filename}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-3.5 text-[13.5px] text-zinc-500">
                    {doc.category}
                  </td>
                  <td className="px-5 py-3.5 text-center">
                    <StatusBadge chunkCount={doc.chunk_count} />
                  </td>
                  <td className="px-5 py-3.5 text-right text-[13.5px] text-zinc-600">
                    {doc.chunk_count > 0 ? `${doc.chunk_count}개` : '—'}
                  </td>
                  <td className="px-3 py-3.5">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        // TODO: delete handler
                      }}
                      className="flex h-7 w-7 items-center justify-center rounded-lg text-zinc-300 transition-colors hover:bg-red-50 hover:text-red-500"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                      </svg>
                    </button>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>

      {totalDocuments > 0 && (
        <div className="flex items-center justify-center gap-3 border-t border-zinc-100 py-3">
          <button
            onClick={() => onPageChange(offset - limit)}
            disabled={!hasPrev}
            className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-40"
          >
            &lt; 이전
          </button>
          <span className="text-[12px] text-zinc-400">
            {currentPage} / {totalPages}
          </span>
          <button
            onClick={() => onPageChange(offset + limit)}
            disabled={!hasNext}
            className="rounded-xl border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-[12px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-40"
          >
            다음 &gt;
          </button>
        </div>
      )}
    </div>
  );
};

export default DocumentTable;
