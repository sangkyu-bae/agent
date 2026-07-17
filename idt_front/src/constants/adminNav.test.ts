import { describe, it, expect } from 'vitest';
import { ADMIN_NAV_ITEMS, ADMIN_ENTRY_PATH } from './adminNav';

describe('adminNav 상수', () => {
  it('N1: 관리자 메뉴는 8개다', () => {
    expect(ADMIN_NAV_ITEMS).toHaveLength(8);
  });

  it('N1-2: MCP 서버 메뉴가 포함된다', () => {
    const paths = ADMIN_NAV_ITEMS.map((item) => item.path);
    expect(paths).toContain('/admin/mcp-servers');
  });

  it('N1-4: LLM 모델 메뉴가 포함된다', () => {
    const paths = ADMIN_NAV_ITEMS.map((item) => item.path);
    expect(paths).toContain('/admin/llm-models');
  });

  it('N1-5: 청킹 프로파일 메뉴가 포함된다', () => {
    const paths = ADMIN_NAV_ITEMS.map((item) => item.path);
    expect(paths).toContain('/admin/chunking-profiles');
  });

  it('N1-3: Skill 관리 메뉴가 포함된다', () => {
    const paths = ADMIN_NAV_ITEMS.map((item) => item.path);
    expect(paths).toContain('/admin/skills');
  });

  it('N2: path는 중복되지 않는다', () => {
    const paths = ADMIN_NAV_ITEMS.map((item) => item.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('N3: ADMIN_ENTRY_PATH는 메뉴 항목에 포함된다', () => {
    const paths = ADMIN_NAV_ITEMS.map((item) => item.path);
    expect(paths).toContain(ADMIN_ENTRY_PATH);
  });

  it('모든 항목은 label/path/icon/description을 갖는다', () => {
    for (const item of ADMIN_NAV_ITEMS) {
      expect(item.label).toBeTruthy();
      expect(item.path).toMatch(/^\/admin\//);
      expect(item.icon).toBeTruthy();
      expect(item.description).toBeTruthy();
    }
  });
});
