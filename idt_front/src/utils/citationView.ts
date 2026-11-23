// Design Ref: answer-citation-verification §5.3 — 메시지 근거를 인용 화면용으로 나눈다(순수 계산).
// 설계서의 useCitationView 훅을 순수 함수로 둔다 — 상태가 없어 훅이 필요 없다(Do module-8).
import {
  CITATION_STATUS,
  SOURCE_KIND,
  type CitationStatus,
  type DocumentSource,
  type SourceCitationEntry,
} from '@/types/chat';

export interface CitationRow {
  no: number;
  entry: SourceCitationEntry;
  /** 이 인용이 속한 문서 칩 */
  source: DocumentSource;
}

export interface CitationView {
  /** null 이면 인용 정보가 없는 메시지 — 기존 칩 렌더 */
  status: CitationStatus | null;
  rows: CitationRow[];
  /** 검색했지만 답변에 쓰지 않은 문서(none 이면 검색된 문서 전부) */
  unused: DocumentSource[];
  /** 문서가 아닌 칩(웹·위키·도구) 등 인용과 무관한 근거 */
  others: DocumentSource[];
}

const isCitedDocument = (s: DocumentSource) => s.kind === SOURCE_KIND.DOCUMENT && !!s.citation;

export const buildCitationView = (sources: DocumentSource[]): CitationView => {
  const documents = sources.filter(isCitedDocument);
  const others = sources.filter((s) => !isCitedDocument(s));
  if (documents.length === 0) return { status: null, rows: [], unused: [], others };

  const status = documents[0].citation!.status;
  const seen = new Set<number>();
  const rows: CitationRow[] = [];
  const unused: DocumentSource[] = [];
  documents.forEach((source) => {
    const entries = status === CITATION_STATUS.VERIFIED ? (source.citation?.entries ?? []) : [];
    if (entries.length === 0) unused.push(source);
    entries.forEach((entry) => {
      if (seen.has(entry.no)) return;
      seen.add(entry.no);
      rows.push({ no: entry.no, entry, source });
    });
  });
  rows.sort((a, b) => a.no - b.no);
  return { status, rows, unused, others };
};
