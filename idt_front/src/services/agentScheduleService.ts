import authApiClient from './api/authClient';
import { API_ENDPOINTS } from '@/constants/api';
import type {
  ScheduleCreateRequest,
  ScheduleUpdateRequest,
  ScheduleResponse,
  ScheduleRunResponse,
} from '@/types/agentSchedule';

// agent-schedule: 에이전트 스케줄 CRUD + 활성 토글 + 실행 이력
export const agentScheduleService = {
  list: (agentId: string) =>
    authApiClient.get<ScheduleResponse[]>(API_ENDPOINTS.AGENT_SCHEDULES(agentId)),

  create: (agentId: string, data: ScheduleCreateRequest) =>
    authApiClient.post<ScheduleResponse>(
      API_ENDPOINTS.AGENT_SCHEDULES(agentId),
      data,
    ),

  update: (agentId: string, scheduleId: string, data: ScheduleUpdateRequest) =>
    authApiClient.put<ScheduleResponse>(
      API_ENDPOINTS.AGENT_SCHEDULE_DETAIL(agentId, scheduleId),
      data,
    ),

  remove: (agentId: string, scheduleId: string) =>
    authApiClient.delete<void>(
      API_ENDPOINTS.AGENT_SCHEDULE_DETAIL(agentId, scheduleId),
    ),

  setEnabled: (agentId: string, scheduleId: string, enabled: boolean) =>
    authApiClient.patch<ScheduleResponse>(
      API_ENDPOINTS.AGENT_SCHEDULE_ENABLED(agentId, scheduleId),
      { enabled },
    ),

  listRuns: (
    agentId: string,
    scheduleId: string,
    params?: { limit?: number; offset?: number },
  ) =>
    authApiClient.get<ScheduleRunResponse[]>(
      API_ENDPOINTS.AGENT_SCHEDULE_RUNS(agentId, scheduleId),
      { params },
    ),
};
