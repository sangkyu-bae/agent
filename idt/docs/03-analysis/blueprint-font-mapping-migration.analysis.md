# blueprint-font-mapping-migration Gap Analysis

> **Project**: idt (sangplusbot 백엔드)
> **Author**: 배상규
> **Date**: 2026-08-25
> **Phase**: Check
> **Plan**: [blueprint-font-mapping-migration.plan.md](../01-plan/features/blueprint-font-mapping-migration.plan.md)
> **Design**: [blueprint-font-mapping-migration.design.md](../02-design/features/blueprint-font-mapping-migration.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | FR-01이 저장된 블루프린트에 도달하지 못해 폰트 깨짐이 실사용에서 그대로 재현된다 |
| **WHO** | P2 — 골든 샘플을 등록해 두고 반복 사용하는 KB 운영자/에이전트 소유자 |
| **RISK** | 정규화 오탐이 저장된 모든 블루프린트로 확산 (FR-06으로 대응) |
| **SUCCESS** | 기존(미수정) 블루프린트로 생성한 PPTX의 모든 run이 유효한 패밀리명을 갖는다 |
| **SCOPE** | 읽기 경계 정규화 + 쓰기 승격 + 오탐 방지 |

---

## 0. 분석 방법 고지

**gap-detector 서브에이전트를 호출하지 않았습니다.** 이 세션은 사용자가 명시 요청하지 않은 에이전트 호출을 금지하고 있어, 아래 분석은 전부 **제가 직접 수행한 정적 검증과 실행 측정** 결과입니다. 독립적인 제3자 검증 관점은 반영되지 않았습니다.

모든 수치는 실행 명령의 출력에서 온 것이며, 추정치는 그렇다고 표기했습니다.

---

## 1. Strategic Alignment

| 질문 | 판정 | 근거 |
|------|:----:|------|
| Plan의 핵심 문제(WHY)를 해결했는가 | ✅ | 정규화 미적용 시 `{'Malgun Gothic Bold', 'Malgun Gothic Regular'}`, 적용 시 `{'Malgun Gothic'}` — 대조 실측 |
| 재추출 없이 기존 자산에 적용되는가 | ✅ | `repository._to_domain` 경유 — `test_find_by_id_normalizes_polluted_fonts` |
| 설계 결정(DR-1~8)을 따랐는가 | ✅ | 8/8 — §4 |
| 범위를 넘지 않았는가 | ✅ | 마이그레이션 스크립트 0건, `FontCatalogPort` 주입 없음, application 레이어 무변경 |

### 1.1 핵심 증거 — SC-1 대조 실측

```
정규화 미적용: {'Malgun Gothic Bold', 'Malgun Gothic Regular'}   ← PowerPoint 미해석
정규화 적용  : {'Malgun Gothic'}                                  ← latin/ea/cs 전부
```

동일 오염 블루프린트(항등 매핑)를 두 경로로 렌더해 얻은 값이다. 테스트가 헛돌지 않음을 입증한다.

---

## 2. Success Criteria 평가

| SC | 내용 | 판정 | 증거 |
|:--:|------|:----:|------|
| SC-1 | 오염 블루프린트 → 전 run이 `Malgun Gothic` | ✅ | `test_golden_sample_fidelity.py::test_sc1_polluted_blueprint_renders_valid_family_names` + §1.1 대조 |
| SC-2 | 멱등성 | ✅ | `test_already_normalized_blueprint_is_returned_unchanged`(동일 객체 `is`), `test_normalization_is_idempotent` |
| SC-3 | 키 충돌 결정론 + 테스트 고정 | ✅ | `test_mapping_conflict_picks_alphabetically_first_value` — `font_normalization.py:52` |
| SC-4 | 관리 API 응답 정규화 | ✅ | `test_payload_to_domain_normalizes_polluted_fonts` |
| SC-5 | 설계 시나리오 **전건** 자동화 | ✅ | **26/26** — §3.3 |
| SC-6 | blueprint 기존 테스트 회귀 0건 | ✅ | 264 passed / 0 failed |
| SC-7 | `Times New Roman`·`Arial Black` 보존 | ✅ | `test_normalize_protects_known_families` 8케이스 |

**Success Rate: 7/7 (100%)**

직전 사이클(pptx-font-fidelity)에서 SC-4가 17/18로 미달했던 항목을 이번엔 SC-5로 명시 고정했고, 실제로 전건 충족했다.

---

## 3. Gap Analysis

### 3.1 Structural Match — 100%

| 설계 명시 항목 | 실제 | 판정 |
|---------------|------|:----:|
| `src/domain/blueprint/font_normalization.py` | 존재 (54줄) | ✅ |
| `normalize_blueprint_fonts()` | `font_normalization.py:20` | ✅ |
| `_normalized_fonts()` | `font_normalization.py:43` | ✅ |
| `_normalized_mapping()` | `font_normalization.py:47` | ✅ |
| `_family()` | `font_normalization.py:37` | ✅ |
| `_PROTECTED_FAMILIES` | `policies.py:74` | ✅ |
| `_family_key()` | `policies.py:678` | ✅ |
| 호출 ① `repository._to_domain` | 결선됨 | ✅ |
| 호출 ② `schemas/blueprint.to_domain` | 결선됨 | ✅ |
| 테스트 파일 6개 (신규 1 / 수정 5) | 전부 존재 | ✅ |

**10/10 = 100%**

### 3.2 Functional Depth — 100%

| FR | 구현 위치 | 판정 |
|:--:|----------|:----:|
| FR-01 `style.fonts` 정규화 | `_normalized_fonts` | ✅ |
| FR-02 `font_mapping` 키·값 정규화 + 충돌 처리 | `_normalized_mapping` | ✅ |
| FR-03 쓰기 승격 | 호출 ② + `test_update_persists_normalized_fonts` | ✅ |
| FR-04 관리 API 응답 일치 | 호출 ② 경유 | ✅ |
| FR-05 멱등성 | 조기 반환(`return blueprint`) | ✅ |
| FR-06 오탐 방지 | `_strip_trailing_tokens` 루프 내 `break` | ✅ |

- **Placeholder 0건** — `TODO`/`FIXME`/`NotImplementedError`/빈 `pass` 검색 결과 없음
- **Shallow 파일 0건** — 신규 모듈 커버리지 100%

### 3.3 Test Scenario Coverage — 26/26 = 100%

| 계층 | 설계 시나리오 | 자동화 | 판정 |
|------|:------------:|:------:|:----:|
| L1 Domain Unit | 1~14 (14건) | 14 | ✅ |
| L2 Boundary Integration | 15~21 (7건) | 7 | ✅ |
| L3 Render Integration | 22~24 (3건) | 3 | ✅ |
| L4 Architecture Contract | 25~26 (2건) | 2 | ✅ |

파라미터화 전개 기준 실제 테스트 함수는 **91건**이 관련 파일에서 수집·통과했다.

### 3.4 API Contract — 100%

설계 §4가 "계약 변경 없음"으로 못박았고, 그대로 지켜졌다.

- `BlueprintPayload` / `BlueprintResponse` 필드 구조 무변경
- 응답 **값**만 정규화됨 (설계 §4.2 diff와 일치)
- `idt_front` 타입 동기화 불필요 — 루트 CLAUDE.md §4-1 요건 해당 없음

### 3.5 Runtime — 97%

```
264 passed, 1 deselected, 0 failed   (blueprint 관련 전체)
```

3점 감점 사유는 §5.1(실 DB 데이터 미검증) 하나다. 실행 실패는 0건이다.

### 3.6 Match Rate

```
Overall = Structural×0.15 + Functional×0.25 + Contract×0.25 + Runtime×0.35
        = 100×0.15 + 100×0.25 + 100×0.25 + 97×0.35
        = 15 + 25 + 25 + 33.95
        = 98.95  →  99%
```

| 축 | 점수 |
|----|:----:|
| Structural | 100% |
| Functional | 100% |
| Contract | 100% |
| Runtime | 97% |
| **Overall** | **99%** |

---

## 4. Decision Record 준수 검증

| DR | 결정 | 준수 | 검증 방법 |
|:--:|------|:----:|----------|
| DR-1 | 도메인 순수 함수 + 경계 명시 호출 | ✅ | AST 계약 테스트가 호출부 2곳(`repository.py`, `schemas/blueprint.py`) 모두 정규화 동반을 확인 |
| DR-2 | `style.fonts`·`font_mapping` 동시 정규화 | ✅ | `_normalized_fonts`+`_normalized_mapping` 동시 호출, 시나리오 23이 회귀 방어 |
| DR-3 | 보호는 데이터(`frozenset`) | ✅ | `policies.py:74` — 로직 분기 아닌 상수 |
| DR-4 | 보호 검사를 토큰 제거 루프 안에 | ✅ | `Arial Black Italic` → `Arial Black` 통과 (진입부 검사였다면 `Arial`로 붕괴) |
| DR-5 | 굵기 힌트 폐기 | ✅ | `font_normalization.py:39` `family, _ = ...` |
| DR-6 | 충돌 시 사전순 첫 번째 | ✅ | `font_normalization.py:52` `sorted(values)[0]` |
| DR-7 | DB 마이그레이션 없음 | ✅ | `db/migration/` 신규 파일 0건 (V064~V066은 타 기능) |
| DR-8 | 정규화 경로 로깅 없음 | ✅ | `font_normalization.py` 내 logger 참조 0건 |

**8/8 = 100%**

---

## 5. 발견 사항

### 5.1 ⚠️ Important — 실 DB 데이터 미검증 (미해결)

Plan §9가 "Do 착수 전 필수"로 지정한 **저장된 `font_mapping` 실물 확인이 끝내 이뤄지지 않았다.** MySQL(포트 3308)이 Plan·Design·Do·Check 전 구간에서 응답하지 않았다.

- 오염 형태는 **생성물 역산 추정**이다 (`samples/ab89d9d0....pptx`의 run 타이프페이스로부터)
- 테스트는 항등 매핑(`Bold→Bold`)과 혼합 매핑(`golden_v1.json`: `Bold→NanumGothic`) 두 형태를 덮는다
- 제3의 형태(예: 키만 정규화되고 값은 오염, 또는 빈 매핑)가 존재할 가능성은 배제하지 못했다

**영향**: SC-1의 실사용 적용성에 대한 확신도가 낮아진다. 다만 `_family()`가 임의 문자열을 받아 유효 문자열을 돌려주므로 **구조적 실패는 발생하지 않는다** — 최악의 경우 기대만큼 정리되지 않을 뿐이다.

**권장 조치**: DB 기동 후 아래 1회 실행.

```sql
SELECT id, JSON_EXTRACT(blueprint_json, '$.font_mapping'),
           JSON_EXTRACT(blueprint_json, '$.style.fonts')
FROM document_blueprint;
```

### 5.2 ℹ️ Info — coverage 모드에서만 나타나는 기존 실패 (본 변경과 무관, A/B 확인)

`pytest --cov=src.interfaces.schemas.blueprint` 로 실행하면 `test_blueprint_wiring.py::test_app_registers_blueprint_routes_and_guards_auth` 1건이 `KeyError: 'pydantic.root_model'`로 실패한다.

**A/B 대조로 본 변경과 무관함을 확인했다.**

| 조건 | 결과 |
|------|------|
| 변경 적용 + `--cov=src.interfaces.schemas.blueprint` | 1 failed |
| **변경 제거** + 동일 cov 플래그 | **1 failed** (동일) |
| 변경 적용, cov 없음 | 2 passed |
| 변경 적용 + `--cov=src.config` | 2 passed |
| 변경 적용 + `--cov=src.domain.blueprint.schemas` | 2 passed |

원인은 coverage.py가 대상 모듈을 조기 임포트할 때 pydantic 제네릭 서브모델 생성이 `sys.modules['pydantic.root_model']`을 찾지 못하는 pydantic 내부 상호작용이다. 해당 모듈에 pydantic 제네릭이 있는 경우에만 재현된다.

**조치 불필요** — 이번 사이클 산출물의 결함이 아니다. 다만 CI가 이 모듈에 coverage를 켠다면 별도 대응이 필요하므로 기록해 둔다.

### 5.3 ℹ️ Info — 보호 목록의 알려진 한계 (설계상 수용)

`Noto Sans Black` → `Noto Sans` + bold. `Black`이 정당한 굵기 표기인 경우와 패밀리명의 일부인 경우를 이름만으로는 구분할 수 없다. DR-3이 선택한 목록 방식의 대가이며, 새 충돌이 발견되면 `_PROTECTED_FAMILIES`에 추가하면 된다.

`Gill Sans MT` → `Gill Sans`도 축약되지만 `Gill Sans`가 실존 패밀리이므로 문제되지 않는다.

---

## 6. 품질 지표

### 6.1 커버리지

| 파일 | 커버리지 | 미커버 |
|------|:--------:|--------|
| `domain/blueprint/font_normalization.py` | **100%** | 0줄 |
| `infrastructure/blueprint/repository.py` | **100%** | 0줄 |
| `interfaces/schemas/blueprint.py` | **100%** | 0줄 |
| `domain/blueprint/policies.py` | 96% | 18줄 — **전부 기존 `_check_table`/`_check_chart` 분기**, 이번 변경분 아님 |

### 6.2 코딩 규칙 (`idt/CLAUDE.md`)

| 규칙 | 판정 | 확인 |
|------|:----:|------|
| 함수 40줄 이하 | ✅ | AST 검사 — 위반 0건 |
| if 중첩 2단계 이하 | ✅ | 최대 1단계 |
| `print()` 금지 | ✅ | 0건 |
| 명시적 타입 | ✅ | 전 함수 시그니처 타입 명시 |
| config 하드코딩 금지 | ✅ | 보호 목록은 모듈 상수 |
| domain → infrastructure 참조 금지 | ✅ | `test_layer_contract.py` 통과 |
| ruff lint | ✅ | 변경 11개 파일 대상 All checks passed |
| **변경 파일에만 린트 실행** | ✅ | 디렉토리 전체 `--fix` 미사용 (직전 사고 재발 방지) |

### 6.3 추적성

`# Design Ref: blueprint-font-mapping-migration DR-N` / `# Plan SC-7` 주석이 핵심 결정 지점에 삽입되어 코드→설계 역추적이 가능하다.

---

## 7. 종합

| 항목 | 결과 |
|------|:----:|
| Match Rate | **99%** (기준 90%) |
| Success Criteria | **7/7 (100%)** |
| Decision Record 준수 | **8/8 (100%)** |
| 설계 시나리오 자동화 | **26/26 (100%)** |
| 회귀 | **0건** (264 passed) |
| Critical 이슈 | **0건** |
| Important 이슈 | **1건** (§5.1 실 DB 미검증) |

**종합 점수: 97/100**

감점은 §5.1 하나다. 코드·테스트·문서 정합성 자체에는 결함이 발견되지 않았다.

---

## 8. Next Steps

**Checkpoint 5 결정 (2026-08-25): 「그대로 진행」** — Match Rate 99%가 기준(90%)을 충족하고 Critical 0건이므로 수정 없이 report 단계로 진행한다. §5.1은 코드 결함이 아닌 환경 제약이므로 백로그로 이월한다.

- [x] Checkpoint 5 — 현 상태 수용
- [ ] (백로그) DB 기동 후 §5.1 쿼리 1회 실행 — 실물 오염 형태 확인
- [ ] (백로그) §5.3 보호 패밀리 목록 보강 — 새 충돌 발견 시
- [ ] 완료 보고서 (`/pdca report blueprint-font-mapping-migration`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-25 | 최초 작성 — Match Rate 99%, SC 7/7, DR 8/8 | 배상규 |
