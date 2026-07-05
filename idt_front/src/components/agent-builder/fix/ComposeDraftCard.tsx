import { useState } from 'react';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';

interface ComposeDraftCardProps {
  draft: ComposeAgentDraftResponse;
  mode: 'create' | 'edit';
  /** FR-10: edit 모드 도구 변경 감지용 현재 폼 도구 목록 */
  currentToolIds: string[];
  applied: boolean;
  /** FR-05: llm_model_id가 등록 모델에 없으면 모델 미변경 안내 */
  modelUnresolved: boolean;
  onApply: () => void;
}

const COVERAGE_BADGE: Record<
  ComposeAgentDraftResponse['coverage'],
  { label: string; className: string }
> = {
  full: { label: 'full', className: 'bg-emerald-100 text-emerald-700' },
  partial: { label: 'partial', className: 'bg-amber-100 text-amber-700' },
  none: { label: 'none', className: 'bg-red-100 text-red-600' },
};

/**
 * Fix 채팅의 초안 카드 — compose 응답을 요약 표시하고
 * [적용하기] 클릭 시에만 좌측 폼에 반영한다 (fix-agent-composer FR-04/07/10).
 */
const ComposeDraftCard = ({
  draft,
  mode,
  currentToolIds,
  applied,
  modelUnresolved,
  onApply,
}: ComposeDraftCardProps) => {
  const [promptExpanded, setPromptExpanded] = useState(false);
  const [instructionsExpanded, setInstructionsExpanded] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  // compose-tool-instructions FR-07: 지침이 있는 워커만 표시 대상
  const workersWithInstruction = draft.workers.filter((w) => w.instruction);

  const badge = COVERAGE_BADGE[draft.coverage];
  const isNone = draft.coverage === 'none';
  const toolsChanged =
    mode === 'edit' &&
    (draft.tool_ids.length !== currentToolIds.length ||
      draft.tool_ids.some((id) => !currentToolIds.includes(id)));

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm">
      {/* 헤더 */}
      <div className="flex items-center justify-between gap-2">
        <p className="text-[14px] font-semibold text-zinc-900">
          {draft.name_suggestion || '이름 미정'}
        </p>
        <span
          className={`shrink-0 rounded-full px-2 py-0.5 text-[10.5px] font-semibold ${badge.className}`}
        >
          {badge.label}
        </span>
      </div>

      {isNone ? (
        <p className="mt-2 text-[13px] text-zinc-500">
          현재 등록된 도구로는 요청을 수행할 수 없습니다.
        </p>
      ) : (
        <>
          {/* 도구 칩 */}
          <div className="mt-3 flex flex-wrap gap-1.5">
            {draft.tool_ids.map((id) => (
              <span
                key={id}
                className="flex items-center gap-1 rounded-lg border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-[11.5px] text-zinc-600"
              >
                {id}
                {id.startsWith('mcp_') && (
                  <span className="rounded bg-sky-100 px-1 py-px text-[9.5px] font-semibold text-sky-600">
                    MCP
                  </span>
                )}
              </span>
            ))}
          </div>

          {/* 실행 흐름 */}
          {draft.flow_hint && (
            <p className="mt-2 text-[12px] text-zinc-400">{draft.flow_hint}</p>
          )}

          {/* 도구별 지침 (compose-tool-instructions FR-07) */}
          {workersWithInstruction.length > 0 && (
            <div className="mt-3 rounded-xl border border-zinc-100 bg-white px-3 py-2">
              <button
                type="button"
                onClick={() => setInstructionsExpanded((v) => !v)}
                className="text-[11.5px] font-medium text-violet-500 hover:text-violet-600"
              >
                도구별 지침 {instructionsExpanded ? '접기' : `보기 (${workersWithInstruction.length})`}
              </button>
              {instructionsExpanded && (
                <ul className="mt-2 space-y-2">
                  {workersWithInstruction.map((w) => (
                    <li key={w.worker_id}>
                      <p className="text-[11.5px] font-semibold text-zinc-700">
                        {w.tool_id}
                      </p>
                      <p className="whitespace-pre-wrap text-[12px] leading-[1.6] text-zinc-500">
                        {w.instruction}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* 시스템 프롬프트 */}
          {draft.system_prompt && (
            <div className="mt-3 rounded-xl bg-zinc-50 px-3 py-2">
              <p
                className={`whitespace-pre-wrap text-[12.5px] leading-[1.6] text-zinc-600 ${
                  promptExpanded ? '' : 'line-clamp-3'
                }`}
              >
                {draft.system_prompt}
              </p>
              <button
                type="button"
                onClick={() => setPromptExpanded((v) => !v)}
                className="mt-1 text-[11.5px] font-medium text-violet-500 hover:text-violet-600"
              >
                {promptExpanded ? '접기' : '더보기'}
              </button>
            </div>
          )}
        </>
      )}

      {/* 미커버 역량 */}
      {draft.missing_capabilities.length > 0 && (
        <div className="mt-3 rounded-xl bg-amber-50 px-3 py-2">
          {draft.missing_capabilities.map((m) => (
            <p key={m.capability} className="text-[12px] leading-[1.6] text-amber-700">
              ⚠ {m.capability} — {m.reason}
              {m.suggestion && ` (${m.suggestion})`}
            </p>
          ))}
        </div>
      )}

      {/* 노트 */}
      {draft.notes && (
        <p className="mt-2 text-[11px] leading-[1.6] text-zinc-400">{draft.notes}</p>
      )}

      {/* edit 모드 도구 변경 제약 (FR-10) */}
      {!isNone && toolsChanged && (
        <p className="mt-2 text-[11.5px] font-medium text-amber-600">
          도구 변경은 수정 화면에서 저장되지 않습니다.
        </p>
      )}

      {/* 모델 미매핑 안내 (FR-05) */}
      {!isNone && modelUnresolved && (
        <p className="mt-1 text-[11.5px] text-zinc-400">
          모델 {draft.llm_model_id}은(는) 등록 목록에 없어 현재 모델이 유지됩니다.
        </p>
      )}

      {/* 액션 */}
      {!isNone &&
        (applied ? (
          <p className="mt-3 text-[12.5px] font-semibold text-emerald-600">✓ 적용됨</p>
        ) : (
          !dismissed && (
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={onApply}
                className="rounded-xl bg-violet-600 px-4 py-2 text-[12.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
              >
                적용하기
              </button>
              <button
                type="button"
                onClick={() => setDismissed(true)}
                className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2 text-[12.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
              >
                무시
              </button>
            </div>
          )
        ))}
    </div>
  );
};

export default ComposeDraftCard;
