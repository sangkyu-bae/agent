import { describe, it, expect } from 'vitest';
import {
  ADMIN_NAV_GROUPS,
  ADMIN_NAV_ITEMS,
  ADMIN_ENTRY_PATH,
  findAdminGroupByPath,
  isAdminItemActive,
} from './adminNav';

describe('adminNav 상수 — 그룹 구조', () => {
  it('G1: 그룹은 4개다 (관측/조직/문서·품질/에이전트 리소스)', () => {
    expect(ADMIN_NAV_GROUPS.map((g) => g.key)).toEqual([
      'observability',
      'org',
      'docs-quality',
      'agent-resources',
    ]);
  });

  it('G2: ADMIN_NAV_ITEMS는 그룹 flatten과 동일하다', () => {
    expect(ADMIN_NAV_ITEMS).toEqual(ADMIN_NAV_GROUPS.flatMap((g) => g.items));
  });

  it('G3: path는 중복되지 않고 전부 /admin/으로 시작한다', () => {
    const paths = ADMIN_NAV_ITEMS.map((item) => item.path);
    expect(new Set(paths).size).toBe(paths.length);
    for (const path of paths) {
      expect(path).toMatch(/^\/admin\//);
    }
  });

  it('G4: 기존 12개 페이지 path가 전부 포함된다', () => {
    const paths = ADMIN_NAV_ITEMS.map((item) => item.path);
    const expected = [
      '/admin/dashboard',
      '/admin/users',
      '/admin/departments',
      '/admin/ragas',
      '/admin/agent-runs',
      '/admin/llm-models',
      '/admin/chunking-profiles',
      '/admin/mcp-servers',
      '/admin/tools',
      // builtin-middleware D10: 미들웨어 관리
      '/admin/middleware',
      '/admin/skills',
      '/admin/wiki',
    ];
    for (const path of expected) {
      expect(paths).toContain(path);
    }
    expect(paths).toHaveLength(expected.length);
  });

  it('G5: ADMIN_ENTRY_PATH는 /admin/dashboard이며 메뉴 항목에 포함된다', () => {
    expect(ADMIN_ENTRY_PATH).toBe('/admin/dashboard');
    expect(ADMIN_NAV_ITEMS.map((item) => item.path)).toContain(ADMIN_ENTRY_PATH);
  });

  it('G6: findAdminGroupByPath는 하위 상세 경로도 소속 그룹을 찾는다', () => {
    expect(findAdminGroupByPath('/admin/agent-runs/run-1')?.key).toBe('observability');
    expect(findAdminGroupByPath('/admin/users')?.key).toBe('org');
    expect(findAdminGroupByPath('/admin/ragas')?.key).toBe('docs-quality');
    expect(findAdminGroupByPath('/admin/wiki')?.key).toBe('agent-resources');
  });

  it('G7: admin 외 경로는 undefined를 반환한다', () => {
    expect(findAdminGroupByPath('/chatpage')).toBeUndefined();
    expect(findAdminGroupByPath('/')).toBeUndefined();
  });

  it('G8: isAdminItemActive는 exact/하위 경로만 활성으로 본다', () => {
    const item = ADMIN_NAV_ITEMS.find((i) => i.path === '/admin/tools')!;
    expect(isAdminItemActive(item, '/admin/tools')).toBe(true);
    expect(isAdminItemActive(item, '/admin/tools/detail')).toBe(true);
    expect(isAdminItemActive(item, '/admin/tools-x')).toBe(false);
    expect(isAdminItemActive(item, '/admin/skills')).toBe(false);
  });

  it('모든 그룹/항목은 필수 필드를 갖는다', () => {
    for (const group of ADMIN_NAV_GROUPS) {
      expect(group.label).toBeTruthy();
      expect(group.icon).toBeTruthy();
      expect(group.items.length).toBeGreaterThan(0);
      for (const item of group.items) {
        expect(item.label).toBeTruthy();
        expect(item.icon).toBeTruthy();
        expect(item.description).toBeTruthy();
      }
    }
  });
});
