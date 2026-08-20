// question-card Design §8.2 #6-14 — 순차 플로우 단위 테스트.
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import QuestionCardFlow from './QuestionCardFlow';
import type { FlowQuestion } from './types';

const questions: FlowQuestion[] = [
  {
    id: 'q1',
    title: '문서 범위는 어디까지인가요?',
    options: ['여신심사', '전체'],
    allowFreeText: true,
  },
  {
    id: 'q2',
    title: '응답 언어는 무엇인가요?',
    options: [],
    allowFreeText: true,
  },
];

const setup = (overrides?: Partial<Parameters<typeof QuestionCardFlow>[0]>) => {
  const onComplete = vi.fn();
  const utils = render(
    <QuestionCardFlow questions={questions} onComplete={onComplete} {...overrides} />,
  );
  return { onComplete, ...utils };
};

describe('QuestionCardFlow — 순차 노출 (F2/F6)', () => {
  it('초기에는 첫 질문 카드만 표시된다', () => {
    setup();

    expect(screen.getByText('문서 범위는 어디까지인가요?')).toBeInTheDocument();
    expect(screen.queryByText('응답 언어는 무엇인가요?')).not.toBeInTheDocument();
  });

  it('선택 전에는 제출 버튼이 비활성이다 (F4)', () => {
    setup();

    expect(screen.getByRole('button', { name: '제출' })).toBeDisabled();
  });

  it('옵션 선택 후 제출하면 카드가 잠기고 다음 질문이 나타난다', async () => {
    setup();

    await userEvent.click(screen.getByText('여신심사'));
    await userEvent.click(screen.getByRole('button', { name: '제출' }));

    expect(screen.getByText('✓ 답변 완료')).toBeInTheDocument();
    expect(screen.getByText('응답 언어는 무엇인가요?')).toBeInTheDocument();
    // 잠긴 카드의 라디오는 비활성
    expect(screen.getByRole('radio', { name: '여신심사' })).toBeDisabled();
  });

  it('직접 입력 텍스트가 답변 값이 된다 (F3)', async () => {
    const { onComplete } = setup();

    // q1: 직접 입력
    await userEvent.click(screen.getByText('직접 입력 (원하는 내용을 자유롭게 작성)'));
    await userEvent.type(
      screen.getByLabelText('문서 범위는 어디까지인가요? 직접 입력'),
      '여신+수신',
    );
    await userEvent.click(screen.getByRole('button', { name: '제출' }));

    // q2: 직접 입력
    await userEvent.click(
      screen.getAllByText('직접 입력 (원하는 내용을 자유롭게 작성)').at(-1)!,
    );
    await userEvent.type(
      screen.getByLabelText('응답 언어는 무엇인가요? 직접 입력'),
      '한국어',
    );
    await userEvent.click(screen.getByRole('button', { name: '제출' }));

    expect(onComplete).toHaveBeenCalledWith([
      { id: 'q1', value: '여신+수신' },
      { id: 'q2', value: '한국어' },
    ]);
  });

  it('직접 입력 선택 후 텍스트가 비어 있으면 제출이 비활성이다 (F4)', async () => {
    setup();

    await userEvent.click(screen.getByText('직접 입력 (원하는 내용을 자유롭게 작성)'));

    expect(screen.getByRole('button', { name: '제출' })).toBeDisabled();
  });

  it('건너뛰기는 무응답으로 확정하고 다음 질문으로 넘어간다 (F5)', async () => {
    const { onComplete } = setup();

    await userEvent.click(screen.getByRole('button', { name: '건너뛰기' }));

    expect(screen.getByText('응답 언어는 무엇인가요?')).toBeInTheDocument();
    expect(onComplete).not.toHaveBeenCalled();
  });

  it('마지막 질문 제출 시 onComplete가 전체 답변으로 1회 호출된다 (F6/F7)', async () => {
    const { onComplete } = setup();

    await userEvent.click(screen.getByText('전체'));
    await userEvent.click(screen.getByRole('button', { name: '제출' }));
    await userEvent.click(screen.getByRole('button', { name: '건너뛰기' }));

    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith([
      { id: 'q1', value: '전체' },
      { id: 'q2', value: '' },
    ]);
    // 완료 후 모든 카드 잠금 — 제출/건너뛰기 버튼 없음
    expect(screen.queryByRole('button', { name: '제출' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '건너뛰기' })).not.toBeInTheDocument();
  });
});

describe('QuestionCardFlow — 외부 상태 (F8/F9)', () => {
  it('completed=true면 모든 카드가 잠금 상태로 표시된다 (F8)', () => {
    setup({ completed: true });

    expect(screen.getByText('문서 범위는 어디까지인가요?')).toBeInTheDocument();
    expect(screen.getByText('응답 언어는 무엇인가요?')).toBeInTheDocument();
    expect(screen.getAllByText('✓ 답변 완료')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: '제출' })).not.toBeInTheDocument();
    expect(screen.getByRole('radio', { name: '여신심사' })).toBeDisabled();
  });

  it('disabled=true면 라디오·제출·건너뛰기가 모두 비활성이다 (F9)', () => {
    setup({ disabled: true });

    expect(screen.getByRole('radio', { name: '여신심사' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '제출' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '건너뛰기' })).toBeDisabled();
  });

  it('questions가 비어 있으면 아무것도 렌더하지 않는다', () => {
    const { container } = setup({ questions: [] });

    expect(container.firstChild).toBeNull();
  });

  it('header 슬롯을 카드 위에 렌더한다', () => {
    setup({ header: <p>계획 요약입니다</p> });

    expect(screen.getByText('계획 요약입니다')).toBeInTheDocument();
  });
});
