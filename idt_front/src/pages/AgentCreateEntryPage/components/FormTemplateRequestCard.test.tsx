// wizard-template-request Design §8.3 L2-02~L2-06 — 양식 요청 카드 (MSW)
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import { EXTRACT_ERROR_MESSAGE } from '@/utils/documentExtractorErrors';
import { extractResponseToDraft } from '@/utils/wizardTemplate';
import type { ExtractDocumentResponse } from '@/types/documentExtractor';
import FormTemplateRequestCard, {
  type FormTemplateRequestCardProps,
} from './FormTemplateRequestCard';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const REQUEST = {
  tool_id: 'internal:document_extractor',
  kind: 'form_template' as const,
  message: '여신심의서 작성에 쓸 양식 파일(PDF 또는 DOCX)을 올려주세요.',
  accept: ['pdf', 'docx'],
};

const EXTRACT: ExtractDocumentResponse = {
  source_file_id: 'file-1',
  source_format: 'docx',
  html: '<p>회사명: ㅇㅇ상사</p><p>금액: 5억</p>',
  preview_html: null,
  suggested_slots: [
    { key: 'company', label: '회사명', slot_type: 'value', description: '법인명', fill_hint: '', sample_value: 'ㅇㅇ상사' },
    { key: 'amount', label: '금액', slot_type: 'value', description: '', fill_hint: '', sample_value: '5억' },
  ],
  mcp_pdf_to_html_tool_id: 'mcp:pdf',
  mcp_html_to_doc_tool_id: 'mcp:doc',
};

const stubExtract = (
  body: ExtractDocumentResponse | { detail: { code: string; message: string } } = EXTRACT,
  status = 200,
) => {
  const calls: string[] = [];
  server.use(
    http.post(`*${API_ENDPOINTS.DOCUMENT_EXTRACTOR_EXTRACT}`, async ({ request }) => {
      // jsdom multipart 는 formData() 로 못 읽는다 — raw 본문에서 파일명만 단언
      calls.push(await request.text());
      return HttpResponse.json(body, { status });
    }),
  );
  return calls;
};

const renderCard = (over: Partial<FormTemplateRequestCardProps> = {}) => {
  const onDraftChange = vi.fn();
  const onBusyChange = vi.fn();
  const Wrapper = createWrapper();
  render(
    <Wrapper>
      <FormTemplateRequestCard
        request={REQUEST}
        draft={null}
        onDraftChange={onDraftChange}
        onBusyChange={onBusyChange}
        {...over}
      />
    </Wrapper>,
  );
  return { onDraftChange, onBusyChange };
};

const docx = (name = '여신심의서.docx') =>
  new File(['PK'], name, {
    type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  });

describe('FormTemplateRequestCard — idle', () => {
  it('서버 문구와 파일 입력(PDF, DOCX)을 보여준다', () => {
    renderCard();
    expect(screen.getByText(/여신심의서 작성에 쓸 양식 파일/)).toBeInTheDocument();
    const input = screen.getByLabelText('양식 파일 선택') as HTMLInputElement;
    expect(input.accept).toBe('.pdf,.docx');
    expect(screen.getByText('PDF, DOCX')).toBeInTheDocument();
  });
});

describe('FormTemplateRequestCard — 첨부 → 추출 (L2-02·L2-03)', () => {
  it('파일 선택 즉시 extract 를 부르고 busy 를 알린 뒤 드래프트를 올린다', async () => {
    const calls = stubExtract();
    const { onDraftChange, onBusyChange } = renderCard();
    await userEvent.upload(screen.getByLabelText('양식 파일 선택'), docx());

    await waitFor(() => expect(onDraftChange).toHaveBeenCalledTimes(1));
    expect(calls).toHaveLength(1);
    // jsdom/undici 는 multipart 파일명을 "blob" 으로 보내므로 file 필드 존재만 단언
    expect(calls[0]).toContain('name="file"');
    expect(onBusyChange.mock.calls.map((c) => c[0])).toEqual([true, false]);
    const draft = onDraftChange.mock.calls[0][0];
    expect(draft.confirmed).toBe(false);
    expect(draft.templateName).toBe('여신심의서');
    expect(draft.slots).toHaveLength(2);
  });

  it('추출 실패(413)는 코드 문구를 alert 로 보이고 드래프트는 null (L2-05)', async () => {
    stubExtract({ detail: { code: 'DOCUMENT_TOO_LARGE', message: 'too big' } }, 413);
    const { onDraftChange, onBusyChange } = renderCard();
    await userEvent.upload(screen.getByLabelText('양식 파일 선택'), docx());

    expect(await screen.findByRole('alert')).toHaveTextContent(
      EXTRACT_ERROR_MESSAGE.DOCUMENT_TOO_LARGE,
    );
    expect(onDraftChange).toHaveBeenCalledWith(null);
    expect(onBusyChange).toHaveBeenLastCalledWith(false);
    // 재시도 가능 — 파일 입력이 다시 보인다
    expect(screen.getByLabelText('양식 파일 선택')).toBeInTheDocument();
  });
});

describe('FormTemplateRequestCard — review → confirmed (L2-04·L2-06)', () => {
  const reviewDraft = () => extractResponseToDraft(EXTRACT, '여신심의서.docx');

  it('슬롯 목록(label·description·예시)과 [이대로 사용]을 보여준다', () => {
    renderCard({ draft: reviewDraft() });
    expect(screen.getByText('채움 항목 2개를 찾았습니다')).toBeInTheDocument();
    const list = screen.getByRole('list', { name: '채움 항목' });
    expect(list).toHaveTextContent('회사명');
    expect(list).toHaveTextContent('법인명');
    expect(list).toHaveTextContent('예: ㅇㅇ상사');
    expect(screen.getByRole('button', { name: '이대로 사용' })).toBeInTheDocument();
    expect(screen.getByText(/세부 수정은 생성 후 스튜디오/)).toBeInTheDocument();
  });

  it('[이대로 사용]은 토큰화된 확정 드래프트를 올린다', async () => {
    const { onDraftChange } = renderCard({ draft: reviewDraft() });
    await userEvent.click(screen.getByRole('button', { name: '이대로 사용' }));
    const draft = onDraftChange.mock.calls[0][0];
    expect(draft.confirmed).toBe(true);
    expect(draft.htmlSkeleton).toContain('{{company}}');
    expect(draft.slots).toHaveLength(2);
  });

  it('예시값을 하나도 못 찾으면 NO_USABLE_SLOTS 문구, 확정 안 됨 (L2-06)', async () => {
    const draft = { ...reviewDraft(), html: '<p>아무것도 없음</p>' };
    const { onDraftChange } = renderCard({ draft });
    await userEvent.click(screen.getByRole('button', { name: '이대로 사용' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/확정할 수 있는 항목이 없습니다/);
    expect(onDraftChange).not.toHaveBeenCalled();
  });

  it('확정 상태는 요약을 보여주고 [다시 올리기]로 초기화한다', async () => {
    const confirmed = { ...reviewDraft(), confirmed: true, htmlSkeleton: '<p>{{company}}</p>' };
    const { onDraftChange } = renderCard({ draft: confirmed });
    expect(screen.getByText('✓ 양식 등록: 여신심의서 · 슬롯 2개')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '이대로 사용' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '다시 올리기' }));
    expect(onDraftChange).toHaveBeenCalledWith(null);
  });
});

describe('FormTemplateRequestCard — locked (FR-11)', () => {
  it('확정이면 등록 이력, 건너뜀이면 건너뜀 표기', () => {
    const confirmed = {
      ...extractResponseToDraft(EXTRACT, 'a.docx'),
      confirmed: true,
      htmlSkeleton: 'x',
    };
    const { unmount } = render(
      <FormTemplateRequestCard
        request={REQUEST}
        draft={confirmed}
        locked
        onDraftChange={vi.fn()}
        onBusyChange={vi.fn()}
      />,
      { wrapper: createWrapper() },
    );
    expect(screen.getByText('✓ 양식 등록: a · 슬롯 2개')).toBeInTheDocument();
    unmount();
    render(
      <FormTemplateRequestCard
        request={REQUEST}
        draft={null}
        locked
        skipped
        onDraftChange={vi.fn()}
        onBusyChange={vi.fn()}
      />,
      { wrapper: createWrapper() },
    );
    expect(screen.getByText('✓ 건너뜀(양식)')).toBeInTheDocument();
    expect(screen.queryByLabelText('양식 파일 선택')).not.toBeInTheDocument();
  });
});
