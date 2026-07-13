import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import AdminLlmModelsPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPage = () =>
  render(<AdminLlmModelsPage />, { wrapper: createWrapper() });

describe('AdminLlmModelsPage', () => {
  it('P1: 모델 목록을 렌더한다 (상태 칩·기본 배지 포함)', async () => {
    renderPage();
    expect(await screen.findByText('GPT-4o')).toBeInTheDocument();
    expect(screen.getByText('Claude Sonnet 4.6')).toBeInTheDocument();
    expect(screen.getByText('gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('기본')).toBeInTheDocument();
    expect(screen.getAllByText('활성')).toHaveLength(2);
  });

  it('P2: 가격 미설정 모델은 "미설정" 칩을 표시한다', async () => {
    renderPage();
    await screen.findByText('GPT-4o');
    // Claude Sonnet: 입력/출력 단가 모두 null
    expect(screen.getAllByText('미설정')).toHaveLength(2);
    // GPT-4o: 설정된 단가 표시 ($값 /1K)
    expect(screen.getByText(/\$0\.0025/)).toBeInTheDocument();
    expect(screen.getByText(/\$0\.0100/)).toBeInTheDocument();
    expect(screen.getAllByText('/1K')).toHaveLength(2);
  });

  it('P3: 등록 모달에서 모델을 생성한다 (POST 바디 검증 + 모달 닫힘)', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/llm-models', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: 'uuid-new',
            provider: captured.provider,
            model_name: captured.model_name,
            display_name: captured.display_name,
            description: null,
            max_tokens: null,
            is_active: true,
            is_default: false,
            base_url: null,
            input_price_per_1k_usd: null,
            output_price_per_1k_usd: null,
            pricing_updated_at: null,
          },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('GPT-4o');

    await user.click(screen.getByRole('button', { name: '모델 등록' }));
    await user.type(screen.getByPlaceholderText('예: gpt-4o'), 'gpt-4o-mini');
    await user.type(screen.getByPlaceholderText('예: GPT-4o'), 'GPT-4o mini');
    await user.type(
      screen.getByPlaceholderText('예: OPENAI_API_KEY'),
      'OPENAI_API_KEY',
    );
    await user.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toMatchObject({
      provider: 'openai',
      model_name: 'gpt-4o-mini',
      display_name: 'GPT-4o mini',
      api_key_env: 'OPENAI_API_KEY',
      is_active: true,
      is_default: false,
    });
    await waitFor(() =>
      expect(screen.queryByText('LLM 모델 등록')).not.toBeInTheDocument(),
    );
  });

  it('P4: 필수값 누락 시 인라인 에러를 표시하고 전송하지 않는다', async () => {
    let posted = false;
    server.use(
      http.post('*/api/v1/llm-models', () => {
        posted = true;
        return HttpResponse.json({}, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('GPT-4o');

    await user.click(screen.getByRole('button', { name: '모델 등록' }));
    // 표시명만 입력, 모델명·api_key_env 누락
    await user.type(screen.getByPlaceholderText('예: GPT-4o'), '이름만');
    await user.click(screen.getByRole('button', { name: '등록' }));

    expect(
      await screen.findByText('모델명·API Key 환경변수명은 필수입니다.'),
    ).toBeInTheDocument();
    expect(posted).toBe(false);
  });

  it('P5: 중복 등록(409) 시 모달을 유지하고 detail 에러를 표시한다', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('GPT-4o');

    await user.click(screen.getByRole('button', { name: '모델 등록' }));
    await user.type(screen.getByPlaceholderText('예: gpt-4o'), 'dup-model');
    await user.type(screen.getByPlaceholderText('예: GPT-4o'), '중복 모델');
    await user.type(
      screen.getByPlaceholderText('예: OPENAI_API_KEY'),
      'OPENAI_API_KEY',
    );
    await user.click(screen.getByRole('button', { name: '등록' }));

    expect(
      await screen.findByText('이미 등록된 모델입니다'),
    ).toBeInTheDocument();
    expect(screen.getByText('LLM 모델 등록')).toBeInTheDocument();
  });

  it('P6: 수정 모달은 프리필되고 provider/모델명은 편집 불가, api_key_env는 미노출이다', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('GPT-4o');

    await user.click(screen.getByRole('button', { name: 'GPT-4o 수정' }));

    expect(screen.getByText('LLM 모델 수정')).toBeInTheDocument();
    expect(screen.getByDisplayValue('GPT-4o')).toBeInTheDocument();
    // provider는 읽기 전용 표시 (셀렉트 없음)
    expect(screen.queryByRole('combobox', { name: 'Provider' })).not.toBeInTheDocument();
    // 모델명 입력 필드 없음 (읽기 전용 div)
    expect(screen.queryByPlaceholderText('예: gpt-4o')).not.toBeInTheDocument();
    // api_key_env 미노출 (write-only)
    expect(screen.queryByPlaceholderText('예: OPENAI_API_KEY')).not.toBeInTheDocument();
  });

  it('P7: 가격 모달 — 음수는 인라인 에러로 차단, 정상 값은 저장 후 닫힌다', async () => {
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch('*/api/v1/llm-models/:id/pricing', async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          id: 'uuid-2',
          provider: 'anthropic',
          model_name: 'claude-sonnet-4-6',
          display_name: 'Claude Sonnet 4.6',
          description: null,
          max_tokens: null,
          is_active: true,
          is_default: false,
          base_url: null,
          input_price_per_1k_usd: '0.003',
          output_price_per_1k_usd: '0.015',
          pricing_updated_at: '2026-07-11T00:00:00',
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('GPT-4o');

    await user.click(screen.getByRole('button', { name: 'Claude Sonnet 4.6 가격' }));
    expect(screen.getByText('가격 설정')).toBeInTheDocument();

    // 음수 입력 → 클라이언트 검증 차단
    // (number input에 userEvent.type으로 '-'를 넣을 수 없어 fireEvent로 값 설정)
    fireEvent.change(screen.getByPlaceholderText('예: 0.0025'), {
      target: { value: '-1' },
    });
    await user.type(screen.getByPlaceholderText('예: 0.0100'), '0.015');
    await user.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('0 이상의 숫자를 입력하세요')).toBeInTheDocument();
    expect(patched).toBeNull();

    // 정상 값으로 수정 후 저장 → PATCH 전송 + 모달 닫힘
    await user.clear(screen.getByPlaceholderText('예: 0.0025'));
    await user.type(screen.getByPlaceholderText('예: 0.0025'), '0.003');
    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      input_price_per_1k_usd: 0.003,
      output_price_per_1k_usd: 0.015,
    });
    await waitFor(() =>
      expect(screen.queryByText('가격 설정')).not.toBeInTheDocument(),
    );
  });

  it('P8: 비활성화 — 경고 다이얼로그를 거쳐 DELETE를 전송한다', async () => {
    let deletedId: string | null = null;
    server.use(
      http.delete('*/api/v1/llm-models/:id', ({ params }) => {
        deletedId = params.id as string;
        return HttpResponse.json({
          id: params.id,
          provider: 'openai',
          model_name: 'gpt-4o',
          display_name: 'GPT-4o',
          description: null,
          max_tokens: null,
          is_active: false,
          is_default: false,
          base_url: null,
          input_price_per_1k_usd: null,
          output_price_per_1k_usd: null,
          pricing_updated_at: null,
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('GPT-4o');

    await user.click(screen.getByRole('button', { name: 'GPT-4o 비활성화' }));
    expect(screen.getByText('모델 비활성화')).toBeInTheDocument();
    expect(screen.getByText(/실행 시점에 실패할 수 있습니다/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '비활성화' }));
    await waitFor(() => expect(deletedId).toBe('uuid-1'));
    await waitFor(() =>
      expect(screen.queryByText('모델 비활성화')).not.toBeInTheDocument(),
    );
  });

  it('P9: 비활성 포함 토글 시 include_inactive=true로 조회한다', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('GPT-4o');
    expect(screen.queryByText('Llama 3 8B')).not.toBeInTheDocument();

    await user.click(screen.getByRole('checkbox', { name: '비활성 포함' }));

    expect(await screen.findByText('Llama 3 8B')).toBeInTheDocument();
    expect(screen.getByText('비활성')).toBeInTheDocument();
  });
});
