---
title: 화면↔API 지도 — 에이전트 화면 (스토어·빌더·워크스페이스)
status: draft
source_type: conversation
source_refs:
  - idt_front/src/App.tsx (라우트 선언)
  - idt_front/src/pages/AgentBuilderPage/index.tsx
  - idt_front/src/constants/api.ts
  - idt_front/docs/archive/2026-08/utility-page/utility-page.report.md
  - idt/docs/archive/2026-08/builtin-tools/builtin-tools.report.md
  - docs/archive/2026-08/fix-agent-planner-hitl/fix-agent-planner-hitl.report.md (Fix 탭 HITL)
confidence: 0.85
version: 3
created: 2026-07-21
updated: 2026-08-06
verified_at: 18fd521e
---

## AgentStorePage — `/agent-store`

에이전트 마켓플레이스(전체공개/부서별/내 에이전트, 구독·포크).

- 진입: `idt_front/src/pages/AgentStorePage/index.tsx`
- 훅: `useAgentStore`
- 엔드포인트: `AGENT_STORE_LIST/DETAIL/SUBSCRIBE/FORK/MY/FORK_STATS`
- 백엔드: `agent_builder_router` → `agent_definition` + `user_agent_subscription` ([[erd-agent]])

## AgentBuilderPage — `/agent-builder`

에이전트 생성/수정 폼 + Fix(자연어 조합) 탭 + 스케줄 관리.

- 진입: `idt_front/src/pages/AgentBuilderPage/index.tsx`
- 훅: `useAgentBuilder`, `useToolCatalog`, `useLlmModels`, `useAgentSchedules`, (`useAgentComposer` — Fix 탭)
- 엔드포인트: `AGENT_BUILDER_CREATE/DETAIL/UPDATE/DELETE`, `AGENT_AVAILABLE_SUB_AGENTS`, `AGENT_COMPOSE`(무저장 초안), `TOOL_CATALOG`, `LLM_MODELS`, `AGENT_SCHEDULES*`
- 백엔드: `agent_builder_router` / `agent_composer_router` / `agent_schedule_router` / `tool_catalog_router`
- 계약 주의: 도구 ID는 카탈로그/폼 표기(`internal:{id}`, `mcp:{srv}:{tool}`)와 저장 표기(`{id}`, `mcp_{srv}`)가 다르다 — 경계를 넘길 때 반드시 변환 (agent-tool-id-dual-namespace, MEMORY 선례)
- 계약 주의: 수정 가능 필드 추가는 스키마+apply_update+repo update()+DI 4곳 세트 — repo 누락 시 조용히 미저장 (agent-repo-update-column-whitelist 선례)
- 계약 주의: 빌트인 도구는 폼에서 "기본" 배지+기본 선택으로 표시되고, 해제는 전용 상태 `excludedBuiltinTools`(→ 요청 필드 `exclude_builtin_tool_ids`)로만 가능하다. Fix 초안 적용은 이 상태에 접근하지 않는다(불변) — [[builtin-tools-optout-channel]]
- 계약 주의: compose 응답은 `status==='needs_clarification'`이면 질문 카드(`ClarifyQuestionCard`)를 띄우고, 답변 시 **질문 텍스트 에코백+라운드 번호**를 동봉해 재호출한다(`FixAgentPanel.tsx`의 `sendCompose`/`pendingClarify`). 신규 응답 필드(`status`/`questions`/`plan_summary`)는 전부 optional — 구형 mock/응답 호환. 상세는 [[stateless-hitl-clarification]]

## UtilityPage — `/tool-connection`

플랫폼 카탈로그 읽기 전용 열람 (탭 4종: 도구/모델/미들웨어/스킬 + 검색·유형 필터·새로고침).

- 진입: `idt_front/src/pages/UtilityPage/index.tsx` (+`UtilityCard.tsx`)
- 훅: 기존 3종 재사용 — `useToolCatalog()`, `useLlmModels(true)`, `useSkills({scope:'all', size:100})`. **전용 백엔드 API 없음** (백엔드 변경 0으로 완결된 화면)
- 미들웨어 탭은 "준비 중" 빈 상태 — 전용 API 자체가 없다 (후속: middleware-catalog)
- 함정: `skills/list`는 **POST**다 — MSW 핸들러를 `http.get`으로 쓰면 조용히 실패 ([[router-map]])
- 이력: 구 `ToolConnectionPage`(100% 목데이터)·`toolService.ts`·`types/tool.ts`는 **삭제됨** — 참조 금지. 목데이터 화면을 만나면 백엔드 `src/api/routes/` 스캔부터 (실 API가 이미 있는 경우가 많다)

## AgentWorkspacePage — `/agents/:agentId/workspace`

에이전트 구성(프롬프트/도구/스킬/지식/스케줄)을 폴더형으로 읽기 전용 열람.

- 진입: `idt_front/src/pages/AgentWorkspacePage/index.tsx`
- 훅: `useAgentStore`(상세), `useToolCatalog`, `useAgentSkills`, `useWiki`
- 백엔드: 신규 API 없음 — 기존 상세/카탈로그/스킬/위키 API 재조합 (agent-workspace-view: 백엔드 diff 0)

## 연관

- 실행 관측(런 상세)은 관리자 화면([[admin-screens]])의 `/admin/agent-runs` 참조
- 에이전트별 지식 열람은 [[wiki-screens]]의 AgentKnowledgePage 참조
