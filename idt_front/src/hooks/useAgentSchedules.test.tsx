import { describe, it, expect, beforeAll, beforeEach, afterEach, afterAll } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { queryClient } from '@/lib/queryClient';
import { server } from '@/__tests__/mocks/server';
import {
  resetScheduleStore,
  seedSchedules,
  mockSchedule,
} from '@/__tests__/mocks/handlers';
import {
  useAgentSchedules,
  useCreateSchedule,
  useDeleteSchedule,
  useToggleScheduleEnabled,
  useScheduleRuns,
  extractScheduleError,
} from './useAgentSchedules';
import type { ScheduleCreateRequest } from '@/types/agentSchedule';

// invalidate가 lib/queryClient 싱글톤을 사용하므로 래퍼도 싱글톤으로 구성
const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

const createPayload: ScheduleCreateRequest = {
  name: '매일 09:00 실행',
  spec: { schedule_type: 'cron', cron_expr: '0 9 * * *' },
  instruction: '{today} 뉴스 요약',
  timezone: 'Asia/Seoul',
  enabled: true,
};

beforeAll(() => server.listen());
beforeEach(() => resetScheduleStore());
afterEach(() => {
  server.resetHandlers();
  queryClient.clear();
});
afterAll(() => server.close());

describe('useAgentSchedules', () => {
  it('스케줄 목록을 조회한다', async () => {
    seedSchedules('agent-1', [mockSchedule(), mockSchedule({ name: '두번째' })]);
    const { result } = renderHook(() => useAgentSchedules('agent-1'), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
  });

  it('agentId가 null이면 조회하지 않는다', () => {
    const { result } = renderHook(() => useAgentSchedules(null), { wrapper });
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useCreateSchedule', () => {
  it('생성 성공 시 목록이 재조회된다 (invalidate)', async () => {
    seedSchedules('agent-1', []);
    const list = renderHook(() => useAgentSchedules('agent-1'), { wrapper });
    await waitFor(() => expect(list.result.current.isSuccess).toBe(true));
    expect(list.result.current.data).toHaveLength(0);

    const { result } = renderHook(() => useCreateSchedule(), { wrapper });
    await result.current.mutateAsync({ agentId: 'agent-1', data: createPayload });

    await waitFor(() => expect(list.result.current.data).toHaveLength(1));
    expect(list.result.current.data?.[0].name).toBe('매일 09:00 실행');
  });

  it('10개 초과 시 400 detail 메시지를 추출한다', async () => {
    seedSchedules(
      'agent-full',
      Array.from({ length: 10 }, () => mockSchedule({ agent_id: 'agent-full' })),
    );
    const { result } = renderHook(() => useCreateSchedule(), { wrapper });
    let message = '';
    try {
      await result.current.mutateAsync({ agentId: 'agent-full', data: createPayload });
    } catch (e) {
      message = extractScheduleError(e);
    }
    expect(message).toContain('최대 10개');
  });
});

describe('useToggleScheduleEnabled', () => {
  it('PATCH로 enabled를 변경한다', async () => {
    const target = mockSchedule({ enabled: true });
    seedSchedules('agent-1', [target]);
    const { result } = renderHook(() => useToggleScheduleEnabled(), { wrapper });
    const updated = await result.current.mutateAsync({
      agentId: 'agent-1',
      scheduleId: target.id,
      enabled: false,
    });
    expect(updated.enabled).toBe(false);
  });
});

describe('useDeleteSchedule', () => {
  it('삭제 후 목록에서 제거된다', async () => {
    const target = mockSchedule();
    seedSchedules('agent-1', [target]);
    const list = renderHook(() => useAgentSchedules('agent-1'), { wrapper });
    await waitFor(() => expect(list.result.current.data).toHaveLength(1));

    const { result } = renderHook(() => useDeleteSchedule(), { wrapper });
    await result.current.mutateAsync({ agentId: 'agent-1', scheduleId: target.id });

    await waitFor(() => expect(list.result.current.data).toHaveLength(0));
  });
});

describe('useScheduleRuns', () => {
  it('enabled=false면 조회하지 않는다', () => {
    const { result } = renderHook(
      () => useScheduleRuns('agent-1', 'sch-1', { enabled: false }),
      { wrapper },
    );
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('enabled=true면 실행 이력을 조회한다', async () => {
    const { result } = renderHook(
      () => useScheduleRuns('agent-1', 'sch-1', { enabled: true }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[1].error_message).toBe('LLM timeout');
  });
});
