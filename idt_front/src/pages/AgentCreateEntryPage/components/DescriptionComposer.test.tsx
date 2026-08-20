// Design §5.4 step① — 설명 입력창의 props 경계(입력 클램프·키보드 규약·전송 가드).
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MAX_PIPELINE_USER_REQUEST_CHARS } from '@/types/agentPipeline';
import DescriptionComposer from './DescriptionComposer';

const setup = (props: Partial<Parameters<typeof DescriptionComposer>[0]> = {}) => {
  const onChange = vi.fn();
  const onSubmit = vi.fn();
  render(
    <DescriptionComposer
      value=""
      onChange={onChange}
      onSubmit={onSubmit}
      isPending={false}
      {...props}
    />,
  );
  return { onChange, onSubmit, user: userEvent.setup() };
};

const textarea = () => screen.getByLabelText('에이전트 설명');
const sendButton = () =>
  screen.getByRole('button', { name: '에이전트 설명 전송' });

describe('DescriptionComposer', () => {
  it('aria-label 과 예시 placeholder 를 제공한다', () => {
    setup();

    expect(textarea()).toBeInTheDocument();
    expect(textarea()).toHaveAttribute(
      'placeholder',
      '구축하려는 에이전트에 대해 설명해 주세요',
    );
  });

  it('상한을 넘긴 입력은 잘라서 onChange 로 올린다', async () => {
    // 서버 max_length 와 같은 값으로 미리 자른다 — 422 를 만들지 않기 위해서다.
    const { onChange, user } = setup();

    await user.click(textarea());
    await user.paste('가'.repeat(MAX_PIPELINE_USER_REQUEST_CHARS + 50));

    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange.mock.calls[0][0]).toHaveLength(
      MAX_PIPELINE_USER_REQUEST_CHARS,
    );
  });

  it('Enter 는 전송, Shift+Enter 는 줄바꿈이다', async () => {
    const { onSubmit, user } = setup({ value: '문서 봇' });

    await user.click(textarea());
    await user.keyboard('{Enter}');
    expect(onSubmit).toHaveBeenCalledTimes(1);

    await user.keyboard('{Shift>}{Enter}{/Shift}');
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('공백만 있으면 전송 버튼과 Enter 를 모두 막는다', async () => {
    const { onSubmit, user } = setup({ value: '   ' });

    expect(sendButton()).toBeDisabled();
    await user.click(textarea());
    await user.keyboard('{Enter}');

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('전송 버튼 클릭은 onSubmit 을 호출한다', async () => {
    const { onSubmit, user } = setup({ value: '문서 봇' });

    await user.click(sendButton());

    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('isPending 이면 입력을 잠그고 진행 표시를 보여준다', () => {
    setup({ value: '문서 봇', isPending: true });

    expect(textarea()).toBeDisabled();
    expect(sendButton()).toBeDisabled();
    expect(screen.getByLabelText('초안 생성 중')).toBeInTheDocument();
  });

  // wizard-chat-layout FR-08 — chat 모드 하단 고정 입력창은 재전송 창구가 아니다.
  // 파이프라인 왕복은 카드 상호작용으로만 일어난다.
  describe('variant="chat"', () => {
    it('입력과 전송을 잠그고 안내 placeholder 를 보여준다', () => {
      setup({ variant: 'chat' });

      expect(textarea()).toBeDisabled();
      expect(textarea()).toHaveAttribute(
        'placeholder',
        '질문 카드에 답하면 다음 단계로 진행됩니다',
      );
      expect(sendButton()).toBeDisabled();
    });

    it('값이 있어도 전송이 불가능하다', async () => {
      const { onSubmit, user } = setup({ variant: 'chat', value: '문서 봇' });

      expect(sendButton()).toBeDisabled();
      await user.click(sendButton());

      expect(onSubmit).not.toHaveBeenCalled();
    });

    it('isPending 이면 진행 표시를 유지한다', () => {
      setup({ variant: 'chat', isPending: true });

      expect(screen.getByLabelText('초안 생성 중')).toBeInTheDocument();
    });
  });
});
