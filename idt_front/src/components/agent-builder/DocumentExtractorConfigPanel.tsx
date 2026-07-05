import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useExtractDocument, useRefineSlots } from '@/hooks/useDocumentExtractor';
import {
  buildPreviewHtml,
  extractPageWidthPt,
  generateSlotKey,
  ptToPx,
  tokenizeHtml,
} from '@/utils/documentTemplate';
import type {
  DocumentExtractorDraft,
  SlotType,
  TemplateSlot,
} from '@/types/documentExtractor';
import { IDLE_RESUGGEST_MS, MAX_REGEN } from '@/types/documentExtractor';

interface DocumentExtractorConfigPanelProps {
  draft: DocumentExtractorDraft | null;
  onChange: (draft: DocumentExtractorDraft | null) => void;
}

const SLOT_TYPE_BADGE = {
  value: { label: '값', className: 'bg-sky-100 text-sky-600' },
  generated: { label: '작성', className: 'bg-violet-100 text-violet-600' },
} as const;

/**
 * 문서추출기 설정 패널 (document-template-extractor Design §7-2).
 *
 * 업로드 → MCP 변환 + 슬롯 추천(extract) → 미리보기/슬롯 편집 →
 * 재요청(refine, 상한 R5) → 확정(프론트 토큰화 D2) → 폼 보유(생성 시 저장).
 * 미확정 5분 유휴 시 자동 재추천 (Plan GA3).
 */
const DocumentExtractorConfigPanel = ({
  draft,
  onChange,
}: DocumentExtractorConfigPanelProps) => {
  const [instruction, setInstruction] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [noticeMessage, setNoticeMessage] = useState<string | null>(null);
  const [newSlotLabel, setNewSlotLabel] = useState('');
  const [newSlotSample, setNewSlotSample] = useState('');
  const [newSlotType, setNewSlotType] = useState<SlotType>('value');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const previewWrapRef = useRef<HTMLDivElement>(null);
  const [previewWidth, setPreviewWidth] = useState<number | null>(null);

  const extractMutation = useExtractDocument();
  const refineMutation = useRefineSlots();

  const isBusy = extractMutation.isPending || refineMutation.isPending;

  // D6: 미리보기 컨테이너 폭 측정 (sandbox iframe 내부 JS 불가 → srcDoc CSS 스케일)
  useLayoutEffect(() => {
    const measure = () => {
      if (previewWrapRef.current) {
        setPreviewWidth(previewWrapRef.current.clientWidth);
      }
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [draft]);

  // 미리보기: layout HTML 우선(D1), 확정 후엔 skeleton. 스케일+하이라이트 조립.
  const previewSource = draft
    ? draft.confirmed
      ? draft.htmlSkeleton
      : (draft.previewHtml ?? draft.html)
    : '';
  const preview = useMemo(() => {
    if (!draft) return null;
    const pageWidthPt = extractPageWidthPt(previewSource);
    const pageWidthPx = pageWidthPt !== null ? ptToPx(pageWidthPt) : undefined;
    const scale =
      pageWidthPx !== undefined && previewWidth !== null && previewWidth > 0
        ? Math.min(1, previewWidth / pageWidthPx)
        : undefined;
    return buildPreviewHtml(previewSource, draft.slots, {
      scale,
      pageWidthPx,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewSource, draft?.slots, previewWidth]);

  const missingSlotLabels =
    draft && preview
      ? draft.slots
          .filter((s) => preview.missingSlotKeys.includes(s.key))
          .map((s) => s.label)
      : [];

  // R4(복원/동기화)는 LeftConfigPanel로 이동 — 모달을 열지 않아도 배지가 정확하도록 (tool-config-modal Design §2.5).

  const handleFileSelected = (file: File | null) => {
    if (!file) return;
    setErrorMessage(null);
    setNoticeMessage(null);
    extractMutation.mutate(
      { file },
      {
        onSuccess: (response) => {
          onChange({
            sourceFileId: response.source_file_id,
            sourceFormat: response.source_format,
            html: response.html,
            previewHtml: response.preview_html ?? undefined,
            slots: response.suggested_slots,
            mcpPdfToHtmlToolId: response.mcp_pdf_to_html_tool_id,
            mcpHtmlToDocToolId: response.mcp_html_to_doc_tool_id,
            regenCount: 0,
            confirmed: false,
            templateName: file.name.replace(/\.(pdf|docx)$/i, ''),
            htmlSkeleton: '',
          });
        },
        onError: (error) => setErrorMessage(error.message),
      },
    );
  };

  const runRefine = (draftNow: DocumentExtractorDraft, text: string) => {
    if (draftNow.regenCount >= MAX_REGEN) {
      setErrorMessage(`재추천 상한(${MAX_REGEN}회)에 도달했습니다.`);
      return;
    }
    setErrorMessage(null);
    refineMutation.mutate(
      {
        html: draftNow.html,
        instruction: text,
        prev_slots: draftNow.slots,
        regen_count: draftNow.regenCount,
      },
      {
        onSuccess: (response) => {
          onChange({
            ...draftNow,
            slots: response.suggested_slots,
            regenCount: draftNow.regenCount + 1,
            confirmed: false,
            htmlSkeleton: '',
          });
        },
        onError: (error) => setErrorMessage(error.message),
      },
    );
  };

  // 유휴 5분 재추천 (미확정 드래프트만, 상한 도달 시 중지)
  useEffect(() => {
    if (!draft || draft.confirmed || draft.regenCount >= MAX_REGEN) return;
    const timer = setTimeout(() => {
      runRefine(draft, '추천이 오래되어 자동으로 다시 추천합니다. 문서에서 자동화할 항목을 재검토해주세요.');
    }, IDLE_RESUGGEST_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  const handleRemoveSlot = (key: string) => {
    if (!draft) return;
    onChange({
      ...draft,
      slots: draft.slots.filter((s) => s.key !== key),
      confirmed: false,
      htmlSkeleton: '',
    });
  };

  const handleEditSlotLabel = (key: string, label: string) => {
    if (!draft) return;
    onChange({
      ...draft,
      slots: draft.slots.map((s) => (s.key === key ? { ...s, label } : s)),
      confirmed: false,
      htmlSkeleton: '',
    });
  };

  const handleAddSlot = () => {
    if (!draft) return;
    const label = newSlotLabel.trim();
    const sample = newSlotSample.trim();
    if (!label || !sample) {
      setErrorMessage('수동 슬롯은 항목명과 예시값(문서 내 실제 텍스트)이 모두 필요합니다.');
      return;
    }
    if (!draft.html.includes(sample)) {
      setErrorMessage('예시값이 문서 본문에 없습니다. 문서에 있는 텍스트를 그대로 입력하세요.');
      return;
    }
    setErrorMessage(null);
    const key = generateSlotKey(draft.slots.map((s) => s.key));
    const slot: TemplateSlot = {
      key,
      label,
      slot_type: newSlotType,
      description: '',
      fill_hint: '',
      sample_value: sample,
    };
    onChange({
      ...draft,
      slots: [...draft.slots, slot],
      confirmed: false,
      htmlSkeleton: '',
    });
    setNewSlotLabel('');
    setNewSlotSample('');
    setNewSlotType('value');
  };

  const handleConfirm = () => {
    if (!draft) return;
    const { htmlSkeleton, usedSlots, missingSlots } = tokenizeHtml(
      draft.html,
      draft.slots,
    );
    if (usedSlots.length === 0) {
      setErrorMessage(
        '확정할 수 있는 슬롯이 없습니다. 예시값이 문서에 존재하는 슬롯이 최소 1개 필요합니다.',
      );
      return;
    }
    setErrorMessage(null);
    setNoticeMessage(
      missingSlots.length > 0
        ? `예시값을 문서에서 찾지 못한 슬롯은 제외되었습니다: ${missingSlots
            .map((s) => s.label)
            .join(', ')}`
        : null,
    );
    onChange({
      ...draft,
      slots: usedSlots,
      confirmed: true,
      htmlSkeleton,
    });
  };

  const handleReset = () => {
    setErrorMessage(null);
    setNoticeMessage(null);
    onChange(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="rounded-xl border border-zinc-200 bg-zinc-50/60 p-4">
      <p className="mb-3 text-[12.5px] font-semibold text-zinc-700">
        문서추출기 — 양식 등록
      </p>

      {/* 업로드 */}
      {!draft && (
        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx"
            aria-label="양식 문서 업로드"
            disabled={isBusy}
            onChange={(e) => handleFileSelected(e.target.files?.[0] ?? null)}
            className="block w-full text-[12.5px] text-zinc-500 file:mr-3 file:rounded-lg file:border-0 file:bg-violet-600 file:px-3 file:py-1.5 file:text-[12px] file:font-medium file:text-white hover:file:bg-violet-700"
          />
          <p className="mt-2 text-[11.5px] text-zinc-400">
            PDF/Word 양식을 올리면 자동화할 항목(슬롯)을 추천합니다. 산출물은
            원본과 같은 포맷으로 생성됩니다.
          </p>
          {extractMutation.isPending && (
            <p className="mt-2 text-[12px] text-violet-600">
              문서를 변환하고 자동화 항목을 분석하는 중…
            </p>
          )}
        </div>
      )}

      {/* 추천 결과 + 확정 */}
      {draft && (
        <div className="space-y-3">
          {/* 템플릿 이름 */}
          <div>
            <label className="mb-1 block text-[11.5px] font-medium text-zinc-500">
              템플릿 이름
            </label>
            <input
              type="text"
              value={draft.templateName}
              onChange={(e) =>
                onChange({ ...draft, templateName: e.target.value })
              }
              aria-label="템플릿 이름"
              className="w-full rounded-lg border border-zinc-200 bg-white px-3 py-2 text-[13px] text-zinc-800 outline-none focus:border-violet-400"
            />
          </div>

          {/* 미리보기 (sandbox iframe — R7 방어 2선) */}
          <div ref={previewWrapRef}>
            <p className="mb-1 text-[11.5px] font-medium text-zinc-500">
              미리보기 (하이라이트 = 자동화 슬롯)
            </p>
            <iframe
              title="양식 미리보기"
              sandbox=""
              srcDoc={preview?.html ?? ''}
              className="h-[45vh] min-h-56 w-full rounded-lg border border-zinc-200 bg-white"
            />
            {missingSlotLabels.length > 0 && (
              <p className="mt-1.5 text-[11.5px] text-amber-600">
                문서에서 위치를 찾지 못한 슬롯 {missingSlotLabels.length}개:{' '}
                {missingSlotLabels.join(', ')} — 확정 시 제외됩니다
              </p>
            )}
          </div>

          {/* 슬롯 목록 */}
          <div>
            <p className="mb-1.5 text-[11.5px] font-medium text-zinc-500">
              자동화 슬롯 ({draft.slots.length})
            </p>
            {draft.slots.length > 0 ? (
              <ul className="space-y-1.5">
                {draft.slots.map((slot: TemplateSlot) => {
                  const badge = SLOT_TYPE_BADGE[slot.slot_type];
                  return (
                    <li
                      key={slot.key}
                      className="flex items-center gap-2 rounded-lg border border-zinc-200 bg-white px-3 py-2"
                    >
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${badge.className}`}
                      >
                        {badge.label}
                      </span>
                      {draft.confirmed ? (
                        <span className="text-[12.5px] font-medium text-zinc-700">
                          {slot.label}
                        </span>
                      ) : (
                        <input
                          type="text"
                          value={slot.label}
                          onChange={(e) =>
                            handleEditSlotLabel(slot.key, e.target.value)
                          }
                          aria-label={`${slot.key} 라벨`}
                          className="w-28 shrink-0 rounded border border-transparent bg-transparent px-1 py-0.5 text-[12.5px] font-medium text-zinc-700 hover:border-zinc-200 focus:border-violet-400 focus:bg-white focus:outline-none"
                        />
                      )}
                      {slot.sample_value && (
                        <span className="min-w-0 flex-1 truncate text-[11.5px] text-zinc-400">
                          예: {slot.sample_value}
                        </span>
                      )}
                      {!draft.confirmed && (
                        <button
                          type="button"
                          onClick={() => handleRemoveSlot(slot.key)}
                          aria-label={`${slot.label} 슬롯 제거`}
                          className="ml-auto shrink-0 rounded px-1.5 py-0.5 text-[11.5px] text-zinc-400 hover:bg-red-50 hover:text-red-500"
                        >
                          제거
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="rounded-lg border border-dashed border-zinc-200 bg-white py-3 text-center text-[12px] text-zinc-400">
                추천된 슬롯이 없습니다 — 재요청으로 보강하거나 아래에서 직접
                추가하세요
              </p>
            )}
          </div>

          {/* 슬롯 수동 추가 (추천이 놓친 항목 보완) */}
          {!draft.confirmed && (
            <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-2.5">
              <p className="mb-1.5 text-[11px] font-medium text-zinc-500">
                슬롯 직접 추가
              </p>
              <div className="flex flex-wrap gap-1.5">
                <input
                  type="text"
                  value={newSlotLabel}
                  onChange={(e) => setNewSlotLabel(e.target.value)}
                  placeholder="항목명 (예: 담당자)"
                  aria-label="새 슬롯 항목명"
                  className="min-w-[90px] flex-1 rounded border border-zinc-200 px-2 py-1.5 text-[12px] outline-none focus:border-violet-400"
                />
                <input
                  type="text"
                  value={newSlotSample}
                  onChange={(e) => setNewSlotSample(e.target.value)}
                  placeholder="문서 내 예시값"
                  aria-label="새 슬롯 예시값"
                  className="min-w-[90px] flex-1 rounded border border-zinc-200 px-2 py-1.5 text-[12px] outline-none focus:border-violet-400"
                />
                <select
                  value={newSlotType}
                  onChange={(e) => setNewSlotType(e.target.value as SlotType)}
                  aria-label="새 슬롯 유형"
                  className="rounded border border-zinc-200 px-2 py-1.5 text-[12px] outline-none focus:border-violet-400"
                >
                  <option value="value">값</option>
                  <option value="generated">작성</option>
                </select>
                <button
                  type="button"
                  onClick={handleAddSlot}
                  className="rounded bg-zinc-900 px-3 py-1.5 text-[12px] font-medium text-white hover:bg-zinc-800"
                >
                  추가
                </button>
              </div>
            </div>
          )}

          {/* 재요청 (미확정 시) */}
          {!draft.confirmed && (
            <div className="flex gap-2">
              <input
                type="text"
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                placeholder="보강 요청 (예: 금액 항목을 더 잘게 나눠줘)"
                aria-label="재추천 요청"
                className="min-w-0 flex-1 rounded-lg border border-zinc-200 bg-white px-3 py-2 text-[12.5px] outline-none focus:border-violet-400"
              />
              <button
                type="button"
                disabled={isBusy || !instruction.trim()}
                onClick={() => {
                  runRefine(draft, instruction.trim());
                  setInstruction('');
                }}
                className="shrink-0 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-[12px] font-medium text-zinc-600 hover:bg-zinc-100 disabled:opacity-40"
              >
                {refineMutation.isPending ? '재추천 중…' : '재요청'}
              </button>
            </div>
          )}

          {/* 상태/에러 */}
          {noticeMessage && (
            <p className="text-[11.5px] text-amber-600">{noticeMessage}</p>
          )}
          {errorMessage && (
            <p className="text-[11.5px] text-red-500">{errorMessage}</p>
          )}
          {draft.confirmed && (
            <p className="rounded-lg bg-emerald-50 px-3 py-2 text-[12px] font-medium text-emerald-700">
              ✓ 확정됨 — 에이전트 생성 시 이 템플릿이 함께 등록됩니다
            </p>
          )}

          {/* 액션 */}
          <div className="flex gap-2">
            {!draft.confirmed && (
              <button
                type="button"
                onClick={handleConfirm}
                disabled={isBusy || draft.slots.length === 0}
                className="rounded-lg bg-violet-600 px-3.5 py-2 text-[12.5px] font-medium text-white hover:bg-violet-700 disabled:opacity-40"
              >
                슬롯 확정
              </button>
            )}
            <button
              type="button"
              onClick={handleReset}
              className="rounded-lg border border-zinc-300 bg-white px-3.5 py-2 text-[12.5px] font-medium text-zinc-500 hover:bg-zinc-100"
            >
              다시 업로드
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default DocumentExtractorConfigPanel;
