import { describe, it, expect, vi, beforeAll, beforeEach, afterEach, afterAll } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { queryClient } from '@/lib/queryClient';
import { server } from '@/__tests__/mocks/server';
import {
  resetScheduleStore,
  seedSchedules,
  mockSchedule,
} from '@/__tests__/mocks/handlers';
import SchedulePanel from './SchedulePanel';
import type { StagedSchedule } from '@/types/agentSchedule';

beforeAll(() => server.listen());
beforeEach(() => resetScheduleStore());
afterEach(() => {
  server.resetHandlers();
  queryClient.clear();
});
afterAll(() => server.close());

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

const renderPanel = (props: Partial<Parameters<typeof SchedulePanel>[0]> = {}) => {
  const onStagedAdd = vi.fn();
  const onStagedRemove = vi.fn();
  render(
    <SchedulePanel
      mode="edit"
      agentId="agent-1"
      stagedSchedules={[]}
      onStagedAdd={onStagedAdd}
      onStagedRemove={onStagedRemove}
      {...props}
    />,
    { wrapper },
  );
  return { onStagedAdd, onStagedRemove };
};

const stagedItem: StagedSchedule = {
  localId: 'local-1',
  name: '매일 09:00 실행',
  spec: { schedule_type: 'cron', cron_expr: '0 9 * * *' },
  instruction: '뉴스 요약',
  timezone: 'Asia/Seoul',
  enabled: true,
};

describe('SchedulePanel — edit 모드', () => {
  it('빈 상태를 렌더한다', async () => {
    seedSchedules('agent-1', []);
    renderPanel();
    expect(await screen.findByText('등록된 스케줄이 없습니다')).toBeInTheDocument();
  });

  it('스케줄 카드를 렌더한다 (요약 + 다음 실행)', async () => {
    seedSchedules('agent-1', [mockSchedule()]);
    renderPanel();
    expect(await screen.findByText('매일 09:00 실행')).toBeInTheDocument();
    expect(screen.getByText(/다음 실행:/)).toBeInTheDocument();
  });

  it('폼 제출 시 POST되어 목록에 추가된다', async () => {
    seedSchedules('agent-1', []);
    renderPanel();
    await screen.findByText('등록된 스케줄이 없습니다');

    await userEvent.click(screen.getByRole('button', { name: /스케줄 추가/ }));
    await userEvent.type(screen.getByLabelText('실행 메시지'), '뉴스 요약');
    await userEvent.click(screen.getByRole('button', { name: '생성' }));

    expect(await screen.findByText('매일 09:00 실행')).toBeInTheDocument();
  });

  it('토글 클릭 시 PATCH되어 일시중지 배지가 표시된다', async () => {
    seedSchedules('agent-1', [mockSchedule({ enabled: true })]);
    renderPanel();
    const toggle = await screen.findByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    await userEvent.click(toggle);
    expect(await screen.findByText('일시중지')).toBeInTheDocument();
  });

  it('삭제는 ConfirmDialog 확인 후 DELETE된다', async () => {
    seedSchedules('agent-1', [mockSchedule()]);
    renderPanel();
    await userEvent.click(await screen.findByLabelText('매일 09:00 실행 삭제'));
    expect(screen.getByText('스케줄 삭제')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '삭제' }));
    expect(await screen.findByText('등록된 스케줄이 없습니다')).toBeInTheDocument();
  });

  it('수정 진입 시 폼에 값이 로드되고 저장 시 PUT된다', async () => {
    seedSchedules('agent-1', [
      mockSchedule({ spec: { schedule_type: 'cron', cron_expr: '30 18 * * *' }, name: '매일 18:30 실행' }),
    ]);
    renderPanel();
    await userEvent.click(await screen.findByLabelText('매일 18:30 실행 수정'));
    expect(screen.getByLabelText('시')).toHaveValue('18');

    await userEvent.selectOptions(screen.getByLabelText('시'), '9');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('매일 09:30 실행')).toBeInTheDocument();
  });

  it('이력 보기 확장 시 실행 이력을 렌더한다 (실패 메시지 포함)', async () => {
    seedSchedules('agent-1', [mockSchedule()]);
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: /이력 보기/ }));
    expect(await screen.findByText('성공')).toBeInTheDocument();
    expect(screen.getByText('실패')).toBeInTheDocument();
    expect(screen.getByText('LLM timeout')).toBeInTheDocument();
  });

  it('10개 도달 시 추가 버튼이 비활성화된다', async () => {
    seedSchedules(
      'agent-1',
      Array.from({ length: 10 }, () => mockSchedule()),
    );
    renderPanel();
    await screen.findAllByText('매일 09:00 실행');
    expect(screen.getByRole('button', { name: /스케줄 추가/ })).toBeDisabled();
  });

  it('daily 유형(백엔드 직접 생성분)은 수정 버튼이 비활성화된다', async () => {
    seedSchedules('agent-1', [
      mockSchedule({ spec: { schedule_type: 'daily', time_of_day: '09:00' } }),
    ]);
    renderPanel();
    expect(await screen.findByLabelText('매일 09:00 실행 수정')).toBeDisabled();
  });
});

describe('SchedulePanel — create 모드 (staged)', () => {
  it('staged 목록을 등록 대기 배지와 함께 렌더한다', () => {
    renderPanel({ mode: 'create', agentId: null, stagedSchedules: [stagedItem] });
    expect(screen.getByText('매일 09:00 실행')).toBeInTheDocument();
    expect(screen.getByText('등록 대기')).toBeInTheDocument();
    expect(screen.getByText('에이전트 생성 시 함께 등록됩니다')).toBeInTheDocument();
  });

  it('폼 제출 시 서버 호출 없이 onStagedAdd만 호출된다', async () => {
    const { onStagedAdd } = renderPanel({ mode: 'create', agentId: null });
    await userEvent.click(screen.getByRole('button', { name: /스케줄 추가/ }));
    await userEvent.type(screen.getByLabelText('실행 메시지'), '뉴스 요약');
    await userEvent.click(screen.getByRole('button', { name: '생성' }));

    await waitFor(() =>
      expect(onStagedAdd).toHaveBeenCalledWith(
        expect.objectContaining({
          name: '매일 09:00 실행',
          spec: { schedule_type: 'cron', cron_expr: '0 9 * * *' },
          instruction: '뉴스 요약',
          localId: expect.any(String),
        }),
      ),
    );
  });

  it('삭제 버튼은 ConfirmDialog 없이 onStagedRemove를 즉시 호출한다', async () => {
    const { onStagedRemove } = renderPanel({
      mode: 'create',
      agentId: null,
      stagedSchedules: [stagedItem],
    });
    await userEvent.click(screen.getByLabelText('매일 09:00 실행 삭제'));
    expect(onStagedRemove).toHaveBeenCalledWith('local-1');
    expect(screen.queryByText('스케줄 삭제')).not.toBeInTheDocument();
  });
});
