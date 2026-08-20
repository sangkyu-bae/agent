import ProgressCard from '@/components/common/ProgressCard';
import { pipelineStepsToProgress } from '@/utils/pipelineStepsToProgress';
import type { PipelineStage, PipelineStepOut } from '@/types/agentPipeline';

interface WizardProgressProps {
  steps: PipelineStepOut[];
  activeStage?: PipelineStage | null;
  className?: string;
}

/**
 * 위저드 진행 표시 — 공통 `ProgressCard` 에 매핑 결과만 넘긴다.
 *
 * Design Ref: agent-create-wizard §5.1 / FR-F02 — **항상 5단계 고정 렌더**다.
 * 위저드가 책임지는 구간은 앞 3개뿐이고, 뒤 2개(에이전트 생성·프롬프트 연결)는
 * 스튜디오 저장에서 완료되므로 대기 상태로 남는다. 사용자가 "아직 저장 안 됐구나"를
 * 진행바만 보고 알 수 있게 하는 것이 이 선택의 이유다.
 *
 * 진행 UI 를 새로 구현하지 않는다 (common-card-components 위키 — 재사용 우선).
 */
const WizardProgress = ({
  steps,
  activeStage = null,
  className = '',
}: WizardProgressProps) => (
  <ProgressCard
    steps={pipelineStepsToProgress(steps, activeStage)}
    title="진행 상황"
    className={className}
  />
);

export default WizardProgress;
