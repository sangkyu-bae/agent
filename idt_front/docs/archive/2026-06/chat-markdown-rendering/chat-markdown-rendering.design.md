# Design: Chat Markdown Rendering

> Feature: `chat-markdown-rendering`
> Phase: Design
> Created: 2026-06-10
> Author: 배상규
> Ref Plan: `docs/01-plan/features/chat-markdown-rendering.plan.md`

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 어시스턴트 응답이 마크다운 원문 그대로 노출됨 (`MessageBubble.tsx`의 `<p whitespace-pre-wrap>`) |
| **Solution** | `MarkdownRenderer` 컴포넌트 신설 (react-markdown + remark-gfm + remark-breaks), `MessageBubble`의 어시스턴트 출력만 교체 |
| **Function (UX Effect)** | 제목/목록/표/코드블록/링크 서식 렌더링. WS 스트리밍 중 점진 렌더링, 완료 메시지는 memo로 재파싱 차단 |
| **Core Value** | 신규 1파일 + 수정 1파일의 최소 변경. raw HTML 미렌더(XSS 안전), 기존 Chart/Source 표시 무변경 |

---

## 1. 변경 파일 목록 및 변경 요약

| 파일 | 변경 유형 | 변경 요약 |
|------|----------|---------|
| `package.json` | 수정 | `react-markdown`, `remark-gfm`, `remark-breaks` 의존성 추가 |
| `src/components/chat/MarkdownRenderer.tsx` | 신규 | react-markdown 래퍼 + Tailwind components 매핑 |
| `src/components/chat/MarkdownRenderer.test.tsx` | 신규 | 렌더링/보안/스트리밍 안정성 테스트 10케이스 |
| `src/components/chat/MessageBubble.tsx` | 수정 | `AssistantMessage` 본문을 `MarkdownRenderer`로 교체, 커서 분리, `memo` 적용 |

> `MessageList`, `ChatPage/index.tsx`, `types/chat.ts`, 서비스/훅은 변경 없음.
> 백엔드 변경 없음 (프론트 전용).

---

## 2. 의존성 설계

```bash
npm install react-markdown remark-gfm remark-breaks
```

| 패키지 | 버전 | 역할 |
|--------|------|------|
| `react-markdown` | ^10 | 마크다운 → React 엘리먼트 (raw HTML 기본 미렌더 → XSS 안전) |
| `remark-gfm` | ^4 | GFM 확장: 표, 취소선, 체크리스트, 자동 링크 |
| `remark-breaks` | ^4 | 단일 개행 → `<br>` (기존 `whitespace-pre-wrap` 줄바꿈 동작 보존) |

**금지**: `rehype-raw` 추가 금지 — raw HTML 렌더링 경로를 열지 않는다.

---

## 3. MarkdownRenderer 설계 (`src/components/chat/MarkdownRenderer.tsx`)

### 3-1. 인터페이스

```typescript
interface MarkdownRendererProps {
  content: string;
}
```

### 3-2. 컴포넌트 본체

```tsx
import { memo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';

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
```

### 3-3. 설계 근거

| 결정 | 근거 |
|------|------|
| `components` 매핑 (typography 플러그인 미사용) | 기존 말풍선 디자인 톤 정밀 제어, 신규 Tailwind 플러그인 의존성 회피 |
| 인라인/블록 코드 구분을 `pre`의 `[&>code]` reset으로 처리 | react-markdown v9+에서 `inline` prop 제거됨 — 블록 코드는 항상 `pre > code` 구조이므로 CSS 셀렉터 구분이 가장 안정적 |
| `table`을 `overflow-x-auto` div로 래핑 | 말풍선 `max-w` 초과 시 가로 스크롤 처리 (Plan §9 리스크 대응) |
| 컴포넌트 단위 `memo` | 스트리밍 중 `MessageList` 재렌더 시 완료 메시지의 마크다운 재파싱 차단 |
| `first:mt-0` / `last:mb-0` | 말풍선 위아래 불필요 여백 제거 |

---

## 4. MessageBubble 수정 설계 (`src/components/chat/MessageBubble.tsx`)

### 4-1. AssistantMessage 본문 교체

```tsx
// Before
<div className="text-[15px] leading-[1.8] text-zinc-800">
  <p className="whitespace-pre-wrap">
    {message.content}
    {message.isStreaming && (
      <span className="ml-1 inline-block h-[18px] w-[3px] animate-pulse rounded-full bg-violet-500 align-middle" />
    )}
  </p>
  ...
</div>

// After
<div className="text-[15px] leading-[1.8] text-zinc-800">
  <MarkdownRenderer content={message.content} />
  {message.isStreaming && (
    <span className="ml-1 inline-block h-[18px] w-[3px] animate-pulse rounded-full bg-violet-500 align-middle" />
  )}
  ...
</div>
```

**커서 분리 근거**: 마크다운은 블록 요소(`<h3>`, `<pre>`, `<table>`)를 생성하므로
기존처럼 `<p>` 내부 inline으로 커서를 둘 수 없다. 콘텐츠 블록 직후 형제 요소로 분리한다.
(커서가 마지막 글자 옆이 아닌 블록 아래 줄에 표시되는 것은 허용 — ChatGPT 동일 패턴)

### 4-2. UserMessage — 변경 없음

사용자 메시지는 의도치 않은 서식 적용 방지를 위해 기존 `<p whitespace-pre-wrap>` plain text 유지.

### 4-3. ChartRenderer / SourceCitation — 위치·조건 변경 없음

`MarkdownRenderer` 다음 형제 요소로 기존 순서 그대로 유지:

```
MarkdownRenderer → (isStreaming 커서) → ChartRenderer[] → SourceCitation
```

### 4-4. memo 적용

```tsx
import { memo } from 'react';
// ...
export default memo(MessageBubble);
```

`ChatPage`는 토큰 수신 시 스트리밍 중인 메시지 객체만 교체하므로,
완료된 메시지는 참조 동일성으로 shallow compare를 통과해 재렌더되지 않는다.

---

## 5. 스트리밍 렌더링 동작 설계

```
WS token 수신 → useChatStream.tokens 누적
  ↓
ChatPage: 스트리밍 메시지 객체 교체 (content = 누적 tokens, isStreaming = true)
  ↓
MessageList 재렌더
  ├─ 완료 메시지: memo(MessageBubble) shallow pass → 재파싱 없음
  └─ 스트리밍 메시지: MarkdownRenderer 재파싱 → best-effort 렌더
       · 닫히지 않은 코드펜스(```) → 열린 코드블록으로 표시
       · 미완성 표 행 → 일반 텍스트 → 완성 시 표로 전환 (허용되는 깜빡임)
  ↓
done → isStreaming = false, 최종 content 확정
```

**성능 한계 기준**: 메시지 1건(수 KB) 단위 재파싱은 60fps 기준 무시 가능.
실측 끊김 발생 시에만 토큰 반영 throttle(50ms)을 후속 적용한다 (이번 범위 아님).

---

## 6. 테스트 설계 (`src/components/chat/MarkdownRenderer.test.tsx`)

TDD Red 단계에서 아래 10케이스를 먼저 작성한다.

| # | 테스트 케이스 | 검증 |
|---|-------------|------|
| 1 | `### 제목` | `<h3>` role heading level 3 렌더 |
| 2 | `**굵게**` / `*기울임*` | `<strong>` / `<em>` 렌더 |
| 3 | `- 항목` / `1. 항목` | `<ul>` / `<ol>` + `<li>` 렌더 |
| 4 | GFM 표 | `<table>`, `<th>`, `<td>` 렌더 + overflow 래퍼 존재 |
| 5 | 펜스 코드블록 | `<pre>` 내부 `<code>` 렌더 |
| 6 | 인라인 `` `code` `` | `<code>` 렌더 (pre 외부) |
| 7 | `[링크](url)` | `target="_blank"`, `rel="noopener noreferrer"` |
| 8 | `<script>alert(1)</script>` 입력 | script 요소 미생성, 텍스트로 이스케이프 (XSS) |
| 9 | `줄1\n줄2` (단일 개행) | `<br>` 생성 (remark-breaks) |
| 10 | 닫히지 않은 ```` ``` ```` 입력 | 크래시 없이 렌더 (스트리밍 미완성 입력 안정성) |

### MessageBubble 검증 추가 (기존 테스트 파일 또는 신규)

| 케이스 | 검증 |
|--------|------|
| 어시스턴트 메시지 `### 제목` | heading 렌더 (마크다운 적용 확인) |
| 사용자 메시지 `### 제목` | 원문 텍스트 그대로 (plain text 유지 확인) |
| `isStreaming: true` | 커서 요소 존재 |

### 회귀 확인

`ChatPage.test.tsx`, `ChatPageIntegration.test.tsx`, `streamRouting.test.tsx` —
기존 단언이 plain text 출력(`getByText`)을 가정하는 경우 마크다운 구조에 맞게 수정.
(마크다운 특수문자가 없는 일반 문장은 `<p>`로 렌더되므로 대부분 영향 없음 예상)

> 실행: `npx vitest run --pool=threads` (Windows forks 풀 타임아웃 회피)

---

## 7. 구현 순서 (Do Phase 참조)

```
Step 1          npm install react-markdown remark-gfm remark-breaks
Step 2  [Red]   MarkdownRenderer.test.tsx 작성 — 10케이스 (실패 확인)
Step 3          MarkdownRenderer.tsx 구현 (§3)
Step 4  [Green] npx vitest run --pool=threads src/components/chat/MarkdownRenderer.test.tsx
Step 5          MessageBubble.tsx 수정 (§4) — 교체 + 커서 분리 + memo
Step 6  [Red→Green] MessageBubble 검증 3케이스 추가 후 통과
Step 7  [Check] 전체 회귀: npx vitest run --pool=threads
Step 8  [Check] npm run type-check && npm run lint
Step 9  [수동]  /chatpage 에서 스트리밍 응답 마크다운 렌더 확인 (표·코드블록 포함 질문)
```

---

## 8. 완료 기준

- [ ] 어시스턴트 응답의 헤딩/목록/표/코드블록/링크가 서식 렌더링됨
- [ ] 인라인 코드와 블록 코드가 시각적으로 구분됨
- [ ] 링크에 `target="_blank" rel="noopener noreferrer"` 적용
- [ ] raw HTML(`<script>`)이 실행되지 않고 텍스트로 표시됨
- [ ] 단일 개행이 줄바꿈으로 보존됨 (기존 동작 대비 레이아웃 회귀 없음)
- [ ] 스트리밍 중 미완성 마크다운 입력에도 크래시 없음
- [ ] 사용자 메시지는 plain text 유지
- [ ] ChartRenderer / SourceCitation 표시 순서·조건 무변경
- [ ] MarkdownRenderer 테스트 10케이스 + MessageBubble 3케이스 통과
- [ ] 기존 chat 테스트 회귀 없음 / `type-check` / `lint` 통과
