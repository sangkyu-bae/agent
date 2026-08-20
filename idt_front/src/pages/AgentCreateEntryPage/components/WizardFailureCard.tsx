import type { PipelineError } from '@/hooks/useAgentPipelineStream';

interface WizardFailureCardProps {
  error: PipelineError;
  onRetry: () => void;
  onManualCreate: () => void;
}

/**
 * 단계 실패·SSE 끊김 안내 (Design §6.1 / FR-F10).
 *
 * 재시도가 안전한 이유를 사용자에게 굳이 설명하지 않지만, 설계상 중요하다:
 * 위저드는 `create` 단계에 도달하지 않으므로 **재시도해도 에이전트가 중복
 * 생성되지 않는다**. 기존 논스톱 파이프라인이 안고 있던 R7 위험이 이 화면에는
 * 존재하지 않는다.
 */
const WizardFailureCard = ({
  error,
  onRetry,
  onManualCreate,
}: WizardFailureCardProps) => (
  <div
    role="alert"
    className="rounded-2xl border border-red-200 bg-red-50/60 p-5"
  >
    <h3 className="text-[14px] font-semibold text-red-700">
      진행하지 못했습니다
    </h3>
    <p className="mt-1 text-[12.5px] leading-relaxed text-red-600">
      {error.message}
    </p>
    <div className="mt-4 flex items-center gap-2">
      <button
        type="button"
        onClick={onRetry}
        className="rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
      >
        다시 시도
      </button>
      <button
        type="button"
        onClick={onManualCreate}
        className="rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300"
      >
        직접 만들기
      </button>
    </div>
  </div>
);

export default WizardFailureCard;
