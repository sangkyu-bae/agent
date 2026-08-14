// Design Ref: agent-create-entry §6.1 — compose가 쓸 만한 초안을 못 냈을 때.
// 빈 스튜디오로 떨어뜨리면 사용자가 이유를 모르므로 진입 화면에 머물며 사유를 보여준다.
import type { ComposeMissingCapability } from '@/types/agentComposer';

export type ComposeFailureReason =
  | 'coverage_none'
  | 'api_error'
  | 'clarify_exhausted';

export interface ComposeFailure {
  reason: ComposeFailureReason;
  message: string;
  missing: ComposeMissingCapability[];
}

const TITLES: Record<ComposeFailureReason, string> = {
  coverage_none: '이 요청을 충족할 도구가 없습니다',
  api_error: '초안 생성에 실패했습니다',
  clarify_exhausted: '요청을 더 구체적으로 적어 주세요',
};

interface ComposeFailureCardProps {
  failure: ComposeFailure;
  onRetry: () => void;
  onManualCreate: () => void;
}

const ComposeFailureCard = ({
  failure,
  onRetry,
  onManualCreate,
}: ComposeFailureCardProps) => (
  <div className="rounded-2xl border border-amber-200 bg-amber-50/60 p-5 text-left">
    <p className="text-[13.5px] font-semibold text-zinc-900">
      ⚠ {TITLES[failure.reason]}
    </p>

    {failure.message && (
      <p className="mt-1.5 text-[12.5px] leading-relaxed text-zinc-600">
        {failure.message}
      </p>
    )}

    {failure.missing.length > 0 && (
      <ul className="mt-3 space-y-2">
        {failure.missing.map((m) => (
          <li key={m.capability} className="text-[12.5px] leading-relaxed">
            <span className="font-medium text-zinc-800">· {m.capability}</span>
            {m.reason && <span className="text-zinc-500"> — {m.reason}</span>}
            {m.suggestion && (
              <span className="block pl-3 text-zinc-500">→ {m.suggestion}</span>
            )}
          </li>
        ))}
      </ul>
    )}

    <div className="mt-4 flex items-center gap-2">
      <button
        type="button"
        onClick={onRetry}
        className="rounded-lg bg-violet-600 px-3.5 py-1.5 text-[12.5px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
      >
        다시 설명하기
      </button>
      <button
        type="button"
        onClick={onManualCreate}
        className="rounded-lg border border-zinc-300 bg-white px-3.5 py-1.5 text-[12.5px] font-medium text-zinc-600 transition-all hover:border-violet-400 hover:text-violet-600 active:scale-95"
      >
        그래도 직접 만들기
      </button>
    </div>
  </div>
);

export default ComposeFailureCard;
