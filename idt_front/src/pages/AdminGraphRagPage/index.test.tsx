// graph-rag-foundation Design §8.3 L2 #1~#7 + 주제 탭 (MSW 기본 핸들러: graphRagMocks)
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { MemoryRouter } from 'react-router-dom';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { mockGraphHealth, mockGraphSettings } from '@/__tests__/mocks/graphRagMocks';
import { API_ENDPOINTS } from '@/constants/api';
import AdminGraphRagPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPage = () => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <MemoryRouter>
        <AdminGraphRagPage />
      </MemoryRouter>
    </Wrapper>
  );
};

const openTab = async (name: string | RegExp) => {
  const user = userEvent.setup();
  await user.click(await screen.findByRole('tab', { name }));
  return user;
};

describe('AdminGraphRagPage — 헤더·탭 (L2 #1)', () => {
  it('단계·연결 상태·탭 6개·검토 대기 건수를 보여 준다', async () => {
    renderPage();
    expect(await screen.findByLabelText('노출 단계')).toHaveValue('admin_only');
    expect(await screen.findByText(/연결됨/)).toBeInTheDocument();
    expect(screen.getByText(/120 \/ 200,000/)).toBeInTheDocument();
    expect(screen.getByText(/외부 클라우드 저장/)).toBeInTheDocument();
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((t) => t.textContent?.replace(/\d+$/, ''))).toEqual([
      '설정', '추출', '엔티티·관계', '주제', '검색 테스트', '검토 큐',
    ]);
    expect(await screen.findByLabelText('검토 대기 1건')).toBeInTheDocument();
  });

  it('단계가 꺼짐이면 설정 외 탭은 비활성이고 안내가 나온다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_SETTINGS}`, () =>
        HttpResponse.json(mockGraphSettings({ rollout_stage: 'off' }))
      )
    );
    renderPage();
    expect(await screen.findByText(/단계가 꺼져 있어/)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '추출' })).toBeDisabled();
    expect(screen.getByRole('tab', { name: '설정' })).toBeEnabled();
  });

  it('Neo4j 미연결이면 사유를 보여 준다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_HEALTH}`, () =>
        HttpResponse.json(mockGraphHealth({ connected: false, error: 'NEO4J_URI not set',
          node_count: null }))
      )
    );
    renderPage();
    expect(await screen.findByText(/연결 안 됨/)).toBeInTheDocument();
    expect(screen.getByText(/NEO4J_URI not set/)).toBeInTheDocument();
  });
});

describe('설정 탭 (L2 #2·#3)', () => {
  it('신규 기준값이 연결 기준값 이상이면 저장이 막힌다', async () => {
    const user = userEvent.setup();
    renderPage();
    const newTh = await screen.findByLabelText('신규 기준값');
    await user.clear(newTh);
    await user.type(newTh, '0.9');
    expect(screen.getByText(/신규 기준값은 연결 기준값보다 작아야/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
  });

  it('Jev 토글 후 저장하면 PUT 으로 전체 설정을 보낸다', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.put(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_SETTINGS}`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(mockGraphSettings({ jev_enabled: true }));
      })
    );
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('switch', { name: 'Jev 판정' }));
    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ jev_enabled: true, link_threshold: 0.85, max_hops: 2 });
    expect(body).not.toHaveProperty('rollout_stage');
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
  });

  it("타입 칩 '기타'는 지울 수 없고 다른 칩은 지울 수 있다", async () => {
    renderPage();
    await screen.findByLabelText('신규 기준값');
    const entityTypes = screen.getByRole('group', { name: '엔티티 타입' });
    expect(within(entityTypes).queryByRole('button', { name: '기타 삭제' })).toBeNull();
    expect(within(entityTypes).getByRole('button', { name: '조문 삭제' })).toBeInTheDocument();
  });
});

describe('추출 탭 (L2 #4)', () => {
  it('KB 를 고르면 문서 표가 나오고 [다시 만들기]는 rebuild 로 요청한다', async () => {
    let mode: string | null = null;
    server.use(
      http.post('*/api/v1/admin/graph-rag/documents/:id/extract', async ({ request }) => {
        mode = ((await request.json()) as { mode: string }).mode;
        return HttpResponse.json({ job_id: 'j', status: 'pending' }, { status: 202 });
      })
    );
    renderPage();
    const user = await openTab('추출');
    await user.selectOptions(await screen.findByLabelText('지식베이스'), 'kb-public-1');
    const row = (await screen.findByText('여신취급규정.pdf')).closest('tr') as HTMLElement;
    expect(within(row).getByText('완료')).toBeInTheDocument();
    expect(within(row).getByText('4 / 4')).toBeInTheDocument();
    await user.click(within(row).getByRole('button', { name: '다시 만들기' }));
    await waitFor(() => expect(mode).toBe('rebuild'));
  });
});

describe('엔티티·관계 탭', () => {
  it('행을 펼치면 별칭·관계·근거 미리보기를 보여 준다', async () => {
    renderPage();
    const user = await openTab('엔티티·관계');
    await user.click(await screen.findByRole('button', { name: /운전자금대출/ }));
    expect(await screen.findByText('운전자금 대출')).toBeInTheDocument();
    expect(screen.getByText('연매출액의 30%')).toBeInTheDocument();
    expect(screen.getByText(/연매출액의 30% 이내로 한다/)).toBeInTheDocument();
  });
});

describe('주제 탭', () => {
  it('대분류 아래 소분류를 보여 주고, 검토 대기 주제를 표시한다', async () => {
    renderPage();
    await openTab('주제');
    const loan = (await screen.findByText('여신관리')).closest('li') as HTMLElement;
    expect(within(loan).getByText('기업대출 심사기준')).toBeInTheDocument();
    expect(screen.getAllByText('검토 대기').length).toBeGreaterThanOrEqual(2);
  });

  it('대분류를 추가하면 POST 로 보낸다', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_TOPICS}`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 't-n', name: '고객', level: 1 }, { status: 201 });
      })
    );
    renderPage();
    const user = await openTab('주제');
    await user.type(await screen.findByLabelText('새 주제 이름'), '고객');
    await user.click(screen.getByRole('button', { name: '주제 추가' }));
    await waitFor(() => expect(body).toMatchObject({ name: '고객', level: 1 }));
  });
});

describe('검색 테스트 탭 (L2 #5)', () => {
  it('질문을 실행하면 주제 범위·연결 엔티티·경로·3열 결과를 보여 준다', async () => {
    renderPage();
    const user = await openTab('검색 테스트');
    await user.type(await screen.findByLabelText('질문'), '운전자금대출 한도는?');
    await user.click(screen.getByRole('button', { name: '실행' }));
    expect(await screen.findByText('여신관리')).toBeInTheDocument();
    expect(screen.getByText(/정확 일치/)).toBeInTheDocument();
    expect(screen.getByText(/운전자금대출 → 한도→ → 연매출액의 30%/)).toBeInTheDocument();
    for (const title of ['그래프', '하이브리드', '결합']) {
      expect(screen.getByRole('region', { name: title })).toBeInTheDocument();
    }
    expect(screen.getByText(/권한 필터로 제외 1건/)).toBeInTheDocument();
  });
});

describe('검토 큐 탭 (L2 #6)', () => {
  it('거절 시 다른 후보를 고르면 그 id 로 재연결을 요청한다', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/admin/graph-rag/review/:id/reject', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ entity_id: 'ent-2' });
      })
    );
    renderPage();
    const user = await openTab(/검토 큐/);
    await user.click(await screen.findByRole('button', { name: '거절' }));
    await user.click(screen.getByRole('radio', { name: /시설자금 한도/ }));
    await user.type(screen.getByLabelText('메모'), '다른 개념');
    await user.click(screen.getByRole('button', { name: '거절 확인' }));
    await waitFor(() =>
      expect(body).toEqual({ target_entity_id: 'ent-2', note: '다른 개념' })
    );
  });

  it('승인하면 approve 를 호출한다', async () => {
    let called = false;
    server.use(
      http.post('*/api/v1/admin/graph-rag/review/:id/approve', () => {
        called = true;
        return new HttpResponse(null, { status: 204 });
      })
    );
    renderPage();
    const user = await openTab(/검토 큐/);
    await user.click(await screen.findByRole('button', { name: '승인' }));
    await waitFor(() => expect(called).toBe(true));
  });
});

describe('단계 변경 (L2 #7)', () => {
  it('전체 공개로 바꿀 때 평가를 고르지 않으면 사유가 필수이고 버튼이 "강제 전환"이다', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_STAGE}`, async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(mockGraphSettings({ rollout_stage: 'general' }));
      })
    );
    const user = userEvent.setup();
    renderPage();
    await user.selectOptions(await screen.findByLabelText('노출 단계'), 'general');
    const dialog = await screen.findByRole('dialog');
    const confirm = within(dialog).getByRole('button', { name: '강제 전환' });
    expect(confirm).toBeDisabled();
    await user.type(within(dialog).getByLabelText('강제 전환 사유'), '평가 일정 전 내부 시연');
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() =>
      expect(body).toMatchObject({ to_stage: 'general', force_reason: '평가 일정 전 내부 시연' })
    );
  });

  it('관리자 테스트로 바꿀 때는 조건 없이 확인만 받는다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.ADMIN_GRAPH_RAG_SETTINGS}`, () =>
        HttpResponse.json(mockGraphSettings({ rollout_stage: 'off' }))
      )
    );
    const user = userEvent.setup();
    renderPage();
    await user.selectOptions(await screen.findByLabelText('노출 단계'), 'admin_only');
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByLabelText('강제 전환 사유')).toBeNull();
    expect(within(dialog).getByRole('button', { name: '변경' })).toBeEnabled();
  });
});
