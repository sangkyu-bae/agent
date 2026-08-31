// Design Ref: multimodal-extractor §5.3/§5.4 — 미리보기 요소 카드 1건
import { useState } from 'react';
import {
  ELEMENT_STATUS_LABELS,
  ELEMENT_TYPE_LABELS,
  type MultimodalElement,
} from '@/types/multimodal';

interface MultimodalElementCardProps {
  element: MultimodalElement;
}

const typeBadgeCls: Record<MultimodalElement['element_type'], string> = {
  figure: 'bg-sky-50 text-sky-700',
  chart: 'bg-violet-50 text-violet-700',
  table_image: 'bg-amber-50 text-amber-700',
  page_scan: 'bg-zinc-100 text-zinc-700',
};

const statusBadgeCls: Record<MultimodalElement['status'], string> = {
  succeeded: 'bg-emerald-50 text-emerald-700',
  failed: 'bg-red-50 text-red-600',
  skipped: 'bg-zinc-100 text-zinc-500',
};

const Collapsible = ({ title, children }: { title: string; children: React.ReactNode }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-[12px] font-medium text-violet-600 hover:underline"
        aria-expanded={open}
      >
        {open ? '▾' : '▸'} {title}
      </button>
      {open && <div className="mt-1">{children}</div>}
    </div>
  );
};

const MultimodalElementCard = ({ element: e }: MultimodalElementCardProps) => {
  const typeLabel = ELEMENT_TYPE_LABELS[e.element_type];
  return (
    <article
      data-testid="mm-element-card"
      className="flex gap-3 rounded-xl border border-zinc-200 bg-white p-3"
    >
      <div className="h-24 w-24 shrink-0 overflow-hidden rounded-lg bg-zinc-100">
        {e.thumbnail_b64 ? (
          <img
            src={`data:image/png;base64,${e.thumbnail_b64}`}
            alt={typeLabel}
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-[11px] text-zinc-400">
            썸네일 없음
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[12px] font-medium text-zinc-500">p.{e.page}</span>
          <span className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${typeBadgeCls[e.element_type]}`}>
            {typeLabel}
          </span>
          <span className={`rounded-md px-2 py-0.5 text-[11px] font-medium ${statusBadgeCls[e.status]}`}>
            {ELEMENT_STATUS_LABELS[e.status]}
          </span>
          {e.degraded_output_mode && (
            <span
              className="rounded-md bg-orange-50 px-2 py-0.5 text-[11px] font-medium text-orange-600"
              title="strict 구조화 출력 대신 폴백 모드로 해석됨"
            >
              degraded
            </span>
          )}
          {e.elapsed_ms != null && (
            <span className="text-[11px] text-zinc-400">{e.elapsed_ms}ms</span>
          )}
        </div>

        {e.status !== 'succeeded' && e.reason && (
          <p className="mt-1 text-[12px] text-red-500">{e.reason}</p>
        )}

        {e.description && (
          <p className="mt-1 whitespace-pre-wrap text-[13px] text-zinc-800">{e.description}</p>
        )}

        {e.keywords.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {e.keywords.map((k) => (
              <span key={k} className="rounded-full bg-zinc-100 px-2 py-0.5 text-[11px] text-zinc-600">
                {k}
              </span>
            ))}
          </div>
        )}

        {e.chart && (
          <Collapsible title={`차트 판독 (${e.chart.data_points.length}개 수치)`}>
            <div className="text-[12px] text-zinc-600">
              {[e.chart.chart_type, e.chart.x_axis && `x: ${e.chart.x_axis}`, e.chart.y_axis && `y: ${e.chart.y_axis}`]
                .filter(Boolean)
                .join(' · ')}
              {e.chart.trend && <span className="ml-2 text-violet-600">추세: {e.chart.trend}</span>}
            </div>
            {e.chart.data_points.length > 0 && (
              <table className="mt-1 text-[12px]">
                <tbody>
                  {e.chart.data_points.map((p, i) => (
                    <tr key={`${p.label}-${i}`}>
                      <td className="pr-3 text-zinc-500">{p.label}</td>
                      <td className="text-zinc-800">{p.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Collapsible>
        )}

        {e.markdown_table && (
          <Collapsible title="마크다운 표">
            <pre className="overflow-x-auto rounded-lg bg-zinc-50 p-2 text-[11px] text-zinc-700">
              {e.markdown_table}
            </pre>
          </Collapsible>
        )}

        {e.page_text && (
          <Collapsible title="전사 텍스트">
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-zinc-50 p-2 text-[11px] text-zinc-700">
              {e.page_text}
            </pre>
          </Collapsible>
        )}
      </div>
    </article>
  );
};

export default MultimodalElementCard;
