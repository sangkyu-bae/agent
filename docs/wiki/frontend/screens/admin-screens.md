---
title: 화면↔API 지도 — 관리자 화면 (/admin/*)
status: draft
source_type: conversation
source_refs:
  - idt_front/src/App.tsx (AdminRoute + AdminLayout 라우트 블록)
  - idt_front/src/constants/api.ts (ADMIN_* 블록)
  - idt/docs/archive/2026-07/admin-dashboard/admin-dashboard.report.md
confidence: 0.85
version: 1
created: 2026-07-21
updated: 2026-07-21
verified_at: 6cc25656
---

모든 `/admin/*` 라우트는 `AdminRoute`(비admin이면 `/`로 리다이렉트) + `AdminLayout` 하위에 선언된다.

| 라우트 | 화면 한 줄 | 훅 | 주 엔드포인트 → 백엔드 라우터 |
|---|---|---|---|
| `/admin/dashboard` | 운영 대시보드(적재량·KB별·최근문서·헬스+usage 위젯) | `useAdminDashboard`, `useAgentRunAdmin` | `ADMIN_DASHBOARD_*`, `ADMIN_USAGE_*` → `admin_dashboard_router`, `agent_run_router` |
| `/admin/users` | 가입 승인/거절 + 사용자 직접 등록 | `useAdminUsers` | `ADMIN_USERS_*`, `ADMIN_USER_APPROVE/REJECT` → `admin_user_router` |
| `/admin/departments` | 부서 CRUD + 사용자-부서 배정 | `useDepartments` | `ADMIN_DEPARTMENTS`, `ADMIN_USER_DEPT_*` → `department_router` |
| `/admin/mcp-servers` | MCP 서버 레지스트리 관리(연결 테스트 포함) | `useMcpServers` | `MCP_SERVERS`, `MCP_SERVER_TEST` → `mcp_registry_router` |
| `/admin/llm-models` | LLM 모델 등록/가격/비활성화 | `useLlmModels` | `LLM_MODELS`, `LLM_MODEL_PRICING` → `llm_model_router` |
| `/admin/chunking-profiles` | 청킹 프로파일 관리 + 요약 LLM 배정 | `useChunkingProfiles`, `useLlmModels` | `ADMIN_CHUNKING_PROFILES*` → `admin_chunking_router` |
| `/admin/skills` | 스킬 정의 관리 | `useSkills` | `SKILLS*` → `skill_builder_router` |
| `/admin/ragas` | RAGAS 평가 대시보드/런/테스트셋 | (서비스 직접: `adminRagasService`) | `ADMIN_RAGAS_*` → `admin_ragas_router` |
| `/admin/agent-runs`, `/admin/agent-runs/:runId` | 에이전트 런 관측(비용/토큰/스텝 드릴다운) | `useAgentRunAdmin` | `ADMIN_AGENT_RUNS`, `ADMIN_AGENT_RUN_DETAIL` → `agent_run_router` |
| `/admin/wiki` | 제품 위키 큐레이션(승인/반려/폐기/distill) | `useWiki`, `useAgentStore`, `useRagToolConfig` | `WIKI_*` → `wiki_router` ([[wiki-screens]]) |

## 계약 주의 (코드만 봐서는 놓치기 쉬운 것)

- `/admin/chunking-profiles`의 수정은 **PUT 전체 교체 + 프리필** 패턴이다 — 부분 수정 아님 (chunking-profile-admin-ui). `summary_llm_model_id`는 FK 없는 소프트 참조 ([[erd-kb]]).
- `/admin/dashboard`의 적재량은 MySQL `document_metadata` 메타 기준이다. Qdrant/ES 실적재량 대사는 [[e2e-carryover-checklist]]로 이월된 상태.
- 평가 관측 위젯(`ADMIN_EVAL_AGENTS`, `ADMIN_EVAL_RECENT_NEGATIVE` → `eval_router`)은 agent-eval-gate 계열 — 집계 0건이면 None 반환 계약 ([[feedback-toggle-row-delete]]).
