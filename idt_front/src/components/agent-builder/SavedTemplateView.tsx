// Design Ref: extractor-template-preview §5.1 — 저장된 양식 보기 (읽기 전용, 교체는 업로드 모드로)
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import Badge from '@/components/ui/Badge';
import Button from '@/components/ui/Button';
import {
  buildPreviewHtml,
  extractPageWidthPt,
  ptToPx,
} from '@/utils/documentTemplate';
import type {
  AgentDocumentTemplateResponse,
  TemplateSlot,
} from '@/types/documentExtractor';
import { SAVED_TEMPLATE_TEXT } from '@/types/documentExtractor';

interface SavedTemplateViewProps {
  /** null = 양식 없음(404), undefined = 아직 없음 */
  template: AgentDocumentTemplateResponse | null | undefined;
  isLoading: boolean;
  isError: boolean;
  onReplace: () => void;
}

const SLOT_TYPE_BADGE = {
  value: { label: '값', tone: 'info' },
  generated: { label: '작성', tone: 'brand' },
} as const;

/** 원본 HTML 에서 온 라벨·예시값의 개행·탭을 한 칸으로 접는다 */
const collapse = (text: string) => text.replace(/\s+/g, ' ').trim();

const SavedTemplateView = ({
  template,
  isLoading,
  isError,
  onReplace,
}: SavedTemplateViewProps) => {
  const previewWrapRef = useRef<HTMLDivElement>(null);
  const [previewWidth, setPreviewWidth] = useState<number | null>(null);

  // sandbox iframe 내부 JS 불가 → 컨테이너 폭으로 srcDoc CSS 스케일 (추출기 패널 D6 과 동일)
  useLayoutEffect(() => {
    const measure = () => {
      if (previewWrapRef.current) setPreviewWidth(previewWrapRef.current.clientWidth);
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [template]);

  const previewHtml = useMemo(() => {
    if (!template) return '';
    const slots: TemplateSlot[] = template.slots.map((s) => ({
      ...s,
      label: collapse(s.label),
      fill_hint: '',
    }));
    const pageWidthPt = extractPageWidthPt(template.html_skeleton);
    const pageWidthPx = pageWidthPt !== null ? ptToPx(pageWidthPt) : undefined;
    const scale =
      pageWidthPx !== undefined && previewWidth !== null && previewWidth > 0
        ? Math.min(1, previewWidth / pageWidthPx)
        : undefined;
    return buildPreviewHtml(template.html_skeleton, slots, { scale, pageWidthPx }).html;
  }, [template, previewWidth]);

  const replaceButton = (
    <Button variant="secondary" size="sm" onClick={onReplace}>
      {SAVED_TEMPLATE_TEXT.replace}
    </Button>
  );

  if (isLoading) {
    return (
      <p role="status" className="text-sm text-fg-subtle">
        {SAVED_TEMPLATE_TEXT.loading}
      </p>
    );
  }

  if (isError || !template) {
    return (
      <div className="space-y-3">
        <p role="alert" className="text-sm text-danger">
          {SAVED_TEMPLATE_TEXT.error}
        </p>
        {replaceButton}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <h3 className="text-base font-semibold text-fg">{SAVED_TEMPLATE_TEXT.heading}</h3>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-fg-secondary">{template.name}</span>
          <Badge>{template.source_format.toUpperCase()}</Badge>
          <Badge>{`슬롯 ${template.slots.length}`}</Badge>
          {template.is_inherited && <Badge tone="info">{SAVED_TEMPLATE_TEXT.inherited}</Badge>}
        </div>
        <p className="text-xs text-fg-subtle">{SAVED_TEMPLATE_TEXT.previewNotice}</p>
      </div>

      <div ref={previewWrapRef}>
        <iframe
          title={SAVED_TEMPLATE_TEXT.previewTitle}
          sandbox=""
          srcDoc={previewHtml}
          className="h-[45vh] min-h-56 w-full rounded-xl border border-border bg-surface"
        />
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium text-fg-subtle">
          자동화 슬롯 ({template.slots.length})
        </p>
        <ul className="space-y-1.5">
          {template.slots.map((slot) => {
            const badge = SLOT_TYPE_BADGE[slot.slot_type];
            const sample = collapse(slot.sample_value);
            return (
              <li
                key={slot.key}
                className="flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2"
              >
                <Badge tone={badge.tone}>{badge.label}</Badge>
                <span className="shrink-0 text-sm font-medium text-fg-secondary">
                  {collapse(slot.label)}
                </span>
                {sample && (
                  <span className="min-w-0 flex-1 truncate text-xs text-fg-subtle">
                    {`예: ${sample}`}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
        {template.samples_hidden && (
          <p className="mt-2 text-xs text-fg-subtle">{SAVED_TEMPLATE_TEXT.samplesHidden}</p>
        )}
      </div>

      {replaceButton}
    </div>
  );
};

export default SavedTemplateView;
