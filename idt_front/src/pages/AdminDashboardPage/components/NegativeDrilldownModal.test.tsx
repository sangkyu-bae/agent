// negative-feedback-drilldown Design §8.4: 드릴다운 모달 상태별 표시.
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import type { NegativeDrilldown, RecentNegativeItem } from '@/types/messageFeedback';
import NegativeDrilldownModal from './NegativeDrilldownModal';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const URL = '*/api/v1/admin/eval/negative/284/drilldown';
const RUN_ID = '5a7d6c11-ecc1-4b05-8fea-66b4123e4f1f';

const item: RecentNegativeItem = {
  message_id: 284,
  agent_id: 'agent-1',
  comment: '답변이 틀림',
  created_at: '2026-10-20T05:03:00Z',
};

const source = {
  id: 's1',
  collection_name: 'policy-kb',
  document_id: 'd1',
  chunk_id: 'c1',
  score: 0.8123,
  rank_index: 1, // 백엔드가 enumerate(start=1)로 저장한다
  content_preview: '여신 규정 제3조',
  created_at: '2026-10-20T05:03:00Z',
};

const drilldown: NegativeDrilldown = {
  message_id: 284,
  agent_id: 'agent-1',
  question: '한도가 얼마인가요?',
  answer: '**한도는** 1억원입니다.',
  runs: [
    {
      run_id: RUN_ID,
      agent_id: 'agent-1',
      langsmith_run_url: 'https://smith.example/run/1',
      groups: [
        {
          search_query: '여신 한도 규정',
          query_source: 'rewrite',
          search_mode: 'hybrid',
          sources: [source],
        },
      ],
    },
  ],
};

const mockDrilldown = (body: Partial<NegativeDrilldown>) =>
  server.use(http.get(URL, () => HttpResponse.json({ ...drilldown, ...body })));

const renderModal = (target: RecentNegativeItem = item, onClose = vi.fn()) => {
  const Wrapper = createWrapper();
  render(
    <Wrapper>
      <MemoryRouter>
        <NegativeDrilldownModal item={target} onClose={onClose} />
      </MemoryRouter>
    </Wrapper>,
  );
  return onClose;
};

describe('NegativeDrilldownModal', () => {
  it('로딩 중에는 안내를 표시한다', () => {
    server.use(
      http.get(URL, async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return HttpResponse.json(drilldown);
      }),
    );
    renderModal();

    expect(screen.getByText('불러오는 중…')).toBeInTheDocument();
  });

  it('제목과 에이전트, 이유, 질문, 답변을 표시한다', async () => {
    mockDrilldown({});
    renderModal();

    const dialog = await screen.findByRole('dialog', { name: '답변 드릴다운' });
    expect(within(dialog).getByText(/agent-1/)).toBeInTheDocument();
    expect(await screen.findByText('한도가 얼마인가요?')).toBeInTheDocument();
    expect(screen.getByText('답변이 틀림')).toBeInTheDocument();
  });

  it('답변을 마크다운으로 렌더링한다', async () => {
    mockDrilldown({});
    renderModal();

    const bold = await screen.findByText('한도는');
    expect(bold.tagName).toBe('STRONG');
  });

  it('이유가 없으면 코멘트 없음으로 표시한다', async () => {
    mockDrilldown({});
    renderModal({ ...item, comment: null });

    expect(await screen.findByText('코멘트 없음')).toBeInTheDocument();
  });

  it('런 상세 링크가 해당 런으로 연결된다', async () => {
    mockDrilldown({});
    renderModal();

    const link = await screen.findByRole('link', { name: '런 상세' });
    expect(link).toHaveAttribute('href', `/admin/agent-runs/${RUN_ID}`);
  });

  it('LangSmith 링크는 새 탭으로 연다', async () => {
    mockDrilldown({});
    renderModal();

    const link = await screen.findByRole('link', { name: 'LangSmith' });
    expect(link).toHaveAttribute('href', 'https://smith.example/run/1');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('langsmith_run_url이 없으면 링크를 표시하지 않는다', async () => {
    mockDrilldown({ runs: [{ ...drilldown.runs[0], langsmith_run_url: null }] });
    renderModal();

    await screen.findByRole('link', { name: '런 상세' });
    expect(screen.queryByRole('link', { name: 'LangSmith' })).not.toBeInTheDocument();
  });

  it('재작성 쿼리별 근거 문서를 표시한다', async () => {
    mockDrilldown({});
    renderModal();

    expect(await screen.findByText(/여신 한도 규정/)).toBeInTheDocument();
    expect(screen.getByText(/hybrid/)).toBeInTheDocument();
    expect(screen.getByText(/policy-kb/)).toHaveTextContent('1. policy-kb · 0.81');
    expect(screen.getByText('여신 규정 제3조')).toBeInTheDocument();
  });

  it('런은 있으나 근거가 없으면 검색 미사용으로 표시한다', async () => {
    mockDrilldown({ runs: [{ ...drilldown.runs[0], groups: [] }] });
    renderModal();

    expect(
      await screen.findByText('이 실행은 문서 검색을 사용하지 않았습니다'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '런 상세' })).toBeInTheDocument();
  });

  it('질문은 있으나 런이 없으면 실행 기록 없음으로 표시한다', async () => {
    mockDrilldown({ runs: [] });
    renderModal();

    expect(await screen.findByText('연결된 실행 기록이 없습니다')).toBeInTheDocument();
  });

  it('질문 복원에 실패해도 답변은 표시한다', async () => {
    mockDrilldown({ question: null, runs: [] });
    renderModal();

    expect(await screen.findByText('질문을 찾지 못했습니다')).toBeInTheDocument();
    expect(screen.getByText('한도는')).toBeInTheDocument();
    expect(screen.queryByText('연결된 실행 기록이 없습니다')).not.toBeInTheDocument();
  });

  it('404면 원본 없음을 표시하고 재시도 버튼을 두지 않는다', async () => {
    server.use(
      http.get(URL, () =>
        HttpResponse.json({ detail: '메시지를 찾을 수 없습니다.' }, { status: 404 }),
      ),
    );
    renderModal();

    expect(await screen.findByText('원본 대화를 찾을 수 없습니다')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '다시 시도' })).not.toBeInTheDocument();
  });

  it('서버 오류 후 다시 시도하면 본문을 표시한다', async () => {
    let calls = 0;
    server.use(
      http.get(URL, () => {
        calls += 1;
        return calls === 1
          ? HttpResponse.json({ detail: 'boom' }, { status: 500 })
          : HttpResponse.json(drilldown);
      }),
    );
    renderModal();

    expect(await screen.findByText('불러오지 못했습니다')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));

    expect(await screen.findByText('한도가 얼마인가요?')).toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it('닫기 버튼을 누르면 onClose를 호출한다', async () => {
    mockDrilldown({});
    const onClose = renderModal();

    await userEvent.click(await screen.findByRole('button', { name: '닫기' }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
