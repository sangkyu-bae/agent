// Design Ref: tool-access-control §5.1·§5.4 — 내부 도구 / MCP 서버별 그룹 체크리스트.
// 잠금(기본 세트·부서 상속) 항목은 체크된 채 편집 불가, 사유를 배지로 보인다(색만으로 의미 전달 금지).
import Badge from '@/components/ui/Badge';
import type { CatalogTool } from '@/types/toolCatalog';

interface ToolAccessChecklistProps {
  tools: CatalogTool[];
  /** mcp_server_id → 서버 이름 (카탈로그 응답에는 서버 이름이 없다) */
  serverNames: Record<string, string>;
  /** 이 대상에 직접 허용된 도구 (편집 대상) */
  selected: Set<string>;
  /** tool_id → 잠금 사유 라벨. 잠금 항목은 체크·비활성 */
  locks: Record<string, string>;
  onToggle: (toolId: string) => void;
  onSetMany: (toolIds: string[], checked: boolean) => void;
  extraBadges?: (tool: CatalogTool) => string[];
  disabled?: boolean;
}

interface ToolGroup {
  key: string;
  label: string;
  tools: CatalogTool[];
  bulk: boolean;
}

const groupTools = (tools: CatalogTool[], serverNames: Record<string, string>): ToolGroup[] => {
  const internal = tools.filter((t) => t.source !== 'mcp');
  const byServer = new Map<string, CatalogTool[]>();
  for (const t of tools) {
    if (t.source !== 'mcp') continue;
    const key = t.mcp_server_id ?? 'unknown';
    byServer.set(key, [...(byServer.get(key) ?? []), t]);
  }
  const groups: ToolGroup[] = [];
  if (internal.length) groups.push({ key: 'internal', label: '내부 도구', tools: internal, bulk: false });
  for (const [serverId, list] of byServer) {
    groups.push({
      key: serverId,
      label: `MCP: ${serverNames[serverId] ?? serverId.slice(0, 8)}`,
      tools: list,
      bulk: true,
    });
  }
  return groups;
};

const ToolAccessChecklist = ({
  tools,
  serverNames,
  selected,
  locks,
  onToggle,
  onSetMany,
  extraBadges,
  disabled = false,
}: ToolAccessChecklistProps) => {
  const groups = groupTools(tools, serverNames);

  return (
    <div className="flex flex-col gap-4">
      {groups.map((group) => {
        const editable = group.tools.filter((t) => !locks[t.tool_id]).map((t) => t.tool_id);
        const headingId = `tool-access-group-${group.key}`;
        return (
          <section
            key={group.key}
            role="group"
            aria-labelledby={headingId}
            className="rounded-xl border border-border bg-surface shadow-sm"
          >
            <header className="flex items-center gap-2 border-b border-border px-4 py-2.5">
              <h3 id={headingId} className="text-sm font-semibold text-fg">
                {group.label}
              </h3>
              <span className="text-xs text-fg-subtle">{group.tools.length}개</span>
              {group.bulk && (
                <div className="ml-auto flex gap-1">
                  <button
                    type="button"
                    disabled={disabled || editable.length === 0}
                    onClick={() => onSetMany(editable, true)}
                    className="rounded-md px-2 py-1 text-xs font-medium text-brand-700 transition-colors duration-150 hover:bg-brand-50 disabled:opacity-50"
                  >
                    전체 선택
                  </button>
                  <button
                    type="button"
                    disabled={disabled || editable.length === 0}
                    onClick={() => onSetMany(editable, false)}
                    className="rounded-md px-2 py-1 text-xs font-medium text-fg-muted transition-colors duration-150 hover:bg-surface-sunken disabled:opacity-50"
                  >
                    전체 해제
                  </button>
                </div>
              )}
            </header>
            <ul className="divide-y divide-border">
              {group.tools.map((t) => {
                const lock = locks[t.tool_id];
                const checked = !!lock || selected.has(t.tool_id);
                const inputId = `tool-access-${t.tool_id}`;
                return (
                  <li key={t.tool_id} className="flex items-center gap-3 px-4 py-2.5">
                    <input
                      id={inputId}
                      type="checkbox"
                      checked={checked}
                      disabled={disabled || !!lock}
                      onChange={() => onToggle(t.tool_id)}
                      className="h-4 w-4 accent-brand-600 disabled:opacity-60"
                    />
                    <label htmlFor={inputId} className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-fg">{t.name}</span>
                      {t.description && (
                        <span className="block truncate text-xs text-fg-subtle">{t.description}</span>
                      )}
                    </label>
                    <div className="flex shrink-0 flex-wrap justify-end gap-1">
                      {lock && <Badge tone="brand">{lock}</Badge>}
                      {t.requires_approval && <Badge tone="warning">승인 필요</Badge>}
                      {(extraBadges?.(t) ?? []).map((b) => (
                        <Badge key={b} tone="neutral">{b}</Badge>
                      ))}
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
};

export default ToolAccessChecklist;
