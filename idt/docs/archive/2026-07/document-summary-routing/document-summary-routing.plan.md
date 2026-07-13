# document-summary-routing Planning Document

> **Summary**: 문서 등록 파이프라인 3단계 — 2단계(card-section-summary)가 저장한 **섹션 요약 전량을 모아 문서 단위 요약을 생성·저장**한다. 섹션 요약 잡이 completed되는 시점에 같은 러너 흐름에서 자동 체이닝(추가 LLM 1~수회)으로 생성하며, 동일 Qdrant 컬렉션에 `chunk_type='document_summary'` 1 point/문서(결정적 ID 멱등 upsert) + ES 기존 요약 전용 필드로 저장한다. 문서 키워드는 섹션 키워드 합집합(LLM 추가 호출 없음). 입력이 상한을 초과하는 대용량 문서는 배치 중간 요약 → 최종 요약의 2계층(map-reduce)으로 처리한다. 이 데이터는 후속 사이클(summary-routed-retrieval)에서 리트리버 1차 라우팅(질의→문서 선별)의 검색 대상이 된다.
>
> **Project**: sangplusbot (idt 백엔드 전용)
> **Author**: 배상규
> **Date**: 2026-07-09
> **Status**: Draft
> **선행**: clause-aware-chunking(1단계, 완료) → card-section-summary(2단계, 완료 — `docs/archive/2026-07/card-section-summary/`)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 2단계까지로 섹션(조) 단위 요약은 확보했지만, "이 문서가 무엇에 관한 것인지"를 대표하는 문서 수준 신호가 없어 리트리버 1차 라우팅(질의→문서 후보 선별)을 만들 수 없다. 질의가 여러 문서에 걸친 KB에서는 섹션 요약만으로 후보 공간이 넓다. |
| **Solution** | 섹션 요약 잡 완료 직후 같은 러너에서 자동 체이닝: 섹션 요약 전량(제목+3줄)을 chunk_index 순으로 결합 → LLM 1회(상한 초과 시 배치 중간 요약→최종의 2계층) → 문서 대표 요약 생성 → 동일 컬렉션 `document_summary` point(문서당 1개, 멱등) + ES 저장. 키워드는 섹션 키워드 합집합 상위 N(추가 LLM 없음). |
| **Function/UX Effect** | 사용자 개입 불필요 — 업로드하면 섹션 요약→문서 요약까지 자동. 기존 상태/재시도 API 의미 확장(completed = 섹션 전량 + 문서 요약 성공, 재시도 시 완료 섹션 스킵 후 문서 요약만 재생성). 신규 API·마이그레이션 없이 동작(Design에서 최종 확정). |
| **Core Value** | 3계층 라우팅 데이터(문서 요약 → 섹션 요약 → rawchunk) 완성. 문서 요약은 `document_id`로 섹션·rawchunk와 연결되어 후속 라우팅 검색이 계층 하강만 구현하면 됨. 기존 검색 격리 체계(D8 가드)를 확장 적용해 회귀 0 유지. |

---

## 1. Overview

### 1.1 Purpose

문서 등록 3단계 파이프라인의 마지막 데이터 계층을 구축한다.

```
1단계 (완료)   clause-aware 청킹 → rawchunk (조=parent / 항·호=child)
2단계 (완료)   카드 섹션(=parent)별 키워드+3줄 요약 → section_summary
3단계 (이번)   섹션 요약 전량 집계 → 문서 단위 요약 → document_summary
후속           summary-routed-retrieval: 질의 → 문서 요약(1차) → 섹션 요약(2차) → rawchunk 확장
```

**이번 사이클은 문서 요약의 생성·저장까지**다(사용자 확정). 라우팅 검색 경로 개편은 범위 밖.

### 1.2 Background — 현재 구조 (2단계 산출물, 2026-07-08 구축)

**재사용 가능한 2단계 자산** (전부 이번 사이클의 빌딩블록):

- **러너/잡 인프라**: `SummarizeSectionsUseCase.run()`이 섹션 전량 처리 후 `failed==0`이면 completed 전이(`src/application/section_summary/use_case.py`). 잡 스냅샷(llm_model_id/embedding provider·model)과 `SessionScopedSectionSummaryJobStore`(독립 짧은 세션) 보유 — **문서 요약 체이닝은 completed 전이 직전에 단계 하나를 끼워넣는 구조**.
- **섹션 요약 데이터**: Qdrant payload `{chunk_type: "section_summary", section_ref, clause_title, chunk_index, keywords(list), summary, document_id, kb_id, ...}` — `document_id` scroll로 전량 수집 가능(2단계 Plan §4-6이 이 사용처를 예고).
- **저장 계약/격리**: ES 요약 전용 필드(`summary_text`/`summary_keywords`/`clause_title`)는 **문서 요약이 그대로 재사용 가능**(신규 매핑 불필요 가능성 높음 — Design 확정). Qdrant 격리는 `QdrantVectorStore._apply_section_summary_guard`(must_not) 단일 초크포인트 — `document_summary` 타입 추가 확장.
- **멱등 패턴**: `summary_id_for()`(uuid5) 선례 → `document-summary:{document_id}` 결정적 ID로 재시도 안전.
- **LLM 폴백**: `LlmSectionSummarizer`의 structured output→JSON 폴백 패턴 재사용(vLLM 대응).
- **chunk_type 게이트**: `VALID_CHUNK_TYPES` 2곳(`domain/chunking/value_objects.py`, `metadata_filter.py`) + doc_browse post-filter — `document_summary` 추가 지점 명확.

**마이그레이션**: 최신 V045(agent-recursion-limit). 이번 사이클은 **신규 테이블/컬럼 없이 가능**할 것으로 예상(잡 상태 의미 확장으로 처리, §4-2) — 필요 여부는 Design에서 최종 확정.

### 1.3 사용자 결정 사항 (2026-07-09 확인)

| 질문 | 결정 |
|------|------|
| 사이클 범위 | **문서 요약 생성·저장까지** — 라우팅 검색 경로 개편은 후속(summary-routed-retrieval) 분리 |
| 생성 시점 | **섹션 요약 완료 직후 자동 체이닝** — 같은 러너 흐름, 사용자 개입 불필요, 재시도 시에도 자동 |
| 저장 구조 | **동일 컬렉션 `chunk_type='document_summary'` + ES** — 섹션 요약과 동일 패턴(결정적 ID·격리·동반 삭제) |
| 대용량 문서 | **상한 내 전량 1회 + 초과 시 계층 요약** — 배치 중간 요약 → 최종 요약(map-reduce 2계층) |

---

## 2. Scope

### 2.1 In Scope (백엔드 idt/)

**A. 문서 요약 생성 단계 (러너 체이닝)**
- [ ] `SummarizeSectionsUseCase` 확장: 섹션 처리 후 `failed_sections == 0`일 때 문서 요약 단계 실행 → 성공 시 completed / 실패 시 failed(명확한 error, 예: "document summary failed: ...") — **completed의 의미 = 섹션 전량 + 문서 요약까지 성공**
- [ ] 문서 요약 실패 후 재시도: 기존 done_refs 스킵 로직으로 섹션은 전부 스킵 → 문서 요약만 재생성(멱등 upsert)
- [ ] 섹션이 0건(전량 실패/빈 문서)이면 문서 요약 스킵(기존 failed 흐름 유지)

**B. 문서 요약 생성 로직 (infrastructure)**
- [ ] 입력 수집: Qdrant에서 `document_id + chunk_type='section_summary'` scroll → chunk_index 순 정렬 → `[{clause_title, summary, keywords}]` (2단계 `QdrantSectionSource` 확장 또는 신규 메서드)
- [ ] 단일 패스: 결합 입력이 `document_summary_input_char_cap` 이내면 LLM 1회로 문서 요약 생성(요약 줄 수 기본값·프롬프트는 Design 확정, 섹션 요약과 동일 폴백 패턴)
- [ ] 계층 패스(map-reduce): 초과 시 섹션 요약을 cap 단위 배치로 분할 → 배치별 중간 요약 → 중간 요약 결합해 최종 요약(2계층 고정 — 중간 요약 결합도 초과하는 극단 케이스는 절단+warning, Design 확정)
- [ ] 문서 키워드: **LLM 추가 호출 없이** 섹션 키워드 합집합에서 빈도/등장순 상위 N개(N은 상수, Design 확정)

**C. 저장 (섹션 요약 계약 준용)**
- [ ] Qdrant: `document_summary` point 1개/문서 — id = `uuid5("document-summary:{document_id}")`(멱등), vector = 요약 임베딩(잡 스냅샷 임베딩 모델), payload = `{chunk_type, chunk_id, document_id, kb_id, kb_name, user_id, collection_name, filename, summary, keywords, section_count, content=summary}`
- [ ] ES: `_id` = 동일 결정적 ID, 기존 요약 전용 필드(`summary_text`/`summary_keywords`) 재사용 + `chunk_type='document_summary'` — **신규 매핑 필드 없이 가능하면 매핑 무수정**(Design 확정)
- [ ] 문서 삭제 동반: payload/body에 `document_id` 포함 → 기존 `document_id` 기준 삭제 경로가 자동 커버(2단계와 동일)

**D. 격리 확장 (동작 보존 수정)**
- [ ] `VALID_CHUNK_TYPES` 2곳에 `document_summary` 추가
- [ ] Qdrant 어댑터 가드: must_not 대상을 요약 타입 집합({section_summary, document_summary})으로 일반화 — 명시 필터 시 해제 규칙 유지, 기존 가드 테스트 갱신
- [ ] doc_browse post-filter에 `document_summary` 추가
- [ ] ES는 기존 D7 방식(content/morph_* 미기재)으로 자동 격리 — BM25 무영향

**E. 상태 노출 (additive, 최소)**
- [ ] 기존 상태 API(`GET .../section-summary`)에 문서 요약 상태 노출 필요 여부·방식(예: `document_summary_done` 필드 vs completed 의미 내포로 충분)은 Design에서 확정 — 신규 엔드포인트는 만들지 않음

**F. 테스트 (TDD — 구현 전 작성)**
- [ ] 체이닝: 섹션 성공 → 문서 요약 생성 → completed / 문서 요약 실패 → failed(+error) / 재시도 시 섹션 스킵 + 문서 요약만 재생성
- [ ] 계층 요약: cap 이내 1회 호출, 초과 시 배치 분할·중간→최종 호출 횟수, 키워드 합집합 상위 N
- [ ] 저장 계약: 결정적 ID, payload/ES body, 섹션 0건 스킵
- [ ] 격리 가드: `document_summary`가 기존 검색·doc_browse에 미노출(기존 section_summary 테스트 확장)
- [ ] 회귀 가드: 2단계 기존 테스트(75건) 무수정 통과 또는 의미 확장분만 갱신

### 2.2 Out of Scope (후속 PDCA)

| 항목 | 사유/비고 |
|------|-----------|
| 리트리버 라우팅 검색(질의→문서 요약→섹션 요약→rawchunk) | 데이터 3계층 완성 후 summary-routed-retrieval로 |
| 문서 요약 전용 별도 잡/상태 테이블 | 섹션 요약 잡의 completed 의미 확장으로 흡수(사용자 결정 — 자동 체이닝) |
| 프론트엔드(진행 상태·문서 요약 표시) | section-summary-frontend와 통합 후속 |
| 기존 문서 백필 | section-summary-backfill과 함께 |
| KB/컬렉션 단위 상위 요약 | 문서 단위까지만 — 필요성 확인 후 재검토 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| FR-01 | 섹션 요약 잡의 모든 섹션이 성공하면 같은 실행 흐름에서 문서 요약이 자동 생성된다 | High |
| FR-02 | 문서 요약 입력은 해당 문서의 섹션 요약 전량(제목+요약, chunk_index 순)이며, 상한 이내면 LLM 1회로 생성된다 | High |
| FR-03 | 입력이 상한을 초과하면 배치 중간 요약 → 최종 요약의 2계층으로 생성된다(전량 반영, 조용한 탈락 금지) | High |
| FR-04 | 문서 요약은 동일 Qdrant 컬렉션에 `chunk_type='document_summary'` 1 point/문서로 저장되고 결정적 ID로 재시도 시 멱등이다 | High |
| FR-05 | 문서 요약·키워드가 ES에 저장된다(기존 요약 전용 필드 재사용). 문서 키워드는 섹션 키워드 합집합 상위 N(LLM 추가 호출 없음) | High |
| FR-06 | 잡 completed = 섹션 전량 + 문서 요약 성공. 문서 요약 실패 시 잡 failed + 원인 식별 가능한 error | High |
| FR-07 | 재시도 시 완료된 섹션은 재처리하지 않고 문서 요약부터 재생성된다 | High |
| FR-08 | `document_summary` 청크는 기존 검색 경로(벡터/BM25)와 doc_browse 열람에 노출되지 않는다 | High |
| FR-09 | 섹션 요약이 0건인 문서는 문서 요약을 생성하지 않는다(잡은 기존 실패 의미 유지) | Medium |
| FR-10 | 문서 삭제 시 문서 요약 point/ES 문서가 동반 삭제된다(기존 document_id 기준 경로) | High |
| FR-11 | 문서 요약 생성 로그에 document_id/잡/모델/입력 섹션 수/패스 방식(단일·계층)이 request_id와 함께 기록된다 | Medium |

### 3.2 Non-Functional Requirements

| ID | 요구사항 |
|----|----------|
| NFR-01 | 기존 검색·업로드·2단계 섹션 요약 동작에 회귀 없음. 가드 확장은 동작 보존 수정으로만 |
| NFR-02 | Thin DDD — 생성 로직은 인터페이스 뒤(infrastructure), 흐름 제어는 application, 규칙(cap·키워드 N·줄 수 절단)은 domain 정책 |
| NFR-03 | TDD — 테스트 선작성 (pytest) |
| NFR-04 | 함수 40줄 이하, if 중첩 2단계 이하, config 하드코딩 금지(cap·배치 크기는 settings) |
| NFR-05 | LOG-001 — print 금지, exception= 필수, request_id 전파 |
| NFR-06 | DB-001 — 문서 요약 단계도 기존 JobStore 경유(독립 짧은 세션), LLM/임베딩 호출은 트랜잭션 밖 |
| NFR-07 | 대용량 방어 — 계층 요약 배치 수 상한 + 최종 입력 절단(NFR-08 선례), 방어 절단은 domain 정책에 |

---

## 4. 핵심 설계 방향 (Plan 레벨 결정, 상세는 Design)

1. **잡 확장이지 신규 잡이 아니다**: 문서 요약은 섹션 요약 잡의 마지막 단계. 상태 머신·재시도 API·stale 판정 전부 기존 것 재사용. 신규 테이블/컬럼 없이 가능하면 마이그레이션 0(문서 요약 존재의 진실 원천 = Qdrant point, 2단계 D3와 동일 철학). 상태 API additive 필드 필요성만 Design에서 판단.
2. **입력은 섹션 요약이지 원문이 아니다**: 문서 요약 = 요약의 요약. rawchunk를 다시 읽지 않음 — 비용 상수화(섹션 수에 비례하는 LLM 호출은 2단계에서 이미 지불). 계층 패스도 섹션 요약 텍스트만 다룬다.
3. **키워드는 집계, 요약만 생성**: 문서 키워드는 섹션 키워드 빈도 집계(결정론적) — LLM 비용 0, 섹션 키워드와의 일관성 보장.
4. **격리 가드의 일반화**: 2단계의 단일 타입 가드(must_not section_summary)를 "요약 타입 집합" 가드로 일반화 — 이후 요약 계층이 늘어도 집합에 추가만. 명시 필터 통과 규칙은 타입별 동일.
5. **저장 계약 재사용 우선**: ES 신규 필드 0을 목표(기존 `summary_text`/`summary_keywords` + chunk_type 구분). Qdrant payload도 섹션 요약 계약에서 section_ref→(없음), clause_title→(없음), `section_count` 추가 정도의 최소 차이.
6. **후속 라우팅 대비 계약**: 문서 요약 point는 `document_id`·`kb_id`를 보유 — 1차 라우팅(문서 선별) 후 `document_id`로 섹션 요약(2차), `section_ref`로 rawchunk(3차)로 하강하는 검색이 추가 데이터 없이 가능해야 한다.

---

## 5. Risks & Mitigations

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 체이닝으로 잡 실행 시간 증가(+LLM 1~수회) | 대형 문서 진행률 체감 저하 | 문서 요약은 섹션 완료 후 1스텝 — 진행 카운트는 이미 100% 표시, 로그로 단계 가시화. 계층 패스 배치 수 상한 |
| 계층 요약의 품질 저하(중간 요약에서 정보 손실) | 라우팅 정확도 하락 | 배치를 chunk_index 순 연속 구간으로 유지(문서 흐름 보존) + 중간 요약 줄 수를 최종보다 넉넉히. 품질 검증은 후속 라우팅 사이클에서 실측 |
| 문서 요약 실패가 잡 전체를 failed로 표시 | "섹션은 다 됐는데 실패" 혼동 | error 메시지에 단계 명시("document summary failed") + 재시도는 문서 요약만 재실행(빠름). 상태 필드 분리는 Design 판단 |
| 2단계 가드/열람 테스트와의 충돌 | 기존 테스트 갱신 필요 | must_not 집합 일반화 시 기존 section_summary 가드 테스트를 파라미터화 확장(의미 변화 없음 확인) |
| 재시도마다 문서 요약 재생성(섹션 무변화여도) | 소액 LLM 비용 중복 | 멱등 upsert라 정합성 문제 없음 — 1회 호출 비용 수용(존재 검사 추가는 Design에서 비용/복잡도 비교) |
| 섹션 요약 잡 completed 의미 변경 | 기존 상태 소비자(프론트 예정) 혼동 | 프론트 미구현 상태라 지금이 의미 확정 적기 — API description 갱신 + 리포트 명시 |

---

## 6. Acceptance Criteria

- [ ] 요약 활성 프로파일 KB 업로드 → 잡 completed 시점에 Qdrant `document_summary` point 1개(결정적 ID, summary/keywords/section_count payload) + ES 문서 존재
- [ ] 섹션 요약 텍스트가 cap 이내인 문서: LLM 1회 / 초과 문서: 배치 중간 요약→최종 요약 호출 패턴 확인(단위 테스트)
- [ ] 문서 키워드 = 섹션 키워드 합집합 상위 N (결정론적, LLM 무호출)
- [ ] 문서 요약 단계 강제 실패 → 잡 failed(+단계 명시 error) → 재시도 → 섹션 LLM 재호출 0회 + 문서 요약 재생성 → completed
- [ ] `document_summary`가 하이브리드 검색(벡터/BM25)·doc_browse 결과에 미노출(격리 테스트)
- [ ] 문서 삭제 후 document_summary point/ES 문서 잔존 0
- [ ] 2단계 기존 테스트 회귀 0건(사전 실패분 제외) + `/verify-architecture`, `/verify-tdd`, `/verify-logging` 통과

---

## 7. 후속 로드맵 (참고)

1. **summary-routed-retrieval**: 질의 → 문서 요약 검색(1차, 명시 필터로 가드 통과) → 섹션 요약(2차) → `section_ref` rawchunk 확장(3차) + LLM 키워드 검색 — 3계층 데이터 완성으로 착수 가능
2. **section-summary-frontend**: 프로파일 모델 지정 UI + 문서별 요약(섹션·문서) 진행 상태 표시 (`/api-contract-sync`)
3. **section-summary-backfill**: 기존 적재 문서 일괄 요약(섹션+문서) + cron 보정
4. **routing-quality-eval**: RAGAS 인프라(RAGAS-001) 재사용해 라우팅 검색 vs 기존 하이브리드 정확도 실측
