// document-revision §5.1·§5.4 — 문서 목록의 개정 관리 UI (module-9)
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { ApiError } from '@/services/api/ApiError';
import type { DocumentVersion, KbDocumentInfo } from '@/types/knowledgeBase';
import DocumentVersionHistory from './DocumentVersionHistory';
import PendingSyncBanner from './PendingSyncBanner';
import RevisionLinkModal from './RevisionLinkModal';
import RevisionMetaDialog from './RevisionMetaDialog';
import RevisionRollbackDialog from './RevisionRollbackDialog';
import { revisionErrorMessage } from './revisionErrors';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const version = (over: Partial<DocumentVersion> = {}): DocumentVersion => ({
  document_id: 'v2', filename: '규정.pdf', lineage_id: 'v1', version_no: 2,
  version_label: '2026-11 개정', effective_date: '2026-12-01',
  revision_status: 'active', sync_state: 'synced', superseded_by: null,
  superseded_at: null, revised_by: '7', created_at: '2026-11-20T10:00:00',
  ...over,
});

const doc = (over: Partial<KbDocumentInfo> = {}): KbDocumentInfo => ({
  document_id: 'v2', filename: '규정.pdf', chunk_count: 3,
  chunking_strategy: 'parent_child', created_at: '2026-11-20T10:00:00',
  can_delete: true, version_no: 2, version_label: '2026-11 개정',
  effective_date: null, revision_status: 'active', sync_state: 'synced',
  lineage_id: 'v1', has_history: true,
  ...over,
});

const renderWith = (ui: React.ReactElement) => render(ui, { wrapper: createWrapper() });

describe('revisionErrorMessage', () => {
  it('reason 코드를 한국어 안내로 바꾼다', () => {
    const err = new ApiError('x', 409, 'REVISION_LINK_INVALID', {
      code: 'REVISION_LINK_INVALID', reason: 'source_has_history', message: 'x',
    });
    expect(revisionErrorMessage(err)).toMatch(/이미 이전 버전/);
  });

  it('알 수 없으면 서버 메시지, 그것도 없으면 기본 문구', () => {
    expect(revisionErrorMessage(new Error('서버 오류'))).toBe('서버 오류');
    expect(revisionErrorMessage(null)).toMatch(/잠시 후/);
  });
});

describe('DocumentVersionHistory', () => {
  it('계보 버전을 최신순으로 보여주고 상태를 글자로 표시한다', async () => {
    server.use(
      http.get(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_VERSIONS(':kbId', ':docId')}`,
        () =>
          HttpResponse.json({
            lineage_id: 'v1',
            versions: [
              version(),
              version({
                document_id: 'v1', version_no: 1, version_label: null,
                effective_date: null, revision_status: 'superseded',
                created_at: '2025-03-02T09:00:00',
              }),
            ],
          }),
      ),
    );
    renderWith(<DocumentVersionHistory kbId="kb-1" documentId="v2" />);
    const items = await screen.findAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('v2');
    expect(items[0]).toHaveTextContent('2026-11 개정');
    expect(items[0]).toHaveTextContent('시행 2026-12-01');
    expect(items[0]).toHaveTextContent('현재');
    expect(items[1]).toHaveTextContent('v1');
    expect(items[1]).toHaveTextContent('2025-03-02');
    expect(items[1]).toHaveTextContent('대체됨');
  });
});

describe('RevisionRollbackDialog', () => {
  it('분리(기본)로 되돌리고 닫는다', async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_ROLLBACK(':kbId', ':docId')}`,
        async ({ request }) => {
          bodies.push(await request.json());
          return HttpResponse.json({
            restored_document_id: 'v1', detached_document_id: 'v2',
            deleted_document_id: null, sync_state: 'synced',
          });
        },
      ),
    );
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWith(
      <RevisionRollbackDialog kbId="kb-1" document={doc()} isOpen onClose={onClose} />,
    );
    expect(screen.getByText(/이전 버전\(v1\)을 다시 검색에 사용/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '되돌리기' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(bodies).toEqual([{ mode: 'detach' }]);
  });

  it('삭제를 고르면 delete 로 보낸다', async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_ROLLBACK(':kbId', ':docId')}`,
        async ({ request }) => {
          bodies.push(await request.json());
          return HttpResponse.json({
            restored_document_id: 'v1', detached_document_id: null,
            deleted_document_id: 'v2', sync_state: 'synced',
          });
        },
      ),
    );
    const user = userEvent.setup();
    renderWith(
      <RevisionRollbackDialog kbId="kb-1" document={doc()} isOpen onClose={vi.fn()} />,
    );
    await user.click(screen.getByRole('radio', { name: /이 버전을 삭제/ }));
    await user.click(screen.getByRole('button', { name: '되돌리기' }));
    await waitFor(() => expect(bodies).toEqual([{ mode: 'delete' }]));
  });

  it('409 사유를 보여준다', async () => {
    server.use(
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_ROLLBACK(':kbId', ':docId')}`,
        () =>
          HttpResponse.json(
            { detail: { code: 'ROLLBACK_NOT_ALLOWED', reason: 'no_previous', message: 'no_previous' } },
            { status: 409 },
          ),
      ),
    );
    const user = userEvent.setup();
    renderWith(
      <RevisionRollbackDialog kbId="kb-1" document={doc()} isOpen onClose={vi.fn()} />,
    );
    await user.click(screen.getByRole('button', { name: '되돌리기' }));
    expect(await screen.findByText(/되돌릴 이전 버전이 없습니다/)).toBeInTheDocument();
  });
});

describe('RevisionLinkModal', () => {
  it('같은 KB의 다른 문서를 대체 대상으로 연결한다', async () => {
    const bodies: unknown[] = [];
    server.use(
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_LINK(':kbId', ':docId')}`,
        async ({ request, params }) => {
          bodies.push({ doc: params.docId, ...(await request.json() as object) });
          return HttpResponse.json({ document: version({ document_id: 'n1' }), sync_state: 'synced' });
        },
      ),
    );
    const onClose = vi.fn();
    const user = userEvent.setup();
    const self = doc({ document_id: 'n1', filename: '규정_2026.pdf', lineage_id: null, version_no: 1, has_history: false });
    renderWith(
      <RevisionLinkModal
        kbId="kb-1"
        document={self}
        candidates={[self, doc({ document_id: 'o1', filename: '규정_2025.pdf', version_no: 1, lineage_id: null })]}
        isOpen
        onClose={onClose}
      />,
    );
    const select = screen.getByLabelText('대체되는 문서');
    expect(screen.queryByRole('option', { name: /규정_2026\.pdf/ })).not.toBeInTheDocument();
    await user.selectOptions(select, 'o1');
    await user.click(screen.getByRole('button', { name: '연결' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(bodies).toEqual([{ doc: 'n1', supersedes_document_id: 'o1' }]);
  });
});

describe('RevisionMetaDialog', () => {
  it('라벨·시행일을 저장한다(빈 값은 null)', async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_META(':kbId', ':docId')}`,
        async ({ request }) => {
          bodies.push(await request.json());
          return HttpResponse.json(version());
        },
      ),
    );
    const onClose = vi.fn();
    const user = userEvent.setup();
    renderWith(
      <RevisionMetaDialog kbId="kb-1" document={doc()} isOpen onClose={onClose} />,
    );
    const label = screen.getByLabelText('버전 라벨');
    expect(label).toHaveValue('2026-11 개정');
    await user.clear(label);
    await user.type(label, '2026-12 개정');
    await user.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    expect(bodies).toEqual([{ version_label: '2026-12 개정', effective_date: null }]);
  });
});

describe('PendingSyncBanner', () => {
  it('반영 실패 문서를 알리고 다시 반영한다', async () => {
    const calls: string[] = [];
    server.use(
      http.post(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_REVISION_SYNC(':kbId', ':docId')}`,
        ({ params }) => {
          calls.push(String(params.docId));
          return HttpResponse.json({ document_id: params.docId, revision_status: 'superseded', sync_state: 'synced' });
        },
      ),
    );
    const user = userEvent.setup();
    renderWith(
      <PendingSyncBanner
        kbId="kb-1"
        items={[version({ document_id: 'v1', version_no: 1, revision_status: 'superseded', sync_state: 'pending' })]}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/검색 제외 반영이 끝나지 않은 문서/);
    await user.click(screen.getByRole('button', { name: '규정.pdf v1 다시 반영' }));
    await waitFor(() => expect(calls).toEqual(['v1']));
  });

  it('항목이 없으면 아무것도 그리지 않는다', () => {
    const { container } = renderWith(<PendingSyncBanner kbId="kb-1" items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
