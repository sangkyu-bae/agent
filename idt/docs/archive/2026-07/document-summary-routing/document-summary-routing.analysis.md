# document-summary-routing Gap Analysis (Check)

> **Design**: `docs/02-design/features/document-summary-routing.design.md` (D1~D15)
> **Plan**: `docs/01-plan/features/document-summary-routing.plan.md` (FR-01~11, NFR-01~07)
> **Analyzer**: gap-detector Agent
> **Date**: 2026-07-09
> **Match Rate**: **98% → 즉시 조치 후 99%**

---

## 1. 점수 요약

| 카테고리 | 가중치 | 점수 | 상태 |
|----------|:------:|:----:|:----:|
| 설계 결정 D1~D15 | 60% | 99% (14 Full + D8 부분→조치 후 Full) | ✅ |
| 데이터 계약/흐름 (§4/§5) | 20% | 100% (payload/ES body/체이닝/재시도 완전 일치) | ✅ |
| 테스트 계획 (§6) | 20% | 98% (전량 존재 + 극단 케이스 1건 보강) | ✅ |
| **종합** | | **98% → 99%** | ✅ (≥90% — iterate 불요) |

## 2. 설계 결정 검증 (요지)

D1~D15 전부 반영 확인 (근거 파일:라인은 gap-detector 리포트 기준):

- **D1 체이닝**: additive 주입 + `_run_document_summary`, None이면 기존 동작 불변 — 2단계 러너 테스트 5건 무수정 통과 구조
- **D4 재시도 free win**: 별도 코드 없이 done_refs 스킵 + failed==0 재진입으로 "섹션 LLM 0회 + 문서 요약만 재생성" 성립 — 테스트로 검증
- **D8 계층 요약**: 단일/배치/최종·max_batches 명시 실패·중간 결합 절단 구현
- **D10~D11 저장 계약**: 결정적 uuid5·ES 먼저→Qdrant·**ES 신규 매핑 필드 0**(forbidden 필드 테스트) — "마이그레이션 0·신규 API 0·ES 매핑 0" 목표 코드로 확인
- **D12 가드 일반화**: `_SUMMARY_CHUNK_TYPES` frozenset + MatchAny, 양 타입 bypass 테스트
- **회귀 보존**: step=None 경로·가드 bypass 규칙·parse 승격 후 섹션 요약자 위임(동작 불변) 전부 확인

## 3. 발견된 Gap 및 조치 (전부 Low)

| # | Gap | 심각도 | 조치 (2026-07-09 즉시) |
|---|-----|:------:|------|
| G1 | FR-11 "모델" 로깅 — 성공 로그에 `llm_model_id` 미기재(설계 D15 필드셋과는 정합, Plan FR-11과 미세 불일치) | Low | 성공 로그에 `llm_model_id` 추가 → 해소 |
| G2 | D8 `INTERIM_SUMMARY_LINES` 상수 미정의(프롬프트에 "5줄" 하드코딩) | Low | `_INTERIM_SUMMARY_LINES=5` 상수화 + 최종 프롬프트도 `DOC_SUMMARY_LINES` 참조 → 해소 |
| G3 | D8 단일 블록 > cap 극단 케이스 방어 없음(배치 ≤ cap 미보장) | Low | 블록 생성 시 cap 방어 절단 + 극단 케이스 테스트 추가 → 해소 |

조치 후 잔여 Gap **0건** (테스트 47건 재통과).

## 4. Plan 요구사항 충족

- **FR-01~FR-10**: 전부 충족 (자동 체이닝, 상한 내 전량/계층 요약, 결정적 ID 멱등, 키워드 집계 LLM 0회, completed 의미 확장+error prefix, 재시도 문서 요약만, 격리, 0건 스킵, 삭제 동반)
- **FR-11**: G1 조치로 충족
- **NFR**: 회귀 0(2단계 109건 + 영향권 320건 그린), Thin DDD(step 인터페이스 domain·구현 infra), TDD 선작성, DB-001(step은 SessionScoped repo만), 방어 절단(G3 보강)

## 5. 특이사항 (설계 초과 — 긍정)

- 성공 로그에 `chunking_profile_id` 추가(2단계 FR-11 교훈 선반영)
- 회귀 관점 명시 검증: 2단계 동작 보존 4항목 전부 확인

## 6. 결론

Match Rate 98%(조치 후 99%) ≥ 90% — **Act(iterate) 불요, Report 단계 진행 가능**.
