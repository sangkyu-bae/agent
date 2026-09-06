// agent-update-tool-editing D §5.1 — 저장 payload 의 tool_ids 구성
import { describe, it, expect } from 'vitest';
import { buildToolIdsForSave } from './agentToolPayload';
import type { CatalogTool } from '@/types/toolCatalog';

const tool = (over: Partial<CatalogTool> = {}): CatalogTool => ({
  tool_id: 'internal:tavily_search',
  source: 'internal',
  name: '웹 검색',
  description: '',
  mcp_server_id: null,
  mcp_server_name: null,
  requires_env: [],
  is_builtin: false,
  category: null,
  max_tool_calls: null,
  ...over,
});

const catalog: CatalogTool[] = [
  tool(),
  tool({ tool_id: 'internal:excel_export', name: '엑셀' }),
  tool({ tool_id: 'internal:wiki_read', name: '위키 열람', is_builtin: true }),
  tool({ tool_id: 'internal:wiki_list', name: '위키 목록', is_builtin: true }),
];

describe('buildToolIdsForSave', () => {
  it('사용자 선택 도구를 순서 그대로 반환한다', () => {
    expect(
      buildToolIdsForSave(['internal:tavily_search', 'internal:excel_export'], catalog),
    ).toEqual(['internal:tavily_search', 'internal:excel_export']);
  });

  it('빌트인은 제외한다 — 서버가 규칙대로 재주입하고, 도구 상한에서도 빠져야 한다', () => {
    expect(
      buildToolIdsForSave(
        ['internal:tavily_search', 'internal:wiki_read', 'internal:wiki_list'],
        catalog,
      ),
    ).toEqual(['internal:tavily_search']);
  });

  it('빈 선택은 빈 배열 — undefined(무변경)와 구분된다', () => {
    expect(buildToolIdsForSave([], catalog)).toEqual([]);
  });

  it('카탈로그에 없는 도구는 그대로 남긴다 (서버가 검증)', () => {
    expect(buildToolIdsForSave(['mcp:srv-1:fetch'], catalog)).toEqual([
      'mcp:srv-1:fetch',
    ]);
  });

  it('카탈로그 미로딩 시 선택을 그대로 통과시킨다', () => {
    expect(buildToolIdsForSave(['internal:wiki_read'], undefined)).toEqual([
      'internal:wiki_read',
    ]);
  });
});
