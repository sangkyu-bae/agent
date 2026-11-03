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

// ── kb-profile-selector Design §8.3 ───────────────────────────────

describe('KbChunkingSettingsCard — 프로파일 선택', () => {
  const clauseKb: KnowledgeBaseInfo = {
    ...baseKb,
    use_clause_chunking: true,
    chunking_profile_id: 'prof-contract',
    chunk_size: 700,
    chunk_overlap: 0,
  };

  const countProfileCalls = () => {
    const counter = { calls: 0 };
    server.events.on('request:start', ({ request }) => {
      if (new URL(request.url).pathname === API_ENDPOINTS.CHUNKING_PROFILES) {
        counter.calls += 1;
      }
    });
    return counter;
  };

  const capturePatch = () => {
    const capture: { body: Record<string, unknown> | null } = { body: null };
    server.use(
      http.patch(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_CHUNKING(KB_ID)}`,
        async ({ request }) => {
          capture.body = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({ ...clauseKb });
        },
      ),
    );
    return capture;
  };

  const openModal = () =>
    userEvent.click(screen.getByRole('button', { name: '설정 변경' }));

  const profileCombobox = () =>
    screen.findByRole('combobox', { name: '청킹 프로파일' });

  afterEach(() => server.events.removeAllListeners());

  it('K1: 기본 모드 KB는 프로파일 목록을 조회하지 않는다', async () => {
    const counter = countProfileCalls();
    renderCard();

    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(counter.calls).toBe(0);
  });

  it('K2: 조항 모드 KB는 카드에 적용 프로파일 이름을 표시한다', async () => {
    renderCard(clauseKb);

    expect(
      await screen.findByText('조항 단위 청킹 — 계약서'),
    ).toBeInTheDocument();
  });

  it('K3: 프로파일을 바꿔 저장하면 새 ID를 보내고 오버라이드를 유지한다', async () => {
    const capture = capturePatch();
    renderCard(clauseKb);

    await openModal();
    await userEvent.click(await profileCombobox());
    await userEvent.click(
      screen.getByRole('option', { name: /금융 조항 기본.*기본\]/ }),
    );
    await userEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(capture.body).not.toBeNull());
    expect(capture.body).toMatchObject({
      use_clause_chunking: true,
      chunking_profile_id: 'prof-default',
      chunk_size: 700,
      chunk_overlap: 0,
    });
  });

  it('K4: 삭제된 프로파일을 참조한 KB는 null로 저장한다', async () => {
    const capture = capturePatch();
    renderCard({ ...clauseKb, chunking_profile_id: 'prof-deleted' });

    await openModal();
    await screen.findByText(/삭제되어 기본 프로파일로 처리됩니다/);
    await userEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(capture.body).not.toBeNull());
    expect(capture.body).toMatchObject({
      use_clause_chunking: true,
      chunking_profile_id: null,
    });
  });

  it('K5: 목록 조회 실패 중 저장하면 기존 지정을 유지한다', async () => {
    const capture = capturePatch();
    server.use(
      http.get(`*${API_ENDPOINTS.CHUNKING_PROFILES}`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    );
    renderCard(clauseKb);

    await openModal();
    await screen.findByText(/저장해도 현재 지정은 유지됩니다/);
    expect(screen.getByText('조항 단위 청킹 (프로파일 기반)')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(capture.body).not.toBeNull());
    expect(capture.body).toMatchObject({
      chunking_profile_id: 'prof-contract',
    });
  });

  it('K6: 모드를 바꿨다 돌아와도 선택값을 유지한다', async () => {
    renderCard({ ...clauseKb, chunking_profile_id: null });

    await openModal();
    await userEvent.click(await profileCombobox());
    await userEvent.click(screen.getByRole('option', { name: '계약서' }));
    await userEvent.click(screen.getByRole('radio', { name: /커스텀 청킹/ }));
    await userEvent.click(
      screen.getByRole('radio', { name: /조항 단위 청킹/ }),
    );

    expect(await profileCombobox()).toHaveTextContent('계약서');
  });

  it('K7: 취소 후 다시 열면 KB 저장값으로 초기화한다', async () => {
    renderCard(clauseKb);

    await openModal();
    await userEvent.click(await profileCombobox());
    await userEvent.click(
      screen.getByRole('option', { name: /기본 프로파일 따름/ }),
    );
    await userEvent.click(screen.getByRole('button', { name: '취소' }));
    await openModal();

    expect(await profileCombobox()).toHaveTextContent('계약서');
  });

  it('K8: 조항에서 기본으로 바꾸면 프로파일과 오버라이드를 null로 보낸다', async () => {
    const capture = capturePatch();
    renderCard(clauseKb);

    await openModal();
    await userEvent.click(screen.getByRole('radio', { name: /기본 청킹/ }));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(capture.body).not.toBeNull());
    expect(capture.body).toMatchObject({
      use_clause_chunking: false,
      chunking_profile_id: null,
      chunk_size: null,
      chunk_overlap: null,
    });
  });

  it('K9: 저장이 404면 메시지를 표시하고 목록을 다시 조회한다', async () => {
    server.use(
      http.patch(`*${API_ENDPOINTS.KNOWLEDGE_BASE_CHUNKING(KB_ID)}`, () =>
        HttpResponse.json(
          { detail: "Chunking profile 'prof-contract' not found" },
          { status: 404 },
        ),
      ),
    );
    const counter = countProfileCalls();
    renderCard(clauseKb);

    await openModal();
    await screen.findByText(/경계 규칙 1개/);
    await userEvent.click(screen.getByRole('button', { name: '저장' }));

    expect(await screen.findByText(/not found/)).toBeInTheDocument();
    await waitFor(() => expect(counter.calls).toBe(2));
  });
});
