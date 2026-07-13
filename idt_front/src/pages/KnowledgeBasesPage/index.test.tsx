import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import {
  afterAll,
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
} from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { useAuthStore } from '@/store/authStore';
import KnowledgeBasesPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

beforeEach(() => {
  useAuthStore.setState({
    user: { id: 1, email: 'user@test.com', role: 'user' } as never,
    isAuthenticated: true,
  });
});

const renderPage = () =>
  render(
    <MemoryRouter>
      <KnowledgeBasesPage />
    </MemoryRouter>,
    { wrapper: createWrapper() },
  );

describe('KnowledgeBasesPage — kb-management-ui', () => {
  it('지식베이스 목록과 scope 배지를 렌더링한다', async () => {
    renderPage();

    expect(await screen.findByText('전사 규정')).toBeInTheDocument();
    expect(screen.getByText('여신 심사 기준')).toBeInTheDocument();
    expect(screen.getByText('내 메모')).toBeInTheDocument();
    // scope 배지 (SCOPE_LABELS: 공개/부서/개인)
    expect(screen.getByText('공개')).toBeInTheDocument();
    expect(screen.getByText('부서')).toBeInTheDocument();
    expect(screen.getByText('개인')).toBeInTheDocument();
  });

  it('빈 목록이면 생성 유도 안내를 보여준다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.KNOWLEDGE_BASES}`, () =>
        HttpResponse.json({ knowledge_bases: [], total: 0 }),
      ),
    );
    renderPage();

    expect(
      await screen.findByText(/아직 지식베이스가 없습니다/),
    ).toBeInTheDocument();
  });

  it('생성 성공 시 모달이 닫힌다', async () => {
    renderPage();
    await screen.findByText('전사 규정');

    await userEvent.click(
      screen.getByRole('button', { name: '+ 새 지식베이스' }),
    );
    expect(screen.getByText('새 지식베이스')).toBeInTheDocument();

    await userEvent.type(
      screen.getByPlaceholderText('여신 규정집'),
      '테스트 KB',
    );
    await userEvent.click(
      screen.getByRole('combobox', { name: '대상 컬렉션' }),
    );
    await userEvent.click(
      await screen.findByRole('option', { name: /documents/ }),
    );
    await userEvent.click(screen.getByRole('button', { name: '생성' }));

    await waitFor(() =>
      expect(screen.queryByText('새 지식베이스')).not.toBeInTheDocument(),
    );
  });

  it('이름 중복(409)이면 인라인 에러를 표시한다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.KNOWLEDGE_BASES}`, () =>
        HttpResponse.json(
          { detail: "Knowledge base '테스트 KB' already exists" },
          { status: 409 },
        ),
      ),
    );
    renderPage();
    await screen.findByText('전사 규정');

    await userEvent.click(
      screen.getByRole('button', { name: '+ 새 지식베이스' }),
    );
    await userEvent.type(
      screen.getByPlaceholderText('여신 규정집'),
      '테스트 KB',
    );
    await userEvent.click(
      screen.getByRole('combobox', { name: '대상 컬렉션' }),
    );
    await userEvent.click(
      await screen.findByRole('option', { name: /documents/ }),
    );
    await userEvent.click(screen.getByRole('button', { name: '생성' }));

    expect(
      await screen.findByText('같은 이름의 지식베이스가 이미 있습니다'),
    ).toBeInTheDocument();
  });

  it('소유자는 삭제 확인 후 삭제할 수 있다', async () => {
    renderPage();
    await screen.findByText('전사 규정');

    // kb-public-1 (owner_id: 1) — 현재 사용자 소유
    await userEvent.click(
      screen.getByRole('button', { name: '전사 규정 삭제' }),
    );
    expect(screen.getByText('지식베이스 삭제')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '삭제' }));

    await waitFor(() =>
      expect(
        screen.queryByText('지식베이스 삭제'),
      ).not.toBeInTheDocument(),
    );
  });

  it('소유자가 아니면 삭제 버튼이 노출되지 않는다 (D8)', async () => {
    renderPage();
    await screen.findByText('전사 규정');

    // kb-dept-1 (owner_id: 2), kb-personal-1 (owner_id: 3) — 비소유
    expect(
      screen.queryByRole('button', { name: '여신 심사 기준 삭제' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '내 메모 삭제' }),
    ).not.toBeInTheDocument();
  });
});
