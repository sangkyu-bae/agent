# blueprint-font-mapping-migration Design Document

> **Summary**: 도메인 순수 함수 `normalize_blueprint_fonts`를 블루프린트 로드 경계 2곳에서 호출해, 저장된 오염 폰트명을 재추출 없이 바로잡는다.
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-25
> **Status**: Draft
> **Planning Doc**: [blueprint-font-mapping-migration.plan.md](../../01-plan/features/blueprint-font-mapping-migration.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | FR-01이 저장된 블루프린트에 도달하지 못해 폰트 깨짐이 실사용에서 그대로 재현된다 |
| **WHO** | P2 — 골든 샘플을 등록해 두고 반복 사용하는 KB 운영자/에이전트 소유자 |
| **RISK** | 읽기 경계 변경이 직렬화 왕복 등가성 계약을 깬다 — **실측 결과 현 픽스처는 전부 정규화 불변점이라 실질 위험은 낮음** (§5.1) |
| **SUCCESS** | 기존(미수정) 블루프린트로 생성한 PPTX의 모든 run이 유효한 패밀리명을 갖는다 |
| **SCOPE** | 읽기 경계 정규화 + 쓰기 승격 + 정규화 오탐 방지. 데이터 마이그레이션·카탈로그 재매핑은 제외 |

---

## 1. Overview

### 1.1 Design Goals

1. **저장된 블루프린트를 읽는 모든 경로**가 유효한 폰트 패밀리명을 반환한다 — DB 읽기와 관리 API 입력 양쪽.
2. 정규화 로직은 **도메인 순수 함수** 하나로 모으고, 인프라·인터페이스는 호출만 한다.
3. `serialization.py`가 선언한 **"순수 변환"** 계약을 훼손하지 않는다.
4. 정규화가 **정상 폰트명을 훼손하지 않는다** — `Times New Roman`, `Arial Black` 같은 실존 패밀리 보호.
5. DB 스키마·마이그레이션 **없음**. 쓰기가 일어나는 블루프린트부터 점진적으로 데이터가 정리된다.

### 1.2 Design Principles

- **단일 정책, 다중 호출**: 정책은 도메인 1곳, 호출은 경계마다 명시적으로. 암묵적 부수효과를 만들지 않는다.
- **키·값 동시 정규화**: `style.fonts`(조회 키)와 `font_mapping`(조회 표)은 **함께** 정규화해야 조회가 성립한다. 한쪽만 바꾸면 조회가 깨진다.
- **멱등**: 이미 정규화된 블루프린트는 몇 번을 통과해도 동일하다.
- **안전한 열화**: 매핑 조회가 실패해도 폴백 값이 이미 정규화된 유효 이름이다.
- **보호는 데이터로**: 오탐 방지는 코어 로직 분기가 아니라 **보호 패밀리 목록**(데이터)으로 처리한다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

세 안 모두 **로드 경계 정규화**(Plan Checkpoint 2 결정)이며, 정규화 로직의 배치 레이어만 다르다.

| Criteria | A: Minimal | B: Clean | C: Pragmatic |
|----------|:-:|:-:|:-:|
| **적용 지점** | `repository._to_domain` | `blueprint_from_dict` 내부 | 도메인 함수 + 호출부 2곳 |
| **New Files** | 0 | 0 | 1 |
| **Modified Files** | 3 | 2 | 3 |
| **DB 읽기 커버** | ✅ | ✅ | ✅ |
| **API 입력(PUT) 커버** | ❌ (별도 추가 필요) | ✅ 자동 | ✅ |
| **왕복 순수성 계약** | ✅ 무손상 | ⚠️ 계약 변경 | ✅ 무손상 |
| **정책 레이어** | 인프라에 분산 | 도메인 | 도메인 |
| **누락 위험** | 높음 | 없음 | 중간 (AST 테스트로 완화) |
| **Complexity** | Low | Low | Medium |
| **Maintainability** | Medium | High | High |
| **Recommendation** | — | 단일 병목 중시 | **기본 권장** |

**Selected**: **Option C — Pragmatic** (Checkpoint 3)

**Rationale**: `serialization.py` docstring이 명시한 "순수 변환(표준 라이브러리만)" 계약을 지키면서, DB 읽기와 API 입력 두 경로를 모두 덮는다. 호출이 코드에 드러나 추적이 쉽고, 유일한 약점인 "새 로드 경로 누락"은 기존 `test_layer_contract.py`와 같은 AST 계약 테스트로 막는다.

### 2.1 Component Diagram

```
                    ┌──────────────────────────────────────┐
                    │ domain/blueprint                     │
                    │                                      │
  ┌─────────────┐   │  policies.py                         │
  │ MySQL       │   │    FontFamilyPolicy.normalize()      │
  │ blueprint_  │   │    + _PROTECTED_FAMILIES  (FR-06)    │
  │ json        │   │              ▲                       │
  └──────┬──────┘   │              │ 재사용                 │
         │          │  font_normalization.py       [NEW]   │
         │ read     │    normalize_blueprint_fonts(bp)     │
         ▼          │      ├─ _normalized_fonts()          │
  ┌─────────────┐   │      └─ _normalized_mapping()        │
  │ repository  │──▶│              ▲          ▲            │
  │ ._to_domain │   └──────────────┼──────────┼────────────┘
  └──────┬──────┘                  │          │
         │                    호출 ①      호출 ②
         │                                     │
         │                          ┌──────────┴──────────┐
         │                          │ interfaces/schemas  │
         │                          │ BlueprintUpsert     │
         │                          │   .to_domain()      │
         │                          └──────────▲──────────┘
         ▼                                     │ PUT
  ┌──────────────────────┐              ┌──────┴──────┐
  │ generation_use_case  │              │ 관리 UI      │
  │  → PptxSlideRenderer │              └─────────────┘
  └──────────────────────┘
```

### 2.2 Data Flow

**읽기 경로 (주 수혜자)**

```
blueprint_json (오염)
  → blueprint_from_dict()          ← 순수 변환, 무변경
  → normalize_blueprint_fonts()    ← 신규 ①
  → DocumentBlueprint (정규화됨)
  → generation_use_case.generate(blueprint, ...)
  → PptxSlideRenderer.render(bp, slides, assets, bp.font_mapping)
  → _Ctx.font(role) = font_mapping[style.fonts[role]]   ← 양쪽 다 정규화되어 조회 성립
  → set_run_font(run, "Malgun Gothic")                  ← 유효한 패밀리명
```

**쓰기 승격 경로 (FR-03)**

```
관리 UI PUT
  → BlueprintUpsert.to_domain()
      → blueprint_from_dict() → normalize_blueprint_fonts()   ← 신규 ②
  → admin_use_case.update(edited)   ← 이미 정규화된 객체
  → repository.update() → blueprint_to_dict() → blueprint_json (정규화 저장)
```

읽기에서 정규화된 객체가 `admin_use_case.update`의 `current`로도 쓰이므로, **관리 UI에서 저장을 한 번 거친 블루프린트는 DB 값 자체가 정리된다.**

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `font_normalization.py` | `policies.FontFamilyPolicy`, `value_objects.DocumentBlueprint/StyleTokens` | 정규화 재사용 + 객체 재구성 |
| `repository._to_domain` | `font_normalization` | 호출 ① |
| `schemas/blueprint.BlueprintUpsert.to_domain` | `font_normalization` | 호출 ② |
| `pptx_renderer._Ctx.font` | (변경 없음) | 정규화된 값을 그대로 수신 |

`font_normalization.py`는 도메인 내부만 참조한다 — `test_layer_contract.py`의 금지 임포트 검사를 그대로 통과한다.

---

## 3. Data Model

### 3.1 Entity Definition

**신규 엔티티 없음.** 기존 `DocumentBlueprint`의 두 필드만 값이 바뀐다.

```python
@dataclass(frozen=True)
class StyleTokens:
    fonts: dict[str, str]        # role → 폰트명 : 값이 정규화 대상 (FR-01)
    ...

@dataclass(frozen=True)
class DocumentBlueprint:
    font_mapping: dict[str, str] # 원본명 → 대상명 : 키·값 모두 정규화 대상 (FR-02)
    ...
```

두 필드는 렌더러에서 **한 쌍으로 소비**된다.

```python
# pptx_renderer.py:117-118 (변경 없음)
original = self.style.fonts.get(role, "")      # ← 조회 키
return self.font_mapping.get(original, original) or original
```

### 3.2 변환 규칙

| 대상 | 규칙 | 예시 |
|------|------|------|
| `style.fonts[role]` | `normalize(v)[0]`, 빈 문자열이면 원본 유지 | `Malgun Gothic Bold` → `Malgun Gothic` |
| `font_mapping` 키 | `normalize(k)[0]` | `Malgun Gothic Regular` → `Malgun Gothic` |
| `font_mapping` 값 | `normalize(v)[0]` | `NanumGothic` → `NanumGothic` (불변) |
| 키 충돌 | 정규화된 후보 집합에서 **사전순 첫 번째** (Checkpoint 3) | `{Bold→A, Regular→A}` → `{Malgun Gothic: A}` |

굵기 힌트(`normalize`의 두 번째 반환값)는 **버린다**. 굵기는 run의 `bold` 속성으로 이미 표현되며, 패밀리명에 되돌리면 이중 적용이 된다.

### 3.3 Database Schema

**변경 없음.** DDL·마이그레이션 파일 추가 없음. `blueprint_json` 컬럼의 값만 쓰기 시점에 자연히 갱신된다.

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | 계약 변경 |
|--------|------|-------------|:--------:|
| GET | `/admin/blueprints/{id}` | 상세 조회 | **없음** (필드 구조 동일, 값만 정규화) |
| GET | `/admin/blueprints` | 목록 | **없음** |
| PUT | `/admin/blueprints/{id}` | 수정 | **없음** (입력은 그대로 수용, 저장 시 정규화) |

**응답 스키마 무변경 → 프론트엔드 타입 동기화 불필요** (루트 CLAUDE.md §4-1 확인 완료).

### 4.2 관찰 가능한 동작 변화

`GET /admin/blueprints/{id}` 응답에서 값만 바뀐다.

```diff
  "style": {
    "fonts": {
-     "heading": "Malgun Gothic Bold",
-     "body": "Malgun Gothic Regular"
+     "heading": "Malgun Gothic",
+     "body": "Malgun Gothic"
    }
  },
  "font_mapping": {
-   "Malgun Gothic Bold": "Malgun Gothic Bold",
-   "Malgun Gothic Regular": "Malgun Gothic Regular"
+   "Malgun Gothic": "Malgun Gothic"
  }
```

`font_mapping` 항목 수가 줄 수 있다(키 접힘). 이는 **의도된 동작**이며 클라이언트는 이 맵을 표시 용도로만 사용한다.

---

## 5. UI/UX Design

해당 없음 — 백엔드 전용. 관리 UI의 폰트 표시값이 정확해지는 부수 효과만 있다 (§4.2).

---

## 6. Error Handling

### 6.1 오류 정책

정규화는 **예외를 던지지 않는다.** 도메인 순수 함수이며 입력이 어떤 문자열이든 문자열을 반환한다.

| 상황 | 처리 | 근거 |
|------|------|------|
| 빈 폰트명 (`""`) | 원본(`""`) 유지 | `StyleTokens.__post_init__`은 키 존재만 검사하므로 안전 |
| 이름 전체가 서브패밀리 토큰 (`"Bold"`) | 원본 유지 | `FontFamilyPolicy.normalize` 기존 방어 |
| 보호 패밀리 (`"Times New Roman"`) | 원본 유지 | FR-06 |
| 매핑 조회 실패 | `_Ctx.font`가 `original`(정규화됨) 폴백 | 기존 렌더러 동작, 값이 이미 유효 |
| `font_mapping`이 비어 있음 | `style.fonts` 정규화만 적용 | 조회 실패 폴백과 동일 경로 |

### 6.2 로깅

정규화는 **로그를 남기지 않는다.** 블루프린트 목록 조회(`list_all`)에서 건마다 발생해 로그가 범람한다. 값 변화 추적이 필요하면 관리 API 응답(§4.2)으로 확인한다.

---

## 7. Security Considerations

- [x] 입력 검증 — 정규화는 문자열 → 문자열 순수 변환. 주입 표면 없음
- [x] 정규식 ReDoS — 기존 `_FONT_TOKEN_SPLIT` / `_SUBSET_PREFIX` 재사용, 백트래킹 없는 단순 패턴. 신규 정규식 추가 없음
- [x] 인증/인가 — 변경 없음 (관리 라우터의 기존 가드 유지)
- [x] 민감정보 — 폰트명은 비민감

---

## 8. Test Plan

### 8.1 Test Scope

이 프로젝트는 백엔드 전용이므로 템플릿의 L1/L2/L3(웹 UI)를 pytest 계층으로 치환한다.

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| **L1: Domain Unit** | `FontFamilyPolicy` 오탐 방지, `normalize_blueprint_fonts` | pytest | Do |
| **L2: Boundary Integration** | `repository._to_domain`, `BlueprintUpsert.to_domain` | pytest | Do |
| **L3: Render Integration** | 오염 블루프린트 → PPTX 산출물 검증 | pytest + python-pptx | Do |
| **L4: Architecture Contract** | 모든 `blueprint_from_dict` 호출부가 정규화를 거치는지 | pytest + AST | Do |

### 8.2 L1: Domain Unit 시나리오

| # | 대상 | 입력 | 기대 |
|---|------|------|------|
| 1 | `normalize` | `"Times New Roman"` | `("Times New Roman", False)` — 보호 (FR-06) |
| 2 | `normalize` | `"Arial Black"` | `("Arial Black", False)` — 보호 (FR-06) |
| 3 | `normalize` | `"Arial Black Italic"` | `("Arial Black", False)` — Italic만 탈락, 보호는 유지 |
| 4 | `normalize` | `"Malgun Gothic Bold"` | `("Malgun Gothic", True)` — 기존 동작 회귀 없음 |
| 5 | `normalize` | `"Franklin Gothic Book"` | `("Franklin Gothic", False)` — 정상 축약 유지 |
| 6 | `normalize` | `"ABCDEF+Times New Roman"` | `("Times New Roman", False)` — 서브셋 프리픽스 제거 후 보호 |
| 7 | `normalize_blueprint_fonts` | `fonts={"heading":"Malgun Gothic Bold"}` | `"Malgun Gothic"` (FR-01) |
| 8 | `normalize_blueprint_fonts` | `mapping={"Malgun Gothic Bold":"X","Malgun Gothic Regular":"X"}` | `{"Malgun Gothic":"X"}` — 키 접힘 (FR-02) |
| 9 | `normalize_blueprint_fonts` | 충돌 값이 다름 `{Bold:"B", Regular:"A"}` | `{"Malgun Gothic":"A"}` — 사전순 첫 번째 |
| 10 | `normalize_blueprint_fonts` | 이미 정규화된 블루프린트 | 입력과 동일 객체값 (FR-05 멱등) |
| 11 | `normalize_blueprint_fonts` | 두 번 연속 적용 | 1회 적용과 동일 (FR-05 멱등) |
| 12 | `normalize_blueprint_fonts` | `fonts={"heading":""}` | `""` 유지, 예외 없음 |
| 13 | `normalize_blueprint_fonts` | `font_mapping={}` | 빈 맵 유지, `fonts`만 정규화 |
| 14 | `normalize_blueprint_fonts` | 다른 필드(patterns/narrative/assets) | **불변** — 폰트 외 필드 무손상 |

### 8.3 L2: Boundary Integration 시나리오

| # | 경계 | 시나리오 | 기대 |
|---|------|----------|------|
| 15 | `repository.find_by_id` | 오염 `blueprint_json` 행 로드 | 반환 객체의 `style.fonts`·`font_mapping` 정규화됨 |
| 16 | `repository.list_all` | 오염 행 2건 로드 | 모든 항목 정규화됨 |
| 17 | `BlueprintUpsert.to_domain` | 오염 폰트명이 담긴 PUT 페이로드 | 정규화된 도메인 객체 반환 (FR-03) |
| 18 | `repository.update` | 정규화된 객체 저장 | `blueprint_json`에 정규화된 값 기록 (FR-03) |
| 19 | `blueprint_from_dict` 단독 | 오염 dict | **정규화되지 않음** — 순수성 계약 유지 확인 |
| 20 | `test_roundtrip_is_lossless` | 기존 테스트 | **무수정 통과** (§5.1 실측 근거) |
| 21 | v1 스냅샷 (`golden_v1.json`) | `schema_version=1` 로드 | 로드 성공 + 정규화 적용, 버전은 1 보존 |

### 8.4 L3: Render Integration 시나리오

| # | 시나리오 | 성공 기준 |
|---|----------|-----------|
| 22 | **SC-1 핵심** — 항등 매핑을 가진 오염 블루프린트(`{"Malgun Gothic Bold":"Malgun Gothic Bold"}`)로 렌더 | PPTX 전 run의 `latin`/`ea`/`cs`가 `"Malgun Gothic"`, 서브패밀리 접미사 0건 |
| 23 | `golden_v1.json` 렌더 (`test_sc8_v1_snapshot`) | 기존 단언 유지 — 매핑 값 `NanumGothic`이 접힘 후에도 조회에 성공 |
| 24 | 정규화 전후 슬라이드 수·도형 수 | 동일 (폰트 외 렌더 결과 불변) |

> 시나리오 23이 이번 설계의 **가장 날카로운 회귀 검사**다. `style.fonts`만 정규화하고 `font_mapping` 키를 그대로 두면 조회가 빗나가 `NanumGothic` → `Malgun Gothic`으로 퇴화하는데, 이 테스트가 즉시 잡는다.

### 8.5 L4: Architecture Contract 시나리오

| # | 검사 | 기대 |
|---|------|------|
| 25 | `src/` 내 `blueprint_from_dict` 호출 모듈 열거 (AST) | 각 모듈이 `normalize_blueprint_fonts`도 참조 — 미참조 시 실패 |
| 26 | `font_normalization.py` 임포트 검사 | `test_layer_contract.py`의 금지 루트/프리픽스 위반 0건 |

### 8.6 Seed Data Requirements

| 픽스처 | 최소 건수 | 필수 값 |
|--------|:--------:|---------|
| 오염 블루프린트 (항등 매핑) | 1 | `fonts={heading:"Malgun Gothic Bold", body:"Malgun Gothic Regular"}`, `font_mapping` 항등 |
| `golden_v1.json` | 기존 재사용 | 수정 금지 — 회귀 기준선 |

신규 픽스처는 `tests/fixtures/blueprint/`에 두지 않고 **테스트 내 팩토리 함수**로 만든다. 기존 `_bp()` 패턴을 따른다.

---

## 9. Clean Architecture

### 9.1 Layer Structure

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **Domain** | 폰트 정규화 정책·순수 변환 | `src/domain/blueprint/` |
| **Application** | (변경 없음) | `src/application/blueprint/` |
| **Infrastructure** | DB 행 → 도메인 객체 복원 시 정규화 호출 | `src/infrastructure/blueprint/repository.py` |
| **Interfaces** | API 페이로드 → 도메인 객체 복원 시 정규화 호출 | `src/interfaces/schemas/blueprint.py` |

### 9.2 Dependency Rules

```
Interfaces ──→ Domain ←── Infrastructure
                 ▲
                 └── Application

Domain 은 외부를 참조하지 않는다.
font_normalization.py 는 policies / value_objects 만 임포트한다.
```

### 9.3 This Feature's Layer Assignment

| Component | Layer | Location | 상태 |
|-----------|-------|----------|:----:|
| `_PROTECTED_FAMILIES` + 보호 분기 | Domain | `policies.py` | 수정 |
| `normalize_blueprint_fonts()` | Domain | `font_normalization.py` | **신규** |
| `_to_domain()` 호출 ① | Infrastructure | `repository.py` | 수정 |
| `BlueprintUpsert.to_domain()` 호출 ② | Interfaces | `schemas/blueprint.py` | 수정 |

**application 레이어는 손대지 않는다.** `admin_use_case.update`는 이미 정규화된 객체를 받으므로 변경이 불필요하다 — Option A 대비 이점.

---

## 10. Coding Convention Reference

### 10.1 이 기능의 적용 규칙

| Item | Convention |
|------|-----------|
| 함수 길이 | 40줄 이하 — `normalize_blueprint_fonts`는 `_normalized_fonts`/`_normalized_mapping`으로 분할 |
| if 중첩 | 2단계 이하 |
| 타이핑 | 명시적 (`dict[str, str]`, `DocumentBlueprint`) |
| 하드코딩 | 보호 목록은 모듈 상수 `frozenset`으로 — 매직 문자열 인라인 금지 |
| 로깅 | 정규화 경로에 로깅 없음 (§6.2) |
| `print()` | 금지 |
| 주석 | `# Design Ref: §{절}` / `# Plan SC: {기준}` 형태로 추적 링크 |
| 린트 | **변경한 파일에만** `ruff check` — 디렉토리 전체 `--fix` 금지 (Plan §8.2) |

### 10.2 명명

| 대상 | 규칙 | 예시 |
|------|------|------|
| 모듈 | snake_case | `font_normalization.py` |
| 공개 함수 | snake_case 동사구 | `normalize_blueprint_fonts` |
| 내부 헬퍼 | `_` 접두 | `_normalized_fonts`, `_normalized_mapping`, `_family_key` |
| 상수 | `_UPPER_SNAKE` | `_PROTECTED_FAMILIES` |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/blueprint/
│   ├── policies.py                 [수정] _PROTECTED_FAMILIES + 보호 분기
│   └── font_normalization.py       [신규] normalize_blueprint_fonts
├── infrastructure/blueprint/
│   └── repository.py               [수정] _to_domain 에서 호출 ①
└── interfaces/schemas/
    └── blueprint.py                [수정] to_domain 에서 호출 ②

tests/
├── domain/blueprint/
│   ├── test_font_family_policy.py  [수정] 보호 패밀리 6건
│   ├── test_font_normalization.py  [신규] 시나리오 7~14
│   └── test_layer_contract.py      [수정] 시나리오 25~26
├── infrastructure/blueprint/
│   └── test_repository.py          [수정] 시나리오 15~16, 18
├── api/
│   └── test_admin_blueprint_router.py [수정] 시나리오 17
└── integration/blueprint/
    └── test_golden_sample_fidelity.py [수정] 시나리오 22~24
```

**신규 1 / 수정 3 (src) + 신규 1 / 수정 5 (tests)**

### 11.2 Implementation Order

TDD — 각 단계는 Red → Green → Refactor.

1. [ ] **FR-06 오탐 방지** — `test_font_family_policy.py`에 시나리오 1~6 추가(Red) → `policies.py`에 `_PROTECTED_FAMILIES` + `_strip_trailing_tokens` 보호 분기(Green)
2. [ ] **FR-01/02/05 정규화 함수** — `test_font_normalization.py` 시나리오 7~14(Red) → `font_normalization.py` 작성(Green)
3. [ ] **FR-01/03 읽기 경계** — 시나리오 15~16, 18, 21(Red) → `repository._to_domain` 호출 ①(Green)
4. [ ] **FR-03/04 쓰기 경계** — 시나리오 17(Red) → `schemas/blueprint.to_domain` 호출 ②(Green)
5. [ ] **순수성 계약 확인** — 시나리오 19~20 (기존 테스트 무수정 통과 확인)
6. [ ] **SC-1 산출물 검증** — 시나리오 22~24
7. [ ] **누락 방지 계약** — 시나리오 25~26
8. [ ] 변경 파일 대상 `ruff check` + blueprint 전체 회귀

> **1번을 가장 먼저 하는 이유**: 2번 이후는 모두 `normalize`를 신뢰하고 쌓아 올린다. 오탐이 남은 채로 경계에 붙이면 저장된 모든 블루프린트로 오탐이 확산된다.

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 도메인 정규화 | `module-1` | 구현 순서 1~2 — `policies.py` 보호 목록 + `font_normalization.py` + 도메인 테스트 | 15-20 |
| 경계 결선·검증 | `module-2` | 구현 순서 3~8 — repository/schemas 호출, 통합·계약 테스트, 회귀 | 20-25 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Plan + Design | 전체 | 완료 |
| Session 2 | Do | `--scope module-1,module-2` | 35-45 |
| Session 3 | Check + Report | 전체 | 20-30 |

> 총 변경 규모가 작아(src 4파일) **단일 세션 구현을 권장**한다. 모듈 분할은 컨텍스트가 부족할 때만 사용한다.

---

## 12. Key Design Decisions (DR)

| ID | Decision | Rationale |
|----|----------|-----------|
| **DR-1** | 정규화는 도메인 순수 함수, 호출은 경계에서 명시적 | `serialization.py`의 "순수 변환" 계약 보존 + 두 경로 커버 (Checkpoint 3, Option C) |
| **DR-2** | `style.fonts`와 `font_mapping`을 **반드시 함께** 정규화 | 렌더러가 전자를 키로 후자를 조회한다. 한쪽만 바꾸면 조회가 빗나가 매핑이 무력화된다 (시나리오 23) |
| **DR-3** | 오탐 방지는 **보호 패밀리 목록**(데이터) | 코어 로직 분기보다 확장이 싸다. 새 충돌 발견 시 목록만 늘린다 (Checkpoint 3) |
| **DR-4** | 보호 검사는 `normalize` 진입부가 아니라 **토큰 제거 루프 안**에서 | 진입부 검사는 `"Arial Black Italic"`을 놓친다. 루프 안이면 Italic만 떼고 `Arial Black`에서 멈춘다 |
| **DR-5** | 굵기 힌트(`normalize`의 2번째 반환값)는 **버린다** | 굵기는 run의 `bold` 속성으로 이미 표현. 패밀리명에 되돌리면 이중 적용 |
| **DR-6** | 키 충돌 시 **사전순 첫 번째** | 결정론적이고 테스트로 고정하기 쉽다. Regular 판별 로직 추가를 피한다 (Checkpoint 3) |
| **DR-7** | DB 마이그레이션 **없음**, 쓰기 시 점진 승격 | 되돌리기 어려운 파괴적 작업 회피. 원본 보존은 추적성 이점도 있다 (Plan §2.2) |
| **DR-8** | 정규화 경로에 **로깅 없음** | `list_all`에서 건마다 발생해 로그가 범람한다 (§6.2) |

---

## 13. Verification Notes (설계 중 실측)

Plan의 두 가정을 코드로 검증한 결과를 남긴다.

### 13.1 왕복 등가성 리스크 — 하향 조정

Plan §5 최상단 리스크(High/High)였으나, `test_serialization.py` 픽스처 값이 전부 정규화 불변점이다.

```
'H' → 'H'    'B' → 'B'    'NanumGothicBold' → 'NanumGothicBold'
```

Option C는 `blueprint_from_dict`를 건드리지 않으므로 이 리스크가 **구조적으로 소거**된다. 시나리오 19~20이 이를 고정한다.

### 13.2 정규화 오탐 — 신규 발견, FR-06으로 승격

Plan §5는 이 위험을 Low로 평가하고 "이름 전체가 토큰이면 원본 유지" 방어를 근거로 들었으나, **마지막 토큰만 토큰인 경우 그 방어는 작동하지 않는다.**

```
'Times New Roman' → ('Times New', False)   ← 실존하지 않는 이름
'Arial Black'     → ('Arial', True)        ← 별개 패밀리를 접음
```

Plan의 평가가 틀렸고, 이번 작업이 이 오탐을 저장된 모든 블루프린트로 확산시키므로 **범위에 포함**한다. Plan §3.1에 FR-06을 추가해야 한다(§14).

### 13.3 `golden_v1.json` 회귀 위험 확인

기존 픽스처가 `fonts`는 오염(`Malgun Gothic Bold`), `font_mapping` 값은 이미 정규화(`NanumGothic`)된 혼합 상태다. `style.fonts`만 정규화하면 조회가 빗나가 **`NanumGothic` → `Malgun Gothic`으로 퇴화**한다. DR-2가 이를 막고 시나리오 23이 검증한다.

---

## 14. Plan 문서 갱신 필요 항목

| 항목 | 내용 |
|------|------|
| Plan §3.1 | **FR-06 추가** — 정규화 오탐 방지 (보호 패밀리 목록), Priority High |
| Plan §4.1 | **SC-7 추가** — `Times New Roman`·`Arial Black`이 정규화 후에도 보존됨 |
| Plan §5 | 왕복 등가성 리스크 Likelihood를 High → **Low**로 하향 (§13.1 근거) |
| Plan §5 | 오탐 리스크 Likelihood를 Low → **High**로 상향, 완화책을 "테스트 추가" → "보호 목록 + FR-06"으로 교체 (§13.2 근거) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-25 | 최초 작성 — Option C 선정, FR-06 신규 발견 반영 | 배상규 |
