# document-revision Planning Document

> **Summary**: KB에 문서를 올릴 때 기존 문서의 개정본인지 판정(시스템 제안 → 운영자 확정)해 버전 계보로 묶고, 구버전은 보존하되 리트리버에서 제외해 근거에 신·구 조문이 섞이지 않게 한다.
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-11-21
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 업로드할 때마다 새 `document_id`(uuid4)가 발급되고 중복·개정 판정이 전혀 없어, 개정본을 올리면 구버전과 신버전 청크가 함께 검색된다. 바뀐 조문의 구 내용이 근거로 뽑혀 "근거 없으면 답하지 않는다" 원칙이 무력화된다. |
| **Solution** | 적재 전에 사전 점검 API가 파일 해시(완전 동일 → 차단)·파일명 정규화·본문 유사도·LLM 판정으로 개정 후보를 찾아 제안하고, 운영자가 확정하면 새 문서를 같은 계보의 다음 버전으로 적재한 뒤 구버전을 `superseded`로 전환해 검색에서 제외한다. |
| **Function/UX Effect** | 업로드 모달에서 "기존 「여신심사기준」의 개정본으로 보입니다(근거: …)"를 확인·확정하고, 문서 목록에서 버전 이력 조회·되돌리기·라벨 입력이 가능하다. 답변 근거 칩에 버전 라벨이 표시된다. |
| **Core Value** | P2(KB 운영자)가 DB 조작 없이 화면 안에서 개정을 관리하고, P1·P4는 최신 규정만을 근거로 한 답을 받는다. 판정 로그를 쌓아 추후 완전 자동 개정으로 넘어갈 근거를 실측으로 마련한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 개정본 업로드 시 구·신버전 청크가 함께 검색돼 잘못된 근거가 인용된다 |
| **WHO** | P2 KB 운영자(개정 확정·이력 관리), P1/P4 최종 사용자(최신 근거만 받음), P3 관리자(판정 로그) |
| **RISK** | 오판정으로 멀쩡한 문서가 검색에서 빠짐 / 적재·전환 중간 실패로 둘 다 활성 또는 둘 다 비활성 / 검색 경로 중 필터 누락 경로 |
| **SUCCESS** | 개정 확정 후 모든 검색 경로에서 구버전 청크 0건, 동일 해시 재업로드 차단, 되돌리기 시 구버전 즉시 복귀, 개정 후보 top-1 정확도 ≥ 90%(픽스처 세트) |
| **SCOPE** | KB 업로드 경로 백엔드 + 프론트(업로드 모달·문서 목록·근거 칩). 컬렉션 직접 업로드·레거시 업로드·quick setup의 판정은 제외(단, 검색 제외 필터는 전 경로 공통 적용) |

---

## 1. Overview

### 1.1 Purpose

KB 문서 업로드 시 "이 문서가 기존 문서의 개정본인가"를 판정하는 장치를 만들고, 개정이 확정되면 구버전을 검색 근거에서 제외해 항상 최신 버전만 인용되게 한다.

### 1.2 Background — 현재 상태 (조사 완료, 2026-11-21)

| # | 확인 지점 | 결과 |
|---|-----------|------|
| 1 | `idt/src/application/unified_upload/use_case.py:96` | `document_id = str(uuid.uuid4())` — 업로드마다 새 ID. 파서의 `generate_document_id(filename)`도 덮어씀 |
| 2 | 중복 판정 | 없음. 파일 해시 미계산, 업로드 시 파일명 조회 없음 → 같은 파일 재업로드 시 두 문서가 모두 검색됨 |
| 3 | `idt/src/domain/agent_run/source_policy.py:182-193` | "같은 파일을 다시 올리면 document_id 만 달라 같은 이름의 칩이 겹친다" — 인용 칩을 파일명 기준으로 중복 제거하는 우회로 이미 존재 (문제 실재의 방증) |
| 4 | MySQL `document_metadata` (V014, V047) | status·version·hash·계보 컬럼 없음 |
| 5 | Qdrant / ES / Neo4j | 모두 `document_id` 키. Qdrant payload는 평면 문자열, parent·요약 청크도 같은 컬렉션·같은 document_id |
| 6 | 검색 필터 | `HybridSearchRequest`는 동등 비교 `metadata_filter`/`lenient_filter`만. Qdrant에는 `_apply_section_summary_guard`(`must_not`) 선례 존재 |
| 7 | 삭제 경로 | `DeleteDocumentUseCase.delete_verified` — 하드 삭제만, KB 문서에 soft delete·상태 개념 없음 |
| 8 | 프론트 | `KbUploadDocumentModal`(1파일씩), `KbDocumentTable`(파일명/청크 수/청킹 방식/업로드일) — 버전·상태 표시 없음 |

### 1.3 Related Documents

- 유저 시나리오: `docs/USER-SCENARIOS.md` — S1(KB 구축·검증 폐루프), 원칙 "LLM은 제안, 사람이 확정", "근거 없으면 답하지 않는다"
- 참고 패턴: wiki 문서 status(draft/approved/deprecated) + SQL 필터 (`idt/src/infrastructure/wiki/wiki_repository.py:242`) — 패턴만 참고, 코드 재사용 안 함
- 연관 기능: graph-rag-foundation(삭제·보조 검색 훅), source-passage-viewer, agent-run-source-citations, answer-citation-verification(진행 중, V093·V094 점유)

---

## 2. Scope

### 2.1 In Scope

- [ ] **문서 버전 모델**: `document_metadata`에 계보·버전·상태·해시 컬럼 추가 (기존 문서는 v1·active로 간주)
- [ ] **사전 점검 API**: 파일을 받아 해시·파일명 정규화·앞부분 본문 유사도·LLM 판정으로 개정 후보와 근거를 반환 (적재하지 않음)
- [ ] **완전 동일 파일 차단**: 같은 KB에 해시 일치 문서가 있으면 업로드 차단 + 기존 문서 안내
- [ ] **개정 확정 업로드**: 업로드 요청에 `supersedes_document_id`(선택)와 버전 라벨을 받아 새 버전으로 적재 → 성공 후 구버전 `superseded` 전환
- [ ] **검색 제외**: Qdrant·ES·Graph RAG 보조 검색(ES 근거 조회) 전 경로에서 superseded 문서 제외 (KB 업로드 외 경로로 들어간 문서에도 동일 필터)
- [ ] **버전 이력 조회**: 문서 목록에 "v3 (최신)" 표시, 펼치면 이전 버전(업로드일·확정자·라벨)
- [ ] **되돌리기**: 잘못 확정한 개정을 취소 → 구버전 재활성, 신버전은 계보에서 분리(신규 문서로 남기거나 삭제 선택)
- [ ] **수동 개정 연결**: 이미 올라간 기존 중복 문서를 목록에서 "이 문서가 대체한 문서 지정"으로 사후 연결
- [ ] **버전 라벨·시행일 입력**: 자동 버전 번호 외 운영자 라벨(예: "2026-11 개정")·시행일(표시용 메타데이터, 전환 시점에는 영향 없음)
- [ ] **인용 버전 표시**: 답변 근거 칩·원문 뷰어에 버전 라벨 표시
- [ ] **KB별 개정 모드 스위치**: `revision_mode = suggest | auto` 자리 마련, 이번 사이클은 `suggest`만 동작(`auto` 선택 불가 또는 suggest로 처리)
- [ ] **판정 로그**: 사전 점검마다 신호별 점수·LLM 판정·운영자 최종 결정을 기록 (추후 auto 임계값 실측용)

### 2.2 Out of Scope

- 완전 자동 개정 확정 로직(`auto` 모드 실동작) — 판정 로그 축적 후 별도 사이클
- 시행일 예약 전환(시행일까지 구버전 활성) — 확정 즉시 전환으로 결정
- 컬렉션 직접 업로드(`/documents/upload-all`)·레거시 업로드·quick setup 경로의 개정 판정
- KB 전체 일괄 개정 후보 스캔
- 구버전 그래프 데이터(Neo4j) 삭제·재추출 — 보존하고 보조 검색 근거 단계에서만 제외
- 신·구버전 조문 diff 화면, "과거 시점 규정 기준 답변"(time-travel 질의)
- 여러 파일 동시 업로드의 일괄 판정

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `document_metadata`에 `file_hash`(SHA-256), `lineage_id`(계보 ID, 기존 문서는 자기 document_id), `version_no`(기본 1), `version_label`, `effective_date`(표시용), `revision_status`(active/superseded, 기본 active), `superseded_by`, `superseded_at`, `superseded_by_user` 추가. 신규 Flyway는 **V095 이후**(V093·V094는 answer-citation-verification 점유) | High | Pending |
| FR-02 | 사전 점검 API(`POST /knowledge-bases/{kb_id}/documents/revision-check`): 파일 해시 계산 → 같은 KB의 active 문서와 해시 일치 시 `duplicate` 응답(차단 대상 문서 정보 포함) | High | Pending |
| FR-03 | 사전 점검 후보 생성: 파일명 정규화(버전·날짜·"개정/수정/최종/(n)" 꼬리표·확장자 제거) 일치·유사 + 새 문서 앞부분(첫 N페이지/일정 토큰) 임베딩과 기존 문서 대표 텍스트(문서 요약 또는 첫 청크) 유사도로 같은 KB의 active 문서 중 상위 후보 선정 | High | Pending |
| FR-04 | 후보가 있으면 LLM이 두 문서 앞부분을 비교해 `same_document_revision / different_document / uncertain` + 근거 문장을 반환. LLM 실패·타임아웃 시 신호 점수만으로 제안(업로드를 막지 않음) | High | Pending |
| FR-05 | 사전 점검 응답: `{ verdict: new|revision_candidate|duplicate, candidates: [{document_id, filename, version_no, version_label, scores{filename, content}, llm_verdict, reason}], check_id }` | High | Pending |
| FR-06 | KB 업로드 API에 선택 필드 `supersedes_document_id`, `version_label`, `effective_date`, `revision_check_id` 추가. 서버에서 해시 중복을 재검사(사전 점검 우회 방지)하고 중복이면 409 | High | Pending |
| FR-07 | 개정 확정 업로드 순서: 새 버전 적재(Qdrant·ES·MySQL, 같은 lineage_id, version_no+1) **성공 후** 구버전을 superseded로 전환. 전환 실패 시 재시도/보상 처리하고 결과를 응답에 명시 (둘 다 비활성이 되는 상태 금지) | High | Pending |
| FR-08 | 검색 제외: superseded 문서의 청크(parent·child·요약 포함)를 RAG 도구 하이브리드 검색·멀티쿼리·라우티드 검색·KB 리트리버 테스트·Graph RAG ES 근거 조회에서 제외. 상태 필드가 없는 기존 청크는 active로 취급(하위 호환, 백필 불필요) | High | Pending |
| FR-09 | 대상 문서 검증: `supersedes_document_id`는 같은 KB·active·쓰기 권한 있는 문서만 허용. 이미 superseded인 문서를 대체하려 하면 거부(계보 갈래 금지, 항상 최신 버전만 대체) | High | Pending |
| FR-10 | 버전 이력 조회 API: 계보 단위 버전 목록(버전 번호·라벨·시행일·업로드일·확정자·상태). KB 문서 목록 API는 기본으로 active만 반환하고 각 항목에 `version_no`·`version_label`·`has_history` 포함 | High | Pending |
| FR-11 | 되돌리기 API: 최신 버전의 개정을 취소 → 직전 버전 active 복귀, 취소된 버전은 (a) 계보에서 분리해 독립 문서로 유지 또는 (b) 삭제 중 운영자가 선택 | Medium | Pending |
| FR-12 | 수동 개정 연결 API: 기존 active 문서 A를 기존 active 문서 B의 개정으로 사후 지정(A의 계보를 B 계보에 편입, B superseded). 판정 로그에 `manual_link`로 기록 | Medium | Pending |
| FR-13 | 버전 라벨·시행일 수정 API(메타데이터만, 검색 영향 없음) | Low | Pending |
| FR-14 | 인용 버전 표시: 근거 칩·원문 뷰어 라벨에 버전 라벨(없으면 `v{n}`) 표시. 기존 파일명 기준 칩 중복 제거 로직과 충돌 없게 정리 | Medium | Pending |
| FR-15 | KB 설정 `revision_mode`(suggest/auto, 기본 suggest). 이번 사이클에서 auto는 저장 불가(또는 suggest와 동일 동작) — 스위치 자리만 마련 | Medium | Pending |
| FR-16 | 판정 로그 테이블: check_id, kb_id, 새 파일명·해시, 후보별 신호 점수·LLM 판정·근거, 시스템 제안, 운영자 최종 결정(revision/new/cancel), 결정자, 결정 시각 | Medium | Pending |
| FR-17 | 프론트 업로드 모달: 파일 선택 → 사전 점검 → 결과에 따라 (중복) 차단 안내 / (후보) "「X」 v2의 개정본으로 보입니다" + 근거 + [개정으로 올리기]/[새 문서로 올리기]/[다른 문서 선택] / (신규) 바로 업로드. 버전 라벨·시행일 입력 | High | Pending |
| FR-18 | 프론트 문서 목록: 버전 배지, 이력 펼치기, 되돌리기, "대체한 문서 지정", 라벨 수정 메뉴 | Medium | Pending |
| FR-19 | 삭제 정책: active 최신 버전 삭제 시 직전 버전을 자동 복귀할지 확인(확인 다이얼로그 문구 포함). 계보 전체 삭제 옵션 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 정확성 | 개정 확정 후 모든 검색 경로에서 superseded 청크 노출 0건 | 경로별 통합 테스트 + 실 Qdrant/ES 수동 검증 |
| 판정 품질 | 개정 쌍 픽스처(파일명 변경·동일 파일명·무관 문서 포함)에서 top-1 후보 정확도 ≥ 90%, 무관 문서를 개정으로 제안하는 비율 ≤ 5% | 픽스처 기반 평가 스크립트 |
| 성능 | 사전 점검 p95 ≤ 10초(LLM 포함), LLM 제외 신호만 ≤ 3초 | 로컬 측정, 로그 elapsed |
| 가용성 | LLM·임베딩 실패가 업로드를 막지 않음(제안 생략 후 신규 업로드 가능) | 실패 주입 테스트 |
| 일관성 | 적재 성공 + 전환 실패 시에도 신버전은 검색됨(둘 다 비활성 금지). 불일치는 로그·응답에 표시 | 실패 주입 테스트 |
| 보안·권한 | 사전 점검·확정·되돌리기·수동 연결은 KB 쓰기 권한 필요, 다른 KB 문서는 후보로 노출 금지 | 권한 테스트 |
| 하위 호환 | 마이그레이션 후 기존 문서·청크 재색인 없이 그대로 검색 | 마이그레이션 후 회귀 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 구버전 A(v1)를 개정본 B로 확정한 뒤, RAG 도구·리트리버 테스트·Graph RAG 보조 검색에서 A의 청크(parent·child·요약)가 0건
- [ ] SC-2: 같은 KB에 해시가 같은 파일을 다시 올리면 사전 점검과 업로드 API 모두 차단(409)하고 기존 문서 정보를 안내
- [ ] SC-3: 개정 쌍 픽스처 세트에서 top-1 후보 정확도 ≥ 90%, 무관 문서 오제안 ≤ 5%
- [ ] SC-4: 되돌리기 실행 시 직전 버전이 즉시 검색에 복귀하고, 취소된 버전은 선택한 처리(분리/삭제)대로 반영
- [ ] SC-5: 근거 칩·원문 뷰어에 버전 라벨이 표시
- [ ] SC-6: 사전 점검 100%가 판정 로그에 기록되고, 운영자 최종 결정이 연결됨
- [ ] SC-7: LLM 실패 시에도 업로드 흐름이 끝까지 진행됨
- [ ] SC-8: 업로드 → 개정 확정 → 검색 확인 → 되돌리기까지 DB/Swagger 조작 없이 화면에서 완주 (S1 기준)

### 4.2 Quality Criteria

- [ ] 백엔드 pytest TDD(Red→Green→Refactor), 신규 모듈 테스트 파일 존재 (`verify-tdd`)
- [ ] 프론트 Vitest + RTL + MSW (MSW에서 `formData()` 사용 금지 — 기존 함정)
- [ ] DDL 컬럼 COMMENT 규칙 통과 (`tests/db/test_migration_ddl_comments.py`)
- [ ] `verify-architecture`·`verify-logging` 통과, 린트 0 오류, 빌드 성공

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 오판정 확정으로 멀쩡한 문서가 검색에서 빠짐 | High | Medium | 사람 확정 필수(suggest 모드), 확정 화면에 근거·두 문서 앞부분 노출, 되돌리기 제공 |
| 적재 성공 후 구버전 전환 실패 → 두 버전 동시 활성 | Medium | Low | 적재 후 전환 순서 고정, 재시도 + 불일치 표시, 목록에 "전환 미완료" 상태 노출·재시도 버튼 |
| 상태를 청크 payload에 쓰는 방식이면 대량 청크 업데이트 부분 실패 | High | Medium | Design에서 (a) 청크 payload 갱신 vs (b) 검색 시 MySQL의 superseded document_id 목록을 `must_not`으로 주입 비교 결정. (b)는 원자성 높으나 목록 증가 시 필터 크기 문제 |
| 필터 누락된 검색 경로가 남음(멀티쿼리·라우티드·ES 보조·리트리버 테스트 등) | High | Medium | Impact Analysis 6.2 경로 전수 목록 + 경로별 회귀 테스트, 필터 주입을 공통 지점 한 곳으로 모음 |
| 사전 점검 시 파싱 비용 2배(점검 + 실제 적재) | Medium | High | 점검은 앞부분만 파싱, 또는 점검 결과(파싱물) 단기 캐시를 check_id로 재사용 — Design에서 결정 |
| 파일명 정규화 규칙이 부서별 명명 관습을 못 따라감 | Medium | Medium | 본문 유사도·LLM 신호로 보완, 정규화 규칙은 코드 하드코딩 최소화(일반화 원칙) |
| HWP·엑셀 등 앞부분 텍스트가 빈약한 형식 | Medium | Medium | 형식별 대표 텍스트(시트명·머리글 등) 정의, 신호 부족 시 "후보 없음 + 수동 선택" 경로 |
| Flyway 버전 충돌(answer-citation이 V093·V094 점유) | Medium | Medium | V095 이후 사용, 머지 순서 확인, 로컬 DB 적용 이력 메모 |
| 인용 칩의 파일명 기준 중복 제거와 버전 표시 충돌 | Low | Medium | 칩 키를 lineage 기준으로 재정의할지 Design에서 결정 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `document_metadata` | DB 테이블 | 계보·버전·상태·해시·라벨·시행일 컬럼 추가 (Flyway V095+) |
| 판정 로그 테이블(신규) | DB 테이블 | 사전 점검·운영자 결정 기록 |
| `knowledge_base` | DB 테이블 | `revision_mode` 컬럼 추가 |
| KB 업로드 API | API | 선택 필드 `supersedes_document_id`·`version_label`·`effective_date`·`revision_check_id`, 해시 중복 409 |
| 사전 점검·이력·되돌리기·수동 연결·라벨 수정 API | API (신규) | 신규 엔드포인트 |
| KB 문서 목록 응답 | API 스키마 | `version_no`·`version_label`·`has_history`·`revision_status` 추가, 기본 active만 |
| `HybridSearchRequest`/`SearchFilter` | 도메인 VO | 문서 제외(`must_not`) 표현 추가 또는 상태 필터 |
| Qdrant payload / ES 문서 | 저장소 | (안 a 선택 시) `revision_status` 필드 추가·갱신 |
| 인용 라벨 | 응답 데이터 | 버전 라벨 포함 |
| 프론트 타입·서비스·훅 | Frontend | `types/knowledgeBase.ts`, `services/knowledgeBaseService.ts`, `hooks/useKnowledgeBases.ts`, 엔드포인트 상수 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| document_metadata | CREATE | `unified_upload/use_case.py:136` (KB·컬렉션·quick 공통) | 신규 컬럼 기본값으로 무영향, KB 경로만 계보 값 설정 |
| document_metadata | READ | `document_metadata_repository.find_by_kb_id`, `find_filenames`(근거 칩 라벨), doc_browse 목록 | 목록 기본 필터 변경 → Needs verification |
| document_metadata | DELETE | `doc_browse/delete_document_use_case.py`, `knowledge_base/delete_document_use_case.py:56` | 계보 처리(직전 버전 복귀) 추가 → Needs verification |
| 검색 | READ | `rag_agent/tools.py` `_single_query_search:385`·멀티쿼리 `:348`·라우티드 `:320`, `_hybrid_filters:132` | 제외 필터 주입 → Needs verification |
| 검색 | READ | `hybrid_search/use_case.py:100-117`(ES), `qdrant_vectorstore.py:194`(Qdrant, `_apply_section_summary_guard` 선례) | 필터 확장 → Needs verification |
| 검색 | READ | `routed_retrieval/use_case.py:133`, `graph_rag/es_evidence_fetcher.py:21` | 제외 필터 주입 → Needs verification |
| 검색 | READ | KB 리트리버 테스트 API, 콘텐츠 브라우저 | 리트리버 테스트는 제외, 콘텐츠 브라우저는 구버전 열람 허용 여부 Design 결정 |
| 인용 | READ | `agent_run/run_sources.py`, `agent_run/source_policy.py:182-197`, `source_viewer/enricher.py` | 버전 라벨 추가 → Needs verification |
| Graph RAG | 훅 | `graph_rag/hooks.py` post_ingest(`:39`)·deletion(`:107`) | 신버전은 정상 추출, 구버전 그래프 보존 → None |
| 프론트 | UI | `KbUploadDocumentModal.tsx`, `KbDocumentTable.tsx`, `KnowledgeBaseDetailPage`, `SourceCitation.tsx`, `sourceViewer/*` | UI 변경 |

### 6.3 Verification

- [ ] 6.2 검색 경로 전부에 superseded 제외 회귀 테스트
- [ ] 컬렉션 직접 업로드·quick setup 경로가 신규 컬럼 기본값으로 정상 동작
- [ ] 권한(KB 쓰기) 없는 사용자의 사전 점검·확정·되돌리기 거부

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Starter | ☐ |
| Dynamic | ☐ |
| **Enterprise** (DDD 레이어, main.py 단일 DI) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 판정 주체 | 사람 지정 / 시스템 제안+사람 확정 / 완전 자동 | **제안+확정** (auto 자리만) | "LLM은 제안, 사람이 확정" 원칙. 판정 로그로 auto 임계값 실측 후 전환 |
| 구버전 처리 | 하드 삭제 / 보존+검색 제외 / 보존+순위 하향 | **보존+검색 제외** | 섞임 완전 차단 + 이력·되돌리기 가능 |
| 판정 시점 | 사전 점검 후 적재 / 적재 후 검토 대기 | **사전 점검 후 적재** | 신버전이 적재 즉시 활성, 대기 상태 관리 불필요 |
| 전환 시점 | 확정 즉시 / 시행일 예약 | **확정 즉시** | 검색 필터에 날짜 비교 불필요. 시행일은 표시용 |
| 탐지 신호 | 파일명·본문 유사도·해시·LLM | **4종 모두** | 해시=중복 차단, 파일명·본문=후보 생성, LLM=최종 판정·근거 |
| 동일 파일 | 차단 / 경고 후 허용 / 대체 | **차단 + 기존 문서 안내** | 섞임의 직접 원인 제거 |
| Graph RAG 구버전 | 보조 검색 제외 / 그래프 삭제 / 범위 밖 | **보조 검색 근거 단계에서 제외** | 되돌리기 시 재추출 불필요 |
| 기존 중복 데이터 | 수동 연결 / 일괄 스캔 / 정리 안 함 | **목록에서 수동 개정 연결** | 기존 문서는 v1·active로 간주, 백필 없음 |
| 검색 제외 구현 | (a) 청크 payload `revision_status` 갱신 / (b) 질의 시 superseded ID 목록 `must_not` / (c) 혼합 | **Design에서 결정** | 원자성·필터 크기·성능 트레이드오프 비교 필요 |
| 사전 점검 파싱 재사용 | 앞부분만 별도 파싱 / check_id로 파싱물 캐시 | **Design에서 결정** | 비용 vs 복잡도 |
| 프론트 | React 19 + TanStack Query + Zustand (기존) | 기존 | — |
| 테스트 | pytest / Vitest + RTL + MSW | 기존 | TDD 공통 원칙 |

### 7.3 Clean Architecture Approach

```
idt/src/
  domain/document_revision/        # 계보·버전 엔티티, 파일명 정규화 정책, 판정 결과 VO, 포트(판정기·로그 저장소)
  application/document_revision/   # RevisionCheckUseCase, SupersedeUseCase, RollbackUseCase, LinkRevisionUseCase
  infrastructure/document_revision/# 판정 로그 repo, LLM 판정 어댑터, 유사도 계산 어댑터
  api/routes/knowledge_base_router.py  # 신규 엔드포인트 (또는 별도 라우터 — Design 결정)
  main.py                          # DI 등록 (단일 집중)
idt_front/src/
  types/knowledgeBase.ts · services/knowledgeBaseService.ts · hooks/useKnowledgeBases.ts
  components/knowledge-base/  KbUploadDocumentModal(점검 단계) · KbDocumentTable(버전 배지·이력)
```

---

## 8. Convention Prerequisites

- `idt/CLAUDE.md`·`idt_front/CLAUDE.md`·`idt/docs/rules/` 준수 (DDD 레이어 의존 방향, LOG-001, DI는 main.py)
- Flyway 파일명 `V0xx__*.sql`, 모든 컬럼 COMMENT, **V095 이후 번호** (answer-citation-verification의 V093·V094와 머지 순서 확인)
- API 스키마 변경 시 프론트 타입 동기화(`/api-contract-sync`)
- 컴포넌트 파일에서 런타임 상수 export 금지 — `as const`는 `src/types/*.ts`
- 백엔드 테스트 실행은 `uv run python -m pytest`

---

## 9. Next Steps

1. [ ] `/pdca design document-revision` — 3안 비교(특히 검색 제외 구현 a/b/c, 사전 점검 파싱 재사용, 라우터 배치)
2. [ ] Design 착수 전 worktree 생성(`wt/document-revision`) 후 이 Plan 문서를 그쪽으로 옮김 — master 체크아웃의 untracked docs가 pull을 막는 기존 함정 회피
3. [ ] 개정 쌍 픽스처 세트 준비(동일 파일명 개정, 파일명 변경 개정, 무관 문서, 완전 동일 파일, HWP/엑셀 포함)
4. [ ] Do → Check(gap 분석) → Report

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-21 | 초안 — 사용자 질의 3회(판정 주체·구버전 처리·탐지 신호·범위 / 흐름·시행일·이력·자동화 / 중복·그래프·기존 데이터) 반영 | 배상규 |
