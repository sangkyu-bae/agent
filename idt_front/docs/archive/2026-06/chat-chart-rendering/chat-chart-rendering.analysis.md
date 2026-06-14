---
template: analysis
version: 1.2
feature: chat-chart-rendering
date: 2026-06-05
author: 배상규
project: idt_front
version_project: 0.0.0
design_doc: ../02-design/features/chat-chart-rendering.design.md
---

# chat-chart-rendering Gap Analysis Report

## Match Rate: 100%

```
┌─────────────────────────────────────────────┐
│  Design Match Rate: 100%   ✅                │
├─────────────────────────────────────────────┤
│  ✅ Match:            28 items (100%)        │
│  ⚠️ Missing design:    0 items               │
│  ❌ Not implemented:   0 items (in-scope)    │
└─────────────────────────────────────────────┘
```

설계와 구현이 완전히 일치한다. In-scope 갭 없음. 2개의 deferred 항목은 의도된 out-of-scope(미집계).

## 1. Analysis Overview

- Design: `docs/02-design/features/chat-chart-rendering.design.md`
- Plan: `docs/01-plan/features/chat-chart-rendering.plan.md`
- Implementation: `src/types/chart.ts`, `src/utils/chartValidator.ts`, `src/lib/chartSetup.ts`, `src/hooks/useChart.ts`, `src/components/chat/ChartRenderer.tsx`, `src/components/chat/MessageBubble.tsx`, `src/types/chat.ts`, `src/types/websocket.ts`
- Date: 2026-06-05

## 2. File Existence & Layer Assignment (§9.1, §11.1)

| Component | Designed Layer | Actual Location | Status |
|-----------|---------------|-----------------|--------|
| `ChartPayload`, `SUPPORTED_CHART_TYPES`, `SupportedChartType` | Domain | `src/types/chart.ts` | ✅ |
| `chartValidator` | Application (util) | `src/utils/chartValidator.ts` | ✅ |
| `chartSetup` | Infrastructure | `src/lib/chartSetup.ts` | ✅ |
| `useChart` | Presentation (hook) | `src/hooks/useChart.ts` | ✅ |
| `ChartRenderer` | Presentation | `src/components/chat/ChartRenderer.tsx` | ✅ |
| `MessageBubble` (mod) | Presentation | `src/components/chat/MessageBubble.tsx` | ✅ |
| `Message.charts` (mod) | Domain | `src/types/chat.ts` | ✅ |
| `ChatAnswerCompletedData.charts` (mod) | Domain | `src/types/websocket.ts` | ✅ |
| `chart.js@^4` dependency | — | `package.json` | ✅ |

모든 계획 파일 8개 + 의존성 존재. 테스트 파일 전부 존재: `chartValidator.test.ts`, `useChart.test.tsx`, `ChartRenderer.test.tsx`.

## 3. Detailed Checks

### 3.1 useChart lifecycle (§11.3) — ✅ Match
| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Create on mount with config | `new Chart(canvas, ...)` in `useEffect` | ✅ |
| Recreate on config change | `chartRef.current?.destroy()` 후 재생성; `[config]` dep | ✅ |
| Destroy on unmount | cleanup `destroy(); chartRef.current = null` | ✅ |
| Default responsive options 주입 | `responsive: true, maintainAspectRatio: false, ...config.options` | ✅ |
| canvas ref null guard | `if (!canvas \|\| !config) return` | ✅ |
| `ensureChartRegistered()` 선호출 | effect 최상단 | ✅ |

### 3.2 chartValidator (§6.1) — ✅ Match
| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Type 화이트리스트 | `SUPPORTED_CHART_TYPES.includes(...)` | ✅ |
| object/null guard | `if (!payload \|\| typeof payload !== 'object')` | ✅ |
| datasets 비어있지 않은 배열 | `Array.isArray(datasets) && datasets.length > 0` | ✅ |
| `toChartConfiguration` {type,data,options} 매핑 | 정확 패스스루 | ✅ |

### 3.3 ChartRenderer (§5.3, §5.4) — ✅ Match
| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Validation gate | `isValidChartPayload(payload)` | ✅ |
| `useMemo` config 안정화 | `useMemo(..., [valid, payload])` | ✅ |
| Fallback UI 텍스트/스타일 | `bg-zinc-50 ... text-zinc-500` + "차트를 표시할 수 없습니다." | ✅ |
| 컨테이너 스타일 (rounded-2xl border bg-white p-4 shadow-sm, height=320) | 일치 | ✅ |
| `<canvas ref={canvasRef}>` | 존재 | ✅ |
| Props/arrow fn/`export default` 하단 (§10.2) | 일치 | ✅ |

### 3.4 Contract fields (§3.2, §3.3) — ✅ Match
| Field | Spec | Implementation | Status |
|-------|------|----------------|--------|
| `Message.charts?: ChartPayload[]` | optional, 하위호환 | `src/types/chat.ts` | ✅ |
| `ChatAnswerCompletedData.charts?: ChartPayload[]` | optional, contract-only | `src/types/websocket.ts` | ✅ |
| `ChartPayload {type, data, options?}` | Chart.js native passthrough | `src/types/chart.ts` | ✅ |

### 3.5 MessageBubble integration position (§5.1) — ✅ Match
`message.content` 아래, `SourceCitation` 위에 차트 렌더. `charts.length > 0` 가드, `ChartRenderer` 매핑, `flex flex-col gap-3`. 설계 레이아웃(text → charts → sources)과 일치.

### 3.6 Test coverage vs §8.2 — ✅ Match
| Design test case | Present | Location |
|------------------|:-------:|----------|
| valid bar → true | ✅ | chartValidator.test.ts |
| unknown type → false | ✅ | chartValidator.test.ts |
| datasets missing → false | ✅ | chartValidator.test.ts |
| datasets [] → false | ✅ | chartValidator.test.ts |
| toChartConfiguration mapping | ✅ | chartValidator.test.ts |
| mount → Chart created once | ✅ | useChart.test.tsx |
| config change → destroy + recreate | ✅ | useChart.test.tsx |
| config null → no create | ✅ | useChart.test.tsx |
| unmount → destroy | ✅ | useChart.test.tsx |
| valid payload → canvas | ✅ | ChartRenderer.test.tsx |
| invalid payload → fallback | ✅ | ChartRenderer.test.tsx |

추가 테스트(§8.2 초과): `null/원시값 거부`, `options 보존`, responsive 기본 options 주입 검증. jsdom 제약(§8.1)대로 `vi.mock('chart.js')` 사용.

## 4. Clean Architecture Compliance — ✅ 100%

의존성 방향 위반 없음. Presentation → Application/Domain/Infra(lib) 단방향, Domain은 chart.js 타입만 재노출(순수). import 순서(external → `@/` → `import type`) 전 파일 준수.

## 5. Convention Compliance — ✅ ~100%

컴포넌트 PascalCase, 훅/유틸/타입 camelCase, 상수 UPPER_SNAKE, arrow fn + `export default` 하단, Props interface 상단, `@/` 절대경로 — 전부 준수.

## 6. Intentional Out-of-Scope (미집계)

| Item | Status | Note |
|------|--------|------|
| 백엔드 `charts` 필드 emit | Contract-only (Plan §3.2) | 프론트 타입 정의 완료, 백엔드 연동 대기 |
| Stream-receiver의 `charts` → `Message` 매핑 | Deferred follow-up | `ChatAnswerCompletedData.charts`는 존재하나, WS 어댑터가 아직 커밋되는 assistant `Message`로 매핑하지 않음. 설계 §3.3대로 "백엔드 합의 후" 진행. 설계 갭 아님 |
| recharts 제거/마이그레이션 | Out-of-scope | recharts@3.8.1 공존 유지 |

## 7. Recommended Actions

### Follow-up (백엔드가 `charts`를 내려주기 시작할 때)
1. 채팅 WS 어댑터/chatStore에서 `chat_answer_completed` 수신 시 `data.charts`를 커밋되는 assistant `Message.charts`로 복사. 이것이 end-to-end 차트 표시를 위한 유일한 남은 배선이며, 프론트 측은 모두 준비됨.

### Optional polish (non-blocking)
2. `useChart`의 `new Chart(...)`를 try/catch로 감싸 chart.js 내부 throw를 fallback 경로로 전환 고려 (설계 §6.1의 "(선택)"). 현재 validator는 type/datasets는 커버하나 scale-config 불일치는 미커버.

## 8. Conclusion

설계-구현 일치 — **Match Rate 100%** (전 in-scope 항목). 모든 계획 파일이 설계 레이어에 존재하고, `useChart` lifecycle / validator / renderer / contract / MessageBubble 통합이 모두 설계에 부합하며, 테스트 커버리지가 §8.2 이상. 남은 작업은 명시적 out-of-scope인 백엔드 emit과 deferred stream-receiver 매핑(follow-up)뿐. 설계 문서 수정 불필요.
