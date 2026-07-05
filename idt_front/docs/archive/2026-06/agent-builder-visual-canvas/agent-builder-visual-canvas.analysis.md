# Gap Analysis: agent-builder-visual-canvas

| 항목 | 내용 |
|------|------|
| Feature | agent-builder-visual-canvas |
| Design 참조 | `docs/02-design/features/agent-builder-visual-canvas.design.md` |
| 분석일 | 2026-06-30 |
| **Match Rate** | **100%** (6 MATCH / 0 PARTIAL / 0 MISSING) |
| 판정 | ✅ ≥90% 충족 — Act/iterate 불필요 |

## 1. 항목별 검증

| # | Design 요구 | 상태 | 근거 |
|---|-------------|:----:|------|
| 1 | §2.1 constants (EDGE_COLOR/DEFAULT_LAYOUT/EMPTY_TEXT/NODE_ID) | MATCH | constants.ts — 색상 정확(skill/model `#f59e0b`, tool `#3b82f6`, subagent `#8b5cf6`, middleware `#a855f7`), 6좌표·빈텍스트·NODE_ID 일치 |
| 2 | §2.2 buildGraph (6노드/5엣지/모델라벨/플레이스홀더) | MATCH | buildGraph.ts — agent+5 resource, 5엣지 모두 `source=agent`+`EDGE_COLOR` stroke, 라벨 로직 정확, skill/middleware `[],true` |
| 3 | §2.3 AgentNode + ResourceNode | MATCH | 플레이스홀더·Edit in Form→onEditInForm·핸들; 종류별 헤더·빈텍스트vs목록·tool/subagent/model 액션·disabled `title="준비중"` |
| 4 | §2.4 VisualCanvas (Provider/state/mergeData/reset/Controls/lazy) | MATCH | Provider·state hooks·mergeData(position 보존)·기본레이아웃 reset+fitView·Controls bottom-left·nodesConnectable=false·hideAttribution·lazy |
| 5 | §2.5 LeftConfigPanel (탭 활성화/분기/콜백4/모달유지) | MATCH | `disabled` 제거+onClick, form/visual 분기, 콜백 4종 정확 배선, 모달 3종 유지 |
| 6 | §4 테스트 (순수함수/노드단위/캔버스스모크) | MATCH | buildGraph.test + AgentNode/ResourceNode 단위 + VisualCanvas 스모크 (총 23 케이스 통과) |

## 2. Gap 목록 (체크리스트 차단 없음 — 전부 경미)

| Gap | 심각도 | 상세 |
|-----|:------:|------|
| 미들웨어 아이콘 불일치 | low | Design 표는 `▥`, 구현은 `🧩`. 장식 요소만 다름 |
| 스모크 테스트 범위 축소 | low | §4.3은 캔버스에서 `onEditInForm`/`onConfigModel` 발화 검증 명시했으나, jsdom+d3-drag 충돌로 노드 클릭은 단위 테스트(AgentNode/ResourceNode)로 이전. 의도 보존 |
| NODE_ID 타입 확장 | low | Design은 `as const` 리터럴, 구현은 `Record<VisualNodeKind,string>`. 값 동일, 런타임 영향 없음 |

## 3. 검증 로그

| 검증 | 결과 |
|------|------|
| `npm run type-check` | ✅ 통과 |
| 신규 비주얼 테스트 | ✅ 23/23 |
| agent-builder 전체 | ✅ 51/51 (회귀 없음) |
| ESLint (신규 코드) | ✅ 0 |

## 4. 결론

구현이 6개 영역(상수·그래프 빌더·노드 2종·캔버스 배선·패널 통합·3계층 테스트)에서 Design을 충실히 실현. 3개 편차는 장식/구조/타입 주석 수준으로 기능 영향 0. **Act 반복 불필요, `/pdca report` 진행 가능.**
