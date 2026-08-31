# blueprint-font-mapping-migration Completion Report

> **Status**: Complete
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Completion Date**: 2026-08-25
> **PDCA Cycle**: pptx-font-fidelity 후속 (결함 A 대응)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | blueprint-font-mapping-migration |
| Start Date | 2026-08-25 |
| End Date | 2026-08-25 |
| Duration | 1일 (단일 세션) |
| Trigger | 사용자 지적 — "우리가 변경한 것에도 불구하고 폰트가 깨져 있다" |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 100%                       │
├─────────────────────────────────────────────┤
│  ✅ 완료:      FR-01 ~ FR-06  (6 / 6)        │
│  ✅ 성공기준:  SC-1 ~ SC-7    (7 / 7)        │
│  ✅ 설계결정:  DR-1 ~ DR-8    (8 / 8)        │
│  ✅ 테스트:    설계 시나리오  (26 / 26)      │
│  ❌ 취소:      0건                            │
├─────────────────────────────────────────────┤
│  Match Rate: 99%      회귀: 0건 (264 passed) │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | `font_mapping`이 추출 시점에 `blueprint_json`으로 고정 저장되어, 직전 사이클의 FR-01(폰트명 정규화)이 **기존 블루프린트에 전혀 도달하지 못했다.** `Malgun Gothic Bold`라는 존재하지 않는 타이프페이스명이 그대로 PPTX에 기록되어 뷰어가 대체 폰트로 렌더 |
| **Solution** | 도메인 순수 함수 `normalize_blueprint_fonts`를 블루프린트 **로드 경계 2곳**(DB 읽기 / API 입력)에서 명시 호출. DB 마이그레이션 없이 즉시 적용되고, 쓰기가 일어나는 블루프린트부터 데이터가 점진 정리됨 |
| **Function/UX Effect** | 재추출·재업로드 없이 기존 블루프린트의 PPT 폰트가 정상화. **실측: `{'Malgun Gothic Bold', 'Malgun Gothic Regular'}` → `{'Malgun Gothic'}`** (latin/ea/cs 전부). 관리 UI 표시값도 실제 렌더 이름과 일치 |
| **Core Value** | 직전 사이클이 **신규 추출 경로에만 닿았던 구멍**을 막아, 이미 등록된 자산에도 수정이 실효하게 만들었다. 부수적으로 `Times New Roman` → `Times New` 오탐(기존 결함)을 발견·차단 |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 오염 블루프린트 → PPTX 전 run이 `Malgun Gothic` | ✅ Met | `test_golden_sample_fidelity.py::test_sc1_polluted_blueprint_renders_valid_family_names` + 정규화 유/무 대조 실측 |
| SC-2 | 멱등성 | ✅ Met | `test_already_normalized_blueprint_is_returned_unchanged` (동일 객체 `is` 반환), `test_normalization_is_idempotent` |
| SC-3 | 키 충돌 결정론 + 테스트 고정 | ✅ Met | `font_normalization.py:52` `sorted(values)[0]` / `test_mapping_conflict_picks_alphabetically_first_value` |
| SC-4 | 관리 API 응답 정규화 | ✅ Met | `test_payload_to_domain_normalizes_polluted_fonts` |
| SC-5 | 설계 §8 시나리오 **전건** 자동화 | ✅ Met | **26 / 26** (L1 14 · L2 7 · L3 3 · L4 2) |
| SC-6 | blueprint 기존 테스트 회귀 0건 | ✅ Met | 264 passed / 0 failed |
| SC-7 | `Times New Roman`·`Arial Black` 보존 | ✅ Met | `test_normalize_protects_known_families` 8케이스 |

**Success Rate: 7 / 7 (100%)**

> 직전 사이클(pptx-font-fidelity)은 SC-4(테스트 작성)가 17/18로 부분 충족이었다. 이번엔 그 항목을 SC-5로 명시 승격해 전건 충족했다.

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 적용 지점 = **로드 경계 정규화** | ✅ | DB 무변경으로 롤백 자유. 마이그레이션 스크립트 0건 |
| [Plan] | 카탈로그 = **정규화만** | ✅ | 도메인 정책만 사용, `FontCatalogPort` 주입 없음 — 결선 확대 회피 |
| [Plan] | 쓰기 = **승격한다** | ✅ | `test_update_persists_normalized_fonts` — 읽고 저장하면 `blueprint_json` 정리됨 |
| [Design] DR-1 | 도메인 순수 함수 + 경계 명시 호출 (Option C) | ✅ | `serialization.py` "순수 변환" 계약 무손상. AST 계약 테스트가 호출부 2곳 강제 |
| [Design] DR-2 | `style.fonts`·`font_mapping` **동시** 정규화 | ✅ | 한쪽만 바꿨다면 `golden_v1` 매핑이 `NanumGothic` → `Malgun Gothic`으로 퇴화. 시나리오 23이 방어 |
| [Design] DR-3 | 보호는 **데이터**(frozenset) | ✅ | `policies.py:74` — 로직 분기 아닌 상수. 새 충돌은 목록 추가로 대응 |
| [Design] DR-4 | 보호 검사를 **토큰 제거 루프 안**에 | ✅ | `Arial Black Italic` → `Arial Black` 통과. 진입부 검사였다면 `Arial`로 붕괴 |
| [Design] DR-5 | 굵기 힌트 **폐기** | ✅ | `font_normalization.py:39` — run의 `bold` 속성과 이중 적용 방지 |
| [Design] DR-6 | 충돌 시 **사전순 첫 번째** | ✅ | Regular 판별 로직 없이 결정론 확보 |
| [Design] DR-7 | DB 마이그레이션 **없음** | ✅ | `db/migration/` 신규 파일 0건 |
| [Design] DR-8 | 정규화 경로 **로깅 없음** | ✅ | `list_all` 로그 범람 방지 — logger 참조 0건 |

**준수율: 11 / 11 (100%)**

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [blueprint-font-mapping-migration.plan.md](../01-plan/features/blueprint-font-mapping-migration.plan.md) | ✅ Finalized (v0.2 — Design 실측 반영) |
| Design | [blueprint-font-mapping-migration.design.md](../02-design/features/blueprint-font-mapping-migration.design.md) | ✅ Finalized |
| Check | [blueprint-font-mapping-migration.analysis.md](../03-analysis/blueprint-font-mapping-migration.analysis.md) | ✅ Complete (99%) |
| Act | 본 문서 | ✅ Complete |
| 선행 사이클 | [pptx-font-fidelity.analysis.md](../03-analysis/pptx-font-fidelity.analysis.md) | 참조 |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | Requirement | Status | Notes |
|----|-------------|:------:|-------|
| FR-01 | `style.fonts` 정규화 | ✅ Complete | `_normalized_fonts` |
| FR-02 | `font_mapping` 키·값 정규화 + 충돌 처리 | ✅ Complete | `_normalized_mapping` — DR-2가 핵심 |
| FR-03 | 쓰기 승격 | ✅ Complete | API 입력 경계 결선으로 자동 충족 |
| FR-04 | 관리 API 응답 일치 | ✅ Complete | 응답 스키마 무변경, 값만 정규화 |
| FR-05 | 멱등성 | ✅ Complete | 변경 없으면 동일 객체 반환 |
| FR-06 | 정규화 오탐 방지 | ✅ Complete | **Design 단계에서 신규 발견** — §6.1 참조 |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|:------:|
| 아키텍처 (domain → infra 참조 금지) | 위반 0건 | 0건 | ✅ |
| 하위호환 (v1 / v2 schema) | 양쪽 로드 성공 | 양쪽 통과 | ✅ |
| 멱등성 | `f(f(x)) == f(x)` | 통과 | ✅ |
| 회귀 | 0건 | 0건 (264 passed) | ✅ |
| 신규 코드 커버리지 | 95% | **100%** | ✅ |
| 함수 40줄 이하 | 위반 0건 | 0건 (AST 검사) | ✅ |
| ruff lint | 0건 | All checks passed | ✅ |
| API 계약 | 변경 없음 | 변경 없음 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | 규모 | Status |
|-------------|----------|:----:|:------:|
| 정규화 도메인 모듈 | `src/domain/blueprint/font_normalization.py` | 52줄 (신규) | ✅ |
| 보호 패밀리 목록 | `src/domain/blueprint/policies.py` | +12줄 | ✅ |
| 읽기 경계 결선 | `src/infrastructure/blueprint/repository.py` | +3줄 | ✅ |
| 쓰기 경계 결선 | `src/interfaces/schemas/blueprint.py` | +2줄 | ✅ |
| 도메인 테스트 | `tests/domain/blueprint/test_font_normalization.py` | 177줄 (신규) | ✅ |
| 오탐 방지 테스트 | `tests/domain/blueprint/test_font_family_policy.py` | +9케이스 | ✅ |
| 경계 테스트 | `tests/infrastructure/blueprint/test_repository.py` | +5건 | ✅ |
| 계약 테스트 | `tests/domain/blueprint/test_layer_contract.py` | +2건 | ✅ |
| 순수성 테스트 | `tests/domain/blueprint/test_serialization.py` | +1건 | ✅ |
| API 경계 테스트 | `tests/api/test_admin_blueprint_router.py` | +2건 | ✅ |
| 렌더 통합 테스트 | `tests/integration/blueprint/test_golden_sample_fidelity.py` | +3건 | ✅ |
| PDCA 문서 4종 | `docs/01-plan` ~ `docs/04-report` | — | ✅ |

**src 신규 1 / 수정 3 (~69줄), 테스트 신규 1 / 수정 5 (~230줄)**

---

## 4. Incomplete Items

### 4.1 다음 사이클 이월

| Item | Reason | Priority | 비고 |
|------|--------|:--------:|------|
| **실 DB `font_mapping` 실물 확인** | MySQL(3308)이 Plan~Check 전 구간 무응답 | Medium | Plan §9가 "Do 착수 전 필수"로 지정했으나 환경 제약으로 미이행. 코드 결함 아님 |
| 보호 패밀리 목록 보강 | 설계상 수용한 한계 | Low | `Noto Sans Black` → `Noto Sans` 등. 새 충돌 발견 시 목록 추가 |

### 4.2 이번 범위에서 명시 제외 (사용자 보고 결함 B/C/D)

첫 지적에서 확인된 4개 결함 중 **A만 이번 사이클 범위**였다. 나머지 3건은 그대로 남아 있다.

| Item | 증상 | 근본 원인 | 상태 |
|------|------|-----------|:----:|
| **B — 슬롯 좌표 정합성** | 표지 제목 위치 어긋남, 3페이지 하이라이트 박스와 글자 0.16in 겹침 | 장식은 PDF **실측**, 슬롯 좌표는 vision LLM **추정**. 둘을 한 번도 맞추지 않음 (`extraction_use_case.py:356`) | 미착수 |
| **C — 슬롯 내용 폴백 부재** | 목차 항목 0개, 마지막 카드 3개 전부 빈 상태 | 목차를 슬라이드 1장씩 독립 호출로 작성(다른 슬라이드 제목을 모름) + `_check_bullets`가 길이 초과 시 슬롯 **전체 폐기** | 미착수 |
| **D — 차트/표/문단 스타일** | 막대 위 값 없음, 축에 % 없음, 설명 문단 여백 없음, 표 테두리 없음 | `chart_builder`에 데이터 레이블 코드 없음 · `ChartSpec.unit`이 **죽은 필드** · `_bullets`가 `spacing=1.0`이라 줄간격 미설정 · `TableStyle.border` 미사용 | 미착수 |

> **B가 파급이 가장 크고(전 슬라이드 정렬) 난이도도 가장 높다.** 실측 span bbox로 슬롯을 스냅하는 로직이 필요하다.

### 4.3 취소/보류

없음.

---

## 5. Quality Metrics

### 5.1 최종 분석 결과

| Metric | Target | Final | 판정 |
|--------|:------:|:-----:|:----:|
| Design Match Rate | 90% | **99%** | ✅ |
| — Structural | — | 100% | ✅ |
| — Functional | — | 100% | ✅ |
| — Contract | — | 100% | ✅ |
| — Runtime | — | 97% | ✅ |
| Success Criteria | — | 7/7 (100%) | ✅ |
| Decision Record 준수 | — | 11/11 (100%) | ✅ |
| 설계 시나리오 자동화 | 100% | 26/26 (100%) | ✅ |
| 신규 코드 커버리지 | 95% | 100% | ✅ |
| 회귀 | 0건 | 0건 | ✅ |
| Critical 이슈 | 0건 | 0건 | ✅ |
| **종합 점수** | — | **97 / 100** | ✅ |

Runtime 3점 감점은 §4.1 실 DB 미검증 1건이 유일하다. 실행 실패는 0건이다.

### 5.2 해결한 이슈

| Issue | Resolution | Result |
|-------|------------|:------:|
| FR-01이 기존 블루프린트에 미적용 (결함 A) | 로드 경계 정규화 | ✅ 해결 — 대조 실측 확인 |
| `Times New Roman` → `Times New` 오탐 | 보호 패밀리 목록 + 루프 내 검사 | ✅ 해결 |
| `Arial Black` → `Arial`+bold 오탐 | 동상 | ✅ 해결 |
| `golden_v1` 매핑 퇴화 위험 | 키·값 동시 정규화 (DR-2) | ✅ 예방 — 시나리오 23이 고정 |
| Option C의 호출부 누락 위험 | AST 계약 테스트 | ✅ 예방 |

### 5.3 조사했으나 조치 불필요로 판정한 건

| 현상 | 조사 | 결론 |
|------|------|------|
| `--cov=src.interfaces.schemas.blueprint` 시 `test_blueprint_wiring` 1건 실패 (`KeyError: 'pydantic.root_model'`) | 변경 적용/제거 A/B 대조 + 타 모듈 cov 대조 | **본 변경과 무관한 기존 pydantic↔coverage.py 상호작용.** 변경을 제거해도 동일 실패. cov 없이는 통과. CI가 이 모듈에 coverage를 켤 경우를 대비해 분석 §5.2에 기록 |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **대조 실측으로 테스트의 비공허성을 입증했다.** 정규화를 뺀 상태로 같은 블루프린트를 렌더해 `Malgun Gothic Bold`가 나오는 것을 확인한 뒤 통과 테스트를 인정했다. "테스트가 통과했다"와 "테스트가 무언가를 지킨다"는 다르다.
- **Design 단계의 실측이 Plan의 오판 2건을 뒤집었다.** 왕복 등가성 리스크는 High→Low로, 정규화 오탐은 Low→High로 재평가되어 FR-06이 신설됐다. 문서를 쓰기 전에 코드를 돌려본 것이 주효했다.
- **기존 픽스처가 함정을 잡아 줬다.** `golden_v1.json`이 `fonts`만 오염되고 `font_mapping` 값은 정규화된 혼합 상태라, `fonts`만 고쳤다면 오히려 퇴화했을 것이다. DR-2는 이 픽스처를 읽었기에 나온 결정이다.
- **직전 사이클의 미달 항목을 이번 성공 기준으로 승격했다.** SC-4(17/18) → SC-5(26/26).
- **직전 사이클의 사고(tests/ 전체 ruff --fix로 647개 파일 오염)를 Plan §8.2 규칙으로 명문화하고 준수했다.**

### 6.2 What Needs Improvement (Problem)

- **Plan의 리스크 평가가 근거 없이 작성됐다.** "이름 전체가 토큰이면 원본 유지 방어가 있으니 가능성 낮음"이라고 썼는데, 그 방어는 마지막 토큰만 토큰인 경우 작동하지 않는다. `normalize("Times New Roman")`을 한 번만 실행했으면 Plan 단계에서 알았을 일이다.
- **Plan §9가 "Do 착수 전 필수"로 지정한 항목을 미이행한 채 Do를 진행했다.** 환경 제약이 이유였고 사용자 승인도 받았지만, 필수 항목을 스스로 무력화한 절차상 결함이다.
- **직전 사이클의 검증 범위가 좁았다.** "골든 샘플 재생성으로 검증 완료"라고 보고했으나 그 경로는 재추출을 포함했고, 기존 블루프린트 경로는 검증하지 않았다. 이번 결함 A는 그 구멍에서 나왔다.
- **결함 A~D 중 A만 처리해 사용자가 처음 지적한 증상 대부분은 여전히 남아 있다.** 범위 결정은 사용자 몫이었으나, 진척 체감과 실제 해결 사이의 간극은 인지해야 한다.

### 6.3 What to Try Next (Try)

- **Plan 리스크 표에 "실측 여부" 열 추가.** 근거가 추정인지 실행 결과인지 구분해 표기하면 §6.2의 첫 문제를 구조적으로 막는다.
- **"수정이 기존 저장 데이터에 닿는가"를 체크리스트 항목으로.** 이번 결함 A의 본질은 신규 경로만 고치고 기존 데이터 경로를 잊은 것이다. 데이터를 영속화하는 기능에는 항상 물어야 할 질문이다.
- **AST 계약 테스트를 다른 "여러 호출부를 강제하는" 결정에도 적용.** Option C처럼 병목이 아닌 설계를 택할 때 누락을 막는 저비용 장치로 효과가 확인됐다.
- **결함 B 착수 전 좌표 정합 방식을 프로토타입으로 먼저 검증.** vision 추정과 실측 스냅의 매칭 규칙은 문서로 결정하기 어렵다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA 프로세스

| Phase | Current | Improvement Suggestion |
|-------|---------|------------------------|
| Plan | 리스크 가능성을 추정으로 기재 | **위험 판단 전 관련 함수 1회 실행** — 이번에 Design까지 밀린 오탐 발견을 Plan으로 앞당김 |
| Design | (양호) 3안 비교 + 실측 검증 절이 유효했음 | 유지 |
| Do | (양호) TDD Red→Green 8단계 | 유지 |
| Check | gap-detector 미사용 (세션 규칙) | 독립 검증 관점 부재를 문서에 고지하는 관행 유지 |
| 전반 | "Do 착수 전 필수" 항목의 미이행 처리 절차 없음 | **미이행 시 Plan을 갱신하고 사유를 남기는 규칙** 명문화 |

### 7.2 도구/환경

| Area | Improvement Suggestion | Expected Benefit |
|------|------------------------|------------------|
| 로컬 DB | MySQL(3308) 기동 상태를 개발 전제 조건으로 문서화 | 이번처럼 필수 검증이 통째로 누락되는 상황 방지 |
| CI 커버리지 | `src/interfaces/schemas/*` 모듈에 coverage 적용 시 §5.3 이슈 확인 | 원인 불명 CI 실패 예방 |

---

## 8. Next Steps

### 8.1 즉시

- [ ] 서버 재기동 후 기존 블루프린트로 PPT 재생성 — 결함 A 해소 육안 확인
- [ ] MySQL 기동 후 §4.1 쿼리 1회 실행 (백로그)

```sql
SELECT id, JSON_EXTRACT(blueprint_json, '$.font_mapping'),
           JSON_EXTRACT(blueprint_json, '$.style.fonts')
FROM document_blueprint;
```

### 8.2 다음 PDCA 사이클

| Item | Priority | 근거 |
|------|:--------:|------|
| **결함 B — 슬롯 좌표 정합성** | High | 전 슬라이드 정렬에 영향. 표지·본문 모두 어긋남 |
| **결함 C — 목차·카드 내용 폴백** | High | 목차가 통째로 비는 것은 산출물 완성도에 치명적 |
| **결함 D — 차트 레이블·단위·문단 여백** | Medium | 개별 영향은 작으나 건수가 많음 |

---

## 9. Changelog

### 2026-08-25

**Added:**
- `src/domain/blueprint/font_normalization.py` — `normalize_blueprint_fonts()` 도메인 순수 함수
- `_PROTECTED_FAMILIES` 보호 패밀리 목록 (`Times New Roman`, `Arial Black`)
- 블루프린트 로드 경계 누락 방지 AST 계약 테스트

**Changed:**
- `BlueprintRepository._to_domain` — 로드 시 폰트명 정규화
- `BlueprintPayload.to_domain` — API 입력 시 폰트명 정규화 (쓰기 승격)
- `FontFamilyPolicy._strip_trailing_tokens` — 보호 패밀리에서 토큰 제거 중단

**Fixed:**
- 기존 블루프린트에 폰트명 정규화가 적용되지 않아 PPTX에 무효 타이프페이스명이 기록되던 문제
- `Times New Roman` → `Times New`, `Arial Black` → `Arial` 정규화 오탐

**Unchanged (의도적):**
- DB 스키마 / 마이그레이션 — 추가 없음
- API 응답 스키마 — 필드 구조 무변경 (값만 정규화)
- `blueprint_from_dict` — 순수 변환 계약 유지

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-25 | 완료 보고서 작성 — Match Rate 99%, SC 7/7, DR 11/11 | 배상규 |
