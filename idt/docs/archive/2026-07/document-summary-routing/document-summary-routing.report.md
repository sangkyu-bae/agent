# document-summary-routing 완료 리포트

> **Feature**: document-summary-routing (문서 단위 요약 자동 체이닝 — 문서 등록 3단계)
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Period**: 2026-07-09 (Plan → Report, 단일 세션)
> **Final Match Rate**: **99%** (최초 98% → Low Gap 3건 즉시 해소)
> **Status**: ✅ Completed — **문서 등록 파이프라인 3계층(rawchunk→섹션 요약→문서 요약) 완성**

---

## Executive Summary

### 1.1 개요

| 항목 | 내용 |
|------|------|
| Feature | document-summary-routing |
| 기간 | 2026-07-09 (Plan·Design·Do·Check·Report) |
| PDCA 흐름 | Plan ✅ → Design ✅ → Do ✅ → Check ✅ (99%) → Report ✅ |
| 아키텍처 | Thin DDD |
| 선행 사이클 | clause-aware-chunking(1단계) → card-section-summary(2단계) — 3부작 완결 |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| Match Rate | 99% (D1~D15 반영, 데이터 계약/흐름 100%) |
| 신규 프로덕션 파일 | 1개 (`document_summary_step.py` 322 LOC) |
| 수정(additive) 파일 | 12개 (domain 5·app 2·infra 3·api/config 2) |
| **마이그레이션 / 신규 API / ES 매핑 변경** | **0 / 0 / 0** (설계 목표 달성 — gap-detector 코드 확인) |
| 신규/확장 테스트 | 약 25건 (step 신규 11 + 정책 8 + 체이닝 4 + 기타) — 관련 스위트 총 110건 통과 |
| 회귀 | 0건 (2단계 전체 + KB/프로파일/라우터 77 + 격리 영향권 320 그린) |
| High/Medium 잔여 Gap | 0건 (Low 3건 Check 중 즉시 해소) |

### 1.3 Value Delivered

| Perspective | 전달된 가치 (실측) |
|-------------|---------------------|
| **Problem** | 섹션(조) 요약까지는 있었지만 "이 문서가 무엇에 관한 것인지" 문서 수준 신호가 없어 리트리버 1차 라우팅(질의→문서 후보 선별)을 만들 수 없던 문제 → 문서당 1개의 대표 요약 point 자동 생성. |
| **Solution** | 섹션 요약 잡 completed 직전 자동 체이닝: 섹션 요약 전량(제목+3줄, chunk_index 순) → cap(24000자) 이내 LLM 1회 / 초과 시 배치 중간 요약→최종 2계층 → 동일 컬렉션 `chunk_type='document_summary'`(결정적 uuid5 멱등 upsert) + ES 기존 필드 저장. 문서 키워드는 섹션 키워드 빈도 집계(LLM 0회). |
| **Function/UX Effect** | 사용자 개입 0 — 업로드 한 번이면 rawchunk→섹션 요약→문서 요약까지 자동. 기존 상태/재시도 API 그대로(completed 의미 확장), 재시도는 섹션 LLM 재호출 없이 문서 요약만 재생성(별도 코드 없이 기존 멱등 구조에서 자동 성립). |
| **Core Value** | **3계층 라우팅 데이터 완성** — 후속 summary-routed-retrieval은 계층 하강(문서→`document_id`→섹션→`section_ref`→rawchunk)만 구현하면 됨. 격리 가드를 요약 타입 집합으로 일반화해 검색 회귀 0 유지. |

---

## 2. 구현 범위

### 2.1 신규 (1개)

| 파일 | 역할 |
|------|------|
| `infrastructure/section_summary/document_summary_step.py` (322 LOC) | 자기완결 문서 요약 단계 — 모델 검증→수집→단일/계층 요약(`LlmDocumentSummarizer`: structured→JSON 폴백)→키워드 집계→임베딩(`filename+요약`)→ES 먼저·Qdrant 마지막 멱등 저장 |

### 2.2 수정 (additive, 12개)

- **domain**: entities(`document_summary_id_for`·`SectionSummaryItem`·`DocumentSummaryRecord`), interfaces(`DocumentSummaryStepInterface`), policy(`aggregate_keywords` 빈도·동률 등장순 상위 15 / `sanitize_document_output` 5줄·300자), `VALID_CHUNK_TYPES` 2곳 += `document_summary`
- **application**: 러너 체이닝(`_run_document_summary` — step=None이면 기존 동작 완전 불변), doc_browse 열람 제외 집합 확장
- **infrastructure**: `list_summary_items` 수집기(빈 요약 스킵·정렬), `parse_summary_json` 공용 승격(섹션 요약자는 위임 — 동작 불변), Qdrant 가드 일반화(`_SUMMARY_CHUNK_TYPES` + MatchAny, 명시 필터 bypass 유지)
- **api/config**: main.py step 배선, config 2개(`document_summary_input_char_cap=24000`, `max_batches=10`), KB 라우터 description(completed 의미) 갱신

---

## 3. 핵심 설계 결정 이행 (D1~D15: 15/15)

- **D1 additive 체이닝**: optional 주입으로 2단계 러너 테스트 무수정 통과 — "기능 확장 = 기존 경로 불변" 원칙 3연속 적용.
- **D4 재시도 free win**: 별도 코드 0줄 — 기존 done_refs 스킵 + failed==0 재진입이 "섹션 LLM 0회 + 문서 요약만 재생성"을 자동 성립(설계 단계 코드 확인으로 발견, 테스트로 고정).
- **D8 계층 요약**: cap 이내 전량 1회 / 초과 시 연속 구간 배치→중간(5줄)→최종. 배치 상한 초과는 명시 실패(조용한 탈락 금지).
- **D9 키워드 집계**: LLM 0회 결정론적 — 섹션 키워드와의 일관성 보장 + 비용 0.
- **D12 가드 일반화**: 단일 타입 must_not → 요약 타입 집합 MatchAny 1조건 — 이후 요약 계층이 늘어도 집합 원소 추가만.

## 4. Gap 처리 (Check 98% → 99%, 전부 Low)

| # | Gap | 조치 |
|---|-----|------|
| G1 | FR-11 성공 로그에 `llm_model_id` 누락 | 로그 필드 추가 → 해소 |
| G2 | 중간 요약 줄 수 프롬프트 하드코딩 | `_INTERIM_SUMMARY_LINES` 상수화 + 최종 프롬프트 `DOC_SUMMARY_LINES` 참조 → 해소 |
| G3 | 단일 블록>cap 극단 케이스 방어 없음 | 블록 방어 절단 + 테스트 추가 → 해소 |

## 5. 검증 결과

- **테스트**: 관련 스위트 110건 통과(신규/확장 ~25건 포함). 회귀: 2단계 + KB/프로파일/라우터 77건, 격리 영향권(doc_browse·업로드·하이브리드·청킹·retriever) 320건 그린.
- **verify 핵심 검사**: print 0, `logger.error` 전건 `exception=`, domain→infra 0, infra Policy 0, 신규 모듈 테스트 보유.
- **배선**: `import src.api.main` OK.
- **회귀 보존 명시 검증**(gap-detector): step=None 경로·가드 bypass·parse 위임·2단계 테스트 구조 4항목 확인.

## 6. 후속 과제

1. **summary-routed-retrieval (다음 사이클)**: 질의 → 문서 요약 검색(1차, 명시 필터로 가드 통과) → 섹션 요약(2차) → `section_ref` rawchunk 확장(3차) + LLM 키워드 검색 — **3계층 데이터 완성으로 착수 조건 충족**.
2. **section-summary-frontend**: 프로파일 모델 지정 UI + 요약 진행 상태 표시 (`/api-contract-sync`).
3. **section-summary-backfill**: 기존 적재 문서 일괄 요약(섹션+문서) + cron 보정.
4. **routing-quality-eval**: RAGAS 인프라 재사용 — 라우팅 검색 vs 기존 하이브리드 정확도 실측.
5. **운영**: 별도 마이그레이션/설정 불필요 — 2단계 V043/V044 적용 + 프로파일 요약 모델 지정만으로 3단계까지 자동 동작.

## 7. 학습 노트

- **"잡 확장이지 신규 잡이 아니다"의 배당**: 상태 머신·재시도 API·stale 판정·멱등 패턴을 전부 재사용해 마이그레이션 0·API 0으로 기능 하나를 얹음 — 선행 사이클에서 진실 원천을 저장소(Qdrant point)에 둔 설계가 확장 비용을 극적으로 낮춤.
- **재시도 요구사항이 공짜였던 이유**: 2단계의 "완료 판정 = point 존재" 결정이 3단계의 "실패 시 문서 요약만 재생성"을 코드 0줄로 만들었다. 멱등성을 데이터에 내장하면 제어 흐름이 단순해진다.
- **요약의 요약은 비용 상수화**: 문서 요약 입력을 원문이 아닌 섹션 요약으로 한정 — LLM 비용이 문서 크기와 무관하게 1~수회로 고정(섹션 비례 비용은 2단계에서 이미 지불).
- **가드는 처음부터 집합으로**: 2단계의 단일 타입 가드를 3단계에서 집합으로 일반화 — 계층형 데이터를 쌓는 파이프라인이라면 격리 메커니즘은 첫 설계에서 확장 가능형으로 두는 편이 갱신 비용을 줄인다.
