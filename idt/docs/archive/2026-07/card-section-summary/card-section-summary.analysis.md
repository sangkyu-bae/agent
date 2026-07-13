# card-section-summary Gap Analysis (Check)

> **Design**: `docs/02-design/features/card-section-summary.design.md` (D1~D18)
> **Plan**: `docs/01-plan/features/card-section-summary.plan.md` (FR-01~11, NFR-01~08)
> **Analyzer**: gap-detector Agent
> **Date**: 2026-07-08
> **Match Rate**: **98% → 즉시 조치 후 99%**

---

## 1. 점수 요약

| 카테고리 | 가중치 | 점수 | 상태 |
|----------|:------:|:----:|:----:|
| 설계 결정 D1~D18 | 60% | 99% (18/18 반영) | ✅ |
| API/데이터 계약 (§4/§5/§7) | 20% | 96% | ✅ |
| 테스트 계획 (§9) | 20% | 100% (9/9 + 보너스 2) | ✅ |
| **종합** | | **98%** | ✅ (≥90% — iterate 불요) |

## 2. 설계 결정 검증 (요지)

D1~D18 **전부 코드 반영 확인** (근거 파일:라인은 gap-detector 리포트 기준):

- D1 SectionSource 추상화(parent scroll + chunk_index 정렬), D5 결정적 uuid5 ID, D6 ES→Qdrant 순서 + done_refs 스킵, D7 ES 전용 필드(content/morph_* 미기재) + startup put_mapping, D8 어댑터 must_not 가드(명시 필터 시 해제), D9 doc_browse post-filter, D10 structured→JSON 폴백 + 방어 절단, D11 create_task 런처(참조 보관·실패 격리), D12 Semaphore+Lock(heartbeat 겸용), D13 임베딩 스냅샷, D14 resolve_summary_spec additive, D15 엔드포인트/응답 필드, D16 프로파일 422 검증, D17 설정 4개, D18 chunk_type 집합 2곳 확장
- §4 DB 스키마 ↔ SQLAlchemy 모델 완전 일치 (UNIQUE/인덱스/타입 포함)
- §7 API: GET 200/404/403, retry 202/409/403, 권한 검사가 잡 조회에 선행(403 > 404) — 설계대로

## 3. 발견된 Gap 및 조치

| # | Gap | 심각도 | 조치 (2026-07-08 즉시) |
|---|-----|:------:|------|
| G1 | Qdrant payload가 §5.1 계약의 상위집합(`content`/`collection_name`/`user_id` 추가) — 기능 무해(격리는 chunk_type 기준), 기존 청크 payload 관례와 정합 | Low | **설계 §5.1 문서를 실제 계약으로 갱신** (구현 유지) |
| G2 | 설계 §5.2/§5.3의 analyzer 명칭 `korean_nori`는 실존하지 않음 — 코드의 `nori_analyzer`가 정답 | Low | **설계 문서 정정** (`nori_analyzer`) |
| G3 | FR-11: 잡 로그에 `chunking_profile_id` 필드 누락 (잡 레코드에는 존재) | Medium | **코드 수정** — `launcher.py`(launched 로그)·`use_case.py`(processed 로그)에 `chunking_profile_id` 추가, 테스트 재통과 확인 |

조치 후 잔여 Gap **0건**.

## 4. Plan 요구사항 충족

- **FR-01~FR-10**: 전부 충족 (프로파일 모델 검증 422, 자동 킥오프, 1섹션 1호출, 동일 컬렉션 `section_summary` 저장, ES 키워드/요약, 상태 API, 실패분만 재시도, 검색 격리, 업로드 무영향, 기존 경로 불변)
- **FR-11**: G3 조치로 충족
- **NFR**: additive-only(기존 검색 쿼리 무수정, 가드는 동작 보존), Thin DDD(도메인 인터페이스 4종 + 인프라 구현), TDD(신규 63 + 추가 12 테스트), DB-001(JobStore 독립 짧은 세션, LLM 호출 트랜잭션 밖), LOG-001(print 0, exception= 3/3)

## 5. 특이사항 (설계 초과 구현 — 긍정)

- 보너스 테스트 2종: `test_query_use_case.py`(권한/404/재시도 게이팅), `test_qdrant_section_source.py`(복합 필터/정렬/done_refs)
- 임베딩 provider는 LaunchInput에 싣지 않고 런처가 모델 레지스트리에서 조회(동일 모델 → 차원 일치 보존, 실패 시 "openai" 폴백) — D13 의도 충족

## 6. 회귀 확인

- 신규/수정 스위트 전부 통과: section_summary 55건(조치 후 재확인), 라우터 3종 34건, 애플리케이션 121건, 인프라·도메인 330건
- 실행 중 관측된 실패는 전부 **사전 실패**로 검증: `test_es_client` 1건, `test_parent_child_retriever` 7건(가드 변경 되돌려도 동일 — stash 검증)

## 7. 결론

Match Rate 98%(조치 후 99%) ≥ 90% — **Act(iterate) 불요, Report 단계 진행 가능**.
