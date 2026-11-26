// stock-analysis-agents §9.4 설정 — 역할 매핑 11행(역할·에이전트·빌더로 이동) + "기본 에이전트 만들기".
// 지침·모델·도구는 빌더에서 바꾼다(D3) — 여기서는 어떤 에이전트를 쓰는지만 정한다.
import { useState } from 'react';
import { Link } from 'react-router-dom';
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import { useBootstrapAgents, useRoleAgents, useSaveRoleAgents } from '@/hooks/useMarketAnalysis';
import type { RoleAgentRow } from '@/types/marketAnalysis';
import { marketAnalysisErrorMessage } from '@/utils/marketAnalysis';
import { Card, ErrorBox, Loading, Table, Td, Th } from './parts';

interface RoleAgentTableProps {
  canManage: boolean;
}

const BOOTSTRAP_LABELS = { created: '새로 만듦', kept: '그대로', failed: '실패' } as const;

const RoleAgentForm = ({
  rows,
  canManage,
  save,
  bootstrap,
}: {
  rows: RoleAgentRow[];
  canManage: boolean;
  /** 부모가 들고 있는 mutation — 매핑이 바뀌어 표가 새로 그려져도 결과가 남는다 */
  save: ReturnType<typeof useSaveRoleAgents>;
  bootstrap: ReturnType<typeof useBootstrapAgents>;
}) => {
  const [draft, setDraft] = useState<Record<string, string>>(() =>
    Object.fromEntries(rows.map((r) => [r.role, r.agent_id ?? ''])),
  );

  const changed = Object.fromEntries(
    rows
      .filter((r) => (draft[r.role] ?? '').trim() && (draft[r.role] ?? '').trim() !== (r.agent_id ?? ''))
      .map((r) => [r.role, draft[r.role].trim()]),
  );
  const missing = rows.filter((r) => !r.agent_id).length;
  const errorRoles = new Set(
    save.isError && save.error && typeof save.error === 'object' && 'detail' in save.error
      ? (((save.error as { detail?: { roles?: string[] } }).detail?.roles) ?? [])
      : [],
  );

  return (
    <Card
      title="역할별 에이전트"
      actions={
        canManage && (
          <Button
            size="sm"
            variant="secondary"
            isPending={bootstrap.isPending}
            pendingText="만드는 중…"
            onClick={() => bootstrap.mutate()}
          >
            기본 에이전트 만들기
          </Button>
        )
      }
    >
      <p className="mb-3 text-xs text-fg-subtle">
        에이전트가 지정되지 않은 역할에만 기본 에이전트를 만들어 연결합니다. 매수·매도 판단 역할이
        비어 있으면 회차가 실패합니다.{missing > 0 && ` 지금 ${missing}개 역할이 비어 있습니다.`}
      </p>
      {bootstrap.isError && (
        <p role="alert" className="mb-2 text-sm text-danger">
          {marketAnalysisErrorMessage(bootstrap.error, '기본 에이전트를 만들지 못했습니다.')}
        </p>
      )}
      {bootstrap.isSuccess && (
        <ul role="status" className="mb-3 flex flex-wrap gap-1 text-xs">
          {bootstrap.data.items.map((i) => (
            <li key={i.role}>
              <Badge tone={i.status === 'failed' ? 'danger' : i.status === 'created' ? 'success' : 'neutral'}>
                {rows.find((r) => r.role === i.role)?.name ?? i.role}: {BOOTSTRAP_LABELS[i.status]}
              </Badge>
            </li>
          ))}
        </ul>
      )}
      <Table label="역할별 에이전트">
        <thead>
          <tr>
            <Th>역할</Th>
            <Th>에이전트 ID</Th>
            <Th>빌더</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.role}>
              <Td>
                {r.name}
                {!r.agent_id && (
                  <Badge tone="warning" className="ml-2">
                    미지정
                  </Badge>
                )}
              </Td>
              <Td>
                <input
                  aria-label={`${r.name} 에이전트 ID`}
                  value={draft[r.role] ?? ''}
                  disabled={!canManage}
                  onChange={(e) => setDraft((d) => ({ ...d, [r.role]: e.target.value }))}
                  className="h-8 w-72 rounded-md border border-border bg-surface px-2 text-sm text-fg disabled:bg-surface-muted"
                />
                {errorRoles.has(r.role) && (
                  <p className="mt-1 text-xs text-danger">에이전트가 없거나 삭제되었습니다.</p>
                )}
              </Td>
              <Td>
                {r.agent_id ? (
                  <Link
                    to={`/agent-builder?edit=${encodeURIComponent(r.agent_id)}&returnTo=${encodeURIComponent('/market-analysis')}`}
                    className="text-sm text-brand-600 hover:text-brand-700"
                  >
                    지침 편집
                  </Link>
                ) : (
                  '-'
                )}
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {canManage && (
        <div className="mt-3 flex items-center justify-end gap-3">
          {save.isError && errorRoles.size === 0 && (
            <p role="alert" className="text-sm text-danger">
              {marketAnalysisErrorMessage(save.error, '매핑을 저장하지 못했습니다.')}
            </p>
          )}
          {save.isSuccess && <p role="status" className="text-sm text-success">저장했습니다.</p>}
          <Button
            size="sm"
            disabled={Object.keys(changed).length === 0}
            isPending={save.isPending}
            onClick={() => save.mutate(changed)}
          >
            매핑 저장
          </Button>
        </div>
      )}
    </Card>
  );
};

const RoleAgentTable = ({ canManage }: RoleAgentTableProps) => {
  const query = useRoleAgents();
  const save = useSaveRoleAgents();
  const bootstrap = useBootstrapAgents();
  if (query.isLoading) return <Loading />;
  if (query.isError) return <ErrorBox error={query.error} fallback="역할 매핑을 불러오지 못했습니다." />;
  if (!query.data) return null;
  // 서버 값이 바뀌면(부트스트랩·저장) 입력을 새 값으로 다시 시작한다
  return (
    <RoleAgentForm
      key={query.data.roles.map((r) => `${r.role}:${r.agent_id ?? ''}`).join('|')}
      rows={query.data.roles}
      canManage={canManage}
      save={save}
      bootstrap={bootstrap}
    />
  );
};

export default RoleAgentTable;
