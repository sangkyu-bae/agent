import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  beforeAll,
  afterEach,
  afterAll,
  describe,
  it,
  expect,
  vi,
} from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import KbUploadDocumentModal from './KbUploadDocumentModal';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderModal = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <KbUploadDocumentModal
        isOpen
        onClose={vi.fn()}
        kbId="kb-1"
        kbName="여신 규정집"
      />
    </QueryClientProvider>,
  );
};

describe('KbUploadDocumentModal', () => {
  it('파일 입력이 PDF·엑셀·한글 확장자를 허용한다 (kb-excel-upload D10, hwp-parser §5.3)', () => {
    renderModal();
    const input = screen.getByLabelText('업로드할 문서 파일');
    expect(input).toHaveAttribute('accept', '.pdf,.xlsx,.xls,.hwp,.hwpx');
  });

  it('지원 형식 안내 문구를 표시한다', () => {
    renderModal();
    expect(screen.getByText(/지원 형식: PDF, 엑셀/)).toBeInTheDocument();
  });

  it('지원 형식 안내에 한글(.hwp/.hwpx)을 표시한다 (hwp-parser §5.4)', () => {
    renderModal();
    expect(screen.getByText(/한글\(\.hwp\/\.hwpx\)/)).toBeInTheDocument();
  });

  it('업로드 실패(422) 시 서버 detail 메시지를 표시한다', async () => {
    server.use(
      http.post('*/api/v1/knowledge-bases/kb-1/documents', () =>
        HttpResponse.json(
          {
            detail:
              "Sheet '대량' in '한도표.xlsx' has 30000 rows, exceeds limit 20000. Split the file and retry",
          },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderModal();
    const input = screen.getByLabelText('업로드할 문서 파일');
    await user.upload(
      input,
      new File(['x'], '한도표.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }),
    );
    // document-revision: 파일 선택 직후 사전 점검이 끝나야 업로드 버튼이 켜진다
    const button = await screen.findByRole('button', { name: '업로드' });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    await waitFor(() => {
      expect(screen.getByText(/exceeds limit 20000/)).toBeInTheDocument();
    });
  });
});

// ── document-revision §5 — 사전 점검 → 결정 → 업로드 ─────────────────
const UPLOAD_URL = '*/api/v1/knowledge-bases/kb-1/documents';
const CHECK_URL = '*/api/v1/knowledge-bases/kb-1/documents/revision-check';

const uploadResponse = (revision: object | null) => ({
  kb_id: 'kb-1', kb_name: '여신 규정집', collection_name: 'c',
  document_id: 'new', filename: '여신심사기준_2026.pdf', total_pages: 1,
  chunk_count: 3, chunking_strategy: 'parent_child',
  qdrant: { status: 'success' }, es: { status: 'success' },
  status: 'completed', section_summary: null, revision,
});

const candidateCheck = {
  check_id: 'chk-1', verdict: 'revision_candidate', duplicate_of: null,
  suggested_document_id: 'old',
  candidates: [{
    document_id: 'old', filename: '여신심사기준_2025.pdf', version_no: 2,
    version_label: null, filename_score: 1, content_score: 0.9,
    combined_score: 0.94, llm_verdict: 'same_document_revision',
    llm_reason: '같은 규정의 개정판',
  }],
  llm_status: 'ok', elapsed_ms: 20,
};

const pickFile = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.upload(
    screen.getByLabelText('업로드할 문서 파일'),
    new File(['x'], '여신심사기준_2026.pdf', { type: 'application/pdf' }),
  );
};

describe('KbUploadDocumentModal — 개정 사전 점검', () => {
  it('개정 후보면 제안을 보여주고 개정으로 업로드한 뒤 결과를 안내한다', async () => {
    let uploads = 0;
    server.use(
      http.post(CHECK_URL, () => HttpResponse.json(candidateCheck)),
      http.post(UPLOAD_URL, () => {
        uploads += 1;
        return HttpResponse.json(uploadResponse({
          applied: true, lineage_id: 'old', version_no: 3,
          superseded_document_id: 'old', sync_state: 'synced', reason: null,
        }));
      }),
    );
    const user = userEvent.setup();
    renderModal();
    await pickFile(user);

    expect(await screen.findByText(/개정본으로 보입니다/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '업로드' }));

    expect(await screen.findByText(/v3 버전으로 개정되었습니다/)).toBeInTheDocument();
    expect(screen.getByText(/이전 버전은 검색에서 제외됩니다/)).toBeInTheDocument();
    expect(uploads).toBe(1);
  });

  it('반영이 끝나지 않으면(pending) 재시도를 안내한다', async () => {
    server.use(
      http.post(CHECK_URL, () => HttpResponse.json(candidateCheck)),
      http.post(UPLOAD_URL, () =>
        HttpResponse.json(uploadResponse({
          applied: true, lineage_id: 'old', version_no: 3,
          superseded_document_id: 'old', sync_state: 'pending', reason: null,
        })),
      ),
    );
    const user = userEvent.setup();
    renderModal();
    await pickFile(user);
    await screen.findByText(/개정본으로 보입니다/);
    await user.click(screen.getByRole('button', { name: '업로드' }));
    expect(await screen.findByText(/검색에서 빼는 작업이 끝나지 않았습니다/)).toBeInTheDocument();
  });

  it('적재 미완료로 개정이 적용되지 않으면 알린다', async () => {
    server.use(
      http.post(CHECK_URL, () => HttpResponse.json(candidateCheck)),
      http.post(UPLOAD_URL, () =>
        HttpResponse.json(uploadResponse({
          applied: false, lineage_id: null, version_no: 1,
          superseded_document_id: null, sync_state: null, reason: 'ingest_incomplete',
        })),
      ),
    );
    const user = userEvent.setup();
    renderModal();
    await pickFile(user);
    await screen.findByText(/개정본으로 보입니다/);
    await user.click(screen.getByRole('button', { name: '업로드' }));
    expect(await screen.findByText(/개정을 적용하지 않고 새 문서로/)).toBeInTheDocument();
  });

  it('완전 동일 파일이면 업로드 버튼이 꺼진다', async () => {
    server.use(
      http.post(CHECK_URL, () =>
        HttpResponse.json({
          ...candidateCheck, verdict: 'duplicate', candidates: [],
          suggested_document_id: null,
          duplicate_of: {
            document_id: 'old', filename: '여신심사기준_2025.pdf', lineage_id: 'old',
            version_no: 1, version_label: null, effective_date: null,
            revision_status: 'active', sync_state: 'synced', superseded_by: null,
            superseded_at: null, revised_by: null, created_at: null,
          },
        }),
      ),
    );
    const user = userEvent.setup();
    renderModal();
    await pickFile(user);
    expect(await screen.findByRole('alert')).toHaveTextContent('이미 같은 파일이 있습니다');
    expect(screen.getByRole('button', { name: '업로드' })).toBeDisabled();
  });

  it('점검 요청이 실패해도 새 문서로 올릴 수 있다', async () => {
    server.use(
      http.post(CHECK_URL, () => HttpResponse.json({ detail: 'boom' }, { status: 500 })),
      http.post(UPLOAD_URL, () => HttpResponse.json(uploadResponse(null))),
    );
    const user = userEvent.setup();
    renderModal();
    await pickFile(user);
    expect(await screen.findByText(/개정 여부를 확인하지 못했습니다/)).toBeInTheDocument();
    const button = screen.getByRole('button', { name: '업로드' });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    expect(await screen.findByText(/업로드가 완료되었습니다/)).toBeInTheDocument();
  });

  it('대상 문서가 바뀌어 409 면 다시 점검을 안내한다', async () => {
    server.use(
      http.post(CHECK_URL, () => HttpResponse.json(candidateCheck)),
      http.post(UPLOAD_URL, () =>
        HttpResponse.json(
          { detail: { code: 'REVISION_TARGET_INVALID', reason: 'not_latest', message: 'not_latest' } },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderModal();
    await pickFile(user);
    await screen.findByText(/개정본으로 보입니다/);
    await user.click(screen.getByRole('button', { name: '업로드' }));
    expect(await screen.findByText(/대상 문서의 상태가 바뀌었습니다/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '다시 점검' })).toBeInTheDocument();
  });
});
