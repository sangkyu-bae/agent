// jobs-page-revamp Design §8.3 — JobsPage 단위 (훅 모킹: 기존 선례 유지)
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import JobsPage from './index';
import type { JobHistoryItem, MySchedule } from '@/types/backgroundJob';

const mocks = vi.hoisted(() => ({
  useJobHistory: vi.fn(),
  useMySchedules: vi.fn(),
  useToggleScheduleEnabled: vi.fn(),
  useDeleteSchedule: vi.fn(),
  useMarkSeen: vi.fn(),
  useDeleteJob: vi.fn(),
  useCleanupJobs: vi.fn(),
  invalidateUnseenCount: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('@/hooks/useBackgroundJobs', () => ({
  useJobHistory: mocks.useJobHistory,
  useMySchedules: mocks.useMySchedules,
  invalidateMySchedules: vi.fn(),
  invalidateUnseenCount: mocks.invalidateUnseenCount,
  useMarkSeen: mocks.useMarkSeen,
  useDeleteJob: mocks.useDeleteJob,
  useCleanupJobs: mocks.useCleanupJobs,
  extractJobError: (e: unknown) => (e as Error)?.message ?? '오류',
}));

vi.mock('@/hooks/useAgentSchedules', () => ({
  useToggleScheduleEnabled: mocks.useToggleScheduleEnabled,
  useDeleteSchedule: mocks.useDeleteSchedule,
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

const item = (overrides: Partial<JobHistoryItem> = {}): JobHistoryItem => ({
  id: 'j1',
  type: 'manual',
  occurred_at: '2026-09-03T10:17:00',
  title: '시장 조사해줘',
  status: 'success',
  agent_id: '630b99b4-aaaa-bbbb-cccc-ddddeeeeffff',
  agent_name: '리서치 봇',
  session_id: 'sess-1',
  error_message: null,
  seen_at: null,
  started_at: '2026-09-03T10:17:02',
  finished_at: '2026-09-03T10:17:44',
  deletable: true,
  ...overrides,
});

const schedule = (overrides: Partial<MySchedule> = {}): MySchedule => ({
  id: 's1',
  agent_id: 'a1',
  agent_name: '리서치 봇',
  name: '아침 요약',
  spec: { schedule_type: 'daily', time_of_day: '09:00' },
  instruction: '오늘 뉴스 요약해줘',
  enabled: true,
  timezone: 'Asia/Seoul',
  next_run_at: '2026-09-04T00:00:00',
  last_run_at: null,
  ...overrides,
});

const mutationStub = () => ({
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  error: null as Error | null,
});

let deleteMutation: ReturnType<typeof mutationStub>;
let cleanupMutation: ReturnType<typeof mutationStub>;
let markSeenMutation: { mutate: ReturnType<typeof vi.fn> };
let toggleMutation: ReturnType<typeof mutationStub>;
let deleteScheduleMutation: ReturnType<typeof mutationStub>;
let refetch: ReturnType<typeof vi.fn>;

const setHistory = (items: JobHistoryItem[], total = items.length) => {
  mocks.useJobHistory.mockReturnValue({
    data: { items, total },
    isLoading: false,
    refetch,
  });
};

beforeEach(() => {
  refetch = vi.fn();
  deleteMutation = mutationStub();
  cleanupMutation = mutationStub();
  markSeenMutation = { mutate: vi.fn() };
  setHistory([item()]);
  toggleMutation = mutationStub();
  deleteScheduleMutation = mutationStub();
  mocks.useMySchedules.mockReturnValue({
    data: [schedule()],
    isLoading: false,
  });
  mocks.useToggleScheduleEnabled.mockReturnValue(toggleMutation);
  mocks.useDeleteSchedule.mockReturnValue(deleteScheduleMutation);
  mocks.useMarkSeen.mockReturnValue(markSeenMutation);
  mocks.useDeleteJob.mockReturnValue(deleteMutation);
  mocks.useCleanupJobs.mockReturnValue(cleanupMutation);
});

afterEach(() => {
  vi.clearAllMocks();
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <JobsPage />
    </MemoryRouter>,
  );

/** 마지막으로 useJobHistory 에 전달된 조회 파라미터 */
const lastParams = () =>
  mocks.useJobHistory.mock.calls[mocks.useJobHistory.mock.calls.length - 1][0];

const filterGroup = (name: string) => screen.getByRole('group', { name });

describe('JobsPage — 작업 기록 탭 (Design §5.4)', () => {
  it('헤더·필터·테이블 열을 렌더한다', () => {
    renderPage();
    expect(screen.getByText('백그라운드 작업')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '정리' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '새로고침' })).toBeInTheDocument();
    for (const name of ['상태 필터', '유형 필터', '기간 필터']) {
      expect(filterGroup(name)).toBeInTheDocument();
    }
    for (const header of ['시간', '제목', '상태', '에이전트']) {
      expect(
        screen.getByRole('columnheader', { name: header }),
      ).toBeInTheDocument();
    }
  });

  it('행에 시간·제목·상태·에이전트를 표시한다', () => {
    setHistory([item({ status: 'failed', error_message: '도구 호출 실패' })]);
    renderPage();
    expect(screen.getByText('2026-09-03 19:17')).toBeInTheDocument();
    expect(screen.getByText('시장 조사해줘')).toBeInTheDocument();
    expect(screen.getByText('실패')).toBeInTheDocument();
    expect(screen.getByText('리서치 봇')).toBeInTheDocument();
    expect(screen.getByText('도구 호출 실패')).toBeInTheDocument();
  });

  it('에이전트명이 없으면 id 앞 8자로 대체한다', () => {
    setHistory([item({ agent_name: null })]);
    renderPage();
    expect(screen.getByText('630b99b4')).toBeInTheDocument();
  });

  it('새로고침 클릭 시 목록과 미확인 수를 함께 재조회한다 (FR-13)', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '새로고침' }));
    expect(refetch).toHaveBeenCalled();
    // 배지가 15초 폴링 주기까지 옛 값을 유지하면 안 된다
    expect(mocks.invalidateUnseenCount).toHaveBeenCalled();
  });

  it('행 클릭 시 seen 처리 후 세션 딥링크로 이동한다', async () => {
    renderPage();
    await userEvent.click(screen.getByText('시장 조사해줘'));
    expect(markSeenMutation.mutate).toHaveBeenCalledWith({ jobId: 'j1' });
    expect(mocks.navigate).toHaveBeenCalledWith(
      '/chatpage?agentId=630b99b4-aaaa-bbbb-cccc-ddddeeeeffff&sessionId=sess-1',
    );
  });

  it('스케줄 행 클릭은 seen 처리를 하지 않는다', async () => {
    setHistory([
      item({ id: 'r1', type: 'schedule', title: '아침 요약', deletable: false }),
    ]);
    renderPage();
    await userEvent.click(screen.getByText('아침 요약'));
    expect(markSeenMutation.mutate).not.toHaveBeenCalled();
  });

  it('결과가 없으면 빈 상태 문구를 표시한다', () => {
    setHistory([], 0);
    renderPage();
    expect(screen.getByText('조건에 맞는 작업이 없습니다')).toBeInTheDocument();
  });
});

describe('JobsPage — 필터 (FR-07~09)', () => {
  it('완료됨 필터 클릭 시 status=done 으로 재조회한다', async () => {
    renderPage();
    await userEvent.click(within(filterGroup('상태 필터')).getByText('완료됨'));
    expect(lastParams()).toEqual(
      expect.objectContaining({ status: 'done', offset: 0 }),
    );
  });

  it('유형·기간 필터도 파라미터로 전달된다', async () => {
    renderPage();
    await userEvent.click(within(filterGroup('유형 필터')).getByText('수동'));
    await userEvent.click(within(filterGroup('기간 필터')).getByText('오늘'));
    expect(lastParams()).toEqual(
      expect.objectContaining({ type: 'manual', period: 'today' }),
    );
  });

  it('필터를 바꾸면 첫 페이지로 되돌린다', async () => {
    setHistory([item()], 60);
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '다음 페이지' }));
    expect(lastParams().offset).toBe(20);
    await userEvent.click(within(filterGroup('상태 필터')).getByText('진행중'));
    expect(lastParams().offset).toBe(0);
  });

  it('선택된 필터 버튼만 눌린 상태로 표시한다', async () => {
    renderPage();
    expect(within(filterGroup('상태 필터')).getByText('전체')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await userEvent.click(within(filterGroup('상태 필터')).getByText('완료됨'));
    expect(within(filterGroup('상태 필터')).getByText('완료됨')).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });
});

describe('JobsPage — 삭제·정리 (FR-03~05, FR-11)', () => {
  it('스케줄 실행 행에는 휴지통을 노출하지 않는다', () => {
    setHistory([
      item({ id: 'r1', type: 'schedule', title: '아침 요약', deletable: false }),
    ]);
    renderPage();
    expect(
      screen.queryByRole('button', { name: '아침 요약 삭제' }),
    ).not.toBeInTheDocument();
  });

  it('수동 작업 행에는 휴지통을 노출한다', () => {
    renderPage();
    expect(
      screen.getByRole('button', { name: '시장 조사해줘 삭제' }),
    ).toBeInTheDocument();
  });

  it('휴지통 → 확인 시 삭제를 호출한다', async () => {
    renderPage();
    await userEvent.click(
      screen.getByRole('button', { name: '시장 조사해줘 삭제' }),
    );
    await userEvent.click(screen.getByRole('button', { name: '삭제' }));
    expect(deleteMutation.mutate).toHaveBeenCalledWith(
      { jobId: 'j1' },
      expect.anything(),
    );
  });

  it('휴지통 → 취소 시 삭제하지 않는다', async () => {
    renderPage();
    await userEvent.click(
      screen.getByRole('button', { name: '시장 조사해줘 삭제' }),
    );
    await userEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(deleteMutation.mutate).not.toHaveBeenCalled();
  });

  it('삭제 실패(409) 시 에러 메시지를 보여준다', async () => {
    deleteMutation.isError = true;
    deleteMutation.error = new Error('진행 중인 작업은 삭제할 수 없습니다');
    renderPage();
    await userEvent.click(
      screen.getByRole('button', { name: '시장 조사해줘 삭제' }),
    );
    expect(
      screen.getByText('진행 중인 작업은 삭제할 수 없습니다'),
    ).toBeInTheDocument();
  });

  it('정리 → 확인 시 일괄 정리를 호출한다', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '정리' }));
    expect(
      screen.getByText(/완료·실패한 작업을 모두 정리합니다/),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '정리하기' }));
    expect(cleanupMutation.mutate).toHaveBeenCalled();
  });
});

describe('JobsPage — 페이지네이션 (FR-14)', () => {
  it('total 기준으로 페이지 수를 표시한다', () => {
    setHistory([item()], 45);
    renderPage();
    expect(screen.getByText('1 / 3 페이지')).toBeInTheDocument();
  });

  it('첫 페이지에서 이전 버튼이 비활성이다', () => {
    setHistory([item()], 45);
    renderPage();
    expect(screen.getByRole('button', { name: '이전 페이지' })).toBeDisabled();
  });

  it('마지막 페이지에서 다음 버튼이 비활성이다', () => {
    setHistory([item()], 15);
    renderPage();
    expect(screen.getByRole('button', { name: '다음 페이지' })).toBeDisabled();
  });

  it('다음 페이지 클릭 시 offset 이 증가한다', async () => {
    setHistory([item()], 45);
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '다음 페이지' }));
    expect(lastParams().offset).toBe(20);
    expect(screen.getByText('2 / 3 페이지')).toBeInTheDocument();
  });
});

describe('JobsPage — 스케줄 작업 탭 (FR-15)', () => {
  const openScheduleTab = async () => {
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '스케줄 작업' }));
  };

  it('탭 전환 시 스케줄 정의 목록을 보여준다', async () => {
    await openScheduleTab();
    expect(screen.getByText('아침 요약')).toBeInTheDocument();
    for (const header of ['스케줄명', '주기', '다음 실행', '에이전트', '활성']) {
      expect(
        screen.getByRole('columnheader', { name: header }),
      ).toBeInTheDocument();
    }
    // 작업 기록 탭의 필터는 사라진다
    expect(
      screen.queryByRole('group', { name: '상태 필터' }),
    ).not.toBeInTheDocument();
  });

  it('비활성 스케줄은 다음 실행을 표시하지 않는다', async () => {
    mocks.useMySchedules.mockReturnValue({
      data: [schedule({ enabled: false })],
      isLoading: false,
    });
    await openScheduleTab();
    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('활성 토글 시 반대 값으로 갱신을 요청한다', async () => {
    await openScheduleTab();
    await userEvent.click(screen.getByRole('switch'));
    expect(toggleMutation.mutate).toHaveBeenCalledWith(
      { agentId: 'a1', scheduleId: 's1', enabled: false },
      expect.anything(),
    );
  });

  it('스케줄 삭제 → 확인 시 삭제를 호출한다', async () => {
    await openScheduleTab();
    await userEvent.click(
      screen.getByRole('button', { name: '아침 요약 삭제' }),
    );
    await userEvent.click(screen.getByRole('button', { name: '스케줄 삭제' }));
    expect(deleteScheduleMutation.mutate).toHaveBeenCalledWith(
      { agentId: 'a1', scheduleId: 's1' },
      expect.anything(),
    );
  });

  it('스케줄 삭제 → 취소 시 삭제하지 않는다', async () => {
    await openScheduleTab();
    await userEvent.click(
      screen.getByRole('button', { name: '아침 요약 삭제' }),
    );
    await userEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(deleteScheduleMutation.mutate).not.toHaveBeenCalled();
  });

  it('스케줄이 없으면 빈 상태 문구를 표시한다', async () => {
    mocks.useMySchedules.mockReturnValue({ data: [], isLoading: false });
    await openScheduleTab();
    expect(screen.getByText('등록된 스케줄이 없습니다')).toBeInTheDocument();
  });
});
