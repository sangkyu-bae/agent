import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import BoundaryRulesEditor from './BoundaryRulesEditor';
import type { BoundaryRule } from '@/types/chunkingProfile';

const twoRules: BoundaryRule[] = [
  { pattern: '^제\\s*\\d+\\s*장', priority: 1, level: 'parent' },
  { pattern: '^제\\s*\\d+\\s*조', priority: 2, level: 'child' },
];

describe('BoundaryRulesEditor', () => {
  it('E1: 규칙 추가 버튼 클릭 시 child 기본값 행이 추가된다', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<BoundaryRulesEditor rules={[]} onChange={onChange} />);

    await user.click(screen.getByRole('button', { name: '규칙 추가' }));

    expect(onChange).toHaveBeenCalledWith([
      { pattern: '', priority: 1, level: 'child' },
    ]);
  });

  it('E2: 행 삭제 시 해당 행만 제거된다', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<BoundaryRulesEditor rules={twoRules} onChange={onChange} />);

    await user.click(screen.getByRole('button', { name: '규칙 1 삭제' }));

    expect(onChange).toHaveBeenCalledWith([twoRules[1]]);
  });

  it('E3: 잘못된 정규식 패턴은 인라인 에러를 표시한다', () => {
    render(
      <BoundaryRulesEditor
        rules={[{ pattern: '[미완성', priority: 1, level: 'child' }]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText('유효하지 않은 정규식')).toBeInTheDocument();
  });

  it('E4: level 변경이 onChange에 반영된다', () => {
    const onChange = vi.fn();
    render(<BoundaryRulesEditor rules={twoRules} onChange={onChange} />);

    fireEvent.change(screen.getByRole('combobox', { name: '규칙 2 레벨' }), {
      target: { value: 'parent' },
    });

    expect(onChange).toHaveBeenCalledWith([
      twoRules[0],
      { ...twoRules[1], level: 'parent' },
    ]);
  });

  it('E5: 규칙이 없으면 빈 상태 안내를 표시한다', () => {
    render(<BoundaryRulesEditor rules={[]} onChange={vi.fn()} />);
    expect(
      screen.getByText('규칙이 없습니다. 조항 경계 정규식을 추가하세요.'),
    ).toBeInTheDocument();
  });
});
