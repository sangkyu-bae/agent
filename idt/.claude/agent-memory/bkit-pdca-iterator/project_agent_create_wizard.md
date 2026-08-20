---
name: project-agent-create-wizard-iteration1
description: agent-create-wizard PDCA iteration 1 (2026-08-20) — 프론트 Critical 2 + Important 5 수정 완료, 잔여 항목과 SSE 테스트 제약
metadata:
  type: project
---

agent-create-wizard Act(iterate) 1회차 완료 (2026-08-20, branch `feature/agent-create-wizard`).
Gap 분석 기준 Overall 89% → 프론트 테스트 자산 결손(F-1/F-2/F-7)과 UX/실패 가시성 결함(F-4/F-5/F-6), 상수 정본화(F-3)를 모두 반영.

**Why:** 프론트 Structural 68%·Runtime 70%의 원인이 기능 결손이 아니라 **테스트 자산 결손**이었다.
F-5(SSE 실패 시 진행바가 '대기중'으로 회귀)는 이 기능의 WHY(생성 과정의 블랙박스 제거)와 정면 충돌해 우선 수정 대상이었다.

**이번 사이클에서 손대지 않기로 한 것 (다음 사이클 후보):**
- SC-2 실서버 수동 E2E (`GET /api/v1/agents/{id}` 일치) — MSW로 대체 불가, 파이프라인 이월 #15와 동시 소화 대상
- Minor gap: F-9(MSW 기본 핸들러) · F-10(`llm_model_id` 핸드오프) · F-12(실시간 글자수·LoadingButton) · F-13(`MAX_CLARIFY_ROUNDS` 하드코딩) · 백엔드 B-2/B-3/B-4/B-5
- Design 문서 drift 4건(analysis §10) — "코드가 진실" 규칙상 문서 갱신은 사용자 결정 대기

**검증 baseline (2026-08-20 실측):** 프론트 전체 스위트는 clean 이 아니다.
- vitest: 9 failed / 1052 passed — ChatPage(1)·UpdateScopeModal(6)·CreateCollectionModal(1)·DatasetsTab(1). 위저드와 무관하며 stash 대조로 확인됨
- `npx tsc -b`: 197줄 오류가 baseline. 앱 tsconfig 가 `types:["vite/client"]` 만 로드해 전역 vitest 심볼이 없는 기존 테스트 파일들 + 무관 소스 5종 + vite.config.ts
→ 회귀 판정은 **개수 diff**로만 해야 한다. "전량 green" 을 기대하면 잘못된 결론이 난다.

**함정 (재현에 시간을 쓰지 말 것):** MSW 로는 "SSE 스트림이 받다가 끊김"을 재현할 수 없다.
인터셉터가 본문을 버퍼링해 `controller.error()` 이전 청크가 소비자에게 도달하지 않고(`pull` 분할도 동일), 결국 steps 가 빈 채로 온다.
`useAgentPipelineStream` 같은 스트림 소비 훅은 `agentPipelineService.stream` 경계에서 `vi.mock`(+`vi.hoisted`)으로 검증할 것.

**How to apply:** 이 기능을 다시 다루면 `/pdca analyze agent-create-wizard` 로 재측정한 뒤,
90% 도달 시 `/pdca report agent-create-wizard`. 남은 미달 축은 대부분 실서버 검증(SC-2)에 묶여 있다.
관련: [[project-agent-user-context-iteration1]]
