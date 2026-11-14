---
title: 마이그레이션 배포 의존성 — 기능별 필수 V버전
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/db/migration/ (V046~V060 파일 확인, 2026-08-14)
  - idt/db/migration/V061__create_prompt_session.sql · V062__create_prompt_version.sql (v4, ⚠️ 미커밋)
  - docs/archive/2026-08/prompt-composer/prompt-composer.design.md (§3.3)
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.report.md (마이그레이션 0 — V061/V062 의존)
  - idt/docs/archive/2026-08/background-jobs/background-jobs.report.md
  - idt/docs/archive/2026-08/doc-generator/, agent-webhook/, agent-webhook-outbound/, builtin-middleware/
  - docs/archive/2026-08/eval-hub/
  - idt/docs/archive/2026-07/agent-eval-gate/agent-eval-gate.report.md
  - idt/docs/archive/2026-07/wiki-user-facing/wiki-user-facing.report.md
  - idt/docs/archive/2026-07/kb-retrieval-test/kb-retrieval-test.report.md
  - idt/docs/archive/2026-07/wiki-folder-summaries/wiki-folder-summaries.report.md
  - idt/docs/archive/2026-08/builtin-tools/builtin-tools.report.md
  - idt/db/migration/V063~V079 (v5 — 파일 헤더 주석 + ORM 모델 매핑 확인, 2026-10-13)
  - idt/docs/archive/2026-10/subagent-step-observability/subagent-step-observability.report.md (V079 운영 적용 필요)
  - idt/docs/archive/2026-09/ (agent-model-benchmark·mcp-tool-category-routing·jobs-page-revamp·mcp-identity-header — V067~V070·V076~V077)
  - idt/db/migration/V080~V085 (v6 — 파일 헤더 주석 + ORM 매핑 grep, 2026-11-14)
  - docs/archive/2026-10/agent-opener/agent-opener.report.md (§8.1 V080 미적용 시 500)
  - docs/archive/2026-11/tool-access-control/tool-access-control.report.md (§8.1 배포 전 MCP 전체 동기화, G-08)
  - docs/archive/2026-11/agent-kb-quick-setup/agent-kb-quick-setup.report.md (V084 + 기본 임베딩 모델 1회 설정)
  - idt/docs/archive/2026-11/image-generation-tool/image-generation-tool.report.md (V081)
  - idt/docs/archive/2026-11/agent-token-limit/agent-token-limit.report.md (V085, G-3 머지 순서)
  - 99b1512(#94, V085) · 3f7749c(#95, V084) 머지 순서
confidence: 0.85
version: 6
created: 2026-07-21
updated: 2026-11-14
verified_at: 2fc45c5
---

> v6 (2026-11-14): **V080~V085 6건 추가**(2026-10 중순~11). 판정 방식은 v5와 동일. V083은 **배포 절차 전제(MCP 전체 동기화)**가 있는 첫 시드다. 에이전트 갱신이라 approved → draft 강등.
>
> v5 (2026-10-13): **V063~V079 17건 추가**(2026-08 말~2026-10). 신규 행의 "요구하는 기능"은 SQL 파일 헤더 주석,
> "미적용 시"는 ORM 모델이 해당 컬럼을 매핑하는지(`grep`)로 판정했다 — 매핑돼 있으면 V054와 같은 유형
> (테이블 조회 자체가 SQL 에러). 각 기능의 세부 증상은 해당 PDCA 보고서가 SoT. 에이전트 갱신이므로 approved → draft 강등 → 2026-10-13 재승인(배상규).
> V046~V062 행은 v4(7c3ffdd) 확인분 그대로이며 V061/V062 SQL은 이후 커밋됐다.

## 문제

기능 코드는 머지됐지만 마이그레이션이 배포 환경에 적용되지 않으면 런타임에서 깨진다.
어떤 기능이 어느 V버전을 요구하는지가 PDCA 아카이브에 흩어져 있어 배포 시 확인이 어렵다.

## 검증된 사실 — 미적용 시 깨지는 최근 마이그레이션 (V046~V085)

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
| V061 | `prompt_session` 신규 테이블 (⚠️ 미커밋) | prompt-composer | 프롬프트 생성 세션 저장 실패(5xx — DB 실패는 degraded로 위장하지 않음). `agent_id` FK **미설정이 의도** — 에이전트 삭제가 생성 이력 삭제로 전이되면 안 됨(백필 API가 정합 담당) |
| V062 | `prompt_version` 신규 테이블 (session FK CASCADE, `uq_session_version`, `schema_version` 선반영) | prompt-composer + **agent-create-pipeline(자체 마이그레이션 0이지만 V061/V062 의존)** | 버전 저장 실패. pipeline은 prompt-composer 미가동 시 **라우터 자체가 등록되지 않아 404** ([[router-map]] 조건부 include) |

### V063~V079 (v5 추가, 2026-08 말~2026-10)

| V | 내용 | 요구하는 기능 | 미적용 시 |
|---|---|---|---|
| V063 | `prompt_version.source` (작성 주체 구분) | agent-create-wizard (4단계 프롬프트 직접 편집본 보존) | 모델 매핑 컬럼 — `prompt_version` 조회 SQL 에러(prompt-composer·pipeline 공통) |
| V064 | `llm_model.supports_vision` (기본 0) | multimodal-extractor (비전 모델 드롭다운 = is_active AND supports_vision) | 모델 매핑 컬럼 — **`llm_model` 조회 자체가 깨짐**(모델 레지스트리는 거의 모든 경로가 읽음) — **배포 전 필수** |
| V065 | `multimodal_setting` 신규 테이블(단일 행, vision_model_id 소프트 참조) | multimodal-extractor 전역 설정 | 설정 조회/저장 실패. ENUM 대신 VARCHAR(앱 검증)·CHARSET 미명시 원칙 |
| V066 | `document_blueprint` 신규 테이블(blueprint_json + 에셋 LONGBLOB 영구 보관) | golden-sample-blueprint | blueprint 추출·조회 실패 |
| V067 | `evaluation_sweep` 신규 테이블(스윕 = evaluation_run N건의 부모, 재현 스냅샷) | agent-model-benchmark | 스윕 생성 실패 |
| V068 | `evaluation_run`에 모델 차원, `evaluation_result`에 관측 키·도구 호출 기록(전부 nullable) | agent-model-benchmark | 모델 매핑 컬럼 — eval-hub 기존 평가 조회도 SQL 에러 — **배포 전 필수** |
| V069 | `tool_catalog.category` + 도구 호출 상한 | mcp-tool-category-routing (워커 노드 종류 결정) | 모델 매핑 컬럼 — **`tool_catalog` 조회 자체가 SQL 에러**(V054와 동형) — **배포 전 필수** |
| V070 | `agent_background_job.deleted_at` (소프트 삭제) | jobs-page-revamp (작업함 정리) | 모델 매핑 컬럼 — **워커 claim 쿼리부터 실패**(V060과 묶어 필수) |
| V071 | `approval_request` 신규 테이블(승인 요청 + 런 재개 스냅샷, DATETIME UTC naive) | approval-gate ([[approval-gate-run-contract]]) | 게이트 도구 호출 시 승인 요청 저장 실패 |
| V072 | `tool_catalog.requires_approval` (런타임 SoT, ToolMeta 기본값은 시드 전용) | approval-gate 도구 축 | 모델 매핑 컬럼 — V069와 함께 `tool_catalog` 조회 에러 — **배포 전 필수** |
| V073 | `middleware_catalog`에 승인 게이트 **시드 INSERT**(is_builtin=0, is_enforced=0) | approval-gate 미들웨어 등록 | 관리자가 켤 미들웨어 항목이 없음. V056 선례대로 **시드가 유일한 공급원**(부팅 sync로 복구되지 않는다고 전제할 것) |
| V074 | `approval_request.session_id` (NULL 허용 — V071 기존 행) | approval-gate Check G1 (재개 답변 저장 세션) | 모델 매핑 컬럼 — 승인 요청 조회 에러. 미적용 시 재개가 `SessionId("")`로 실패해 최종 답변 유실하던 결함의 수정분 |
| V075 | `mcp_server_registry.default_requires_approval` (서버 축 초기값) | approval-gate-phase2-mcp-executor | 모델 매핑 컬럼 — **MCP 서버 레지스트리 조회 에러**(MCP 도구 sync 경로 전체) |
| V076 | `users.mailbox_upn` (사용자별 메일함 UPN) | mcp-identity-header | 모델 매핑 컬럼 — **`users` 조회 = 로그인·`/auth/me` 실패** — **배포 전 필수** |
| V077 | `mcp_server_registry.identity_config` (SecretCipher 암호화) | mcp-identity-header (서버별 신원 헤더) | 모델 매핑 컬럼 — V075와 함께 레지스트리 조회 에러 |
| V078 | `approval_request`에 수정 전 원본 보존 3컬럼(`original_tool_args` 등, NULL=무수정) | approval-edit-before-approve | 모델 매핑 컬럼 — 승인 요청 조회 에러 |
| V079 | `ai_run_step.parent_step_id`(FK 없음)·`depth`(기본 0) | subagent-step-observability ([[run-step-hierarchy-and-latency]]) | 모델 매핑 컬럼 — **런 상세·step 기록 전부 SQL 에러**(RunTracker는 모든 에이전트 실행이 탐) — **배포 전 필수** |

### V080~V085 (v6 추가, 2026-10 중순~11)

| V | 내용 | 요구하는 기능 | 미적용 시 |
|---|---|---|---|
| V080 | `agent_opener` 신규 테이블(agent_definition CASCADE, 저장은 전체 교체) | agent-opener (대화 시작 예시 질문) | 신규 테이블이지만 **에이전트 핵심 경로가 읽는다** — `/agents/my`·상세·생성·수정·포크가 500(보고서 §8.1) — **배포 전 필수** |
| V081 | `llm_model.model_kind`(기본 `'chat'`)·`price_per_image_usd` | image-generation-tool (채팅·비전·서브에이전트 드롭다운은 chat만) | 모델 매핑 컬럼 — **`llm_model` 조회 자체가 깨짐**(V064와 동형) — **배포 전 필수** |
| V082 | `tool_access_default`·`_department`·`_user` 3테이블(도구·부서·사용자 FK CASCADE) | tool-access-control (판정 = admin 전부 \| 기본 ∪ 부서 ∪ 사용자, **규칙 없는 도구는 기본 차단**) | 판정을 쓰는 도구 목록·저장·포크·실행·승인 집행 경로 실패. `tool_catalog`에 컬럼을 추가하지 않은 건 V054/V069 유형 사고를 피하려는 결정 |
| V083 | `tool_access_default`에 **현재 카탈로그 전 도구 시드**(비활성 포함) | tool-access-control "배포 직후 동작 변화 0" | ⚠️ V082만 적용하고 V083을 빼면 **비관리자는 모든 도구가 차단**된다. 또 **시드는 적용 시점의 카탈로그만 복사**하므로 미동기화 MCP 서버의 도구는 빠진다(G-08) → **V083 전에 모든 MCP 서버 카탈로그 동기화**(`/admin/mcp-servers` 또는 `POST /api/v1/tool-catalog/sync`). 이후 sync로 생기는 도구는 기본 차단 |
| V084 | `kb_default_setting` 단일 행(고정 id 시드, `default_embedding_model_id` 소프트 참조) | agent-kb-quick-setup (빌더 원스톱 KB) | 설정 조회 실패. 적용해도 **NULL이면 KB 자동 생성이 422**(조용한 폴백 없음) → 배포 후 관리자가 `/admin/kb-defaults`에서 기본 임베딩 모델 1회 설정 |
| V085 | `agent_definition.token_limit` INT NOT NULL DEFAULT 50000 (8000~500000은 도메인 검증, 단위는 글자수÷4 추정치) | agent-token-limit | 모델 매핑 컬럼 — **`agent_definition` 조회 = 거의 모든 에이전트 경로 SQL 에러** — **배포 전 필수**. `agent_definition`은 create_all 생성 테이블이라([[erd-agent]]) 신규 DB는 컬럼이 이미 생기고 기존 DB만 ALTER가 필요 |

**V084/V085 머지 순서 역전**: master에는 V085(#94, 2026-11-05 17:13:55)가 V084(#95, 17:14:15)보다 20초 먼저 머지됐다. 두 머지 사이 상태로 운영 배포된 적이 없다면 무관하지만, V085만 먼저 적용된 환경이 있으면 Flyway 기본 설정(outOfOrder 끔)에서는 V084가 적용되지 않는다 — 그 경우 outOfOrder 또는 수동 적용 필요. 운영 적용 절차(Flyway 사용 여부)는 아직 미확인(보고서 G-3).

공통: V046~V085는 전부 additive(컬럼 추가·신규 테이블·시드)라 **역방향 호환** — 먼저 적용해도 구버전 코드가 깨지지 않는다. 신규 테이블/FK는 CHARSET/COLLATE 미명시 원칙을 따른다 ([[mysql-fk-collation]]).

**"적용해도 조용한" 것과 "적용 안 하면 즉시 터지는" 것의 구분**: V054(모델에 컬럼 존재)와 V060(워커 기본 on)은 미적용 시 **기능을 안 써도** 터진다. (v5) V063~V079 중 **컬럼 추가 12건은 전부 ORM 모델에 매핑돼 있어 같은 유형**이다 — 특히 V064(`llm_model`)·V069/V072(`tool_catalog`)·V070(백그라운드 워커)·V076(`users`)·V079(`ai_run_step`)는 기능과 무관하게 앱 핵심 경로가 깨진다. 신규 테이블 5건(V065~V067·V071)과 시드 1건(V073)은 해당 기능 사용 시에만 터진다.

## 다음에 적용하는 법

1. 배포 전 대상 환경에서 flyway 이력(또는 `SHOW TABLES`/`SHOW COLUMNS`)으로 **V085**까지 적용됐는지 확인한다.
   V083 직전에 MCP 전체 동기화, 적용 뒤 관리자 기본 임베딩 모델 설정(V084)까지가 한 세트다.
   로컬은 flyway 이력 없이 SQL을 직접 실행해 온 환경이라(V079 보고서) "로컬에서 됐다"가 운영 적용의 증거가 아니다.
2. 새 기능 사이클이 마이그레이션을 추가하면 이 표에 한 줄 추가한다 (기능명 + 미적용 시 증상).
   번호는 착수 시 **다른 worktree의 미커밋 파일까지** 확인해 고른다(`ls ../wt/*/idt/db/migration` — V084 충돌을 이렇게 잡아 V085로 바꿈). 병렬 feature가 둘 다 마이그레이션을 가지면 PR 본문에 머지 순서를 적는다.
   시드가 다른 데이터 상태(카탈로그 동기화 등)에 의존하면 Plan 리스크와 이 표에 "적용 전 절차"로 적는다(V083 선례).
3. "마이그레이션 0" 기능도 선행 V에 의존할 수 있다(예: 환류 3부작 → V052, extraction/org-scope → V050) — 의존 열에 명시한다.
4. 적용 후 E2E 일괄 체크리스트([[e2e-carryover-checklist]])를 소화한다 — 특히 V047은 KB E2E의 선행 조건.
