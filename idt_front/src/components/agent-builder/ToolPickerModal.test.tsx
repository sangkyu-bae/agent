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
    is_builtin: false,
  },
  {
    tool_id: 'mcp:weather',
    source: 'mcp',
    name: '날씨',
    description: 'MCP 날씨 도구',
    mcp_server_id: 's1',
    mcp_server_name: 'weather-server',
    requires_env: [],
    is_builtin: false,
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

  // builtin-tools D8: 빌트인 카드 — 기본 선택 + "기본" 배지 + 전용 콜백 분리
  describe('빌트인 도구', () => {
    const BUILTIN_TOOL: CatalogTool = {
      tool_id: 'internal:wiki_read',
      source: 'internal',
      name: '에이전트 위키 열람',
      description: '위키 문서 열람',
      mcp_server_id: null,
      mcp_server_name: null,
      requires_env: [],
      is_builtin: true,
    };

    it('빌트인 도구에 "기본" 배지를 표시하고 기본 선택 상태로 렌더한다', () => {
      render(
        <ToolPickerModal
          isOpen
          catalogTools={[BUILTIN_TOOL, ...TOOLS]}
          selectedIds={[]}
          excludedBuiltinIds={[]}
          onToggle={vi.fn()}
          onToggleBuiltin={vi.fn()}
          onClose={vi.fn()}
        />,
      );
      expect(screen.getByText('기본')).toBeInTheDocument();
      // 선택 스타일(violet 보더)은 체크 아이콘 존재로 확인
      const card = screen.getByText('에이전트 위키 열람').closest('button')!;
      expect(card.querySelector('svg')).not.toBeNull();
    });

    it('빌트인 토글은 onToggle이 아니라 onToggleBuiltin으로 위임된다', async () => {
      const onToggle = vi.fn();
      const onToggleBuiltin = vi.fn();
      render(
        <ToolPickerModal
          isOpen
          catalogTools={[BUILTIN_TOOL]}
          selectedIds={[]}
          excludedBuiltinIds={[]}
          onToggle={onToggle}
          onToggleBuiltin={onToggleBuiltin}
          onClose={vi.fn()}
        />,
      );
      await userEvent.click(screen.getByText('에이전트 위키 열람'));
      expect(onToggleBuiltin).toHaveBeenCalledWith('internal:wiki_read');
      expect(onToggle).not.toHaveBeenCalled();
    });

    it('excluded된 빌트인은 선택 해제 상태로 렌더한다', () => {
      render(
        <ToolPickerModal
          isOpen
          catalogTools={[BUILTIN_TOOL]}
          selectedIds={[]}
          excludedBuiltinIds={['internal:wiki_read']}
          onToggle={vi.fn()}
          onToggleBuiltin={vi.fn()}
          onClose={vi.fn()}
        />,
      );
      const card = screen.getByText('에이전트 위키 열람').closest('button')!;
      expect(card.querySelector('svg')).toBeNull();
    });

    it('onToggleBuiltin 미전달(edit 모드) 시 빌트인도 일반 도구로 동작한다', async () => {
      const onToggle = vi.fn();
      render(
        <ToolPickerModal
          isOpen
          catalogTools={[BUILTIN_TOOL]}
          selectedIds={[]}
          onToggle={onToggle}
          onClose={vi.fn()}
        />,
      );
      expect(screen.queryByText('기본')).not.toBeInTheDocument();
      await userEvent.click(screen.getByText('에이전트 위키 열람'));
      expect(onToggle).toHaveBeenCalledWith('internal:wiki_read');
    });
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
