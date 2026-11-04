// Design Ref: tool-access-control §5 (Plan FR-14·15) — 부서·사용자 중심 도구 권한 화면.
// 판정 = 기본 세트 ∪ 소속 부서 허용 ∪ 사용자 허용. 이 화면은 대상 하나의 '직접 허용'만 편집하고,
// 상속분(기본 세트·부서)은 체크·잠금으로 보여 준다. 저장은 대상별 PUT 전체 교체.
import { useMemo, useState } from 'react';
import Tabs from '@/components/ui/Tabs';
import LoadingButton from '@/components/common/LoadingButton';
import ToolAccessChecklist from '@/components/admin/tool-access/ToolAccessChecklist';
import { useToolCatalog } from '@/hooks/useToolCatalog';
import { useMcpServers } from '@/hooks/useMcpServers';
import { useDepartments } from '@/hooks/useDepartments';
import { useAllUsers } from '@/hooks/useAdminUsers';
import {
  useDefaultToolAccess,
  useDepartmentToolAccess,
  useReplaceToolAccess,
  useUserToolAccess,
  type ToolAccessTarget,
} from '@/hooks/useToolAccess';
import type { CatalogTool } from '@/types/toolCatalog';
import { TOOL_ACCESS_TAB_LABELS, TOOL_ACCESS_TABS, type ToolAccessTab } from '@/types/toolAccess';

const getErrorMessage = (err: unknown): string =>
  err instanceof Error && err.message ? err.message : '저장에 실패했습니다.';

const sameSet = (a: Set<string>, b: Set<string>) =>
  a.size === b.size && [...a].every((x) => b.has(x));

const AdminToolAccessPage = () => {
  const [tab, setTab] = useState<ToolAccessTab>('default');
  const [deptId, setDeptId] = useState<string | null>(null);
  const [userId, setUserId] = useState<number | null>(null);
  const [userQuery, setUserQuery] = useState('');
  // 대상 키가 같을 때만 쓰는 편집본 — 대상이 바뀌거나 저장 후 비우면 서버 값으로 돌아간다.
  const [draft, setDraft] = useState<{ key: string; ids: Set<string> } | null>(null);
  const [notice, setNotice] = useState<{ tone: 'success' | 'danger'; text: string } | null>(null);

  const catalogQuery = useToolCatalog();
  const mcpQuery = useMcpServers();
  const defaultQuery = useDefaultToolAccess();
  const departmentsQuery = useDepartments();
  const usersQuery = useAllUsers({ status: 'approved', q: userQuery || undefined, limit: 100 });
  const deptQuery = useDepartmentToolAccess(tab === 'department' ? deptId : null);
  const userAccessQuery = useUserToolAccess(tab === 'user' ? userId : null);
  const replace = useReplaceToolAccess();

  const tools: CatalogTool[] = catalogQuery.data ?? [];
  const serverNames = useMemo(
    () => Object.fromEntries((mcpQuery.data?.items ?? []).map((s) => [s.id, s.name])),
    [mcpQuery.data],
  );
  const defaultIds = useMemo(() => new Set(defaultQuery.data?.tool_ids ?? []), [defaultQuery.data]);

  // ── 현재 대상의 서버 값·잠금 ───────────────────────────────────────────
  let target: ToolAccessTarget | null = null;
  let serverIds = new Set<string>();
  let locks: Record<string, string> = {};
  let isTargetAdmin = false;
  let isTargetLoading = false;

  if (tab === 'default') {
    target = { kind: 'default' };
    serverIds = defaultIds;
    isTargetLoading = defaultQuery.isLoading;
  } else if (tab === 'department' && deptId) {
    target = { kind: 'department', id: deptId };
    serverIds = new Set(deptQuery.data?.tool_ids ?? []);
    locks = Object.fromEntries((deptQuery.data?.default_tool_ids ?? []).map((t) => [t, '기본']));
    isTargetLoading = deptQuery.isLoading;
  } else if (tab === 'user' && userId !== null) {
    target = { kind: 'user', id: userId };
    const data = userAccessQuery.data;
    serverIds = new Set(data?.tool_ids ?? []);
    isTargetAdmin = !!data?.is_admin;
    locks = Object.fromEntries(
      (data?.inherited ?? []).map((i) => [
        i.tool_id,
        i.sources
          .map((s) => (s.kind === 'default' ? '기본' : `부서: ${s.department_name ?? s.department_id}`))
          .join(' · '),
      ]),
    );
    isTargetLoading = userAccessQuery.isLoading;
  }

  const targetKey = target ? `${target.kind}:${'id' in target ? target.id : ''}` : '';
  const selected = draft?.key === targetKey ? draft.ids : serverIds;
  const dirty = !!target && !sameSet(selected, serverIds);
  const editable = !!target && !isTargetLoading && !isTargetAdmin;

  const update = (next: Set<string>) => {
    setNotice(null);
    setDraft({ key: targetKey, ids: next });
  };
  const handleToggle = (toolId: string) => {
    const next = new Set(selected);
    if (next.has(toolId)) next.delete(toolId);
    else next.add(toolId);
    update(next);
  };
  const handleSetMany = (toolIds: string[], checked: boolean) => {
    const next = new Set(selected);
    toolIds.forEach((t) => (checked ? next.add(t) : next.delete(t)));
    update(next);
  };
  const handleSave = () => {
    if (!target) return;
    setNotice(null);
    replace.mutate(
      { target, toolIds: [...selected] },
      {
        onSuccess: () => {
          setDraft(null);
          setNotice({ tone: 'success', text: '저장했습니다.' });
        },
        onError: (err) => setNotice({ tone: 'danger', text: getErrorMessage(err) }),
      },
    );
  };
  const switchTab = (key: string) => {
    setTab(key as ToolAccessTab);
    setDraft(null);
    setNotice(null);
  };

  // FR-15: 기본 세트 탭에서 의도치 않은 차단을 알아보게 한다.
  const defaultTabBadges = (t: CatalogTool): string[] => {
    if (selected.has(t.tool_id)) return [];
    return t.is_builtin ? ['빌트인·비기본', '기본 세트 아님'] : ['기본 세트 아님'];
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-fg">도구 권한</h1>
        <p className="mt-1 text-sm text-fg-muted">
          부서·사용자가 쓸 수 있는 도구를 지정합니다. 사용 가능 도구 = 기본 허용 도구 + 소속 부서 허용 + 사용자 허용이며,
          어디에도 허용되지 않은 도구는 관리자 외에는 사용할 수 없습니다.
        </p>
      </div>

      <Tabs
        aria-label="도구 권한 대상"
        items={TOOL_ACCESS_TABS.map((key) => ({ key, label: TOOL_ACCESS_TAB_LABELS[key] }))}
        value={tab}
        onChange={switchTab}
        className="mb-5"
      />

      <div className="mb-4 flex flex-wrap items-end gap-3">
        {tab === 'department' && (
          <label className="flex flex-col gap-1 text-xs font-medium text-fg-subtle">
            부서
            <select
              aria-label="부서"
              value={deptId ?? ''}
              onChange={(e) => {
                setDeptId(e.target.value || null);
                setNotice(null);
              }}
              className="min-w-56 rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg"
            >
              <option value="">부서를 선택하세요</option>
              {(departmentsQuery.data?.departments ?? []).map((d) => (
                <option key={d.id} value={d.id}>{d.name}</option>
              ))}
            </select>
          </label>
        )}
        {tab === 'user' && (
          <>
            <label className="flex flex-col gap-1 text-xs font-medium text-fg-subtle">
              사용자 검색
              <input
                type="search"
                value={userQuery}
                onChange={(e) => setUserQuery(e.target.value)}
                placeholder="이메일 일부"
                className="min-w-48 rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-fg-subtle">
              사용자
              <select
                aria-label="사용자"
                value={userId ?? ''}
                onChange={(e) => {
                  setUserId(e.target.value ? Number(e.target.value) : null);
                  setNotice(null);
                }}
                className="min-w-64 rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg"
              >
                <option value="">사용자를 선택하세요</option>
                {(usersQuery.data?.items ?? []).map((u) => (
                  <option key={u.id} value={u.id}>
                    {(u.display_name ?? u.email) + (u.department_names.length ? ` (${u.department_names.join(', ')})` : '')}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        <LoadingButton
          type="button"
          isPending={replace.isPending}
          pendingText="저장 중…"
          disabled={!editable || !dirty}
          onClick={handleSave}
          className="ml-auto rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors duration-150 hover:bg-brand-700 disabled:opacity-50"
        >
          저장
        </LoadingButton>
      </div>

      {notice && (
        <p
          role={notice.tone === 'danger' ? 'alert' : 'status'}
          className={`mb-4 rounded-md border px-3 py-2 text-sm ${
            notice.tone === 'danger'
              ? 'border-danger-border bg-danger-bg text-danger'
              : 'border-success-border bg-success-bg text-success'
          }`}
        >
          {notice.text}
        </p>
      )}

      {isTargetAdmin && (
        <p role="status" className="mb-4 rounded-md border border-info-border bg-info-bg px-3 py-2 text-sm text-info">
          관리자는 모든 도구를 사용할 수 있습니다.
        </p>
      )}

      {catalogQuery.isError ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-border bg-surface-muted py-10">
          <p className="text-sm text-fg-muted">도구 목록을 불러올 수 없습니다</p>
          <button
            type="button"
            onClick={() => catalogQuery.refetch()}
            className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
          >
            다시 시도
          </button>
        </div>
      ) : catalogQuery.isLoading || isTargetLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded-xl border border-border bg-surface-sunken" />
          ))}
        </div>
      ) : !target ? (
        <p className="rounded-xl border border-border bg-surface-muted py-10 text-center text-sm text-fg-subtle">
          {tab === 'department' ? '부서를 선택하세요.' : '사용자를 선택하세요.'}
        </p>
      ) : (
        <ToolAccessChecklist
          tools={tools}
          serverNames={serverNames}
          selected={selected}
          locks={locks}
          onToggle={handleToggle}
          onSetMany={handleSetMany}
          extraBadges={tab === 'default' ? defaultTabBadges : undefined}
          disabled={!editable}
        />
      )}
    </div>
  );
};

export default AdminToolAccessPage;
