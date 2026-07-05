# Report: Agent Builder Visual Canvas

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | agent-builder-visual-canvas |
| 기간 | 2026-06-30 (Plan→Report 단일 세션) |
| 영역 | 프론트엔드 단독 (idt_front) — 백엔드 변경 없음 |
| Match Rate | **100%** |
| 의존성 추가 | `@xyflow/react@12.11.1` |
| 코드 규모 | 구현 421줄(6파일) + 테스트 270줄(4파일) |

### 1.3 Value Delivered

| 관점 | 설명 | 실제 결과 |
|------|------|-----------|
| **Problem** | 비주얼 탭이 `disabled`(준비중)로 막혀 에이전트 구성을 폼으로만 확인 | 탭 활성화 완료 — 노드 그래프로 전체 구조 즉시 파악 |
| **Solution** | 폼 상태를 React Flow 노드 그래프로 렌더 + 노드 버튼이 기존 모달 재사용해 양방향 동기화 | 6노드(에이전트 허브 + 스킬/도구/서브/미들웨어/모델) + 5색상 점선 엣지, 단일 `form` 소스 공유로 양방향 자동 동기화 |
| **Function UX Effect** | 색상별 엣지·드래그·줌·기본 레이아웃 리셋·모달 연동 | 도구/모델/서브에이전트 노드 → 기존 모달 open, Edit in Form → 폼 탭 전환, `mergeData`로 드래그 위치 보존 |
| **Core Value** | Agent Builder 사용성 향상 + 시각화 확장 기반 | 스킬·미들웨어 플레이스홀더로 향후 확장 지점 확보, RF 테스트 패턴 정립 |

---

## 2. PDCA 사이클 요약

| 단계 | 산출물 | 결과 |
|------|--------|------|
| Plan | `01-plan/features/agent-builder-visual-canvas.plan.md` | 4개 설계 결정 확정(라이브러리/상호작용/플레이스홀더/레이아웃) |
| Design | `02-design/features/agent-builder-visual-canvas.design.md` | 파일별 시그니처·상수·시퀀스·테스트 전략 |
| Do | 구현 6파일 + 테스트 4파일 | TDD Red→Green, type-check/lint 통과 |
| Check | `03-analysis/agent-builder-visual-canvas.analysis.md` | gap-detector Match Rate **100%** (6/6 MATCH) |
| Report | 본 문서 | 완료 |

---

## 3. 구현 결과

### 3.1 신규 파일 (`src/components/agent-builder/visual/`)

| 파일 | 줄 | 역할 |
|------|----|------|
| `constants.ts` | 65 | NODE_ID·EDGE_COLOR·DEFAULT_LAYOUT·EMPTY_TEXT·RESOURCE_META |
| `buildGraph.ts` | 78 | `buildNodes`/`buildEdges`/`buildModelLabel` 순수 함수 |
| `VisualCanvas.tsx` | 134 | ReactFlow 통합 + Controls + 기본 레이아웃 + `mergeData`(위치 보존) |
| `nodes/AgentNode.tsx` | 55 | 중앙 허브 노드 (Edit in Form) |
| `nodes/ResourceNode.tsx` | 81 | 스킬/도구/서브/미들웨어/모델 공통 카드 |
| `nodes/index.ts` | 8 | `nodeTypes` 매핑 |
| 테스트 4파일 | 270 | 23 케이스 |

### 3.2 수정 파일

- `LeftConfigPanel.tsx` — 비주얼 탭 `disabled` 제거 + 탭 분기 + 콜백 4종 + `lazy` 지연 로딩
- `package.json` — `@xyflow/react` 추가

---

## 4. 검증 결과

| 검증 | 결과 |
|------|------|
| `npm run type-check` | ✅ 통과 |
| 신규 비주얼 테스트 | ✅ 23/23 |
| agent-builder 전체 | ✅ 51/51 (회귀 없음) |
| ESLint (신규 코드) | ✅ 0 |
| gap-detector Match Rate | ✅ 100% |

---

## 5. 학습 / 기술 노트

1. **React Flow + jsdom 제약** — 드래그 가능한 노드를 `userEvent.click` 하면 d3-drag가 jsdom에서 크래시. 노드 콜백은 `<ReactFlowProvider>` 단위 테스트로, 캔버스는 렌더 스모크로 분리. `ResizeObserver` 폴리필 필수, `globalThis.`(빌드 `tsc -b` 호환). → CC 메모리 `reactflow-jsdom-test-gotchas` 기록.
2. **단일 소스 동기화** — 폼·비주얼이 같은 `form` prop을 공유해 별도 sync 로직 없이 양방향 반영. 변경은 항상 `onChange`.
3. **position 보존** — 폼 변경 시 `mergeData`로 노드 `data`만 교체, 드래그 좌표 유지.

---

## 6. 잔여 / 후속 작업

| 항목 | 상태 | 비고 |
|------|------|------|
| 스킬 노드 실제 연동 | 후속 | 현재 플레이스홀더. 데이터 모델 확장 또는 우측 AgentSkillPanel 연동 시 활성화 |
| 미들웨어 노드 실제 연동 | 후속 | LangChain 미들웨어 기능 구현 후 |
| 노드 위치 영속화 | 범위 외 | 현재 새로고침 시 초기화(설계 결정) |
| 미들웨어 아이콘 글리프 | 경미 | Design `▥` vs 구현 `🧩` (기능 영향 없음) |

---

## 7. 결론

Plan→Check 전 단계를 단일 세션에서 완료하고 **Match Rate 100%**를 달성. 비주얼 탭이 완전 인터랙티브하게 동작하며, 폼과 양방향 동기화·드래그·줌·기본 레이아웃을 지원한다. 회귀 없음, 신규 테스트 23건 통과. 후속으로 `/pdca archive agent-builder-visual-canvas` 가능.
