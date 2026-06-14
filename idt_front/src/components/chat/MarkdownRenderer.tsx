import { memo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';

interface MarkdownRendererProps {
  content: string;
}

/** 어시스턴트 말풍선 디자인 톤(text-[15px] leading-[1.8] zinc-800)에 맞춘 요소 매핑 */
const components: Components = {
  h1: ({ children }) => (
    <h1 className="mb-3 mt-5 text-xl font-bold text-zinc-900 first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2.5 mt-5 text-lg font-bold text-zinc-900 first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-2 mt-4 text-base font-semibold text-zinc-900 first:mt-0">{children}</h3>
  ),
  h4: ({ children }) => (
    <h4 className="mb-2 mt-3 text-[15px] font-semibold text-zinc-900 first:mt-0">{children}</h4>
  ),
  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="leading-[1.7]">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="mb-3 border-l-4 border-violet-200 pl-4 text-zinc-600 last:mb-0">
      {children}
    </blockquote>
  ),
  // 인라인 코드 스타일. 블록 코드는 pre 의 [&>code] reset 으로 무효화됨
  code: ({ children }) => (
    <code className="rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[13px] text-rose-600">
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="mb-3 overflow-x-auto rounded-xl bg-zinc-900 p-4 font-mono text-[13px] leading-relaxed text-zinc-100 last:mb-0 [&>code]:bg-transparent [&>code]:p-0 [&>code]:text-inherit">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto last:mb-0">
      <table className="min-w-full border-collapse text-[14px]">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-zinc-50">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-zinc-200 px-3 py-2 text-left font-semibold text-zinc-900">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="border border-zinc-200 px-3 py-2">{children}</td>,
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-violet-600 underline underline-offset-2 hover:text-violet-700"
    >
      {children}
    </a>
  ),
  hr: () => <hr className="my-4 border-zinc-200" />,
  strong: ({ children }) => <strong className="font-semibold text-zinc-900">{children}</strong>,
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
