import type { KbDocumentInfo } from '@/types/knowledgeBase';

interface KbDocumentTableProps {
  documents: KbDocumentInfo[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  /** 행 클릭 → 저장 내용 드릴다운 (kb-content-browser) */
  onRowClick?: (doc: KbDocumentInfo) => void;
  selectedId?: string | null;
  /** 문서 단위 검색 스코프 지정 (kb-retrieval-test D10) — 드릴다운과 독립 */
  onSearchInDocument?: (doc: KbDocumentInfo) => void;
}

const STRATEGY_LABELS: Record<string, string> = {
  parent_child: '기본',
  clause_aware: '조항 단위',
};

const KbDocumentTable = ({
  documents,
  isLoading,
  isError,
  onRetry,
  onRowClick,
  selectedId,
  onSearchInDocument,
}: KbDocumentTableProps) => {
  if (isLoading) {
    return (
      <p className="py-10 text-center text-[14px] text-zinc-400">
        문서 목록을 불러오는 중...
      </p>
    );
  }

  if (isError) {
    return (
      <div className="py-10 text-center">
        <p className="text-[14px] text-red-500">
          문서 목록을 불러오지 못했습니다
        </p>
        <button
          onClick={onRetry}
          className="mt-3 rounded-xl border border-zinc-200 px-4 py-2 text-[13px] font-medium text-zinc-600 hover:bg-zinc-50"
        >
          다시 시도
        </button>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <p className="py-10 text-center text-[14px] text-zinc-400">
        아직 업로드된 문서가 없습니다. 문서를 업로드해보세요.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-zinc-200">
      <table className="w-full text-left text-[14px]">
        <thead className="bg-zinc-50 text-[12px] text-zinc-500">
          <tr>
            <th className="px-4 py-3 font-medium">파일명</th>
            <th className="px-4 py-3 font-medium">청크 수</th>
            <th className="px-4 py-3 font-medium">청킹 방식</th>
            <th className="px-4 py-3 font-medium">업로드일</th>
            {onSearchInDocument && (
              <th className="px-4 py-3 font-medium">검색</th>
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100">
          {documents.map((doc) => (
            <tr
              key={doc.document_id}
              onClick={() => onRowClick?.(doc)}
              aria-selected={selectedId === doc.document_id}
              className={`${onRowClick ? 'cursor-pointer' : ''} ${
                selectedId === doc.document_id
                  ? 'bg-violet-50/70'
                  : 'hover:bg-zinc-50/60'
              }`}
            >
              <td className="px-4 py-3 font-medium text-zinc-800">
                {doc.filename}
              </td>
              <td className="px-4 py-3 text-zinc-500">{doc.chunk_count}</td>
              <td className="px-4 py-3 text-zinc-500">
                {STRATEGY_LABELS[doc.chunking_strategy] ??
                  doc.chunking_strategy}
              </td>
              <td className="px-4 py-3 text-zinc-500">
                {doc.created_at ? doc.created_at.slice(0, 10) : '—'}
              </td>
              {onSearchInDocument && (
                <td className="px-4 py-3">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      onSearchInDocument(doc);
                    }}
                    className="rounded-lg border border-zinc-200 px-2.5 py-1 text-[12px] text-zinc-500 transition-colors hover:border-violet-300 hover:text-violet-600"
                  >
                    이 문서에서 검색
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default KbDocumentTable;
