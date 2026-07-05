import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import AgentSkillPanel from './AgentSkillPanel';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('AgentSkillPanel (toggle)', () => {
  it('스킬 후보를 토글 카드로 표시하고 선택 개수를 카운트한다', async () => {
    render(<AgentSkillPanel selectedIds={['skill-1']} onToggle={() => {}} />, {
      wrapper: createWrapper(),
    });

    await waitFor(() =>
      expect(screen.getByText('환율 계산기')).toBeInTheDocument(),
    );
    // 1/3 카운터
    expect(screen.getByText('1/3')).toBeInTheDocument();
    // python script → 미실행 경고
    expect(screen.getByText('⚠ script 미실행')).toBeInTheDocument();
    // script 미실행 안내
    expect(screen.getByText(/script는 현재 실행되지 않습니다/)).toBeInTheDocument();
    // 선택된 스킬 스위치는 on
    expect(screen.getByRole('switch', { name: '환율 계산기 토글' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
  });

  it('토글 클릭 시 onToggle을 호출한다', async () => {
    const onToggle = vi.fn();
    render(<AgentSkillPanel selectedIds={[]} onToggle={onToggle} />, {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(screen.getByText('공용 요약기')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('switch', { name: '공용 요약기 토글' }));
    expect(onToggle).toHaveBeenCalledWith('skill-2');
  });

  it('최대 개수(3) 도달 시 미선택 스킬 스위치가 비활성화된다', async () => {
    render(
      <AgentSkillPanel selectedIds={['a', 'b', 'c']} onToggle={() => {}} />,
      { wrapper: createWrapper() },
    );
    expect(screen.getByText('3/3')).toBeInTheDocument();
    // 목록 로드 후 — 후보(환율 계산기)는 selectedIds에 없으므로 비활성
    await waitFor(() =>
      expect(screen.getByText('환율 계산기')).toBeInTheDocument(),
    );
    expect(screen.getByRole('switch', { name: '환율 계산기 토글' })).toBeDisabled();
  });
});
