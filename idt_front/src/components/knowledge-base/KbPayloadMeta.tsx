import { useState } from 'react';

/** Qdrant payload / ES 소스 필드를 그대로 노출하는 토글 (kb-content-browser Plan In-Scope B).
 *  저장 정합성 눈검증용 — 기본 접힘. */
const KbPayloadMeta = ({ metadata }: { metadata: Record<string, string> }) => {
  const [open, setOpen] = useState(false);
  const entries = Object.entries(metadata);

  if (entries.length === 0) return null;

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-[11.5px] font-medium text-zinc-400 hover:text-violet-600"
      >
        {open ? 'ⓘ 메타 닫기' : 'ⓘ 메타 보기'}
      </button>
      {open && (
        <dl className="mt-1.5 space-y-0.5 rounded-lg bg-zinc-50 p-2.5 font-mono text-[11px] text-zinc-500">
          {entries.map(([key, value]) => (
            <div key={key} className="flex gap-2">
              <dt className="shrink-0 font-semibold text-zinc-600">{key}</dt>
              <dd className="break-all">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
};

export default KbPayloadMeta;
