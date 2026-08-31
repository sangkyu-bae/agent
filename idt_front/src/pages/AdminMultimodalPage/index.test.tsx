// Design §8.3 L2 #1~#6 — 설정 탭·미리보기 탭 (MSW 기본 핸들러 사용)
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import AdminMultimodalPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPage = () => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <MemoryRouter>
        <AdminMultimodalPage />
      </MemoryRouter>
    </Wrapper>
  );
};

const waitSettings = async () =>
  await screen.findByLabelText('비전 모델', {}, { timeout: 3000 });

describe('AdminMultimodalPage — 설정 탭 (L2 #1)', () => {
  it('§5.4 설정 요소가 전부 렌더되고 모델 select 에는 비전 모델만 있다', async () => {
    renderPage();
    const select = (await waitSettings()) as HTMLSelectElement;

    // 비전 모델: mock llm-models 중 supports_vision=true 인 gpt-4o, claude 2개 + 미선택
    const options = within(select).getAllByRole('option');
    expect(options.map((o) => o.textContent)).toEqual([
      '— 미선택 —',
      'GPT-4o (openai/gpt-4o)',
      'Claude Sonnet 4.6 (anthropic/claude-sonnet-4-6)',
    ]);
    expect(select.value).toBe('uuid-1');

    expect(screen.getByRole('switch', { name: '활성화' })).toBeChecked();
    expect(screen.getByLabelText('문서당 최대 이미지')).toHaveValue(50);
    expect(screen.getByLabelText('최소 픽셀(가로·세로)')).toHaveValue(100);
    expect(screen.getByLabelText('최소 면적 비율')).toHaveValue(0.02);
    expect(screen.getByLabelText('동시 호출 수')).toHaveValue(4);
    expect(screen.getByLabelText('건당 타임아웃(초)')).toHaveValue(60);
    expect(screen.getByRole('radio', { name: '한국어 (ko)' })).toBeChecked();
    expect(screen.getByRole('radio', { name: '상세 (detailed)' })).toBeChecked();
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled(); // dirty 아님
    expect(screen.getByRole('button', { name: '연결 테스트' })).toBeEnabled();
  });

  it('선택 모델이 비활성이면 경고 배너를 보여준다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.ADMIN_MULTIMODAL_SETTINGS}`, () =>
        HttpResponse.json({
          id: 's', enabled: true, vision_model_id: 'gone', vision_model: null,
          warnings: ["selected model 'gone' not found"],
          max_images_per_doc: 50, min_image_px: 100, min_area_ratio: 0.02, concurrency: 4,
          timeout_sec: 60, output_language: 'ko', detail_level: 'detailed',
          updated_at: '2026-08-21T09:00:00',
        })
      )
    );
    renderPage();
    await waitSettings();
    expect(await screen.findByRole('alert')).toHaveTextContent("selected model 'gone' not found");
  });

  it('비전 모델이 하나도 없으면 LLM 모델 관리 링크를 안내한다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.LLM_MODELS}`, () => HttpResponse.json({ models: [] }))
    );
    renderPage();
    await waitSettings();
    expect(await screen.findByRole('link', { name: 'LLM 모델 관리로 이동' })).toHaveAttribute(
      'href',
      '/admin/llm-models'
    );
  });
});

describe('AdminMultimodalPage — 검증·저장 (L2 #2, #3)', () => {
  it('범위 밖 입력은 인라인 오류 + 저장 비활성', async () => {
    renderPage();
    await waitSettings();
    const user = userEvent.setup();
    const concurrency = screen.getByLabelText('동시 호출 수');
    await user.clear(concurrency);
    await user.type(concurrency, '0');
    expect(await screen.findByText('1~16 범위여야 합니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
  });

  it('저장은 PUT 을 정확히 1회 호출하고 성공 메시지를 보인다 (이중 클릭 방지는 호출 횟수로 검증)', async () => {
    let putCount = 0;
    let lastBody: Record<string, unknown> | null = null;
    server.use(
      http.put(`*${API_ENDPOINTS.ADMIN_MULTIMODAL_SETTINGS}`, async ({ request }) => {
        putCount += 1;
        lastBody = (await request.json()) as Record<string, unknown>;
        await new Promise((r) => setTimeout(r, 50));
        return HttpResponse.json({
          id: 's', ...lastBody, vision_model: null, warnings: [], updated_at: '2026-08-21T10:00:00',
        });
      })
    );
    renderPage();
    await waitSettings();
    const user = userEvent.setup();
    const concurrency = screen.getByLabelText('동시 호출 수');
    await user.clear(concurrency);
    await user.type(concurrency, '2');
    await user.click(screen.getByRole('radio', { name: '간략 (brief)' }));

    const save = screen.getByRole('button', { name: '저장' });
    expect(save).toBeEnabled();
    await user.click(save);
    await user.click(save); // 대기 중 두 번째 클릭

    expect(await screen.findByText('저장되었습니다.')).toBeInTheDocument();
    expect(putCount).toBe(1);
    expect(lastBody).toMatchObject({
      concurrency: 2, detail_level: 'brief', vision_model_id: 'uuid-1', enabled: true,
      max_images_per_doc: 50, min_image_px: 100, min_area_ratio: 0.02, timeout_sec: 60,
      output_language: 'ko',
    });
  });

  it('409/404 서버 메시지를 그대로 표시한다', async () => {
    renderPage();
    const select = await waitSettings();
    const user = userEvent.setup();
    // mock: supports_vision=false 인 uuid-3 은 select 에 없으므로 서버 409 를 직접 시뮬레이션
    server.use(
      http.put(`*${API_ENDPOINTS.ADMIN_MULTIMODAL_SETTINGS}`, () =>
        HttpResponse.json(
          { detail: { code: 'VISION_MODEL_NOT_CAPABLE', message: '비전 미지원 모델' } },
          { status: 409 }
        )
      )
    );
    await user.selectOptions(select, 'uuid-2');
    await user.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('비전 미지원 모델')).toBeInTheDocument();
  });
});

describe('AdminMultimodalPage — 연결 테스트 (L2 #4)', () => {
  it('POST /test 호출 후 결과 카드를 보여준다', async () => {
    renderPage();
    await waitSettings();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '연결 테스트' }));
    const card = await screen.findByTestId('mm-test-result');
    expect(card).toHaveTextContent('연결 성공');
    expect(card).toHaveTextContent('openai/gpt-4o');
    expect(card).toHaveTextContent('분기별 여신 한도 막대 차트');
    expect(card).not.toHaveTextContent('degraded');
  });

  it('degraded 배지와 실패(ok=false)를 구분해 보여준다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.ADMIN_MULTIMODAL_TEST}`, () =>
        HttpResponse.json({
          ok: false, provider: 'ollama', model_name: 'qwen-vl', elapsed_ms: 8,
          degraded_output_mode: true, draft: null, error: 'RuntimeError: connection refused',
        })
      )
    );
    renderPage();
    await waitSettings();
    await userEvent.setup().click(screen.getByRole('button', { name: '연결 테스트' }));
    const card = await screen.findByTestId('mm-test-result');
    expect(card).toHaveTextContent('연결 실패');
    expect(card).toHaveTextContent('degraded');
    expect(card).toHaveTextContent('connection refused');
  });

  it('409 MULTIMODAL_NOT_CONFIGURED 는 오류 메시지로 표시된다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.ADMIN_MULTIMODAL_TEST}`, () =>
        HttpResponse.json(
          { detail: { code: 'MULTIMODAL_NOT_CONFIGURED', message: 'vision_model_id is not set' } },
          { status: 409 }
        )
      )
    );
    renderPage();
    await waitSettings();
    await userEvent.setup().click(screen.getByRole('button', { name: '연결 테스트' }));
    expect(await screen.findByText('vision_model_id is not set')).toBeInTheDocument();
  });
});

describe('AdminMultimodalPage — 미리보기 탭 (L2 #5, #6)', () => {
  const pdf = () =>
    new File([new Uint8Array([37, 80, 68, 70])], 'sample.pdf', { type: 'application/pdf' });

  it('PDF 업로드·실행 후 요약 바와 요소 카드(상태 배지 3종)를 렌더한다', async () => {
    renderPage();
    await waitSettings();
    const user = userEvent.setup();
    await user.click(screen.getByRole('tab', { name: '미리보기' }));

    const run = screen.getByRole('button', { name: '실행' });
    expect(run).toBeDisabled();
    await user.upload(screen.getByLabelText('PDF 파일'), pdf());
    expect(run).toBeEnabled();
    await user.click(run);

    const section = await screen.findByRole('region', { name: '미리보기 결과' });
    expect(within(section).getByText('후보').nextSibling).toHaveTextContent('4');
    expect(within(section).getByText('필터 제외').nextSibling).toHaveTextContent('1');
    expect(within(section).getByText('상한 skip').nextSibling).toHaveTextContent('1');
    expect(within(section).getByText('openai/gpt-4o')).toBeInTheDocument();

    const cards = within(section).getAllByTestId('mm-element-card');
    expect(cards).toHaveLength(3);
    expect(cards[0]).toHaveTextContent('p.12');
    expect(cards[0]).toHaveTextContent('차트');
    expect(cards[0]).toHaveTextContent('성공');
    expect(cards[0]).toHaveTextContent('2024년 분기별 여신 한도 추이');
    expect(within(cards[0]).getByRole('img', { name: '차트' })).toBeInTheDocument();
    expect(cards[1]).toHaveTextContent('실패');
    expect(cards[1]).toHaveTextContent('timeout (1 retry)');
    expect(cards[2]).toHaveTextContent('건너뜀');
    expect(cards[2]).toHaveTextContent('limit:max_images_per_doc=50');
    // debug 미사용 → 필터 제외 목록 없음
    expect(screen.queryByText(/^필터 제외 목록 \(/)).not.toBeInTheDocument();
  });

  it('차트 판독은 접기에서 수치 표를 보여준다', async () => {
    renderPage();
    await waitSettings();
    const user = userEvent.setup();
    await user.click(screen.getByRole('tab', { name: '미리보기' }));
    await user.upload(screen.getByLabelText('PDF 파일'), pdf());
    await user.click(screen.getByRole('button', { name: '실행' }));
    const cards = await screen.findAllByTestId('mm-element-card');
    await user.click(within(cards[0]).getByRole('button', { name: /차트 판독/ }));
    expect(within(cards[0]).getByText('1Q')).toBeInTheDocument();
    expect(within(cards[0]).getByText('150')).toBeInTheDocument();
    expect(within(cards[0]).getByText(/추세: 증가/)).toBeInTheDocument();
  });

  it('debug 토글 시 필터 제외 목록 테이블을 보여준다', async () => {
    renderPage();
    await waitSettings();
    const user = userEvent.setup();
    await user.click(screen.getByRole('tab', { name: '미리보기' }));
    await user.upload(screen.getByLabelText('PDF 파일'), pdf());
    await user.click(screen.getByRole('checkbox', { name: /debug/ }));
    await user.click(screen.getByRole('button', { name: '실행' }));
    expect(await screen.findByText('필터 제외 목록 (1)')).toBeInTheDocument();
    expect(screen.getByText('min_image_px')).toBeInTheDocument();
    expect(screen.getByText('48×48')).toBeInTheDocument();
  });

  it('PDF 외 파일은 클라이언트에서 차단한다', async () => {
    renderPage();
    await waitSettings();
    const user = userEvent.setup();
    await user.click(screen.getByRole('tab', { name: '미리보기' }));
    const input = screen.getByLabelText('PDF 파일') as HTMLInputElement;
    // user.upload 은 accept 불일치 파일을 jsdom 에서 조용히 버릴 수 있어 change 이벤트를 직접 발사
    fireEvent.change(input, {
      target: { files: [new File([new Uint8Array([1])], 'a.docx', { type: 'application/octet-stream' })] },
    });
    expect(await screen.findByText('PDF 파일만 업로드할 수 있습니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '실행' })).toBeDisabled();
  });

  it('409 응답이면 설정 탭 유도 버튼을 보여주고 클릭 시 설정 탭으로 이동한다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.PREVIEW_MULTIMODAL}`, () =>
        HttpResponse.json(
          { detail: { code: 'MULTIMODAL_NOT_CONFIGURED', message: 'vision_model_id is not set' } },
          { status: 409 }
        )
      )
    );
    renderPage();
    await waitSettings();
    const user = userEvent.setup();
    await user.click(screen.getByRole('tab', { name: '미리보기' }));
    await user.upload(screen.getByLabelText('PDF 파일'), pdf());
    await user.click(screen.getByRole('button', { name: '실행' }));
    const goto = await screen.findByRole('button', { name: '설정 탭에서 모델을 먼저 선택하세요' });
    await user.click(goto);
    await waitFor(() =>
      expect(screen.getByRole('tab', { name: '설정' })).toHaveAttribute('aria-selected', 'true')
    );
  });
});
