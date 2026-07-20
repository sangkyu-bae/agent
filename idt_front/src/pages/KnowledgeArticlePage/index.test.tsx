// wiki-user-facing: 위키 문서 단독 뷰 (근거 배지 착지점).
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import KnowledgeArticlePage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPage = (articleId = 'w1') => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <MemoryRouter initialEntries={[`/knowledge/${articleId}`]}>
        <Routes>
          <Route path="/knowledge/:articleId" element={<KnowledgeArticlePage />} />
        </Routes>
      </MemoryRouter>
    </Wrapper>,
  );
};

describe('KnowledgeArticlePage', () => {
  it('문서 제목·본문·출처·갱신일·전체 지식 링크가 렌더된다', async () => {
    renderPage('w1');
    expect(await screen.findByText('위키-w1')).toBeInTheDocument();
    expect(screen.getByText('정제된 본문')).toBeInTheDocument();
    expect(screen.getByText(/출처: doc:1/)).toBeInTheDocument();
    expect(screen.getByText(/2026-06-30/)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /전체 지식 보기/ });
    expect(link).toHaveAttribute('href', '/agents/agent-1/knowledge');
  });

  it('404면 안내 문구를 보여준다', async () => {
    server.use(
      http.get('*/api/v1/wiki/:id', () =>
        HttpResponse.json({ detail: 'not found' }, { status: 404 }),
      ),
    );
    renderPage('missing');
    expect(
      await screen.findByText(/문서를 찾을 수 없습니다/),
    ).toBeInTheDocument();
  });
});
