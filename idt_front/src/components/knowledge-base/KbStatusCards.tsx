import type { KbDocumentInfo } from '@/types/knowledgeBase';

interface KbStatusCardsProps {
  documents: KbDocumentInfo[];
  total: number;
}

/** 문서 업로드/처리 상태 요약 (kb-retrieval-test FR-07).
 *  컬렉션 문서 페이지와 동일한 chunk_count 간이 판정 —
 *  chunk_count>0 준비완료, 0 처리중, 오류는 실측 없이 0 고정. */
const KbStatusCards = ({ documents, total }: KbStatusCardsProps) => {
  const readyCount = documents.filter((d) => d.chunk_count > 0).length;
  const processingCount = documents.filter((d) => d.chunk_count === 0).length;

  return (
    <div className="mt-6 grid grid-cols-4 gap-4">
      <div className="rounded-2xl border border-zinc-200 bg-white px-5 py-4">
        <p className="text-[12px] text-zinc-400">전체 문서</p>
        <p
          data-testid="kb-total-count"
          className="mt-1 text-2xl font-bold text-zinc-900"
        >
          {total}
        </p>
      </div>
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 px-5 py-4">
        <div className="flex items-center gap-1.5">
          <svg className="h-3.5 w-3.5 text-emerald-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
          </svg>
          <p className="text-[12px] text-emerald-600">준비 완료</p>
        </div>
        <p
          data-testid="kb-ready-count"
          className="mt-1 text-2xl font-bold text-emerald-600"
        >
          {readyCount}
        </p>
      </div>
      <div className="rounded-2xl border border-amber-200 bg-amber-50/50 px-5 py-4">
        <div className="flex items-center gap-1.5">
          <svg className="h-3.5 w-3.5 animate-spin text-amber-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182M2.985 19.644l3.182-3.182" />
          </svg>
          <p className="text-[12px] text-amber-600">처리 중</p>
        </div>
        <p
          data-testid="kb-processing-count"
          className="mt-1 text-2xl font-bold text-amber-600"
        >
          {processingCount}
        </p>
      </div>
      <div className="rounded-2xl border border-red-200 bg-red-50/50 px-5 py-4">
        <div className="flex items-center gap-1.5">
          <svg className="h-3.5 w-3.5 text-red-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
          </svg>
          <p className="text-[12px] text-red-500">오류</p>
        </div>
        <p
          data-testid="kb-error-count"
          className="mt-1 text-2xl font-bold text-red-500"
        >
          0
        </p>
      </div>
    </div>
  );
};

export default KbStatusCards;
