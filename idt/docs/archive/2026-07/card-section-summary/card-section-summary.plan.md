# card-section-summary Planning Document

> **Summary**: 문서 등록 파이프라인 2단계 — clause-aware 청킹(1단계)이 산출한 조(條) 단위 parent 청크를 "카드 섹션"으로 삼아, 섹션마다 LLM으로 **키워드 목록 + 3줄 요약**을 생성해 저장한다. 요약은 동일 Qdrant 컬렉션에 `chunk_type='section_summary'`로 임베딩 저장(후속 리트리버 라우팅: 요약 검색 → rawchunk 확장), 키워드·요약 텍스트는 ES에 저장(키워드 검색 대비). 요약용 LLM은 관리자가 청킹 프로파일에 지정(기존 `llm_model` 테이블의 vLLM/OpenAI 등 재사용). 처리는 업로드 완료 후 백그라운드로 수행하며 상태(처리중/완료/실패)를 사용자에게 노출하고 재시도 API를 제공한다.
>
> **Project**: sangplusbot (idt 백엔드 전용)
> **Author**: 배상규
> **Date**: 2026-07-08
> **Status**: Draft
> **선행**: clause-aware-chunking (완료, `docs/archive/2026-07/clause-aware-chunking/`)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 현재 리트리버는 rawchunk(조·항 청크)를 직접 검색한다. 질의가 조문 표현과 다르면(일상어 질문 등) 벡터/BM25 매칭이 약해지고, 섹션 수준의 "이 조가 무엇에 관한 것인지" 신호가 없어 라우팅 기반 검색(요약으로 섹션 선별 → rawchunk 확장)을 만들 수 없다. 키워드 검색도 형태소 빈도 기반(`morph_keywords`)뿐이라 의미 기반 키워드가 없다. |
| **Solution** | 업로드 완료 후 백그라운드 잡이 문서의 각 카드 섹션(=clause-aware parent 청크)에 대해 LLM 1회 호출로 키워드 목록 + 3줄 요약을 생성한다. 요약은 임베딩되어 동일 Qdrant 컬렉션에 `chunk_type='section_summary'` + 원 parent 참조로 저장, 키워드·요약은 ES 전용 필드에 저장된다. 요약 LLM은 청킹 프로파일에 관리자가 지정(미지정 시 요약 비활성 — opt-in), vLLM 등 자가호스트 모델은 기존 `llm_model`(base_url) 인프라 그대로 사용. |
| **Function/UX Effect** | 관리자: 프로파일 수정 API로 문서 유형별 요약 모델 지정. 사용자: 업로드는 기존처럼 즉시 완료되고, 문서별 요약 진행 상태(처리중/완료/실패, 진행률)를 조회·재시도할 수 있다(화면은 후속, API 먼저). |
| **Core Value** | 3단계 라우팅 검색 구조(3번: 문서 요약 → 2번: 섹션 요약 → 1번: rawchunk)의 중간층 데이터가 축적된다. 요약·키워드는 기존 검색 경로에 혼입되지 않게 격리 저장되어(additive) 회귀 없이 후속 리트리버 개편의 기반이 된다. |

---

## 1. Overview

### 1.1 Purpose

문서 등록 3단계 파이프라인 중 **2단계(섹션 요약·키워드 추출)**를 구축한다.

```
1단계 (완료)   clause-aware 청킹 → rawchunk (조=parent / 항·호=child)
2단계 (이번)   카드 섹션(=parent 청크)별 키워드 + 3줄 요약 생성·저장
3단계 (후속)   섹션 요약 전체를 모아 문서 단위 요약 → 리트리버 1차 라우팅
```

최종 목표 검색 흐름(후속 PDCA): 질의 → 문서 요약(3번)으로 문서 선별 → 섹션 요약(2번)으로 섹션 라우팅 → 해당 섹션의 rawchunk(1번) 확장. 키워드는 키워드(BM25/term) 검색 보조로 사용.
**이번 사이클은 2단계 데이터의 생성·저장·상태관리까지**이며, 검색 경로 연동은 범위 밖이다.

### 1.2 Background — 현재 구조 (2026-07-08 코드 확인)

**1단계 산출물이 섹션 식별 정보를 이미 보유**
- `ClauseAwareStrategy` parent 청크 메타데이터: `chunk_type="parent"`, `chunk_id`, `children_ids`, `clause_title`(조 제목), `page_start/page_end`, `boundary` (`src/infrastructure/chunking/strategies/clause_aware_strategy.py:144-152`). → 카드 섹션 1개 = parent 청크 1개로 매핑 가능, 섹션→rawchunk 연결은 `chunk_id`/`children_ids`로 자동.

**LLM 모델 관리 인프라 존재 — 신규 테이블 불필요**
- `llm_model` 테이블 + 관리자 CRUD (`src/application/llm_model/`), `base_url` 컬럼으로 vLLM 등 OpenAI 호환 엔드포인트 지원 (V035, `src/domain/llm_model/entity.py:47`).
- 팩토리: `LLMFactory.create(llm_model, temperature) -> BaseChatModel` (`src/infrastructure/llm/llm_factory.py:16-28`) — vLLM은 openai provider + base_url + 더미키 처리(`:33-46`). `find_default → factory.create` 사용 선례: `slot_extractor.py:176-179`.

**저장·검색 인프라**
- 업로드는 Qdrant/ES 병렬 저장(`unified_upload/use_case.py:100-108`), Qdrant payload는 문자열 캐스팅 저장(`:255-263`), ES는 고정 필드 화이트리스트(`:280-296`).
- Qdrant 벡터 검색은 `chunk_type="child"` 필터로 격리(`parent_child_retriever.py:168`) → `section_summary` 타입 추가가 기존 벡터 검색에 혼입되지 않음.
- ES BM25는 `multi_match(content^1.5, morph_text)` (`hybrid_search/use_case.py:92-98`) — **chunk_type 필터 여부 미확인, 혼입 방지 방안은 Design에서 확정**(§4-3).
- `VALID_CHUNK_TYPES = {"parent","child","full","semantic"}` (`domain/chunking/value_objects.py`) 및 `Literal` 스키마(`domain/chunking/schemas.py:53`), `MetadataFilter` 검증(`domain/retriever/value_objects/metadata_filter.py:41`) — `section_summary` 확장 지점.

**백그라운드 처리 선례**
- `agent_schedule`: 회차별 독립 세션·짧은 트랜잭션으로 LLM 실행, 개별 실패 격리 (`trigger_due_schedules_use_case.py:86-152`). 상태·이력 기록 패턴 참고.
- 업로드 시점 LLM 요약/키워드 추출 코드는 현재 없음(형태소 기반 `morph_keywords`만 존재).

**DB 마이그레이션**: 최신 V042 → 이번 사이클은 V043부터.

### 1.3 사용자 결정 사항 (2026-07-08 확인)

| 질문 | 결정 |
|------|------|
| 카드 섹션 단위 | **조 단위 parent 청크 재사용** — 단, 장·절 등 상위 경계로 변경이 용이하도록 섹션 소스를 추상화(§4-1) |
| 처리 시점 | **업로드 후 백그라운드** — 사용자가 화면에서 알 수 있게 처리중/완료/실패 상태 데이터를 남김 |
| 실행 방식 | **인프로세스 태스크(asyncio) + 재시도 API** — 외부 cron 불요, 서버 재시작 유실분은 재시도로 복구 |
| 저장 구조 | **Qdrant 동일 컬렉션(`chunk_type='section_summary'`) + ES 신규 필드** — MySQL에 요약 원본 별도 보관 없음 |
| 요약 LLM 선택 | **청킹 프로파일에 모델 지정** — 기존 `llm_model` 테이블 참조(vLLM 등은 관리자가 llm_model에 등록 후 선택) |

---

## 2. Scope

### 2.1 In Scope (백엔드 idt/)

**A. 청킹 프로파일 확장 — 요약 설정**
- [ ] `V043__alter_chunking_profile_add_summary.sql`(additive): `summary_llm_model_id`(VARCHAR(36) NULL, FK→llm_model — 콜레이션 관례 준수: CHARSET/COLLATE 명시 금지), 필요 시 `summary_keyword_count` 등 파라미터 컬럼(구성은 Design 확정)
- [ ] 의미: **NULL = 섹션 요약 비활성(opt-in)** / 값 = 해당 프로파일로 업로드된 문서는 요약 잡 생성
- [ ] `ChunkingProfile` 엔티티·정책·관리자 CRUD API에 필드 additive 반영 (모델 존재·활성 검증은 UseCase에서)

**B. 섹션 요약 잡 도메인 + 영속화**
- [ ] `domain/section_summary/`(가칭): `SectionSummaryJob` 엔티티(document_id, collection_name, kb_id, profile_id, llm_model_id, status[pending/processing/completed/failed], total_sections/done_sections/failed_sections, error, 타임스탬프), Repository 인터페이스, 정책(상태 전이·재시도 가능 조건)
- [ ] `V044__create_section_summary_job.sql` — 잡 테이블(문서 단위 1행). 섹션 단위 결과 행 분리 여부는 Design 확정(추천: 잡 1행 + 섹션별 성공 여부는 Qdrant 존재로 판정 — 과도한 정규화 회피)
- [ ] 부분 실패 모델: 일부 섹션 실패 시 status/카운트 표현과 재시도 시 실패분만 재처리하는 규칙은 Design 확정

**C. 섹션 요약 파이프라인 (application)**
- [ ] 섹션 소스 추상화: `SectionSource`(가칭) — "문서의 섹션 목록(id, title, text, children 참조)" 조회 인터페이스. v1 구현 = Qdrant에서 `document_id + chunk_type='parent'` scroll (후속: 장·절 단위 소스로 교체 가능, §4-1)
- [ ] `SummarizeSectionsUseCase`(가칭): 잡 클레임 → 섹션별 LLM 1회 호출(structured output: `keywords: list[str]` + `summary`(3줄)) → 요약 임베딩 → Qdrant point(`chunk_type='section_summary'`, payload: `section_ref`(원 parent chunk_id), `clause_title`, `keywords`, `summary`, `document_id`, `kb_id` 등) + ES 문서 저장 → 진행 카운트 갱신
- [ ] LLM 호출 동시성 제한(semaphore) + 섹션 단위 실패 격리(한 섹션 실패가 잡 전체를 중단하지 않음)
- [ ] DB 상태 갱신은 독립 세션·짧은 트랜잭션(agent_schedule 선례) — LLM 호출을 트랜잭션에 묶지 않음
- [ ] vLLM 등 structured output 미지원 모델 폴백(JSON 프롬프트 + 파싱) 여부는 Design 확정

**D. 업로드 연동 (additive)**
- [ ] KB 업로드 완료 시: 사용된 프로파일에 `summary_llm_model_id`가 있으면 잡 레코드 생성(pending) + `asyncio.create_task`로 즉시 실행 킥오프. 업로드 응답은 기존대로 즉시 반환(요약 잡 id/상태 포함 여부는 Design)
- [ ] 요약 잡 생성·실행 실패가 업로드 성공 상태를 훼손하지 않음(완전 격리)
- [ ] 프로파일 미지정/요약 비활성 경로는 기존 동작 완전 불변(회귀 가드)

**E. 상태 조회·재시도 API**
- [ ] `GET .../documents/{document_id}/section-summary` — 잡 상태 + 진행률(total/done/failed) (경로·KB 스코프는 Design 확정, 프론트 화면 연동은 후속)
- [ ] `POST .../documents/{document_id}/section-summary/retry` — failed(및 서버 재시작으로 남은 stale processing) 잡 재실행, 실패분만 재처리
- [ ] 목록 조회(KB 단위 문서별 상태) 필요 여부는 Design 확정

**F. 저장소 확장 (additive)**
- [ ] `VALID_CHUNK_TYPES`/`chunking/schemas.py` Literal/`MetadataFilter` 검증에 `section_summary` 추가 — 사용처 전수 확인
- [ ] ES 매핑 신규 필드: 요약 텍스트·LLM 키워드 전용 필드(기존 BM25 `multi_match` 대상 필드에 혼입되지 않는 저장 방식 — §4-3, Design 확정)
- [ ] 문서 삭제 시 요약 청크 동반 삭제 — 기존 삭제 경로가 `document_id` 기준이면 자동 커버, 확인 후 필요 시 보강

**G. 테스트 (TDD — 구현 전 작성)**
- [ ] 파이프라인 단위: 섹션→LLM 호출→저장 흐름, structured output 파싱, 섹션 단위 실패 격리, 진행 카운트, 동시성 제한
- [ ] 잡 상태 전이·재시도 정책 테스트(pending→processing→completed/failed, 실패분만 재처리)
- [ ] 프로파일 요약 설정 검증(존재하지 않는/비활성 모델 422)
- [ ] 업로드 연동: 요약 활성 프로파일 업로드 시 잡 생성, 비활성 시 기존 동작 불변(회귀 가드), 잡 실패 시 업로드 상태 무영향
- [ ] 검색 격리 가드: `section_summary` 청크가 기존 child 벡터 검색·BM25 결과에 나타나지 않음

### 2.2 Out of Scope (후속 PDCA)

| 항목 | 사유/비고 |
|------|-----------|
| 리트리버 라우팅 연동(요약 검색 → rawchunk 확장) | 2단계 데이터 축적 후 검색 경로 개편으로 진행 |
| 3단계: 문서 단위 요약(섹션 요약 집계) + 1차 라우팅 | 이번 산출물(섹션 요약)을 입력으로 사용 — §7 로드맵 |
| 키워드 검색 경로 개편(LLM 키워드 활용 검색) | 키워드는 저장까지만, 검색 활용은 라우팅 개편과 함께 |
| 프론트엔드(프로파일 모델 지정 UI, 업로드 진행 상태 표시) | API 검증 후 `/api-contract-sync`와 함께 |
| 기존 적재 문서 백필(재요약) | 신규 업로드부터 적용, 백필은 별도 사이클 |
| cron 보정(유실 잡 자동 재처리) | 재시도 API로 시작, 운영상 필요해지면 agent_schedule 선례로 추가 |
| 요약 프롬프트의 프로파일별 커스터마이즈 | 고정 프롬프트로 시작 |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 우선순위 |
|----|----------|---------|
| FR-01 | 관리자는 청킹 프로파일에 섹션 요약용 LLM 모델(`llm_model` 참조, vLLM 포함)을 지정/해제할 수 있다. 존재하지 않거나 비활성 모델 지정은 422 | High |
| FR-02 | 요약 모델이 지정된 프로파일로 업로드가 완료되면 섹션 요약 잡이 자동 생성되고 백그라운드로 실행된다. 업로드 응답은 기존처럼 즉시 반환 | High |
| FR-03 | 각 카드 섹션(=parent 청크)에 대해 LLM 1회 호출로 키워드 목록 + 3줄 요약을 생성한다 | High |
| FR-04 | 섹션 요약은 임베딩되어 동일 Qdrant 컬렉션에 `chunk_type='section_summary'` + 원 parent 참조(`section_ref`)로 저장된다 | High |
| FR-05 | 키워드·요약 텍스트가 ES에 저장되어 후속 키워드 검색에 사용 가능하다 | High |
| FR-06 | 사용자는 문서별 요약 잡 상태(처리중/완료/실패)와 진행률(total/done/failed 섹션 수)을 API로 조회할 수 있다 | High |
| FR-07 | 실패한 잡을 재시도 API로 재실행할 수 있으며, 성공한 섹션은 재처리하지 않는다 | High |
| FR-08 | `section_summary` 청크는 기존 검색 경로(child 벡터 검색, BM25)에 혼입되지 않는다 | High |
| FR-09 | 요약 잡의 생성·실행 실패는 업로드 결과(status)에 영향을 주지 않는다. 개별 섹션 실패는 잡 전체를 중단시키지 않는다 | High |
| FR-10 | 요약 미활성 프로파일·기존 업로드 경로는 동작이 완전히 불변이다 | High |
| FR-11 | 잡 실행 로그에 문서/프로파일/모델/섹션 수가 request_id와 함께 기록된다 | Medium |

### 3.2 Non-Functional Requirements

| ID | 요구사항 |
|----|----------|
| NFR-01 | 기존 엔드포인트·유스케이스·전략·검색에 회귀 없음 (additive-only). 기존 검색 격리를 위한 필터 보강은 동작 보존 수정으로만 허용 |
| NFR-02 | Thin DDD 준수 — 파이프라인 로직은 application, LLM/저장은 infrastructure 주입, 상태 전이 규칙은 domain 정책 |
| NFR-03 | TDD — 테스트 선작성 (pytest) |
| NFR-04 | 함수 40줄 이하, if 중첩 2단계 이하, config 하드코딩 금지(키워드 개수·동시성 상한 등은 상수/설정) |
| NFR-05 | 로깅 규칙(LOG-001) — print 금지, 스택 트레이스 보존, request_id 전파 |
| NFR-06 | DB 세션 규칙 — repository 내 commit/rollback 금지, 백그라운드 잡은 독립 세션·짧은 트랜잭션(LLM 호출을 트랜잭션에 포함 금지) |
| NFR-07 | LLM 호출 동시성 제한 및 섹션 수 상한(폭주 방지) — 값은 Design 확정 |
| NFR-08 | 요약/키워드 텍스트 길이 상한(프롬프트 지시 + 저장 전 방어 절단) — Qdrant payload/ES 필드 비대 방지 |

---

## 4. 핵심 설계 방향 (Plan 레벨 결정, 상세는 Design)

1. **섹션 소스 추상화 (변경 용이성 요구)**: "카드 섹션"의 출처를 `SectionSource` 인터페이스로 분리 — v1은 Qdrant의 parent 청크(조) scroll. 후속에 장·절 등 상위 경계 섹션으로 바꿀 때 소스 구현만 교체하고 요약 파이프라인·저장 계약은 불변. 섹션 계약: `{section_id, title, text, document_id}`.
2. **1 섹션 = 1 LLM 호출**: 키워드 + 3줄 요약을 structured output 1회로 획득(호출 수 최소화). 요약 3줄은 "라우팅용 대표성"이 목적 — 프롬프트에 조 제목(`clause_title`) 컨텍스트 포함.
3. **검색 격리가 최우선 제약**: Qdrant는 기존 child 필터로 자동 격리 확인됨. ES는 BM25 `multi_match(content, morph_text)`에 안 걸리도록 **요약·키워드를 전용 필드에만 저장하고 `content`를 채우지 않는 방식(추천)** vs 기존 쿼리에 chunk_type 제외 필터 추가 — Design에서 확정. 격리 여부는 회귀 가드 테스트로 검증.
4. **상태 모델은 문서 단위 잡 1행**: total/done/failed 카운트로 진행률 표현. 섹션별 성공 여부는 저장소(Qdrant point 존재)로 판정해 재시도 시 실패분만 재처리 — 섹션별 상태 테이블은 만들지 않음(과도한 정규화 회피). 정확한 상태 전이·stale processing(서버 재시작 잔존) 판정 기준은 Design.
5. **late binding 일관성**: 요약 모델은 잡 생성 시점의 프로파일 값을 잡 레코드에 스냅샷(실행 중 프로파일 변경에 영향받지 않음). 모델이 실행 시점에 비활성이면 잡 failed + 명확한 에러 메시지.
6. **3단계 대비**: 섹션 요약 산출물은 `document_id`로 전량 수집 가능해야 함(Qdrant scroll) — 3번(문서 요약)이 별도 저장 없이 입력으로 사용.

---

## 5. Risks & Mitigations

| 리스크 | 영향 | 대응 |
|--------|------|------|
| 요약 청크가 기존 검색 결과에 혼입 | 답변 품질 오염, 회귀 | Qdrant: child 필터 격리 확인됨. ES: 전용 필드 저장(또는 필터 보강)으로 격리 + 회귀 가드 테스트 필수 |
| 문서당 섹션 수십~수백 → LLM 비용·시간 폭증 | vLLM/API 과부하, 잡 장기화 | 동시성 semaphore + 섹션 수 상한 + 프로파일 단위 opt-in(모델 미지정 시 비활성) |
| 서버 재시작 시 processing 잡 고아화 | 상태 영구 '처리중' 표시 | stale 판정 기준(updated_at 경과) + 재시도 API로 복구. cron 보정은 후속 |
| vLLM 모델이 structured output(함수 호출) 미지원 | 키워드/요약 파싱 실패 | JSON 프롬프트 + 관대한 파싱 폴백을 Design에서 확정, 파싱 실패는 섹션 단위 실패로 격리 |
| `VALID_CHUNK_TYPES`/Literal 확장 누락 지점 | 저장·조회 시 검증 예외 | `chunk_type` 사용처 전수 조사(Design 체크리스트) + 타입 확장 테스트 |
| 재시도 시 중복 저장(동일 섹션 요약 2건) | 라우팅 검색 중복 | 요약 point id를 `section_ref` 기반 결정적 생성(upsert) — Design 확정 |
| 문서 삭제 후 요약 청크 잔존 | 고아 데이터, 잘못된 라우팅 | 기존 삭제 경로의 `document_id` 기준 삭제 범위 확인, 미커버 시 보강 |
| 대형 조문(parent 2000토큰)이 LLM 컨텍스트 부담 | 요약 품질 저하/비용 | 프로파일 parent 상한이 이미 존재. 입력 절단 상한 적용(doc-extractor 20000자 절단 선례) |

---

## 6. Acceptance Criteria

- [ ] 관리자가 프로파일에 요약 모델 지정(PUT) → 해당 KB 업로드 → 업로드 응답 즉시 반환 + 잡 생성 확인
- [ ] 잡 완료 후: Qdrant 동일 컬렉션에 섹션 수만큼 `section_summary` point(keywords/summary/section_ref/clause_title payload) + ES에 키워드·요약 저장
- [ ] 상태 조회 API가 pending→processing(진행률 증가)→completed 전이를 반환
- [ ] 일부 섹션 강제 실패 시 잡 상태·failed 카운트 반영, 재시도 API가 실패분만 재처리해 completed 도달
- [ ] 존재하지 않는/비활성 모델을 프로파일에 지정 시 422
- [ ] 요약 비활성 프로파일·기존 경로 업로드는 잡 미생성 + 기존 동작 불변(회귀 가드)
- [ ] `section_summary` 청크가 기존 하이브리드 검색(벡터 child + BM25) 결과에 미노출(격리 테스트)
- [ ] 기존 테스트 스위트 신규 회귀 0건 (사전 실패분 제외)
- [ ] `/verify-architecture`, `/verify-tdd`, `/verify-logging` 통과

---

## 7. 후속 로드맵 (참고)

1. **document-summary-routing (3단계)**: 섹션 요약 전량을 집계해 문서 단위 요약 생성 → 리트리버 1차 라우팅(문서 선별) 데이터
2. **summary-routed-retrieval**: 검색 경로 개편 — 질의 → (문서 요약) → 섹션 요약 검색 → `section_ref`로 rawchunk(parent/children) 확장 + LLM 키워드 활용 키워드 검색
3. **section-summary-frontend**: 프로파일 요약 모델 지정 UI + 문서 목록의 요약 진행 상태 표시 (`/api-contract-sync`)
4. **section-summary-backfill**: 기존 적재 문서 일괄 요약(배치) + cron 보정(유실 잡 자동 재처리)
