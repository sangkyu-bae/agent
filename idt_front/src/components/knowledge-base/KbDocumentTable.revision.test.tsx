// document-revision §5.1 — 문서 목록 버전 배지·이력·개정 관리 버튼
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import type { KbDocumentInfo } from '@/types/knowledgeBase';
import KbDocumentTable from './KbDocumentTable';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const base = {
  chunk_count: 3, chunking_strategy: 'parent_child', created_at: '2026-11-20T00:00:00Z',
  can_delete: true, effective_date: null, revision_status: 'active' as const,
  sync_state: 'synced' as const,
};

const revised: KbDocumentInfo = {
  ...base, document_id: 'v2', filename: '규정.pdf', version_no: 2,
  version_label: '2026-11 개정', lineage_id: 'v1', has_history: true,
};
const solo: KbDocumentInfo = {
  ...base, document_id: 'solo', filename: '금리표.xlsx', version_no: 1,
  version_label: null, lineage_id: null, has_history: false,
};
const legacy: KbDocumentInfo = {
  document_id: 'old', filename: '예전.pdf', chunk_count: 1,
  chunking_strategy: 'parent_child', created_at: null, can_delete: false,
};

const renderTable = (props: Partial<React.ComponentProps<typeof KbDocumentTable>> = {}) =>
  render(
    <KbDocumentTable
      documents={[revised, solo, legacy]}
      isLoading={false}
      isError={false}
      onRetry={vi.fn()}
      kbId="kb-1"
      {...props}
    />,
    { wrapper: createWrapper() },
  );

const rowOf = (filename: string) => screen.getByText(filename).closest('tr') as HTMLElement;

describe('KbDocumentTable — 버전 표시', () => {
  it('버전 배지: 개정본은 번호와 라벨, 필드가 없는 응답은 v1', () => {
    renderTable();
    expect(within(rowOf('규정.pdf')).getByText('v2 · 2026-11 개정')).toBeInTheDocument();
    expect(within(rowOf('금리표.xlsx')).getByText('v1')).toBeInTheDocument();
    expect(within(rowOf('예전.pdf')).getByText('v1')).toBeInTheDocument();
  });

  it('이력이 있는 행만 이력 토글이 있고, 펼치면 버전 목록을 불러온다', async () => {
    server.use(
      http.get(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_VERSIONS(':kbId', ':docId')}`,
        () =>
          HttpResponse.json({
            lineage_id: 'v1',
            versions: [
              { document_id: 'v2', filename: '규정.pdf', lineage_id: 'v1', version_no: 2,
                version_label: '2026-11 개정', effective_date: null, revision_status: 'active',
                sync_state: 'synced', superseded_by: null, superseded_at: null,
                revised_by: null, created_at: null },
              { document_id: 'v1', filename: '규정_old.pdf', lineage_id: 'v1', version_no: 1,
                version_label: null, effective_date: null, revision_status: 'superseded',
                sync_state: 'synced', superseded_by: 'v2', superseded_at: null,
                revised_by: null, created_at: null },
            ],
          }),
      ),
    );
    const onRowClick = vi.fn();
    const user = userEvent.setup();
    renderTable({ onRowClick });
    expect(within(rowOf('금리표.xlsx')).queryByRole('button', { name: /이력/ })).not.toBeInTheDocument();
    const toggle = within(rowOf('규정.pdf')).getByRole('button', { name: '규정.pdf 버전 이력' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByText(/규정_old\.pdf/)).toBeInTheDocument();
    expect(onRowClick).not.toHaveBeenCalled();
  });
});

describe('KbDocumentTable — 개정 관리 버튼', () => {
  it('되돌리기는 v2 이상, 대체 문서 지정은 계보 없는 문서에만', async () => {
    const onRollback = vi.fn();
    const onLink = vi.fn();
    const onEditMeta = vi.fn();
    const user = userEvent.setup();
    renderTable({ onRollback, onLink, onEditMeta });

    const revisedRow = within(rowOf('규정.pdf'));
    const soloRow = within(rowOf('금리표.xlsx'));
    expect(revisedRow.getByRole('button', { name: '규정.pdf 개정 되돌리기' })).toBeInTheDocument();
    expect(revisedRow.queryByRole('button', { name: /대체한 문서 지정/ })).not.toBeInTheDocument();
    expect(soloRow.queryByRole('button', { name: /되돌리기/ })).not.toBeInTheDocument();

    await user.click(soloRow.getByRole('button', { name: '금리표.xlsx 대체한 문서 지정' }));
    expect(onLink).toHaveBeenCalledWith(solo);
    await user.click(revisedRow.getByRole('button', { name: '규정.pdf 개정 되돌리기' }));
    expect(onRollback).toHaveBeenCalledWith(revised);
    await user.click(revisedRow.getByRole('button', { name: '규정.pdf 버전 라벨 수정' }));
    expect(onEditMeta).toHaveBeenCalledWith(revised);
  });

  it('콜백을 넘기지 않으면 버튼을 그리지 않는다(기존 화면 호환)', () => {
    renderTable();
    expect(screen.queryByRole('button', { name: /되돌리기|대체한 문서|라벨 수정/ })).not.toBeInTheDocument();
  });
});

describe('KbDocumentTable — 이력이 사라진 행', () => {
  it('펼친 뒤 되돌리기로 이력이 없어지면 이력 행을 닫는다', async () => {
    server.use(
      http.get(
        `*${API_ENDPOINTS.KNOWLEDGE_BASE_DOCUMENT_VERSIONS(':kbId', ':docId')}`,
        () => HttpResponse.json({ lineage_id: 'v1', versions: [] }),
      ),
    );
    const user = userEvent.setup();
    const { rerender } = renderTable();
    await user.click(screen.getByRole('button', { name: '규정.pdf 버전 이력' }));
    expect(screen.getByRole('list', { name: '버전 이력' })).toBeInTheDocument();

    const detached = { ...revised, version_no: 1, version_label: null, lineage_id: null, has_history: false };
    rerender(
      <KbDocumentTable
        documents={[detached, solo]}
        isLoading={false}
        isError={false}
        onRetry={vi.fn()}
        kbId="kb-1"
      />,
    );
    expect(screen.queryByRole('list', { name: '버전 이력' })).not.toBeInTheDocument();
  });
});
