// approval-gate Design §5.4 — 승인 대기 탭 UI 체크리스트 검증
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ApprovalTable from './ApprovalTable';
import type { ApprovalItem } from '@/types/approval';

const mocks = vi.hoisted(() => ({
  useApprovals: vi.fn(),
  approve: vi.fn(),
  reject: vi.fn(),
  markSeen: vi.fn(),
}));

vi.mock('@/hooks/useApprovals', () => ({
  useApprovals: mocks.useApprovals,
  useApproveApproval: () => ({ mutateAsync: mocks.approve }),
  useRejectApproval: () => ({ mutateAsync: mocks.reject }),
  useMarkApprovalSeen: () => ({ mutate: mocks.markSeen }),
  extractApprovalError: (e: unknown) => (e as Error)?.message ?? '오류',
}));

const item = (over: Partial<ApprovalItem> = {}): ApprovalItem => ({
  id: 'ap1',
  agent_id: 'ag1',
  agent_name: '금리 변경 에이전트',
  tool_id: 'rate_update',
  draft_preview: '기준금리를 3.50% → 3.25%로 변경합니다',
  status: 'pending',
  execute_after: null,
  expires_at: new Date(Date.now() + 86_400_000).toISOString(),
  seen_at: null,
  created_at: new Date().toISOString(),
  ...over,
});

const setList = (
  items: ApprovalItem[],
  extra: Record<string, unknown> = {},
) =>
  mocks.useApprovals.mockReturnValue({
    data: { data: items, pagination: { total: items.length, page: 1, size: 20 } },
    isLoading: false,
    isError: false,
    ...extra,
  });

beforeEach(() => {
  vi.clearAllMocks();
  mocks.approve.mockResolvedValue({ id: 'ap1', status: 'executed', message: '집행되었습니다.' });
  mocks.reject.mockResolvedValue({ id: 'ap1', status: 'rejected', message: '거절 처리되었습니다.' });
});

describe('ApprovalTable — 목록 표시', () => {
  it('에이전트명과 도구 ID를 보여준다', () => {
    setList([item()]);
    render(<ApprovalTable />);
    expect(screen.getByText('금리 변경 에이전트')).toBeInTheDocument();
    expect(screen.getByText(/rate_update/)).toBeInTheDocument();
  });

  it('상태 배지를 보여준다', () => {
    setList([item()]);
    render(<ApprovalTable />);
    expect(screen.getByText('승인 대기')).toBeInTheDocument();
  });

  it('미확인 점을 표시한다', () => {
    setList([item({ seen_at: null })]);
    render(<ApprovalTable />);
    expect(screen.getByLabelText('미확인')).toBeInTheDocument();
  });

  it('확인한 건은 미확인 점이 없다', () => {
    setList([item({ seen_at: new Date().toISOString() })]);
    render(<ApprovalTable />);
    expect(screen.queryByLabelText('미확인')).not.toBeInTheDocument();
  });

  it('초안 미리보기를 보여준다', () => {
    setList([item()]);
    render(<ApprovalTable />);
    expect(screen.getByText(/기준금리를 3.50%/)).toBeInTheDocument();
  });

  it('집행 예정 시각이 있으면 표시한다', () => {
    setList([item({ status: 'scheduled', execute_after: '2026-09-22T00:00:00' })]);
    render(<ApprovalTable />);
    // '집행 예정' 은 상태 배지와 정의목록 dt 두 곳에 나온다 — dt 를 특정한다.
    const labels = screen.getAllByText('집행 예정');
    expect(labels.some((el) => el.tagName === 'DT')).toBe(true);
  });

  it('만료 잔여 시간을 보여준다', () => {
    setList([item()]);
    render(<ApprovalTable />);
    expect(screen.getByText(/남음/)).toBeInTheDocument();
  });

  it('빈 목록이면 안내 문구를 보여준다', () => {
    setList([]);
    render(<ApprovalTable />);
    expect(screen.getByText('승인 대기 중인 작업이 없습니다.')).toBeInTheDocument();
  });

  it('로딩 중 문구를 보여준다', () => {
    mocks.useApprovals.mockReturnValue({ data: undefined, isLoading: true, isError: false });
    render(<ApprovalTable />);
    expect(screen.getByText('불러오는 중…')).toBeInTheDocument();
  });

  it('오류 시 alert 를 보여준다', () => {
    mocks.useApprovals.mockReturnValue({ data: undefined, isLoading: false, isError: true });
    render(<ApprovalTable />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});

describe('ApprovalTable — 상태 필터', () => {
  it('필터 버튼 4종을 보여준다', () => {
    setList([]);
    render(<ApprovalTable />);
    ['전체', '대기', '예약됨', '완료'].forEach((label) =>
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument(),
    );
  });

  it('필터를 바꾸면 해당 상태로 조회한다', async () => {
    setList([]);
    render(<ApprovalTable />);
    await userEvent.click(screen.getByRole('button', { name: '완료' }));
    await waitFor(() =>
      expect(mocks.useApprovals).toHaveBeenCalledWith(
        expect.objectContaining({
          statuses: ['executed', 'rejected', 'expired', 'failed'],
        }),
      ),
    );
  });
});

describe('ApprovalTable — 승인', () => {
  it('승인 버튼을 누르면 mutate 한다', async () => {
    setList([item()]);
    render(<ApprovalTable />);
    await userEvent.click(screen.getByRole('button', { name: '승인' }));
    expect(mocks.approve).toHaveBeenCalledWith({ approvalId: 'ap1' });
  });

  it('성공 메시지를 status 로 노출한다', async () => {
    setList([item()]);
    render(<ApprovalTable />);
    await userEvent.click(screen.getByRole('button', { name: '승인' }));
    expect(await screen.findByRole('status')).toHaveTextContent('집행되었습니다.');
  });

  it('409 등 오류 메시지도 status 로 노출한다', async () => {
    setList([item()]);
    mocks.approve.mockRejectedValue(new Error('이미 처리된 요청입니다.'));
    render(<ApprovalTable />);
    await userEvent.click(screen.getByRole('button', { name: '승인' }));
    expect(await screen.findByRole('status')).toHaveTextContent('이미 처리된 요청');
  });

  it('종료 상태에는 액션 버튼이 없다', () => {
    setList([item({ status: 'executed' })]);
    render(<ApprovalTable />);
    expect(screen.queryByRole('button', { name: '승인' })).not.toBeInTheDocument();
  });

  it('예약된 건도 재결정 대상이 아니다', () => {
    setList([item({ status: 'scheduled' })]);
    render(<ApprovalTable />);
    expect(screen.queryByRole('button', { name: '승인' })).not.toBeInTheDocument();
  });
});

describe('ApprovalTable — 거절', () => {
  it('거절을 누르면 사유 다이얼로그가 열린다', async () => {
    setList([item()]);
    render(<ApprovalTable />);
    await userEvent.click(screen.getByRole('button', { name: '거절' }));
    expect(screen.getByRole('dialog', { name: '거절 사유 입력' })).toBeInTheDocument();
  });

  it('사유가 비면 제출 버튼이 비활성이다', async () => {
    setList([item()]);
    render(<ApprovalTable />);
    await userEvent.click(screen.getByRole('button', { name: '거절' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByRole('button', { name: '거절' })).toBeDisabled();
  });

  it('사유를 입력하고 제출하면 mutate 한다', async () => {
    setList([item()]);
    render(<ApprovalTable />);
    await userEvent.click(screen.getByRole('button', { name: '거절' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('거절 사유'), '한도 초과');
    await userEvent.click(within(dialog).getByRole('button', { name: '거절' }));
    await waitFor(() =>
      expect(mocks.reject).toHaveBeenCalledWith({
        approvalId: 'ap1',
        reason: '한도 초과',
      }),
    );
  });
});

describe('ApprovalTable — 확인 처리', () => {
  it('초안을 펼치면 미확인 건을 seen 처리한다', async () => {
    setList([item({ seen_at: null })]);
    render(<ApprovalTable />);
    await userEvent.click(screen.getByLabelText('초안 전문 보기'));
    expect(mocks.markSeen).toHaveBeenCalledWith('ap1');
  });

  it('이미 확인한 건은 다시 seen 처리하지 않는다', async () => {
    setList([item({ seen_at: new Date().toISOString() })]);
    render(<ApprovalTable />);
    await userEvent.click(screen.getByLabelText('초안 전문 보기'));
    expect(mocks.markSeen).not.toHaveBeenCalled();
  });
});

describe('ApprovalTable — 예약 시각 표시 (Check G12)', () => {
  it('예약 승인은 UTC 시각을 로컬 시각으로 안내한다', async () => {
    setList([item()]);
    // KST 00:00 == UTC 15:00 전날 — 서버는 +00:00 을 명시해 보낸다.
    mocks.approve.mockResolvedValue({
      id: 'ap1', status: 'scheduled',
      execute_after: '2026-09-21T15:00:00+00:00',
      message: '승인되었습니다. 예약된 시각에 집행됩니다.',
    });
    render(<ApprovalTable />);
    await userEvent.click(screen.getByRole('button', { name: '승인' }));
    const expected = new Date('2026-09-21T15:00:00+00:00').toLocaleString('ko-KR', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
    expect(await screen.findByRole('status')).toHaveTextContent(
      `${expected}에 집행 예정입니다.`,
    );
  });
});
