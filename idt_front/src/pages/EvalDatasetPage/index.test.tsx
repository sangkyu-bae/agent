// eval-hub: 평가 허브 탭 전환·admin 대시보드 가시성
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { useAuthStore } from '@/store/authStore';
import EvalDatasetPage from './index';

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => {
  server.resetHandlers();
  useAuthStore.setState({ user: null });
});
afterAll(() => server.close());

const emptyPage = { items: [], total: 0, limit: 20, offset: 0 };

const stubApis = () => {
  server.use(
    http.get('*/api/ragas/testsets', () => HttpResponse.json(emptyPage)),
    http.get('*/api/ragas/runs', () => HttpResponse.json(emptyPage)),
    http.get('*/api/ragas/metrics', () => HttpResponse.json([])),
    http.get('*/api/v1/admin/ragas/dashboard', () =>
      HttpResponse.json({
        total_runs: 3,
        status_counts: { completed: 2 },
        target_type_counts: { rag: 3 },
        avg_metrics: {},
        recent_runs: [],
      }),
    ),
  );
};

const renderPage = (initialEntry = '/eval-dataset') => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <MemoryRouter initialEntries={[initialEntry]}>
        <EvalDatasetPage />
      </MemoryRouter>
    </Wrapper>,
  );
};

const loginAs = (role: 'user' | 'admin') => {
  useAuthStore.setState({
    user: { id: 1, email: 'u@test.com', role, status: 'approved' } as never,
  });
};

describe('EvalDatasetPage 탭', () => {
  it('기본은 데이터셋 탭이 활성', async () => {
    stubApis();
    loginAs('user');
    renderPage();
    expect(
      await screen.findByText('사용 가능한 데이터셋이 없습니다.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '데이터셋' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('평가기 탭 전환 시 메트릭 카탈로그 설명 표시', async () => {
    stubApis();
    loginAs('user');
    renderPage();
    await userEvent.click(screen.getByRole('tab', { name: '평가기' }));
    expect(
      await screen.findByText(/내장 평가기\(메트릭\) 목록/),
    ).toBeInTheDocument();
  });

  it('일반 사용자에게 대시보드 탭 미노출', async () => {
    stubApis();
    loginAs('user');
    renderPage();
    await screen.findByText('사용 가능한 데이터셋이 없습니다.');
    expect(screen.queryByRole('tab', { name: '대시보드' })).not.toBeInTheDocument();
  });

  it('admin은 대시보드 탭 노출·조회 가능', async () => {
    stubApis();
    loginAs('admin');
    renderPage();
    await userEvent.click(await screen.findByRole('tab', { name: '대시보드' }));
    expect(await screen.findByText('총 실행')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('일반 사용자가 ?tab=dashboard 직접 진입 시 데이터셋으로 폴백', async () => {
    stubApis();
    loginAs('user');
    renderPage('/eval-dataset?tab=dashboard');
    expect(
      await screen.findByText('사용 가능한 데이터셋이 없습니다.'),
    ).toBeInTheDocument();
  });
});
