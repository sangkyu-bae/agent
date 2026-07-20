# agent-workspace-view Design Document

> **Plan**: `docs/01-plan/features/agent-workspace-view.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **소스 기준**: master 실코드 (types/agentStore.ts WorkerInfo·AgentDetail · agent_builder_router.py:572 · useAgentStore/useAgentSkills/useWiki 훅 · AgentKnowledgePage · AgentDetailModal)

---

## 1. Plan 이월 결정 4건 — 확정

| # | 결정 대상 | 확정안 | 근거 (실측) |
|---|-----------|--------|------|
| ① | 스킬 API 권한 | `GET /agents/{id}/skills`는 `get_current_user` + UC 뷰어 검증(`viewer_user_id/role` 전달, PermissionError→403) — **에이전트 열람 권한과 동일 위임**. 403/404는 스킬 폴더만 "불러올 수 없음" 강등(FR-05) | `agent_builder_router.py:572-589` 실측 |
| ② | 지식 폴더 | **wiki tree 요약 임베드**(`useWikiTree` 재사용 — 그룹명·문서 수 목록) + "전체 지식 보기 →" AgentKnowledgePage 링크. 트리 전체 렌더는 중복 구현이라 안 함 | 기존 훅·페이지 재사용, 코드 중복 0 |
| ③ | workers 표시 범위 | **worker_type 분기 상세 표시** — `tool`: tool_id 카탈로그 라벨 + RAG면 tool_config에서 collection_name/kb_id/use_wiki_first/use_routed_search 안전 접근 표시 / `sub_agent`: ref_agent_name | `WorkerInfo`에 worker_type·ref_agent_name·tool_config 기존재 (types/agentStore.ts:31-40) |
| ④ | 라우트·진입점 | `/agents/:agentId/workspace` + 진입점 2곳: AgentKnowledgePage 헤더 "워크스페이스 →" / AgentDetailModal "워크스페이스 보기" 링크(모달 닫고 navigate) | AgentKnowledgePage와 대칭 URL |

## 2. Architecture (프론트 전용 — 백엔드 diff 0)

```
/agents/:agentId/workspace  (신규 라우트, ProtectedRoute + AgentChatLayout 내부)
  AgentWorkspacePage
    ├─ useAgentDetail(agentId)     ← 지침·도구·정보·can_edit (기존 훅)
    ├─ useAgentSkills(agentId)     ← 스킬 폴더 (기존 훅, 실패 시 폴더 강등)
    └─ useWikiTree(agentId)        ← 지식 폴더 요약 (기존 훅, 실패 시 폴더 강등)

  레이아웃: 좌측 폴더 nav(고정 6항목) + 우측 콘텐츠 (AgentKnowledgePage 2단 선례)
    📄 지침       → system_prompt 마크다운 렌더 (react-markdown + remark-gfm 기존 의존성)
    🔧 도구       → workers(worker_type='tool') + tool_ids 라벨
    👥 서브에이전트 → workers(worker_type='sub_agent') — 0건이면 "없음"
    🧩 스킬       → 부착 스킬 이름·설명 목록
    📖 지식       → tree 그룹·건수 요약 + 전체 보기 링크
    ℹ️ 정보       → 모델·temperature·공개범위·소유자·생성일 + (can_edit) 수정하기 링크
```

## 3. Detailed Design

### 3-1. 파일 구성

| 파일 | 내용 |
|------|------|
| `pages/AgentWorkspacePage/index.tsx` (신규) | 페이지 본체 — 폴더 nav state(`activeSection`) + 섹션 렌더. 200줄 초과 시 섹션 컴포넌트 분리 |
| `pages/AgentWorkspacePage/index.test.tsx` (신규) | 테스트 (§4) |
| `utils/agentDetailMapping.ts` (재사용) | tool_id → 카탈로그 라벨은 기존 `mapDraftToolIdsToCatalog` 활용 — **카탈로그 조회 실패 시 원문 id 표시**(FR-03) |
| `App.tsx` | 라우트 1줄 additive |
| `AgentKnowledgePage/index.tsx` | 헤더에 "워크스페이스 →" 링크 1개 |
| `AgentDetailModal.tsx` | "워크스페이스 보기" 링크(모달 close + navigate) |

### 3-2. 핵심 규칙

- **읽기 전용** — 어떤 mutation 훅도 사용하지 않음. 소유자용 "수정하기"는 `/agent-builder` 링크만(can_edit === true 조건, FR-07)
- **폴더별 독립 강등**(FR-05): agent detail 실패 → 페이지 전체 안내(존재/권한 없음, KnowledgeArticlePage 문구 선례) / skills·tree 실패 → 해당 폴더에만 "불러올 수 없음" (다른 폴더 정상)
- **tool_config 안전 접근**: `Record<string, unknown> | null`이므로 `typeof` 가드 후 표시 — 없는 키는 미표시(막지 않음)
- 페이지 래퍼: 패턴 A(고정 헤더 + 스크롤 바디). 콘텐츠 컬럼은 좌측 폴더 nav(w-52)와 함께 놓이는 읽기 뷰라 max-w-3xl(지침 마크다운 가독성 우선 — 테이블/대시보드 아님)
- 헤더: 에이전트 이름 + visibility 뱃지 + (can_edit) 수정하기

### 3-3. MSW

기존 `*/api/v1/agents/:agentId` 상세 핸들러(AgentKnowledgePage 테스트에서 오버라이드 사용 중)를 기본 핸들러로 승격 여부 확인 — 없으면 추가: AgentDetail 전체 필드(mock system_prompt·workers 2종·tool_ids). `*/api/v1/agents/:agentId/skills` 핸들러 추가(기존재 시 재사용).

## 4. Test Plan (TDD — Red 먼저)

| 케이스 | 검증 |
|--------|------|
| 폴더 6항목 렌더 + 기본 섹션(지침) 표시 | FR-01 |
| 지침 마크다운 렌더 (헤딩 존재) | FR-02 |
| 도구 섹션: 카탈로그 라벨 + RAG 설정 라벨(KB/위키 우선 등) | FR-03·③ |
| 서브에이전트 섹션: ref_agent_name 표시 / 0건 "없음" | ③ |
| 스킬 API 403 → 스킬 폴더만 강등, 다른 섹션 정상 | FR-05·① |
| 지식 섹션: 그룹·건수 + AgentKnowledgePage 링크 | FR-06·② |
| can_edit=false면 수정하기 미노출 / true면 노출 | FR-07 |
| AgentKnowledgePage → workspace 링크 렌더 (기존 테스트 회귀 0) | FR-06 |

## 5. Implementation Order

1. MSW 핸들러 정비 (agent detail·skills 기본 핸들러)
2. AgentWorkspacePage 테스트 작성 (Red)
3. 페이지 구현 + App 라우트
4. 진입점 2곳(AgentKnowledgePage·AgentDetailModal) + 기존 테스트 회귀 확인
5. tsc + 백엔드 diff 0 확인 → `/pdca analyze`

## 6. Plan 리스크 해소 매핑

| Plan 리스크 | 해소 |
|-------------|------|
| 스킬 API 비소유자 403 | 결정 ① 실측 — 뷰어 검증 위임 구조, 403은 폴더 강등 |
| tool_id 네임스페이스 오염 | `mapDraftToolIdsToCatalog` 재사용 + 미매칭 원문 표시 |
| system_prompt 렌더 성능 | 단순 마크다운 + 스크롤 (측정상 문제 시 후속) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-20 | 이월 결정 4건 확정 (스킬 API 뷰어 위임 실측·tree 요약 임베드·worker_type 분기·라우트/진입점 2곳) | 배상규 |
