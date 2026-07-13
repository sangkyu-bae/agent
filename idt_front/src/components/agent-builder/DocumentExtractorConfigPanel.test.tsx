// DocumentExtractorConfigPanel 테스트 (document-template-extractor Design §7-2)
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { server } from '@/__tests__/mocks/server';
import { API_ENDPOINTS } from '@/constants/api';
import type { DocumentExtractorDraft } from '@/types/documentExtractor';
import DocumentExtractorConfigPanel from './DocumentExtractorConfigPanel';

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  sessionStorage.clear();
});
afterAll(() => server.close());

const renderWithQuery = (ui: ReactNode) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
};

const EXTRACT_RESPONSE = {
  source_file_id: 'a'.repeat(32),
  source_format: 'pdf',
  html: '<p>금액: 5억 원</p>',
  preview_html: '<div class="pdf-page">금액: 5억 원</div>',
  suggested_slots: [
    {
      key: 'loan_amount', label: '여신금액', slot_type: 'value',
      description: '', fill_hint: '', sample_value: '5억 원',
    },
  ],
  mcp_pdf_to_html_tool_id: 'mcp_p2h',
  mcp_html_to_doc_tool_id: 'mcp_h2d',
};

const draftFixture = (
  overrides: Partial<DocumentExtractorDraft> = {},
): DocumentExtractorDraft => ({
  sourceFileId: 'a'.repeat(32),
  sourceFormat: 'pdf',
  html: '<p>금액: 5억 원</p>',
  slots: EXTRACT_RESPONSE.suggested_slots as DocumentExtractorDraft['slots'],
  mcpPdfToHtmlToolId: 'mcp_p2h',
  mcpHtmlToDocToolId: 'mcp_h2d',
  regenCount: 0,
  confirmed: false,
  templateName: '여신심의서',
  htmlSkeleton: '',
  ...overrides,
});

describe('DocumentExtractorConfigPanel — 업로드/추출', () => {
  it('extract 실패 시 업로드 화면(draft 없음)에도 에러 메시지를 표시한다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_EXTRACT}`, () =>
        HttpResponse.json(
          {
            detail: {
              code: 'SLOT_EXTRACTION_FAILED',
              message: '슬롯 추출 LLM 호출에 실패했습니다: 429 rate_limit',
            },
          },
          { status: 502 },
        ),
      ),
    );
    renderWithQuery(
      <DocumentExtractorConfigPanel draft={null} onChange={vi.fn()} />,
    );

    await userEvent.upload(
      screen.getByLabelText('양식 문서 업로드'),
      new File(['%PDF'], '큰문서.pdf', { type: 'application/pdf' }),
    );

    expect(
      await screen.findByText(
        '슬롯 추출 LLM 호출에 실패했습니다: 429 rate_limit',
      ),
    ).toBeInTheDocument();
  });

  it('파일 업로드 시 extract 응답으로 드래프트를 생성한다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_EXTRACT}`, () =>
        HttpResponse.json(EXTRACT_RESPONSE),
      ),
    );
    const onChange = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigPanel draft={null} onChange={onChange} />,
    );

    const file = new File(['%PDF'], '여신심의서.pdf', {
      type: 'application/pdf',
    });
    await userEvent.upload(
      screen.getByLabelText('양식 문서 업로드'),
      file,
    );

    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const draft = onChange.mock.calls[0][0] as DocumentExtractorDraft;
    expect(draft.sourceFileId).toBe('a'.repeat(32));
    expect(draft.slots[0].key).toBe('loan_amount');
    expect(draft.confirmed).toBe(false);
    expect(draft.templateName).toBe('여신심의서');
    expect(draft.mcpHtmlToDocToolId).toBe('mcp_h2d');
    // D1: layout 미리보기 HTML을 드래프트에 보관
    expect(draft.previewHtml).toBe(EXTRACT_RESPONSE.preview_html);
  });

  it('preview_html이 null이면 previewHtml 없이 드래프트를 만든다 (text 폴백)', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_EXTRACT}`, () =>
        HttpResponse.json({ ...EXTRACT_RESPONSE, preview_html: null }),
      ),
    );
    const onChange = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigPanel draft={null} onChange={onChange} />,
    );
    await userEvent.upload(
      screen.getByLabelText('양식 문서 업로드'),
      new File(['%PDF'], 'a.pdf', { type: 'application/pdf' }),
    );
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const draft = onChange.mock.calls[0][0] as DocumentExtractorDraft;
    expect(draft.previewHtml).toBeUndefined();
  });
});

describe('DocumentExtractorConfigPanel — 미리보기 (D1/D4/FR-06)', () => {
  it('미리보기 iframe은 layout previewHtml 기반 하이라이트를 사용한다', () => {
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture({
          previewHtml: '<div class="pdf-page">금액: 5억 원</div>',
        })}
        onChange={vi.fn()}
      />,
    );
    const iframe = screen.getByTitle('양식 미리보기') as HTMLIFrameElement;
    expect(iframe.getAttribute('srcdoc')).toContain('pdf-page');
    expect(iframe.getAttribute('srcdoc')).toContain('data-slot="loan_amount"');
  });

  it('위치를 찾지 못한 슬롯은 안내 문구를 노출한다 (FR-06)', () => {
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture({
          slots: [
            {
              key: 'ghost', label: '유령항목', slot_type: 'value',
              description: '', fill_hint: '', sample_value: '본문에 없는 값',
            },
          ],
        })}
        onChange={vi.fn()}
      />,
    );
    expect(
      screen.getByText(/위치를 찾지 못한 슬롯 1개: 유령항목/),
    ).toBeInTheDocument();
  });
});

describe('DocumentExtractorConfigPanel — 슬롯 편집/확정', () => {
  it('슬롯 제거 시 confirmed가 해제된 드래프트로 onChange된다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture()}
        onChange={onChange}
      />,
    );
    await userEvent.click(
      screen.getByRole('button', { name: '여신금액 슬롯 제거' }),
    );
    const updated = onChange.mock.calls[0][0] as DocumentExtractorDraft;
    expect(updated.slots).toHaveLength(0);
    expect(updated.confirmed).toBe(false);
  });

  it('슬롯 확정 시 html_skeleton에 {{key}} 토큰이 생성된다 (D2)', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture()}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByRole('button', { name: '슬롯 확정' }));
    const confirmed = onChange.mock.calls[0][0] as DocumentExtractorDraft;
    expect(confirmed.confirmed).toBe(true);
    expect(confirmed.htmlSkeleton).toBe('<p>금액: {{loan_amount}}</p>');
  });

  it('확정된 드래프트는 확정 배지를 표시한다', () => {
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture({
          confirmed: true,
          htmlSkeleton: '<p>금액: {{loan_amount}}</p>',
        })}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/확정됨/)).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '슬롯 확정' }),
    ).not.toBeInTheDocument();
  });
});

describe('DocumentExtractorConfigPanel — 슬롯 수동 추가/라벨 편집 (G2)', () => {
  it('라벨 입력 편집 시 해당 슬롯 라벨이 갱신된다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture()}
        onChange={onChange}
      />,
    );
    const labelInput = screen.getByLabelText('loan_amount 라벨');
    await userEvent.type(labelInput, 'X');
    const updated = onChange.mock.calls.at(-1)?.[0] as DocumentExtractorDraft;
    expect(updated.slots[0].label).toContain('X');
    expect(updated.confirmed).toBe(false);
  });

  it('문서에 있는 예시값으로 수동 슬롯을 추가한다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture()}
        onChange={onChange}
      />,
    );
    await userEvent.type(screen.getByLabelText('새 슬롯 항목명'), '담당자');
    await userEvent.type(screen.getByLabelText('새 슬롯 예시값'), '5억 원');
    await userEvent.click(screen.getByRole('button', { name: '추가' }));

    const updated = onChange.mock.calls.at(-1)?.[0] as DocumentExtractorDraft;
    expect(updated.slots).toHaveLength(2);
    const added = updated.slots[1];
    expect(added.label).toBe('담당자');
    expect(added.sample_value).toBe('5억 원');
    expect(added.key).toMatch(/^[a-z][a-z0-9_]{0,49}$/);
  });

  it('예시값이 문서에 없으면 슬롯을 추가하지 않고 버튼 인접 에러를 표시한다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture()}
        onChange={onChange}
      />,
    );
    await userEvent.type(screen.getByLabelText('새 슬롯 항목명'), '담당자');
    await userEvent.type(screen.getByLabelText('새 슬롯 예시값'), '존재하지않는값');
    await userEvent.click(screen.getByRole('button', { name: '추가' }));

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('alert')).toHaveTextContent(
      /예시값을 문서에서 찾지 못했습니다/,
    );
  });

  // doc-extractor-slot-add-fix FR-01: MCP pdf_to_html 실출력(숫자 엔티티/span 분절)
  it('엔티티/분절 문서에서도 화면 표기 예시값으로 슬롯을 추가한다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture({
          html: '<p><span>&#xb2f4;</span><span>&#xb2f9;&#xc790;: &#xae40;&#xacfc;&#xc7a5;</span></p>',
        })}
        onChange={onChange}
      />,
    );
    await userEvent.type(screen.getByLabelText('새 슬롯 항목명'), '담당자');
    await userEvent.type(screen.getByLabelText('새 슬롯 예시값'), '김과장');
    await userEvent.click(screen.getByRole('button', { name: '추가' }));

    const updated = onChange.mock.calls.at(-1)?.[0] as DocumentExtractorDraft;
    expect(updated.slots).toHaveLength(2);
    expect(updated.slots[1].sample_value).toBe('김과장');
  });

  it('추가 성공 시 성공 피드백을 표시하고 입력 필드를 초기화한다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture()}
        onChange={onChange}
      />,
    );
    await userEvent.type(screen.getByLabelText('새 슬롯 항목명'), '담당자');
    await userEvent.type(screen.getByLabelText('새 슬롯 예시값'), '5억 원');
    await userEvent.click(screen.getByRole('button', { name: '추가' }));

    expect(screen.getByRole('status')).toHaveTextContent(
      "'담당자' 슬롯이 추가되었습니다.",
    );
    expect(screen.getByLabelText('새 슬롯 항목명')).toHaveValue('');
    expect(screen.getByLabelText('새 슬롯 예시값')).toHaveValue('');
  });

  it('입력값을 다시 수정하면 이전 피드백이 사라진다', async () => {
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture()}
        onChange={vi.fn()}
      />,
    );
    await userEvent.type(screen.getByLabelText('새 슬롯 항목명'), '담당자');
    await userEvent.type(screen.getByLabelText('새 슬롯 예시값'), '없는값');
    await userEvent.click(screen.getByRole('button', { name: '추가' }));
    expect(screen.getByRole('alert')).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText('새 슬롯 예시값'), '5');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

// sessionStorage 복원(R4) 테스트는 LeftConfigPanel.test.tsx로 이관 (tool-config-modal Design §2.5)

describe('DocumentExtractorConfigPanel — 재요청', () => {
  it('재요청 시 refine 응답 슬롯으로 교체되고 regenCount가 증가한다', async () => {
    server.use(
      http.post(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_REFINE}`, () =>
        HttpResponse.json({
          suggested_slots: [
            {
              key: 'applicant', label: '신청자명', slot_type: 'value',
              description: '', fill_hint: '', sample_value: '홍길동',
            },
          ],
        }),
      ),
    );
    const onChange = vi.fn();
    renderWithQuery(
      <DocumentExtractorConfigPanel
        draft={draftFixture()}
        onChange={onChange}
      />,
    );
    await userEvent.type(
      screen.getByLabelText('재추천 요청'),
      '신청자 항목도 추가해줘',
    );
    await userEvent.click(screen.getByRole('button', { name: '재요청' }));

    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const updated = onChange.mock.calls[0][0] as DocumentExtractorDraft;
    expect(updated.slots[0].key).toBe('applicant');
    expect(updated.regenCount).toBe(1);
  });
});
