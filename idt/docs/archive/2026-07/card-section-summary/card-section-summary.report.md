# card-section-summary 완료 리포트

> **Feature**: card-section-summary (카드 섹션 키워드+3줄 요약 백그라운드 파이프라인 — 문서 등록 2단계)
> **Project**: sangplusbot (idt 백엔드)
> **Author**: 배상규
> **Period**: 2026-07-08 (Plan → Report, 단일 세션)
> **Final Match Rate**: **99%** (최초 98% → 경미 Gap 3건 즉시 해소)
> **Status**: ✅ Completed (백엔드) — 리트리버 라우팅 연동·3단계(문서 요약)·프론트는 후속 PDCA

---

## Executive Summary

### 1.1 개요

| 항목 | 내용 |
|------|------|
| Feature | card-section-summary |
| 기간 | 2026-07-08 (Plan·Design·Do·Check·Report) |
| PDCA 흐름 | Plan ✅ → Design ✅ → Do ✅ → Check ✅ (99%) → Report ✅ |
| 아키텍처 | Thin DDD (Domain·Application·Infrastructure·Interfaces) |
| 선행 사이클 | clause-aware-chunking (1단계 rawchunk — 조=parent 청킹) |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| Match Rate | 99% (D1~D18 설계 결정 18/18 반영) |
| 신규 프로덕션 파일 | 14개 (Python 12개 1,211 LOC + 마이그레이션 V043/V044) |
| 수정(additive) 파일 | 15개 (config·chunk_type 집합 2곳·ES 매핑·Qdrant 어댑터·프로파일 4종·KB 3종·라우터 2종·main.py) |
| 신규 테스트 | 75건 (신규 파일 63 + 기존 파일 추가 12, 1,033 LOC) — 전부 통과 |
| 관련 기존 스위트 회귀 | 0건 (라우터 34·애플리케이션 121·인프라/도메인 330 통과, 관측 실패 8건은 stash 검증으로 사전 실패 확인) |
| High/Medium 잔여 Gap | 0건 (Medium 1건은 Check 중 즉시 해소) |
| 검증 스킬 | /verify-architecture(신규 위반 0)·/verify-logging·/verify-tdd 통과 |

### 1.3 Value Delivered

| Perspective | 전달된 가치 (실측) |
|-------------|---------------------|
| **Problem** | 리트리버가 rawchunk를 직접 검색해 일상어 질의와 조문 표현의 괴리 시 매칭이 약하고, 섹션 수준 라우팅 신호·의미 기반 키워드가 부재하던 문제 → 카드 섹션(=조 parent)별 LLM 키워드+3줄 요약 데이터를 자동 축적하는 파이프라인 구축. |
| **Solution** | 업로드 완료 후 인프로세스 백그라운드 잡이 섹션당 LLM 1회 호출(structured output→JSON 폴백)로 키워드+요약 생성 → 동일 Qdrant 컬렉션 `chunk_type='section_summary'`(결정적 uuid5 ID, 멱등 upsert) + ES 전용 필드 저장. 요약 LLM은 청킹 프로파일에 관리자 지정(`summary_llm_model_id`, NULL=비활성) — vLLM은 기존 `llm_model`(base_url) 인프라 재사용. |
| **Function/UX Effect** | 관리자: 프로파일 API로 문서 유형별 요약 모델 지정(부재/비활성 모델 422). 사용자: 업로드 즉시 응답 + `GET .../section-summary`로 진행률(total/done/failed·stale) 조회, `POST .../retry`로 실패분만 재처리(202/409). 업로드 응답에 잡 킥오프 정보 노출. |
| **Core Value** | 3단계 라우팅 검색(문서 요약→섹션 요약→rawchunk)의 중간층 데이터 확보 + **기존 검색 완전 격리**(Qdrant 어댑터 must_not 가드 단일 초크포인트, ES는 BM25 비대상 전용 필드, doc_browse 제외) — 회귀 0건으로 안전하게 병행 도입. `section_ref`로 rawchunk 확장 연결고리 보존. |

---

## 2. 구현 범위

### 2.1 신규 프로덕션 파일 (14개)

| 레이어 | 파일 | 역할 |
|--------|------|------|
| DB | `V043__alter_chunking_profile_add_summary_model.sql` | 프로파일 요약 모델 소프트 참조(NULL=비활성) |
| DB | `V044__create_section_summary_job.sql` | 잡 테이블(문서당 1행, UNIQUE(document_id), 실행 스냅샷) |
| domain | `section_summary/entities.py` | Job·SectionCard·Spec·Record + 결정적 `summary_id_for`(uuid5) |
| domain | `section_summary/interfaces.py` | JobStore·SectionSource·Summarizer·Writer 인터페이스 |
| domain | `section_summary/policy.py` | 상태 전이·can_retry(failed/stale)·출력 방어 절단 |
| application | `section_summary/use_case.py` | 러너 — 모델 검증→섹션 조회→기완료 스킵→Semaphore 병렬→카운트 |
| application | `section_summary/launcher.py` | 잡 INSERT + `asyncio.create_task` 킥오프(실패 시 업로드 무영향) |
| application | `section_summary/query_use_case.py` | 상태 조회/재시도(KB 권한·409 게이팅) |
| application | `section_summary/schemas.py` | LaunchInput/Info·JobStatus·RetryNotAllowedError |
| infra | `section_summary/job_repository.py` | 저층 레포 + SessionScoped 스토어(호출별 독립 짧은 세션) |
| infra | `section_summary/qdrant_section_source.py` | parent scroll 섹션 소스 + done_refs(멱등 재시도) |
| infra | `section_summary/llm_summarizer.py` | structured output → JSON 프롬프트 폴백(1회 재시도) |
| infra | `section_summary/summary_writer.py` | ES→Qdrant 순서 저장(Qdrant=완료 마커) |
| infra | `persistence/models/section_summary_job.py` | SQLAlchemy 모델 |

### 2.2 수정 파일 (additive, 15개)

- `config.py` — D17 설정 4개(동시성·입력 절단·stale 기준·섹션 상한)
- `domain/chunking/value_objects.py`, `domain/retriever/.../metadata_filter.py` — `VALID_CHUNK_TYPES` += `section_summary`
- `infrastructure/elasticsearch/es_index_mappings.py` — 요약 전용 필드 4개
- `infrastructure/vector/qdrant_vectorstore.py` — D8 must_not 격리 가드(명시 필터 시 해제)
- `application/doc_browse/get_chunks_use_case.py` — D9 열람 제외 post-filter
- 프로파일 4종(entities/model/repository/use_case) + `admin_chunking_router.py` — `summary_llm_model_id` + D16 검증
- `knowledge_base/chunking_resolver.py`(`resolve_summary_spec` additive) + `upload_use_case.py`(킥오프, 반환 3-튜플) + `knowledge_base_router.py`(상태/재시도 엔드포인트 + 응답 필드)
- `api/main.py` — `create_section_summary_components()` 싱글턴 배선 + ES additive `put_mapping`

---

## 3. 핵심 설계 결정 이행 (D1~D18: 18/18)

대표 결정의 이행 확인 (전체는 analysis 문서 §1):

- **D1 섹션 소스 추상화**: `SectionSourceInterface` + v1 `QdrantSectionSource`(parent scroll) — 사용자 요구 "장·절 등 상위 경계로 변경 용이"를 구현체 교체 지점으로 충족.
- **D5/D6 멱등성**: 결정적 uuid5 ID(Qdrant upsert/ES 덮어쓰기) + ES→Qdrant 순서(point 존재=완료 마커) + `list_done_refs` 스킵 → 재시도가 실패분만 재처리(LLM 재호출 없음, 테스트 검증).
- **D7/D8/D9 검색 격리**: Plan의 "Qdrant 자동 격리" 가정이 코드 확인에서 틀린 것으로 판명(하이브리드 벡터 측 필터 없음) → 어댑터 단일 초크포인트 must_not 가드로 설계 수정 후 구현. ES는 `content`/`morph_*` 미기재 전용 필드로 BM25 구조적 미노출. 각각 회귀 가드 테스트.
- **D11/D12 실행 모델**: `asyncio.create_task`(코드베이스 최초 도입) + JobStore가 세션을 캡슐화(호출별 독립 짧은 트랜잭션, DB-001) + Semaphore/Lock — 진행 카운트 UPDATE가 heartbeat 겸 stale 판정 근거.
- **D16 late-binding 검증**: 프로파일 저장 시 모델 존재+활성 422, 실행 시점 부재/비활성은 잡 failed로 표면화(에러 삼킴 없음).

---

## 4. Gap 처리 (Check 98% → 99%)

| # | Gap | 심각도 | 조치 |
|---|-----|:------:|------|
| G1 | Qdrant payload가 설계 §5.1의 상위집합(`content`/`collection_name`/`user_id`) — 기능 무해 | Low | 설계 문서를 실제 계약으로 갱신 → 해소 |
| G2 | 설계 §5.2/§5.3 analyzer 명칭 오기(`korean_nori` — 실존 X, 코드의 `nori_analyzer`가 정답) | Low | 설계 문서 정정 → 해소 |
| G3 | FR-11 로그에 `chunking_profile_id` 누락 | Medium | launcher/runner 로그 필드 추가 + 테스트 재통과 → 해소 |

---

## 5. 검증 결과

- **테스트**: 신규 75건 전부 통과(도메인 정책 23·러너/런처/조회 31·인프라 15·킥오프 5·라우터/기타 추가분). 관련 기존 스위트 485건 통과, 회귀 0건.
- **사전 실패 판별**: `test_es_client` 1건·`test_parent_child_retriever` 7건은 **가드 변경을 stash로 되돌려 재실행**해 동일 실패임을 검증 — 신규 회귀 아님(메모리의 기존 사전 실패군).
- **verify-architecture**: 신규 코드 위반 0건 (검출 항목은 전부 미수정 기존 파일).
- **verify-logging**: print 0건, except 내 error 3곳 모두 `exception=` 포함, 민감정보/기본 logging 사용 없음.
- **verify-tdd**: 갭 2건(query_use_case, qdrant_section_source) 발견 즉시 테스트 보강.
- **배선 검증**: `import src.api.main` 성공(DI 조립 오류 없음).

---

## 6. 후속 과제 (Plan §7 로드맵)

1. **운영 절차 (즉시)**: Flyway V043/V044 적용. ES 신규 필드는 서버 기동 시 `put_mapping` 자동 반영. vLLM 사용 시 `llm_model` 등록(provider=openai + base_url) 후 프로파일에 지정.
2. **document-summary-routing (3단계)**: 섹션 요약 전량(document_id scroll) 집계 → 문서 단위 요약 → 리트리버 1차 라우팅.
3. **summary-routed-retrieval**: 검색 경로 개편 — 섹션 요약 검색(명시 필터로 D8 가드 통과) → `section_ref`로 rawchunk 확장 + LLM 키워드 검색.
4. **section-summary-frontend**: 프로파일 요약 모델 지정 UI + 문서 목록 진행 상태 표시 (`/api-contract-sync`).
5. **section-summary-backfill**: 기존 적재 문서 일괄 요약 + cron 보정(유실 잡 자동 재처리).

---

## 7. 학습 노트

- **Plan 가정의 코드 검증이 설계를 바꿨다**: "Qdrant는 child 필터로 자동 격리" 가정이 Design 단계 코드 확인(하이브리드 벡터 측 무필터)에서 반증 → 경로별 수정 대신 어댑터 단일 초크포인트 가드로 전환. 다수 검색 경로가 있는 시스템에서 격리는 어댑터 레벨이 누락 위험이 가장 낮다.
- **결정적 ID + 저장 순서 = 멱등 재시도**: uuid5(section_ref) + "ES 먼저, Qdrant 마지막(완료 마커)" 조합으로 섹션별 상태 테이블 없이 실패분만 재처리하는 재시도를 구현 — 상태 저장 최소화 패턴.
- **세션 캡슐화 스토어 패턴**: 장수명 백그라운드 컴포넌트에는 `SessionScoped*` 어댑터(호출별 독립 짧은 세션)가 러너 코드에서 세션 관리를 완전히 제거해 테스트 가능성과 DB-001 준수를 동시에 확보 (`SessionScopedLlmModelRepository` 선례 확장).
- **반환 시그니처 변경의 최소 파급**: `execute` 2→3튜플 변경은 호출부 전수 grep으로 라우터+테스트 1곳만 영향임을 확인 후 진행 — "additive 원칙"은 동작 보존이 본질이며, 파급 범위를 실측하면 안전한 시그니처 변경도 가능.
