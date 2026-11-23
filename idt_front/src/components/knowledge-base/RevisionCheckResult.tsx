// Design Ref: document-revision §5.1 — 사전 점검 결과 패널 (중복 차단 / 개정 제안 / 신규 안내).
import { useId } from 'react';
import Input from '@/components/ui/Input';
import type {
  DocumentVersion,
  RevisionCandidate,
  RevisionCheckResponse,
} from '@/types/knowledgeBase';
import type { RevisionDecision } from './revisionDecision';

interface RevisionCheckResultProps {
  result: RevisionCheckResponse;
  decision: RevisionDecision;
  onChange: (decision: RevisionDecision) => void;
}

const percent = (score: number) => `${Math.round(score * 100)}%`;

const versionText = (v: { version_no: number; version_label: string | null }) =>
  v.version_label ? `v${v.version_no} · ${v.version_label}` : `v${v.version_no}`;

const formatDate = (iso: string | null) => (iso ? iso.slice(0, 10) : null);

const DuplicateNotice = ({ doc }: { doc: DocumentVersion }) => {
  const uploaded = formatDate(doc.created_at);
  return (
    <div
      role="alert"
      className="rounded-xl border border-warning-border bg-warning-bg px-3 py-2.5 text-sm text-warning"
    >
      <p className="font-semibold">이미 같은 파일이 있습니다</p>
      <p className="mt-0.5">
        「{doc.filename}」 {versionText(doc)}
        {uploaded ? ` · ${uploaded} 업로드` : ''}
      </p>
      <p className="mt-1">
        {doc.revision_status === 'superseded'
          ? '이전 버전과 같은 파일입니다. 이전 버전을 다시 쓰려면 문서 이력에서 되돌리기를 사용하세요.'
          : '다른 파일을 선택하세요.'}
      </p>
    </div>
  );
};

const CandidateSummary = ({
  candidate,
  llmFailed,
}: {
  candidate: RevisionCandidate;
  llmFailed: boolean;
}) => (
  <div className="rounded-xl border border-info-border bg-info-bg px-3 py-2.5 text-sm text-fg-secondary">
    <p className="font-semibold text-fg">
      기존 「{candidate.filename}」 {versionText(candidate)}의 개정본으로 보입니다
    </p>
    {candidate.llm_reason && <p className="mt-1">근거: {candidate.llm_reason}</p>}
    <p className="mt-1 text-xs text-fg-muted">
      파일명 {percent(candidate.filename_score)} · 본문 {percent(candidate.content_score)}
    </p>
    {llmFailed && (
      <p className="mt-1 text-xs text-fg-muted">
        자동 판정을 하지 못해 일치 점수로 제안했습니다.
      </p>
    )}
  </div>
);

const RevisionCheckResult = ({ result, decision, onChange }: RevisionCheckResultProps) => {
  const groupName = useId();
  const targetSelectId = useId();

  if (result.verdict === 'duplicate' && result.duplicate_of) {
    return <DuplicateNotice doc={result.duplicate_of} />;
  }

  const suggested = result.candidates.find(
    (c) => c.document_id === result.suggested_document_id,
  );
  const update = (patch: Partial<RevisionDecision>) => onChange({ ...decision, ...patch });

  return (
    <div className="space-y-3">
      {result.verdict === 'revision_candidate' && suggested ? (
        <CandidateSummary candidate={suggested} llmFailed={result.llm_status === 'failed'} />
      ) : (
        <p className="rounded-xl bg-surface-muted px-3 py-2.5 text-sm text-fg-secondary">
          기존 문서 중 일치하는 개정 대상이 없습니다.
        </p>
      )}

      {result.candidates.length > 0 && (
        <fieldset className="space-y-2">
          <legend className="sr-only">업로드 방식</legend>
          <label className="flex items-center gap-2 text-sm text-fg">
            <input
              type="radio"
              name={groupName}
              checked={decision.mode === 'revision'}
              onChange={() =>
                update({
                  mode: 'revision',
                  targetId: decision.targetId ?? result.candidates[0].document_id,
                })
              }
            />
            기존 문서의 개정본으로 올리기
          </label>
          {decision.mode === 'revision' && result.candidates.length > 1 && (
            <div className="pl-6">
              <label htmlFor={targetSelectId} className="mb-1 block text-xs text-fg-muted">
                대상 문서
              </label>
              <select
                id={targetSelectId}
                value={decision.targetId ?? ''}
                onChange={(e) => update({ targetId: e.target.value })}
                className="h-8 w-full rounded-md border border-border bg-surface px-2 text-sm text-fg"
              >
                {result.candidates.map((c) => (
                  <option key={c.document_id} value={c.document_id}>
                    {c.filename} ({versionText(c)})
                  </option>
                ))}
              </select>
            </div>
          )}
          <label className="flex items-center gap-2 text-sm text-fg">
            <input
              type="radio"
              name={groupName}
              checked={decision.mode === 'new'}
              onChange={() => update({ mode: 'new' })}
            />
            새 문서로 올리기
          </label>
        </fieldset>
      )}

      {decision.mode === 'revision' && (
        <div className="grid grid-cols-2 gap-2">
          <Input
            label="버전 라벨"
            size="sm"
            maxLength={100}
            placeholder="예: 2026-11 개정"
            value={decision.versionLabel}
            onChange={(e) => update({ versionLabel: e.target.value })}
          />
          <Input
            label="시행일"
            size="sm"
            type="date"
            value={decision.effectiveDate}
            onChange={(e) => update({ effectiveDate: e.target.value })}
          />
        </div>
      )}
    </div>
  );
};

export default RevisionCheckResult;
