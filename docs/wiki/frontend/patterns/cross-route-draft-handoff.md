---
title: 라우트 간 1회성 상태 핸드오프 — 생명주기 계약 G1~G5
status: draft
source_type: conversation
source_refs:
  - idt_front/src/store/agentDraftStore.ts (persist 금지 · consumePendingIntent 원자적 읽기+비우기)
  - idt_front/src/pages/AgentBuilderPage/index.tsx:111-138 (consumedIntentRef 가드 + settled 대기)
  - idt_front/src/utils/composeDraftToForm.ts (초안→폼 변환 단일 구현, Fix 탭과 공유)
  - idt_front/src/__tests__/integration/agentCreateEntry.test.tsx (G3·G4·G5 시나리오)
  - docs/archive/2026-08/agent-create-entry/agent-create-entry.report.md (§5.2 G1~G5, §6.1)
confidence: 0.85
version: 1
created: 2026-08-14
updated: 2026-08-14
verified_at: 12c69b4
---

# 라우트 간 1회성 상태 핸드오프 — 생명주기 계약 G1~G5

## 문제

`/agent-builder/new`(진입 화면)에서 만든 초안을 `/agent-builder`(스튜디오) 폼에
넘겨야 한다. 라우트가 다르니 props로 못 넘기고, 전역 스토어를 쓰면 곧바로
**유령 초안** 문제가 생긴다 — 새로고침 후 옛 초안 부활, 같은 초안 두 번 적용,
뒤로가기 후 재적용, 로딩 중 적용으로 인한 **조용한 실패**.

## 검증된 사실

핸드오프 스토어에 5개 규칙을 문서로 먼저 못 박고 각 규칙에 테스트를 1:1로 붙인
결과, Check 단계에서 5/5가 초록임을 즉시 증명할 수 있었다.

| ID | 규칙 | 구현 | 검증 |
|----|------|------|------|
| **G1** | `persist` 미들웨어 금지, 브라우저 스토리지 미사용 | 순수 `create()` | 스토어 테스트가 `localStorage.length === 0 && sessionStorage.length === 0` 단언 |
| **G2** | 읽기+비우기를 **한 호출 안에서** (`consumePendingIntent`) | `get()` → 있으면 즉시 `set(null)` → 반환 | 2회 연속 호출 시 2번째 `null` |
| **G3** | 진입 화면 mount 시 clear | `clearPendingIntent()` | 통합 시나리오 "유령 초안" |
| **G4** | mount 후 1회 + `useRef` 가드, **selector 구독 금지** | `useAgentDraftStore.getState()`로만 접근 | 재적용 없음 시나리오 |
| **G5** | 의존 쿼리가 **settled된 뒤에만** 소비 | `if (isToolsLoading \|\| isModelsLoading) return;` | 80ms 지연 핸들러 시나리오 |

### 왜 G4에서 selector 구독이 금지인가

스토어를 selector로 구독하면 `consume` → 값 변경 → 리렌더 → effect 재실행 →
재소비 루프가 생긴다. **소비형 스토어는 구독하지 않고 `getState()`로만 읽는다.**

### 왜 G5가 가장 위험한가

초안의 도구·모델은 카탈로그(`catalogTools`, `models`)로 **역매핑**되어야 폼에
들어간다. 로딩 중에 변환하면 매핑이 **에러 없이 조용히 실패**해 빈 도구 칩과
원시 모델 id가 남는다. 문서화하지 않았으면 놓쳤을 함정이고, 화면상 "그냥 좀
비어 보이는" 상태라 QA도 잡기 어렵다.

### 새로고침 시 초안 유실은 버그가 아니다

G1의 직접 귀결. "새로고침/재로그인 후 옛 초안이 되살아나는 경로를 아예 만들지
않는다"가 목적이므로, 유실은 **정의된 동작**이다. 스토어 주석에 그렇게 적혀 있다.

### 변환 로직은 단일 구현을 공유한다

`composeDraftToForm`은 진입 화면과 기존 Fix 탭이 함께 쓴다. 기존 페이지의
40줄 인라인 로직을 4줄 위임 래퍼로 줄이는 리팩터가 선행됐고, 이 module을 먼저
끝내고 기존 테스트 초록을 확인한 뒤 진행해 회귀 추적 비용이 0이었다.

### 공유 컴포넌트는 고치지 말고 형제를 추가한다

HITL 스킵 UI는 Design상 `ClarifyQuestionCard` 안에 버튼 2개였으나, 카드를 고치면
Fix 탭까지 영향을 받으므로 **카드는 무수정**하고 진입 화면에 형제 버튼을 추가했다.
설계와 구현이 어긋나면 구현을 맞추기보다 **Design 문서를 갱신**하는 쪽이 기본값.

## 다음에 적용하는 법

1. 라우트 간 상태 핸드오프가 생기면 **코드보다 먼저 G1~G5에 해당하는 계약을 적고**
   각 항목에 테스트를 1:1로 붙인다. (import → 파일 → 초안 → 스튜디오 같은 후속
   기능도 같은 경로를 재사용하도록 설계돼 있다.)
2. 소비형 전역 상태는 `persist` 금지 + 원자적 consume + `getState()` 접근 3종 세트.
3. **파생 데이터가 다른 쿼리에 의존하면 settled 가드를 필수로.** "조용히 빈 값"이
   되는 변환은 전부 이 패턴 대상이다.
4. 진입 화면 신설 시 기존 진입 버튼들은 **회귀 테스트로 고정**하고 목적지를 바꾸지
   않는다 (숙련 사용자 경로 보존).

## 관련 문서

- 화면↔API 지도: `frontend/screens/agent-screens.md`
- HITL 왕복 계약: `backend/patterns/stateless-hitl-clarification.md`
- 거짓 초록 게이트: `conventions/false-green-quality-gates.md`
