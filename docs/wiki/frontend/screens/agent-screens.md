---
title: 화면↔API 지도 — 에이전트 화면 (스토어·빌더·워크스페이스)
status: draft
source_type: conversation
source_refs:
  - idt_front/src/App.tsx (라우트 선언)
  - idt_front/src/pages/AgentBuilderPage/index.tsx
  - idt_front/src/constants/api.ts
confidence: 0.85
version: 1
created: 2026-07-21
updated: 2026-07-21
verified_at: 6cc25656
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

## AgentWorkspacePage — `/agents/:agentId/workspace`

에이전트 구성(프롬프트/도구/스킬/지식/스케줄)을 폴더형으로 읽기 전용 열람.

- 진입: `idt_front/src/pages/AgentWorkspacePage/index.tsx`
- 훅: `useAgentStore`(상세), `useToolCatalog`, `useAgentSkills`, `useWiki`
- 백엔드: 신규 API 없음 — 기존 상세/카탈로그/스킬/위키 API 재조합 (agent-workspace-view: 백엔드 diff 0)

## 연관

- 실행 관측(런 상세)은 관리자 화면([[admin-screens]])의 `/admin/agent-runs` 참조
- 에이전트별 지식 열람은 [[wiki-screens]]의 AgentKnowledgePage 참조
