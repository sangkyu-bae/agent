// background-jobs Design §6 — NotificationBell 단위 (훅 모킹)
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import NotificationBell from './NotificationBell';
import type { JobHistoryItem } from '@/types/backgroundJob';

const mocks = vi.hoisted(() => ({
  useUnseenCount: vi.fn(),
  useJobHistory: vi.fn(),
  useMarkSeen: vi.fn(),
  useMarkAllSeen: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('@/hooks/useBackgroundJobs', () => ({
  useUnseenCount: mocks.useUnseenCount,
  useJobHistory: mocks.useJobHistory,
  useMarkSeen: mocks.useMarkSeen,
  useMarkAllSeen: mocks.useMarkAllSeen,
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

const job = (overrides: Partial<JobHistoryItem> = {}): JobHistoryItem => ({
  id: 'j1',
  type: 'manual',
  occurred_at: '2026-08-11T02:00:00',
  title: '보고서 만들어줘',
  status: 'success',
  agent_id: 'a1',
  agent_name: '리서치 봇',
  session_id: 'sess-1',
  error_message: null,
  seen_at: null,
  started_at: '2026-08-11T02:00:05',
  finished_at: '2026-08-11T02:01:05',
  deletable: true,
  ...overrides,
});

/** jobs-page-revamp: 목록 응답이 {items,total} 로 바뀌었다 */
const listResult = (items: JobHistoryItem[]) => ({
  data: { items, total: items.length },
});

let markSeenMutation: { mutate: ReturnType<typeof vi.fn> };
let markAllSeenMutation: { mutate: ReturnType<typeof vi.fn> };

beforeEach(() => {
  markSeenMutation = { mutate: vi.fn() };
  markAllSeenMutation = { mutate: vi.fn() };
  mocks.useUnseenCount.mockReturnValue({ data: { count: 2 } });
  mocks.useJobHistory.mockReturnValue(listResult([job()]));
  mocks.useMarkSeen.mockReturnValue(markSeenMutation);
  mocks.useMarkAllSeen.mockReturnValue(markAllSeenMutation);
});

afterEach(() => {
  vi.restoreAllMocks();
  mocks.navigate.mockReset();
});

const renderBell = () =>
  render(
    <MemoryRouter>
      <NotificationBell />
    </MemoryRouter>,
  );

describe('NotificationBell (D11)', () => {
  it('미확인 카운트를 배지로 표시한다', () => {
    renderBell();
    expect(screen.getByTestId('bell-badge')).toHaveTextContent('2');
  });

  it('카운트 0이면 배지를 숨긴다', () => {
    mocks.useUnseenCount.mockReturnValue({ data: { count: 0 } });
    renderBell();
    expect(screen.queryByTestId('bell-badge')).not.toBeInTheDocument();
  });

  it('10건 이상이면 9+로 축약한다', () => {
    mocks.useUnseenCount.mockReturnValue({ data: { count: 12 } });
    renderBell();
    expect(screen.getByTestId('bell-badge')).toHaveTextContent('9+');
  });

  it('벨 클릭 시 최근 작업 드롭다운을 연다', async () => {
    renderBell();
    await userEvent.click(
      screen.getByRole('button', { name: '백그라운드 작업 알림' }),
    );
    expect(screen.getByText('보고서 만들어줘')).toBeInTheDocument();
    expect(screen.getByText('새 결과')).toBeInTheDocument();
  });

  it('모두 확인 클릭 시 일괄 확인을 호출한다', async () => {
    renderBell();
    await userEvent.click(
      screen.getByRole('button', { name: '백그라운드 작업 알림' }),
    );
    await userEvent.click(screen.getByRole('button', { name: '모두 확인' }));
    expect(markAllSeenMutation.mutate).toHaveBeenCalled();
  });

  it('항목 클릭 시 seen 처리 후 해당 세션 딥링크로 이동한다', async () => {
    renderBell();
    await userEvent.click(
      screen.getByRole('button', { name: '백그라운드 작업 알림' }),
    );
    await userEvent.click(screen.getByText('보고서 만들어줘'));
    expect(markSeenMutation.mutate).toHaveBeenCalledWith({ jobId: 'j1' });
    expect(mocks.navigate).toHaveBeenCalledWith(
      '/chatpage?agentId=a1&sessionId=sess-1',
    );
  });

  it('세션 없는 항목 클릭 시 작업함으로 이동한다', async () => {
    mocks.useJobHistory.mockReturnValue(listResult([job({ session_id: null })]));
    renderBell();
    await userEvent.click(
      screen.getByRole('button', { name: '백그라운드 작업 알림' }),
    );
    await userEvent.click(screen.getByText('보고서 만들어줘'));
    expect(mocks.navigate).toHaveBeenCalledWith('/jobs');
  });

  it('드롭다운에는 완료/실패만 표시한다 — 진행중 혼입 방지', async () => {
    mocks.useJobHistory.mockReturnValue(
      listResult([
        job({ id: 'j-running', status: 'running', title: '진행중 작업' }),
        job({ id: 'j-done', title: '완료된 작업' }),
      ]),
    );
    renderBell();
    await userEvent.click(
      screen.getByRole('button', { name: '백그라운드 작업 알림' }),
    );
    expect(screen.getByText('완료된 작업')).toBeInTheDocument();
    expect(screen.queryByText('진행중 작업')).not.toBeInTheDocument();
  });

  it('모두 확인 후 카운트가 0이 되면 배지가 사라진다', async () => {
    const { rerender } = renderBell();
    await userEvent.click(
      screen.getByRole('button', { name: '백그라운드 작업 알림' }),
    );
    await userEvent.click(screen.getByRole('button', { name: '모두 확인' }));
    expect(markAllSeenMutation.mutate).toHaveBeenCalled();
    // 일괄 확인 → unseenCount invalidate 재조회가 0을 반환하는 상황
    mocks.useUnseenCount.mockReturnValue({ data: { count: 0 } });
    rerender(
      <MemoryRouter>
        <NotificationBell />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('bell-badge')).not.toBeInTheDocument();
  });

  it('드롭다운은 수동 작업만 요청한다 — 배지(unseen-count)와 목록 일치', () => {
    renderBell();
    expect(mocks.useJobHistory).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'manual' }),
    );
  });

  it('작업이 없으면 빈 상태 문구를 표시한다', async () => {
    mocks.useJobHistory.mockReturnValue(listResult([]));
    renderBell();
    await userEvent.click(
      screen.getByRole('button', { name: '백그라운드 작업 알림' }),
    );
    expect(
      screen.getByText('등록된 백그라운드 작업이 없습니다'),
    ).toBeInTheDocument();
  });
});
