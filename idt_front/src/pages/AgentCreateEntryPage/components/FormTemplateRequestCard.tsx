// Design Ref: wizard-template-request §5.1/§3.1 — 위저드 양식 요청 카드.
// 상태는 templateDraft 에서 파생한다(draft 없음=idle, 미확정=review, 확정=confirmed).
// 추출 진행·에러만 카드 로컬이다. 미리보기는 없다(D6) — 슬롯 목록으로 판단 근거를 준다.
import { useRef, useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import ProgressCard from '@/components/common/ProgressCard';
import { useExtractDocument } from '@/hooks/useDocumentExtractor';
import { PROGRESS_STEP_STATUS } from '@/types/progress';
import type { ProgressStep } from '@/types/progress';
import type { PipelineDocumentRequest } from '@/types/agentPipeline';
import type { DocumentExtractorDraft } from '@/types/documentExtractor';
import {
  NO_USABLE_SLOTS_MESSAGE,
  extractErrorMessage,
} from '@/utils/documentExtractorErrors';
import { confirmTemplateDraft, extractResponseToDraft } from '@/utils/wizardTemplate';

export interface FormTemplateRequestCardProps {
  request: PipelineDocumentRequest;
  draft: DocumentExtractorDraft | null;
  /** 프롬프트 단계 진입 후 읽기 전용 이력 (FR-11) */
  locked?: boolean;
  /** 잠긴 상태에서 "건너뜀" 표기용 */
  skipped?: boolean;
  onDraftChange: (draft: DocumentExtractorDraft | null) => void;
  /** 추출 진행 중 여부 — 부모가 [건너뛰기]/[계속]을 잠근다 (FR-15) */
  onBusyChange: (busy: boolean) => void;
}

const MAX_VISIBLE_SLOTS = 20;

const extractingSteps = (): ProgressStep[] => [
  { id: 'convert', label: '양식 변환', status: PROGRESS_STEP_STATUS.IN_PROGRESS },
  { id: 'suggest', label: '채움 항목 추천', status: PROGRESS_STEP_STATUS.PENDING },
];

const FormTemplateRequestCard = ({
  request,
  draft,
  locked = false,
  skipped = false,
  onDraftChange,
  onBusyChange,
}: FormTemplateRequestCardProps) => {
  const extractMutation = useExtractDocument();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const busy = extractMutation.isPending;
  const accept = request.accept.map((ext) => `.${ext}`).join(',');
  const acceptLabel = request.accept.map((ext) => ext.toUpperCase()).join(', ');

  const resetInput = () => {
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleFileSelected = async (file: File | null) => {
    if (!file || busy) return;
    setErrorMessage(null);
    setNotice(null);
    setFileName(file.name);
    onBusyChange(true);
    try {
      const response = await extractMutation.mutateAsync({ file });
      onDraftChange(extractResponseToDraft(response, file.name));
    } catch (error) {
      setErrorMessage(extractErrorMessage(error));
      onDraftChange(null);
    } finally {
      onBusyChange(false);
      resetInput();
    }
  };

  const handleConfirm = () => {
    if (!draft) return;
    const result = confirmTemplateDraft(draft);
    if (!result.ok) {
      setErrorMessage(NO_USABLE_SLOTS_MESSAGE);
      return;
    }
    setErrorMessage(null);
    setNotice(
      result.missingSlots.length > 0
        ? `예시값을 문서에서 찾지 못한 항목은 제외했습니다: ${result.missingSlots
            .map((s) => s.label)
            .join(', ')}`
        : null,
    );
    onDraftChange(result.draft);
  };

  const handleReset = () => {
    setErrorMessage(null);
    setNotice(null);
    setFileName('');
    onDraftChange(null);
    resetInput();
  };

  // ── 잠긴 이력 (FR-11) ────────────────────────────────────────────────
  if (locked) {
    return (
      <section
        aria-label="양식 요청"
        className="rounded-xl border border-zinc-200 bg-zinc-50/60 p-4"
      >
        <p className="text-[12.5px] font-medium text-violet-500">
          {draft?.confirmed
            ? `✓ 양식 등록: ${draft.templateName} · 슬롯 ${draft.slots.length}개`
            : skipped
              ? '✓ 건너뜀(양식)'
              : '양식 미등록'}
        </p>
      </section>
    );
  }

  return (
    <section
      aria-label="양식 요청"
      className="space-y-3 rounded-xl border border-violet-200 bg-violet-50/40 p-4"
    >
      <p className="text-[13px] leading-relaxed text-zinc-800">📄 {request.message}</p>

      {errorMessage && (
        <p role="alert" className="text-[12.5px] text-red-600">
          {errorMessage}
        </p>
      )}

      {busy && (
        <div aria-live="polite">
          <ProgressCard title={fileName || '양식 분석'} steps={extractingSteps()} />
        </div>
      )}

      {!busy && !draft && (
        <div className="space-y-1">
          <label
            htmlFor="form-template-file"
            className="block text-[12.5px] font-medium text-zinc-600"
          >
            양식 파일 선택
          </label>
          <input
            id="form-template-file"
            ref={fileInputRef}
            type="file"
            accept={accept}
            onChange={(e) => void handleFileSelected(e.target.files?.[0] ?? null)}
            className="block w-full text-[12.5px] text-zinc-500 file:mr-3 file:rounded-lg file:border-0 file:bg-violet-600 file:px-3 file:py-1.5 file:text-[12px] file:font-medium file:text-white hover:file:bg-violet-700"
          />
          <p className="text-[11.5px] text-zinc-400">{acceptLabel}</p>
        </div>
      )}

      {!busy && draft && (
        <div className="space-y-3">
          <p className="text-[13px] font-semibold text-zinc-800">
            {draft.confirmed
              ? `✓ 양식 등록: ${draft.templateName} · 슬롯 ${draft.slots.length}개`
              : `채움 항목 ${draft.slots.length}개를 찾았습니다`}
          </p>
          <ul role="list" aria-label="채움 항목" className="space-y-1.5">
            {draft.slots.slice(0, MAX_VISIBLE_SLOTS).map((slot) => (
              <li key={slot.key} className="text-[12.5px] text-zinc-700">
                <span className="font-medium">{slot.label}</span>
                {slot.description && (
                  <span className="text-zinc-500"> — {slot.description}</span>
                )}
                {slot.sample_value && (
                  <span className="text-zinc-400"> (예: {slot.sample_value})</span>
                )}
              </li>
            ))}
            {draft.slots.length > MAX_VISIBLE_SLOTS && (
              <li className="text-[12px] text-zinc-400">
                외 {draft.slots.length - MAX_VISIBLE_SLOTS}개
              </li>
            )}
          </ul>
          {notice && <p className="text-[12px] text-zinc-500">{notice}</p>}
          {!draft.confirmed && (
            <p className="text-[12px] text-zinc-500">
              세부 수정은 생성 후 스튜디오의 문서추출기 패널에서 할 수 있습니다.
            </p>
          )}
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={handleReset}
              className="rounded-xl px-4 py-2 text-[13px] font-medium text-zinc-500 transition-colors hover:bg-zinc-100"
            >
              다시 올리기
            </button>
            {!draft.confirmed && (
              <LoadingButton
                type="button"
                isPending={false}
                onClick={handleConfirm}
                className="rounded-xl bg-violet-600 px-4 py-2 text-[13px] font-medium text-white transition-all hover:bg-violet-700"
              >
                이대로 사용
              </LoadingButton>
            )}
          </div>
        </div>
      )}
    </section>
  );
};

export default FormTemplateRequestCard;
