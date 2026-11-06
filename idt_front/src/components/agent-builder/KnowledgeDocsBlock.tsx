// Design Ref: agent-kb-quick-setup §5.1/§5.4 — 도구함 "지식 문서" 블록.
// 파일 드롭 한 번으로 KB·전용 컬렉션·RAG 도구가 구성된다. 스튜디오와 위저드가 공유한다.
// 간단 모드에는 컬렉션·벡터·청킹·검색 모드 용어를 쓰지 않는다 (Plan NFR 문구).
// Check G1: 전부 실패 후 [다시 시도]는 이미 만들어진 KB 에 파일만 다시 올린다 — /quick 을 또 불러
// 빈 KB 가 누적되지 않게 한다. Check G2: 고아 안내는 KB 가 생긴 뒤에도 두 화면 모두에서 보인다.
import { useId, useState } from 'react';
import Dropdown from '@/components/common/Dropdown';
import ProgressCard from '@/components/common/ProgressCard';
import { useKbDefaults } from '@/hooks/useKbDefaults';
import { useKnowledgeBases } from '@/hooks/useKnowledgeBases';
import { useQuickKnowledgeBase, useRetryKbUpload } from '@/hooks/useQuickKnowledgeBase';
import { ApiError } from '@/services/api/ApiError';
import { SCOPE_LABELS } from '@/types/collection';
import {
  KB_DEFAULTS_NOT_CONFIGURED_CODE,
  KB_DEFAULTS_NOT_CONFIGURED_MESSAGE,
  KB_QUICK_ACCEPT,
  KB_QUICK_DOC_STATUS,
  KB_QUICK_MAX_FILES,
  type QuickKbResponse,
} from '@/types/kbQuickSetup';
import {
  kbNameForAgent,
  quickKbProgressSteps,
  scopeForVisibility,
  type AgentVisibility,
  type QuickKbPhase,
} from '@/utils/kbQuickSetup';

export interface KnowledgeDocsBlockProps {
  agentName: string;
  visibility: AgentVisibility;
  departmentId?: string | null;
  /** 현재 폼에 연결된 KB (toolConfigs[RAG].kb_id) */
  attachedKbId?: string;
  mode: 'studio' | 'wizard';
  /** 프롬프트 단계 진입 후 읽기 전용 (위저드) */
  locked?: boolean;
  onAttached: (kbId: string, result: QuickKbResponse | null) => void;
  onDetach: () => void;
}

const errorMessage = (err: unknown): string => {
  if (err instanceof ApiError && err.code === KB_DEFAULTS_NOT_CONFIGURED_CODE) {
    return KB_DEFAULTS_NOT_CONFIGURED_MESSAGE;
  }
  return err instanceof Error && err.message ? err.message : '지식베이스를 만들지 못했습니다';
};

const KnowledgeDocsBlock = ({
  agentName,
  visibility,
  departmentId,
  attachedKbId,
  mode,
  locked = false,
  onAttached,
  onDetach,
}: KnowledgeDocsBlockProps) => {
  const inputId = useId();
  const { data: defaults, isLoading: isDefaultsLoading } = useKbDefaults();
  const { data: knowledgeBases } = useKnowledgeBases();
  const quick = useQuickKnowledgeBase();
  const retry = useRetryKbUpload();
  const [lastFiles, setLastFiles] = useState<File[]>([]);
  /** 마지막 /quick 또는 재시도 결과 — 재시도는 이 결과의 kb_id 를 재사용한다 (G1) */
  const [result, setResult] = useState<QuickKbResponse | null>(null);

  const configured = defaults?.configured ?? false;
  const isPending = quick.isPending || retry.isPending;
  const error = quick.error ?? retry.error;
  const phase: QuickKbPhase = isPending
    ? 'pending'
    : error
      ? 'error'
      : result
        ? 'done'
        : 'idle';
  const attachedKb = attachedKbId
    ? knowledgeBases?.find((kb) => kb.kb_id === attachedKbId)
    : undefined;

  // FR-08: 성공 파일이 1개 이상일 때만 도구를 연결한다. 전부 실패면 미부착.
  const settle = (data: QuickKbResponse) => {
    setResult(data);
    if (data.uploaded_count > 0) onAttached(data.kb_id, data);
  };

  const submit = (files: File[]) => {
    if (files.length === 0) return;
    setLastFiles(files);
    quick.mutate(
      {
        name: kbNameForAgent(agentName),
        scope: scopeForVisibility(visibility),
        departmentId: visibility === 'department' ? departmentId : null,
        files,
      },
      { onSuccess: settle },
    );
  };

  /** G1: KB 는 이미 있으므로 같은 KB 에 파일만 다시 올린다. KB 생성 자체가 실패했으면 처음부터. */
  const handleRetry = () => {
    if (result?.kb_id) {
      retry.mutate({ kb: result, files: lastFiles }, { onSuccess: settle });
    } else {
      submit(lastFiles);
    }
  };

  const handleFiles = (list: FileList | null) => {
    const files = Array.from(list ?? []).slice(0, KB_QUICK_MAX_FILES);
    submit(files);
  };

  const failedDocs = result?.documents.filter((d) => d.status === KB_QUICK_DOC_STATUS.FAILED) ?? [];
  const allFailed = !!result && result.uploaded_count === 0;
  const canDrop = configured && !locked && !isPending;
  // G2: 자동 생성 KB 는 저장과 무관하게 남는다 — 생성 직후에도, 위저드에서도 알린다.
  const showOrphanNotice = mode === 'studio' || !!result || !!attachedKbId;

  return (
    <section
      aria-label="지식 문서"
      className="mb-3 rounded-2xl border border-violet-200 bg-violet-50/30 p-4"
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[13px] font-semibold text-zinc-800">지식 문서</span>
        {attachedKb && (
          <span
            className={`rounded-md px-2 py-0.5 text-[11px] font-semibold ${SCOPE_LABELS[attachedKb.scope].bg} ${SCOPE_LABELS[attachedKb.scope].color}`}
          >
            {SCOPE_LABELS[attachedKb.scope].label}
          </span>
        )}
      </div>

      {attachedKbId ? (
        <div className="flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2">
          <span className="text-[13px] text-emerald-800">
            연결됨: {attachedKb?.name ?? attachedKbId}
          </span>
          {!locked && (
            <button
              type="button"
              onClick={onDetach}
              className="ml-auto rounded-lg px-2 py-1 text-[12px] font-medium text-zinc-500 transition-colors hover:bg-white hover:text-zinc-800"
            >
              바꾸기
            </button>
          )}
        </div>
      ) : (
        <>
          <p className="mb-3 text-[12.5px] leading-relaxed text-zinc-600">
            문서를 올리면 이 에이전트 전용 지식베이스가 만들어지고 문서 검색 도구가
            연결됩니다.
          </p>

          {!isDefaultsLoading && !configured && (
            <p role="alert" className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-[12px] text-amber-700">
              {KB_DEFAULTS_NOT_CONFIGURED_MESSAGE}
            </p>
          )}

          <label
            htmlFor={inputId}
            className={`block cursor-pointer rounded-xl border-2 border-dashed px-4 py-5 text-center transition-colors ${
              canDrop
                ? 'border-violet-300 bg-white hover:border-violet-400'
                : 'cursor-not-allowed border-zinc-200 bg-zinc-50 text-zinc-400'
            }`}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (canDrop) handleFiles(e.dataTransfer.files);
            }}
          >
            <span className="block text-[13px] font-medium">파일 끌어다 놓기 / 선택</span>
            <span className="mt-1 block text-[11.5px] text-zinc-400">
              PDF·엑셀·한글 최대 {KB_QUICK_MAX_FILES}개
            </span>
            <input
              id={inputId}
              type="file"
              multiple
              accept={KB_QUICK_ACCEPT}
              aria-label="지식 문서 파일 선택"
              disabled={!canDrop}
              className="sr-only"
              onChange={(e) => {
                handleFiles(e.target.files);
                e.target.value = '';
              }}
            />
          </label>

          <div className="mt-3">
            <span className="mb-1 block text-[12px] text-zinc-500">또는 기존 지식베이스 선택</span>
            <Dropdown
              value=""
              onChange={(kbId) => {
                if (kbId) onAttached(kbId, null);
              }}
              ariaLabel="기존 지식베이스 선택"
              placeholder="선택 안 함"
              disabled={locked}
              options={[
                { value: '', label: '선택 안 함' },
                ...(knowledgeBases ?? []).map((kb) => ({
                  value: kb.kb_id,
                  label: `[${SCOPE_LABELS[kb.scope].label}] ${kb.name}`,
                })),
              ]}
              className="w-full"
            />
          </div>
        </>
      )}

      {phase !== 'idle' && (
        <div className="mt-3" aria-live="polite">
          <ProgressCard
            steps={quickKbProgressSteps(phase, result, lastFiles.length)}
            title="지식 문서 준비"
          />
          {phase === 'error' && (
            <p role="alert" className="mt-2 text-[12px] text-red-600">
              {errorMessage(error)}
            </p>
          )}
          {failedDocs.length > 0 && (
            <ul className="mt-2 space-y-1" aria-label="올리지 못한 파일">
              {failedDocs.map((d) => (
                <li key={d.filename} className="text-[12px] text-red-600">
                  {d.filename}: {d.error ?? '올리지 못했습니다'}
                </li>
              ))}
            </ul>
          )}
          {allFailed && !isPending && (
            <div className="mt-2 flex items-center gap-2">
              <span className="text-[12px] text-red-600">도구를 연결하지 못했습니다</span>
              <button
                type="button"
                onClick={handleRetry}
                className="rounded-lg bg-violet-600 px-3 py-1.5 text-[12px] font-medium text-white transition-all hover:bg-violet-700"
              >
                다시 시도
              </button>
            </div>
          )}
        </div>
      )}

      {showOrphanNotice && (
        <p className="mt-3 text-[11.5px] text-zinc-400">저장하지 않아도 지식베이스는 남습니다</p>
      )}
    </section>
  );
};

export default KnowledgeDocsBlock;
