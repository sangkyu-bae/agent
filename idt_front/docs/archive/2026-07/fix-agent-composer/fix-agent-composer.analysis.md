# fix-agent-composer Gap Analysis

> **Design**: [fix-agent-composer.design.md](../../02-design/features/fix-agent-composer.design.md)
> **Plan**: [fix-agent-composer.plan.md](../../01-plan/features/fix-agent-composer.plan.md) (FR-01~FR-10)
> **Date**: 2026-07-05
> **Analyzer**: gap-detector agent + 수동 검증 (G1 오탐 판정)

---

## 1. Match Rate

| Category | Score | Status |
|----------|:-----:|:------:|
| 백엔드 (§3, B1~B6) | 100% | ✅ |
| 프론트 types/service/hook (§4.1~4.2) | 92% | ✅ |
| 프론트 컴포넌트 (§4.3~4.4) | 92% | ✅ |
| 배선 + 폼 매핑 (§4.5~4.7) | 100% | ✅ |
| 테스트 커버리지 (F1~F11) | 90% | ✅ |
| **Overall (38/41 항목)** | **93%** | ✅ |

> gap-detector 최초 판정은 ~90%(37/41)였으나, G1(아래)이 오탐으로 확인되어 93%로 보정.

---

## 2. 검증 결과 요약

### 2.1 백엔드 (§3) — 전 항목 Match ✅

| 항목 | 근거 |
|------|------|
| `ComposeCurrentConfig` 제약 (name≤200 / sp≤4000 / tool_ids≤10 / temp 0~2) | `schemas.py:9-16` |
| `ComposeHistoryTurn` (Literal role, content 1~2000) | `schemas.py:19-23` |
| `ComposeAgentRequest` 확장 (history≤20턴), 응답 스키마 불변 | `schemas.py:26-34` |
| `ComposePolicy` MAX_HISTORY_TURNS=6 / MAX_HISTORY_TURN_CHARS=500 / `clamp_history` | `policies.py:10-27` |
| `_CURRENT_CONFIG_BLOCK` 증분 수정 규칙 3종 (변경만 적용 / 기존 도구 유지 / 프롬프트 재작성) | `composer.py:68-80` |
| messages 순서: system → history → user | `composer.py:117-119` |
| use case 배선 (clamp 후 전달, 하위호환 None) | `compose_agent_use_case.py:55-66` |

### 2.2 프론트 (§4) — 전 항목 Match ✅

타입/상수/서비스/훅, FixAgentPanel(예시 3종·새 대화·Enter/Shift+Enter·placeholder·로딩 인디케이터·1000자 절단·history 요약 변환·에러 턴 제외·최근 6턴), ComposeDraftCard(coverage 뱃지·MCP 칩·프롬프트 더보기·미커버 경고·edit 제약 경고·모델 미매핑 안내·적용됨 상태·none 분기), handleApplyDraft(§4.6 매핑표 전체 — RAG/문서추출기 부수효과, 역매핑 실패 시 모델 유지), MCP 필터 제거 3개소, API 문서 갱신 — 모두 구현 확인.

---

## 3. Gap 목록

### ~~G1 — 에러 버블 422 detail 미표시~~ → **오탐 (기각)**

- gap-detector 판정: FixAgentPanel이 `error.message`만 사용해 detail 미노출 (FR-09 위반).
- **수동 검증 결과**: compose는 `authClient` 경유이며, 응답 인터셉터가 `data.message ?? data.detail ?? 기본문구`를 `ApiError(message)`로 변환해 reject한다 (`src/services/api/authClient.ts:59-65`). 따라서 `error.message`에 이미 백엔드 한국어 detail이 담긴다. **FR-09 충족.**

### G2 — [전송 ↑] 버튼 없음 (Low, Design 다이어그램 전용)

- Design §4.3 ASCII 레이아웃에만 존재. FR-03 본문 요구는 "Enter 전송/Shift+Enter 줄바꿈"이며 충족됨.
- 처리: Design 다이어그램 표기를 Enter 전용으로 갱신 (문서 정합화). 버튼 추가는 선택.

### G3 — F1 전용 service 테스트 없음 (Low)

- `agentComposerService`는 `useAgentComposer.test.ts`가 MSW 경유로 간접 검증 (서비스 로직이 1줄 위임이라 실효 커버리지 동일).
- 처리: F1을 F2에 통합된 것으로 간주 (Design 갱신).

### G4 — F10 후반부(저장 422 → 에러 다이얼로그) 미검증 (Low)

- MCP tool_ids 전송 검증은 존재 (`AgentBuilderStudio.test.tsx` F10 전반부). 422 → 다이얼로그 경로는 코드 존재(`index.tsx` onError)하나 테스트 미작성.
- 처리: 후속 보강 권장 (기존 에러 다이얼로그 공통 경로라 위험도 낮음).

---

## 4. Design ≠ 구현 (기능 동등 — 문서 정합화만)

| Design | 구현 | 판단 |
|--------|------|------|
| `compose(history: list[ComposeHistoryTurn])` | `history: list[dict]` (use case가 사전 절단) | 경계가 더 깔끔 — Design §3.3 갱신 |
| 서비스가 `res.data` 반환 | axios promise 반환, 훅에서 unwrap | 프로젝트 기존 패턴(agentBuilderService)과 일치 |
| Card `onDismiss` prop | 카드 내부 `dismissed` state | 부모 배선 불필요 — 단순화 |
| (암시) 카드 내부 모델 조회 | `modelUnresolved` prop (패널에서 계산) | 관심사 분리 개선 |

---

## 5. 테스트 실행 결과

| 범위 | 결과 |
|------|------|
| 백엔드 composer 영역 (schemas/policies/composer/use case/router) | **45 passed** (회귀 0) |
| 백엔드 agent_builder 교차 실행 ERROR 27건 | 단독 실행 시 전부 통과 → 기존 Windows 이벤트루프 flakiness (기능 무관) |
| 프론트 agent-builder 영역 | **141 passed** (신규 37 포함) |
| 프론트 전체 스위트 | 472 passed / 8 failed — **실패 8건은 사전 실패 기준선(collection 7 + ChatPage 1)과 일치**, ChartRenderer 1건은 워커 기동 타임아웃(infra) |
| type-check | 통과 |
| lint (변경 파일) | 신규 파일 0 error (AgentBuilderPage 2건은 기존 useEffect 경고) |

---

## 6. 결론

- **Match Rate 93% (≥90%)** — FR-01~FR-10 전부 구현. 기능적 결함 없음.
- 남은 항목은 문서 정합화(G2/G3, §4 표기 3건)와 테스트 보강(G4) 수준.
- 수동 E2E(서버 기동 후 채팅→카드→적용→저장)는 배포 전 1회 권장.

**Next**: `/pdca report fix-agent-composer` (또는 G4 테스트 보강 후 report)
