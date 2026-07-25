---
title: 화면↔API 지도 — 위키·지식 노출 화면
status: draft
source_type: conversation
source_refs:
  - idt_front/src/App.tsx (agents/:agentId/knowledge, knowledge/:articleId, admin/wiki 라우트)
  - idt/docs/archive/2026-07/wiki-user-facing/wiki-user-facing.report.md
  - idt_front/src/constants/api.ts (WIKI_* 블록)
confidence: 0.85
version: 1
created: 2026-07-21
updated: 2026-07-21
verified_at: 6cc25656
---

제품 위키(`wiki_article`)를 노출하는 화면 3종. 데이터 모델은 [[erd-wiki]] 참조.

## AgentKnowledgePage — `/agents/:agentId/knowledge`

에이전트별 지식 트리(가상 폴더 `path` 기반) 브라우저 + 소유자 직접 작성(HUMAN).

- 진입: `idt_front/src/pages/AgentKnowledgePage/index.tsx`
- 훅: `useWiki`, `useAgentStore`(에이전트 컨텍스트/`can_manage` 인가)
- 엔드포인트: `WIKI_TREE`, `WIKI_LIST`, `WIKI_CREATE`
- 백엔드: `wiki_router` → `wiki_article` (V051 `path` 필요)

## KnowledgeArticlePage — `/knowledge/:articleId`

위키 문서 단독 뷰(채팅 근거 배지에서 진입).

- 진입: `idt_front/src/pages/KnowledgeArticlePage/index.tsx`
- 훅: `useWiki` → `WIKI_DETAIL`
- 계약: 검색 청크의 `chunk_id` = article id — 근거 배지가 이 라우트로 직결된다 (wiki-user-facing 실코드 제약)

## WikiPage — `/admin/wiki` (관리자)

위키 라이프사이클 큐레이션 — distill 실행, draft 승인/반려, 폐기/복원, 수정.

- 진입: `idt_front/src/pages/WikiPage/index.tsx`
- 훅: `useWiki`, `useAgentStore`, `useRagToolConfig`(distill 대상 컬렉션 선택)
- 엔드포인트: `WIKI_DISTILL`, `WIKI_APPROVE/REJECT/DEPRECATE/RESTORE/UPDATE`

## 백엔드 계약 주의

- **tree 라우트 선언 순서 의존**: `GET /api/v1/wiki/tree`는 `GET /api/v1/wiki/{id}`보다 **먼저** 선언되어야 한다. 뒤에 두면 `tree`가 `{id}`로 매칭된다 (wiki-user-facing).
- `agent_id`에는 예약석이 있다: `HUMAN`(소유자 직접 작성), `CONVERSATION`(👎 피드백 환류 — wiki-feedback-loop). human 출처 문서만 소유자 편집 허용.
- 편집 인가는 `can_manage` 필드로 프론트에 내려온다 — 프론트에서 role을 재판정하지 않는다.
