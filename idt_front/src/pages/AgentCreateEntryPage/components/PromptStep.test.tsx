// Design §5.4 step④ — 프롬프트 편집기의 props 경계(상한 가드·경고 배너·도구 요약).
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MAX_ASSEMBLED_CHARS } from '@/types/agentPipeline';
import PromptStep from './PromptStep';

const setup = (props: Partial<Parameters<typeof PromptStep>[0]> = {}) => {
  const onChange = vi.fn();
  const onRegenerate = vi.fn();
  const onSubmit = vi.fn();
  const onBack = vi.fn();
  render(
    <PromptStep
      value="당신은 사내 문서를 찾아 답하는 에이전트입니다."
      clampReason={null}
      degraded={false}
      toolNames={[]}
      isPending={false}
      onChange={onChange}
      onRegenerate={onRegenerate}
      onSubmit={onSubmit}
      onBack={onBack}
      {...props}
    />,
  );
  return {
    onChange,
    onRegenerate,
    onSubmit,
    onBack,
    user: userEvent.setup(),
  };
};

const editor = () => screen.getByLabelText('시스템 프롬프트');
const sendButton = () => screen.getByRole('button', { name: '스튜디오로 보내기' });

describe('PromptStep', () => {
  it('프롬프트를 편집 가능한 textarea 에 프리필한다', () => {
    setup();

    expect(editor()).toHaveValue('당신은 사내 문서를 찾아 답하는 에이전트입니다.');
    expect(editor()).toBeEnabled();
  });

  it('편집하면 onChange 로 올린다', async () => {
    const { onChange, user } = setup({ value: '지침' });

    await user.type(editor(), '!');

    expect(onChange).toHaveBeenCalledWith('지침!');
  });

  it('현재 길이와 상한을 함께 보여준다', () => {
    setup({ value: '가나다' });

    expect(screen.getByText(`3 / ${MAX_ASSEMBLED_CHARS}`)).toBeInTheDocument();
  });

  it('상한을 넘기면 경고와 함께 전송을 막는다', () => {
    // 여기서 막지 않으면 스튜디오 저장에서 422 가 난다.
    setup({ value: '가'.repeat(MAX_ASSEMBLED_CHARS + 1) });

    expect(screen.getByText(/상한을 넘겨 저장할 수 없습니다/)).toBeInTheDocument();
    expect(sendButton()).toBeDisabled();
  });

  it('비어 있으면 전송을 막는다', () => {
    setup({ value: '   ' });

    expect(sendButton()).toBeDisabled();
  });

  it('clamp 사유가 있으면 절단 안내를 띄운다', () => {
    setup({ clampReason: '프롬프트 5000자 → 4000자 절단' });

    expect(screen.getByText(/일부가 잘렸습니다/)).toBeInTheDocument();
    expect(screen.getByText(/4000자 절단/)).toBeInTheDocument();
  });

  it('degraded 면 규칙기반 폴백 안내를 띄운다', () => {
    setup({ degraded: true });

    expect(
      screen.getByText(/규칙기반 문안으로 만들었습니다/),
    ).toBeInTheDocument();
  });

  it('확정 도구를 읽기 전용 칩으로 요약한다', () => {
    setup({ toolNames: ['문서 검색', '엑셀 내보내기'] });

    expect(screen.getByText('사용 도구')).toBeInTheDocument();
    expect(screen.getByText('문서 검색')).toBeInTheDocument();
    expect(screen.getByText('엑셀 내보내기')).toBeInTheDocument();
  });

  it('도구가 없으면 요약 영역을 감춘다', () => {
    setup({ toolNames: [] });

    expect(screen.queryByText('사용 도구')).not.toBeInTheDocument();
  });

  it('[다시 생성]·[이전]·[스튜디오로 보내기]가 각 콜백을 부른다', async () => {
    const { onRegenerate, onSubmit, onBack, user } = setup();

    await user.click(screen.getByRole('button', { name: '다시 생성' }));
    await user.click(screen.getByRole('button', { name: '이전' }));
    await user.click(sendButton());

    expect(onRegenerate).toHaveBeenCalledTimes(1);
    expect(onBack).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('isPending 이면 편집과 버튼을 잠근다', () => {
    setup({ isPending: true });

    expect(editor()).toBeDisabled();
    expect(screen.getByRole('button', { name: '이전' })).toBeDisabled();
    expect(screen.getByRole('button', { name: /생성 중/ })).toBeDisabled();
  });

  // prompt-depth FR-23/FR-25
  it('상한이 서버(8000)와 같은 값이다', () => {
    expect(MAX_ASSEMBLED_CHARS).toBe(8000);
  });

  it('상한 경계에서는 저장을 막지 않는다', () => {
    setup({ value: '가'.repeat(MAX_ASSEMBLED_CHARS) });

    expect(sendButton()).toBeEnabled();
  });

  it('긴 본문을 읽을 수 있게 편집기가 스크롤된다', () => {
    setup({ value: '가'.repeat(3000) });

    const textarea = editor();
    expect(textarea).toHaveAttribute('rows', '22');
    expect(textarea.className).toContain('overflow-y-auto');
    expect(textarea.className).toContain('max-h-[60vh]');
  });
});
