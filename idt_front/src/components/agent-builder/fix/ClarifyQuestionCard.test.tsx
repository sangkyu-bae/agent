import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ClarifyingQuestion } from '@/types/agentComposer';
import ClarifyQuestionCard from './ClarifyQuestionCard';

const questions: ClarifyingQuestion[] = [
  {
    id: 'q0-1',
    question: '문서 범위는 어디까지인가요?',
    options: ['여신심사', '전체'],
    allow_free_text: true,
  },
  {
    id: 'q0-2',
    question: '응답 언어는 무엇인가요?',
    options: [],
    allow_free_text: true,
  },
];

const renderCard = (overrides?: Partial<Parameters<typeof ClarifyQuestionCard>[0]>) => {
  const onSubmit = vi.fn();
  render(
    <ClarifyQuestionCard
      questions={questions}
      planSummary="규정 질의응답 에이전트로 이해했어요."
      answered={false}
      isPending={false}
      onSubmit={onSubmit}
      {...overrides}
    />,
  );
  return { onSubmit };
};

describe('ClarifyQuestionCard (fix-agent-planner-hitl)', () => {
  it('planSummary와 질문·선택지를 렌더한다', () => {
    renderCard();
    expect(screen.getByText('규정 질의응답 에이전트로 이해했어요.')).toBeInTheDocument();
    expect(screen.getByText('문서 범위는 어디까지인가요?')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '여신심사' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '전체' })).toBeInTheDocument();
  });

  it('선택지 선택 + 자유 입력 답변을 모아 제출한다', async () => {
    const { onSubmit } = renderCard();

    await userEvent.click(screen.getByRole('button', { name: '여신심사' }));
    await userEvent.type(
      screen.getByLabelText('응답 언어는 무엇인가요? 직접 입력'),
      '한국어',
    );
    await userEvent.click(screen.getByRole('button', { name: '답변 제출' }));

    expect(onSubmit).toHaveBeenCalledWith([
      { question_id: 'q0-1', question: '문서 범위는 어디까지인가요?', answer: '여신심사' },
      { question_id: 'q0-2', question: '응답 언어는 무엇인가요?', answer: '한국어' },
    ]);
  });

  it('부분 답변 허용: 미답변 질문은 answer=""로 제출된다', async () => {
    const { onSubmit } = renderCard();

    await userEvent.click(screen.getByRole('button', { name: '전체' }));
    await userEvent.click(screen.getByRole('button', { name: '답변 제출' }));

    expect(onSubmit).toHaveBeenCalledWith([
      { question_id: 'q0-1', question: '문서 범위는 어디까지인가요?', answer: '전체' },
      { question_id: 'q0-2', question: '응답 언어는 무엇인가요?', answer: '' },
    ]);
  });

  it('자유 입력이 있으면 선택지보다 우선한다', async () => {
    const { onSubmit } = renderCard();

    await userEvent.click(screen.getByRole('button', { name: '여신심사' }));
    await userEvent.type(
      screen.getByLabelText('문서 범위는 어디까지인가요? 직접 입력'),
      '여신+수신',
    );
    await userEvent.click(screen.getByRole('button', { name: '답변 제출' }));

    expect(onSubmit.mock.calls[0][0][0].answer).toBe('여신+수신');
  });

  it('answered=true면 제출 버튼 대신 답변 완료 표시 + 입력 비활성', () => {
    const { onSubmit } = renderCard({ answered: true });

    expect(screen.getByText('✓ 답변 완료')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '답변 제출' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '여신심사' })).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('isPending이면 제출 버튼 비활성', () => {
    renderCard({ isPending: true });
    expect(screen.getByRole('button', { name: '답변 제출' })).toBeDisabled();
  });
});
