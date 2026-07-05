import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import type { CatalogTool } from '@/types/toolCatalog';
import ToolPickerModal from './ToolPickerModal';

const TOOLS: CatalogTool[] = [
  {
    tool_id: 'internal:internal_document_search',
    source: 'internal',
    name: '문서 검색',
    description: '내부 문서 RAG 검색',
    mcp_server_id: null,
    mcp_server_name: null,
    requires_env: [],
  },
  {
    tool_id: 'mcp:weather',
    source: 'mcp',
    name: '날씨',
    description: 'MCP 날씨 도구',
    mcp_server_id: 's1',
    mcp_server_name: 'weather-server',
    requires_env: [],
  },
];

describe('ToolPickerModal', () => {
  it('항목 클릭 시 onToggle이 tool_id로 호출된다', async () => {
    const onToggle = vi.fn();
    render(
      <ToolPickerModal
        isOpen
        catalogTools={TOOLS}
        selectedIds={[]}
        onToggle={onToggle}
        onClose={vi.fn()}
      />,
    );

    await userEvent.click(screen.getByText('문서 검색'));
    expect(onToggle).toHaveBeenCalledWith('internal:internal_document_search');
  });

  // fix-agent-composer FR-08: 저장 API가 mcp_* tool_id를 수용하므로 생성 모드 차단 해제
  it('생성 모드에서도 MCP 도구를 선택할 수 있다', async () => {
    const onToggle = vi.fn();
    render(
      <ToolPickerModal
        isOpen
        catalogTools={TOOLS}
        selectedIds={[]}
        onToggle={onToggle}
        onClose={vi.fn()}
      />,
    );

    const mcpButton = screen.getByText('날씨').closest('button')!;
    expect(mcpButton).not.toBeDisabled();
    await userEvent.click(mcpButton);
    expect(onToggle).toHaveBeenCalledWith('mcp:weather');
  });

  it('MCP 도구에 MCP 뱃지를 표시한다', () => {
    render(
      <ToolPickerModal
        isOpen
        catalogTools={TOOLS}
        selectedIds={[]}
        onToggle={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText('MCP')).toBeInTheDocument();
  });

  it('완료 버튼 클릭 시 onClose가 호출된다', async () => {
    const onClose = vi.fn();
    render(
      <ToolPickerModal
        isOpen
        catalogTools={TOOLS}
        selectedIds={[]}
        onToggle={vi.fn()}
        onClose={onClose}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: '완료' }));
    expect(onClose).toHaveBeenCalled();
  });
});
