# agent-workspace-view Plan Document

> **Feature**: agent-workspace-view — 에이전트 구성을 폴더처럼 열람하는 투명성 뷰
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **비전 근거**: growing-agent-vision 투명성 원칙 — "에이전트는 블랙박스가 아니라 열람 가능한 작업 공간" (사용자 원 요청: 2026-07 대화 — 프롬프트=CLAUDE.md 유사물로 노출)

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 사용자는 에이전트가 어떤 지침·도구·지식으로 움직이는지 볼 수 없다 — 스토어 상세 모달은 요약뿐이고, 유일한 열람 화면(지식 브라우저)은 위키만 보여줘 에이전트가 블랙박스로 남는다 |
| **Solution** | `/agents/:id/workspace` 읽기 전용 페이지 — 지침·도구·서브에이전트·스킬·지식을 **폴더 트리 메타포**로 통합 열람. **백엔드 무변경**: AgentDetail(system_prompt·tool_ids·workers·skill_ids 기노출) + 스킬 API + wiki tree 재사용 |
| **Function UX Effect** | 에이전트를 "열어보는" 경험 — 📄 지침.md 전문, 🔧 도구별 설정(RAG·KB 라벨), 📖 지식 폴더로 원클릭 이동. 지식 브라우저와 상호 링크 |
| **Core Value** | growing-agent 7원칙 중 투명성 축의 완성 — 사용자가 구성을 검증할 수 있어야 성장(승인·환류)에 대한 신뢰가 성립. 위키(지식)에 이어 나머지 구성 요소 전부를 가시화 |

---

## 1. 배경 / 문제 (실코드 확인)

- `AgentDetail`(types/agentStore.ts:42-63)이 이미 노출: `system_prompt`, `tool_ids`, `workers`(RAG tool_config 포함), `skill_ids`, `llm_model_id`, `visibility`, `owner_user_id` — **데이터는 전부 존재, 화면이 없다**.
- 현재 열람 경로: ① AgentDetailModal(스토어) — 요약 팝업 ② AgentKnowledgePage — 위키만 ③ agent-builder 수정 폼 — 소유자 전용 + 편집 UI라 열람 부적합.
- 선례: chunking-profile-admin-ui가 "프론트 전용 사이클"(95%)로 완결된 전례 — 동일 유형.

## 2. 목표 / 범위

### In Scope (프론트 전용)

1. **`/agents/:agentId/workspace` 페이지** — 좌측 폴더 트리 + 우측 콘텐츠 뷰:
   - 📄 **지침** — system_prompt 전문 (CLAUDE.md 유사물, 마크다운 렌더)
   - 🔧 **도구** — tool_ids + workers의 RAG 설정 요약(컬렉션/KB 라벨, wiki-first·routed 토글 표시)
   - 👥 **서브에이전트** — workers 중 서브에이전트 항목(이름·역할)
   - 🧩 **스킬** — 부착 스킬 목록(AGENT_SKILLS API)
   - 📖 **지식** — wiki tree 요약(그룹·문서 수) + AgentKnowledgePage 링크
   - ℹ️ **정보** — 모델·temperature·공개 범위·소유자·생성일
2. **진입점**: AgentKnowledgePage ↔ workspace 상호 링크 + AgentDetailModal에 "워크스페이스 보기" 링크
3. 소유자에게는 "수정하기"(agent-builder 편집) 링크 노출 — 열람과 편집의 분리 유지

### Out of Scope

- 백엔드 변경 일체 (신규 API 0 — 기존 응답으로 부족한 항목은 "표시 생략" 처리)
- 편집 기능 (기존 agent-builder가 담당)
- 실행 이력·비용 표시 (usage/observability 화면이 담당)
- 메모리 표시 (user 스코프 — 에이전트 소속 아님)

## 3. 요구사항

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-01 | 폴더 트리 6항목 렌더 — 항목 클릭 시 우측 뷰 전환 | AgentKnowledgePage FolderNode 렌더 선례 |
| FR-02 | 지침은 전문 마크다운 렌더 (react-markdown 기존 의존성) | |
| FR-03 | 도구 뷰: tool_id → 카탈로그 라벨 변환 (`mapDraftToolIdsToCatalog` 이중 네임스페이스 규칙 재사용) | 미매칭 id는 원문 표시 |
| FR-04 | 접근 권한 = 에이전트 상세 조회 권한과 동일 (visibility 기반, 신규 규칙 0) — 조회 실패 시 안내 | |
| FR-05 | 스킬·지식 로드 실패는 해당 폴더만 "불러올 수 없음" (페이지 전체 실패 금지) | |
| FR-06 | 지식 폴더 → AgentKnowledgePage 이동, 역방향 링크도 추가 | |
| FR-07 | 소유자에게만 "수정하기" 링크 (can_edit 필드 사용) | |

## 4. 성공 기준

- Match ≥ 90%, 기존 페이지·모달 회귀 0, tsc 에러 0
- 백엔드 diff 0줄 검증 (프론트 전용 확인)

## 5. 리스크

| 리스크 | 완화 |
|--------|------|
| 스킬 API(AGENT_SKILLS)가 비소유자에게 403일 가능성 | Design에서 라우터 권한 실측 — 403이면 스킬 폴더 조건부 표시(FR-05 경로) |
| tool_id 이중 네임스페이스 표시 오염 | 기존 `mapDraftToolIdsToCatalog` 재사용 (CC 메모리 기록 함정) |
| system_prompt가 길 때 렌더 성능 | 단순 마크다운 렌더 + 스크롤 (별도 최적화 불요) |

## 6. Design 이월 결정

| # | 결정 대상 | 후보 |
|---|-----------|------|
| ① | 스킬 API 권한 실측 | skill_builder/agent_skill 라우터 require 확인 → 표시 전략 확정 |
| ② | 지식 폴더 데이터 | wiki tree 요약 임베드(그룹·건수) vs 단순 링크만 |
| ③ | workers 표시 범위 | RAG 워커 tool_config 상세(컬렉션·KB·토글) vs 이름만 |
| ④ | 라우트·진입점 최종 | /agents/:id/workspace + 모달 링크 위치 |

## 7. 참조

- 데이터: `types/agentStore.ts` AgentDetail · `useAgentStore.ts` useAgentDetail · `AGENT_SKILLS` API · `useWikiTree`
- 렌더 선례: `AgentKnowledgePage`(폴더 트리) · `AgentDetailModal`(상세 요약) · `agentDetailMapping.ts`(라벨 변환)
- 유형 선례: chunking-profile-admin-ui (프론트 전용 사이클)
