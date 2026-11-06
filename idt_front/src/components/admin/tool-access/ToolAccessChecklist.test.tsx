import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import ToolAccessChecklist from './ToolAccessChecklist';
import type { CatalogTool } from '@/types/toolCatalog';

const SRV = '7f3c0000-0000-0000-0000-000000000001';

const tool = (over: Partial<CatalogTool>): CatalogTool => ({
  tool_id: 'internal:x',
  source: 'internal',
  name: 'x',
  description: '',
  mcp_server_id: null,
  mcp_server_name: null,
  requires_env: [],
  is_builtin: false,
  category: null,
  max_tool_calls: null,
  requires_approval: false,
  ...over,
});

const TOOLS: CatalogTool[] = [
  tool({ tool_id: 'internal:internal_document_search', name: '내부 문서 검색' }),
  tool({ tool_id: 'internal:python_code_executor', name: 'Python 코드 실행' }),
  tool({ tool_id: `mcp:${SRV}:search_ticket`, source: 'mcp', mcp_server_id: SRV, name: 'search_ticket' }),
  tool({
    tool_id: `mcp:${SRV}:write_ticket`, source: 'mcp', mcp_server_id: SRV, name: 'write_ticket',
    requires_approval: true,
  }),
];

const setup = (over: Partial<Parameters<typeof ToolAccessChecklist>[0]> = {}) => {
  const onToggle = vi.fn();
  const onSetMany = vi.fn();
  render(
    <ToolAccessChecklist
      tools={TOOLS}
      serverNames={{ [SRV]: '사내 티켓 시스템' }}
      selected={new Set(['internal:python_code_executor'])}
      locks={{ 'internal:internal_document_search': '기본' }}
      onToggle={onToggle}
      onSetMany={onSetMany}
      {...over}
    />,
  );
  return { onToggle, onSetMany };
};

describe('ToolAccessChecklist', () => {
  it('내부 도구와 MCP 서버별 그룹으로 나눈다', () => {
    setup();
    expect(screen.getByRole('group', { name: '내부 도구' })).toBeInTheDocument();
    const mcp = screen.getByRole('group', { name: 'MCP: 사내 티켓 시스템' });
    expect(within(mcp).getAllByRole('checkbox')).toHaveLength(2);
  });

  it('잠금 항목은 체크·비활성이고 잠금 사유 배지를 보인다', () => {
    setup();
    const locked = screen.getByRole('checkbox', { name: '내부 문서 검색' });
    expect(locked).toBeChecked();
    expect(locked).toBeDisabled();
    expect(screen.getByText('기본')).toBeInTheDocument();
  });

  it('선택 상태를 반영하고 클릭하면 onToggle', async () => {
    const { onToggle } = setup();
    const py = screen.getByRole('checkbox', { name: 'Python 코드 실행' });
    expect(py).toBeChecked();
    await userEvent.click(screen.getByRole('checkbox', { name: 'search_ticket' }));
    expect(onToggle).toHaveBeenCalledWith(`mcp:${SRV}:search_ticket`);
  });

  it('승인 필요 배지', () => {
    setup();
    expect(screen.getByText('승인 필요')).toBeInTheDocument();
  });

  it('서버 그룹 전체 선택·해제는 잠금 항목을 제외한 도구로 onSetMany', async () => {
    const { onSetMany } = setup({ locks: { [`mcp:${SRV}:search_ticket`]: '기본' } });
    const mcp = screen.getByRole('group', { name: 'MCP: 사내 티켓 시스템' });
    await userEvent.click(within(mcp).getByRole('button', { name: '전체 선택' }));
    expect(onSetMany).toHaveBeenCalledWith([`mcp:${SRV}:write_ticket`], true);
    await userEvent.click(within(mcp).getByRole('button', { name: '전체 해제' }));
    expect(onSetMany).toHaveBeenLastCalledWith([`mcp:${SRV}:write_ticket`], false);
  });

  it('서버 이름을 모르면 id 앞부분으로 표시', () => {
    setup({ serverNames: {} });
    expect(screen.getByRole('group', { name: 'MCP: 7f3c0000' })).toBeInTheDocument();
  });

  it('extraBadges 로 행별 상태 배지를 붙인다', () => {
    setup({ extraBadges: (t) => (t.tool_id.endsWith('write_ticket') ? ['미지정(차단)'] : []) });
    expect(screen.getByText('미지정(차단)')).toBeInTheDocument();
  });

  it('disabled 면 모든 체크박스와 버튼이 비활성', () => {
    setup({ disabled: true });
    screen.getAllByRole('checkbox').forEach((c) => expect(c).toBeDisabled());
    screen.getAllByRole('button').forEach((b) => expect(b).toBeDisabled());
  });
});
