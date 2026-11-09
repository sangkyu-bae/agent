import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { server } from '@/__tests__/mocks/server';
import type {
  AgentDocumentTemplateResponse,
  DocumentExtractorDraft,
} from '@/types/documentExtractor';
import { FORM_TEMPLATE_REPLACE_NOTICE } from '@/types/agentPipeline';
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

// ── extractor-template-preview Design §5.2 — 저장 양식 보기/교체 모드 (F7–F9) ──

const SAVED: AgentDocumentTemplateResponse = {
  template_id: 'tpl-1',
  name: '여신 승인 신청서',
  source_format: 'docx',
  html_skeleton: '<p>{{borrower_name}}</p>',
  slots: [
    {
      key: 'borrower_name', label: '차주명', slot_type: 'value',
      description: '', sample_value: '홍길동',
    },
  ],
  samples_hidden: false,
  is_inherited: false,
  updated_at: '2026-11-09T00:00:00',
};

describe('DocumentExtractorConfigModal — 저장된 양식', () => {
  it('F7: 드래프트 없음 + 저장 양식 → 보기 모드, 교체 → 업로드, 다시 보기로 복귀', async () => {
    renderWithQuery(
      <DocumentExtractorConfigModal
        isOpen
        draft={null}
        onChange={vi.fn()}
        onClose={vi.fn()}
        emptyNotice={FORM_TEMPLATE_REPLACE_NOTICE}
        hasSavedTemplate
        savedTemplate={SAVED}
      />,
    );

    expect(screen.getByRole('heading', { name: '저장된 양식' })).toBeInTheDocument();
    expect(screen.getByText('여신 승인 신청서')).toBeInTheDocument();
    expect(screen.queryByLabelText('양식 문서 업로드')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: '새 파일로 교체' }));
    expect(screen.getByLabelText('양식 문서 업로드')).toBeInTheDocument();
    expect(screen.getByText(FORM_TEMPLATE_REPLACE_NOTICE)).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '저장된 양식 보기' }));
    expect(screen.getByRole('heading', { name: '저장된 양식' })).toBeInTheDocument();
  });

  it('F8: 드래프트가 있으면 저장 양식이 있어도 기존 편집 패널을 보여준다', () => {
    renderWithQuery(
      <DocumentExtractorConfigModal
        isOpen
        draft={DRAFT}
        onChange={vi.fn()}
        onClose={vi.fn()}
        hasSavedTemplate
        savedTemplate={SAVED}
      />,
    );

    expect(screen.getByLabelText('템플릿 이름')).toHaveValue('여신심의서');
    expect(screen.queryByRole('heading', { name: '저장된 양식' })).toBeNull();
    expect(screen.queryByRole('button', { name: '저장된 양식 보기' })).toBeNull();
  });

  it('F9: 조회 오류면 오류 문구와 교체 버튼을 보여준다', () => {
    renderWithQuery(
      <DocumentExtractorConfigModal
        isOpen
        draft={null}
        onChange={vi.fn()}
        onClose={vi.fn()}
        hasSavedTemplate
        savedTemplate={undefined}
        isSavedTemplateError
      />,
    );

    expect(screen.getByText('저장된 양식을 불러오지 못했습니다')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '새 파일로 교체' })).toBeInTheDocument();
  });

  it('저장 양식이 없으면 기존처럼 업로드 화면을 바로 보여준다', () => {
    renderWithQuery(
      <DocumentExtractorConfigModal
        isOpen
        draft={null}
        onChange={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('양식 문서 업로드')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '저장된 양식 보기' })).toBeNull();
  });
});
