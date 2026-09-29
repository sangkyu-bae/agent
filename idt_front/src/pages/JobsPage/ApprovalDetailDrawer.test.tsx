// approval-edit-before-approve Design §5.4 / §8.3 (F3~F7) — 승인 상세 드로어
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ApprovalDetailDrawer from './ApprovalDetailDrawer';
import type { ApprovalDetail } from '@/types/approval';
import { APPROVAL_NOT_EDITABLE_HINT } from '@/types/approval';

const mocks = vi.hoisted(() => ({
  useApprovalDetail: vi.fn(),
  approve: vi.fn(),
}));

vi.mock('@/hooks/useApprovals', () => ({
  useApprovalDetail: mocks.useApprovalDetail,
  useApproveApproval: () => ({ mutateAsync: mocks.approve }),
  extractApprovalError: (e: unknown) => (e as Error)?.message ?? '오류',
}));

const detail = (over: Partial<ApprovalDetail> = {}): ApprovalDetail => ({
  id: 'ap1',
  agent_id: 'ag1',
  agent_name: '메일 에이전트',
  tool_id: 'mcp:mail:send',
  draft_preview: '안녕하세요 본문',
  status: 'pending',
  execute_after: null,
  expires_at: new Date(Date.now() + 86_400_000).toISOString(),
  seen_at: null,
  created_at: new Date().toISOString(),
  edited: false,
  draft: '안녕하세요 본문',
  tool_args: { arguments: {} },
  worker_id: 'w1',
  decided_by: null,
  decided_at: null,
  decision_reason: null,
  executed_at: null,
  error_message: null,
  editable: true,
  body_key: 'body',
  editable_keys: ['to', 'body'],
  display_args: { to: 'a@x.com', body: '안녕하세요 본문', priority: 1 },
  original_tool_args: null,
  edited_by: null,
  edited_at: null,
  ...over,
});

const setDetail = (d: ApprovalDetail | undefined, extra = {}) =>
  mocks.useApprovalDetail.mockReturnValue({
    data: d,
    isLoading: false,
    isError: false,
    ...extra,
  });

const renderDrawer = (props: Partial<Parameters<typeof ApprovalDetailDrawer>[0]> = {}) => {
  const onDone = vi.fn();
  const onReject = vi.fn();
  const onClose = vi.fn();
  render(
    <ApprovalDetailDrawer
      approvalId="ap1"
      onClose={onClose}
      onDone={onDone}
      onReject={onReject}
      {...props}
    />,
  );
  return { onDone, onReject, onClose };
};

beforeEach(() => {
  vi.clearAllMocks();
  mocks.approve.mockResolvedValue({
    id: 'ap1', status: 'executed', execute_after: null, message: '수정본으로 집행되었습니다.',
  });
});

describe('ApprovalDetailDrawer — 보기', () => {
  it('초안 전문과 호출 인자를 보여준다 (F3)', () => {
    setDetail(detail());
    renderDrawer();
    expect(screen.getByText('안녕하세요 본문')).toBeInTheDocument();
    expect(screen.getByText('a@x.com')).toBeInTheDocument();
    expect(screen.getByText('본문 (body)')).toBeInTheDocument();
  });

  it('문자열이 아닌 인자는 수정 불가로 표시한다', () => {
    setDetail(detail());
    renderDrawer();
    const row = screen.getByText('priority').closest('tr')!;
    expect(within(row).getByText('수정 불가')).toBeInTheDocument();
  });

  it('수정된 건은 배지와 원본 보기를 제공한다', async () => {
    setDetail(detail({
      edited: true,
      original_tool_args: { to: 'old@x.com', body: '옛 본문' },
      edited_by: 'u1',
      edited_at: new Date().toISOString(),
      status: 'executed',
    }));
    renderDrawer();
    expect(screen.getByText('수정됨')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /원본 보기/ }));
    expect(screen.getByText(/old@x\.com/)).toBeInTheDocument();
  });

  it('편집 불가 건은 수정 버튼이 비활성이고 안내한다 (F4)', () => {
    setDetail(detail({ editable: false, body_key: null, editable_keys: [] }));
    renderDrawer();
    expect(screen.getByRole('button', { name: '수정' })).toBeDisabled();
    expect(screen.getByText(APPROVAL_NOT_EDITABLE_HINT)).toBeInTheDocument();
  });

  it('처리된 건은 결정 버튼을 보여주지 않는다', () => {
    setDetail(detail({ status: 'executed' }));
    renderDrawer();
    expect(screen.queryByRole('button', { name: '승인' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '수정' })).not.toBeInTheDocument();
  });

  it('일반 승인은 수정본 없이 호출한다', async () => {
    setDetail(detail());
    const { onDone } = renderDrawer();
    await userEvent.click(screen.getByRole('button', { name: '승인' }));
    expect(mocks.approve).toHaveBeenCalledWith({ approvalId: 'ap1' });
    expect(onDone).toHaveBeenCalled();
  });

  it('거절은 부모에게 위임한다', async () => {
    setDetail(detail());
    const { onReject } = renderDrawer();
    await userEvent.click(screen.getByRole('button', { name: '거절' }));
    expect(onReject).toHaveBeenCalledWith(expect.objectContaining({ id: 'ap1' }));
  });
});

describe('ApprovalDetailDrawer — 수정 후 승인', () => {
  it('변경 없으면 수정 후 승인이 비활성', async () => {
    setDetail(detail());
    renderDrawer();
    await userEvent.click(screen.getByRole('button', { name: '수정' }));
    expect(screen.getByRole('button', { name: '수정 후 승인' })).toBeDisabled();
  });

  it('바뀐 키만 담아 승인한다 (F5)', async () => {
    setDetail(detail());
    const { onDone } = renderDrawer();
    await userEvent.click(screen.getByRole('button', { name: '수정' }));
    const body = screen.getByLabelText('body');
    await userEvent.clear(body);
    await userEvent.type(body, '수정된 본문');
    expect(body).toHaveAttribute('data-changed', 'true');
    await userEvent.click(screen.getByRole('button', { name: '수정 후 승인' }));
    const dialog = screen.getByRole('dialog', { name: /수정 후 승인/ });
    expect(within(dialog).getByText(/body/)).toBeInTheDocument();
    expect(within(dialog).queryByText(/본문 외 값이 바뀌었습니다/)).not.toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole('button', { name: '수정 후 승인' }));
    expect(mocks.approve).toHaveBeenCalledWith({
      approvalId: 'ap1',
      editedArgs: { body: '수정된 본문' },
    });
    expect(onDone).toHaveBeenCalled();
  });

  it('본문 외 필드를 바꾸면 경고한다 (F6)', async () => {
    setDetail(detail());
    renderDrawer();
    await userEvent.click(screen.getByRole('button', { name: '수정' }));
    const to = screen.getByLabelText('to');
    await userEvent.clear(to);
    await userEvent.type(to, 'z@x.com');
    await userEvent.click(screen.getByRole('button', { name: '수정 후 승인' }));
    const dialog = screen.getByRole('dialog', { name: /수정 후 승인/ });
    expect(within(dialog).getByText(/본문 외 값이 바뀌었습니다/)).toBeInTheDocument();
  });

  it('서버 검증 실패는 드로어에 남아 오류를 보여준다 (F7)', async () => {
    setDetail(detail());
    mocks.approve.mockRejectedValue(new Error('수정할 수 없는 필드입니다: bcc'));
    const { onDone } = renderDrawer();
    await userEvent.click(screen.getByRole('button', { name: '수정' }));
    await userEvent.type(screen.getByLabelText('body'), '!');
    await userEvent.click(screen.getByRole('button', { name: '수정 후 승인' }));
    const dialog = screen.getByRole('dialog', { name: /수정 후 승인/ });
    await userEvent.click(within(dialog).getByRole('button', { name: '수정 후 승인' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('수정할 수 없는 필드입니다: bcc');
    expect(onDone).not.toHaveBeenCalled();
    expect(screen.getByLabelText('body')).toBeInTheDocument();
  });

  it('취소하면 보기 모드로 돌아가고 입력을 버린다', async () => {
    setDetail(detail());
    renderDrawer();
    await userEvent.click(screen.getByRole('button', { name: '수정' }));
    await userEvent.type(screen.getByLabelText('body'), '!');
    await userEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(screen.queryByLabelText('body')).not.toBeInTheDocument();
    expect(screen.getByText('안녕하세요 본문')).toBeInTheDocument();
  });
});
