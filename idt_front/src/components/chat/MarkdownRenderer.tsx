import { memo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import { FileText } from 'lucide-react';
import { documentExtractorService } from '@/services/documentExtractorService';
import { useExcelPreviewStore } from '@/store/excelPreviewStore';
import { EXCEL_PREVIEW_TRIGGER } from '@/types/excelPreview';

interface MarkdownRendererProps {
  content: string;
}

// document-template-extractor GB3: 산출 파일 링크는 JWT가 필요해
// <a href> 직행 대신 인증 클라이언트로 blob 다운로드한다.
const DOC_EXTRACTOR_FILE_PREFIX = '/api/v1/document-extractor/files/';

const extractText = (children: unknown): string =>
  typeof children === 'string'
    ? children
    : Array.isArray(children)
      ? children.filter((c) => typeof c === 'string').join('')
      : '';

// Design Ref: ui-redesign-chat §5.4 — 어시스턴트 본문 톤(text-md leading-[1.7] text-fg)에 맞춘 요소 매핑. 로직 변경 없음.
const components: Components = {
  h1: ({ children }) => (
    <h1 className="mb-3 mt-5 text-xl font-bold text-fg first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2.5 mt-5 text-lg font-bold text-fg first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 mt-4 text-md font-semibold text-fg first:mt-0">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="mb-2 mt-3 text-base font-semibold text-fg first:mt-0">{children}</h4>
  ),
  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="leading-[1.7]">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-4 border-brand-200 pl-4 text-fg-muted last:mb-0">
      {children}
    </blockquote>
  ),
  // 인라인 코드 스타일. 블록 코드는 pre 의 [&>code] reset 으로 무효화됨
  code: ({ children }) => (
    <code className="rounded-md bg-surface-sunken px-1.5 py-0.5 font-mono text-sm text-fg-secondary">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="mb-3 overflow-x-auto rounded-xl bg-fg p-4 font-mono text-sm leading-relaxed text-surface-sunken last:mb-0 [&>code]:bg-transparent [&>code]:p-0 [&>code]:text-inherit">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto last:mb-0">
      <table className="min-w-full border-collapse text-base">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-surface-muted">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-border px-3 py-2 text-left font-semibold text-fg">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border px-3 py-2">{children}</td>,
  a: ({ href, children }) => {
    if (href?.startsWith(DOC_EXTRACTOR_FILE_PREFIX)) {
      const fileId = href.slice(DOC_EXTRACTOR_FILE_PREFIX.length);
      const filename = extractText(children);
      // excel-preview Design §5.3: .xlsx 판별은 링크 텍스트(=파일명) 확장자.
      // 모달 상태는 스토어가 소유 — 여기서는 open()만 호출 (memo 트리 밖).
      const isXlsx = /\.xlsx$/i.test(filename);
      const openPreview = () =>
        useExcelPreviewStore.getState().open({ fileId, filename });
      const download = () =>
        void documentExtractorService.downloadGeneratedFile(fileId, filename);
      // FR-09: 'link' 모드면 링크 클릭=프리뷰, 다운로드는 모달 안에서만
      const linkOpensPreview = isXlsx && EXCEL_PREVIEW_TRIGGER === 'link';
      return (
        <>
          <a
            href={href}
            onClick={(e) => {
              e.preventDefault();
              if (linkOpensPreview) {
                openPreview();
              } else {
                download();
              }
            }}
            className="inline-flex items-center gap-1 font-medium text-brand-600 underline underline-offset-2 hover:text-brand-700"
          >
            <FileText className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
            {children}
          </a>
          {isXlsx && EXCEL_PREVIEW_TRIGGER === 'button' && (
            <button
              type="button"
              aria-label={`${filename} 미리보기`}
              onClick={openPreview}
              className="ml-1.5 inline-flex items-center rounded-md border border-brand-200 bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700 transition-colors duration-150 hover:bg-brand-100"
            >
              미리보기
            </button>
          )}
        </>
      );
    }
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium text-brand-600 underline underline-offset-2 hover:text-brand-700"
      >
        {children}
      </a>
    );
  },
  hr: () => <hr className="my-4 border-border" />,
  strong: ({ children }) => <strong className="font-semibold text-fg">{children}</strong>,
};

const MarkdownRenderer = ({ content }: MarkdownRendererProps) => (
  <div className="min-w-0">
    <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={components}>
      {content}
    </ReactMarkdown>
  </div>
);

/** 스트리밍 중 완료된 과거 메시지의 재파싱 차단 — content 동일 시 재렌더 생략 */
export default memo(MarkdownRenderer);
