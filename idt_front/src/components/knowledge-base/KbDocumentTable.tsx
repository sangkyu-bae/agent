import { Fragment, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  Link2,
  Pencil,
  Trash2,
  Undo2,
} from "lucide-react";
import Badge from "@/components/ui/Badge";
import IconButton from "@/components/ui/IconButton";
import type { KbDocumentInfo } from "@/types/knowledgeBase";
import DocumentVersionHistory from "./DocumentVersionHistory";

interface KbDocumentTableProps {
  documents: KbDocumentInfo[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  /** 행 클릭 → 저장 내용 드릴다운 (kb-content-browser) */
  onRowClick?: (doc: KbDocumentInfo) => void;
  selectedId?: string | null;
  /** 문서 단위 검색 스코프 지정 (kb-retrieval-test D10) — 드릴다운과 독립 */
  onSearchInDocument?: (doc: KbDocumentInfo) => void;
  /** 문서 삭제 (kb-document-management FR-10) — can_delete 행에만 노출 */
  onDeleteDocument?: (doc: KbDocumentInfo) => void;
  // document-revision §5.1 — 버전 이력 펼침(kbId 필요)과 개정 관리 버튼(콜백이 있을 때만)
  kbId?: string;
  onRollback?: (doc: KbDocumentInfo) => void;
  onLink?: (doc: KbDocumentInfo) => void;
  onEditMeta?: (doc: KbDocumentInfo) => void;
}

const versionText = (doc: KbDocumentInfo) => {
  const no = doc.version_no ?? 1;
  return doc.version_label ? `v${no} · ${doc.version_label}` : `v${no}`;
};

const ICON = {
  className: "h-4 w-4",
  strokeWidth: 1.75,
  "aria-hidden": true,
} as const;

const STRATEGY_LABELS: Record<string, string> = {
  parent_child: "기본",
  clause_aware: "조항 단위",
};

const KbDocumentTable = ({
  documents,
  isLoading,
  isError,
  onRetry,
  onRowClick,
  selectedId,
  onSearchInDocument,
  onDeleteDocument,
  kbId,
  onRollback,
  onLink,
  onEditMeta,
}: KbDocumentTableProps) => {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const hasRevisionActions = !!(onRollback || onLink || onEditMeta);
  const showManage = !!onDeleteDocument || hasRevisionActions;
  const columnCount = 5 + (onSearchInDocument ? 1 : 0) + (showManage ? 1 : 0);

  if (isLoading) {
    return (
      <p className="py-10 text-center text-[14px] text-zinc-400">
        문서 목록을 불러오는 중...
      </p>
    );
  }

  if (isError) {
    return (
      <div className="py-10 text-center">
        <p className="text-[14px] text-red-500">
          문서 목록을 불러오지 못했습니다
        </p>
        <button
          onClick={onRetry}
          className="mt-3 rounded-xl border border-zinc-200 px-4 py-2 text-[13px] font-medium text-zinc-600 hover:bg-zinc-50"
        >
          다시 시도
        </button>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <p className="py-10 text-center text-[14px] text-zinc-400">
        아직 업로드된 문서가 없습니다. 문서를 업로드해보세요.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-zinc-200">
      <table className="w-full text-left text-[14px]">
        <thead className="bg-zinc-50 text-[12px] text-zinc-500">
          <tr>
            <th className="px-4 py-3 font-medium">파일명</th>
            <th className="px-4 py-3 font-medium">버전</th>
            <th className="px-4 py-3 font-medium">청크 수</th>
            <th className="px-4 py-3 font-medium">청킹 방식</th>
            <th className="px-4 py-3 font-medium">업로드일</th>
            {onSearchInDocument && (
              <th className="px-4 py-3 font-medium">검색</th>
            )}
            {showManage && <th className="px-4 py-3 font-medium">관리</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100">
          {documents.map((doc) => {
            const expanded = expandedId === doc.document_id;
            const canExpand = !!kbId && !!doc.has_history;
            return (
              <Fragment key={doc.document_id}>
                <tr
                  onClick={() => onRowClick?.(doc)}
                  aria-selected={selectedId === doc.document_id}
                  className={`${onRowClick ? "cursor-pointer" : ""} ${
                    selectedId === doc.document_id
                      ? "bg-violet-50/70"
                      : "hover:bg-zinc-50/60"
                  }`}
                >
                  <td className="px-4 py-3 font-medium text-zinc-800">
                    {doc.filename}
                  </td>
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-1">
                      <Badge
                        tone={(doc.version_no ?? 1) > 1 ? "brand" : "neutral"}
                      >
                        {versionText(doc)}
                      </Badge>
                      {canExpand && (
                        <IconButton
                          aria-label={`${doc.filename} 버전 이력`}
                          aria-expanded={expanded}
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedId(expanded ? null : doc.document_id);
                          }}
                        >
                          {expanded ? (
                            <ChevronDown {...ICON} />
                          ) : (
                            <ChevronRight {...ICON} />
                          )}
                        </IconButton>
                      )}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-zinc-500">{doc.chunk_count}</td>
                  <td className="px-4 py-3 text-zinc-500">
                    {STRATEGY_LABELS[doc.chunking_strategy] ??
                      doc.chunking_strategy}
                  </td>
                  <td className="px-4 py-3 text-zinc-500">
                    {doc.created_at ? doc.created_at.slice(0, 10) : "—"}
                  </td>
                  {onSearchInDocument && (
                    <td className="px-4 py-3">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSearchInDocument(doc);
                        }}
                        className="rounded-lg border border-zinc-200 px-2.5 py-1 text-[12px] text-zinc-500 transition-colors hover:border-violet-300 hover:text-violet-600"
                      >
                        이 문서에서 검색
                      </button>
                    </td>
                  )}
                  {showManage && (
                    <td className="px-4 py-3">
                      <span className="flex items-center gap-1">
                        {onRollback && (doc.version_no ?? 1) > 1 && (
                          <IconButton
                            aria-label={`${doc.filename} 개정 되돌리기`}
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              onRollback(doc);
                            }}
                          >
                            <Undo2 {...ICON} />
                          </IconButton>
                        )}
                        {onLink && !doc.lineage_id && (
                          <IconButton
                            aria-label={`${doc.filename} 대체한 문서 지정`}
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              onLink(doc);
                            }}
                          >
                            <Link2 {...ICON} />
                          </IconButton>
                        )}
                        {onEditMeta && (
                          <IconButton
                            aria-label={`${doc.filename} 버전 라벨 수정`}
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              onEditMeta(doc);
                            }}
                          >
                            <Pencil {...ICON} />
                          </IconButton>
                        )}
                        {onDeleteDocument && doc.can_delete && (
                          <IconButton
                            aria-label={`${doc.filename} 삭제`}
                            tone="danger"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              onDeleteDocument(doc);
                            }}
                          >
                            <Trash2
                              className="h-4 w-4"
                              strokeWidth={1.75}
                              aria-hidden
                            />
                          </IconButton>
                        )}
                      </span>
                    </td>
                  )}
                </tr>
                {expanded && canExpand && kbId && (
                  <tr>
                    <td
                      colSpan={columnCount}
                      className="bg-surface-muted px-6 py-3"
                    >
                      <DocumentVersionHistory
                        kbId={kbId}
                        documentId={doc.document_id}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default KbDocumentTable;
