import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  beforeAll,
  beforeEach,
  afterEach,
  afterAll,
  describe,
  it,
  expect,
} from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import AdminChunkingProfilesPage from './index';
import type { ChunkingProfile } from '@/types/chunkingProfile';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const profileA: ChunkingProfile = {
  profile_id: 'prof-1',
  name: '금융 조항 기본',
  description: '조 단위 분할',
  boundary_rules: [
    { pattern: '^제\\s*\\d+\\s*장', priority: 1, level: 'parent' },
    { pattern: '^제\\s*\\d+\\s*조', priority: 1, level: 'child' },
  ],
  parent_chunk_size: 2000,
  chunk_size: 500,
  chunk_overlap: 50,
  is_default: true,
  summary_llm_model_id: 'uuid-1', // GPT-4o (활성)
  created_at: '2026-07-01T00:00:00',
  updated_at: '2026-07-10T00:00:00',
};

const profileB: ChunkingProfile = {
  profile_id: 'prof-2',
  name: '요약 미사용 프로파일',
  description: null,
  boundary_rules: [{ pattern: '^\\d+\\.', priority: 1, level: 'child' }],
  parent_chunk_size: 1500,
  chunk_size: 400,
  chunk_overlap: 40,
  is_default: false,
  summary_llm_model_id: null,
  created_at: '2026-07-02T00:00:00',
  updated_at: '2026-07-11T00:00:00',
};

const profileC: ChunkingProfile = {
  profile_id: 'prof-3',
  name: '비활성 LLM 참조',
  description: null,
  boundary_rules: [{ pattern: '^부칙', priority: 1, level: 'child' }],
  parent_chunk_size: 2000,
  chunk_size: 500,
  chunk_overlap: 50,
  is_default: false,
  summary_llm_model_id: 'uuid-3', // Llama 3 8B (비활성)
  created_at: '2026-07-03T00:00:00',
  updated_at: '2026-07-12T00:00:00',
};

// resetHandlers가 use() 등록분을 지우므로 매 테스트 기본 목록 핸들러 재등록
beforeEach(() => {
  server.use(
    http.get('*/api/v1/admin/chunking/profiles', () =>
      HttpResponse.json({
        profiles: [profileA, profileB, profileC],
        total: 3,
      }),
    ),
  );
});

const renderPage = () =>
  render(<AdminChunkingProfilesPage />, { wrapper: createWrapper() });

describe('AdminChunkingProfilesPage', () => {
  it('P1: 목록 렌더 — 이름·기본 뱃지·요약 LLM 매핑·요약 비활성 표시', async () => {
    renderPage();
    expect(await screen.findByText('금융 조항 기본')).toBeInTheDocument();
    expect(screen.getByText('요약 미사용 프로파일')).toBeInTheDocument();
    expect(screen.getByText('기본')).toBeInTheDocument();
    // summary_llm_model_id → display_name 매핑
    expect(await screen.findByText('GPT-4o')).toBeInTheDocument();
    expect(screen.getByText('요약 비활성')).toBeInTheDocument();
    // 사이즈 요약 표기 (profileA·profileC 동일 사이즈 → 2행)
    expect(
      screen.getAllByText('parent 2000 · chunk 500 · overlap 50'),
    ).toHaveLength(2);
  });

  it('P2: 생성 — 폼 입력 후 POST 바디 검증 + 모달 닫힘', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/v1/admin/chunking/profiles', async ({ request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { ...profileB, profile_id: 'prof-new', name: captured.name as string },
          { status: 201 },
        );
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('금융 조항 기본');

    await user.click(screen.getByRole('button', { name: '프로파일 등록' }));
    await user.type(
      screen.getByPlaceholderText('예: 금융 약관 조항 프로파일'),
      '새 프로파일',
    );
    await user.click(screen.getByRole('button', { name: '규칙 추가' }));
    await user.type(screen.getByLabelText('규칙 1 패턴'), '^부칙');
    // 요약 LLM 지정 (활성 모델)
    await user.selectOptions(screen.getByLabelText('요약 LLM'), 'uuid-1');
    await user.click(screen.getByRole('button', { name: '등록' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toMatchObject({
      name: '새 프로파일',
      description: null,
      parent_chunk_size: 2000,
      chunk_size: 500,
      chunk_overlap: 50,
      is_default: false,
      summary_llm_model_id: 'uuid-1',
    });
    expect(
      (captured as unknown as Record<string, unknown>).boundary_rules,
    ).toEqual([{ pattern: '^부칙', priority: 1, level: 'child' }]);
    await waitFor(() =>
      expect(screen.queryByText('청킹 프로파일 등록')).not.toBeInTheDocument(),
    );
  });

  it('P3: 수정 프리필 — 이름만 바꿔도 PUT 바디에 나머지 필드가 보존된다 (D2)', async () => {
    let captured: Record<string, unknown> | null = null;
    server.use(
      http.put('*/api/v1/admin/chunking/profiles/:id', async ({ params, request }) => {
        captured = (await request.json()) as Record<string, unknown>;
        expect(params.id).toBe('prof-1');
        return HttpResponse.json(profileA);
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('금융 조항 기본');

    await user.click(screen.getByRole('button', { name: '금융 조항 기본 수정' }));
    const nameInput = screen.getByDisplayValue('금융 조항 기본');
    await user.clear(nameInput);
    await user.type(nameInput, '이름 변경됨');
    await user.click(screen.getByRole('button', { name: '저장' }));

    await waitFor(() => expect(captured).not.toBeNull());
    expect(captured).toMatchObject({
      name: '이름 변경됨',
      description: '조 단위 분할',
      parent_chunk_size: 2000,
      chunk_size: 500,
      chunk_overlap: 50,
      is_default: true,
      summary_llm_model_id: 'uuid-1',
    });
    expect(
      (captured as unknown as Record<string, unknown>).boundary_rules,
    ).toHaveLength(2);
  });

  it('P4: 비활성 LLM 참조 프로파일 수정 시 "(비활성)" 옵션으로 값이 유지된다 (D3)', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('비활성 LLM 참조');

    await user.click(
      screen.getByRole('button', { name: '비활성 LLM 참조 수정' }),
    );

    const select = (await screen.findByLabelText('요약 LLM')) as HTMLSelectElement;
    expect(select.value).toBe('uuid-3');
    expect(
      screen.getByRole('option', { name: 'Llama 3 8B (비활성)' }),
    ).toBeInTheDocument();
  });

  it('P5: 필수값 검증 — 이름 누락·규칙 없음·잘못된 정규식은 전송하지 않는다', async () => {
    let posted = false;
    server.use(
      http.post('*/api/v1/admin/chunking/profiles', () => {
        posted = true;
        return HttpResponse.json(profileB, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('금융 조항 기본');

    await user.click(screen.getByRole('button', { name: '프로파일 등록' }));
    // 이름 누락
    await user.click(screen.getByRole('button', { name: '등록' }));
    expect(await screen.findByText('이름은 필수입니다.')).toBeInTheDocument();

    // 이름 입력, 규칙 없음
    await user.type(
      screen.getByPlaceholderText('예: 금융 약관 조항 프로파일'),
      '검증 테스트',
    );
    await user.click(screen.getByRole('button', { name: '등록' }));
    expect(
      await screen.findByText('경계 규칙을 1개 이상 추가하세요.'),
    ).toBeInTheDocument();

    // 잘못된 정규식 — '['는 userEvent 키 디스크립터라 fireEvent로 주입
    await user.click(screen.getByRole('button', { name: '규칙 추가' }));
    fireEvent.change(screen.getByLabelText('규칙 1 패턴'), {
      target: { value: '[미완성' },
    });
    await user.click(screen.getByRole('button', { name: '등록' }));
    expect(
      await screen.findByText('유효하지 않은 정규식 패턴이 있습니다.'),
    ).toBeInTheDocument();

    expect(posted).toBe(false);
  });

  it('P6: 기본 지정 액션 — PUT /default 호출', async () => {
    let calledId: string | null = null;
    server.use(
      http.put('*/api/v1/admin/chunking/profiles/:id/default', ({ params }) => {
        calledId = params.id as string;
        return HttpResponse.json({
          profile_id: params.id,
          message: 'Default profile updated',
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('요약 미사용 프로파일');

    // 기본 프로파일(prof-1)에는 기본 지정 버튼이 없다
    expect(
      screen.queryByRole('button', { name: '금융 조항 기본 기본 지정' }),
    ).not.toBeInTheDocument();

    await user.click(
      screen.getByRole('button', { name: '요약 미사용 프로파일 기본 지정' }),
    );
    await waitFor(() => expect(calledId).toBe('prof-2'));
  });

  it('P7: 삭제 — 확인 다이얼로그(폴백 안내) 후 DELETE 전송', async () => {
    let deletedId: string | null = null;
    server.use(
      http.delete('*/api/v1/admin/chunking/profiles/:id', ({ params }) => {
        deletedId = params.id as string;
        return HttpResponse.json({
          profile_id: params.id,
          message: 'Chunking profile deleted',
        });
      }),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('요약 미사용 프로파일');

    await user.click(
      screen.getByRole('button', { name: '요약 미사용 프로파일 삭제' }),
    );
    expect(screen.getByText('프로파일 삭제')).toBeInTheDocument();
    expect(
      screen.getByText(/기본 프로파일로 폴백됩니다/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '삭제' }));
    await waitFor(() => expect(deletedId).toBe('prof-2'));
    await waitFor(() =>
      expect(screen.queryByText('프로파일 삭제')).not.toBeInTheDocument(),
    );
  });

  it('P8: 이름 중복(409) — 모달 유지 + 서버 detail 표시', async () => {
    server.use(
      http.post('*/api/v1/admin/chunking/profiles', () =>
        HttpResponse.json(
          { detail: '이미 존재하는 프로파일 이름입니다' },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('금융 조항 기본');

    await user.click(screen.getByRole('button', { name: '프로파일 등록' }));
    await user.type(
      screen.getByPlaceholderText('예: 금융 약관 조항 프로파일'),
      '중복 이름',
    );
    await user.click(screen.getByRole('button', { name: '규칙 추가' }));
    await user.type(screen.getByLabelText('규칙 1 패턴'), '^부칙');
    await user.click(screen.getByRole('button', { name: '등록' }));

    expect(
      await screen.findByText('이미 존재하는 프로파일 이름입니다'),
    ).toBeInTheDocument();
    expect(screen.getByText('청킹 프로파일 등록')).toBeInTheDocument();
  });
});
