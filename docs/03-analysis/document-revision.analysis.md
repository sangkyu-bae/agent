# document-revision Analysis Report

> **Feature**: document-revision (KB 문서 개정 판정·버전 계보·검색 제외)
> **Date**: 2026-11-23
> **Phase**: Check
> **Plan**: `docs/01-plan/features/document-revision.plan.md`
> **Design**: `docs/02-design/features/document-revision.design.md` (§12.1~§12.5 Do 확정 사항 우선)
> **Worktree**: `wt/document-revision` (feature/document-revision, 미커밋)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 개정본 업로드 시 구·신버전 청크가 함께 검색돼 잘못된 근거가 인용된다 |
| **WHO** | P2 KB 운영자(개정 확정·이력 관리), P1/P4 최종 사용자(최신 근거만 받음), P3 관리자(판정 로그) |
| **RISK** | 오판정으로 멀쩡한 문서가 검색에서 빠짐 / 적재·전환 중간 실패로 둘 다 활성 또는 둘 다 비활성 / 검색 경로 중 필터 누락 경로 |
| **SUCCESS** | 개정 확정 후 모든 검색 경로에서 구버전 청크 0건, 동일 해시 재업로드 차단, 되돌리기 시 구버전 즉시 복귀, 개정 후보 top-1 정확도 ≥ 90%(픽스처 세트) |
| **SCOPE** | KB 업로드 경로 백엔드 + 프론트(업로드 모달·문서 목록·근거 칩). 검색 제외 필터는 전 경로 공통 |

---

## Strategic Alignment Check

### 핵심 문제 해결 여부

실서버 E2E(§2.7)에서 개정 확정 직후 리트리버 테스트 결과에 구버전 청크가 0건, 되돌리기 직후 다시 등장함을 확인했다. "구·신버전 혼재"라는 WHY 는 해결됐다. 남은 전략적 위험은 **파일명이 바뀐 개정본을 찾지 못하는 문제(SC-3)** 로, 기본 임계값 때문이다(Gap C1).

### Success Criteria Status

| SC | 내용 | 상태 | 근거 |
|----|------|:----:|------|
| SC-1 | 개정 확정 후 구버전 청크 0건 | ✅ Met | E2E `search after revision` — v1 문서 ID 부재(하이브리드 검색 경로). 정적: 가드 G1~G5 + 계약 테스트 `tests/contracts/test_revision_search_guard_coverage.py` |
| SC-2 | 동일 해시 재업로드 차단 | ✅ Met | E2E 업로드 409 `DUPLICATE_DOCUMENT` + 사전 점검 `verdict=duplicate` |
| SC-3 | top-1 정확도 ≥ 90%, 오제안 ≤ 5% | ❌ Not Met (기본값) / ✅ 임계값 보정 시 | 기본 `revision_content_min=0.75`: 정확도 **40%**(파일명 변경 개정 3건 후보 없음), 오제안 0%. `0.3` 진단 실행: 정확도 **100%**, 오제안 **0%** (§2.7 L3-2) |
| SC-4 | 되돌리기 시 즉시 복귀 | ✅ Met | E2E detach 후 v1 재등장, 최신 삭제(`restore_previous`) 후 v1 재등장 |
| SC-5 | 근거 칩·뷰어 버전 라벨 | ⚠️ Partial | 백엔드 라벨 생성·칩 중복 제거 단위 테스트 통과. 실제 에이전트 답변 칩 화면 확인 미실행 |
| SC-6 | 사전 점검 100% 판정 로그 + 결정 연결 | ✅ Met | E2E 판정 로그 4행(precheck·revision / precheck·duplicate / rollback·detach / manual_link·revision) |
| SC-7 | LLM 실패에도 업로드 진행 | ⚠️ Partial | LLM 예외·타임아웃·미설정, 임베딩 실패는 처리(단위 테스트). **파싱 실패는 500**(Gap I3) — 프론트는 점검 실패 시 새 문서 업로드 허용으로 흐름은 이어짐 |
| SC-8 | 화면만으로 완주 | ⚠️ Partial | API 단위로 업로드→개정→검색→되돌리기→연결→삭제 완주. 브라우저 화면 확인 미실행 |

### Decision Record Verification

| 결정 | 준수 | 비고 |
|------|:---:|------|
| 시스템 제안 + 사람 확정 (auto 는 자리만) | ✅ | revision_mode suggest 만 저장, auto 422 |
| 구버전 보존 + 검색 제외 | ✅ | payload `revision_status` + 가드 |
| 사전 점검 후 적재 | ✅ | |
| 확정 즉시 전환(시행일 표시용) | ✅ | |
| 신호 4종(해시·파일명·본문·LLM) | ✅ | 본문 임계값 보정 필요(C1) |
| Graph RAG 는 근거 단계에서만 제외 | ✅ | G5 `es_evidence_fetcher` |
| Option C (payload 표식 + 최하단 가드) | ✅ | |

---

## 1. Analysis Overview

- 정적 분석: gap-detector 에이전트(설계↔코드 3축) + 본인 재확인
- 런타임: 로컬 MySQL 에 V095~V097 적용(2026-11-23) 후 인프로세스 `TestClient`(실 MySQL·Qdrant·ES·임베딩·보조 LLM) E2E 1회 + SC-3 평가 2회
- 회귀: 백엔드 전체 pytest(master 대비 신규 실패 0, worktree 전용 blueprint 6건은 샘플 PDF 부재), 프론트 전체 vitest(master 와 동일 10건 실패), tsc·eslint 신규 오류 0

---

## 2. Gap Analysis

### 2.1 API Endpoints (Design §4 + §12.3)

| # | Endpoint | 상태 |
|---|----------|:---:|
| 1 | POST `/{kb}/documents/revision-check` | ✅ |
| 2 | POST `/{kb}/documents` (Form 4 + 409 + revision) | ✅ (응답 200 — Design 표기는 201, §2.6) |
| 3 | GET `/{kb}/documents` (버전 필드 + pending_sync) | ✅ |
| 4 | GET `…/{doc}/versions` | ✅ |
| 5 | POST `…/revision-rollback` | ✅ (Gap I2) |
| 6 | POST `…/revision-link` | ✅ |
| 7 | PATCH `…/revision-meta` | ✅ |
| 8 | POST `…/revision-sync` | ✅ |
| 9 | DELETE `…/{doc}?restore_previous` | ✅ (Gap I2) |
| 10 | PATCH `/{kb}/revision-mode` | ✅ (§12.3 경로) |

### 2.2 Data Model

V095~V097 3종, `DocumentMetadataModel` 10컬럼·인덱스 3, `knowledge_base.revision_mode`, `DocumentRevisionCheckModel`. 모델↔DDL 대조 테스트(`tests/db/test_document_revision_migrations.py`) 통과, 로컬 적용 후 10/10 컬럼 확인.

### 2.3 Component Structure

백엔드: domain 6 · application 5(관리 유스케이스는 §12.3 대로 1개로 통합) · infrastructure 9 · 라우터 1(+기존 1 확장). 프론트: 설계 7 컴포넌트 + `revisionDecision.ts` · `revisionErrors.ts`. 평가 스크립트 `idt/scripts/eval_revision_candidates.py` 와 픽스처 `tests/fixtures/document_revision/revision_pairs.json` 은 Check 에서 추가.

### 2.4 Functional Depth

플레이스홀더 없음. 해시·후보 점수·LLM 판정(타임아웃·폴백)·전환 순서·되돌리기/연결/메타/재반영·restore_previous·인용 라벨 모두 실제 로직이며 E2E 로 주요 경로 확인.

### 2.5 Page UI Checklist (Design §5.4)

모든 항목에 대응 컴포넌트와 RTL 테스트가 있다(업로드 모달 6·결과 패널 9·결정 로직 5·목록 4·대화상자 9·삭제 3). 브라우저 실화면 확인은 미실행.

### 2.6 API Contract (3-way)

10개 엔드포인트 경로·메서드·요청 필드·응답 필드가 Design ↔ FastAPI ↔ `constants/api.ts`·`knowledgeBaseService.ts`·`types/knowledgeBase.ts` 에서 일치. 409 detail `{code, reason, message}` / 중복 `{code, message, document}` 를 프론트 `RevisionErrorDetail`·`revisionErrors.ts` 가 처리. 차이: 업로드 성공 상태코드 200(기존 엔드포인트 계약 유지, Design 표기 201 → 문서 수정 대상).

### 2.7 Runtime Verification

**L1/L3-1 E2E** (`scratchpad/e2e_document_revision.py`, 일회용 KB·컬렉션 생성 후 정리 완료)

| 단계 | 결과 |
|------|------|
| quick 생성 + v1 적재, 무관 문서 적재 | 201 / 200 |
| 사전 점검(파일명 같은 개정본) | `revision_candidate`, 제안=v1, LLM `same_document_revision`, 6.8s |
| 개정 업로드 | `applied=true`, v2, `sync_state=synced` |
| 리트리버 테스트 | v1 0건, v2 검색됨 (SC-1) |
| 동일 파일 업로드 / 점검 | 409 `DUPLICATE_DOCUMENT` / `duplicate` (SC-2) |
| 목록 / 이력 | v1 숨김, v2 `version_no=2·has_history=true` / [2, 1] |
| 되돌리기(detach) | v1 복귀, 검색에 재등장 (SC-4) |
| 사후 연결 | 200, v1 다시 제외 |
| 최신 삭제(restore_previous) | `restored_document_id=v1`, v1 재등장 |
| 판정 로그 | 4행 (SC-6) |

**L3-2 SC-3 평가** (`scripts/eval_revision_candidates.py`, 기본 6문서 + probe 10)

| 실행 | top-1 정확도 | 오제안율 | 중복 | 관찰 |
|------|:---:|:---:|:---:|------|
| 기본값 `content_min=0.75` | **40%** (2/5) | 0% | ✅ | 파일명 변경 개정 3건이 후보조차 안 됨 |
| 진단 `content_min=0.3` | **100%** (5/5) | 0% | ✅ | LLM 이 무관 4건 모두 `different_document` |

본문 유사도 분포: 개정 쌍 **0.65~0.70**, 무관 문서 **0.31~0.35** — 거의 같은 문서도 0.7 안팎이다(앞부분 토막 대 청크 전체 비교 구조). 0.75 는 개정 쌍 전부보다 높아 파일명이 다르면 놓친다. 단, 합성 문서가 짧아(문서당 약 250자) 실문서 분포는 판정 로그로 다시 봐야 한다.

### 2.8 Match Rate

| 축 | 점수 | 근거 |
|----|:---:|------|
| Structural | 95% | 평가 스크립트·픽스처는 Check 에서 보충 |
| Functional | 90% | 로직 완비, Gap I2·I3 |
| Contract | 95% | 201→200 표기 차이 |
| Runtime | 85% | E2E 전 단계 통과, SC-3 기본값 미달 |
| **Overall** (런타임 포함 공식) | **90.3%** | 0.15·95 + 0.25·90 + 0.25·95 + 0.35·85 |

---

## 3. Gap List

### Critical

| ID | 내용 | 근거 | 수정안 |
|----|------|------|--------|
| C1 | **SC-3 미달** — 기본 `revision_content_min=0.75` 가 개정 쌍 본문 점수(0.65~0.70)보다 높아 파일명이 바뀐 개정본을 후보에서 놓침 | §2.7 L3-2 | 기본값을 **0.5** 로(개정 0.65~0.70 / 무관 0.31~0.35 중간). config·`RevisionScoringConfig`·Design §10.4 동시 수정 후 평가 재실행 |

### Important (확신 ≥ 80%)

| ID | 내용 | 근거 | 수정안 |
|----|------|------|--------|
| I2 | 되돌리기(delete)·최신 삭제(restore_previous)에서 이전 버전 재활성 표식이 실패(`sync=pending`)해도 현재 버전을 지운다 → MySQL 은 active 인데 청크는 superseded 로 남아 **계보 전체가 검색에서 빠짐**(Design 목표 2 위반) | `revision_management_use_case.py` rollback, `delete_document_use_case.py::_restore_previous` | 재활성이 `SYNCED` 가 아니면 삭제하지 않는다: 되돌리기는 detach 로 낮추고 `sync_state=pending` 반환, 삭제는 409(`RESTORE_PENDING`)로 막고 재반영 안내 |
| I3 | 사전 점검에서 파서 예외가 500 으로 나간다(SC-7 범위) | `revision_check_use_case.py` 파싱 단계 | 파싱 예외를 잡아 `verdict=new`·후보 없음·`llm_status=skipped` 로 응답하고 로그 기록(미지원 확장자는 기존 업로드처럼 422 유지) |
| I4 | Plan FR-19 "계보 전체 삭제" 옵션이 Design·코드에 없고 기록도 없음 | Plan §3.1 FR-19 | 이번 사이클 범위 밖으로 Design §12 에 명시(삭제 체크 해제로 계보가 검색에서 빠지는 경로는 있음) |

### Minor

| ID | 내용 | 수정안 |
|----|------|--------|
| M5 | detach 시 `version_label`·`effective_date` 가 남아 독립 v1 에 "2026-11 개정" 라벨이 붙는다 | detach 에서 두 필드도 비움 |
| M6 | 업로드 성공 200(Design 표기 201) | Design 을 200 으로 정정(기존 계약 유지) |
| M7 | 점수 폴백이 `failed` 뿐 아니라 `skipped`(보조 LLM 미설정)에도 적용 | 의도한 동작으로 Design §12 에 기록 |
| M8 | ES `update_by_query` 가 `conflicts=proceed` 라 버전 충돌로 건너뛴 청크가 있어도 성공 처리 | 응답 `version_conflicts > 0` 이면 실패로 보고 pending |
| M9 | quick setup 도 해시 중복 검사를 거쳐 같은 파일 2개를 함께 올리면 하나가 실패 처리 | 의도(중복 차단)로 Design §12 에 기록 |
| M10 | 삭제 중 저장소 삭제가 예외로 끝나면 MySQL 은 롤백되나 이전 버전 청크는 이미 active 로 표식 → 두 버전 모두 검색(근거 공백은 아님) | I2 수정 시 재활성을 삭제 성공 뒤로 옮기거나 pending 기록 |

---

## 4. Test Coverage

- 백엔드 신규 테스트: domain 57 · infra(가드·마커·리포지토리·점검 어댑터) · application(전환·점검·관리·업로드·삭제·목록·모드) · API(업로드·점검·관리·목록/삭제) · 계약 1 · DB 1 — 전부 통과
- 프론트 신규 테스트: 서비스 6 · 훅 4 · 결정 5 · 결과 패널 9 · 모달 6 · 목록 4 · 대화상자 9 · 삭제 3 — 전부 통과
- 미커버: Gap I2 의 표식 실패 + delete 조합, 브라우저 실화면, 에이전트 답변 근거 칩 실측

## 5. Clean Architecture

domain 은 외부 의존 없음(확인), infrastructure → domain 포트, application 은 domain·포트에만 의존. ES 가드 절은 domain 순수 dict(§9.2 결정). DI 는 `main.py` 단일.

## 6. Act-1 결과 (2026-11-23)

| Gap | 조치 | 검증 |
|-----|------|------|
| C1 | `revision_content_min` 0.75 → 0.5 (`value_objects.py`, `config.py`) | **SC-3 재측정: top-1 100%(5/5), 오제안 0%(0/4), 중복 ✅** (기본값 그대로) |
| I2 | 되돌리기 delete: 복귀 미완료면 detach 로 낮춤 / 최신 삭제: 409 `RESTORE_PENDING` + 표식 되돌림 | 단위 테스트 2·API 테스트 1 추가 |
| I3 | 사전 점검 파싱 예외 → 파일명 점수만으로 계속(미지원 확장자는 422 유지) | 단위 테스트 2 추가 |
| I4 | 범위 밖으로 Design §12.6 기록 | — |
| M5 | detach 시 라벨·시행일 비움 | 단위 테스트 1 추가 |
| M8 | ES `version_conflicts > 0` → 실패(pending) | 단위 테스트 1 추가 |
| M6·M7·M9·M10 | Design §12.6 기록 | — |

**SC 재평가**: SC-1·2·3·4·6 ✅ Met, SC-7 ✅ Met(파싱 실패 처리 추가), SC-5·SC-8 ⚠️ Partial(브라우저 실화면 미확인 — 단위·API 테스트로만 확인).

**Match Rate (Act-1 후)**: Structural 97 · Functional 96 · Contract 97 · Runtime 95 → **96.1%** (0.15·97 + 0.25·96 + 0.25·97 + 0.35·95).

## 7. 다음 단계

1. 브라우저 화면 확인(SC-5·SC-8) — 업로드 모달·목록·근거 칩 (Report 전 또는 이월)
2. Report
