---
title: E2E 이월 체크리스트 — Qdrant/ES/실서버 기동 시 일괄 소화 목록
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/docs/archive/2026-07/kb-rag-filter/kb-rag-filter.report.md
  - idt/docs/archive/2026-07/kb-management-ui/kb-management-ui.report.md
  - idt/docs/archive/2026-07/kb-retrieval-test/kb-retrieval-test.report.md
  - idt/docs/archive/2026-07/wiki-user-facing/wiki-user-facing.report.md
  - idt/docs/archive/2026-07/agent-memory/agent-memory.report.md
  - idt/docs/archive/2026-10/excel-preview/excel-preview.report.md §8.1 (v2)
  - docs/archive/2026-10/prompt-guard/prompt-guard.report.md §4.1 (v2)
  - idt/docs/archive/2026-10/subagent-step-observability/subagent-step-observability.report.md §4.1 (v2)
  - idt/docs/archive/2026-10/hwp-parser/hwp-parser.report.md §4.1 환경 메모 (v2)
confidence: 0.9
version: 2
created: 2026-07-21
updated: 2026-10-13
verified_at: 3b6353b
---

> v2 (2026-10-13): "2026-10 사이클" 절 추가(excel-preview 수동 E2E 4종, prompt-guard 배포 전 수기 항목·운영 관측,
> subagent-step-observability 화면 확인·V079, hwp-parser ES nori). 기존 절은 v1(6cc25656) 그대로. approved → draft 강등 → 2026-10-13 재승인(배상규).

## 문제

단위/통합 테스트는 통과했지만 Qdrant/ES/실 LLM 기동이 필요해 실측하지 못한 검증이
사이클마다 "이월"로 쌓였다. 흩어진 이월 항목을 한 번의 환경 기동으로 일괄 소화하기 위한 목록.

**선행 조건**: [[migration-deploy-deps]]의 V046~V052 적용 (특히 V047은 KB 시리즈 전체의 선행).
필요 플래그: `eval_feedback_extraction_enabled`, `WIKI_FEEDBACK_DRAFT`, `WIKI_FEEDBACK_REINFORCE` (환류 계열).

## 체크리스트 (출처 = 각 report.md의 이월 절)

### KB 파이프라인 시리즈 (Qdrant/ES 기동)

- [ ] **kb-rag-filter G2**: Qdrant payload `kb_id` 실측, KB A/B 격리 검색, clamp 확인 — `idt/docs/archive/2026-07/kb-rag-filter/kb-rag-filter.report.md`
- [ ] **kb-management-ui G3**: KB 생성→업로드→agent-builder 드롭다운→검색 격리 (kb-rag-filter G2와 일괄) — `idt/docs/archive/2026-07/kb-management-ui/kb-management-ui.report.md`
- [ ] **kb-custom-chunking 3종**: 커스텀 청킹 실측 / 회귀 / 기존 문서 불변 — `idt/docs/archive/2026-07/kb-custom-chunking/kb-custom-chunking.report.md`
- [ ] **kb-excel-upload**: 실 xlsx 업로드→Qdrant payload `sheet_name`→KB 검색 히트→콘텐츠 브라우저 조회 (V047·V048 선행) — `idt/docs/archive/2026-07/kb-excel-upload/kb-excel-upload.report.md`
- [ ] **kb-retrieval-test**: 같은 컬렉션 공유 KB 2개 kb_id 격리 실측 + V047 이전 문서 미출현 + 문서 스코프 검색 — `idt/docs/archive/2026-07/kb-retrieval-test/kb-retrieval-test.report.md`
- [ ] **kb-content-browser DF1(⑤)**: source 토글 ES/Qdrant 브라우저 실측 — `idt/docs/archive/2026-07/kb-content-browser/kb-content-browser.report.md`
- [ ] **chunking-profile-admin-ui G2**: 프로파일에 요약 LLM 지정→조항 청킹 KB 업로드→`section_summary_job.llm_model_id` 확인 — `idt/docs/archive/2026-07/chunking-profile-admin-ui/chunking-profile-admin-ui.report.md`
- [ ] **summary-routed-retrieval**: 요약 활성 KB에 규정 PDF 업로드→`POST /api/v1/retrieval/routed`→routing 근거·fallback_used 관찰, K/N/weights 튜닝 — `idt/docs/archive/2026-07/summary-routed-retrieval/summary-routed-retrieval.report.md`
- [ ] **admin-dashboard**: Qdrant/ES 실기동 상태 헬스 표시 + stats 실데이터 대사 — `idt/docs/archive/2026-07/admin-dashboard/admin-dashboard.report.md`

### 위키·환류 시리즈 (MySQL/Qdrant + 플래그 on)

- [ ] **wiki-user-facing** (V051 + Qdrant): 작성→`use_wiki_first` 검색 반영→근거 배지→문서 뷰 — `idt/docs/archive/2026-07/wiki-user-facing/wiki-user-facing.report.md`
- [ ] **fix-wiki-distill-dedup**: 같은 컬렉션 distill 2회→2회차 skipped_count 확인 — `idt/docs/archive/2026-07/fix-wiki-distill-dedup/fix-wiki-distill-dedup.report.md`
- [ ] **eval-feedback-loop**: 👎+이유→추출→PENDING→승인 전 구간 — `idt/docs/archive/2026-07/eval-feedback-loop/eval-feedback-loop.report.md`
- [ ] **wiki-feedback-loop**: 👎+이유→memory 후보 + wiki 초안 팬아웃→각 승인 전 구간 — `idt/docs/archive/2026-07/wiki-feedback-loop/wiki-feedback-loop.report.md`
- [ ] **recurring-feedback-promotion**: 3플래그 on, 같은 주제 👎 2회→초안 강화 실측 — `idt/docs/archive/2026-07/recurring-feedback-promotion/recurring-feedback-promotion.report.md`

### 메모리 시리즈 (실서버 + LangSmith)

- [ ] **agent-memory**: 등록→`[사용자 메모리]` 블록 주입(trace)→삭제 후 미주입 — `idt/docs/archive/2026-07/agent-memory/agent-memory.report.md`
- [ ] **agent-memory-extraction**: `.env` on→채팅→pending→승인→주입 — `idt/docs/archive/2026-07/agent-memory-extraction/agent-memory-extraction.report.md`
- [ ] **agent-memory-org-scope**: 같은 부서 2명 org 메모리 공유·병합 주입 — `idt/docs/archive/2026-07/agent-memory-org-scope/agent-memory-org-scope.report.md`
- [ ] **expose-user-department**: 다부서 사용자 승격 대상 선택·admin 부서 작성 왕복 — `idt/docs/archive/2026-07/expose-user-department/expose-user-department.report.md`

### 에이전트·기타 (실서버/실 LLM)

- [ ] **agent-workspace-view**: 실제 에이전트 6폴더 열람 + 진입점 왕복 — `idt/docs/archive/2026-07/agent-workspace-view/agent-workspace-view.report.md`
- [ ] **nl-agent-composer**: compose→POST /agents→run (실 LLM/DB, 라우터 401 검증 포함) — `idt/docs/archive/2026-07/nl-agent-composer/nl-agent-composer.report.md`
- [ ] **analysis-source-preservation**: 턴1 엑셀 첨부 분석→턴2 "분기별로 다시"(첨부 X)→원천 재집계 + LangSmith context/토큰 측정 — `idt/docs/archive/2026-07/analysis-source-preservation/analysis-source-preservation.report.md`
- [ ] **agent-eval-gate**: E2E 수동 검증 (일괄 체크리스트 편입 명시) — `idt/docs/archive/2026-07/agent-eval-gate/agent-eval-gate.report.md`

### 2026-10 사이클 (실서버·실에이전트, v2 추가)

- [ ] **excel-preview §8.1 (배포 전 1회)**: 엑셀 생성 에이전트로 .xlsx 산출→미리보기 전 시트 탭·데이터 일치 / 모달 다운로드 vs 링크 다운로드 바이트 동일(`fc /b`) / TTL(1h) 만료 후 "만료" 문구 + 모달 열린 채 만료 후 다운로드 실패 안내 / 10MB·5시트·2만 행 응답 2초 이내·채팅 UI 비차단 — `idt/docs/archive/2026-10/excel-preview/excel-preview.report.md`
- [ ] **prompt-guard (배포 전 수기)**: `idt/.env.example`에 `PROMPT_GUARD_*` 5키 반영(bkit이 `.env*` 쓰기 차단으로 미반영) / 기동 로그에 `prompt_guard assembly failed` 없음 확인(mode 오타면 가드 전체 off) / 운영 1~2주 `prompt_guard decision` 로그의 `judge_error=timeout`·REVIEW 비율 관측 후 타임아웃(3s)·soft 규칙 조정 — `docs/archive/2026-10/prompt-guard/prompt-guard.report.md`, [[prompt-injection-guard]]
- [ ] **subagent-step-observability SC-5**: **V079 운영 적용 후** `/admin/agent-runs/{runId}` 실행 상세에서 서브에이전트 step 아래 자식이 들여쓰기·"하위 N"·접기로 묶이는지 육안 확인(실런 run `8863101d`) — `idt/docs/archive/2026-10/subagent-step-observability/subagent-step-observability.report.md`
- [ ] **hwp-parser 환경**: ES에 `analysis-nori` 설치 후 `documents` 인덱스 재생성(로컬은 한국어 분석기 없이 생성됨) → 한글 문서 업로드 후 KB 검색 히트 확인 — `idt/docs/archive/2026-10/hwp-parser/hwp-parser.report.md`

## 다음에 적용하는 법

- 새 사이클 report에 "E2E 이월"이 생기면 이 목록에 추가한다 (출처 경로 필수).
- 항목을 실측 완료하면 체크하고, 도메인 전체가 소화되면 해당 절을 접거나 완료 표시한다.
- 반복 교훈: E2E를 기약 없이 미루지 말고 unit test 완료 직후 E2E 스크립트라도 작성해 둘 것 (kb-management-ui 회고).
