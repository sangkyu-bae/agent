# Plan: Chat Markdown Rendering

> Feature: `chat-markdown-rendering`
> Phase: Plan
> Created: 2026-06-10
> Author: 배상규

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | `/chatpage`의 어시스턴트 응답이 마크다운 원문(`### 제목`, `**굵게**`, `\| 표 \|`)을 그대로 노출해 가독성이 떨어진다. |
| **Solution** | `react-markdown` + `remark-gfm` 기반 `MarkdownRenderer` 컴포넌트를 신설하고 `MessageBubble`의 어시스턴트 메시지 출력을 교체한다. 스트리밍 중에도 누적 토큰을 점진적으로 마크다운 렌더링한다. |
| **Function (UX Effect)** | 제목/목록/표/코드블록/링크가 서식 적용된 형태로 표시되어 LLM 응답 가독성이 즉시 개선된다. ChatPage·Agent Chat 등 `MessageBubble`을 쓰는 모든 화면에 일괄 적용된다. |
| **Core Value** | 단일 렌더링 지점(`MessageBubble`)만 수정하는 저위험 변경으로 플랫폼 전반의 응답 품질 체감을 높인다. raw HTML 미렌더 정책으로 XSS 안전성 유지. |

---

## 1. 배경 및 목표

### 배경

백엔드(General Chat / Agent)의 LLM 응답은 마크다운 형식(제목, 목록, 표, 코드블록 등)으로 생성되는 경우가 많다.
그러나 현재 프론트엔드는 `MessageBubble.tsx`의 `AssistantMessage`에서 응답을
`<p className="whitespace-pre-wrap">{message.content}</p>` 로 **원문 그대로** 출력한다.

- 마크다운 라이브러리 미설치 (`package.json`에 react-markdown/remark 계열 없음)
- 렌더링 지점은 `MessageBubble.tsx` 단일 컴포넌트
  - 경로: `/chatpage` → `pages/ChatPage/index.tsx` → `MessageList` → `MessageBubble`
- 응답은 `useChatStream`(WebSocket)으로 **토큰 단위 스트리밍**되므로, 미완성 마크다운(닫히지 않은 코드펜스 등)이 수시로 렌더링됨

### 목표

어시스턴트 응답을 마크다운으로 파싱하여 서식 적용된 HTML로 렌더링한다.
스트리밍 중에도 자연스럽게 점진 렌더링되며, 기존 ChartRenderer / SourceCitation 배치는 유지한다.

---

## 2. 구현 범위

### In Scope

| 항목 | 설명 |
|------|------|
| 라이브러리 도입 | `react-markdown`(^10) + `remark-gfm`(^4) — React 19 호환 |
| 줄바꿈 보존 | `remark-breaks`(^4) — LLM 응답의 단일 개행을 `<br>`로 처리 (기존 `whitespace-pre-wrap` 동작 보존) |
| `MarkdownRenderer` 컴포넌트 신설 | `src/components/chat/MarkdownRenderer.tsx` — components 매핑으로 기존 디자인 톤(text-[15px], zinc-800) 유지 |
| `MessageBubble` 교체 | `AssistantMessage`의 `<p>` → `<MarkdownRenderer content={...} />` |
| 스트리밍 대응 | 누적 `tokens`를 매 청크마다 재파싱. 완료된 메시지는 `React.memo`로 재렌더 차단. 스트리밍 커서를 마크다운 블록 외부로 이동 |
| 링크 안전 처리 | `<a>`에 `target="_blank" rel="noopener noreferrer"` 강제 |
| XSS 방어 | `rehype-raw` 미사용 — raw HTML은 텍스트로 이스케이프 (react-markdown 기본 동작) |
| GFM 지원 | 표, 취소선, 체크리스트, 자동 링크 |

### Out of Scope

| 항목 | 이유 |
|------|------|
| 코드 syntax highlighting (`rehype-highlight`/shiki) | 번들 크기 큼 — 기본 코드블록 스타일만 적용, 별도 태스크 |
| 사용자 메시지 마크다운 렌더링 | 사용자 입력은 plain text 유지 (의도치 않은 서식 적용 방지) |
| 코드블록 복사 버튼 | 부가 기능 — Phase 2 |
| Excel 분석 / ToolPreviewPanel 출력 변경 | 별도 렌더링 경로 — 현행 유지 |
| 백엔드 변경 | 없음 — 프론트 전용 작업 |

---

## 3. 기술 선택

### 라이브러리: react-markdown

| 후보 | 판단 |
|------|------|
| **react-markdown (채택)** | React 컴포넌트 매핑 방식 → Tailwind 클래스 직접 주입 용이. raw HTML 기본 미렌더로 XSS 안전. remark/rehype 생태계 확장성 |
| marked + DOMPurify | 문자열 → `dangerouslySetInnerHTML` 방식. sanitize 누락 리스크, React 친화성 낮음 |
| @tailwindcss/typography (prose) | 스타일링 보조 수단일 뿐 파서 아님. components 매핑으로 충분하여 플러그인 추가 보류 |

### 스트리밍 렌더링 전략

- `react-markdown`은 미완성 마크다운 입력에도 예외 없이 best-effort 렌더링함 (닫히지 않은 코드펜스 → 열린 코드블록으로 표시)
- 메시지 1건 분량의 재파싱 비용은 낮음. 단, 완료된 과거 메시지의 불필요한 재파싱을 막기 위해 `MessageBubble`(또는 `MarkdownRenderer`)을 `React.memo` 처리
- 스트리밍 커서(보라색 막대)는 현재 `<p>` 내부 inline 요소 — 마크다운은 블록 요소를 생성하므로 커서를 콘텐츠 블록 **뒤에 별도 요소**로 분리

---

## 4. 변경 파일 목록

### 신규 파일

| 파일 | 내용 |
|------|------|
| `src/components/chat/MarkdownRenderer.tsx` | react-markdown 래퍼. remark-gfm/breaks 플러그인, 요소별 Tailwind 스타일 매핑 (h1~h4, p, ul/ol/li, table, code/pre, blockquote, a, hr) |
| `src/components/chat/MarkdownRenderer.test.tsx` | TDD 테스트 (아래 §6) |

### 수정 파일

| 파일 | 변경 내용 |
|------|---------|
| `package.json` | `react-markdown`, `remark-gfm`, `remark-breaks` 의존성 추가 |
| `src/components/chat/MessageBubble.tsx` | `AssistantMessage`의 `<p whitespace-pre-wrap>` → `MarkdownRenderer` 교체, 스트리밍 커서 분리, `React.memo` 적용 |

> `MessageList`, `ChatPage/index.tsx`, 타입, 서비스, 훅은 변경 없음.

---

## 5. 데이터 흐름 (변경 후)

```
WS 토큰 수신 (useChatStream.tokens 누적)
  ↓
ChatPage → MessageList → MessageBubble (isStreaming=true, content=누적 토큰)
  ↓
AssistantMessage
  ├─ <MarkdownRenderer content={message.content} />   ← 매 청크 재파싱
  ├─ {isStreaming && <커서 />}                         ← 블록 외부 분리
  ├─ ChartRenderer (charts 있을 때)                    ← 현행 유지
  └─ SourceCitation (sources 있을 때)                  ← 현행 유지
```

---

## 6. 테스트 계획 (TDD)

### Red → Green → Refactor

| 테스트 파일 | 테스트 항목 |
|------------|------------|
| `MarkdownRenderer.test.tsx` | ① 헤딩(`###`) → `<h3>` ② 굵게/기울임 ③ 순서/비순서 목록 ④ GFM 표 → `<table>` ⑤ 코드블록 → `<pre><code>` ⑥ 인라인 코드 ⑦ 링크 `target=_blank rel=noopener noreferrer` ⑧ raw HTML(`<script>`) 텍스트 이스케이프 (XSS) ⑨ 단일 개행 줄바꿈 보존 ⑩ 미완성 코드펜스 입력 시 크래시 없음 |
| `MessageBubble` 관련 기존 테스트 | 어시스턴트 메시지가 마크다운으로 렌더되는지 검증 추가, 사용자 메시지는 plain text 유지 검증 |
| 기존 스위트 회귀 | `ChatPage.test.tsx`, `ChatPageIntegration.test.tsx`, `streamRouting.test.tsx` 통과 유지 |

> 실행: `vitest --pool=threads` (Windows forks 풀 타임아웃 이슈 회피)

---

## 7. 완료 기준 (Definition of Done)

- [ ] 어시스턴트 응답의 제목/목록/표/코드블록/링크가 서식 적용되어 표시됨
- [ ] 스트리밍 중 누적 토큰이 점진적으로 마크다운 렌더링되며 크래시 없음
- [ ] 사용자 메시지는 기존대로 plain text 출력
- [ ] raw HTML 입력이 실행되지 않고 텍스트로 표시됨 (XSS 안전)
- [ ] ChartRenderer / SourceCitation 표시 위치·동작 변화 없음
- [ ] `MarkdownRenderer.test.tsx` 전체 통과
- [ ] 기존 chat 관련 테스트 회귀 없음
- [ ] `npm run type-check` 및 `npm run lint` 통과

---

## 8. 구현 순서 (Do Phase 참조)

```
1. npm install react-markdown remark-gfm remark-breaks
2. TDD Red: MarkdownRenderer.test.tsx 작성 (실패 확인)
3. MarkdownRenderer.tsx 구현 — 플러그인 + components 스타일 매핑
4. TDD Green: 테스트 통과 확인
5. MessageBubble.tsx — AssistantMessage 교체, 커서 분리, React.memo
6. 기존 테스트 회귀 확인 + MessageBubble 검증 추가
7. TDD Refactor: 스타일 정리
8. npm run type-check && npm run lint && vitest run --pool=threads
9. 수동 확인: /chatpage 스트리밍 응답 마크다운 렌더링
```

---

## 9. 리스크

| 리스크 | 대응 |
|--------|------|
| 매 토큰 청크마다 재파싱으로 인한 렌더 비용 | 메시지 1건 단위라 비용 낮음. 완료 메시지는 `React.memo`로 차단. 문제 시 throttle(예: 50ms) 후속 적용 |
| 단일 개행 무시로 기존 응답 레이아웃 변화 | `remark-breaks`로 단일 개행 → `<br>` 보존 |
| 미완성 마크다운(열린 코드펜스)이 스트리밍 중 어색하게 보임 | react-markdown best-effort 렌더로 기능상 문제 없음 — UI 폴리시 개선은 Phase 2 |
| 번들 크기 증가 (약 +40~60KB gzip) | SPA 단일 진입 페이지 핵심 기능으로 수용. 필요 시 lazy import 검토 |
| 표가 말풍선 폭(max-w) 초과 | `table` 래퍼에 `overflow-x-auto` 적용 |
| 기존 테스트가 plain text 출력을 가정 | 회귀 테스트 수정 범위에 포함 (§6) |
