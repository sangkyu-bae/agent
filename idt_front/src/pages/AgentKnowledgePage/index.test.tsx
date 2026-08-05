// wiki-user-facing: 에이전트 지식 브라우저 — 트리·문서 뷰·소유자 전용 UI.
import { QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { delay, http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { queryClient } from '@/lib/queryClient';
import { useAuthStore } from '@/store/authStore';
import AgentKnowledgePage from './index';

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  useAuthStore.setState({ user: null });
});
afterAll(() => server.close());

const renderPage = (agentId = 'agent-1') => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <MemoryRouter initialEntries={[`/agents/${agentId}/knowledge`]}>
        <Routes>
          <Route
            path="/agents/:agentId/knowledge"
            element={<AgentKnowledgePage />}
          />
        </Routes>
      </MemoryRouter>
    </Wrapper>,
  );
};

const loginAsOwner = () => {
  // 에이전트 상세 mock의 owner_user_id='user-1'과 일치하도록 오버라이드
  useAuthStore.setState({
    user: {
      id: 1, email: 'owner@test.com', role: 'user', status: 'approved',
    } as never,
  });
  server.use(
    http.get('*/api/v1/agents/:agentId', ({ params }) =>
      HttpResponse.json({
        agent_id: params.agentId as string,
        name: '문서 분석가',
        description: '',
        visibility: 'public',
        department_name: null,
        temperature: 0.7,
        owner_user_id: '1',
        can_edit: true,
        can_delete: true,
        created_at: '2026-04-20T10:00:00Z',
      }),
    ),
  );
};

describe('AgentKnowledgePage', () => {
  it('path가 / 단위 중첩 폴더로 렌더되고 미분류 그룹이 표시된다', async () => {
    renderPage();
    // "여신/한도" → 📁 여신 > 📁 한도 중첩 (설계 결정 ⑥)
    expect(await screen.findByText('📁 여신')).toBeInTheDocument();
    expect(screen.getByText('📁 한도')).toBeInTheDocument();
    expect(screen.queryByText('📁 여신/한도')).not.toBeInTheDocument();
    expect(screen.getByText('📁 미분류')).toBeInTheDocument();
    expect(screen.getByText('위키-w1')).toBeInTheDocument();
  });

  it('워크스페이스 링크가 렌더된다 (agent-workspace-view)', async () => {
    renderPage();
    const link = await screen.findByRole('link', { name: /워크스페이스/ });
    expect(link).toHaveAttribute('href', '/agents/agent-1/workspace');
  });

  it('문서 선택 시 본문·출처·갱신일이 표시된다', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByText('위키-w1'));
    expect(await screen.findByText('정제된 본문')).toBeInTheDocument();
    // FR-06: 출처(source_refs)와 갱신일 노출
    expect(screen.getByText(/출처: doc:1/)).toBeInTheDocument();
    expect(screen.getByText(/2026-06-30/)).toBeInTheDocument();
  });

  it('비소유자에게는 문서 작성 버튼이 보이지 않는다', async () => {
    renderPage();
    await screen.findByText('📁 여신');
    expect(screen.queryByText('문서 작성')).not.toBeInTheDocument();
  });

  it('소유자에게는 문서 작성 버튼이 보이고 폼이 열린다', async () => {
    loginAsOwner();
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByText('문서 작성'));
    expect(screen.getByLabelText('제목')).toBeInTheDocument();
    expect(screen.getByLabelText('본문')).toBeInTheDocument();
    expect(screen.getByLabelText('분류 경로')).toBeInTheDocument();
  });

  it('작성 폼 저장 시 목록 화면으로 돌아온다', async () => {
    loginAsOwner();
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByText('문서 작성'));
    await user.type(screen.getByLabelText('제목'), '새 용어');
    await user.type(screen.getByLabelText('본문'), '용어 정의 본문');
    await user.click(screen.getByText('저장'));
    expect(
      await screen.findByText('왼쪽 트리에서 문서를 선택하세요.'),
    ).toBeInTheDocument();
  });
});

// mutation-pending-guard: 저장 중복 제출 방지 + 실패 표면화
describe('AgentKnowledgePage — mutation pending guard', () => {
  const openFormAndFill = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(await screen.findByText('문서 작성'));
    await user.type(screen.getByLabelText('제목'), '새 용어');
    await user.type(screen.getByLabelText('본문'), '용어 정의 본문');
  };

  it('K1+K2: 저장 대기 중 버튼이 비활성화되고 이중 클릭해도 POST는 1회만 발생한다', async () => {
    let createCalls = 0;
    server.use(
      http.post('*/api/v1/wiki', async () => {
        createCalls += 1;
        await delay(150);
        return HttpResponse.json({ id: 'w-new' }, { status: 201 });
      }),
    );
    loginAsOwner();
    const user = userEvent.setup();
    renderPage();
    await openFormAndFill(user);

    await user.click(screen.getByText('저장'));
    // K2: 대기 중 상태 — "저장 중…" 문구 + disabled
    const pendingButton = await screen.findByRole('button', {
      name: '저장 중…',
    });
    expect(pendingButton).toBeDisabled();
    // K1: 대기 중 재클릭 (disabled라 무시되어야 함)
    await user.click(pendingButton);

    expect(
      await screen.findByText('왼쪽 트리에서 문서를 선택하세요.'),
    ).toBeInTheDocument();
    expect(createCalls).toBe(1);
  });

  it('K3: 저장 실패 시 인라인 에러가 표시되고 폼과 입력값이 보존된다', async () => {
    server.use(
      http.post('*/api/v1/wiki', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    loginAsOwner();
    const user = userEvent.setup();
    renderPage();
    await openFormAndFill(user);

    await user.click(screen.getByText('저장'));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      '저장에 실패했습니다',
    );
    // 폼 유지 + 입력 보존
    expect(screen.getByLabelText('제목')).toHaveValue('새 용어');
    expect(screen.getByLabelText('본문')).toHaveValue('용어 정의 본문');
  });

  it('K4: 실패 후 재시도 성공 시 에러가 사라지고 폼이 닫힌다', async () => {
    server.use(
      http.post('*/api/v1/wiki', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    loginAsOwner();
    const user = userEvent.setup();
    renderPage();
    await openFormAndFill(user);

    await user.click(screen.getByText('저장'));
    await screen.findByRole('alert');

    // 서버 복구 시나리오 — 성공 핸들러로 교체 후 재시도
    server.use(
      http.post('*/api/v1/wiki', () =>
        HttpResponse.json({ id: 'w-new' }, { status: 201 }),
      ),
    );
    await user.click(screen.getByText('저장'));
    expect(
      await screen.findByText('왼쪽 트리에서 문서를 선택하세요.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('K5: 실패 후 취소하고 다시 열면 에러가 남아있지 않다', async () => {
    server.use(
      http.post('*/api/v1/wiki', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    loginAsOwner();
    const user = userEvent.setup();
    renderPage();
    await openFormAndFill(user);

    await user.click(screen.getByText('저장'));
    await screen.findByRole('alert');

    await user.click(screen.getByText('취소'));
    expect(
      await screen.findByText('왼쪽 트리에서 문서를 선택하세요.'),
    ).toBeInTheDocument();

    await user.click(screen.getByText('문서 작성'));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

// knowledge-deprecate-visibility: 폐기 성공 시 선택 해제 + 트리 제거
describe('AgentKnowledgePage — deprecate visibility', () => {
  // invalidateWiki는 전역 queryClient(@/lib/queryClient)를 무효화하므로,
  // 재조회 검증은 프로덕션 배선(main.tsx)과 동일하게 전역 클라이언트를 주입한다
  const renderWithGlobalClient = (agentId = 'agent-1') =>
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/agents/${agentId}/knowledge`]}>
          <Routes>
            <Route
              path="/agents/:agentId/knowledge"
              element={<AgentKnowledgePage />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

  afterEach(() => {
    // 전역 클라이언트 공유 오염 방지 — 관측자 리패치가 일어나지 않도록
    // 반드시 언마운트(cleanup) 후에 캐시를 비운다
    cleanup();
    queryClient.clear();
  });

  // 폐기 버튼은 소유자 + source_type='human'에서만 렌더 — 기본 mock(distilled) 오버라이드
  const humanArticle = (id: string, status = 'approved') => ({
    id,
    agent_id: 'agent-1',
    title: `위키-${id}`,
    content: '정제된 본문',
    source_type: 'human',
    source_refs: ['doc:1'],
    status,
    confidence: 0.8,
    valid_until: null,
    version: 1,
    editor_id: null,
    reviewer_id: null,
    created_at: '2026-06-30T00:00:00Z',
    updated_at: '2026-06-30T00:00:00Z',
    path: '여신/한도',
  });

  const treeWith = (items: Array<{ id: string; title: string }>) => ({
    agent_id: 'agent-1',
    groups: items.length
      ? [
          {
            path: '여신/한도',
            items: items.map(({ id, title }) => ({
              id,
              title,
              status: 'approved',
              source_type: 'human',
              updated_at: '2026-07-18T00:00:00Z',
            })),
          },
        ]
      : [],
    total: items.length,
  });

  /** 폐기 PATCH 성공 시 이후 tree 재조회에서 해당 문서가 빠지는 서버 상태를 모사.
   *  MSW 런타임 핸들러는 등록 순으로 우선 매칭 — tree를 ':id'보다 먼저 선언한다. */
  const setupDeprecableServer = () => {
    loginAsOwner();
    let deprecated = false;
    server.use(
      http.get(`*${API_ENDPOINTS.WIKI_TREE}`, () =>
        HttpResponse.json(
          deprecated
            ? treeWith([])
            : treeWith([{ id: 'w1', title: '위키-w1' }]),
        ),
      ),
      http.get('*/api/v1/wiki/:id', ({ params }) =>
        HttpResponse.json(humanArticle(String(params.id))),
      ),
      http.patch('*/api/v1/wiki/:id/deprecate', ({ params }) => {
        deprecated = true;
        return HttpResponse.json(humanArticle(String(params.id), 'deprecated'));
      }),
    );
  };

  const selectAndDeprecate = async (
    user: ReturnType<typeof userEvent.setup>,
  ) => {
    await user.click(await screen.findByText('위키-w1'));
    await user.click(await screen.findByRole('button', { name: '폐기' }));
  };

  it('F1: 폐기 성공 시 본문 패널이 초기 문구로 복귀한다', async () => {
    setupDeprecableServer();
    const user = userEvent.setup();
    renderWithGlobalClient();

    await selectAndDeprecate(user);
    expect(
      await screen.findByText('왼쪽 트리에서 문서를 선택하세요.'),
    ).toBeInTheDocument();
  });

  it('F2: 폐기 성공 시 트리 재조회에서 항목이 사라진다', async () => {
    setupDeprecableServer();
    const user = userEvent.setup();
    renderWithGlobalClient();

    await selectAndDeprecate(user);
    await waitFor(() =>
      expect(screen.queryByText('위키-w1')).not.toBeInTheDocument(),
    );
  });

  it('F3: 폐기 실패 시 문서와 선택이 유지된다', async () => {
    setupDeprecableServer();
    server.use(
      http.patch('*/api/v1/wiki/:id/deprecate', () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderWithGlobalClient();

    await selectAndDeprecate(user);
    // 대기 상태 해제 후에도 본문·트리 항목 유지 (onSuccess 미실행)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '폐기' })).toBeEnabled(),
    );
    expect(screen.getByText('정제된 본문')).toBeInTheDocument();
    // 트리 항목(button)과 본문 제목(h3) 모두 유지 — 트리는 role로 특정
    expect(
      screen.getByRole('button', { name: '위키-w1' }),
    ).toBeInTheDocument();
  });
});
