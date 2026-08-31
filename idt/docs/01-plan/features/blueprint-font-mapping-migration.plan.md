# blueprint-font-mapping-migration Planning Document

> **Summary**: 이미 저장된 블루프린트의 오염된 폰트명을 읽기 경계에서 정규화해, 재추출 없이도 PPTX가 올바른 폰트로 렌더되게 한다.
>
> **Project**: idt (sangplusbot 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-25
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `font_mapping`과 `style.fonts`가 추출 시점 값으로 `blueprint_json`에 고정 저장되어, FR-01(폰트명 정규화)이 **기존 블루프린트에 전혀 적용되지 않는다.** `Malgun Gothic Bold` 같은 존재하지 않는 타이프페이스명이 그대로 PPTX에 기록되어 뷰어가 대체 폰트로 렌더한다. |
| **Solution** | 블루프린트를 **읽어 들이는 단일 경계**에서 `FontFamilyPolicy.normalize`를 적용한다. DB 데이터는 건드리지 않고, 쓰기가 일어나는 시점에 정규화된 값이 자연히 저장되어 점진적으로 정리된다. |
| **Function/UX Effect** | 기존 블루프린트로 생성한 PPT의 폰트가 즉시 정상 렌더된다. 관리 UI의 폰트 표시도 실제 사용 이름과 일치한다. 사용자는 재추출·재업로드 없이 혜택을 받는다. |
| **Core Value** | 직전 사이클(pptx-font-fidelity)이 신규 추출 경로에만 닿았던 구멍을 막아, **이미 등록된 자산에도 수정이 실효**하게 만든다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | FR-01이 저장된 블루프린트에 도달하지 못해 폰트 깨짐이 실사용에서 그대로 재현된다 |
| **WHO** | P2 — 골든 샘플을 등록해 두고 반복 사용하는 KB 운영자/에이전트 소유자 |
| **RISK** | 읽기 경계 변경이 직렬화 왕복(roundtrip) 등가성 계약을 깬다 — 기존 테스트 및 관리 API 응답에 파급 |
| **SUCCESS** | 기존(미수정) 블루프린트로 생성한 PPTX의 모든 run이 유효한 패밀리명을 갖는다 |
| **SCOPE** | 읽기 경계 정규화 + 쓰기 승격. 데이터 마이그레이션·카탈로그 재매핑은 제외 |

---

## 1. Overview

### 1.1 Purpose

이미 DB에 저장된 `DocumentBlueprint`가 서브패밀리명(`Malgun Gothic Bold`, `Malgun Gothic Regular`)과 서브셋 프리픽스를 그대로 보유하는 문제를 해소한다. 재추출을 요구하지 않고, 읽는 순간 유효한 패밀리명으로 바로잡는다.

### 1.2 Background

`pptx-font-fidelity` 사이클에서 FR-01로 `FontFamilyPolicy`를 도입하고 `FontCatalog.propose_mapping`이 이를 거치도록 했다. 그러나 매핑 계산은 **추출 시점 1회**뿐이다.

```python
# extraction_use_case.py:236 — 추출 때 딱 한 번 계산
font_mapping, font_warnings = self._fonts.propose_mapping(_fonts_used(stats))

# generation_use_case.py:135 — 생성 때는 저장된 값을 그대로 사용
pptx = self._renderer.render(blueprint, slides, assets, blueprint.font_mapping)
```

렌더러의 조회는 `style.fonts[role]`을 키로 `font_mapping`을 찾는 구조라, **키(`style.fonts` 값)와 값(`font_mapping` 결과)이 모두 오염**되어 있으면 정규화가 끼어들 틈이 없다.

```python
# pptx_renderer.py:117-118
original = self.style.fonts.get(role, "")
return self.font_mapping.get(original, original) or original
```

**실측 증거** — 수정 후 생성물 `samples/ab89d9d03f6f4de7a4082656078944d3.pptx`(2026-08-24 22:17):
- FR-02는 적용됨: 모든 run이 `latin=ea=cs`로 동일
- FR-03도 적용됨: `핵심 관찰` 16pt bold #1F3A5F, space_after 6pt
- **FR-01만 미적용**: 값이 여전히 `Malgun Gothic Bold` / `Malgun Gothic Regular`

정규화가 동작했다면 `Malgun Gothic`이어야 한다. FR-02/03이 보이는데 FR-01만 안 보인다는 사실 자체가, 코드가 아니라 **저장 데이터가 원인**임을 특정한다.

### 1.3 Related Documents

- 선행 사이클: `docs/01-plan/features/pptx-font-fidelity.plan.md`, `docs/02-design/features/pptx-font-fidelity.design.md`, `docs/03-analysis/pptx-font-fidelity.analysis.md`
- 원 설계: `docs/architecture/golden-sample-blueprint.md` §3.3 / §4.3(DR-5 쓰기 경계 승격)
- 코딩 규칙: `idt/CLAUDE.md`, `docs/rules/db-session.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] 블루프린트 읽기 경계에서 `style.fonts`와 `font_mapping`을 `FontFamilyPolicy.normalize`로 정규화
- [ ] 정규화 결과가 쓰기 시 저장되도록 승격 (관리 UI 수정·저장 경로)
- [ ] `font_mapping` 키/값 동시 정규화로 키 충돌(여러 서브패밀리 → 같은 패밀리) 처리 규칙 확정
- [ ] 직렬화 왕복 등가성 계약 변경에 따른 기존 테스트 조정
- [ ] 기존 블루프린트 기준 회귀 테스트 (오염 데이터 → 정상 PPTX)

### 2.2 Out of Scope

- **일회성 DB 마이그레이션 스크립트** — 읽기 경계 정규화로 증상이 해소되므로 불필요. 되돌리기 어려운 파괴적 작업은 피한다.
- **FontCatalog 재매핑** — 설치 폰트로의 치환(`propose_mapping` 재실행)은 하지 않는다. 패밀리명만 바로잡는다. `generation_use_case`에 `FontCatalogPort`를 주입하는 결선 확대를 피하기 위함.
- **슬롯 좌표 정합성(B)** — vision LLM 추정 좌표와 실측 장식 좌표의 불일치. 별도 사이클.
- **목차·카드 내용 폴백(C)** — 슬롯 내용이 비어 제목만 남는 문제. 별도 사이클.
- **차트 데이터 레이블·단위, 표 테두리, 문단 여백(D)** — 별도 사이클.
- `schema_version` 승격 규칙 변경 — 기존 DR-5를 그대로 따른다.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 저장된 블루프린트를 도메인 객체로 복원할 때 `style.fonts`의 모든 값을 `FontFamilyPolicy.normalize`로 정규화한다 | High | Pending |
| FR-02 | `font_mapping`의 **키와 값을 모두** 정규화한다. 서로 다른 원본이 같은 패밀리로 접히면 결정론적 규칙으로 하나를 남긴다 | High | Pending |
| FR-03 | 정규화된 블루프린트가 `update` / `replace`로 저장될 때 정규화된 값이 `blueprint_json`에 기록된다 (쓰기 승격) | High | Pending |
| FR-04 | 관리 API 응답(`BlueprintDetail`)의 폰트 필드가 실제 렌더에 쓰이는 이름과 일치한다 | Medium | Pending |
| FR-05 | 이미 정규화된 블루프린트는 정규화를 통과해도 값이 변하지 않는다 (멱등성) | High | Pending |
| FR-06 | 정규화가 실존 패밀리를 훼손하지 않는다 — `Times New Roman`·`Arial Black` 등을 **보호 패밀리 목록**으로 제외한다 | High | Pending |

> FR-06은 Design 단계 실측에서 발견된 기존 결함이다. 상세는 설계 §13.2 참조.

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 아키텍처 | domain → infrastructure 참조 없음. 정규화는 도메인 정책만 사용 | `/verify-architecture` |
| 성능 | 블루프린트 1건 로드당 추가 비용이 무시 가능 (폰트 키 수 ≈ 5개, 정규식 기반) | `list_all` 호출의 p95 변화 없음 확인 |
| 하위호환 | v1·v2 `schema_version` 블루프린트 모두 로드 성공 | 기존 `test_serialization` + v1 픽스처 통과 |
| 멱등성 | `normalize(normalize(x)) == normalize(x)` | 도메인 단위 테스트 |
| 회귀 | blueprint 관련 기존 테스트 전부 통과 | `pytest tests/*/blueprint` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1 — **오염된 블루프린트(수정 전 저장 형태)를 로드해 렌더한 PPTX의 모든 run이 `Malgun Gothic`**(서브패밀리 접미사 없음)을 갖는다
- [ ] SC-2 — 이미 정규화된 블루프린트는 로드 전후 값이 동일하다 (멱등)
- [ ] SC-3 — `font_mapping` 키 충돌 시 결정론적으로 하나가 선택되고, 그 규칙이 테스트로 고정된다
- [ ] SC-4 — 관리 API `GET /blueprints/{id}` 응답의 `style.fonts`·`font_mapping`이 정규화된 값이다
- [ ] SC-5 — 설계 §Test Plan의 모든 시나리오에 대응하는 자동화 테스트가 존재한다 (직전 사이클 SC-4 미달 재발 방지)
- [ ] SC-6 — blueprint 관련 기존 테스트 회귀 0건
- [ ] SC-7 — `Times New Roman`·`Arial Black`이 정규화를 통과해도 원형 그대로 보존된다 (FR-06)

### 4.2 Quality Criteria

- [ ] 함수 40줄 이하 / if 중첩 2단계 이하
- [ ] `print()` 없음, 명시적 타입
- [ ] ruff lint 0건 (**변경한 파일에만** 실행 — 직전 사이클에서 tests/ 전체에 `--fix`를 돌려 무관 파일 647개를 건드린 사고 재발 방지)
- [ ] 신규·변경 코드 커버리지 95% 이상

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| ~~**직렬화 왕복 등가성 계약 파괴**~~ — `blueprint_from_dict(blueprint_to_dict(bp)) == bp`를 고정한 `test_serialization.py:116` | High | ~~High~~ → **Low** | **해소됨.** Design이 Option C(`blueprint_from_dict` 무변경)를 채택해 구조적으로 소거. 더불어 픽스처 값(`H`/`B`/`NanumGothicBold`)이 모두 정규화 불변점임을 실측 확인 — 설계 §13.1 |
| 키 충돌로 매핑 항목이 소실 — `Malgun Gothic Bold`와 `Malgun Gothic Regular`가 모두 `Malgun Gothic`으로 접힘 | Medium | High | 값이 서로 다를 때의 우선순위 규칙을 명시하고 테스트로 고정. 접힘 자체는 **의도된 동작**(굵기는 run의 bold 속성으로 표현) |
| 저장 데이터는 계속 오염 상태 — 읽기 정규화는 증상만 가린다 | Low | High | 수용한다. 쓰기 승격으로 손대는 블루프린트부터 점진 정리. 원본 보존은 추적성 측면에서 이점도 있다 |
| 오염 범위 미측정 — MySQL(3308)이 내려가 있어 저장된 블루프린트 실물을 확인하지 못함 | Medium | Medium | Do 단계 착수 전 DB를 띄워 실제 `font_mapping` 값을 1건 이상 확인한다. 예상과 다르면 Plan을 갱신한다 |
| **정규화가 지나쳐 정상 폰트명을 훼손** — `Times New Roman` → `Times New`, `Arial Black` → `Arial`(+bold) | High | ~~Low~~ → **High (실측 확인됨)** | 기존 "이름 전체가 토큰이면 원본 유지" 방어는 **마지막 토큰만 토큰인 경우 작동하지 않는다** — Plan 최초 평가가 틀렸다. **FR-06(보호 패밀리 목록)으로 범위에 포함.** 보호 검사는 토큰 제거 루프 안에 두어 `Arial Black Italic`도 처리한다 — 설계 §13.2 / DR-3 / DR-4 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| 블루프린트 읽기 경계 (`blueprint_from_dict` 또는 `repository._to_domain`) | Domain / Infrastructure | `style.fonts`·`font_mapping` 정규화 삽입 |
| `FontFamilyPolicy` | Domain Policy | 변경 없음 — 기존 `normalize` 재사용 (신규 헬퍼 추가 가능) |
| `blueprint_json` 저장 값 | DB 데이터 | 스키마 무변경. 쓰기 시 정규화된 값이 기록됨 (마이그레이션 없음) |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `blueprint_from_dict` | READ (DB) | `repository.py:188 _to_domain` ← `find_by_id`, `list_all` | **의도된 변경** — 정규화 적용 지점 |
| `blueprint_from_dict` | WRITE (API 입력) | `interfaces/schemas/blueprint.py:139 to_domain` ← 관리 PUT | **Needs verification** — 여기서도 정규화되면 FR-03 쓰기 승격이 자동 충족 |
| `blueprint_to_dict` | WRITE | `repository.py:53 save` / `:78 update` / `:99 replace` | None — 이미 정규화된 객체를 그대로 직렬화 |
| `font_mapping` | READ | `generation_use_case.py:135` → `pptx_renderer._Ctx.font()` | **주 수혜자** — 정상 폰트명 수신 |
| `style.fonts` | READ | `pptx_renderer.py:117` (매핑 조회 키) | **Needs verification** — 키·값 양쪽 정규화가 맞물려야 조회가 성립 |
| `style.fonts` | READ | `interfaces/schemas/blueprint.py` `StyleSchema` → 관리 UI 응답 | 표시 값 변경 (FR-04, 의도됨) |
| `style.fonts` | WRITE | `extraction_use_case.py:277` (신규 추출) | None — 이미 정규화된 경로 |
| 왕복 등가성 | TEST | `tests/domain/blueprint/test_serialization.py:110-116` | **Breaking 가능** — §5 최상단 리스크 참조 |
| v1 하위호환 | TEST | `tests/integration/blueprint/test_golden_sample_fidelity.py:191` | **Needs verification** — v1 픽스처도 정규화를 통과해야 함 |
| 관리 라우터 | TEST | `tests/api/test_admin_blueprint_router.py:97` | **Needs verification** — 응답 기대값에 폰트명 포함 여부 확인 |

### 6.3 Verification

- [ ] 위 모든 소비자가 정규화된 값으로 정상 동작함을 확인
- [ ] 왕복 등가성 계약의 처리 방침이 Design에서 명시적으로 결정됨
- [ ] v1 / v2 `schema_version` 양쪽 로드 확인
- [ ] 관리 API 응답 스키마 변경 없음 → **프론트 타입 동기화 불필요** (값만 바뀜, 필드 구조 동일)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| Starter | 단순 구조 | 정적 사이트 | ☐ |
| Dynamic | 기능 단위 모듈 | BaaS 기반 웹앱 | ☐ |
| **Enterprise** | 레이어 분리 (Thin DDD) | 본 프로젝트 | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 적용 지점 | 렌더 안전망 / **로드 경계** / DB 마이그레이션 / 복합 | **로드 경계 정규화** | 한 지점에서 모든 소비자를 커버하고 DB를 건드리지 않아 롤백이 자유롭다 (Checkpoint 2) |
| 카탈로그 재적용 | 정규화만 / 정규화+재매핑 | **정규화만** | 도메인 정책만 사용해 의존성 추가 없음. 결선 확대 회피 (Checkpoint 2) |
| 쓰기 승격 | 승격 / 원본 유지 | **승격한다** | 기존 DR-5(schema_version 쓰기 경계 승격)와 동일 패턴, 점진적 데이터 정리 (Checkpoint 2) |
| 정규화 배치 레이어 | domain serialization / infrastructure repository | **Design에서 결정** | 왕복 등가성 계약과 직결 — §5 최상단 리스크 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

영향 레이어:
┌──────────────────────────────────────────────────────────┐
│ domain/blueprint/                                        │
│   policies.py          FontFamilyPolicy (재사용, 무변경)  │
│   serialization.py     ← 정규화 후보 지점 A               │
├──────────────────────────────────────────────────────────┤
│ infrastructure/blueprint/                                │
│   repository.py        ← 정규화 후보 지점 B (_to_domain)  │
├──────────────────────────────────────────────────────────┤
│ interfaces/schemas/                                      │
│   blueprint.py         to_domain — 지점 A 선택 시 자동 포함│
└──────────────────────────────────────────────────────────┘

domain → infrastructure 참조 없음 (FontFamilyPolicy는 순수 도메인)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규칙 존재 (루트 + `idt/`)
- [x] `docs/rules/` 세부 규칙 존재 (db-session, logging, testing 등)
- [x] ruff 설정 (`pyproject.toml`)
- [x] pytest 설정

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 네이밍 | exists | 없음 | - |
| 폴더 구조 | exists | 없음 | - |
| 에러 처리 | exists | 정규화 실패 시 원본 유지(예외 던지지 않음) 방침 | High |
| 린트 실행 범위 | **missing** | **변경 파일에만 ruff 실행** — 직전 사고 재발 방지 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| — | 신규 환경변수 없음 | — | ☐ |

### 8.4 Pipeline Integration

해당 없음 (단일 기능 수정, 9-phase 파이프라인 미사용).

---

## 9. Next Steps

1. [ ] **DB 기동 후 실제 `font_mapping` 값 1건 이상 확인** — 오염 범위 실측 (Do 착수 전 필수)
2. [ ] 설계 문서 작성 (`/pdca design blueprint-font-mapping-migration`) — 정규화 배치 레이어 3안 비교
3. [ ] TDD 구현 (Red → Green → Refactor)
4. [ ] Gap 분석 (`/pdca analyze`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-25 | 최초 작성 — pptx-font-fidelity 후속, 결함 A 대응 | 배상규 |

| 0.2 | 2026-08-25 | Design 실측 반영 — FR-06/SC-7 추가, 왕복 리스크 하향, 오탐 리스크 상향 | 배상규 |
