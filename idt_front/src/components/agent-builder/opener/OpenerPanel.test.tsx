// agent-opener Design §5.1 / §8.3 #1~#4 — 오프너 탭 패널 단위 테스트
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import OpenerPanel from './OpenerPanel';
import { OPENER_LIMITS } from '@/constants/agentOpener';

const renderPanel = (openers: string[] = []) => {
  const onChange = vi.fn();
  render(<OpenerPanel openers={openers} onChange={onChange} />);
  return { onChange };
};

describe('OpenerPanel — 렌더', () => {
  it('안내문·카운터·추가 버튼·빈 안내를 노출하고 자체 저장 버튼은 없다', () => {
    renderPanel();
    expect(
      screen.getByText('사용자가 대화를 시작할 수 있는 예시 질문을 설정하세요'),
    ).toBeInTheDocument();
    expect(screen.getByText('0/12')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '추가' })).toBeEnabled();
    expect(screen.getByText(/아직 등록된 오프너가 없습니다\. \+ 추가로 시작하세요/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '저장' })).not.toBeInTheDocument();
  });

  it('기존 오프너를 번호 배지와 입력 행으로 프라임한다', () => {
    renderPanel(['질문 A', '질문 B']);
    expect(screen.getByText('2/12')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '오프너 1' })).toHaveValue('질문 A');
    expect(screen.getByRole('textbox', { name: '오프너 2' })).toHaveValue('질문 B');
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.queryByText(/아직 등록된 오프너가 없습니다/)).not.toBeInTheDocument();
  });

  it('입력 maxLength는 200이다', () => {
    renderPanel(['a']);
    expect(screen.getByRole('textbox', { name: '오프너 1' })).toHaveAttribute(
      'maxlength',
      String(OPENER_LIMITS.MAX_LENGTH),
    );
  });
});

describe('OpenerPanel — 상호작용', () => {
  it('추가 클릭 시 빈 행이 끝에 추가된 배열로 onChange 한다', async () => {
    const { onChange } = renderPanel(['a']);
    await userEvent.click(screen.getByRole('button', { name: '추가' }));
    expect(onChange).toHaveBeenCalledWith(['a', '']);
  });

  it('입력 변경 시 해당 인덱스만 바뀐 배열로 onChange 한다', () => {
    const { onChange } = renderPanel(['a', 'b']);
    fireEvent.change(screen.getByRole('textbox', { name: '오프너 2' }), {
      target: { value: 'bb' },
    });
    expect(onChange).toHaveBeenCalledWith(['a', 'bb']);
  });

  it('삭제 클릭 시 해당 행이 빠진 배열로 onChange 한다', async () => {
    const { onChange } = renderPanel(['a', 'b', 'c']);
    await userEvent.click(screen.getByRole('button', { name: '오프너 2 삭제' }));
    expect(onChange).toHaveBeenCalledWith(['a', 'c']);
  });

  it('12개면 추가 버튼이 비활성이고 카운터가 12/12다', () => {
    const twelve = Array.from({ length: OPENER_LIMITS.MAX_COUNT }, (_, i) => `q${i}`);
    renderPanel(twelve);
    expect(screen.getByText('12/12')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '추가' })).toBeDisabled();
  });
});
