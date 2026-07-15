import { useState } from 'react';
import { useKbDocumentSummary } from '@/hooks/useKnowledgeBases';
import type {
  KbDocumentInfo,
  KbStoreSource,
} from '@/types/knowledgeBase';
import KbChunkList from './KbChunkList';
import KbPayloadMeta from './KbPayloadMeta';
import KbSectionSummaryList from './KbSectionSummaryList';

interface KbDocumentContentPanelProps {
  kbId: string;
  document: KbDocumentInfo;
  onClose: () => void;
}

type ContentTab = 'summary' | 'sections' | 'chunks';

const TABS: { key: ContentTab; label: string }[] = [
  { key: 'summary', label: '문서 요약' },
  { key: 'sections', label: '섹션 요약' },
  { key: 'chunks', label: '청크' },
];

const SOURCES: { key: KbStoreSource; label: string }[] = [
  { key: 'qdrant', label: 'Qdrant' },
  { key: 'es', label: 'Elasticsearch' },
];

const DocumentSummaryView = ({
  kbId,
  documentId,
  source,
}: {
  kbId: string;
  documentId: string;
  source: KbStoreSource;
}) => {
  const summaryQuery = useKbDocumentSummary(kbId, documentId, source);

  if (summaryQuery.isLoading) {
    return (
      <p className="py-8 text-center text-[14px] text-zinc-400">
        문서 요약을 불러오는 중...
      </p>
    );
  }
  if (summaryQuery.isError) {
    return (
      <div className="py-8 text-center">
        <p className="text-[14px] text-red-500">
          문서 요약을 불러오지 못했습니다
        </p>
        <button
          type="button"
          onClick={() => summaryQuery.refetch()}
          className="mt-3 rounded-xl border border-zinc-200 px-4 py-2 text-[13px] font-medium text-zinc-600 hover:bg-zinc-50"
        >
          다시 시도
        </button>
      </div>
    );
  }

  const data = summaryQuery.data;
  if (!data) return null;

  if (!data.exists) {
    return (
      <p className="py-8 text-center text-[14px] text-zinc-400">
        문서 요약이 아직 생성되지 않았습니다
      </p>
    );
  }

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4">
      <p className="whitespace-pre-wrap text-[13.5px] leading-[1.7] text-zinc-700">
        {data.summary_text}
      </p>
      {data.keywords.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {data.keywords.map((kw) => (
            <span
              key={kw}
              className="rounded-md bg-violet-50 px-1.5 py-0.5 text-[11px] font-medium text-violet-600"
            >
              {kw}
            </span>
          ))}
        </div>
      )}
      {data.section_count !== null && data.section_count !== undefined && (
        <p className="mt-2 text-[12px] text-zinc-400">
          섹션 {data.section_count}개 기반 요약
        </p>
      )}
      <KbPayloadMeta metadata={data.metadata} />
    </div>
  );
};

/** KB 문서 저장 내용 3계층 드릴다운 패널 (kb-content-browser Design §5.3).
 *  저장소 토글(D2)은 패널 레벨 상태로 3탭이 공유한다. */
const KbDocumentContentPanel = ({
  kbId,
  document,
  onClose,
}: KbDocumentContentPanelProps) => {
  const [source, setSource] = useState<KbStoreSource>('qdrant');
  const [tab, setTab] = useState<ContentTab>('summary');

  return (
    <div className="mt-4 rounded-2xl border border-violet-200 bg-violet-50/30 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-[15px] font-semibold text-zinc-900">
            📄 {document.filename} — 저장 내용
          </h3>
          <p className="mt-0.5 text-[12px] text-zinc-400">
            청크 {document.chunk_count}개 · {document.chunking_strategy}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="저장 내용 패널 닫기"
          className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-600"
        >
          ✕
        </button>
      </div>

      {/* 저장소 토글 (D2 — 사용자 선택으로 ES/Qdrant 나눠서 확인) */}
      <div
        role="group"
        aria-label="저장소 선택"
        className="mt-3 inline-flex rounded-xl border border-zinc-200 bg-white p-0.5"
      >
        {SOURCES.map((s) => (
          <button
            key={s.key}
            type="button"
            aria-pressed={source === s.key}
            onClick={() => setSource(s.key)}
            className={`rounded-[10px] px-3.5 py-1.5 text-[12.5px] font-medium transition-colors ${
              source === s.key
                ? 'bg-violet-600 text-white'
                : 'text-zinc-500 hover:text-zinc-700'
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* 탭 */}
      <div role="tablist" className="mt-4 flex gap-1 border-b border-zinc-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`px-3.5 py-2 text-[13.5px] font-medium transition-colors ${
              tab === t.key
                ? 'border-b-2 border-violet-600 text-violet-700'
                : 'text-zinc-400 hover:text-zinc-600'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mt-4">
        {tab === 'summary' && (
          <DocumentSummaryView
            kbId={kbId}
            documentId={document.document_id}
            source={source}
          />
        )}
        {tab === 'sections' && (
          <KbSectionSummaryList
            kbId={kbId}
            documentId={document.document_id}
            source={source}
          />
        )}
        {tab === 'chunks' && (
          <KbChunkList
            kbId={kbId}
            documentId={document.document_id}
            source={source}
          />
        )}
      </div>
    </div>
  );
};

export default KbDocumentContentPanel;
