// wiki-user-facing: 에이전트 지식 브라우저 — 트리·문서 뷰·소유자 전용 UI.
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
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
