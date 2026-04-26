# Analysis: embedding-model-registry

> Feature: 임베딩 모델 레지스트리 — DB 기반 벡터 차원 관리 및 컬렉션 자동 생성
> Analyzed: 2026-04-22
> Match Rate: **96%**
> Status: PASS (>= 90%)

---

## 1. 분석 개요

Design 문서(`embedding-model-registry.design.md`)의 13개 구현 항목 + 테스트 계획 + CLAUDE.md 규칙 준수를 실제 구현 코드와 비교 분석.

---

## 2. 항목별 일치 현황

| # | 항목 | 설계 위치 | 상태 |
|---|------|-----------|------|
| 1 | Domain entity (EmbeddingModel) | §3-1 | ✅ Match |
| 2 | Repository interface | §3-2 | ✅ Match |
| 3 | ORM model (EmbeddingModelTable) | §5-1 | ✅ Match |
| 4 | Repository implementation | §5-2 | ✅ Match |
| 5 | Seed data (3 models) | §5-3 | ⚠️ Partial |
| 6 | ListEmbeddingModelsUseCase | §4-1 | ✅ Match |
| 7 | GetDimensionUseCase | §4-2 | ✅ Match |
| 8 | CollectionManagementUseCase 수정 | §4-3 | ✅ Match |
| 9 | API router + schemas | §6 | ✅ Match |
| 10 | DI wiring (main.py) | §7 | ✅ Match |
| 11 | Migration SQL | §8 | ✅ Match |
| 12 | EmbeddingFactory rename | §5-4 | ✅ Match |
| 13 | Test coverage | §11 | ⚠️ Partial |
| 14 | CLAUDE.md 규칙 준수 | §13 | ✅ Match |

---

## 3. Gap 상세

### Gap 1: Seed per-insert 로그 누락 (Low)

- **설계**: `seed_default_embedding_models`에서 모델 등록 시 per-insert `logger.info("inserted", model_name=...)` 로그 출력
- **구현**: "start" / "done" 로그만 존재, per-insert 로그 누락
- **영향**: 운영 관찰성 저하 (3건 이내이므로 실질적 영향 미미)

### Gap 2: Repository 비동기 테스트 미구현 (Medium)

- **설계**: `tests/infrastructure/embedding_model/test_repository.py`에서 async Repository CRUD 검증
- **구현**: ORM 테이블 레벨 sync 테스트만 존재 (`TestEmbeddingModelTable`)
- **영향**: `find_by_model_name`, `list_active`, `save`, `find_by_provider_and_name` 메서드의 직접 테스트 부재 (Application 레이어 mock 테스트로 간접 검증됨)

### Gap 3: 테스트 파일 ���치 차이 (Low)

- **설계**: 기존 `test_use_case.py` / `test_collection_router.py` 보강
- **구현**: 별도 파일 생성 (`test_use_case_embedding_model.py`, `test_collection_router_embedding.py`)
- **영향**: 기능적 동등, 조직적 선택

---

## 4. 점수 산출

| 카테고리 | 점수 | 비고 |
|----------|------|------|
| Design Match (항목 1-12) | 97% | seed 로그 1건 누락 |
| Test Coverage (항목 13) | 90% | async repo 테스트 미흡 |
| CLAUDE.md Compliance (항목 14) | 100% | 10개 규칙 모두 준수 |
| **Overall Match Rate** | **96%** | **PASS** |

---

## 5. 권장 조치

Match Rate >= 90% 달성으로 blocking 수정 불필요. 아래는 선택적 개선 사항:

1. **seed.py per-insert 로그 추가** (Low) — 운영 관찰성 향상
2. **async Repository 테스트 보강** (Medium) — 인프라 레이어 직접 검증

---

## 6. 결론

**96% Match Rate 달성 → Report 단계 진행 가능.**

전체 33개 테스트 통과, 기존 테스트 회귀 없음. 설계 대비 구현 완성도 높음.
