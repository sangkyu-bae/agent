// LeftConfigPanel — 도구 옵션 모달화 테스트 (tool-config-modal Design §2.4/§2.5)
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { server } from '@/__tests__/mocks/server';
import type { CatalogTool } from '@/types/toolCatalog';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import type { DocumentExtractorDraft } from '@/types/documentExtractor';
import { DOCUMENT_EXTRACTOR_TOOL_ID } from '@/types/documentExtractor';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import { DRAFT_STORAGE_KEY } from '@/utils/documentTemplate';
import LeftConfigPanel from './LeftConfigPanel';

beforeAll(() => server.listen());
afterEach(() => {
  server.resetHandlers();
  sessionStorage.clear();
});
afterAll(() => server.close());

const RAG_TOOL_ID = 'internal:internal_document_search';

const catalogTool = (overrides: Partial<CatalogTool>): CatalogTool => ({
  tool_id: '',
  source: 'internal',
  name: '',
  description: '',
  mcp_server_id: null,
  mcp_server_name: null,
  requires_env: [],
  ...overrides,
});

const CATALOG_TOOLS: CatalogTool[] = [
  catalogTool({ tool_id: RAG_TOOL_ID, name: '내부 문서 검색', description: 'RAG 검색' }),
  catalogTool({ tool_id: DOCUMENT_EXTRACTOR_TOOL_ID, name: '문서추출기', description: '양식 자동화' }),
  catalogTool({ tool_id: 'internal:web_search', name: '웹 검색', description: '웹 검색 지원' }),
];

const BASE_FORM: AgentBuilderFormData = {
  name: '테스트',
  description: '',
  model: '',
  systemPrompt: '',
  tools: [],
  temperature: 0.7,
  toolConfigs: {},
  subAgents: [],
  skills: [],
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

const renderPanel = (formOverrides: Partial<AgentBuilderFormData> = {}, onChange = vi.fn(), extra: Partial<Parameters<typeof LeftConfigPanel>[0]> = {}) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const form = { ...BASE_FORM, ...formOverrides };
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <LeftConfigPanel
        form={form}
        onChange={onChange}
        onToolToggle={vi.fn()}
        onSkillToggle={vi.fn()}
        onRagConfigChange={vi.fn()}
        isEditMode={false}
        catalogTools={CATALOG_TOOLS}
        isToolsLoading={false}
        isToolsError={false}
        onRetryTools={vi.fn()}
        models={[]}
        isModelsLoading={false}
        isModelsError={false}
        onRetryModels={vi.fn()}
        {...extra}
      />
    </QueryClientProvider>,
  );
  return { ...utils, onChange };
};

describe('LeftConfigPanel — 지침 필수 (agent-instruction-required)', () => {
  it('지침 placeholder에 자동 생성 안내 문구가 없다 (생성 모드)', () => {
    renderPanel({}, vi.fn(), { isEditMode: false });
    const textarea = screen.getByLabelText('지침');
    expect(textarea).toHaveAttribute(
      'placeholder',
      '에이전트의 시스템 프롬프트/지침을 입력하세요...',
    );
    expect(screen.queryByPlaceholderText(/자동 생성/)).toBeNull();
  });

  it('지침 섹션에 "필수" 뱃지가 표시된다', () => {
    renderPanel();
    expect(screen.getByText('필수')).toBeInTheDocument();
  });

  it('systemPromptError 전달 시 role=alert 에러 메시지를 표시한다', () => {
    renderPanel({}, vi.fn(), { systemPromptError: '지침을 입력해주세요.' });
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('지침을 입력해주세요.');
    expect(screen.getByLabelText('지침')).toHaveAttribute('aria-invalid', 'true');
  });

  it('에러가 없으면 글자 수 카운터를 표시한다', () => {
    renderPanel({ systemPrompt: '안녕' });
    expect(screen.getByText('2자')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).toBeNull();
  });
});

describe('LeftConfigPanel — 인라인 패널 제거', () => {
  it('RAG 도구 선택 시 인라인 설정 패널이 렌더되지 않는다', () => {
    renderPanel({
      tools: [RAG_TOOL_ID],
      toolConfigs: { [RAG_TOOL_ID]: { ...DEFAULT_RAG_CONFIG } },
    });
    // 인라인 패널의 고유 레이블이 없어야 함
    expect(screen.queryByText('검색 대상 컬렉션')).toBeNull();
  });

  it('문서추출기 선택 시 인라인 양식 패널이 렌더되지 않는다', () => {
    renderPanel({ tools: [DOCUMENT_EXTRACTOR_TOOL_ID] });
    expect(screen.queryByLabelText('양식 문서 업로드')).toBeNull();
  });
});

describe('LeftConfigPanel — 설정 버튼/배지', () => {
  it('설정형 도구 행에는 설정 버튼이, 일반 도구 행에는 없다', () => {
    renderPanel({
      tools: [RAG_TOOL_ID, 'internal:web_search'],
      toolConfigs: { [RAG_TOOL_ID]: { ...DEFAULT_RAG_CONFIG } },
    });
    expect(screen.getByRole('button', { name: '내부 문서 검색 설정' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '웹 검색 설정' })).toBeNull();
  });

  it('RAG 행에 컬렉션·모드·top_k 요약 배지가 표시된다', () => {
    renderPanel({
      tools: [RAG_TOOL_ID],
      toolConfigs: {
        [RAG_TOOL_ID]: { ...DEFAULT_RAG_CONFIG, search_mode: 'hybrid', top_k: 5 },
      },
    });
    expect(screen.getByText(/전체 · 하이브리드 · top_k 5/)).toBeInTheDocument();
  });

  it('문서추출기 드래프트 없음 → "양식 미등록" 배지', () => {
    renderPanel({ tools: [DOCUMENT_EXTRACTOR_TOOL_ID] });
    expect(screen.getByText(/양식 미등록/)).toBeInTheDocument();
  });

  it('미확정 드래프트 → "작성 중" 배지 (슬롯 수 포함)', () => {
    renderPanel({
      tools: [DOCUMENT_EXTRACTOR_TOOL_ID],
      documentExtractorDraft: DRAFT,
    });
    expect(screen.getByText(/작성 중 · 슬롯 1/)).toBeInTheDocument();
  });

  it('확정 드래프트 → "양식 확정됨" 배지', () => {
    renderPanel({
      tools: [DOCUMENT_EXTRACTOR_TOOL_ID],
      documentExtractorDraft: { ...DRAFT, confirmed: true },
    });
    expect(screen.getByText(/양식 확정됨/)).toBeInTheDocument();
  });
});

describe('LeftConfigPanel — 설정 모달 오픈', () => {
  it('RAG 설정 버튼 클릭 시 설정 모달이 열린다', async () => {
    renderPanel({
      tools: [RAG_TOOL_ID],
      toolConfigs: { [RAG_TOOL_ID]: { ...DEFAULT_RAG_CONFIG } },
    });
    await userEvent.click(screen.getByRole('button', { name: '내부 문서 검색 설정' }));
    expect(
      screen.getByRole('dialog', { name: '내부 문서 검색 설정' }),
    ).toBeInTheDocument();
  });

  it('문서추출기 설정 버튼 클릭 시 양식 등록 모달이 열린다', async () => {
    renderPanel({ tools: [DOCUMENT_EXTRACTOR_TOOL_ID] });
    await userEvent.click(screen.getByRole('button', { name: '문서추출기 설정' }));
    expect(
      screen.getByRole('dialog', { name: '문서추출기 — 양식 등록' }),
    ).toBeInTheDocument();
  });
});

describe('LeftConfigPanel — picker에서 설정형 도구 추가 시 자동 오픈', () => {
  it('문서추출기 추가 → picker 닫힘 + 양식 등록 모달 자동 오픈', async () => {
    // onToolToggle이 부모에서 form을 갱신하는 것을 흉내내기 위해 rerender 없이
    // 추가 직전 상태(tools=[])로 렌더하고 토글 후 모달 오픈만 검증
    renderPanel({ tools: [] });

    await userEvent.click(screen.getByRole('button', { name: /도구$/ })); // "+ 도구" 버튼
    expect(screen.getByText('도구 추가')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /문서추출기/ }));

    // picker가 닫히고 설정 모달이 열림
    expect(screen.queryByText('도구 추가')).toBeNull();
    expect(
      screen.getByRole('dialog', { name: '문서추출기 — 양식 등록' }),
    ).toBeInTheDocument();
  });
});

describe('LeftConfigPanel — sessionStorage 복원 (R4 이관)', () => {
  it('추출기 도구 선택 + 드래프트 없음 + 저장본 존재 → 복원 onChange 호출', async () => {
    sessionStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(DRAFT));
    const onChange = vi.fn();
    renderPanel({ tools: [DOCUMENT_EXTRACTOR_TOOL_ID] }, onChange);

    await waitFor(() => expect(onChange).toHaveBeenCalled());
    const updated = onChange.mock.calls[0][0] as AgentBuilderFormData;
    expect(updated.documentExtractorDraft?.templateName).toBe('여신심의서');
  });

  it('드래프트가 null로 바뀌면 sessionStorage도 정리된다', () => {
    sessionStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(DRAFT));
    renderPanel({ tools: [], documentExtractorDraft: null });
    expect(sessionStorage.getItem(DRAFT_STORAGE_KEY)).toBeNull();
  });
});
