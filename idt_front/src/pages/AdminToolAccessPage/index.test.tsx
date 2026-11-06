import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, beforeEach, describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import AdminToolAccessPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const SRV = '7f3c0000-0000-0000-0000-000000000001';
const DOC = 'internal:internal_document_search';
const PY = 'internal:python_code_executor';
const TICKET = `mcp:${SRV}:write_ticket`;

const base = {
  description: '', requires_env: [], category: null, max_tool_calls: null,
  mcp_server_name: null, requires_approval: false,
};
const CATALOG = {
  tools: [
    { ...base, tool_id: DOC, source: 'internal', name: '내부 문서 검색', mcp_server_id: null, is_builtin: true },
    { ...base, tool_id: PY, source: 'internal', name: 'Python 코드 실행', mcp_server_id: null, is_builtin: true },
    { ...base, tool_id: TICKET, source: 'mcp', name: 'write_ticket', mcp_server_id: SRV, is_builtin: false },
  ],
};

let puts: { url: string; body: unknown }[] = [];

beforeEach(() => {
  puts = [];
  server.use(
    http.get('*/api/v1/tool-catalog', () => HttpResponse.json(CATALOG)),
    http.get('*/api/v1/mcp-registry', () =>
      HttpResponse.json({ items: [{ id: SRV, name: '사내 티켓 시스템' }], total: 1 }),
    ),
    http.get('*/api/v1/admin/tool-access/default', () => HttpResponse.json({ tool_ids: [DOC] })),
    http.get('*/api/v1/departments', () =>
      HttpResponse.json({ departments: [{ id: 'd-loan', name: '여신부', description: null, created_at: '', updated_at: '' }] }),
    ),
    http.get('*/api/v1/admin/tool-access/departments/d-loan', () =>
      HttpResponse.json({ department_id: 'd-loan', department_name: '여신부', tool_ids: [TICKET], default_tool_ids: [DOC] }),
    ),
    http.get('*/api/v1/admin/users', () =>
      HttpResponse.json({
        items: [
          { id: 12, email: 'kim@corp.com', role: 'user', status: 'approved', display_name: '김행원', position: null, department_names: ['여신부'], created_at: null },
          { id: 1, email: 'admin@corp.com', role: 'admin', status: 'approved', display_name: '관리자', position: null, department_names: [], created_at: null },
        ],
        total: 2,
      }),
    ),
    http.get('*/api/v1/admin/tool-access/users/12', () =>
      HttpResponse.json({
        user_id: 12, is_admin: false, tool_ids: [PY],
        inherited: [
          { tool_id: DOC, sources: [{ kind: 'default' }] },
          { tool_id: TICKET, sources: [{ kind: 'department', department_id: 'd-loan', department_name: '여신부' }] },
        ],
      }),
    ),
    http.get('*/api/v1/admin/tool-access/users/1', () =>
      HttpResponse.json({ user_id: 1, is_admin: true, tool_ids: [], inherited: [] }),
    ),
    http.put('*/api/v1/admin/tool-access/*', async ({ request }) => {
      const body = (await request.json()) as { tool_ids: string[] };
      puts.push({ url: new URL(request.url).pathname, body });
      return HttpResponse.json({ tool_ids: body.tool_ids, department_id: 'd-loan', department_name: '여신부', default_tool_ids: [DOC], user_id: 12, is_admin: false, inherited: [] });
    }),
  );
});

const renderPage = () => render(<AdminToolAccessPage />, { wrapper: createWrapper() });

describe('AdminToolAccessPage', () => {
  it('탭 3개를 보이고 기본 세트 탭이 먼저 열린다', async () => {
    renderPage();
    const tabs = screen.getAllByRole('tab').map((t) => t.textContent);
    expect(tabs).toEqual(['기본 허용 도구', '부서별', '사용자별']);
    expect(await screen.findByRole('checkbox', { name: /내부 문서 검색/ })).toBeChecked();
  });

  it('기본 세트: 저장 버튼은 변경이 있을 때만 활성, 저장은 전체 목록 PUT', async () => {
    renderPage();
    const save = await screen.findByRole('button', { name: '저장' });
    await screen.findByRole('checkbox', { name: /Python 코드 실행/ });
    expect(save).toBeDisabled();
    await userEvent.click(screen.getByRole('checkbox', { name: /Python 코드 실행/ }));
    expect(save).toBeEnabled();
    await userEvent.click(save);
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0].url).toBe('/api/v1/admin/tool-access/default');
    expect((puts[0].body as { tool_ids: string[] }).tool_ids.sort()).toEqual([DOC, PY].sort());
    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
  });

  it('기본 세트: 빌트인인데 기본 세트가 아니면 경고 배지', async () => {
    renderPage();
    const row = (await screen.findByRole('checkbox', { name: /Python 코드 실행/ })).closest('li') as HTMLElement;
    expect(within(row).getByText('빌트인·비기본')).toBeInTheDocument();
    expect(within(row).getByText('기본 세트 아님')).toBeInTheDocument();
  });

  it('MCP 도구는 서버 이름 그룹으로 묶인다', async () => {
    renderPage();
    expect(await screen.findByRole('group', { name: 'MCP: 사내 티켓 시스템' })).toBeInTheDocument();
  });

  it('부서별: 기본 세트는 잠금, 부서 허용은 체크, 저장은 부서 경로', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('tab', { name: '부서별' }));
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: '부서' }), 'd-loan');
    const doc = await screen.findByRole('checkbox', { name: /내부 문서 검색/ });
    expect(doc).toBeChecked();
    expect(doc).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: /write_ticket/ })).toBeChecked();
    await userEvent.click(screen.getByRole('checkbox', { name: /Python 코드 실행/ }));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0].url).toBe('/api/v1/admin/tool-access/departments/d-loan');
    expect((puts[0].body as { tool_ids: string[] }).tool_ids.sort()).toEqual([PY, TICKET].sort());
  });

  it('사용자별: 부서 상속은 "부서: 이름" 잠금, 직접 허용만 PUT 에 담는다', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('tab', { name: '사용자별' }));
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: '사용자' }), '12');
    const ticket = await screen.findByRole('checkbox', { name: /write_ticket/ });
    expect(ticket).toBeDisabled();
    expect(screen.getByText('부서: 여신부')).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /Python 코드 실행/ })).toBeChecked();
    await userEvent.click(screen.getByRole('checkbox', { name: /Python 코드 실행/ }));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0].url).toBe('/api/v1/admin/tool-access/users/12');
    expect(puts[0].body).toEqual({ tool_ids: [] });
  });

  it('사용자별: 관리자 대상이면 안내 배너 + 편집 불가', async () => {
    renderPage();
    await userEvent.click(screen.getByRole('tab', { name: '사용자별' }));
    await userEvent.selectOptions(await screen.findByRole('combobox', { name: '사용자' }), '1');
    expect(await screen.findByText('관리자는 모든 도구를 사용할 수 있습니다.')).toBeInTheDocument();
    screen.getAllByRole('checkbox').forEach((c) => expect(c).toBeDisabled());
    expect(screen.getByRole('button', { name: '저장' })).toBeDisabled();
  });

  it('저장 실패 시 서버 메시지를 보인다', async () => {
    server.use(
      http.put('*/api/v1/admin/tool-access/default', () =>
        HttpResponse.json(
          { detail: { code: 'UNKNOWN_TOOL_IDS', message: '카탈로그에 없는 도구가 포함되어 있습니다', tool_ids: ['x'] } },
          { status: 400 },
        ),
      ),
    );
    renderPage();
    await userEvent.click(await screen.findByRole('checkbox', { name: /Python 코드 실행/ }));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('카탈로그에 없는 도구가 포함되어 있습니다')).toBeInTheDocument();
  });
});
