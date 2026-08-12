// background-jobs Design §6 — JobsPage 단위 (훅 모킹: WebhookSection 선례)
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import JobsPage from './index';
import type { BackgroundJob, MyScheduleRun } from '@/types/backgroundJob';

const mocks = vi.hoisted(() => ({
  useJobList: vi.fn(),
  useMyScheduleRuns: vi.fn(),
  useMarkSeen: vi.fn(),
  useMarkAllSeen: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('@/hooks/useBackgroundJobs', () => ({
  useJobList: mocks.useJobList,
  useMyScheduleRuns: mocks.useMyScheduleRuns,
  useMarkSeen: mocks.useMarkSeen,
  useMarkAllSeen: mocks.useMarkAllSeen,
}));

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mocks.navigate };
});

const job = (overrides: Partial<BackgroundJob> = {}): BackgroundJob => ({
  id: 'j1',
  agent_id: 'a1',
  agent_name: '리서치 봇',
  source: 'chat',
  query: '시장 조사해줘',
  session_id: 'sess-1',
  run_id: 'run-1',
  status: 'success',
  error_message: null,
  seen_at: null,
  queued_at: '2026-08-11T02:00:00',
  started_at: '2026-08-11T02:00:05',
  finished_at: '2026-08-11T02:01:05',
  ...overrides,
});

const scheduleRun = (
  overrides: Partial<MyScheduleRun> = {},
): MyScheduleRun => ({
  id: 'r1',
  schedule_id: 's1',
  schedule_name: '아침 요약',
  agent_id: 'a1',
  agent_name: '리서치 봇',
  status: 'success',
  scheduled_for: '2026-08-11T00:00:00',
  started_at: '2026-08-11T00:00:05',
  finished_at: '2026-08-11T00:01:00',
  session_id: 'sess-9',
  error_message: null,
  ...overrides,
});

let markSeenMutation: { mutate: ReturnType<typeof vi.fn> };
let markAllSeenMutation: { mutate: ReturnType<typeof vi.fn> };

beforeEach(() => {
  markSeenMutation = { mutate: vi.fn() };
  markAllSeenMutation = { mutate: vi.fn() };
  mocks.useJobList.mockReturnValue({ data: [job()], isLoading: false });
  mocks.useMyScheduleRuns.mockReturnValue({
    data: [scheduleRun()],
    isLoading: false,
  });
  mocks.useMarkSeen.mockReturnValue(markSeenMutation);
  mocks.useMarkAllSeen.mockReturnValue(markAllSeenMutation);
});

afterEach(() => {
  vi.restoreAllMocks();
  mocks.navigate.mockReset();
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <JobsPage />
    </MemoryRouter>,
  );

describe('JobsPage — 요청 작업 탭', () => {
  it('작업 목록을 상태 배지·에이전트명·질문·새 결과 표시와 함께 렌더한다', () => {
    renderPage();
    expect(screen.getByText('시장 조사해줘')).toBeInTheDocument();
    expect(screen.getByText('완료')).toBeInTheDocument();
    expect(screen.getByText('리서치 봇')).toBeInTheDocument();
    expect(screen.getByText('새 결과')).toBeInTheDocument();
  });

  it('실패 작업은 에러 메시지를 표시한다', () => {
    mocks.useJobList.mockReturnValue({
      data: [job({ status: 'failed', error_message: 'LLM 실행 실패' })],
      isLoading: false,
    });
    renderPage();
    expect(screen.getByText('실패')).toBeInTheDocument();
    expect(screen.getByText('LLM 실행 실패')).toBeInTheDocument();
  });

  it('결과 보기 클릭 시 seen 처리 후 해당 세션 딥링크로 이동한다', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '결과 보기' }));
    expect(markSeenMutation.mutate).toHaveBeenCalledWith({ jobId: 'j1' });
    expect(mocks.navigate).toHaveBeenCalledWith(
      '/chatpage?agentId=a1&sessionId=sess-1',
    );
  });

  it('세션 없는 완료 작업은 대화 화면으로만 이동한다', async () => {
    mocks.useJobList.mockReturnValue({
      data: [job({ session_id: null })],
      isLoading: false,
    });
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '결과 보기' }));
    expect(mocks.navigate).toHaveBeenCalledWith('/chatpage');
  });

  it('이미 확인한 작업은 결과 보기 시 seen 재요청하지 않는다', async () => {
    mocks.useJobList.mockReturnValue({
      data: [job({ seen_at: '2026-08-11T03:00:00' })],
      isLoading: false,
    });
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '결과 보기' }));
    expect(markSeenMutation.mutate).not.toHaveBeenCalled();
  });

  it('모두 확인 버튼이 일괄 확인을 호출한다', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '모두 확인' }));
    expect(markAllSeenMutation.mutate).toHaveBeenCalled();
  });

  it('작업이 없으면 빈 상태 문구를 표시한다', () => {
    mocks.useJobList.mockReturnValue({ data: [], isLoading: false });
    renderPage();
    expect(
      screen.getByText('등록된 백그라운드 작업이 없습니다'),
    ).toBeInTheDocument();
  });
});

describe('JobsPage — 스케줄 실행 탭 (D9)', () => {
  it('탭 전환 시 스케줄 실행 이력을 에이전트명과 함께 표시한다', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '스케줄 실행' }));
    expect(screen.getByText('아침 요약')).toBeInTheDocument();
    expect(screen.getByText('리서치 봇')).toBeInTheDocument();
    expect(screen.queryByText('시장 조사해줘')).not.toBeInTheDocument();
  });

  it('결과 보기 클릭 시 해당 세션 딥링크로 이동한다', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '스케줄 실행' }));
    await userEvent.click(screen.getByRole('button', { name: '결과 보기' }));
    expect(mocks.navigate).toHaveBeenCalledWith(
      '/chatpage?agentId=a1&sessionId=sess-9',
    );
  });

  it('스케줄 실행 실패는 에러 메시지를 표시한다', async () => {
    mocks.useMyScheduleRuns.mockReturnValue({
      data: [scheduleRun({ status: 'failed', error_message: '타임아웃' })],
      isLoading: false,
    });
    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '스케줄 실행' }));
    expect(screen.getByText('타임아웃')).toBeInTheDocument();
  });
});
