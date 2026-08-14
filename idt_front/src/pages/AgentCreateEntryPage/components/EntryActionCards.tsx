// Design Ref: agent-create-entry §5.4 — 하단 카드 2종.
// 가져오기는 Plan §2.2에서 범위 제외 — export가 없어 실사용성이 없으므로
// 자리만 잡아두고 비활성 상태로 노출한다.
interface EntryActionCardsProps {
  onManualCreate: () => void;
}

const EntryActionCards = ({ onManualCreate }: EntryActionCardsProps) => (
  <div className="grid grid-cols-2 gap-4">
    <button
      type="button"
      onClick={onManualCreate}
      className="flex flex-col items-center gap-3 rounded-2xl border border-zinc-200 bg-white px-6 py-7 shadow-sm transition-all hover:border-violet-300 hover:shadow-md active:scale-[0.98]"
    >
      <svg
        className="h-5 w-5 text-zinc-600"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={1.5}
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L10.582 16.07a4.5 4.5 0 0 1-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 0 1 1.13-1.897l8.932-8.931Zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0 1 15.75 21H5.25A2.25 2.25 0 0 1 3 18.75V8.25A2.25 2.25 0 0 1 5.25 6H10"
        />
      </svg>
      <span className="text-[13.5px] font-medium text-zinc-700">
        에이전트 직접 만들기
      </span>
    </button>

    <button
      type="button"
      disabled
      aria-disabled="true"
      className="flex cursor-not-allowed flex-col items-center gap-3 rounded-2xl border border-zinc-200 bg-zinc-50 px-6 py-7"
    >
      <svg
        className="h-5 w-5 text-zinc-300"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={1.5}
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 7.5 12 3m0 0L7.5 7.5M12 3v13.5"
        />
      </svg>
      <span className="text-[13.5px] font-medium text-zinc-400">
        에이전트 가져오기
      </span>
      <span className="text-[11px] text-zinc-400">준비 중</span>
    </button>
  </div>
);

export default EntryActionCards;
