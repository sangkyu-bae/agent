/**
 * RunListTable unit tests — M5.
 *
 * C1: rows 렌더 + 행 클릭 시 onRowClick(runId) 호출
 * C2: 페이지 버튼 동작 (offset 이동)
 * C3: 빈 결과일 때 안내 문구 표시
 * C4: loading=true 시 스켈레톤 렌더
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RunListTable from './RunListTable';
import type { RunListResponse } from '@/types/agentRunAdmin';

const baseData: RunListResponse = {
  from_dt: null,
  to_dt: null,
  limit: 20,
  offset: 0,
  total: 25,
  rows: [
    {
      id: '11111111-aaaa-bbbb-cccc-000000000001',
      user_id: 'u-1',
      agent_id: 'agent-abcdefg-1',
      conversation_id: 'c-1',
      status: 'SUCCESS',
      started_at: '2026-05-21T03:11:09Z',
      ended_at: '2026-05-21T03:11:21Z',
      latency_ms: 12000,
      total_tokens: 1234,
      total_cost_usd: '0.0123',
      llm_call_count: 2,
      error_message: null,
    },
    {
      id: '22222222-aaaa-bbbb-cccc-000000000002',
      user_id: 'u-2',
      agent_id: 'agent-abcdefg-2',
      conversation_id: 'c-2',
      status: 'FAILED',
      started_at: '2026-05-21T03:10:00Z',
      ended_at: '2026-05-21T03:10:30Z',
      latency_ms: 500,
      total_tokens: 100,
      total_cost_usd: '0.0010',
      llm_call_count: 1,
      error_message: 'some error',
    },
  ],
};

describe('RunListTable', () => {
  it('C1: rows 렌더 + 행 클릭 → onRowClick(runId)', async () => {
    const onRowClick = vi.fn();
    render(
      <RunListTable
        data={baseData}
        onRowClick={onRowClick}
        onPageChange={() => {}}
      />,
    );
    expect(screen.getByText('SUCCESS')).toBeInTheDocument();
    expect(screen.getByText('FAILED')).toBeInTheDocument();
    expect(screen.getByText('$0.0123')).toBeInTheDocument();

    await userEvent.click(screen.getByText('SUCCESS').closest('tr')!);
    expect(onRowClick).toHaveBeenCalledWith(
      '11111111-aaaa-bbbb-cccc-000000000001',
    );
  });

  it('C2: 다음 버튼 클릭 → onPageChange(offset + limit)', async () => {
    const onPageChange = vi.fn();
    render(
      <RunListTable
        data={baseData}
        onRowClick={() => {}}
        onPageChange={onPageChange}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: '다음' }));
    expect(onPageChange).toHaveBeenCalledWith(20);
  });

  it('C3: 빈 rows → 안내 문구', () => {
    render(
      <RunListTable
        data={{ ...baseData, rows: [], total: 0 }}
        onRowClick={() => {}}
        onPageChange={() => {}}
      />,
    );
    expect(screen.getByText(/조건에 맞는 Run이 없습니다/)).toBeInTheDocument();
  });

  it('C4: loading=true → 스켈레톤', () => {
    const { container } = render(
      <RunListTable
        data={undefined}
        loading
        onRowClick={() => {}}
        onPageChange={() => {}}
      />,
    );
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });
});
