// Design §5.4 공통 — 진행바는 입력과 무관하게 항상 5행이고, 상태는 텍스트로 병기한다.
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PIPELINE_STAGE_STATUS } from '@/types/agentPipeline';
import type { PipelineStepOut } from '@/types/agentPipeline';
import WizardProgress from './WizardProgress';

const LABELS = [
  '의도 파악',
  '도구 추천',
  '프롬프트 생성',
  '에이전트 생성',
  '프롬프트 연결',
];

const step = (
  stage: PipelineStepOut['stage'],
  status: PipelineStepOut['status'],
  reason: string | null = null,
): PipelineStepOut => ({ stage, status, reason, elapsed_ms: 1 });

const row = (label: string) => screen.getByText(label).closest('li')!;

describe('WizardProgress', () => {
  it('steps 가 비어도 5단계를 모두 렌더한다', () => {
    // 위저드가 책임지는 구간은 앞 3개지만, 뒤 2개를 감추면 "저장하면 끝난다"는
    // 사실이 화면에서 사라진다.
    render(<WizardProgress steps={[]} />);

    for (const label of LABELS) expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByText('진행 상황')).toBeInTheDocument();
  });

  it('ok/skipped 를 완료·대기중으로 옮긴다', () => {
    render(
      <WizardProgress
        steps={[
          step('intent', PIPELINE_STAGE_STATUS.OK),
          step('tools', PIPELINE_STAGE_STATUS.SKIPPED, 'stopped_for_review'),
        ]}
      />,
    );

    expect(within(row('의도 파악')).getByText('완료')).toBeInTheDocument();
    expect(within(row('도구 추천')).getByText('대기중')).toBeInTheDocument();
    // skipped 의 내부 사유는 노출하지 않는다.
    expect(screen.queryByText(/stopped_for_review/)).not.toBeInTheDocument();
  });

  it('degraded 는 완료 + 사유 배지로 보여준다', () => {
    render(
      <WizardProgress
        steps={[step('tools', PIPELINE_STAGE_STATUS.DEGRADED, '추천 실패')]}
      />,
    );

    expect(within(row('도구 추천')).getByText('추천 실패')).toBeInTheDocument();
  });

  it('failed 는 실패 배지로 보여준다', () => {
    render(
      <WizardProgress
        steps={[step('prompt', PIPELINE_STAGE_STATUS.FAILED, '끊김')]}
      />,
    );

    expect(within(row('프롬프트 생성')).getByText('실패')).toBeInTheDocument();
  });

  it('activeStage 는 진행중으로 표시한다', () => {
    render(<WizardProgress steps={[]} activeStage="prompt" />);

    expect(within(row('프롬프트 생성')).getByText('진행중')).toBeInTheDocument();
    expect(within(row('의도 파악')).getByText('대기중')).toBeInTheDocument();
  });

  it('이미 완료된 단계는 activeStage 여도 되돌리지 않는다', () => {
    // 늦게 도착한 started 이벤트로 진행바가 역행하면 안 된다.
    render(
      <WizardProgress
        steps={[step('intent', PIPELINE_STAGE_STATUS.OK)]}
        activeStage="intent"
      />,
    );

    expect(within(row('의도 파악')).getByText('완료')).toBeInTheDocument();
  });
});
