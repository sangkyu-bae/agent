// Design Ref: ui-redesign-chat §5.4 — 출처 칩. 위키 출처는 warning 톤, 문서 출처는 중립 톤 + hover brand.
// Design Ref: agent-run-source-citations §5.4 — 에이전트 근거 4종, 문서·도구 발췌 패널, 웹 외부 링크.
import { useId, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, ExternalLink, FileText, Globe, Wrench } from 'lucide-react';

import { SOURCE_KIND, type DocumentSource, type SourceKind } from '@/types/chat';
import { cn } from '@/utils/cn';
import { isSafeHttpUrl } from '@/utils/safeUrl';

interface SourceCitationProps {
  sources: DocumentSource[];
}

const KIND_LABEL: Record<SourceKind, string> = {
  document: '문서',
  wiki: '위키',
  web: '웹',
  mcp: '도구',
};

const KIND_ICON = {
  document: FileText,
  wiki: BookOpen,
  web: Globe,
  mcp: Wrench,
} as const;

const CHIP =
  'inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors duration-150';
const NEUTRAL_CHIP = `${CHIP} border-border bg-surface-muted text-fg-muted`;
const INTERACTIVE_CHIP = `${NEUTRAL_CHIP} hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700`;
const WIKI_CHIP = `${CHIP} border-warning-border bg-warning-bg text-warning hover:bg-warning-border/60`;
const ICON = 'h-3.5 w-3.5 shrink-0';

const knowledgePath = (id: string) => `/knowledge/${encodeURIComponent(id)}`;

const Score = ({ score, className }: { score?: number; className?: string }) =>
  typeof score === 'number' ? (
    <span className={cn('font-semibold', className)}>{Math.round(score * 100)}%</span>
  ) : null;

const ChipBody = ({ source, kind }: { source: DocumentSource; kind: SourceKind }) => {
  const Icon = KIND_ICON[kind];
  return (
    <>
      <Icon className={ICON} strokeWidth={1.75} aria-hidden="true" />
      <span className="font-medium">{KIND_LABEL[kind]}</span>
      <span className="max-w-48 truncate">{source.source}</span>
    </>
  );
};

/** 일반 채팅(kind 없음) 출처는 기존 표시를 유지한다. */
const LegacyWikiChip = ({ source }: { source: DocumentSource }) => {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(knowledgePath(source.chunk_id))} className={WIKI_CHIP}>
      <BookOpen className={ICON} strokeWidth={1.75} aria-hidden="true" />
      <span>위키 근거</span>
      <Score score={source.score} />
    </button>
  );
};

const AgentWikiChip = ({ source }: { source: DocumentSource }) => {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(knowledgePath(source.chunk_id))} className={WIKI_CHIP}>
      <ChipBody source={source} kind={SOURCE_KIND.WIKI} />
    </button>
  );
};

const WebChip = ({ source }: { source: DocumentSource }) =>
  isSafeHttpUrl(source.url) ? (
    <a href={source.url} target="_blank" rel="noopener noreferrer" className={INTERACTIVE_CHIP}>
      <ChipBody source={source} kind={SOURCE_KIND.WEB} />
      <ExternalLink className={ICON} strokeWidth={1.75} aria-hidden="true" />
    </a>
  ) : (
    <span className={NEUTRAL_CHIP}>
      <ChipBody source={source} kind={SOURCE_KIND.WEB} />
    </span>
  );

interface ExcerptChipProps {
  source: DocumentSource;
  index: number;
  isOpen: boolean;
  panelId: string;
  onToggle: () => void;
}

const Ordinal = ({ index }: { index: number }) => (
  <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-xs font-semibold text-fg-subtle">
    {index + 1}
  </span>
);

/** 문서·도구 칩 — 발췌가 있으면 패널을 여닫는 버튼, 없으면 표시만 한다. */
const ExcerptChip = ({ source, index, isOpen, panelId, onToggle }: ExcerptChipProps) => {
  const body = source.kind ? (
    <>
      {/* Design §5.4 — 에이전트 문서 칩도 일반 채팅처럼 순번을 단다 */}
      {source.kind === SOURCE_KIND.DOCUMENT && <Ordinal index={index} />}
      <ChipBody source={source} kind={source.kind} />
    </>
  ) : (
    <>
      <Ordinal index={index} />
      <span className="max-w-36 truncate">{source.source}</span>
      <Score score={source.score} className="text-brand-600" />
    </>
  );
  if (!source.content.trim()) return <span className={NEUTRAL_CHIP}>{body}</span>;
  return (
    <button
      type="button"
      aria-expanded={isOpen}
      // 패널은 열린 칩 하나만 렌더되므로 그 칩만 패널을 가리킨다.
      aria-controls={isOpen ? panelId : undefined}
      onClick={onToggle}
      className={cn(INTERACTIVE_CHIP, isOpen && 'border-brand-200 bg-brand-50 text-brand-700')}
    >
      {body}
    </button>
  );
};

const resolveKind = (source: DocumentSource): SourceKind | 'legacyWiki' | 'legacyDocument' => {
  if (source.kind) return source.kind;
  return source.source === 'wiki' ? 'legacyWiki' : 'legacyDocument';
};

const SourceCitation = ({ sources }: SourceCitationProps) => {
  const [openKey, setOpenKey] = useState<string | null>(null);
  const panelId = useId();

  if (sources.length === 0) return null;

  const keyOf = (source: DocumentSource, idx: number) => `${source.kind ?? 'legacy'}:${source.chunk_id}:${idx}`;
  const opened = sources.find((s, idx) => keyOf(s, idx) === openKey);

  return (
    <div className="mt-4 border-t border-border pt-3">
      <p className="mb-2 text-xs font-medium text-fg-subtle">참고 문서</p>
      <div className="flex flex-wrap gap-2">
        {sources.map((source, idx) => {
          const key = keyOf(source, idx);
          const kind = resolveKind(source);
          if (kind === 'legacyWiki') return <LegacyWikiChip key={key} source={source} />;
          if (kind === SOURCE_KIND.WIKI) return <AgentWikiChip key={key} source={source} />;
          if (kind === SOURCE_KIND.WEB) return <WebChip key={key} source={source} />;
          return (
            <ExcerptChip
              key={key}
              source={source}
              index={idx}
              isOpen={openKey === key}
              panelId={panelId}
              onToggle={() => setOpenKey(openKey === key ? null : key)}
            />
          );
        })}
      </div>
      {opened && (
        <div
          id={panelId}
          role="region"
          aria-label={`${opened.source} 발췌`}
          className="mt-3 max-h-60 overflow-y-auto rounded-md border border-border bg-surface-muted p-3 text-sm text-fg-secondary"
        >
          {/* 발췌는 텍스트 노드로만 렌더한다 — HTML·마크다운 미해석 (Design §7) */}
          <p className="whitespace-pre-wrap break-words">{opened.content}</p>
        </div>
      )}
    </div>
  );
};

export default SourceCitation;
