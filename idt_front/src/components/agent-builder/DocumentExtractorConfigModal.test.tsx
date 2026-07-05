import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { server } from '@/__tests__/mocks/server';
import type { DocumentExtractorDraft } from '@/types/documentExtractor';
import DocumentExtractorConfigModal from './DocumentExtractorConfigModal';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderWithQuery = (ui: ReactNode) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
};

const DRAFT: DocumentExtractorDraft = {
  sourceFileId: 'a'.repeat(32),
  sourceFormat: 'pdf',
  html: '<p>금액: 5억 원</p>',
  slots: [
    {
      key: 'loan_amount', label: '여신금액', slot_type: 'value',
      description: '', fill_hint: '', sample_value: '5억 원',
    },
  ],
  mcpPdfToHtmlToolId: 'mcp_p2h',
  mcpHtmlToDocToolId: 'mcp_h2d',
  regenCount: 0,
  confirmed: false,
  templateName: '여신심의서',
  htmlSkeleton: '',
};

describe('DocumentExtractorConfigModal', () => {
  it('isOpen=false면 렌더되지 않는다', () => {
    renderWithQuery(
      <DocumentExtractorConfigModal
        isOpen={false}
        draft={null}
        onChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('드래프트를 패널에 렌더하고 편집은 onChange로 즉시 전달된다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigModal
        isOpen
        draft={DRAFT}
        onChange={onChange}
        onClose={vi.fn()}
      />,
    );
    expect(
      screen.getByRole('dialog', { name: '문서추출기 — 양식 등록' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('템플릿 이름')).toHaveValue('여신심의서');

    await userEvent.click(
      screen.getByRole('button', { name: '여신금액 슬롯 제거' }),
    );
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('닫기 버튼 클릭 시 onClose가 호출된다', async () => {
    const onClose = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigModal
        isOpen
        draft={null}
        onChange={vi.fn()}
        onClose={onClose}
      />,
    );
    // 헤더 X버튼과 footer 버튼 모두 이름이 '닫기' — footer 버튼(마지막)을 클릭
    const closeButtons = screen.getAllByRole('button', { name: '닫기' });
    await userEvent.click(closeButtons[closeButtons.length - 1]);
    expect(onClose).toHaveBeenCalled();
  });
});
