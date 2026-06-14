# Plan: Chat Chart Rendering (채팅 차트 JSON 렌더링 모듈)

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | chat-chart-rendering |
| 작성일 | 2026-06-05 |
| 예상 소요 | 4~6시간 |
| 라이브러리 | chart.js v4 (순수, react-chartjs-2 미사용) |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | 채팅 응답에 차트로 보여주면 좋을 수치 데이터(매출 추이, 비율, 비교 등)가 있어도 현재는 텍스트로만 출력됨. 시각화 수단이 전혀 없음 |
| **Solution** | 메시지의 구조화 필드(`charts`)로 내려오는 **Chart.js config(`{ type, data, options }`)를 그대로 패스스루**하여 렌더링하는 공통 `useChart` 커스텀 훅 + `ChartRenderer` 컴포넌트를 도입 |
| **Function UX Effect** | AI 응답 하단에 막대/라인/파이·도넛/기타(scatter·radar) 차트가 자동 렌더링됨. 한 메시지에 여러 차트도 가능 |
| **Core Value** | 차트 생성 로직을 단일 훅으로 캡슐화하여, 채팅뿐 아니라 대시보드·리포트 등 어디서나 재사용 가능한 공통 차트 모듈 확보 |

---

## 1. 결정 사항 (사용자 확인 완료)

| 결정 | 선택 | 비고 |
|------|------|------|
| 렌더링 라이브러리 | **chart.js 순수 + useRef 훅** | react-chartjs-2 미도입. canvas ref + useEffect로 인스턴스 직접 관리 |
| 차트 JSON 전달 경로 | **메시지의 구조화 필드** | `Message.charts` 필드로 전달. answer 텍스트 파싱 아님 |
| JSON 스키마(계약) | **Chart.js config 그대로 패스스루** | `{ type, data, options }` 네이티브 config. 프론트는 검증 후 거의 그대로 전달 |
| 초기 지원 차트 | **bar, line, pie/doughnut, 기타(scatter/radar)** | chart.js 컨트롤러 등록으로 확장 |

> ⚠️ **현황 메모**: 프로젝트에는 이미 `recharts@3.8.1`이 설치돼 있으나, 사용자 결정에 따라 **chart.js를 신규 도입**한다. recharts 정리/통일 여부는 본 작업 범위 밖(Out-of-Scope)으로 두고 추후 별도 판단한다.

---

## 2. 현재 상황 분석

### 2.1 메시지 렌더링 흐름

```
WS/REST 응답
  → useStream / chatStore (streamingContent 누적)
  → Message { content: string }  ← 순수 텍스트만 보유
  → MessageList → MessageBubble
  → <p className="whitespace-pre-wrap">{content}</p>  ← 텍스트만 출력
```

| 파일 | 현황 |
|------|------|
| `src/types/chat.ts` | `Message`에 `content`, `sources`만 있음. 구조화 데이터 필드 없음 |
| `src/components/chat/MessageBubble.tsx` | `AssistantMessage`가 텍스트 + `SourceCitation`만 렌더 |
| `src/types/websocket.ts` | `ChatAnswerCompletedData`에 `answer/sources/tools_used`만 존재. 차트 필드 없음 |
| `package.json` | `recharts` 설치됨, `chart.js` **미설치** |

### 2.2 시사점

- 차트를 그리려면 `Message`에 **구조화 필드(`charts`)** 를 추가해야 한다 (사용자 결정).
- `SourceCitation`이 이미 "응답 본문 아래 부가 블록"을 렌더하는 선례이므로, 차트도 동일 위치 패턴을 따른다.
- chart.js는 `<canvas>` + 인스턴스 lifecycle 관리가 필요 → **커스텀 훅으로 캡슐화**하는 것이 핵심.

---

## 3. 구현 범위

### 3.1 In-Scope

| # | 항목 | 설명 |
|---|------|------|
| 1 | chart.js 설치 | `chart.js@^4` 의존성 추가 |
| 2 | 차트 타입 정의 | `src/types/chart.ts` — `ChartPayload`, 지원 타입 화이트리스트 |
| 3 | chart.js 컴포넌트 등록 | `src/lib/chartSetup.ts` — 필요한 controller/element/scale 등록 (tree-shaking) |
| 4 | `useChart` 커스텀 훅 | `src/hooks/useChart.ts` — canvas ref + 인스턴스 생성/갱신/파괴 |
| 5 | `ChartRenderer` 컴포넌트 | `src/components/chat/ChartRenderer.tsx` — 훅 래핑 + 컨테이너 + fallback |
| 6 | config 검증 유틸 | `src/utils/chartValidator.ts` — type 화이트리스트/필수 필드 검증 |
| 7 | `Message` 타입 확장 | `charts?: ChartPayload[]` 필드 추가 |
| 8 | MessageBubble 통합 | 응답 본문 아래 차트 목록 렌더 |
| 9 | TDD 테스트 | 훅/컴포넌트/유틸 단위 테스트 |

### 3.2 Out-of-Scope

- 백엔드에서 차트 JSON을 실제로 내려주는 API 구현 (백엔드 책임 — 프론트는 계약만 정의)
- 스트리밍 중 차트 실시간 갱신 (차트는 `answer_completed` 시점에 한 번에 수신/렌더)
- recharts 제거/마이그레이션
- 차트 인터랙션 고도화(드릴다운, export 등)

---

## 4. 차트 JSON 계약 (Chart.js Config Passthrough)

백엔드는 Chart.js 네이티브 config를 그대로 내려주고, 프론트는 검증 후 패스스루한다.

```jsonc
// Message.charts[0] 예시 (막대 차트)
{
  "type": "bar",
  "data": {
    "labels": ["1월", "2월", "3월"],
    "datasets": [
      { "label": "매출(억)", "data": [12, 19, 7] }
    ]
  },
  "options": {            // 선택 — 생략 시 프론트 기본값 적용
    "plugins": { "title": { "display": true, "text": "분기 매출" } }
  }
}
```

```typescript
// src/types/chart.ts
import type { ChartType, ChartData, ChartOptions } from 'chart.js';

/** 백엔드가 내려주는 차트 페이로드 = Chart.js 네이티브 config 패스스루 */
export interface ChartPayload {
  type: ChartType;                 // 'bar' | 'line' | 'pie' | 'doughnut' | 'scatter' | 'radar' ...
  data: ChartData;
  options?: ChartOptions;
}

/** 프론트에서 허용하는 차트 타입 화이트리스트 (검증용) */
export const SUPPORTED_CHART_TYPES = [
  'bar', 'line', 'pie', 'doughnut', 'scatter', 'radar',
] as const;
export type SupportedChartType = (typeof SUPPORTED_CHART_TYPES)[number];
```

> **보안/안정성**: JSON으로는 함수 콜백을 전달할 수 없으므로 XSS 위험은 낮다. 다만 `type`이 화이트리스트 밖이거나 `data.datasets`가 비정상일 때 chart.js가 throw 하므로, 렌더 전 `chartValidator`로 1차 검증한다.

---

## 5. 구현 순서

### Step 1: 의존성 설치

```bash
npm install chart.js
```

### Step 2: chart.js 컴포넌트 등록 (`src/lib/chartSetup.ts`)

chart.js v4는 tree-shakeable이므로 사용할 controller/element/scale/plugin만 등록한다.

```typescript
import {
  Chart,
  // controllers
  BarController, LineController, PieController, DoughnutController,
  ScatterController, RadarController,
  // elements
  BarElement, LineElement, PointElement, ArcElement,
  // scales
  CategoryScale, LinearScale, RadialLinearScale,
  // plugins
  Title, Tooltip, Legend,
} from 'chart.js';

let registered = false;

/** 앱 전역에서 1회만 호출. useChart 내부에서 호출하여 등록 보장 */
export const ensureChartRegistered = () => {
  if (registered) return;
  Chart.register(
    BarController, LineController, PieController, DoughnutController,
    ScatterController, RadarController,
    BarElement, LineElement, PointElement, ArcElement,
    CategoryScale, LinearScale, RadialLinearScale,
    Title, Tooltip, Legend,
  );
  registered = true;
};
```

> 대안: `import 'chart.js/auto'` 한 줄로 전체 등록 가능(간단하지만 번들 큼). 초기에는 명시 등록으로 번들을 통제한다.

### Step 3: `useChart` 커스텀 훅 (`src/hooks/useChart.ts`) — 핵심

```typescript
import { useEffect, useRef } from 'react';
import { Chart, type ChartConfiguration } from 'chart.js';
import { ensureChartRegistered } from '@/lib/chartSetup';

/**
 * Chart.js 인스턴스 lifecycle을 캡슐화하는 공통 훅.
 * - config 변경 시 인스턴스를 재생성(또는 update)
 * - 언마운트 시 destroy로 메모리 누수 방지
 *
 * @returns canvas에 부착할 ref
 */
export const useChart = (config: ChartConfiguration | null) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<Chart | null>(null);

  useEffect(() => {
    ensureChartRegistered();
    const canvas = canvasRef.current;
    if (!canvas || !config) return;

    // 기존 인스턴스 정리 후 재생성 (config 구조가 자유로워 update보다 재생성이 안전)
    chartRef.current?.destroy();
    chartRef.current = new Chart(canvas, {
      ...config,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        ...config.options,
      },
    });

    return () => {
      chartRef.current?.destroy();
      chartRef.current = null;
    };
  }, [config]);

  return canvasRef;
};
```

> **설계 포인트**
> - `config`는 매 렌더 새 객체가 들어오면 매번 재생성된다. `ChartRenderer`에서 `useMemo`로 안정화하거나, 호출부에서 메모이즈된 payload를 넘긴다.
> - 재생성 방식 채택 이유: 패스스루 config는 type/scale이 바뀔 수 있어 `chart.update()`로는 안전하지 않음.

### Step 4: config 검증 유틸 (`src/utils/chartValidator.ts`)

```typescript
import type { ChartConfiguration } from 'chart.js';
import { SUPPORTED_CHART_TYPES } from '@/types/chart';
import type { ChartPayload } from '@/types/chart';

/** 페이로드가 렌더 가능한 형태인지 검증 */
export const isValidChartPayload = (p: unknown): p is ChartPayload => {
  if (!p || typeof p !== 'object') return false;
  const { type, data } = p as Record<string, unknown>;
  if (!SUPPORTED_CHART_TYPES.includes(type as never)) return false;
  if (!data || typeof data !== 'object') return false;
  const datasets = (data as { datasets?: unknown }).datasets;
  return Array.isArray(datasets) && datasets.length > 0;
};

/** ChartPayload → chart.js ChartConfiguration */
export const toChartConfiguration = (p: ChartPayload): ChartConfiguration =>
  ({ type: p.type, data: p.data, options: p.options } as ChartConfiguration);
```

### Step 5: `ChartRenderer` 컴포넌트 (`src/components/chat/ChartRenderer.tsx`)

```tsx
import { useMemo } from 'react';
import type { ChartPayload } from '@/types/chart';
import { useChart } from '@/hooks/useChart';
import { isValidChartPayload, toChartConfiguration } from '@/utils/chartValidator';

interface ChartRendererProps {
  payload: ChartPayload;
  /** 컨테이너 높이 (기본 320px) */
  height?: number;
}

const ChartRenderer = ({ payload, height = 320 }: ChartRendererProps) => {
  const valid = isValidChartPayload(payload);
  const config = useMemo(
    () => (valid ? toChartConfiguration(payload) : null),
    [valid, payload],
  );
  const canvasRef = useChart(config);

  if (!valid) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-zinc-50 px-4 py-3 text-[13px] text-zinc-500">
        차트를 표시할 수 없습니다. (지원하지 않는 형식)
      </div>
    );
  }

  return (
    <div
      className="mt-3 rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm"
      style={{ height }}
    >
      <canvas ref={canvasRef} />
    </div>
  );
};

export default ChartRenderer;
```

> 레이아웃 규칙(CLAUDE.md): 차트 컨테이너는 고정 height + `maintainAspectRatio:false`로 채팅 폭(max-w-3xl) 안에서 반응형 동작.

### Step 6: `Message` 타입 + 어댑터 확장

```typescript
// src/types/chat.ts
import type { ChartPayload } from './chart';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  createdAt: string;
  isStreaming?: boolean;
  sources?: DocumentSource[];
  charts?: ChartPayload[];   // ← 추가
}
```

```typescript
// src/types/websocket.ts — 백엔드 협의 후 추가 (계약 정의)
export interface ChatAnswerCompletedData {
  answer: string;
  tools_used: string[];
  sources: ChatSource[];
  was_summarized: boolean;
  charts?: ChartPayload[];   // ← 추가 (백엔드 합의 필요)
}
```

- `chat_answer_completed` 수신 시 `charts`를 커밋되는 assistant `Message`에 함께 저장.
- REST 응답(`GeneralChatResponse`)에도 동일 필드 추가 가능(백엔드 합의).

### Step 7: MessageBubble 통합 (`src/components/chat/MessageBubble.tsx`)

`AssistantMessage` 내 `SourceCitation` 옆에 차트 목록을 렌더한다.

```tsx
{message.charts && message.charts.length > 0 && (
  <div className="mt-2 flex flex-col gap-3">
    {message.charts.map((chart, i) => (
      <ChartRenderer key={i} payload={chart} />
    ))}
  </div>
)}
```

---

## 6. 상세 변경 파일 목록

| 파일 | 변경 내용 | 신규/수정 |
|------|----------|:--------:|
| `package.json` | `chart.js` 의존성 추가 | 수정 |
| `src/types/chart.ts` | `ChartPayload`, `SUPPORTED_CHART_TYPES` | 신규 |
| `src/lib/chartSetup.ts` | chart.js 컴포넌트 등록 (`ensureChartRegistered`) | 신규 |
| `src/hooks/useChart.ts` | 인스턴스 lifecycle 캡슐화 훅 | 신규 |
| `src/utils/chartValidator.ts` | payload 검증 + config 변환 | 신규 |
| `src/components/chat/ChartRenderer.tsx` | 차트 렌더 컴포넌트 + fallback | 신규 |
| `src/types/chat.ts` | `Message.charts` 필드 추가 | 수정 |
| `src/types/websocket.ts` | `ChatAnswerCompletedData.charts` (백엔드 합의) | 수정 |
| `src/components/chat/MessageBubble.tsx` | 차트 목록 렌더 | 수정 |

---

## 7. 테스트 계획 (TDD: Red → Green → Refactor)

| 대상 | 파일 | 테스트 항목 |
|------|------|-----------|
| `chartValidator` | `src/utils/chartValidator.test.ts` | 정상 payload 통과 / 미지원 type 거부 / datasets 누락 거부 |
| `useChart` | `src/hooks/useChart.test.ts` | 마운트 시 Chart 생성 / config 변경 시 destroy+재생성 / 언마운트 시 destroy |
| `ChartRenderer` | `src/components/chat/ChartRenderer.test.tsx` | 유효 payload → canvas 렌더 / 무효 payload → fallback 메시지 |

> **jsdom 주의**: jsdom에는 canvas 2D context가 없으므로 `chart.js`의 `Chart` 생성자를 `vi.mock('chart.js')`로 모킹하여 "생성/파괴 호출"만 검증한다(실제 픽셀 렌더 검증 X). 이는 [[backend-test-eventloop-flakiness]]처럼 환경 의존 테스트의 격리 원칙과 동일한 맥락.

---

## 8. 리스크 및 대응

| 리스크 | 대응 |
|--------|------|
| canvas 인스턴스 미파괴로 인한 메모리 누수 | `useChart` cleanup에서 항상 `destroy()` 호출 (테스트로 검증) |
| 매 렌더마다 config 새 객체 → 차트 깜빡임/재생성 | `ChartRenderer`에서 `useMemo`, 상위에서 payload 메모이즈 |
| 백엔드가 비정상/미지원 config를 내려줌 | `chartValidator` 1차 검증 + fallback UI (앱 크래시 방지) |
| jsdom canvas 미지원으로 테스트 실패 | `Chart` 생성자 mock으로 lifecycle만 검증 |
| 번들 사이즈 증가 | `chart.js/auto` 대신 명시 등록(`chartSetup.ts`)으로 필요한 것만 포함 |
| recharts와 중복 차트 라이브러리 공존 | 본 작업은 chart.js만 도입. 통일 여부는 별도 과제로 분리 |
| 백엔드 `charts` 필드 미구현 상태 | 프론트 계약(타입)만 먼저 정의 → 백엔드 합의 후 연동. 필드 없으면 차트 미표시(무해) |

---

## 9. 다음 단계

- 설계 상세화가 필요하면: `/pdca design chat-chart-rendering`
- 바로 구현 시작 시: `/pdca do chat-chart-rendering` (TDD 순서 — Step 3·4 유틸/훅부터 Red → Green)
- 백엔드 `charts` 필드 계약은 `idt/` 측과 `/api-contract-sync`로 동기화 권장
