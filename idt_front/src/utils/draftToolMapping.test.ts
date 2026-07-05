// compose-tool-instructions FR-08: 저장 형식 draft tool_ids → 카탈로그 형식 매핑
import { describe, it, expect } from 'vitest';
import { mapDraftToolIdsToCatalog } from './draftToolMapping';
import type { CatalogTool } from '@/types/toolCatalog';

const catalog: CatalogTool[] = [
  {
    tool_id: 'internal:excel_export',
    source: 'internal',
    name: 'Excel 내보내기',
    description: '',
    mcp_server_id: null,
    mcp_server_name: null,
    requires_env: [],
  },
  {
    tool_id: 'internal:internal_document_search',
    source: 'internal',
    name: '내부 문서 검색',
    description: '',
    mcp_server_id: null,
    mcp_server_name: null,
    requires_env: [],
  },
  {
    tool_id: 'mcp:srv-1:fetch_page',
    source: 'mcp',
    name: 'fetch_page',
    description: '',
    mcp_server_id: 'srv-1',
    mcp_server_name: '수집 서버',
    requires_env: [],
  },
  {
    tool_id: 'mcp:srv-1:parse_html',
    source: 'mcp',
    name: 'parse_html',
    description: '',
    mcp_server_id: 'srv-1',
    mcp_server_name: '수집 서버',
    requires_env: [],
  },
];

describe('mapDraftToolIdsToCatalog', () => {
  it('internal 도구는 internal:{id} 카탈로그 형식으로 변환한다', () => {
    expect(mapDraftToolIdsToCatalog(['excel_export'], catalog)).toEqual([
      'internal:excel_export',
    ]);
  });

  it('mcp_{서버ID}는 해당 서버의 카탈로그 도구 전체로 전개한다', () => {
    expect(mapDraftToolIdsToCatalog(['mcp_srv-1'], catalog)).toEqual([
      'mcp:srv-1:fetch_page',
      'mcp:srv-1:parse_html',
    ]);
  });

  it('카탈로그에 없는 도구는 원본을 유지한다 (저장 호환)', () => {
    expect(mapDraftToolIdsToCatalog(['unknown_tool', 'mcp_ghost'], catalog)).toEqual([
      'unknown_tool',
      'mcp_ghost',
    ]);
  });

  it('혼합 + 중복 제거', () => {
    expect(
      mapDraftToolIdsToCatalog(
        ['excel_export', 'mcp_srv-1', 'excel_export'],
        catalog,
      ),
    ).toEqual(['internal:excel_export', 'mcp:srv-1:fetch_page', 'mcp:srv-1:parse_html']);
  });

  it('카탈로그 미로딩(undefined)이면 원본을 유지한다', () => {
    expect(mapDraftToolIdsToCatalog(['excel_export'], undefined)).toEqual([
      'excel_export',
    ]);
  });
});
