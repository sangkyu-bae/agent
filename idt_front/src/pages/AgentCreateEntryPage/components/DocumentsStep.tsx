// Design Ref: agent-kb-quick-setup §5.1 — 위저드 "참고할 문서" 단계 (클라이언트 로컬 단계).
// 서버 파이프라인 5단계는 그대로다: 여기서는 요청을 보내지 않고 kb_id 만 모아 다음 PROMPT 요청에 싣는다.
import KnowledgeDocsBlock from '@/components/agent-builder/KnowledgeDocsBlock';

interface DocumentsStepProps {
  agentName: string;
  attachedKbId: string | null;
  isPending: boolean;
  /** 프롬프트 단계 진입 후 읽기 전용 이력 (FR-11) */
  locked?: boolean;
  onAttached: (kbId: string) => void;
  onDetach: () => void;
  onSkip: () => void;
  onContinue: () => void;
}

const DocumentsStep = ({
  agentName,
  attachedKbId,
  isPending,
  locked = false,
  onAttached,
  onDetach,
  onSkip,
  onContinue,
}: DocumentsStepProps) => (
  <div className="space-y-4">
    <div className="flex items-center justify-between">
      <h2 className="text-[15px] font-semibold text-zinc-900">참고할 문서가 있나요?</h2>
      {locked && (
        <span className="text-[12.5px] font-medium text-violet-500">
          {attachedKbId ? '✓ 문서 연결 완료' : '✓ 건너뜀'}
        </span>
      )}
    </div>
    {!locked && (
      <p className="text-[12.5px] text-zinc-500">
        문서를 올리면 이 에이전트 전용 지식베이스가 만들어지고 문서 검색 도구가 추가됩니다.
        없으면 건너뛰어도 됩니다.
      </p>
    )}

    <KnowledgeDocsBlock
      mode="wizard"
      agentName={agentName}
      visibility="private"
      attachedKbId={attachedKbId ?? undefined}
      locked={locked}
      onAttached={(kbId) => onAttached(kbId)}
      onDetach={onDetach}
    />

    {!locked && (
      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onSkip}
          disabled={isPending}
          className="rounded-xl px-4 py-2 text-[13px] font-medium text-zinc-500 transition-colors hover:bg-zinc-100 disabled:opacity-50"
        >
          건너뛰기
        </button>
        <button
          type="button"
          onClick={onContinue}
          disabled={isPending || !attachedKbId}
          className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white transition-all hover:bg-violet-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          계속
        </button>
      </div>
    )}
  </div>
);

export default DocumentsStep;
