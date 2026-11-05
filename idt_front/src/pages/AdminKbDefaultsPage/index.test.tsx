// agent-kb-quick-setup Design §8.3 L2 #14 — 관리자 기본 임베딩 모델 화면
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import AdminKbDefaultsPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPage = () => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <MemoryRouter>
        <AdminKbDefaultsPage />
      </MemoryRouter>
    </Wrapper>,
  );
};

const waitSelect = async () =>
  (await screen.findByLabelText('기본 임베딩 모델', {}, { timeout: 3000 })) as HTMLSelectElement;

describe('AdminKbDefaultsPage', () => {
  it('활성 임베딩 모델 목록과 현재값이 렌더되고 안내 문구가 있다', async () => {
    renderPage();
    const select = await waitSelect();
    const options = within(select).getAllByRole('option').map((o) => o.textContent);
    expect(options[0]).toBe('— 미선택 —');
    expect(options.some((t) => t?.includes('OpenAI Embedding 3 Small'))).toBe(true);
    expect(select.value).toBe('1');
    expect(screen.getByText('변경은 이후 자동 생성되는 지식베이스에만 적용됩니다')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
  });

  it('미설정이면 경고 문구가 보인다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.ADMIN_KB_DEFAULTS}`, () =>
        HttpResponse.json({
          configured: false, default_embedding_model_id: null, model: null, warnings: [], updated_at: null,
        }),
      ),
    );
    renderPage();
    await waitSelect();
    expect(screen.getByText('미설정이면 사용자가 빌더에서 문서를 올릴 수 없습니다')).toBeInTheDocument();
  });

  it('끊어진 참조 warnings 를 표시한다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.ADMIN_KB_DEFAULTS}`, () =>
        HttpResponse.json({
          configured: false, default_embedding_model_id: 9, model: null,
          warnings: ['기본 임베딩 모델(id=9)이 삭제되었습니다. 다시 선택해 주세요.'], updated_at: null,
        }),
      ),
    );
    renderPage();
    await waitSelect();
    expect(screen.getByText(/id=9.*삭제/)).toBeInTheDocument();
  });

  it('모델을 바꿔 저장하면 PUT 이 호출되고 저장 메시지가 보인다', async () => {
    renderPage();
    const select = await waitSelect();
    await userEvent.selectOptions(select, '2');
    const save = screen.getByRole('button', { name: '저장' });
    expect(save).not.toBeDisabled();
    await userEvent.click(save);
    expect(await screen.findByText('저장되었습니다')).toBeInTheDocument();
    await waitFor(() => expect((screen.getByLabelText('기본 임베딩 모델') as HTMLSelectElement).value).toBe('2'));
  });

  it('서버 404 메시지를 그대로 노출한다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.EMBEDDING_MODELS}`, () =>
        HttpResponse.json({
          models: [
            { id: 1, provider: 'openai', model_name: 'a', display_name: 'A', vector_dimension: 1536, description: '' },
            { id: 99, provider: 'openai', model_name: 'z', display_name: 'Z', vector_dimension: 10, description: '' },
          ],
          total: 2,
        }),
      ),
    );
    renderPage();
    const select = await waitSelect();
    await userEvent.selectOptions(select, '99');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('임베딩 모델을 찾을 수 없습니다')).toBeInTheDocument();
  });
});
