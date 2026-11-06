// agent-kb-quick-setup Design §8.3 L2 #1~#6 — 지식 문서 블록 (MSW 기본 핸들러 + 시나리오별 override)
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import KnowledgeDocsBlock, { type KnowledgeDocsBlockProps } from './KnowledgeDocsBlock';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const FORBIDDEN_TERMS = ['컬렉션', '벡터', '거리 함수', '청킹', 'BM25', 'RRF', 'top_k'];

const renderBlock = (over: Partial<KnowledgeDocsBlockProps> = {}) => {
  const onAttached = vi.fn();
  const onDetach = vi.fn();
  const Wrapper = createWrapper();
  const utils = render(
    <Wrapper>
      <KnowledgeDocsBlock
        mode="studio"
        agentName="여신 상담봇"
        visibility="private"
        onAttached={onAttached}
        onDetach={onDetach}
        {...over}
      />
    </Wrapper>,
  );
  return { ...utils, onAttached, onDetach };
};

const pdf = (name: string) => new File(['%PDF-1.4'], name, { type: 'application/pdf' });

describe('KnowledgeDocsBlock — 업로드 → 연결 (L2 #1)', () => {
  it('파일 2개 업로드 시 /quick 1회 호출 후 kb_id 로 onAttached, 진행 카드 완료', async () => {
    // jsdom multipart 는 undici formData() 가 못 읽는다 — raw 본문으로 필드·파일 수 검증
    let body = '';
    server.use(
      http.post(`*${API_ENDPOINTS.KNOWLEDGE_BASE_QUICK}`, async ({ request }) => {
        body = await request.text();
        return HttpResponse.json(
          {
            kb_id: 'kb-quick-1', kb_name: '여신 상담봇 지식', collection_name: 'kb-quick001',
            scope: 'PERSONAL',
            documents: [
              { filename: 'a.pdf', status: 'uploaded', document_id: 'd1', chunk_count: 12, error: null },
              { filename: 'b.pdf', status: 'uploaded', document_id: 'd2', chunk_count: 8, error: null },
            ],
            uploaded_count: 2, failed_count: 0,
          },
          { status: 201 },
        );
      }),
    );
    const { onAttached } = renderBlock();
    const input = await screen.findByLabelText('지식 문서 파일 선택');
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.upload(input, [pdf('a.pdf'), pdf('b.pdf')]);

    await waitFor(() => expect(onAttached).toHaveBeenCalledWith('kb-quick-1', expect.anything()));
    expect(body).toMatch(/name="name"\r?\n\r?\n여신 상담봇 지식/);
    expect(body).toMatch(/name="scope"\r?\n\r?\nPERSONAL/);
    expect(body.match(/name="files"; filename=/g)).toHaveLength(2);
    expect(await screen.findByText('2/2')).toBeInTheDocument();
  });
});

describe('KnowledgeDocsBlock — 부분/전부 실패 (L2 #2, #3)', () => {
  it('1개 실패: 실패 파일명·사유가 보이고 도구 연결은 진행된다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.KNOWLEDGE_BASE_QUICK}`, () =>
        HttpResponse.json(
          {
            kb_id: 'kb-quick-1', kb_name: 'n', collection_name: 'c', scope: 'PERSONAL',
            documents: [
              { filename: 'ok.pdf', status: 'uploaded', document_id: 'd1', chunk_count: 3, error: null },
              { filename: 'locked.pdf', status: 'failed', document_id: null, chunk_count: 0, error: '암호화된 문서입니다' },
            ],
            uploaded_count: 1, failed_count: 1,
          },
          { status: 201 },
        ),
      ),
    );
    const { onAttached } = renderBlock();
    const input = await screen.findByLabelText('지식 문서 파일 선택');
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.upload(input, [pdf('ok.pdf'), pdf('locked.pdf')]);

    expect(await screen.findByText(/locked\.pdf: 암호화된 문서입니다/)).toBeInTheDocument();
    await waitFor(() => expect(onAttached).toHaveBeenCalledWith('kb-quick-1', expect.anything()));
    expect(screen.queryByText('도구를 연결하지 못했습니다')).not.toBeInTheDocument();
  });

  it('전부 실패: 도구 미부착 + 재시도 버튼', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.KNOWLEDGE_BASE_QUICK}`, () =>
        HttpResponse.json(
          {
            kb_id: 'kb-quick-1', kb_name: 'n', collection_name: 'c', scope: 'PERSONAL',
            documents: [
              { filename: 'bad.pdf', status: 'failed', document_id: null, chunk_count: 0, error: '손상된 파일' },
            ],
            uploaded_count: 0, failed_count: 1,
          },
          { status: 201 },
        ),
      ),
    );
    const { onAttached } = renderBlock();
    const input = await screen.findByLabelText('지식 문서 파일 선택');
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.upload(input, [pdf('bad.pdf')]);

    expect(await screen.findByText('도구를 연결하지 못했습니다')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeInTheDocument();
    expect(onAttached).not.toHaveBeenCalled();
  });

  it('요청 자체가 실패하면(미설정 422) 안내 문구를 그대로 띄운다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.KNOWLEDGE_BASE_QUICK}`, () =>
        HttpResponse.json(
          { detail: { code: 'KB_DEFAULTS_NOT_CONFIGURED', message: '관리자가 기본 임베딩 모델을 설정해야 합니다' } },
          { status: 422 },
        ),
      ),
    );
    renderBlock();
    const input = await screen.findByLabelText('지식 문서 파일 선택');
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.upload(input, [pdf('a.pdf')]);
    expect(
      await screen.findByText('관리자가 기본 임베딩 모델을 설정해야 합니다'),
    ).toBeInTheDocument();
  });
});

describe('KnowledgeDocsBlock — 기존 KB 선택 / 미설정 / 연결 배지 (L2 #4~#6)', () => {
  it('기존 지식베이스를 고르면 /quick 없이 onAttached(kbId, null)', async () => {
    const quickSpy = vi.fn();
    server.use(
      http.post(`*${API_ENDPOINTS.KNOWLEDGE_BASE_QUICK}`, () => {
        quickSpy();
        return HttpResponse.json({}, { status: 500 });
      }),
    );
    const { onAttached } = renderBlock();
    await userEvent.click(await screen.findByRole('combobox', { name: '기존 지식베이스 선택' }));
    await userEvent.click(await screen.findByRole('option', { name: '[공개] 전사 규정' }));
    expect(onAttached).toHaveBeenCalledWith('kb-public-1', null);
    expect(quickSpy).not.toHaveBeenCalled();
  });

  it('기본 임베딩 모델 미설정이면 드롭 영역이 비활성이고 문구가 보인다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.KB_DEFAULTS}`, () =>
        HttpResponse.json({ configured: false, default_embedding_model_id: null, model_display_name: null }),
      ),
    );
    renderBlock();
    expect(
      await screen.findByText('관리자가 기본 임베딩 모델을 설정해야 합니다'),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('지식 문서 파일 선택')).toBeDisabled();
    // 기존 KB 선택은 여전히 가능
    expect(screen.getByRole('combobox', { name: '기존 지식베이스 선택' })).not.toBeDisabled();
  });

  it('연결된 KB 가 있으면 이름·범위 배지와 [바꾸기] 가 보이고 드롭 영역은 없다', async () => {
    const { onDetach } = renderBlock({ attachedKbId: 'kb-dept-1' });
    expect(await screen.findByText(/연결됨: 여신 심사 기준/)).toBeInTheDocument();
    expect(screen.getByText('부서')).toBeInTheDocument();
    expect(screen.queryByLabelText('지식 문서 파일 선택')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '바꾸기' }));
    expect(onDetach).toHaveBeenCalled();
  });

  it('locked 면 바꾸기 버튼과 입력이 잠긴다', async () => {
    renderBlock({ attachedKbId: 'kb-dept-1', locked: true, mode: 'wizard' });
    await screen.findByText(/연결됨/);
    expect(screen.queryByRole('button', { name: '바꾸기' })).not.toBeInTheDocument();
  });

  it('간단 모드 문구에 금지 용어가 없다 (SC-6)', async () => {
    const { container } = renderBlock();
    await screen.findByLabelText('지식 문서 파일 선택');
    const text = container.textContent ?? '';
    for (const term of FORBIDDEN_TERMS) {
      expect(text).not.toContain(term);
    }
    expect(text).toContain('저장하지 않아도 지식베이스는 남습니다');
  });
});

describe('KnowledgeDocsBlock — Check G1/G2', () => {
  it('전부 실패 후 [다시 시도]는 같은 KB 에 업로드 API 로 재시도하고 /quick 을 다시 부르지 않는다', async () => {
    let quickCalls = 0;
    const uploadKbIds: string[] = [];
    server.use(
      http.post(`*${API_ENDPOINTS.KNOWLEDGE_BASE_QUICK}`, () => {
        quickCalls += 1;
        return HttpResponse.json(
          {
            kb_id: 'kb-quick-1', kb_name: 'n', collection_name: 'c', scope: 'PERSONAL',
            documents: [
              { filename: 'bad.pdf', status: 'failed', document_id: null, chunk_count: 0, error: '손상된 파일' },
            ],
            uploaded_count: 0, failed_count: 1,
          },
          { status: 201 },
        );
      }),
      http.post(`*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENTS(':kbId')}`, ({ params }) => {
        uploadKbIds.push(String(params.kbId));
        return HttpResponse.json({
          kb_id: params.kbId, kb_name: 'n', collection_name: 'c', document_id: 'doc-r', filename: 'bad.pdf',
          total_pages: 1, chunk_count: 4, chunking_strategy: 'parent_child',
          qdrant: { status: 'success', error: null }, es: { status: 'success', error: null },
          status: 'completed', section_summary: null,
        });
      }),
    );
    const { onAttached } = renderBlock();
    const input = await screen.findByLabelText('지식 문서 파일 선택');
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.upload(input, [pdf('bad.pdf')]);
    await screen.findByText('도구를 연결하지 못했습니다');
    expect(onAttached).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    await waitFor(() => expect(onAttached).toHaveBeenCalledWith('kb-quick-1', expect.anything()));
    expect(quickCalls).toBe(1);
    expect(uploadKbIds).toEqual(['kb-quick-1']);
    expect(await screen.findByText('1/1')).toBeInTheDocument();
    expect(screen.queryByText('도구를 연결하지 못했습니다')).not.toBeInTheDocument();
  });

  it('위저드 모드에서도 KB 가 생긴 뒤에는 고아 안내가 보인다', async () => {
    renderBlock({ mode: 'wizard' });
    expect(screen.queryByText('저장하지 않아도 지식베이스는 남습니다')).not.toBeInTheDocument();
    const input = await screen.findByLabelText('지식 문서 파일 선택');
    await waitFor(() => expect(input).not.toBeDisabled());
    await userEvent.upload(input, [pdf('a.pdf')]);
    expect(await screen.findByText('저장하지 않아도 지식베이스는 남습니다')).toBeInTheDocument();
  });

  it('연결된 KB 가 있으면 두 모드 모두 고아 안내가 보인다', async () => {
    renderBlock({ mode: 'wizard', attachedKbId: 'kb-dept-1' });
    expect(await screen.findByText('저장하지 않아도 지식베이스는 남습니다')).toBeInTheDocument();
  });
});
