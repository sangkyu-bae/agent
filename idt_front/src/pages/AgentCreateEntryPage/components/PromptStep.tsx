import LoadingButton from '@/components/common/LoadingButton';
import { MAX_ASSEMBLED_CHARS } from '@/types/agentPipeline';

interface PromptStepProps {
  value: string;
  /** 서버가 상한 절단을 했을 때의 사유. null 이면 절단 없음. */
  clampReason: string | null;
  /** 프롬프트 단계가 degraded(규칙기반 폴백)로 끝났는지. */
  degraded: boolean;
  /** 확정된 도구 이름 목록 — 읽기 전용 요약. */
  toolNames: string[];
  isPending: boolean;
  onChange: (next: string) => void;
  onRegenerate: () => void;
  onSubmit: () => void;
  onBack: () => void;
}

/**
 * ④ 프롬프트 검토·편집 (Design §5.4 step④ / FR-F08).
 *
 * 여기 보이는 텍스트가 **그대로 저장될 값**이다: 서버가 정지 응답에서 이미
 * `MAX_ASSEMBLED_CHARS` 로 잘라서 주기 때문에(Design D3), 화면과 저장값이
 * 어긋나지 않는다. 사용자가 편집해 상한을 넘기면 저장에서 422 가 나므로
 * 여기서 막는다.
 */
const PromptStep = ({
  value,
  clampReason,
  degraded,
  toolNames,
  isPending,
  onChange,
  onRegenerate,
  onSubmit,
  onBack,
}: PromptStepProps) => {
  const overLimit = value.length > MAX_ASSEMBLED_CHARS;
  const empty = value.trim().length === 0;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-[15px] font-semibold text-zinc-900">
          시스템 프롬프트를 확인해주세요
        </h2>
        <p className="mt-1 text-[12.5px] text-zinc-500">
          이대로 저장돼요. 마음에 안 들면 직접 고치거나 다시 생성할 수 있습니다.
        </p>
      </div>

      {degraded && (
        <div
          role="status"
          className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-800"
        >
          자동 생성이 원활하지 않아 규칙기반 문안으로 만들었습니다. 내용을 한 번
          확인해주세요.
        </div>
      )}

      {clampReason && (
        <div
          role="status"
          className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[12.5px] text-amber-800"
        >
          프롬프트가 길어 일부가 잘렸습니다 — {clampReason}
        </div>
      )}

      {toolNames.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
            사용 도구
          </span>
          {toolNames.map((name) => (
            <span
              key={name}
              className="rounded-full bg-zinc-100 px-2.5 py-1 text-[12px] text-zinc-600"
            >
              {name}
            </span>
          ))}
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-zinc-300 bg-white shadow-sm transition-all focus-within:border-violet-400">
        {/*
          prompt-depth FR-25 — 7섹션 마크다운은 3000자를 넘길 수 있다. rows 만으로는
          한 화면에 몇 문단밖에 안 들어와 검토가 사실상 불가능하므로, 높이를 늘리고
          뷰포트 기준 상한을 둔 뒤 내부 스크롤로 처리한다.
        */}
        <textarea
          aria-label="시스템 프롬프트"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={isPending}
          rows={22}
          className="block max-h-[60vh] w-full resize-y overflow-y-auto bg-transparent px-4 py-3 text-[13.5px] leading-relaxed text-zinc-900 outline-none disabled:opacity-60"
        />
      </div>

      <div className="flex items-center justify-between">
        <span
          className={
            overLimit
              ? 'text-[12px] font-medium text-red-500'
              : 'text-[12px] text-zinc-400'
          }
        >
          {value.length} / {MAX_ASSEMBLED_CHARS}
          {overLimit && ' — 상한을 넘겨 저장할 수 없습니다'}
        </span>
      </div>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onBack}
            disabled={isPending}
            className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100 disabled:cursor-not-allowed"
          >
            이전
          </button>
          <LoadingButton
            isPending={isPending}
            pendingText="생성 중…"
            onClick={onRegenerate}
            className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-[13.5px] font-medium text-violet-600 transition-all hover:border-violet-300 disabled:opacity-60"
          >
            다시 생성
          </LoadingButton>
        </div>
        <LoadingButton
          isPending={isPending}
          onClick={onSubmit}
          disabled={overLimit || empty}
          className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-60"
        >
          스튜디오로 보내기
        </LoadingButton>
      </div>
    </div>
  );
};

export default PromptStep;
