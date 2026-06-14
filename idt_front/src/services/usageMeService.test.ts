/**
 * usageMeService 보안 테스트 — M5.
 *
 * ★ 핵심: user_id 쿼리 파라미터를 절대 보내지 않는다 (서버 강제).
 *
 * SEC-1: getMyRuns({...}) 호출 시 user_id 쿼리 없음
 * SEC-2: getMyTimeseries({...}) 호출 시 user_id 쿼리 없음
 * SEC-3: getMyUsage({...}) 호출 시 user_id 쿼리 없음
 */
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { usageMeService } from './usageMeService';
import { API_ENDPOINTS } from '@/constants/api';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('usageMeService — user_id 미전송 보안', () => {
  it('SEC-1: getMyRuns 호출 시 user_id 쿼리 파라미터 없음', async () => {
    const seenSearch: string[] = [];
    server.use(
      http.get(`*${API_ENDPOINTS.USAGE_ME_RUNS}`, ({ request }) => {
        seenSearch.push(new URL(request.url).search);
        return HttpResponse.json({
          from_dt: null,
          to_dt: null,
          limit: 20,
          offset: 0,
          total: 0,
          rows: [],
        });
      }),
    );

    await usageMeService.getMyRuns({
      from: '2026-04-21T00:00:00Z',
      to: '2026-05-21T00:00:00Z',
      agent_id: 'a-1',
      status: 'SUCCESS',
      limit: 20,
      offset: 0,
    });

    expect(seenSearch).toHaveLength(1);
    expect(seenSearch[0]).not.toContain('user_id');
  });

  it('SEC-2: getMyTimeseries 호출 시 user_id 쿼리 없음', async () => {
    const seenSearch: string[] = [];
    server.use(
      http.get(`*${API_ENDPOINTS.USAGE_ME_TIMESERIES}`, ({ request }) => {
        seenSearch.push(new URL(request.url).search);
        return HttpResponse.json({
          from_dt: '2026-05-01T00:00:00Z',
          to_dt: '2026-05-31T00:00:00Z',
          bucket: 'day',
          points: [],
        });
      }),
    );

    await usageMeService.getMyTimeseries({
      from: '2026-04-21T00:00:00Z',
      to: '2026-05-21T00:00:00Z',
    });

    expect(seenSearch[0]).not.toContain('user_id');
  });

  it('SEC-3: getMyUsage 호출 시 user_id 쿼리 없음', async () => {
    const seenSearch: string[] = [];
    server.use(
      http.get(`*${API_ENDPOINTS.USAGE_ME}`, ({ request }) => {
        seenSearch.push(new URL(request.url).search);
        return HttpResponse.json({
          from_dt: '2026-05-01T00:00:00Z',
          to_dt: '2026-05-31T00:00:00Z',
          rows: [],
        });
      }),
    );

    await usageMeService.getMyUsage({
      from: '2026-04-21T00:00:00Z',
      to: '2026-05-21T00:00:00Z',
    });

    expect(seenSearch[0]).not.toContain('user_id');
  });
});
