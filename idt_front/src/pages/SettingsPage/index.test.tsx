// agent-memory: 설정 페이지 — "AI가 기억하는 내용" 섹션.
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import SettingsPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPage = () => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <SettingsPage />
    </Wrapper>,
  );
};

describe('SettingsPage — AI가 기억하는 내용', () => {
  it('목록·타입 뱃지·카운터를 렌더한다', async () => {
    renderPage();

    expect(await screen.findByText('여신 심사팀 소속')).toBeInTheDocument();
    expect(screen.getByText('근거 조문 번호 인용 선호')).toBeInTheDocument();
    // '프로필'/'선호'는 추가 폼 select 옵션에도 존재 — 뱃지 포함 복수 매칭 허용
    expect(screen.getAllByText('프로필').length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText('선호').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('2/30')).toBeInTheDocument();
  });

  it('추가 폼 제출 시 등록 요청을 보낸다', async () => {
    const user = userEvent.setup();
    interface PostedBody {
      mem_type?: string;
      content?: string;
    }
    let posted: PostedBody | null = null;
    server.use(
      http.post('*/api/v1/memories', async ({ request }) => {
        posted = (await request.json()) as PostedBody;
        return HttpResponse.json(
          {
            id: 3, mem_type: posted?.mem_type, content: posted?.content,
            created_at: '2026-07-18T00:00:00Z', updated_at: '2026-07-18T00:00:00Z',
          },
          { status: 201 },
        );
      }),
    );
    renderPage();
    await screen.findByText('여신 심사팀 소속');

    await user.selectOptions(screen.getByLabelText('메모리 타입'), 'domain_term');
    await user.type(screen.getByLabelText('메모리 내용'), "'한도'는 동일인 여신한도");
    await user.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(posted).not.toBeNull());
    expect(posted!.mem_type).toBe('domain_term');
    expect(posted!.content).toBe("'한도'는 동일인 여신한도");
  });

  it('항목 수정 버튼 → 인라인 폼 → PATCH 요청', async () => {
    const user = userEvent.setup();
    interface PatchedBody {
      content?: string;
    }
    let patched: PatchedBody | null = null;
    server.use(
      http.patch('*/api/v1/memories/:id', async ({ request }) => {
        patched = (await request.json()) as PatchedBody;
        return HttpResponse.json({
          id: 1, mem_type: 'profile', content: patched?.content,
          created_at: '2026-07-18T00:00:00Z', updated_at: '2026-07-18T00:00:00Z',
        });
      }),
    );
    renderPage();
    await screen.findByText('여신 심사팀 소속');

    await user.click(screen.getAllByRole('button', { name: '수정' })[0]);
    const editBox = screen.getByDisplayValue('여신 심사팀 소속');
    await user.clear(editBox);
    await user.type(editBox, '여신 기획팀 소속');
    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched!.content).toBe('여신 기획팀 소속');
  });

  it('삭제 버튼 클릭 시 DELETE 요청을 보낸다', async () => {
    const user = userEvent.setup();
    let deleted = false;
    server.use(
      http.delete('*/api/v1/memories/:id', () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderPage();
    await screen.findByText('여신 심사팀 소속');

    await user.click(screen.getAllByRole('button', { name: '삭제' })[0]);

    await waitFor(() => expect(deleted).toBe(true));
  });

  it('상한 도달 시 추가 폼이 비활성화되고 안내가 보인다', async () => {
    server.use(
      http.get('*/api/v1/memories', () =>
        HttpResponse.json({
          items: Array.from({ length: 30 }, (_, i) => ({
            id: i + 1, mem_type: 'profile', content: `메모리 ${i + 1}`,
            created_at: '2026-07-18T00:00:00Z', updated_at: '2026-07-18T00:00:00Z',
          })),
          total: 30,
          max_count: 30,
        }),
      ),
    );
    renderPage();

    expect(await screen.findByText('30/30')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '등록' })).toBeDisabled();
    expect(
      screen.getByText(/상한에 도달했습니다/),
    ).toBeInTheDocument();
  });

  it('등록 422 에러 detail을 그대로 표시한다', async () => {
    const user = userEvent.setup();
    server.use(
      http.post('*/api/v1/memories', () =>
        HttpResponse.json(
          { detail: '메모리 내용은 500자를 초과할 수 없습니다.' },
          { status: 422 },
        ),
      ),
    );
    renderPage();
    await screen.findByText('여신 심사팀 소속');

    await user.type(screen.getByLabelText('메모리 내용'), '내용');
    await user.click(screen.getByRole('button', { name: '등록' }));

    expect(
      await screen.findByText('메모리 내용은 500자를 초과할 수 없습니다.'),
    ).toBeInTheDocument();
  });
});
