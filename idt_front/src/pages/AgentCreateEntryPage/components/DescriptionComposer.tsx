// Design Ref: agent-create-entry §5.4 — 설명 입력창 + 전송(▷).
// 키보드 규약(Enter 전송 / Shift+Enter 줄바꿈)은 FixAgentPanel과 동일하게 맞춘다.
export const MAX_USER_REQUEST_CHARS = 1000;

interface DescriptionComposerProps {
  value: string;
  onChange: (next: string) => void;
  onSubmit: () => void;
  isPending: boolean;
}

const DescriptionComposer = ({
  value,
  onChange,
  onSubmit,
  isPending,
}: DescriptionComposerProps) => {
  const canSubmit = value.trim().length > 0 && !isPending;

  return (
    <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm transition-all focus-within:border-violet-400">
      <textarea
        value={value}
        // 서버 max_length=1000과 동일 — 초과분은 전송 전에 잘라 422를 만들지 않는다
        onChange={(e) => onChange(e.target.value.slice(0, MAX_USER_REQUEST_CHARS))}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (canSubmit) onSubmit();
          }
        }}
        disabled={isPending}
        rows={3}
        placeholder="구축하려는 에이전트에 대해 설명해 주세요"
        aria-label="에이전트 설명"
        className="block w-full resize-none bg-transparent px-5 py-4 text-[14.5px] leading-relaxed text-zinc-900 placeholder-zinc-400 outline-none disabled:cursor-not-allowed disabled:bg-zinc-50"
      />

      <div className="flex items-center justify-between border-t border-zinc-100 px-5 py-2.5">
        {isPending ? (
          <div className="flex items-center gap-1.5" aria-label="초안 생성 중">
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.3s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.15s]" />
            <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-violet-400" />
          </div>
        ) : (
          <p className="text-[11.5px] text-zinc-400">
            Enter로 전송, Shift + Enter로 줄바꿈
          </p>
        )}

        <button
          type="button"
          onClick={onSubmit}
          disabled={!canSubmit}
          aria-label="에이전트 설명 전송"
          className="flex h-8 w-8 items-center justify-center rounded-full border border-zinc-200 text-zinc-400 transition-all hover:border-violet-400 hover:text-violet-600 active:scale-95 disabled:cursor-not-allowed disabled:border-zinc-200 disabled:text-zinc-300 disabled:hover:border-zinc-200"
        >
          <svg
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.8}
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M6 12 3.269 3.125A59.769 59.769 0 0 1 21.485 12 59.768 59.768 0 0 1 3.27 20.875L5.999 12Zm0 0h7.5"
            />
          </svg>
        </button>
      </div>
    </div>
  );
};

export default DescriptionComposer;
