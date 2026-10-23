import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import EmptyState from './EmptyState';

describe('EmptyState', () => {
  it('제목·설명·액션·children을 렌더링한다', () => {
    render(
      <EmptyState
        icon={<svg data-testid="icon" />}
        title="에이전트가 없습니다"
        description="첫 AI 에이전트를 만들어 보세요"
        action={<button>새 에이전트 만들기</button>}
      >
        <div data-testid="extra" />
      </EmptyState>,
    );
    expect(screen.getByRole('heading', { level: 2, name: '에이전트가 없습니다' })).toBeInTheDocument();
    expect(screen.getByText('첫 AI 에이전트를 만들어 보세요')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '새 에이전트 만들기' })).toBeInTheDocument();
    expect(screen.getByTestId('extra')).toBeInTheDocument();
    expect(screen.getByTestId('icon').parentElement!.className).toContain('rounded-full');
  });

  it('iconUnstyled이면 원형 배경 없이 배치한다', () => {
    render(<EmptyState icon={<img alt="로고" src="/logo.png" />} iconUnstyled title="제목" />);
    expect(screen.getByRole('img', { name: '로고' }).parentElement!.className).not.toContain('rounded-full');
  });

  it('title만으로도 렌더링된다', () => {
    render(<EmptyState title="조건에 맞는 작업이 없습니다" />);
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('조건에 맞는 작업이 없습니다');
  });
});
