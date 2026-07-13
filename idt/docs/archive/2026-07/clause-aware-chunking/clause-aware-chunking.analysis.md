# clause-aware-chunking Gap Analysis

> **Design**: `docs/02-design/features/clause-aware-chunking.design.md`
> **Plan**: `docs/01-plan/features/clause-aware-chunking.plan.md`
> **Analyzer**: gap-detector (bkit)
> **Date**: 2026-07-07
> **Match Rate**: **99%** (G1/G2 반영 후, 최초 98%)

---

## 1. 종합 점수

| 항목 | 점수 | 상태 |
|------|:----:|:----:|
| Design Match | 99% | ✅ |
| Architecture Compliance (Thin DDD) | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| **Overall** | **99%** | ✅ |

---

## 2. 섹션별 Match Rate

| # | Design 섹션 | Match | 판정 |
|---|-------------|:-----:|------|
| 1 | 설계 결정 D1~D16 (§2) | 16/16 | ✅ |
| 2 | DB 스키마 §4 (V041/V042) | 100% | ✅ |
| 3 | Domain Layer §5 | 100% | ✅ |
| 4 | ClauseAwareStrategy §6 | 100% | ✅ (G1 반영) |
| 5 | Application Layer §7 | 100% | ✅ |
| 6 | API 명세 §8 | 100% | ✅ (G2 반영) |
| 7 | DI 배선 §9 | 100% | ✅ |
| 8 | 테스트 설계 §10 (9개 파일) | 100% | ✅ |
| 9 | FR-01~10 / NFR-01~07 | 27/27 | ✅ |

### D1~D16 결정 추적 (전 항목 구현 확인)
D1(JSON 컬럼) · D2(프로파일=규칙+기본값) · D3(단일 세션 default 유일성 + can_delete 422) ·
D4(V041 시드) · D5(KB additive opt-in) · D6(Query 무시+warning) · D7(overlap 지정 시 size 필수) ·
D8(페이지 결합 + 누적 offset) · D9(parent_child 계약 + Qdrant 전용 추가필드) · D10(UploadChunkingConfig) ·
D11(resolver 폴백) · D12(정책 검증) · D13(table_flattening 미적용) · D14(단일 사용자 엔드포인트) ·
D15(activity log 없음) · D16(그리디 병합).

### 요구사항 검증 (27/27 충족)
- FR-01~10: admin CRUD+403, default 1개, 사용자 목록, KB late-binding, clause_aware 적용,
  parent_child 계약, fallback, legacy 불변, 422 검증, 전략 기록(`KbUploadResponse.chunking_strategy`).
- NFR-01~07: additive 회귀 0, Thin DDD(도메인 `re`만 의존, 전략 DB 무접근), TDD 선작성,
  함수 40줄·factory 상수화, request_id 로깅, repository flush-only, 정규식 컴파일+길이/개수 상한.

---

## 3. Gap 목록

### 🔴 High / 🟡 Medium
없음.

### 🔵 Low — 처리 내역

| # | 항목 | 최초 상태 | 조치 | 결과 |
|---|------|-----------|------|------|
| G1 | 페이지 위치 계산이 `full_text.find()` 역탐색 → 동일 텍스트 조 중복 시 오탐 가능 | Design D8의 "offset 매핑" 의도와 방식 상이 | `_split_parents`가 누적 start_offset을 직접 반환하도록 리팩터 + 중복 텍스트 회귀 테스트 추가 | ✅ 해소 (`clause_aware_strategy.py:52-102`, `test_clause_aware_strategy.py::test_duplicate_clause_text_maps_correct_pages`) |
| G2 | 업로드 엔드포인트에 "clause KB면 Query 무시"(D6) OpenAPI 문서화 누락 | 기능은 use_case 로깅으로 구현됨, 문서만 부재 | `@router.post(..., description=...)` 추가 | ✅ 해소 (`knowledge_base_router.py:225`) |
| G3 | V041 시드 패턴이 전각 괄호 `（`·`제 1 조`(공백) 변형 미커버 | 설계 §4.1이 "Do 단계 실제 PDF 검증 후 미세 조정"으로 명시 이연 | 코드 무수정, Do 체크리스트 9단계로 유지(프로파일 UPDATE로 조정 가능) | ⏸ 이연 (설계 의도) |

---

## 4. 아키텍처 / 컨벤션 검증

- **Thin DDD**: domain은 표준 `re`만 의존(정책), 엔티티 순수 dataclass, 전략은 컴파일된 패턴 주입으로 DB 무접근 — 위반 없음.
- **DB 세션 규칙**: 두 repository 모두 `flush()`만 호출(commit/rollback 없음). DI factory가 동일 `Depends(get_session)`으로 kb_repo/profile_repo/resolver 조립 — UseCase 단일 세션 준수.
- **additive 회귀 가드**: `test_chunking_config.py`가 `chunking_config=None` 시 parent_child 완전 불변 검증. FK 콜레이션 규칙(V037 선례) 준수.

---

## 5. 테스트 현황

- 신규 테스트 **94건** 전부 통과 (G1 회귀 테스트 1건 추가로 93→94).
- 관련 기존 스위트 223건 통과 — 신규 회귀 0건.

---

## 6. 결론

Match Rate **99%**. High/Medium Gap 없음, Low 3건 중 2건(G1·G2) 즉시 해소, 1건(G3)은 설계가
명시 이연한 Do 체크리스트 항목. `/pdca report clause-aware-chunking`으로 완료 리포트 진행 가능.

**남은 Do 체크리스트(코드 무관)**:
1. V041/V042 마이그레이션 Flyway 적용
2. 시드 프로파일 패턴을 실제 규정 PDF 샘플로 검증 (G3 — 필요 시 프로파일 UPDATE)
