// Design §8.3 L2 #1~#8 — 목록 / 추출 / 탭 편집 / 저장 (MSW 기본 핸들러)
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import AdminBlueprintsPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPage = () => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <MemoryRouter>
        <AdminBlueprintsPage />
      </MemoryRouter>
    </Wrapper>
  );
};

const goExtract = async () => {
  renderPage();
  await screen.findByText('golden', {}, { timeout: 3000 });
  await userEvent.click(screen.getByRole('button', { name: '+ 새 blueprint' }));
  const input = screen.getByLabelText('Golden Sample 파일');
  fireEvent.change(input, { target: { files: [new File(['%PDF'], 'golden.pdf', { type: 'application/pdf' })] } });
  await userEvent.click(screen.getByRole('button', { name: '추출 시작' }));
  await screen.findByText(/추출 완료/, {}, { timeout: 3000 });
};

describe('AdminBlueprintsPage — 목록 (L2 #1)', () => {
  it('행·배지·편집/비활성화 액션이 렌더된다', async () => {
    renderPage();
    expect(await screen.findByText('golden')).toBeInTheDocument();
    expect(screen.getByText('old')).toBeInTheDocument();
    expect(screen.getAllByText('active')).toHaveLength(1);
    expect(screen.getByText('inactive')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: '편집' })).toHaveLength(2);
    expect(screen.getAllByRole('button', { name: '비활성화' })).toHaveLength(1); // active 만
  });

  it('비활성화 확인 다이얼로그 → DELETE 호출', async () => {
    let deleted = '';
    server.use(
      http.delete(`*${API_ENDPOINTS.ADMIN_BLUEPRINTS}/:id`, ({ params }) => {
        deleted = String(params.id);
        return HttpResponse.json({ id: params.id, status: 'inactive' });
      })
    );
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: '비활성화' }));
    const dialog = await screen.findByRole('dialog');
    await userEvent.click(within(dialog).getByRole('button', { name: '비활성화' }));
    await waitFor(() => expect(deleted).toBe('bp-1'));
  });

  it('목록 오류는 alert 로 표시된다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.ADMIN_BLUEPRINTS}`, () =>
        HttpResponse.json({ detail: { code: 'X', message: '서버 오류' } }, { status: 500 })
      )
    );
    renderPage();
    expect(await screen.findByRole('alert')).toHaveTextContent('서버 오류');
  });
});

describe('AdminBlueprintsPage — 추출·편집·저장 (L2 #2~#8)', () => {
  it('docx 파일은 클라이언트에서 막힌다', async () => {
    renderPage();
    await screen.findByText('golden');
    await userEvent.click(screen.getByRole('button', { name: '+ 새 blueprint' }));
    fireEvent.change(screen.getByLabelText('Golden Sample 파일'), {
      target: { files: [new File(['x'], 'a.docx')] },
    });
    expect(screen.getByRole('alert')).toHaveTextContent('PDF 또는 PPTX');
    expect(screen.getByRole('button', { name: '추출 시작' })).toBeDisabled();
  });

  it('추출 후 분류 요약·탭·경고 배지가 보이고 패턴 탭에 썸네일/분류 실패 배지가 있다', async () => {
    await goExtract();
    expect(screen.getByText(/성공 1 \/ 실패 1/)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /경고/ })).toHaveTextContent('1');
    await userEvent.click(screen.getByRole('tab', { name: '페이지 패턴' }));
    expect(screen.getByAltText('페이지 1 썸네일')).toBeInTheDocument();
    expect(screen.getByText('분류 실패')).toBeInTheDocument();
    expect((screen.getByLabelText('pattern p2 kind') as HTMLSelectElement).value).toBe('unknown');
  });

  it('스타일 탭 hex 수정 · 패턴 kind 변경 · 서사 섹션 추가 · 폰트 매핑 select 가 저장 payload 에 반영된다', async () => {
    let captured: { draft: Record<string, unknown>; assets: unknown[] } | null = null;
    server.use(
      http.post(`*${API_ENDPOINTS.ADMIN_BLUEPRINTS}`, async ({ request }) => {
        captured = (await request.json()) as typeof captured;
        return HttpResponse.json({ ...captured!.draft, created_at: 'x', updated_at: 'x' }, { status: 201 });
      })
    );
    await goExtract();
    // 스타일
    const hex = screen.getByLabelText('palette primary hex');
    await userEvent.clear(hex);
    await userEvent.type(hex, '#123456');
    // 패턴
    await userEvent.click(screen.getByRole('tab', { name: '페이지 패턴' }));
    await userEvent.selectOptions(screen.getByLabelText('pattern p2 kind'), 'closing');
    // 서사
    await userEvent.click(screen.getByRole('tab', { name: '서사' }));
    await userEvent.click(screen.getByRole('button', { name: '+ 섹션 추가' }));
    await userEvent.type(screen.getByLabelText('section 1 role'), '결론');
    await userEvent.selectOptions(screen.getByLabelText('section 1 patterns'), 'p2');
    // 폰트
    await userEvent.click(screen.getByRole('tab', { name: '폰트 매핑' }));
    await userEvent.selectOptions(await screen.findByLabelText('font 맑은 고딕'), 'NanumGothicBold');
    // 에셋 채택 해제
    await userEvent.click(screen.getByRole('tab', { name: '에셋' }));
    await userEvent.click(screen.getByLabelText('asset a1 adopted'));
    // 저장
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    const d = captured!.draft as {
      style: { palette: Record<string, string>; };
      patterns: { id: string; kind: string }[];
      narrative: { sections: { role: string; pattern_ids: string[] }[] };
      font_mapping: Record<string, string>;
      assets: { adopted: boolean }[];
    };
    expect(d.style.palette.primary).toBe('#123456');
    expect(d.patterns.find((p) => p.id === 'p2')?.kind).toBe('closing');
    expect(d.narrative.sections[1]).toEqual({ role: '결론', pattern_ids: ['p2'], guidance: '' });
    expect(d.font_mapping['맑은 고딕']).toBe('NanumGothicBold');
    expect(d.assets[0].adopted).toBe(false);
    expect(captured!.assets).toEqual([{ id: 'a1', data_b64: 'iVBORw0KGgo=' }]);
    // 저장 후 목록 복귀
    expect(await screen.findByText('old')).toBeInTheDocument();
  });

  it('이름이 비면 인라인 오류, 요청 없음', async () => {
    let called = false;
    server.use(
      http.post(`*${API_ENDPOINTS.ADMIN_BLUEPRINTS}`, () => {
        called = true;
        return HttpResponse.json({}, { status: 201 });
      })
    );
    await goExtract();
    await userEvent.clear(screen.getByLabelText('이름 (필수)'));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('이름을 입력하세요');
    expect(called).toBe(false);
  });

  it('서버 400 은 메시지로 표시된다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.ADMIN_BLUEPRINTS}`, () =>
        HttpResponse.json({ detail: { code: 'VALIDATION_ERROR', message: 'asset a1 has no data' } }, { status: 400 })
      )
    );
    await goExtract();
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('asset a1 has no data');
  });

  it('편집 모드: 상세를 프리필하고 PUT 으로 저장한다', async () => {
    let put: { draft: { name: string } } | null = null;
    server.use(
      http.put(`*${API_ENDPOINTS.ADMIN_BLUEPRINTS}/:id`, async ({ request }) => {
        put = (await request.json()) as typeof put;
        return HttpResponse.json({ ...put!.draft, id: 'bp-1', created_at: 'x', updated_at: 'y' });
      })
    );
    renderPage();
    await userEvent.click((await screen.findAllByRole('button', { name: '편집' }))[0]);
    const name = (await screen.findByLabelText('이름 (필수)')) as HTMLInputElement;
    expect(name.value).toBe('golden');
    await userEvent.type(name, '-v2');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(put?.draft.name).toBe('golden-v2'));
  });
});

describe('AdminBlueprintsPage — Act-1 (G2/G3/G9 + 순서 이동)', () => {
  it('표 헤더 글자·테두리·로고 select 가 payload 에 반영되고, 패턴 제외 토글은 저장 시에만 적용된다', async () => {
    let captured: { draft: Record<string, unknown> } | null = null;
    server.use(
      http.post(`*${API_ENDPOINTS.ADMIN_BLUEPRINTS}`, async ({ request }) => {
        captured = (await request.json()) as typeof captured;
        return HttpResponse.json({ ...captured!.draft, created_at: 'x', updated_at: 'x' }, { status: 201 });
      })
    );
    await goExtract();
    const ht = screen.getByLabelText('table header_text');
    await userEvent.clear(ht);
    await userEvent.type(ht, '#111111');
    const bd = screen.getByLabelText('table border');
    await userEvent.clear(bd);
    await userEvent.type(bd, '#999999');
    await userEvent.selectOptions(screen.getByLabelText('logo_asset_id'), '');
    // 패턴 제외 → 취소 → 다시 제외
    await userEvent.click(screen.getByRole('tab', { name: '페이지 패턴' }));
    const card = () => screen.getByTestId('pattern-card-p2');
    const btn = () => within(card()).getByRole('button', { name: /패턴 제외|제외 취소/ });
    await userEvent.click(btn());
    expect(card()).toHaveAttribute('data-excluded', 'true');
    await userEvent.click(btn());
    expect(card()).toHaveAttribute('data-excluded', 'false');
    await userEvent.click(btn());
    // 서사 섹션 순서 이동 (§8.3 #5)
    await userEvent.click(screen.getByRole('tab', { name: '서사' }));
    await userEvent.click(screen.getByRole('button', { name: '+ 섹션 추가' }));
    await userEvent.type(screen.getByLabelText('section 1 role'), '결론');
    await userEvent.click(screen.getAllByRole('button', { name: '↑' })[1]);
    expect((screen.getByLabelText('section 0 role') as HTMLInputElement).value).toBe('결론');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(captured).not.toBeNull());
    const d = captured!.draft as {
      style: { table_style: { header_text: string; border: string }; header_footer: { logo_asset_id: string | null } };
      patterns: { id: string }[];
      narrative: { sections: { role: string; pattern_ids: string[] }[] };
    };
    expect(d.style.table_style).toMatchObject({ header_text: '#111111', border: '#999999' });
    expect(d.style.header_footer.logo_asset_id).toBeNull();
    expect(d.patterns.map((p) => p.id)).toEqual(['p1']); // p2 제외 적용
    expect(d.narrative.sections[0].role).toBe('결론');
  });
});
