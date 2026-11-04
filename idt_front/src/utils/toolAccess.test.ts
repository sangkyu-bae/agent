import { describe, it, expect } from 'vitest';
import { ApiError } from '@/services/api/ApiError';
import {
  excludedToolsNotice,
  toCatalogToolId,
  toolAccessDeniedMessage,
  unlistedAttachedTools,
} from './toolAccess';

const SRV = '7f3c0000-0000-0000-0000-000000000001';

describe('toCatalogToolId', () => {
  it.each([
    ['python_code_executor', 'internal:python_code_executor'],
    ['internal:excel_export', 'internal:excel_export'],
    [`mcp:${SRV}:search`, `mcp:${SRV}:search`],
    [`mcp_${SRV}`, `mcp_${SRV}`],
  ])('%s → %s', (raw, expected) => {
    expect(toCatalogToolId(raw)).toBe(expected);
  });
});

describe('toolAccessDeniedMessage', () => {
  const names = (id: string) => ({ 'internal:python_code_executor': 'Python 코드 실행' })[id] ?? id;

  it('TOOL_ACCESS_DENIED 면 도구 이름을 나열한다', () => {
    const err = new ApiError('권한이 없는 도구가 포함되어 있습니다', 403, 'TOOL_ACCESS_DENIED', {
      code: 'TOOL_ACCESS_DENIED', message: 'x', tool_ids: ['internal:python_code_executor', `mcp:${SRV}:w`],
    });
    expect(toolAccessDeniedMessage(err, names)).toBe(
      `권한이 없는 도구가 있어 저장할 수 없습니다: Python 코드 실행, mcp:${SRV}:w`,
    );
  });

  it('다른 오류는 null', () => {
    expect(toolAccessDeniedMessage(new ApiError('x', 403), names)).toBeNull();
    expect(toolAccessDeniedMessage(new Error('x'), names)).toBeNull();
  });

  it('tool_ids 가 없어도 코드만으로 안내', () => {
    const err = new ApiError('m', 403, 'TOOL_ACCESS_DENIED');
    expect(toolAccessDeniedMessage(err, names)).toBe('권한이 없는 도구가 있어 저장할 수 없습니다.');
  });
});

describe('unlistedAttachedTools', () => {
  it('카탈로그에 없는 붙은 도구를 tool_access 이름과 함께 돌려준다 (표기 차이 흡수)', () => {
    const got = unlistedAttachedTools(
      ['internal:excel_export', 'python_code_executor'],
      ['internal:excel_export'],
      [
        { tool_id: 'internal:excel_export', name: 'Excel', permitted: true },
        { tool_id: 'internal:python_code_executor', name: 'Python 코드 실행', permitted: false },
      ],
    );
    expect(got).toEqual([{ formId: 'python_code_executor', name: 'Python 코드 실행', permitted: false }]);
  });

  it('tool_access 정보가 없거나 허용(permitted)인 도구는 권한 문제가 아니므로 제외', () => {
    expect(unlistedAttachedTools(['x_tool'], [], undefined)).toEqual([]);
    expect(
      unlistedAttachedTools(['inactive_tool'], [], [
        { tool_id: 'internal:inactive_tool', name: '비활성 도구', permitted: true },
      ]),
    ).toEqual([]);
  });
});

describe('forkExcludedNotice', () => {
  it('제외 도구가 있으면 안내, 없으면 null', async () => {
    const { forkExcludedNotice } = await import('./toolAccess');
    expect(forkExcludedNotice([{ tool_id: 'a', name: 'A', reason: 'no_permission' }])).toBe(
      '복제본에서 권한이 없는 도구를 제외했습니다: A',
    );
    expect(forkExcludedNotice([])).toBeNull();
    expect(forkExcludedNotice(undefined)).toBeNull();
  });
});

describe('excludedToolsNotice', () => {
  it('이름 나열', () => {
    expect(
      excludedToolsNotice([
        { tool_id: 'a', name: 'A', reason: 'no_permission' },
        { tool_id: 'b', name: 'B', reason: 'no_permission' },
      ]),
    ).toBe('권한이 없어 사용하지 않은 도구: A, B');
  });
  it('빈 목록은 null', () => {
    expect(excludedToolsNotice([])).toBeNull();
    expect(excludedToolsNotice(undefined)).toBeNull();
  });
});
