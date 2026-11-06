// agent-kb-quick-setup Design §8.3 L2 #10~#12 — 위저드 문서 단계 (MSW 기본 핸들러)
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import DocumentsStep from './DocumentsStep';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderStep = (over: Partial<Parameters<typeof DocumentsStep>[0]> = {}) => {
  const props = {
    agentName: '문서 Q&A 봇',
    attachedKbId: null,
    isPending: false,
    onAttached: vi.fn(),
    onDetach: vi.fn(),
    onSkip: vi.fn(),
    onContinue: vi.fn(),
    ...over,
  };
  const Wrapper = createWrapper();
  render(
    <Wrapper>
      <DocumentsStep {...props} />
    </Wrapper>,
  );
  return props;
};

describe('DocumentsStep', () => {
  it('제목·블록·건너뛰기가 보이고 KB 없이는 [계속]이 비활성이다', async () => {
    renderStep();
    expect(screen.getByText('참고할 문서가 있나요?')).toBeInTheDocument();
    expect(await screen.findByRole('region', { name: '지식 문서' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '건너뛰기' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: '계속' })).toBeDisabled();
  });

  it('[건너뛰기]는 onSkip 을 부른다', async () => {
    const props = renderStep();
    await userEvent.click(screen.getByRole('button', { name: '건너뛰기' }));
    expect(props.onSkip).toHaveBeenCalled();
  });

  it('KB 가 연결되면 [계속]이 활성화되고 onContinue 를 부른다', async () => {
    const props = renderStep({ attachedKbId: 'kb-public-1' });
    expect(await screen.findByText(/연결됨: 전사 규정/)).toBeInTheDocument();
    const next = screen.getByRole('button', { name: '계속' });
    expect(next).not.toBeDisabled();
    await userEvent.click(next);
    expect(props.onContinue).toHaveBeenCalled();
  });

  it('기존 KB 선택이 onAttached 로 전달된다', async () => {
    const props = renderStep();
    await userEvent.click(await screen.findByRole('combobox', { name: '기존 지식베이스 선택' }));
    await userEvent.click(await screen.findByRole('option', { name: '[부서] 여신 심사 기준' }));
    expect(props.onAttached).toHaveBeenCalledWith('kb-dept-1');
  });

  it('locked 면 버튼이 사라지고 완료 배지만 남는다', async () => {
    renderStep({ attachedKbId: 'kb-public-1', locked: true });
    await screen.findByText(/연결됨/);
    expect(screen.getByText('✓ 문서 연결 완료')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '계속' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '바꾸기' })).not.toBeInTheDocument();
  });

  it('locked + KB 없음이면 건너뜀 배지', () => {
    renderStep({ locked: true });
    expect(screen.getByText('✓ 건너뜀')).toBeInTheDocument();
  });
});

// ── wizard-template-request Design §8.3 L2-01·L2-11·FR-15 — 양식 요청 카드 조립 ──

const FORM_REQUEST = {
  tool_id: 'internal:document_extractor',
  kind: 'form_template' as const,
  message: '여신심의서 작성에 쓸 양식 파일(PDF 또는 DOCX)을 올려주세요.',
  accept: ['pdf', 'docx'],
};

const confirmedDraft = () => ({
  sourceFileId: 'file-1',
  sourceFormat: 'docx' as const,
  html: '<p>{{company}}</p>',
  slots: [
    { key: 'company', label: '회사명', slot_type: 'value' as const, description: '', fill_hint: '', sample_value: 'ㅇㅇ상사' },
  ],
  mcpPdfToHtmlToolId: 'mcp:pdf',
  mcpHtmlToDocToolId: 'mcp:doc',
  regenCount: 0,
  confirmed: true,
  templateName: '여신심의서',
  htmlSkeleton: '<p>{{company}}</p>',
});

describe('DocumentsStep — 양식 요청 카드 (wizard-template-request)', () => {
  it('document_requests 가 0건이면 카드가 없다 (L2-01)', () => {
    renderStep();
    expect(screen.queryByRole('region', { name: '양식 요청' })).not.toBeInTheDocument();
  });

  it('form_template 요청이 있으면 카드가 참고 문서 블록 위에 뜬다', async () => {
    renderStep({ documentRequests: [FORM_REQUEST] });
    const card = screen.getByRole('region', { name: '양식 요청' });
    expect(card).toHaveTextContent(/여신심의서 작성에 쓸 양식 파일/);
    const kb = await screen.findByRole('region', { name: '지식 문서' });
    expect(card.compareDocumentPosition(kb) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('양식만 확정돼도(KB 없이) [계속]이 활성화된다 (FR-14)', () => {
    renderStep({ documentRequests: [FORM_REQUEST], templateDraft: confirmedDraft() });
    expect(screen.getByRole('button', { name: '계속' })).not.toBeDisabled();
  });

  it('추출 진행 중이면 [건너뛰기]·[계속]이 모두 비활성이다 (FR-15)', () => {
    renderStep({
      documentRequests: [FORM_REQUEST],
      templateDraft: confirmedDraft(),
      templateBusy: true,
    });
    expect(screen.getByRole('button', { name: '건너뛰기' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '계속' })).toBeDisabled();
  });

  it('잠긴 상태에서 양식만 등록됐어도 "문서 연결 완료"로 표기한다', () => {
    renderStep({
      documentRequests: [FORM_REQUEST],
      templateDraft: confirmedDraft(),
      locked: true,
    });
    expect(screen.getByText('✓ 문서 연결 완료')).toBeInTheDocument();
    expect(screen.getByText('✓ 양식 등록: 여신심의서 · 슬롯 1개')).toBeInTheDocument();
  });
});
