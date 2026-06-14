# chat-chart-rendering Design Document

> **Summary**: 채팅 응답의 구조화 필드(`Message.charts`)로 전달되는 Chart.js config(JSON)를 패스스루로 렌더링하는 공통 차트 모듈 — `useChart` 훅 중심.
>
> **Project**: idt_front (RAG + AI Agent Frontend)
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-06-05
> **Status**: Draft
> **Planning Doc**: [chat-chart-rendering.plan.md](../../01-plan/features/chat-chart-rendering.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 1 | Schema Definition | N/A (프론트 타입으로 대체) |
| Phase 2 | Coding Conventions | ✅ `idt_front/CLAUDE.md` |
| Phase 3 | Mockup | N/A |
| Phase 4 | API Spec | N/A (백엔드 계약만 정의, 구현은 별도) |

---

## 1. Overview

### 1.1 Design Goals

- 백엔드/LLM이 내려주는 **Chart.js 네이티브 config(JSON)** 를 최소 변환으로 렌더링한다.
- chart.js 인스턴스의 생성/갱신/파괴(lifecycle)를 **단일 커스텀 훅(`useChart`)** 으로 캡슐화하여, 채팅 외(대시보드·리포트 등)에서도 재사용 가능하게 만든다.
- 비정상 config가 와도 앱이 크래시되지 않도록 **검증 + fallback**을 보장한다.

### 1.2 Design Principles

- **단일 책임**: 훅(lifecycle) / 컴포넌트(렌더·fallback) / 유틸(검증·변환)을 분리.
- **Domain 독립성**: `ChartPayload` 타입은 외부 의존 없는 순수 도메인 타입(단, chart.js 타입 재노출).
- **Passthrough 우선**: 프론트는 차트 스펙을 "해석"하지 않고 "전달"한다. 스키마 책임은 백엔드에.
- **메모리 안전**: canvas 인스턴스는 항상 `destroy()`로 회수.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌──────────────────────┐
│   WS / REST 응답      │  charts: ChartPayload[]
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  ws_adapter / service │  → Message.charts 에 매핑
└──────────┬───────────┘
           ▼
┌──────────────────────┐     ┌─────────────────────┐
│   MessageBubble       │────▶│   ChartRenderer      │  (payload 1개당 1개)
│  (charts.map)         │     │  - chartValidator    │
└──────────────────────┘     │  - useChart          │
                             └──────────┬──────────┘
                                        ▼
                             ┌─────────────────────┐
                             │  <canvas> + Chart.js │
                             └─────────────────────┘
```

### 2.2 Data Flow

```
ChartPayload (JSON)
  → isValidChartPayload()  ─(false)→ Fallback UI
  → toChartConfiguration()
  → useChart(config)  → new Chart(canvas, config)
  → cleanup: chart.destroy()
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `ChartRenderer` | `useChart`, `chartValidator` | 검증 후 렌더 위임 |
| `useChart` | `chart.js`, `chartSetup` | 인스턴스 lifecycle |
| `chartSetup` | `chart.js` | controller/element/scale 등록 |
| `MessageBubble` | `ChartRenderer` | 응답 본문 아래 차트 출력 |
| `Message` 타입 | `ChartPayload` | 구조화 필드 |

---

## 3. Data Model

### 3.1 Entity Definition

```typescript
// src/types/chart.ts
import type { ChartType, ChartData, ChartOptions } from 'chart.js';

/** 백엔드 → 프론트 차트 계약 = Chart.js 네이티브 config 패스스루 */
export interface ChartPayload {
  type: ChartType;          // 'bar' | 'line' | 'pie' | 'doughnut' | 'scatter' | 'radar' ...
  data: ChartData;
  options?: ChartOptions;
}

/** 프론트 허용 차트 타입 화이트리스트 (검증 기준) */
export const SUPPORTED_CHART_TYPES = [
  'bar', 'line', 'pie', 'doughnut', 'scatter', 'radar',
] as const;
export type SupportedChartType = (typeof SUPPORTED_CHART_TYPES)[number];
```

### 3.2 Message 확장

```typescript
// src/types/chat.ts (수정)
export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  isStreaming?: boolean;
  sources?: DocumentSource[];
  charts?: ChartPayload[];   // ← 추가 (선택 필드, 하위호환 유지)
}
```

### 3.3 백엔드 계약 (WS / REST)

> 백엔드 구현은 본 작업 범위 밖. 프론트 타입 계약만 정의하고 `/api-contract-sync`로 동기화.

```typescript
// src/types/websocket.ts (수정 — 백엔드 합의 후)
export interface ChatAnswerCompletedData {
  answer: string;
  tools_used: string[];
  sources: ChatSource[];
  was_summarized: boolean;
  charts?: ChartPayload[];   // ← 추가
}
```

차트는 토큰 스트리밍이 아닌 **`chat_answer_completed` 시점에 일괄 수신**한다.

---

## 4. API Specification

본 기능은 신규 백엔드 엔드포인트를 추가하지 않는다. 기존 채팅 응답 페이로드에 `charts` 필드를 **추가하는 계약**만 정의한다.

| 채널 | 메시지/응답 | 추가 필드 |
|------|------------|----------|
| WebSocket | `chat_answer_completed` | `charts?: ChartPayload[]` |
| REST (선택) | `GeneralChatResponse` | `charts?: ChartPayload[]` |

**필드 부재 시 동작**: `charts`가 없거나 빈 배열이면 차트를 렌더하지 않는다(무해, 하위호환).

---

## 5. UI/UX Design

### 5.1 Screen Layout

채팅 AI 메시지 내부, 본문 텍스트 아래·`SourceCitation` 위/옆에 차트 블록을 배치한다.

```
┌─ AssistantMessage ────────────────────────────┐
│ [아바타] 상플AI                                 │
│  본문 텍스트 (whitespace-pre-wrap)              │
│  ┌──────────────────────────────────────────┐ │
│  │  [ChartRenderer] height=320               │ │
│  │   rounded-2xl border bg-white shadow-sm   │ │
│  │   <canvas>  (responsive, !aspectRatio)    │ │
│  └──────────────────────────────────────────┘ │
│  (차트가 여러 개면 gap-3 세로 나열)              │
│  [SourceCitation chips]                         │
└────────────────────────────────────────────────┘
```

### 5.2 User Flow

```
AI 응답 수신(charts 포함)
  → MessageBubble: charts.length > 0 ?
     → 각 payload → ChartRenderer
        → 유효 → canvas에 차트 렌더
        → 무효 → "차트를 표시할 수 없습니다" fallback
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `ChartRenderer` | `src/components/chat/ChartRenderer.tsx` | 검증·컨테이너·fallback, useChart 위임 |
| `useChart` | `src/hooks/useChart.ts` | chart.js 인스턴스 lifecycle |
| `chartSetup` | `src/lib/chartSetup.ts` | chart.js 컴포넌트 등록 |
| `chartValidator` | `src/utils/chartValidator.ts` | payload 검증 + config 변환 |
| `MessageBubble` (수정) | `src/components/chat/MessageBubble.tsx` | charts 렌더 진입점 |

### 5.4 스타일 규약 (CLAUDE.md 준수)

- 컨테이너: `mt-3 rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm`, 고정 `height`(기본 320px).
- chart.js options 기본값: `responsive: true`, `maintainAspectRatio: false` → 컨테이너 폭/높이에 맞춤.
- fallback: `rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-[13px] text-zinc-500`.

---

## 6. Error Handling

### 6.1 에러/예외 정의

| 상황 | 원인 | 처리 |
|------|------|------|
| 미지원 `type` | 화이트리스트 밖 | `isValidChartPayload` false → fallback UI |
| `data.datasets` 누락/빈 배열 | 비정상 페이로드 | fallback UI |
| chart.js 생성 throw | 내부 config 불일치(scale 등) | (선택) try/catch로 감싸 fallback, 콘솔 warn |
| canvas ref null | 마운트 타이밍 | useEffect early-return |
| 인스턴스 미파괴 | cleanup 누락 | useEffect cleanup에서 `destroy()` 보장 |

### 6.2 Fallback 표현

차트 영역을 빈 화면/크래시 대신 안내 박스로 대체하여 대화 흐름을 보존한다.

```tsx
<div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-[13px] text-zinc-500">
  차트를 표시할 수 없습니다. (지원하지 않는 형식)
</div>
```

---

## 7. Security Considerations

- [x] **함수 콜백 차단**: JSON은 함수를 전달 못 하므로 options 내 임의 코드 실행 불가. (단, `eval`성 문자열을 직접 실행하는 로직을 만들지 않는다)
- [x] **type 화이트리스트**: `SUPPORTED_CHART_TYPES`로 제한.
- [x] **datasets 검증**: 배열/비어있지 않음 확인.
- [x] **XSS**: 차트 라벨/제목은 chart.js가 canvas에 그리므로 DOM 주입 없음 (innerHTML 미사용).
- [ ] (해당 없음) 인증/인가 — 기존 채팅 인증 흐름 그대로.

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | `chartValidator` (순수 함수) | Vitest |
| Unit | `useChart` (lifecycle) | Vitest + Testing Library (`renderHook`) |
| Component | `ChartRenderer` (렌더/fallback) | Vitest + RTL |

> **jsdom 제약**: canvas 2D context 미지원 → `vi.mock('chart.js')`로 `Chart` 생성자를 모킹하고 "생성/파괴 호출 횟수·인자"만 검증한다. 실제 픽셀 렌더는 검증하지 않는다.

### 8.2 Test Cases (Key)

**chartValidator.test.ts**
- [ ] 정상 bar payload → `isValidChartPayload === true`
- [ ] `type: 'unknown'` → false
- [ ] `data.datasets` 누락 → false
- [ ] `datasets: []` → false
- [ ] `toChartConfiguration`이 `{type,data,options}` 매핑

**useChart.test.ts**
- [ ] 마운트 + config 존재 → `Chart` 1회 생성
- [ ] config 변경 → 이전 인스턴스 `destroy()` 후 재생성
- [ ] config = null → 생성 안 함
- [ ] 언마운트 → `destroy()` 호출

**ChartRenderer.test.tsx**
- [ ] 유효 payload → `<canvas>` 렌더
- [ ] 무효 payload → fallback 텍스트 렌더

---

## 9. Clean Architecture

### 9.1 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `ChartRenderer`, `MessageBubble` | Presentation | `src/components/chat/` |
| `useChart` | Presentation(hook) | `src/hooks/` |
| `chartValidator` | Application(util) | `src/utils/` |
| `ChartPayload`, `SUPPORTED_CHART_TYPES` | Domain | `src/types/chart.ts` |
| `chartSetup` (chart.js 등록) | Infrastructure | `src/lib/chartSetup.ts` |

### 9.2 Dependency Rules

```
Presentation (ChartRenderer, useChart, MessageBubble)
   ├─→ Application (chartValidator)
   ├─→ Domain (chart.ts)
   └─→ Infrastructure (chartSetup) ── via useChart
Domain(chart.ts) : 외부 비의존 (chart.js 타입만 재노출)
```

규칙 준수: Presentation → Application/Domain/Infra(lib) 단방향. Domain은 순수.

---

## 10. Coding Convention Reference

### 10.1 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 컴포넌트 네이밍 | PascalCase 파일 (`ChartRenderer.tsx`), arrow function, `export default` 하단 |
| 훅 네이밍 | camelCase (`useChart.ts`) |
| 타입 네이밍 | 도메인 모델 접미사 없음 (`ChartPayload`), 상수 UPPER (`SUPPORTED_CHART_TYPES`) |
| import | 외부 → 절대경로(`@/`) → 상대 → `import type` |
| 상태 관리 | 훅 내부 `useRef`/`useEffect`만 사용 (전역 상태 불필요) |
| 테스트 | 소스 옆 배치 (`useChart.test.ts`), Red→Green→Refactor |

### 10.2 Props 패턴 (CLAUDE.md)

```tsx
interface ChartRendererProps {
  payload: ChartPayload;
  height?: number;
}
const ChartRenderer = ({ payload, height = 320 }: ChartRendererProps) => { /* ... */ };
export default ChartRenderer;
```

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── types/chart.ts                    # (신규) ChartPayload, 화이트리스트
├── types/chat.ts                     # (수정) Message.charts
├── types/websocket.ts                # (수정) ChatAnswerCompletedData.charts
├── lib/chartSetup.ts                 # (신규) chart.js 컴포넌트 등록
├── hooks/useChart.ts                 # (신규) 인스턴스 lifecycle 훅
├── hooks/useChart.test.ts            # (신규) 훅 테스트
├── utils/chartValidator.ts           # (신규) 검증/변환
├── utils/chartValidator.test.ts      # (신규) 유틸 테스트
└── components/chat/
    ├── ChartRenderer.tsx             # (신규) 렌더 컴포넌트
    ├── ChartRenderer.test.tsx        # (신규) 컴포넌트 테스트
    └── MessageBubble.tsx             # (수정) charts 렌더
```

### 11.2 Implementation Order (TDD)

1. [ ] `npm install chart.js`
2. [ ] `src/types/chart.ts` — `ChartPayload`, `SUPPORTED_CHART_TYPES` 정의
3. [ ] **(Red)** `chartValidator.test.ts` 작성 → **(Green)** `chartValidator.ts` 구현
4. [ ] `src/lib/chartSetup.ts` — `ensureChartRegistered()` 구현
5. [ ] **(Red)** `useChart.test.ts` (Chart mock) → **(Green)** `useChart.ts` 구현
6. [ ] **(Red)** `ChartRenderer.test.tsx` → **(Green)** `ChartRenderer.tsx` 구현
7. [ ] `src/types/chat.ts` — `Message.charts` 추가
8. [ ] `MessageBubble.tsx` — charts 렌더 통합
9. [ ] `src/types/websocket.ts` — 계약 필드 추가 (백엔드 합의 후 연동)
10. [ ] `npm run type-check && npm run test:run` 그린 확인

### 11.3 핵심 코드 스켈레톤

**useChart.ts (lifecycle 핵심)**
```typescript
export const useChart = (config: ChartConfiguration | null) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    ensureChartRegistered();
    const canvas = canvasRef.current;
    if (!canvas || !config) return;
    chartRef.current?.destroy();
    chartRef.current = new Chart(canvas, {
      ...config,
      options: { responsive: true, maintainAspectRatio: false, ...config.options },
    });
    return () => { chartRef.current?.destroy(); chartRef.current = null; };
  }, [config]);

  return canvasRef;
};
```

> `ChartRenderer`에서 `useMemo`로 config를 안정화하여 불필요한 재생성(깜빡임)을 막는다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-05 | Initial draft (chart.js passthrough 결정 반영) | 배상규 |
