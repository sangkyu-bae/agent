// approval-gate-run-termination Design §5.1 — 도구별 본문 인자(draft_arg_key) 저장·복원
// form.toolConfigs(RAG 설정)와 분리해 보관하고 저장 시에만 tool_configs 로 합친다.
// 서버는 tool_configs[tool_id].draft_arg_key 를 워커 tool_config 로 저장한다(기존 계약).
import type { ToolConfigPayload } from '@/types/agentBuilder';
import type { RagToolConfig } from '@/types/ragToolConfig';

/**
 * 저장 요청의 tool_configs. 보낼 것이 없으면 undefined — 서버가 기존 설정을 승계한다.
 * 빈 본문 인자는 null 로 보내 서버 저장값을 지운다.
 */
export const buildToolConfigsForSave = (
  toolConfigs: Record<string, RagToolConfig>,
  draftArgKeys: Record<string, string>,
): Record<string, ToolConfigPayload> | undefined => {
  const merged: Record<string, ToolConfigPayload> = { ...toolConfigs };
  for (const [toolId, raw] of Object.entries(draftArgKeys)) {
    merged[toolId] = { draft_arg_key: raw.trim() || null };
  }
  return Object.keys(merged).length > 0 ? merged : undefined;
};

interface WorkerLike {
  tool_id: string;
  tool_config?: Record<string, unknown> | null;
}

/** 수정 모드 프리필 — 저장된 워커의 본문 인자를 복원한다. */
export const draftArgKeysFromWorkers = (
  workers: WorkerLike[],
): Record<string, string> =>
  Object.fromEntries(
    workers
      .map((w) => [w.tool_id, w.tool_config?.draft_arg_key] as const)
      .filter((pair): pair is readonly [string, string] =>
        typeof pair[1] === 'string' && pair[1].trim() !== '',
      ),
  );
