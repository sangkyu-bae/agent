// approval-edit-before-approve Check G2 — 실제 authApiClient 인터셉터를 거친 오류가
// 승인 오류 코드 매핑에 도달하는지 검증한다. (훅 목 테스트는 이 경로를 가렸다.)
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { API_ENDPOINTS } from '@/constants/api';
import { ApiError } from '@/services/api/ApiError';
import { approvalService } from '@/services/approvalService';
import { APPROVAL_ERROR_MESSAGES } from '@/types/approval';
import {
  extractApprovalError,
  extractApprovalErrorCode,
  isApprovalConflict,
} from './useApprovals';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const failApprove = (status: number, detail: unknown) =>
  server.use(
    http.post(`*${API_ENDPOINTS.APPROVAL_APPROVE('ap1')}`, () =>
      HttpResponse.json({ detail }, { status }),
    ),
  );

const approveError = async (): Promise<unknown> => {
  try {
    await approvalService.approve('ap1');
  } catch (e) {
    return e;
  }
  throw new Error('approve 가 실패해야 한다');
};

describe('승인 오류 — authApiClient 경유', () => {
  it('ApiError 가 detail.code 를 보존한다', async () => {
    failApprove(409, { code: 'APPROVAL_NOT_PENDING', message: 'status=approved' });
    const e = await approveError();
    expect(e).toBeInstanceOf(ApiError);
    expect((e as ApiError).code).toBe('APPROVAL_NOT_PENDING');
    expect(extractApprovalErrorCode(e)).toBe('APPROVAL_NOT_PENDING');
  });

  it('알려진 코드는 사용자 문구로 바꾼다', async () => {
    failApprove(410, { code: 'APPROVAL_EXPIRED', message: 'ap1' });
    expect(extractApprovalError(await approveError())).toBe(
      APPROVAL_ERROR_MESSAGES.APPROVAL_EXPIRED,
    );
  });

  it('수정 불가 코드도 매핑된다', async () => {
    failApprove(422, { code: 'APPROVAL_NOT_EDITABLE', message: 'x' });
    expect(extractApprovalError(await approveError())).toBe(
      APPROVAL_ERROR_MESSAGES.APPROVAL_NOT_EDITABLE,
    );
  });

  it('매핑 없는 코드는 서버 메시지를 쓴다', async () => {
    failApprove(422, {
      code: 'APPROVAL_EDIT_INVALID',
      message: '수정할 수 없는 필드입니다: bcc',
    });
    expect(extractApprovalError(await approveError())).toBe(
      '수정할 수 없는 필드입니다: bcc',
    );
  });

  it('409 는 충돌로 판정한다', async () => {
    failApprove(409, { code: 'APPROVAL_NOT_PENDING', message: 'x' });
    expect(isApprovalConflict(await approveError())).toBe(true);
  });

  it('409 가 아니면 충돌이 아니다', async () => {
    failApprove(410, { code: 'APPROVAL_EXPIRED', message: 'x' });
    expect(isApprovalConflict(await approveError())).toBe(false);
  });
});

describe('approvalService.approve 바디 (Check M3)', () => {
  const captureBody = () => {
    const seen: { body: string | null } = { body: null };
    server.use(
      http.post(`*${API_ENDPOINTS.APPROVAL_APPROVE('ap1')}`, async ({ request }) => {
        seen.body = await request.text();
        return HttpResponse.json({
          id: 'ap1', status: 'executed', execute_after: null, message: 'ok',
        });
      }),
    );
    return seen;
  };

  it('수정본이 없으면 바디를 보내지 않는다', async () => {
    const seen = captureBody();
    await approvalService.approve('ap1');
    expect(seen.body).toBe('');
  });

  it('빈 수정본도 바디를 보내지 않는다', async () => {
    const seen = captureBody();
    await approvalService.approve('ap1', false, {});
    expect(seen.body).toBe('');
  });

  it('수정본이 있으면 edited_args 로 보낸다', async () => {
    const seen = captureBody();
    await approvalService.approve('ap1', false, { body: '수정' });
    expect(JSON.parse(seen.body!)).toEqual({ edited_args: { body: '수정' } });
  });
});
