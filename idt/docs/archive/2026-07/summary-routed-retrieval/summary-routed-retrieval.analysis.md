# summary-routed-retrieval Gap Analysis (Check)

> **Design**: `docs/02-design/features/summary-routed-retrieval.design.md` (D1~D13)
> **Plan**: `docs/01-plan/features/summary-routed-retrieval.plan.md` (FR-01~11, NFR-01~07)
> **Analyzer**: gap-detector Agent
> **Date**: 2026-07-09
> **Match Rate**: **95% → 즉시 조치 후 99%**

---

## 1. 점수 요약

| 카테고리 | 가중치 | 점수 | 상태 |
|----------|:------:|:----:|:----:|
| 설계 결정 D1~D13 | 60% | 96% (13/13 반영, 시그니처 미세 편차) | ✅ |
| §4 흐름 / D7 API 계약 | 20% | 90% (흐름 완전 일치, 응답 구조 편차 1건) | ✅ |
| 테스트 계획 (§5) | 20% | 100% (8개 파일·계획 케이스 완전 커버) | ✅ |
| **종합** | | **95% → 99%** | ✅ (≥90% — iterate 불요) |

## 2. 설계 결정 검증 (요지)

D1~D13 전부 반영 (근거 파일:라인은 gap-detector 리포트 기준):

- **§4 흐름 완전 일치**: 임베딩 1회 → 문서 0건 시 전량 폴백 → 섹션(벡터 MatchAny + ES BM25 `summary_text^1.5` → RRF) → ES ids query 확장 → dedup 보충. 외부 IO 상한(NFR-04) 준수, **FR-07 LLM 0회** 확인
- **D6 additive 검증**: `metadata_any` default 필드로 기존 생성자 전부 호환, equality·요약 가드 bypass 무변경 — 회귀 테스트 2종 존재, **FR-09 충족**
- **FR-08 단계 교체**: 포트 3종 뒤 구현 격리, fake 3포트 오케스트레이션 테스트로 계약 검증
- **D8 폴백**: chunk_id/parent_id 조 단위 dedup + top_k 절단 + 폴백 실패 시 라우팅 결과 보존

## 3. 발견된 Gap 및 조치

| # | Gap | 심각도 | 조치 (2026-07-09 즉시) |
|---|-----|:------:|------|
| G1 | D7 응답 구조 편차 — 설계 `routing{document,section}` 래퍼 vs 구현 평탄 형제 필드 `document`/`section` | **Medium** | 신규 API로 소비자 부재 → **코드=진실 원칙으로 설계 D7 갱신**(평탄 구조가 pydantic 명세도 단순). `total_found`·document `keywords` 추가분도 문서 반영 |
| G2 | D1 포트 시그니처 편차 — `top_n`→`scope,params`, expand에 `documents_by_id` 추가(D5 근거 동봉 필요분) | Low | 설계 D1을 실제 시그니처로 갱신 |
| G3 | D12 로그에 `fallback_used` boolean 생략 | Low | 로그 필드 추가 + 설계 D12를 실제 필드명으로 정합 |
| G4 | (참고) `execute` 함수 40줄 초과 소지 (NFR-05) | Low | `_descend` 헬퍼 분리 리팩터 — 테스트 74건 재통과 |

조치 후 잔여 Gap **0건**.

## 4. Plan 요구사항 충족

- **FR-01~FR-11 전부 충족**: 3계층 하강 API(FR-01~04), 폴백+`fallback_used`(FR-05), 근거 동봉(FR-06 — 평탄 구조로 충족), LLM 0회(FR-07), 단계 교체(FR-08), 기존 경로 무영향(FR-09 — 회귀 237+74건), 422(FR-10), 관측 로그(FR-11 — G3 보정)
- **NFR**: additive-only(수정 3파일 전부 동작 보존), Thin DDD, TDD(테스트 43건 선작성), IO 상한, 40줄(G4 보정), LOG-001

## 5. 특이사항 (설계 초과 — 긍정)

- 섹션 라우터의 소스별 graceful 강등(벡터/BM25 한쪽 실패 시 다른 쪽 유지) — 설계 §1 의도 부합 견고성 보강
- `total_found` 응답 필드, document 근거 `keywords` — 무해한 관측 상향

## 6. 결론

Match Rate 95%(조치 후 99%) ≥ 90% — **Act(iterate) 불요, Report 단계 진행 가능**.
문서 등록 3부작 + 라우팅 검색으로 **원 목표(문서→섹션→rawchunk 라우팅 리트리버) 전 구간 완성**.
