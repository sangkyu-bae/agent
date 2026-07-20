// agent-workspace-view: 에이전트 워크스페이스 — 폴더형 읽기 전용 열람.
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import AgentWorkspacePage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPage = (agentId = 'agent-1') => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <MemoryRouter initialEntries={[`/agents/${agentId}/workspace`]}>
        <Routes>
          <Route
            path="/agents/:agentId/workspace"
            element={<AgentWorkspacePage />}
          />
        </Routes>
      </MemoryRouter>
    </Wrapper>,
  );
};

/** workers에 sub_agent·RAG 설정을 포함한 상세 오버라이드 */
const useRichAgentDetail = (overrides: Record<string, unknown> = {}) => {
  server.use(
    http.get('*/api/v1/agents/:agentId', ({ params }) =>
      HttpResponse.json({
        agent_id: params.agentId as string,
        name: '문서 분석가',
        description: '문서를 분석하는 AI 에이전트',
        system_prompt: '# 역할\n당신은 문서 분석 전문가입니다.',
        tool_ids: ['tool-1'],
        workers: [
          {
            tool_id: 'internal_document_search', worker_id: 'w-1',
            description: '내부 문서 검색', sort_order: 1,
            tool_config: {
              collection_name: 'policy', kb_id: 'kb-1',
              use_wiki_first: true, use_routed_search: false,
            },
            worker_type: 'tool',
          },
          {
            tool_id: 'sub', worker_id: 'w-2', description: '보조 분석',
            sort_order: 2, tool_config: null, worker_type: 'sub_agent',
            ref_agent_id: 'agent-9', ref_agent_name: '요약 전문가',
          },
        ],
        flow_hint: 'sequential',
        llm_model_id: 'gpt-4o',
        status: 'active',
        visibility: 'public',
        department_id: null,
        department_name: null,
        temperature: 0.7,
        owner_user_id: 'user-1',
        can_edit: false,
        can_delete: false,
        created_at: '2026-04-20T10:00:00Z',
        updated_at: '2026-04-20T10:00:00Z',
        ...overrides,
      }),
    ),
  );
};

describe('AgentWorkspacePage', () => {
  it('폴더 6항목과 기본 섹션(지침)을 렌더한다', async () => {
    useRichAgentDetail();
    renderPage();

    expect(await screen.findByText('문서 분석가')).toBeInTheDocument();
    for (const label of ['지침', '도구', '서브에이전트', '스킬', '지식', '정보']) {
      expect(screen.getByRole('button', { name: new RegExp(label) })).toBeInTheDocument();
    }
    // 기본 섹션: 지침 마크다운 헤딩 렌더 (FR-02)
    expect(await screen.findByRole('heading', { name: '역할' })).toBeInTheDocument();
    expect(screen.getByText('당신은 문서 분석 전문가입니다.')).toBeInTheDocument();
  });

  it('도구 섹션: 워커 설명과 RAG 설정 라벨을 표시한다', async () => {
    useRichAgentDetail();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('문서 분석가');

    await user.click(screen.getByRole('button', { name: /도구/ }));

    expect(screen.getByText('내부 문서 검색')).toBeInTheDocument();
    expect(screen.getByText(/policy/)).toBeInTheDocument();       // collection_name
    expect(screen.getByText(/위키 우선/)).toBeInTheDocument();     // use_wiki_first
  });

  it('서브에이전트 섹션: ref_agent_name을 표시한다', async () => {
    useRichAgentDetail();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('문서 분석가');

    await user.click(screen.getByRole('button', { name: /서브에이전트/ }));

    expect(screen.getByText('요약 전문가')).toBeInTheDocument();
  });

  it('서브에이전트 0건이면 "없음"을 표시한다', async () => {
    const user = userEvent.setup();
    renderPage(); // 기본 핸들러 — sub_agent 워커 없음
    await screen.findByText('문서 분석가');

    await user.click(screen.getByRole('button', { name: /서브에이전트/ }));

    expect(screen.getByText(/서브에이전트가 없습니다/)).toBeInTheDocument();
  });

  it('스킬 API 403이면 스킬 폴더만 강등되고 다른 섹션은 정상이다', async () => {
    useRichAgentDetail();
    server.use(
      http.get('*/api/v1/agents/:agentId/skills', () =>
        HttpResponse.json({ detail: 'forbidden' }, { status: 403 }),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('문서 분석가');

    await user.click(screen.getByRole('button', { name: /스킬/ }));
    expect(await screen.findByText(/불러올 수 없습니다/)).toBeInTheDocument();

    // 다른 섹션(지침)은 정상 (FR-05)
    await user.click(screen.getByRole('button', { name: /지침/ }));
    expect(screen.getByText('당신은 문서 분석 전문가입니다.')).toBeInTheDocument();
  });

  it('지식 섹션: 위키 그룹·건수와 전체 보기 링크를 표시한다', async () => {
    useRichAgentDetail();
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('문서 분석가');

    await user.click(screen.getByRole('button', { name: /지식/ }));

    expect(await screen.findByText(/여신\/한도/)).toBeInTheDocument(); // 기존 tree mock
    const link = screen.getByRole('link', { name: /전체 지식 보기/ });
    expect(link).toHaveAttribute('href', '/agents/agent-1/knowledge');
  });

  it('can_edit=false면 수정하기 링크를 노출하지 않는다', async () => {
    useRichAgentDetail({ can_edit: false });
    renderPage();
    await screen.findByText('문서 분석가');

    expect(screen.queryByRole('link', { name: /수정하기/ })).not.toBeInTheDocument();
  });

  it('can_edit=true면 수정하기 링크를 노출한다 (FR-07)', async () => {
    useRichAgentDetail({ can_edit: true });
    renderPage();
    await screen.findByText('문서 분석가');

    expect(screen.getByRole('link', { name: /수정하기/ })).toBeInTheDocument();
  });
});
