// question-card Design §8.2 #1-5 — 조합 파츠 단위 테스트.
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import QuestionCard from './QuestionCard';
import QuestionOptionItem from './QuestionOptionItem';
import QuestionFreeTextOption from './QuestionFreeTextOption';

describe('QuestionOptionItem', () => {
  it('클릭하면 onSelect가 호출되고 선택 상태가 라디오에 반영된다', async () => {
    const onSelect = vi.fn();
    const { rerender } = render(
      <QuestionOptionItem name="q1" label="옵션 A" selected={false} onSelect={onSelect} />,
    );

    await userEvent.click(screen.getByText('옵션 A'));
    expect(onSelect).toHaveBeenCalledTimes(1);

    rerender(
      <QuestionOptionItem name="q1" label="옵션 A" selected onSelect={onSelect} />,
    );
    expect(screen.getByRole('radio', { name: '옵션 A' })).toBeChecked();
  });

  it('disabled면 클릭해도 onSelect가 호출되지 않는다', async () => {
    const onSelect = vi.fn();
    render(
      <QuestionOptionItem name="q1" label="옵션 A" selected={false} disabled onSelect={onSelect} />,
    );

    await userEvent.click(screen.getByText('옵션 A'));
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole('radio', { name: '옵션 A' })).toBeDisabled();
  });

  // wizard-chat-layout FR-15 실측 회귀 가드 — label에 relative가 없으면
  // sr-only(absolute) 라디오가 body 기준으로 배치돼 스크롤 컨테이너의 overflow
  // 클리핑을 탈출하고, 카드가 쌓이면 문서 스크롤바 + 하단 흰 영역을 만든다.
  it('라디오의 containing block이 label이다 (relative — 클리핑 탈출 방지)', () => {
    render(
      <QuestionOptionItem name="q1" label="옵션 A" selected={false} onSelect={() => {}} />,
    );

    const label = screen.getByRole('radio', { name: '옵션 A' }).closest('label')!;
    expect(label.className).toContain('relative');
  });
});

describe('QuestionFreeTextOption', () => {
  it('선택하면 텍스트 입력이 확장된다', () => {
    render(
      <QuestionFreeTextOption
        name="q1"
        selected
        value=""
        onSelect={() => {}}
        onChange={() => {}}
      />,
    );

    expect(
      screen.getByRole('radio', { name: '직접 입력 (원하는 내용을 자유롭게 작성)' }),
    ).toBeChecked();
    expect(screen.getByLabelText('직접 입력')).toBeInTheDocument();
  });

  it('라디오의 containing block이 label이다 (relative — 클리핑 탈출 방지)', () => {
    render(
      <QuestionFreeTextOption
        name="q1"
        selected={false}
        value=""
        onSelect={() => {}}
        onChange={() => {}}
      />,
    );

    const label = screen
      .getByRole('radio', { name: '직접 입력 (원하는 내용을 자유롭게 작성)' })
      .closest('label')!;
    expect(label.className).toContain('relative');
  });

  it('미선택이면 텍스트 입력이 표시되지 않고 재선택 시 value가 복원된다', () => {
    const { rerender } = render(
      <QuestionFreeTextOption
        name="q1"
        selected={false}
        value="이전 값"
        onSelect={() => {}}
        onChange={() => {}}
      />,
    );

    expect(screen.queryByLabelText('직접 입력')).not.toBeInTheDocument();

    // 재선택하면 보존된 value가 입력에 복원된다 (Analysis G4)
    rerender(
      <QuestionFreeTextOption
        name="q1"
        selected
        value="이전 값"
        onSelect={() => {}}
        onChange={() => {}}
      />,
    );
    expect(screen.getByLabelText('직접 입력')).toHaveValue('이전 값');
  });

  it('입력하면 onChange가 호출된다', async () => {
    const onChange = vi.fn();
    render(
      <QuestionFreeTextOption
        name="q1"
        selected
        value=""
        onSelect={() => {}}
        onChange={onChange}
      />,
    );

    await userEvent.type(screen.getByLabelText('직접 입력'), '한');
    expect(onChange).toHaveBeenCalledWith('한');
  });
});

describe('QuestionCard', () => {
  it('질문 헤더·children·footer를 렌더한다', () => {
    render(
      <QuestionCard title="질문 A" footer={<button type="button">제출</button>}>
        <p>옵션 영역</p>
      </QuestionCard>,
    );

    expect(screen.getByText('질문 A')).toBeInTheDocument();
    expect(screen.getByText('옵션 영역')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '제출' })).toBeInTheDocument();
  });

  it('locked면 footer 대신 답변 완료 배지를 표시한다', () => {
    render(
      <QuestionCard title="질문 A" locked footer={<button type="button">제출</button>}>
        <p>옵션 영역</p>
      </QuestionCard>,
    );

    expect(screen.getByText('✓ 답변 완료')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '제출' })).not.toBeInTheDocument();
  });
});
