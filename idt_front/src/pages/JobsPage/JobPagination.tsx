// jobs-page-revamp Design §5.1 — total 기반 'N / M 페이지' (FR-14)

interface JobPaginationProps {
  total: number;
  pageSize: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
}

const ChevronIcon = ({ direction }: { direction: 'left' | 'right' }) => (
  <svg
    className="h-4 w-4"
    fill="none"
    viewBox="0 0 24 24"
    strokeWidth={2}
    stroke="currentColor"
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d={direction === 'left' ? 'M15.75 19.5L8.25 12l7.5-7.5' : 'M8.25 4.5l7.5 7.5-7.5 7.5'}
    />
  </svg>
);

const JobPagination = ({
  total,
  pageSize,
  offset,
  onOffsetChange,
}: JobPaginationProps) => {
  // 0건일 때도 '1 / 1 페이지'로 보여 페이지 표시가 사라지지 않게 한다
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.floor(offset / pageSize) + 1;
  const isFirst = currentPage <= 1;
  const isLast = currentPage >= totalPages;

  const buttonClass =
    'flex h-8 w-8 items-center justify-center rounded-lg border border-zinc-200 text-zinc-500 transition-all hover:bg-zinc-100 disabled:opacity-40 disabled:hover:bg-transparent';

  return (
    <div className="flex items-center justify-center gap-3 py-4">
      <button
        type="button"
        aria-label="이전 페이지"
        disabled={isFirst}
        onClick={() => onOffsetChange(Math.max(0, offset - pageSize))}
        className={buttonClass}
      >
        <ChevronIcon direction="left" />
      </button>
      <span className="text-[13px] text-zinc-500">
        {currentPage} / {totalPages} 페이지
      </span>
      <button
        type="button"
        aria-label="다음 페이지"
        disabled={isLast}
        onClick={() => onOffsetChange(offset + pageSize)}
        className={buttonClass}
      >
        <ChevronIcon direction="right" />
      </button>
    </div>
  );
};

export default JobPagination;
