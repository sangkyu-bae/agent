// Design §5.4 step② — 질문 카드 조합 + 건너뛰기 + 스테일 가드의 props 경계.
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MAX_CLARIFY_ROUNDS } from '@/types/agentPipeline';
import type { PipelineQuestion } from '@/types/agentPipeline';
import IntentStep from './IntentStep';

const QUESTIONS: PipelineQuestion[] = [
  {
    slot_key: 'purpose',
    question: '이 에이전트의 핵심 용도는 무엇인가요?',
    options: ['문서 Q&A', '보고서 작성'],
    allow_free_text: true,
  },
  {
    slot_key: 'audience',
    question: '누가 사용하나요?',
    options: ['사내 직원', '고객'],
    allow_free_text: false,
  },
];

const setup = (props: Partial<Parameters<typeof IntentStep>[0]> = {}) => {
  const onSubmit = vi.fn();
  const onSkip = vi.fn();
  render(
    <IntentStep
      questions={QUESTIONS}
      round={1}
      maxRounds={2}
      isPending={false}
      answered={false}
      onSubmit={onSubmit}
      onSkip={onSkip}
      {...props}
    />,
  );
  return { onSubmit, onSkip, user: userEvent.setup() };
};

const submitButton = () => screen.getByRole('button', { name: '제출' });

describe('IntentStep', () => {
  it('첫 질문 카드부터 순차로 보여준다', () => {
    setup();

    expect(
      screen.getByText('이 에이전트의 핵심 용도는 무엇인가요?'),
    ).toBeInTheDocument();
    expect(screen.queryByText('누가 사용하나요?')).not.toBeInTheDocument();
  });

  it('남은 라운드를 안내한다', () => {
    setup({ round: 1, maxRounds: 2 });

    expect(screen.getByText(/남은 질문 라운드 1회/)).toBeInTheDocument();
  });

  it('상한에 닿으면 남은 라운드 안내를 감춘다', () => {
    setup({ round: 2, maxRounds: 2 });

    expect(screen.queryByText(/남은 질문 라운드/)).not.toBeInTheDocument();
  });

  // prompt-depth FR-24 — 서버 INTENT_MAX_CLARIFICATION_ROUNDS 와 같은 값이어야
  // "남은 라운드" 안내가 거짓말이 되지 않는다.
  it('라운드 상한 상수가 서버(3)와 같은 값이다', () => {
    expect(MAX_CLARIFY_ROUNDS).toBe(3);
  });

  it('상한 3에서 첫 라운드는 2회가 남았다고 안내한다', () => {
    setup({ round: 1, maxRounds: MAX_CLARIFY_ROUNDS });

    expect(screen.getByText(/남은 질문 라운드 2회/)).toBeInTheDocument();
  });

  it('모든 답변을 slot_key 기준으로 되돌린다', async () => {
    const { onSubmit, user } = setup();

    await user.click(screen.getByText('문서 Q&A'));
    await user.click(submitButton());
    await user.click(screen.getByText('사내 직원'));
    await user.click(submitButton());

    expect(onSubmit).toHaveBeenCalledWith([
      { slot_key: 'purpose', value: '문서 Q&A' },
      { slot_key: 'audience', value: '사내 직원' },
    ]);
  });

  it('무응답 질문은 아예 보내지 않는다', async () => {
    // 서버 SlotAnswer 가 min_length=1 이라 빈 값을 실으면 422 다.
    const { onSubmit, user } = setup();

    await user.click(screen.getByRole('button', { name: '건너뛰기' }));
    await user.click(screen.getByText('사내 직원'));
    await user.click(submitButton());

    expect(onSubmit).toHaveBeenCalledWith([
      { slot_key: 'audience', value: '사내 직원' },
    ]);
  });

  it('[건너뛰고 계속하기]는 onSkip 을 호출한다', async () => {
    const { onSkip, user } = setup();

    await user.click(screen.getByRole('button', { name: '건너뛰고 계속하기' }));

    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  it('answered 면 건너뛰기를 감춘다 (스테일 카드 가드)', () => {
    setup({ answered: true });

    expect(
      screen.queryByRole('button', { name: '건너뛰고 계속하기' }),
    ).not.toBeInTheDocument();
  });

  // wizard-chat-layout FR-07 — 잠긴 라운드는 트랜스크립트 이력이다. 활성 라운드
  // 안내(남은 횟수)가 지난 카드에 남으면 거짓 정보가 된다.
  it('answered 면 라운드 안내 헤더를 감춘다 (이력 카드)', () => {
    setup({ answered: true });

    expect(screen.queryByText(/남은 질문 라운드/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/몇 가지만 확인할게요/),
    ).not.toBeInTheDocument();
  });

  it('isPending 이면 건너뛰기를 잠근다', () => {
    setup({ isPending: true });

    expect(
      screen.getByRole('button', { name: '건너뛰고 계속하기' }),
    ).toBeDisabled();
  });
});
