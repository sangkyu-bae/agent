import { useState } from 'react';
import { useSetToolBuiltin, useToolCatalog } from '@/hooks/useToolCatalog';
import type { CatalogTool } from '@/types/toolCatalog';

/** authClient가 detail을 ApiError(message, status)로 정규화한다 */
const getErrorMessage = (err: unknown, fallback: string): string =>
  err instanceof Error && err.message ? err.message : fallback;

/**
 * 관리자 도구 카탈로그 관리 — builtin-tools D9.
 * 카탈로그 목록을 표시하고 도구별 빌트인(에이전트 생성 시 자동 주입)을 토글한다.
 */
const AdminToolsPage = () => {
  const { data: tools, isLoading, isError, refetch } = useToolCatalog();
  const setBuiltinMutation = useSetToolBuiltin();
  const [error, setError] = useState<string | null>(null);
  // 행 단위 pending — 다른 행 토글은 막지 않되 같은 행 이중 클릭은 차단
  const [pendingToolId, setPendingToolId] = useState<string | null>(null);

  const handleToggle = (tool: CatalogTool) => {
    if (pendingToolId) return;
    setError(null);
    setPendingToolId(tool.tool_id);
    setBuiltinMutation.mutate(
      { toolId: tool.tool_id, isBuiltin: !tool.is_builtin },
      {
        onSettled: () => setPendingToolId(null),
        onError: (err) =>
          setError(getErrorMessage(err, '빌트인 설정 변경에 실패했습니다.')),
      },
    );
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6">
        <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
          Admin
        </p>
        <h1 className="text-3xl font-bold tracking-tight text-zinc-900">도구 관리</h1>
        <p className="mt-1 text-[13px] text-zinc-400">
          도구 카탈로그를 조회하고, 에이전트 생성 시 자동 포함되는 빌트인 도구를 지정합니다.
        </p>
      </div>

      {error && (
        <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">{error}</p>
      )}

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-[52px] animate-pulse rounded-xl border border-zinc-200 bg-zinc-100" />
          ))}
        </div>
      ) : isError ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 py-10">
          <p className="text-[13px] text-zinc-500">도구 목록을 불러올 수 없습니다</p>
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-lg bg-violet-600 px-3.5 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-violet-700 active:scale-95"
          >
            다시 시도
          </button>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-zinc-200">
          <table className="w-full text-left">
            <thead className="bg-zinc-50 text-[12px] font-semibold uppercase tracking-wide text-zinc-400">
              <tr>
                <th className="px-5 py-3">도구</th>
                <th className="px-5 py-3">소스</th>
                <th className="px-5 py-3">설명</th>
                <th className="px-5 py-3 text-center">빌트인</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 bg-white">
              {(tools ?? []).map((tool) => (
                <tr key={tool.tool_id}>
                  <td className="px-5 py-3.5">
                    <span className="text-[13.5px] font-medium text-zinc-800">{tool.name}</span>
                    {tool.is_builtin && (
                      <span className="ml-2 rounded bg-violet-100 px-1.5 py-0.5 text-[10px] font-semibold text-violet-600">기본</span>
                    )}
                  </td>
                  <td className="px-5 py-3.5">
                    {tool.source === 'mcp' ? (
                      <span className="rounded bg-sky-100 px-1.5 py-0.5 text-[10px] font-semibold text-sky-600">MCP</span>
                    ) : (
                      <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-semibold text-zinc-500">내부</span>
                    )}
                  </td>
                  <td className="max-w-md px-5 py-3.5">
                    <p className="line-clamp-2 text-[12.5px] text-zinc-500">{tool.description}</p>
                  </td>
                  <td className="px-5 py-3.5 text-center">
                    <button
                      type="button"
                      role="switch"
                      aria-checked={!!tool.is_builtin}
                      aria-label={`${tool.name} 빌트인`}
                      disabled={pendingToolId === tool.tool_id}
                      onClick={() => handleToggle(tool)}
                      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${
                        tool.is_builtin ? 'bg-violet-600' : 'bg-zinc-300'
                      }`}
                    >
                      <span
                        className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                          tool.is_builtin ? 'translate-x-[18px]' : 'translate-x-[3px]'
                        }`}
                      />
                    </button>
                  </td>
                </tr>
              ))}
              {(tools ?? []).length === 0 && (
                <tr>
                  <td colSpan={4} className="px-5 py-10 text-center text-[13px] text-zinc-400">
                    등록된 도구가 없습니다
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default AdminToolsPage;
