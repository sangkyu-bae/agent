/**
 * KbChunkingSettingsCard 테스트 (kb-custom-chunking Design §8.2)
 *
 * 현재 설정 요약, 수정 모달 프리필, PATCH 호출, 안내 문구.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
} from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import type { KnowledgeBaseInfo } from '@/types/ragToolConfig';
import KbChunkingSettingsCard from './KbChunkingSettingsCard';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const KB_ID = 'kb-1';

const baseKb: KnowledgeBaseInfo = {
  kb_id: KB_ID,
  name: '여신 규정집',
  scope: 'PERSONAL',
  collection_name: 'shared-col',
  use_clause_chunking: false,
  use_custom_chunking: false,
};

const customKb: KnowledgeBaseInfo = {
  ...baseKb,
  use_custom_chunking: true,
  custom_chunking_config: {
    version: 1,
    strategy: 'boundary_pattern',
    chunk_size: 600,
    chunk_overlap: 80,
    parent_chunk_size: 3000,
    boundary_rules: [
      { pattern: '^제\\d+장', priority: 1, level: 'parent' },
    ],
  },
};

const renderCard = (kb: KnowledgeBaseInfo = baseKb) =>
  render(<KbChunkingSettingsCard kb={kb} />, { wrapper: createWrapper() });

describe('KbChunkingSettingsCard — 요약 표시', () => {
  it('기본 청킹 KB는 기본 요약을 보여준다', () => {
    renderCard();
    expect(screen.getByText(/기본 청킹/)).toBeInTheDocument();
  });

  it('커스텀 KB는 전략·크기·규칙 수를 보여준다', () => {
    renderCard(customKb);
    expect(screen.getByText(/커스텀 — 경계 패턴/)).toBeInTheDocument();
    expect(screen.getByText(/크기 600/)).toBeInTheDocument();
    expect(screen.getByText(/규칙 1개/)).toBeInTheDocument();
  });
});

describe('KbChunkingSettingsCard — 설정 변경', () => {
  it('수정 모달에 기존 문서 미적용 안내가 노출된다 (D10)', async () => {
    renderCard(customKb);
    await userEvent.click(screen.getByRole('button', { name: '설정 변경' }));
    expect(
      screen.getByText(/기존 문서는 다시 청킹되지 않습니다/),
    ).toBeInTheDocument();
  });

  it('저장 시 PATCH가 전체 교체 body로 호출되고 모달이 닫힌다', async () => {
    let received: unknown = null;
    server.use(
      http.patch(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_CHUNKING(KB_ID)}`,
        async ({ request }) => {
          received = await request.json();
          return HttpResponse.json({ ...customKb });
        },
      ),
    );
    renderCard(customKb);

    await userEvent.click(screen.getByRole('button', { name: '설정 변경' }));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: '저장' }),
      ).not.toBeInTheDocument(),
    );
    expect(received).toMatchObject({
      use_clause_chunking: false,
      use_custom_chunking: true,
      custom_chunking_config: {
        version: 1,
        strategy: 'boundary_pattern',
        chunk_size: 600,
        chunk_overlap: 80,
        parent_chunk_size: 3000,
      },
    });
  });

  it('서버 422 detail을 에러로 표시하고 모달을 유지한다', async () => {
    server.use(
      http.patch(`*${API_ENDPOINTS.KNOWLEDGE_BASE_CHUNKING(KB_ID)}`, () =>
        HttpResponse.json(
          { detail: "invalid regex pattern '[unclosed'" },
          { status: 422 },
        ),
      ),
    );
    renderCard(customKb);

    await userEvent.click(screen.getByRole('button', { name: '설정 변경' }));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));

    expect(
      await screen.findByText(/invalid regex pattern/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '저장' })).toBeInTheDocument();
  });

  it('기본 청킹으로 전환하면 커스텀 필드가 null로 초기화된다', async () => {
    let received: Record<string, unknown> | null = null;
    server.use(
      http.patch(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_CHUNKING(KB_ID)}`,
        async ({ request }) => {
          received = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({ ...baseKb });
        },
      ),
    );
    renderCard(customKb);

    await userEvent.click(screen.getByRole('button', { name: '설정 변경' }));
    await userEvent.click(screen.getByRole('radio', { name: /기본 청킹/ }));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(received).not.toBeNull());
    expect(received).toMatchObject({
      use_clause_chunking: false,
      use_custom_chunking: false,
      custom_chunking_config: null,
    });
  });
});
