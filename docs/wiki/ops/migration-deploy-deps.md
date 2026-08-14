---
title: 마이그레이션 배포 의존성 — 기능별 필수 V버전
status: approved
source_type: conversation
source_refs:
  - idt/db/migration/ (V046~V060 파일 확인, 2026-08-14)
  - idt/docs/archive/2026-08/background-jobs/background-jobs.report.md
  - idt/docs/archive/2026-08/doc-generator/, agent-webhook/, agent-webhook-outbound/, builtin-middleware/
  - docs/archive/2026-08/eval-hub/
  - idt/docs/archive/2026-07/agent-eval-gate/agent-eval-gate.report.md
  - idt/docs/archive/2026-07/wiki-user-facing/wiki-user-facing.report.md
  - idt/docs/archive/2026-07/kb-retrieval-test/kb-retrieval-test.report.md
  - idt/docs/archive/2026-07/wiki-folder-summaries/wiki-folder-summaries.report.md
  - idt/docs/archive/2026-08/builtin-tools/builtin-tools.report.md
confidence: 0.9
version: 3
created: 2026-07-21
updated: 2026-08-14
verified_at: 12c69b4
reviewer: 배상규
---

## 문제

기능 코드는 머지됐지만 마이그레이션이 배포 환경에 적용되지 않으면 런타임에서 깨진다.
어떤 기능이 어느 V버전을 요구하는지가 PDCA 아카이브에 흩어져 있어 배포 시 확인이 어렵다.

## 검증된 사실 — 미적용 시 깨지는 최근 마이그레이션 (V046~V060)

| V | 내용 | 요구하는 기능 | 미적용 시 |
|---|---|---|---|
| V046 | `ai_retrieval_source`에 search_query/query_source/search_mode 등 additive 컬럼 | retrieval-observability | 검색 관측 기록 시 컬럼 부재 오류 — **배포 전 필수** |
| V047 | `document_metadata.kb_id` (NULL=일반 업로드) | kb-management-ui 이후 KB 시리즈 전체 (문서 목록·엑셀 업로드·리트리버 테스트·콘텐츠 브라우저) | KB 문서 귀속 불가. KB 파이프라인 E2E의 **선행 조건** |
| V048 | `knowledge_base`에 use_custom_chunking + custom_chunking_config | kb-custom-chunking | 커스텀 청킹 설정 저장/조회 실패 |
| V049 | `search_history.kb_id` | kb-retrieval-test | KB 검색 히스토리 기록 실패 — **배포 전 필수** |
| V050 | `agent_memory` 신규 테이블 (Phase 2/3 컬럼 선반영) | agent-memory Phase 1~3 전부 (extraction·org-scope는 추가 마이그레이션 0) | 메모리 기능 전체 불가 — **배포 전 필수** |
| V051 | `wiki_article.path` + idx | wiki-user-facing (지식 트리) | tree API·문서 분류 실패 |
| V052 | `message_feedback` 신규 테이블 | agent-eval-gate + 환류 3부작(eval-feedback-loop·wiki-feedback-loop·recurring-feedback-promotion — 이들 자체는 마이그레이션 0) | 평가/환류 전체 불가 — **배포 전 필수** |
| V053 | `wiki_folder_summary` 신규 테이블 (agent_id+path UQ) | wiki-folder-summaries (기능 플래그 **기본 off** — 적용해도 폴더 모드는 opt-in) | 승인/편집/폐기 시 요약 팬아웃·wiki_list 폴더 모드 실패 |
| V054 | `tool_catalog.is_builtin` + wiki 도구 2종 시드 UPDATE | builtin-tools ([[builtin-tools-optout-channel]]) | **tool_catalog 조회 자체가 SQL 에러** (모델에 컬럼 존재) — **배포 전 필수** |

| V055 | `evaluation_testset`·`evaluation_run`에 `user_id` (NULL=레거시, admin만 열람) | eval-hub | 평가 소유권 쿼리 실패. **FK 미부여**가 의도 — 사용자 삭제 후에도 이력 보존 (V052 선례) |
| V056 | `middleware_catalog` 신규 테이블 + **시드 INSERT** | builtin-middleware | 미들웨어 카탈로그 조회 불가. **부팅 sync가 없어 시드는 이 마이그레이션이 유일한 공급원** — 적용 누락 시 자가 복구 안 됨 |
| V057 | `agent_webhook` 신규 테이블 (에이전트 1:1, opt-in) | agent-webhook (inbound) | 웹훅 채널 CRUD·inbound 호출 실패. 시크릿은 **평문 저장**(HMAC 재계산용) |
| V058 | `agent_webhook_delivery` 신규 테이블 (INSERT only 이력) | agent-webhook-outbound + background-jobs 알림 | outbound 발송 이력 기록 실패. FK가 `agent_webhook`이 아니라 `agent_definition` — 채널 삭제 후에도 이력 보존 |
| V059 | `document_generation_type` 신규 테이블 | doc-generator (문서 생성 타입·빌더 UI) | 문서 유형 관리/생성 노드 실패. UQ 인덱스 없음 — "도구당 active 1개"는 **앱 레이어**가 보장 |
| V060 | `agent_background_job` 신규 테이블 + 인덱스 3종(claim/user/unseen) | background-jobs ([[db-queue-inprocess-worker]]) | **`background_worker_enabled` 기본 true라 워커가 기동 즉시 테이블 부재로 실패** — 배포 전 필수 |

공통: V046~V060은 전부 additive(컬럼 추가 또는 신규 테이블)라 **역방향 호환** — 먼저 적용해도 구버전 코드가 깨지지 않는다. 신규 테이블/FK는 CHARSET/COLLATE 미명시 원칙을 따른다 ([[mysql-fk-collation]]).

**"적용해도 조용한" 것과 "적용 안 하면 즉시 터지는" 것의 구분**: V054(모델에 컬럼 존재)와 V060(워커 기본 on)은 미적용 시 **기능을 안 써도** 터진다. 나머지는 해당 기능 사용 시에만 터진다.

## 다음에 적용하는 법

1. 배포 전 대상 환경에서 flyway 이력(또는 `SHOW TABLES`/`SHOW COLUMNS`)으로 V060까지 적용됐는지 확인한다.
2. 새 기능 사이클이 마이그레이션을 추가하면 이 표에 한 줄 추가한다 (기능명 + 미적용 시 증상).
3. "마이그레이션 0" 기능도 선행 V에 의존할 수 있다(예: 환류 3부작 → V052, extraction/org-scope → V050) — 의존 열에 명시한다.
4. 적용 후 E2E 일괄 체크리스트([[e2e-carryover-checklist]])를 소화한다 — 특히 V047은 KB E2E의 선행 조건.
