// Design §5.4 편집 탭 — 스타일 / 페이지 패턴 / 서사 / 폰트 매핑 / 에셋 / 경고
import { useBlueprintFonts } from '@/hooks/useBlueprints';
import {
  ASSET_KIND_LABELS,
  ASSET_KINDS,
  PATTERN_KIND_LABELS,
  PATTERN_KINDS,
  REQUIRED_SIZE_KEYS,
  SLOT_KIND_LABELS,
  type AssetKind,
  type AssetPreview,
  type BlueprintDraft,
  type BlueprintPattern,
  type NarrativeSection,
  type PatternKind,
} from '@/types/blueprint';

export type EditorTab = 'style' | 'patterns' | 'narrative' | 'fonts' | 'assets' | 'warnings';

const TABS: { key: EditorTab; label: string }[] = [
  { key: 'style', label: '스타일' },
  { key: 'patterns', label: '페이지 패턴' },
  { key: 'narrative', label: '서사' },
  { key: 'fonts', label: '폰트 매핑' },
  { key: 'assets', label: '에셋' },
  { key: 'warnings', label: '경고' },
];

const inputClass =
  'rounded-lg border border-zinc-200 bg-white px-2.5 py-1.5 text-[12.5px] text-zinc-800 outline-none focus:border-violet-400';
const labelClass = 'mb-1 block text-[12px] font-semibold text-zinc-600';

interface BlueprintTabsProps {
  tab: EditorTab;
  onTab: (t: EditorTab) => void;
  draft: BlueprintDraft;
  assets: AssetPreview[];
  pageThumbnails: (string | null)[];
  excluded: string[];
  onToggleExclude: (id: string) => void;
  onPatch: (partial: Partial<BlueprintDraft>) => void;
}

const BlueprintTabs = ({
  tab,
  onTab,
  draft,
  assets,
  pageThumbnails,
  excluded,
  onToggleExclude,
  onPatch,
}: BlueprintTabsProps) => (
  <div className="mt-3">
    <div role="tablist" aria-label="blueprint 편집 탭" className="mb-4 flex gap-1 border-b border-zinc-200">
      {TABS.map((t) => (
        <button
          key={t.key}
          role="tab"
          type="button"
          aria-selected={tab === t.key}
          onClick={() => onTab(t.key)}
          className={`-mb-px border-b-2 px-3 py-2 text-[13px] font-medium ${
            tab === t.key ? 'border-violet-600 text-violet-700' : 'border-transparent text-zinc-500'
          }`}
        >
          {t.label}
          {t.key === 'warnings' && draft.warnings.length > 0 && (
            <span className="ml-1 rounded bg-amber-100 px-1 text-[10.5px] text-amber-700">
              {draft.warnings.length}
            </span>
          )}
        </button>
      ))}
    </div>
    <div role="tabpanel">
      {tab === 'style' && <StyleTab draft={draft} onPatch={onPatch} />}
      {tab === 'patterns' && (
        <PatternsTab
          draft={draft}
          pageThumbnails={pageThumbnails}
          excluded={excluded}
          onToggleExclude={onToggleExclude}
          onPatch={onPatch}
        />
      )}
      {tab === 'narrative' && <NarrativeTab draft={draft} onPatch={onPatch} />}
      {tab === 'fonts' && <FontMappingTab draft={draft} onPatch={onPatch} />}
      {tab === 'assets' && <AssetsTab draft={draft} assets={assets} onPatch={onPatch} />}
      {tab === 'warnings' && <WarningsTab warnings={draft.warnings} />}
    </div>
  </div>
);

// ── 스타일 ───────────────────────────────────────────────

interface TabProps {
  draft: BlueprintDraft;
  onPatch: (partial: Partial<BlueprintDraft>) => void;
}

const StyleTab = ({ draft, onPatch }: TabProps) => {
  const style = draft.style;
  const patchStyle = (partial: Partial<BlueprintDraft['style']>) =>
    onPatch({ style: { ...style, ...partial } });
  return (
    <div className="grid gap-5 md:grid-cols-2">
      <div>
        <p className={labelClass}>팔레트</p>
        <div className="space-y-2">
          {Object.entries(style.palette).map(([k, v]) => (
            <div key={k} className="flex items-center gap-2">
              <input
                aria-label={`palette ${k}`}
                type="color"
                value={v}
                onChange={(e) => patchStyle({ palette: { ...style.palette, [k]: e.target.value.toUpperCase() } })}
                className="h-7 w-9 cursor-pointer rounded border border-zinc-200"
              />
              <span className="w-20 text-[12.5px] text-zinc-600">{k}</span>
              <input
                aria-label={`palette ${k} hex`}
                value={v}
                onChange={(e) => patchStyle({ palette: { ...style.palette, [k]: e.target.value } })}
                className={`${inputClass} w-28 font-mono`}
              />
            </div>
          ))}
        </div>
      </div>
      <div>
        <p className={labelClass}>크기 체계 (pt)</p>
        <div className="grid grid-cols-2 gap-2">
          {REQUIRED_SIZE_KEYS.map((k) => (
            <label key={k} className="text-[12.5px] text-zinc-600">
              {k}
              <input
                aria-label={`size ${k}`}
                type="number"
                min={1}
                step={0.5}
                value={style.sizes[k] ?? ''}
                onChange={(e) => patchStyle({ sizes: { ...style.sizes, [k]: Number(e.target.value) } })}
                className={`${inputClass} mt-1 w-full`}
              />
            </label>
          ))}
        </div>
        <p className={`${labelClass} mt-4`}>표 스타일</p>
        <div className="flex flex-wrap items-center gap-3 text-[12.5px] text-zinc-600">
          <label>
            헤더 배경
            <input
              aria-label="table header_bg"
              value={style.table_style.header_bg}
              onChange={(e) => patchStyle({ table_style: { ...style.table_style, header_bg: e.target.value } })}
              className={`${inputClass} ml-1 w-24 font-mono`}
            />
          </label>
          <label>
            헤더 글자
            <input
              aria-label="table header_text"
              value={style.table_style.header_text}
              onChange={(e) => patchStyle({ table_style: { ...style.table_style, header_text: e.target.value } })}
              className={`${inputClass} ml-1 w-24 font-mono`}
            />
          </label>
          <label>
            테두리
            <input
              aria-label="table border"
              value={style.table_style.border}
              onChange={(e) => patchStyle({ table_style: { ...style.table_style, border: e.target.value } })}
              className={`${inputClass} ml-1 w-24 font-mono`}
            />
          </label>
          <label className="flex items-center gap-1">
            <input
              type="checkbox"
              checked={style.table_style.zebra}
              onChange={(e) => patchStyle({ table_style: { ...style.table_style, zebra: e.target.checked } })}
            />
            줄무늬(zebra)
          </label>
        </div>
        <p className={`${labelClass} mt-4`}>헤더/푸터</p>
        <div className="grid grid-cols-2 gap-2">
          <select
            aria-label="logo_asset_id"
            value={style.header_footer.logo_asset_id ?? ''}
            onChange={(e) =>
              patchStyle({
                header_footer: { ...style.header_footer, logo_asset_id: e.target.value || null },
              })
            }
            className={`${inputClass} col-span-2`}
          >
            <option value="">로고 없음</option>
            {draft.assets
              .filter((a) => a.adopted)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {ASSET_KIND_LABELS[a.kind]} · {a.id}
                </option>
              ))}
          </select>
          <input
            aria-label="page_number_format"
            placeholder="{n} / {total}"
            value={style.header_footer.page_number_format}
            onChange={(e) =>
              patchStyle({ header_footer: { ...style.header_footer, page_number_format: e.target.value } })
            }
            className={inputClass}
          />
          <input
            aria-label="footer_text"
            placeholder="푸터 문구"
            value={style.header_footer.footer_text}
            onChange={(e) =>
              patchStyle({ header_footer: { ...style.header_footer, footer_text: e.target.value } })
            }
            className={inputClass}
          />
        </div>
      </div>
    </div>
  );
};

// ── 페이지 패턴 ──────────────────────────────────────────

const PatternsTab = ({
  draft,
  pageThumbnails,
  excluded,
  onToggleExclude,
  onPatch,
}: TabProps & {
  pageThumbnails: (string | null)[];
  excluded: string[];
  onToggleExclude: (id: string) => void;
}) => {
  const patchPattern = (id: string, partial: Partial<BlueprintPattern>) =>
    onPatch({ patterns: draft.patterns.map((p) => (p.id === id ? { ...p, ...partial } : p)) });
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {draft.patterns.map((p) => {
        const thumb = pageThumbnails[p.sample_page - 1];
        const isExcluded = excluded.includes(p.id);
        return (
          <article
            key={p.id}
            className={`rounded-xl border border-zinc-200 p-3 ${isExcluded ? 'opacity-50' : ''}`}
            data-testid={`pattern-card-${p.id}`}
            data-excluded={isExcluded ? 'true' : 'false'}
          >
            <div className="flex items-center justify-between">
              <span className="text-[12.5px] font-semibold text-zinc-700">
                p.{p.sample_page} · {p.id}
              </span>
              {p.kind === 'unknown' && (
                <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[10.5px] text-amber-700">
                  분류 실패
                </span>
              )}
            </div>
            {thumb && (
              <img
                src={`data:image/png;base64,${thumb}`}
                alt={`페이지 ${p.sample_page} 썸네일`}
                className="mt-2 w-full rounded border border-zinc-100"
              />
            )}
            <select
              aria-label={`pattern ${p.id} kind`}
              value={p.kind}
              onChange={(e) => patchPattern(p.id, { kind: e.target.value as PatternKind })}
              className={`${inputClass} mt-2 w-full`}
            >
              {PATTERN_KINDS.map((k) => (
                <option key={k} value={k}>
                  {PATTERN_KIND_LABELS[k]}
                </option>
              ))}
            </select>
            <ul className="mt-2 space-y-0.5 text-[11.5px] text-zinc-500">
              {p.slots.map((s) => (
                <li key={s.id}>
                  {s.id} · {SLOT_KIND_LABELS[s.kind]} · {s.role}
                  {s.max_chars ? ` · ≤${s.max_chars}자` : ''}
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => onToggleExclude(p.id)}
              aria-pressed={isExcluded}
              className={`mt-2 text-[11.5px] hover:underline ${isExcluded ? 'text-emerald-700' : 'text-red-600'}`}
            >
              {isExcluded ? '제외 취소' : '패턴 제외'}
            </button>
          </article>
        );
      })}
    </div>
  );
};

// ── 서사 ─────────────────────────────────────────────────

const NarrativeTab = ({ draft, onPatch }: TabProps) => {
  const n = draft.narrative;
  const patchN = (partial: Partial<BlueprintDraft['narrative']>) =>
    onPatch({ narrative: { ...n, ...partial } });
  const patchSection = (i: number, partial: Partial<NarrativeSection>) =>
    patchN({ sections: n.sections.map((s, idx) => (idx === i ? { ...s, ...partial } : s)) });
  const move = (i: number, delta: -1 | 1) => {
    const j = i + delta;
    if (j < 0 || j >= n.sections.length) return;
    const next = [...n.sections];
    [next[i], next[j]] = [next[j], next[i]];
    patchN({ sections: next });
  };
  return (
    <div className="space-y-3">
      <div className="flex gap-3">
        <label className="text-[12.5px] text-zinc-600">
          문체(tone)
          <input
            aria-label="tone"
            value={n.tone}
            onChange={(e) => patchN({ tone: e.target.value })}
            className={`${inputClass} ml-1 w-56`}
          />
        </label>
        <label className="text-[12.5px] text-zinc-600">
          언어
          <select
            aria-label="language"
            value={n.language}
            onChange={(e) => patchN({ language: e.target.value })}
            className={`${inputClass} ml-1`}
          >
            <option value="ko">ko</option>
            <option value="en">en</option>
          </select>
        </label>
      </div>
      {n.sections.map((s, i) => (
        <div key={i} className="grid gap-2 rounded-xl border border-zinc-200 p-3 md:grid-cols-[1fr_2fr_2fr_auto]">
          <input
            aria-label={`section ${i} role`}
            value={s.role}
            placeholder="역할"
            onChange={(e) => patchSection(i, { role: e.target.value })}
            className={inputClass}
          />
          <select
            aria-label={`section ${i} patterns`}
            multiple
            value={s.pattern_ids}
            onChange={(e) =>
              patchSection(i, {
                pattern_ids: Array.from(e.target.selectedOptions).map((o) => o.value),
              })
            }
            className={`${inputClass} h-20`}
          >
            {draft.patterns.map((p) => (
              <option key={p.id} value={p.id}>
                {p.id} · {PATTERN_KIND_LABELS[p.kind]}
              </option>
            ))}
          </select>
          <textarea
            aria-label={`section ${i} guidance`}
            value={s.guidance}
            placeholder="내용 지침"
            onChange={(e) => patchSection(i, { guidance: e.target.value })}
            className={`${inputClass} h-20`}
          />
          <div className="flex flex-col gap-1 text-[11.5px]">
            <button type="button" onClick={() => move(i, -1)} className="text-zinc-500">
              ↑
            </button>
            <button type="button" onClick={() => move(i, 1)} className="text-zinc-500">
              ↓
            </button>
            <button
              type="button"
              onClick={() => patchN({ sections: n.sections.filter((_, idx) => idx !== i) })}
              className="text-red-600"
            >
              삭제
            </button>
          </div>
        </div>
      ))}
      <button
        type="button"
        onClick={() => patchN({ sections: [...n.sections, { role: '', pattern_ids: [], guidance: '' }] })}
        className="rounded-lg border border-zinc-200 px-3 py-1.5 text-[12.5px] text-zinc-700 hover:bg-zinc-50"
      >
        + 섹션 추가
      </button>
    </div>
  );
};

// ── 폰트 매핑 ────────────────────────────────────────────

const FontMappingTab = ({ draft, onPatch }: TabProps) => {
  const fonts = useBlueprintFonts();
  const installed = fonts.data?.installed ?? [];
  return (
    <div className="space-y-2">
      {fonts.isError && (
        <p role="alert" className="text-[12.5px] text-red-600">
          {fonts.error.message}
        </p>
      )}
      {Object.entries(draft.font_mapping).map(([src, target]) => {
        const missing = installed.length > 0 && !installed.includes(target);
        return (
          <div key={src} className="flex items-center gap-3 text-[12.5px]">
            <span className="w-48 truncate text-zinc-700" title={src}>
              {src}
            </span>
            <span className="text-zinc-400">→</span>
            <select
              aria-label={`font ${src}`}
              value={target}
              onChange={(e) => onPatch({ font_mapping: { ...draft.font_mapping, [src]: e.target.value } })}
              className={inputClass}
            >
              {!installed.includes(target) && <option value={target}>{target}</option>}
              {installed.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
            {missing && (
              <span title="서버에 설치되지 않은 폰트" className="text-amber-600">
                ⚠ 미설치
              </span>
            )}
          </div>
        );
      })}
      {fonts.data && (
        <p className="text-[11.5px] text-zinc-400">기본 폰트: {fonts.data.default}</p>
      )}
    </div>
  );
};

// ── 에셋 ─────────────────────────────────────────────────

const AssetsTab = ({ draft, assets, onPatch }: TabProps & { assets: AssetPreview[] }) => {
  const previews = new Map(assets.map((a) => [a.id, a]));
  const patchAsset = (id: string, partial: { kind?: AssetKind; adopted?: boolean }) =>
    onPatch({ assets: draft.assets.map((a) => (a.id === id ? { ...a, ...partial } : a)) });
  if (draft.assets.length === 0) {
    return <p className="text-[12.5px] text-zinc-400">반복 이미지(로고·장식·표지)가 없습니다.</p>;
  }
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {draft.assets.map((a) => {
        const thumb = previews.get(a.id)?.thumbnail_b64;
        return (
          <article key={a.id} className="rounded-xl border border-zinc-200 p-3">
            {thumb ? (
              <img src={`data:${a.mime};base64,${thumb}`} alt={`${ASSET_KIND_LABELS[a.kind]} 에셋`} className="h-16 object-contain" />
            ) : (
              <div className="h-16 rounded bg-zinc-100 text-center text-[11px] leading-[4rem] text-zinc-400">
                {a.width}×{a.height}
              </div>
            )}
            <div className="mt-2 flex items-center gap-2 text-[12.5px]">
              <select
                aria-label={`asset ${a.id} kind`}
                value={a.kind}
                onChange={(e) => patchAsset(a.id, { kind: e.target.value as AssetKind })}
                className={inputClass}
              >
                {ASSET_KINDS.map((k) => (
                  <option key={k} value={k}>
                    {ASSET_KIND_LABELS[k]}
                  </option>
                ))}
              </select>
              <label className="flex items-center gap-1 text-zinc-600">
                <input
                  type="checkbox"
                  aria-label={`asset ${a.id} adopted`}
                  checked={a.adopted}
                  onChange={(e) => patchAsset(a.id, { adopted: e.target.checked })}
                />
                채택
              </label>
            </div>
          </article>
        );
      })}
    </div>
  );
};

// ── 경고 ─────────────────────────────────────────────────

const WarningsTab = ({ warnings }: { warnings: string[] }) =>
  warnings.length === 0 ? (
    <p className="text-[12.5px] text-zinc-400">경고가 없습니다.</p>
  ) : (
    <ul className="list-disc space-y-1 pl-5 text-[12.5px] text-amber-700">
      {warnings.map((w, i) => (
        <li key={i}>{w}</li>
      ))}
    </ul>
  );

export default BlueprintTabs;
