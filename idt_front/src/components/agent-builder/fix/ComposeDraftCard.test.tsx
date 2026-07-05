import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';
import ComposeDraftCard from './ComposeDraftCard';

const partialDraft: ComposeAgentDraftResponse = {
  coverage: 'partial',
  name_suggestion: '재무 리포터',
  system_prompt: '당신은 재무 에이전트입니다.',
  tool_ids: ['tavily_search', 'mcp_srv-1'],
  workers: [],
  flow_hint: 'tavily_search → mcp_srv-1',
  llm_model_id: 'model-default',
  temperature: 0.7,
  missing_capabilities: [
    { capability: '사내 ERP 조회', reason: '매칭 도구 없음', suggestion: 'ERP MCP 등록 필요' },
  ],
  notes: '웹 수집은 Tavily로 대체',
};

const noneDraft: ComposeAgentDraftResponse = {
  ...partialDraft,
  coverage: 'none',
  system_prompt: '',
  tool_ids: [],
  flow_hint: '',
  notes: '매칭되는 도구가 없어 초안을 만들지 못했습니다.',
};

const baseProps = {
  mode: 'create' as const,
  currentToolIds: [] as string[],
  applied: false,
  modelUnresolved: false,
};

describe('ComposeDraftCard (fix-agent-composer F7/F8)', () => {
  it('partial 초안: 이름·도구·coverage·미커버 경고와 적용 버튼을 렌더한다', () => {
    const onApply = vi.fn();
    render(<ComposeDraftCard {...baseProps} draft={partialDraft} onApply={onApply} />);

    expect(screen.getByText('재무 리포터')).toBeInTheDocument();
    expect(screen.getByText('partial')).toBeInTheDocument();
    expect(screen.getByText('tavily_search')).toBeInTheDocument();
    expect(screen.getByText(/사내 ERP 조회/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '적용하기' })).toBeInTheDocument();
  });

  it('MCP 도구 칩에 MCP 뱃지를 표시한다', () => {
    render(<ComposeDraftCard {...baseProps} draft={partialDraft} onApply={vi.fn()} />);
    expect(screen.getByText('MCP')).toBeInTheDocument();
  });

  it('적용하기 클릭 시 onApply가 호출된다', async () => {
    const onApply = vi.fn();
    render(<ComposeDraftCard {...baseProps} draft={partialDraft} onApply={onApply} />);
    await userEvent.click(screen.getByRole('button', { name: '적용하기' }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('무시 클릭 시 액션 버튼이 사라지고 onApply는 호출되지 않는다', async () => {
    const onApply = vi.fn();
    render(<ComposeDraftCard {...baseProps} draft={partialDraft} onApply={onApply} />);
    await userEvent.click(screen.getByRole('button', { name: '무시' }));
    expect(screen.queryByRole('button', { name: '적용하기' })).not.toBeInTheDocument();
    expect(onApply).not.toHaveBeenCalled();
  });

  it('coverage none: 안내만 표시하고 적용 버튼을 노출하지 않는다', () => {
    render(<ComposeDraftCard {...baseProps} draft={noneDraft} onApply={vi.fn()} />);
    expect(
      screen.getByText('현재 등록된 도구로는 요청을 수행할 수 없습니다.'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '적용하기' })).not.toBeInTheDocument();
  });

  it('applied면 적용 버튼 대신 적용됨 뱃지를 표시한다', () => {
    render(
      <ComposeDraftCard {...baseProps} draft={partialDraft} applied onApply={vi.fn()} />,
    );
    expect(screen.getByText('✓ 적용됨')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '적용하기' })).not.toBeInTheDocument();
  });

  it('F8: edit 모드에서 도구가 현재 폼과 다르면 저장 제약 경고를 표시한다', () => {
    render(
      <ComposeDraftCard
        {...baseProps}
        mode="edit"
        currentToolIds={['excel_export']}
        draft={partialDraft}
        onApply={vi.fn()}
      />,
    );
    expect(
      screen.getByText('도구 변경은 수정 화면에서 저장되지 않습니다.'),
    ).toBeInTheDocument();
  });

  it('create 모드에서는 도구가 달라도 저장 제약 경고가 없다', () => {
    render(
      <ComposeDraftCard
        {...baseProps}
        currentToolIds={['excel_export']}
        draft={partialDraft}
        onApply={vi.fn()}
      />,
    );
    expect(
      screen.queryByText('도구 변경은 수정 화면에서 저장되지 않습니다.'),
    ).not.toBeInTheDocument();
  });

  it('도구별 지침이 있으면 접기 토글로 표시한다 (compose-tool-instructions)', async () => {
    const draft: ComposeAgentDraftResponse = {
      ...partialDraft,
      workers: [
        {
          tool_id: 'tavily_search',
          worker_id: 'search_worker',
          description: '검색 담당',
          sort_order: 0,
          tool_config: null,
          instruction: '최신 정보 질문에만 사용.',
        },
        {
          tool_id: 'excel_export',
          worker_id: 'excel_worker',
          description: '엑셀 담당',
          sort_order: 1,
          tool_config: null,
          instruction: '',
        },
      ],
    };
    render(<ComposeDraftCard {...baseProps} draft={draft} onApply={vi.fn()} />);

    // 지침 있는 워커 1개만 카운트, 펼치기 전에는 본문 미노출
    const toggle = screen.getByRole('button', { name: /도구별 지침 보기 \(1\)/ });
    expect(screen.queryByText('최신 정보 질문에만 사용.')).not.toBeInTheDocument();

    await userEvent.click(toggle);
    expect(screen.getByText('최신 정보 질문에만 사용.')).toBeInTheDocument();
    // instruction 빈 워커는 표시되지 않는다
    expect(screen.queryByText('excel_export')).not.toBeInTheDocument();
  });

  it('도구별 지침이 모두 비어있으면 지침 토글을 렌더하지 않는다', () => {
    render(<ComposeDraftCard {...baseProps} draft={partialDraft} onApply={vi.fn()} />);
    expect(screen.queryByRole('button', { name: /도구별 지침/ })).not.toBeInTheDocument();
  });

  it('모델 미매핑 시 모델 유지 안내를 표시한다', () => {
    render(
      <ComposeDraftCard
        {...baseProps}
        modelUnresolved
        draft={partialDraft}
        onApply={vi.fn()}
      />,
    );
    expect(screen.getByText(/현재 모델이 유지됩니다/)).toBeInTheDocument();
  });
});
