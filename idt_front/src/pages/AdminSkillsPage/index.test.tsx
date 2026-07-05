import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import AdminSkillsPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPage = () =>
  render(<AdminSkillsPage />, { wrapper: createWrapper() });

describe('AdminSkillsPage', () => {
  it('S-1: Skill 목록을 렌더한다', async () => {
    renderPage();
    expect(await screen.findByText('환율 계산기')).toBeInTheDocument();
    expect(screen.getByText('공용 요약기')).toBeInTheDocument();
    // 소유 스킬은 수정, 비소유 public 스킬은 Fork 버튼
    expect(screen.getByRole('button', { name: '수정' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fork' })).toBeInTheDocument();
  });

  it('S-2: 생성 모달에서 Skill을 만든다', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/skills', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 'skill-new' }, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('환율 계산기');

    await user.click(screen.getByRole('button', { name: 'Skill 만들기' }));
    await user.type(screen.getByPlaceholderText('예: 환율 계산기'), '새 스킬');
    await user.type(
      screen.getByPlaceholderText('이런 상황에 이렇게 동작하라 ...'),
      '이렇게 하라',
    );
    await user.click(screen.getByRole('button', { name: '만들기' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toMatchObject({
      name: '새 스킬',
      instruction: '이렇게 하라',
      script_type: 'none',
      visibility: 'private',
    });
  });

  it('S-3: 이름/지시문 누락 시 검증 에러', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('환율 계산기');

    await user.click(screen.getByRole('button', { name: 'Skill 만들기' }));
    await user.click(screen.getByRole('button', { name: '만들기' }));

    expect(await screen.findByText('이름·지시문은 필수입니다.')).toBeInTheDocument();
  });

  it('S-4: 삭제 확인 후 DELETE 호출', async () => {
    let deleted = false;
    server.use(
      http.delete('*/api/v1/skills/:id', () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('환율 계산기');

    await user.click(screen.getByRole('button', { name: '환율 계산기 삭제' }));
    await user.click(screen.getByRole('button', { name: '삭제' }));

    await waitFor(() => expect(deleted).toBe(true));
  });

  it('S-5: 비소유 스킬 Fork 호출', async () => {
    let forked = false;
    server.use(
      http.post('*/api/v1/skills/:id/fork', () => {
        forked = true;
        return HttpResponse.json({ id: 'skill-forked' }, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('공용 요약기');

    await user.click(screen.getByRole('button', { name: 'Fork' }));
    await waitFor(() => expect(forked).toBe(true));
  });
});
