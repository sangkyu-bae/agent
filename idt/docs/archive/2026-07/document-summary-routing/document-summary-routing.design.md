# document-summary-routing Design Document

> **Plan**: `docs/01-plan/features/document-summary-routing.plan.md`
> **Author**: 배상규
> **Date**: 2026-07-09
> **Status**: Draft
> **선행**: card-section-summary (완료 — `docs/archive/2026-07/card-section-summary/`, 이하 "2단계")

---

## 1. 설계 요약

섹션 요약 잡의 completed 전이 직전에 **문서 요약 단계를 체이닝**한다. 4개 블록:

1. **러너 체이닝**: `SummarizeSectionsUseCase._run_processing`의 `failed == 0` 분기에 `DocumentSummaryStep` 호출 삽입 (optional 주입 — None이면 기존 동작 완전 불변)
2. **문서 요약 생성**: 섹션 요약 전량 수집(Qdrant scroll) → cap 이내 단일 패스 / 초과 시 배치 중간 요약→최종(2계층) → 키워드는 섹션 키워드 빈도 집계(LLM 0회)
3. **저장**: 동일 컬렉션 `chunk_type='document_summary'` 1 point/문서(결정적 uuid5, ES 먼저→Qdrant 마지막) — **ES 신규 매핑 필드 0, DB 마이그레이션 0, 신규 API 0**
4. **격리 일반화**: Qdrant 가드 must_not을 요약 타입 집합으로 확장(MatchAny), doc_browse 제외 확장, `VALID_CHUNK_TYPES` 2곳 확장

### 코드 확인으로 확정된 사실 (2026-07-09 — 2단계 직접 구현분)

| 확인 항목 | 결과 | 영향 |
|-----------|------|------|
| 체이닝 삽입 지점 | `use_case.py:108` — `_execute` 반환 failed==0 → completed 전이 직전 | D1: 이 사이에 step 호출, 예외는 자체 catch로 "document summary failed:" prefix (D3) |
| 재시도 흐름 | 재시도 시 `done_refs` 스킵으로 pending 0 → `_execute` 반환 0 → failed==0 분기 재진입 | 문서 요약 실패 잡의 재시도가 **섹션 LLM 재호출 0회로 문서 요약만 재생성** — 추가 코드 불필요 (D4) |
| 섹션 0건 문서 | `_execute`가 빈 sections에 start_progress(0,0) 후 0 반환 → completed | 문서 요약은 수집 결과 0건이면 warning+스킵, completed 유지(기존 동작 불변, D5) |
| 섹션 요약 payload | `{chunk_type, section_ref, clause_title, chunk_index(str), keywords(list), summary, document_id, kb_id, kb_name?, user_id, collection_name, filename?}` (`summary_writer.py:_qdrant_payload`) | 수집기가 title/summary/keywords/chunk_index + 공통 메타(kb_name/user_id/filename) 전부 확보 가능 (D6) |
| scroll 인프라 | `QdrantSectionSource._scroll(collection, document_id, chunk_type)` 공용 헬퍼 존재 | `list_summary_items()` additive 메서드로 재사용 (D6) |
| ES 요약 필드 | `summary_text`/`summary_keywords`/`clause_title`/`section_ref` 매핑 존재 (2단계 D7) | 문서 요약이 `summary_text`/`summary_keywords` 재사용 — **매핑 무수정 확정** (D8) |
| Qdrant 가드 | `_apply_section_summary_guard` — 단일 타입 must_not, 명시 요청 시 해제 (`qdrant_vectorstore.py:166-191`) | 타입 집합 + `MatchAny`로 일반화, bypass 규칙 유지 (D9) |
| JSON 폴백 | `LlmSectionSummarizer._parse`(코드펜스 제거+json.loads)가 클래스 내부 static | module 함수로 승격해 문서 요약자와 공유 — 기존 클래스는 위임(동작 불변, D7) |
| 잡 스냅샷 | job에 `llm_model_id`/`embedding_provider`/`embedding_model` 보유, `SessionScopedLlmModelRepository.find_by_id` 싱글턴 사용 가능 | step이 자체적으로 모델 로드/검증(러너와 분리, 자기완결) (D2) |
| 마이그레이션 | 최신 V045 | **이번 사이클 마이그레이션 0** (D3 — 문서 요약 존재의 진실 원천 = Qdrant point) |

---

## 2. 설계 결정 (Decisions)

| ID | 결정 | 근거 |
|----|------|------|
| D1 | **체이닝 = 러너 additive 주입**: `SummarizeSectionsUseCase.__init__(..., document_summary_step: DocumentSummaryStepInterface \| None = None)`. `_run_processing`의 `failed == 0` 분기에서 step 실행 → 성공 시 completed / 예외 시 failed(`"document summary failed: {e}"[:1000]`). **None이면 기존 2단계 동작 완전 불변**(회귀 가드 + 단계적 배선) | 사용자 결정(자동 체이닝). optional 주입은 2단계 `summary_launcher=None` 선례 — 기존 테스트 무수정 통과 |
| D2 | **step은 자기완결 단일 인터페이스**: `DocumentSummaryStepInterface.run(job, request_id) -> None`(실패 시 raise). 구현 `DocumentSummaryStep`(infrastructure)이 모델 로드/검증(SessionScoped repo)·수집·LLM·집계·임베딩·저장을 내부 조립 | 러너 테스트는 fake step 하나로 충분(2단계 러너 테스트 패턴 유지). 모델 재로드는 DB 1읽기 — `_execute` 스코프와의 결합 회피 비용으로 수용 |
| D3 | **상태 모델 무변경**: 마이그레이션 0, 신규 컬럼 0, 신규 API 0. completed 의미 = "섹션 전량 + 문서 요약 성공"으로 확장 — 업로드/상태/재시도 엔드포인트의 OpenAPI description만 갱신. 문서 요약 존재의 진실 원천 = Qdrant `document_summary` point(2단계 D3 철학) | Plan §4-1. 프론트 미구현 시점이라 의미 확정 적기. `has_document_summary` 응답 필드는 요청당 Qdrant 조회 비용 대비 가치 낮음 — 후속 프론트 사이클에서 필요 시 재검토 |
| D4 | **재시도 = 문서 요약만 재생성**: 별도 코드 없이 기존 done_refs 스킵 + failed==0 재진입으로 자동 성립(코드 확인). 문서 요약 upsert 멱등이므로 존재 검사 없이 항상 재생성 | 단순성 우선 — 재생성 비용 LLM 1회는 재시도가 필요한 상황(직전 실패)에서만 발생 |
| D5 | 섹션 요약 수집 결과 **0건이면 warning 로그 + 스킵, completed 유지** | 빈 문서의 기존 completed 동작 불변(FR-09). 라우팅 관점에서도 섹션 없는 문서는 문서 요약 무의미 |
| D6 | **수집기 = `QdrantSectionSource.list_summary_items()` additive 메서드**: `_scroll(collection, document_id, "section_summary")` 재사용 → `SectionSummaryItem(title, summary, keywords, chunk_index, meta)` chunk_index 정렬 반환. 공통 메타(kb_name/user_id/filename)는 첫 item의 meta passthrough | 기존 scroll 헬퍼·정렬·meta 추출 관례 재사용. 신규 인터페이스는 domain `interfaces.py`에 additive(`list_summary_items`는 `SectionSourceInterface` 확장이 아닌 step 내부 concrete 사용 — infra→infra 허용) |
| D7 | **LLM 호출 계약**: `DocumentSummaryOutput{summary_lines: list[str]}` (키워드 없음 — 집계로 대체). 프롬프트 입력 = `[섹션 제목] + 3줄 요약`을 chunk_index 순 `\n\n` join. structured output → JSON 폴백 1회 재시도는 2단계 패턴 재사용 — `llm_summarizer._parse`를 module 함수 `parse_summary_json(content, required_keys)`로 승격(기존 클래스 위임, 동작 불변) 후 공유. temperature 0.0 | vLLM 폴백 요구 동일. 코드 중복 대신 공용 함수 승격(40줄 규칙) |
| D8 | **계층 요약(2계층 고정)**: 결합 입력 ≤ `document_summary_input_char_cap`(설정, 기본 24000자)이면 **단일 패스 LLM 1회**. 초과 시 chunk_index 연속 구간으로 cap 이하 배치 분할 → 배치별 중간 요약(LLM 1회/배치, `INTERIM_SUMMARY_LINES=5`줄) → 중간 요약 결합해 최종 요약. 배치 수 > `document_summary_max_batches`(기본 10) → **명시적 실패**(조용한 탈락 금지, 2단계 max_sections 철학). 중간 결합이 여전히 cap 초과하는 극단 케이스는 절단 + warning(2계층 고정) | 사용자 결정(상한 내 전량 + 초과 시 계층). cap 24000 근거: 섹션 요약 1건 ≈ 제목+3줄 ≈ 200~400자 → 문서 60~120섹션까지 단일 패스. max 10배치 = 섹션 상한 500(2단계 D17)과 정합 |
| D9 | **문서 요약 출력 규격**: 최종 요약 `DOC_SUMMARY_LINES=5`줄(라인당 300자 절단 — 2단계 `MAX_LINE_CHARS` 재사용), 문서 키워드 = 섹션 keywords 합집합 **빈도 내림차순·동률 등장순 상위 `MAX_DOC_KEYWORDS=15`개**(domain `SectionSummaryJobPolicy.aggregate_keywords` — 결정론적, LLM 0회). `sanitize_document_output` = 기존 `sanitize_output`의 줄 수 파라미터화 또는 전용 메서드 | Plan §4-3. 라우팅 대표성엔 3줄보다 넉넉한 5줄, 키워드는 섹션과 일관성 보장(집계) |
| D10 | **저장 계약**: id = `document_summary_id_for(document_id)` = `uuid5(NAMESPACE_URL, f"document-summary:{document_id}")`(domain entities additive). **ES 먼저 → Qdrant 마지막**(2단계 D6 순서 관례), ES `_id` 동일 — 재시도 멱등. 임베딩 입력 = `f"{filename}\n{summary_text}"`(filename 없으면 summary만), 모델은 잡 스냅샷 | 2단계 D5/D6 패턴 준용. filename(규정명)이 문서 대표성에 기여 |
| D11 | **Qdrant payload / ES body** (§4 상세): payload에 `section_count`(str) 추가, `section_ref`/`clause_title` 없음 — 그 외 섹션 요약 계약과 동일 키. ES는 기존 필드(`summary_text`/`summary_keywords`)만 사용, `section_count`는 ES 미기재(**매핑 무수정 확정**) | Plan §4-5. ES 신규 필드 0 목표 달성 |
| D12 | **가드 일반화**: `qdrant_vectorstore`의 단일 타입 상수 → `_SUMMARY_CHUNK_TYPES = frozenset({"section_summary", "document_summary"})`. must_not은 `FieldCondition(chunk_type, MatchAny(any=[...]))` 1개로. bypass 규칙: 호출자가 명시한 chunk_type이 요약 타입 집합에 속하면 가드 해제(후속 라우팅은 must 필터가 타입을 고정하므로 안전). 기존 가드 테스트를 집합 기준으로 갱신 | Plan §4-4. 이후 요약 계층 추가 시 집합에 원소만 추가 |
| D13 | doc_browse post-filter를 `chunk_type not in {"section_summary","document_summary"}`로 확장. `VALID_CHUNK_TYPES` 2곳 += `"document_summary"` + `DOCUMENT_SUMMARY_CHUNK_TYPE` 상수 | 2단계 D9/D18 동일 확장 |
| D14 | **설정(config.py)**: `document_summary_input_char_cap=24000`, `document_summary_max_batches=10` 2개만. 줄 수·키워드 N은 domain 상수(정책 소속 — 검증 규칙) | NFR-04. 2단계 D17 관례(운영 조정 가능성 있는 것만 설정) |
| D15 | **로깅(FR-11)**: 성공 시 info `"Document summary generated"` — request_id/job_id/document_id/section_count/pass_mode("single"\|"hierarchical")/batches. 스킵(D5)은 warning, 실패는 러너 error 경로 재사용 | 2단계 FR-11 Gap(G3) 교훈 — 로그 필드를 설계에 명시 |

---

## 3. 파일 구조 (신규/수정)

```
idt/
├── src/
│   ├── domain/section_summary/
│   │   ├── entities.py      [수정: document_summary_id_for, SectionSummaryItem, DocumentSummaryRecord]
│   │   ├── interfaces.py    [수정: DocumentSummaryStepInterface (additive)]
│   │   └── policy.py        [수정: aggregate_keywords, sanitize_document_output (D9)]
│   ├── domain/chunking/value_objects.py                 [수정: VALID_CHUNK_TYPES += document_summary]
│   ├── domain/retriever/value_objects/metadata_filter.py [수정: 동일]
│   ├── application/
│   │   ├── section_summary/use_case.py                  [수정: D1 체이닝 (additive 주입)]
│   │   └── doc_browse/get_chunks_use_case.py            [수정: D13 제외 집합]
│   ├── infrastructure/
│   │   ├── section_summary/
│   │   │   ├── document_summary_step.py                 [신규: DocumentSummaryStep + LlmDocumentSummarizer (핵심)]
│   │   │   ├── qdrant_section_source.py                 [수정: list_summary_items (D6)]
│   │   │   └── llm_summarizer.py                        [수정: parse_summary_json 공용 승격 (D7, 동작 불변)]
│   │   └── vector/qdrant_vectorstore.py                 [수정: D12 가드 일반화]
│   ├── api/
│   │   ├── routes/knowledge_base_router.py              [수정: description만 — completed 의미 갱신 (D3)]
│   │   └── main.py                                      [수정: step 생성·러너 주입]
│   └── config.py                                        [수정: D14 설정 2개]
└── tests/
    ├── domain/section_summary/test_policy.py            [수정: aggregate_keywords·문서 절단 케이스]
    ├── application/section_summary/test_use_case.py     [수정: 체이닝 4케이스 (§6)]
    ├── infrastructure/section_summary/
    │   ├── test_document_summary_step.py                [신규: 단일/계층/스킵/저장 계약/모델 검증]
    │   └── test_qdrant_section_source.py                [수정: list_summary_items]
    ├── infrastructure/vector/test_qdrant_search_guard.py [수정: 집합 가드·양 타입 bypass]
    └── application/doc_browse/test_get_chunks_use_case.py [수정: document_summary 제외]
```

**마이그레이션 0 · 신규 API 0 · ES 매핑 수정 0** (D3/D11)

---

## 4. 저장 데이터 계약

### 4.1 Qdrant `document_summary` point (동일 컬렉션, 문서당 1개)

```
id      = uuid5(NAMESPACE_URL, f"document-summary:{document_id}")   # 멱등 (D10)
vector  = embed(f"{filename}\n{summary_text}")                      # 잡 스냅샷 임베딩 모델
payload = {
  "content": <5줄 요약 텍스트>,
  "chunk_type": "document_summary",
  "chunk_id": <document_summary_id>,
  "document_id": <document_id>,               # → 삭제 동반 + 섹션/rawchunk 하강 연결 (후속 라우팅)
  "collection_name": ..., "kb_id": ...,
  "kb_name": ..., "user_id": ..., "filename": ...,   # 섹션 payload passthrough (D6)
  "keywords": <섹션 키워드 집계 상위 15, list[str]>,
  "summary": <5줄 요약("\n" join)>,
  "section_count": <str>,
}
```

### 4.2 ES 문서 (`_id` = document_summary_id — 기존 매핑 필드만)

```
{
  "chunk_id", "chunk_type": "document_summary",
  "summary_text": <5줄 요약>, "summary_keywords": [<집계 키워드>...],
  "document_id", "user_id", "collection_name", "kb_id", "kb_name"?, "filename"?
  # content/morph_* 없음(BM25 미노출), section_ref/clause_title 없음, 신규 필드 없음 (D11)
}
```

---

## 5. 흐름

### 5.1 러너 체이닝 (D1)

```
_run_processing(job):
  failed = _execute(job)                    # 기존 — 섹션 처리 (재시도 시 전부 스킵되면 0)
  if failed != 0: → failed (기존)
  if self._document_summary_step is None: → completed (기존 동작 불변)
  try:
      await step.run(job, request_id)       # D2 자기완결
  except Exception as e:
      → failed, error = f"document summary failed: {e}"[:1000]   # D3
      return
  → completed                               # = 섹션 전량 + 문서 요약 성공
```

### 5.2 DocumentSummaryStep.run (D2/D5/D7/D8/D9/D10)

```
1. model = llm_model_repo.find_by_id(job.llm_model_id) — 부재/비활성 raise
2. items = source.list_summary_items(job.collection_name, job.document_id)   # chunk_index 순
   items 0건 → warning + return (스킵, D5)
3. combined = "\n\n".join(f"[{title}]\n{summary}")
4. summary_lines:
   len(combined) <= cap → 단일 패스 LLM 1회
   else → 연속 구간 배치 분할(각 ≤ cap) → 배치 수 > max_batches → raise (명시 실패)
          → 배치별 중간 요약(5줄) → 결합(초과 시 절단+warning) → 최종 요약 LLM 1회
5. clean = policy.sanitize_document_output(summary_lines)                    # 5줄·300자 절단
   keywords = policy.aggregate_keywords([item.keywords ...], MAX_DOC_KEYWORDS)  # 빈도·등장순, LLM 0회
6. vector = embedding.embed_text(f"{filename}\n{clean.summary_text}")
7. ES index → Qdrant upsert (결정적 ID, ES 먼저)                              # D10
8. info "Document summary generated" (pass_mode/batches/section_count)       # D15
```

---

## 6. 테스트 계획 (TDD — 구현 전 작성)

| 파일 | 핵심 케이스 |
|------|------------|
| `test_policy.py` (수정) | aggregate_keywords: 빈도 내림차순·동률 등장순·중복/공백 제거·15개 절단·빈 입력 / sanitize_document_output: 5줄·300자·0줄 raise |
| `test_use_case.py` (수정, 러너 체이닝) | ① 섹션 성공+step 성공 → completed & step.run 1회 ② step 예외 → failed("document summary failed:") ③ failed>0 → step 미호출 ④ step=None → 기존 completed(회귀 가드) ⑤ 재시도(전 섹션 done) → 섹션 LLM 0회 + step 호출 |
| `test_document_summary_step.py` (신규) | 단일 패스(cap 이내 LLM 1회·프롬프트에 전 섹션 포함), 계층 패스(배치 분할·중간 N회+최종 1회·연속 구간), max_batches 초과 raise, items 0건 스킵(저장 0), 모델 비활성 raise, 저장 계약(§4.1/4.2 — 결정적 ID·ES 필드·content/morph_* 부재·ES→Qdrant 순서), JSON 폴백 |
| `test_qdrant_section_source.py` (수정) | list_summary_items: 필터(chunk_type=section_summary)·chunk_index 정렬·keywords list 복원·meta passthrough |
| `test_qdrant_search_guard.py` (수정) | 기본 검색 must_not = {section_summary, document_summary}(MatchAny), 각 요약 타입 명시 요청 시 bypass, 기존 필터 보존 |
| `test_get_chunks_use_case.py` (수정) | document_summary 청크 열람 제외 |
| 기존 스위트 | 2단계 75건 중 러너/가드/열람 관련만 갱신, 나머지 무수정 통과 |

---

## 7. 구현 순서 (Do 체크리스트)

1. **domain**: `VALID_CHUNK_TYPES` 2곳 + entities(`document_summary_id_for`/`SectionSummaryItem`/`DocumentSummaryRecord`) + policy(`aggregate_keywords`/`sanitize_document_output`) + `DocumentSummaryStepInterface` (+ 테스트 선작성)
2. **격리 확장**: 가드 일반화(D12) + doc_browse(D13) (+ 기존 테스트 갱신)
3. **infrastructure**: `parse_summary_json` 승격(D7) → `list_summary_items`(D6) → `DocumentSummaryStep`+`LlmDocumentSummarizer`(D8/D10) (+ 테스트 선작성)
4. **application**: 러너 체이닝(D1) (+ 체이닝 테스트 5케이스)
5. **배선**: config 2개(D14) + main.py step 생성·주입 + KB 라우터 description 갱신(D3)
6. **검증**: 전체 테스트 + `/verify-architecture` + `/verify-tdd` + `/verify-logging` + 2단계 회귀 확인
