# judgment-backend Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: sangplusbot (idt 백엔드)
> **Analyst**: 배상규 (gap-detector 정적 분석 + 오케스트레이터 런타임 검증)
> **Date**: 2026-10-16
> **Design Doc**: [judgment-backend.design.md](../02-design/features/judgment-backend.design.md)
> **Plan Doc**: [judgment-backend.plan.md](../01-plan/features/judgment-backend.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 판정형 LLM 호출이 전부 생성 모델에 묶여 있어 판정 전용 모델(Jev)로 못 바꾸고, 폐쇄망에서는 대체(AnyJev)가 필요한데 포트가 없다 |
| **WHO** | 1차: 운영자/배포 담당 — `.env` 한 줄로 백엔드 교체. 2차: 후속 개발자 — 포트에 질문만 얹어 다음 소비 지점 교체. 3차: 최종 사용자 — 동작 불변(폴백) |
| **RISK** | AnyJev HTTP 계약이 미검증이고 두 백엔드 모두 지금 실호출 불가 → 어댑터는 전송 계층 픽스처로 계약 고정, 실호출은 이월 체크리스트 |
| **SUCCESS** | `JUDGMENT_BACKEND=off`에서 기존 테스트 전량 무변경 통과, `jev`/`anyjev`에서 search_decision이 Noul 확률+임계값으로 결정, 백엔드 실패 시 폴백 100%, AST 경계 테스트 통과, 회귀 `FAILED` diff 0 |
| **SCOPE** | 이번: 포트(Noul+Choice) + Jev/AnyJev 어댑터 + 팩토리 + config + search_decision 교체·폴백 + 테스트. 제외: Score, 인프로세스 AnyJev, 다른 소비 지점, 관리자 UI, DB 레지스트리 |

---

## Strategic Alignment Check

### Plan Alignment (PRD 없음)

| Element | Expected | Status |
|---------|----------|:------:|
| Core Problem (WHY) | 판정 백엔드를 포트 뒤로 빼고 설정으로 교체 | ✅ `JudgmentPort` + Jev/AnyJev 어댑터 + `JUDGMENT_BACKEND` 1키 |
| Target User (WHO) | 운영자 `.env` 교체 / 후속 개발자 포트 재사용 / 사용자 동작 불변 | ✅ 기본 `off`, 폴백으로 동작 불변 |
| Value | 코어가 벤더·망 환경에 묶이지 않음 | ✅ domain은 stdlib만, 벤더 특성은 어댑터에 격리 |

### Success Criteria Status (Plan §4.1 DoD)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | FR-01~15 구현·테스트 통과 | ✅ | FR 14 Met / 1 Partial(FR-08, G1). 115 passed (`tests/domain/judgment`, `tests/infrastructure/judgment`, `search_decision/test_judgment_adapter.py`, `api/test_judgment_di.py`) |
| SC-2 | 전송 픽스처 5케이스 × 2백엔드 × Noul/Choice | ⚠️ | 5케이스 × 2백엔드는 전부 있으나 실패 케이스는 Noul 요청만(G8) |
| SC-3 | 팩토리 4실패→None·2정상 | ✅ | `test_factory.py`(예외 전파) + `test_judgment_di.py:38-51`(main None + warning 1회) |
| SC-4 | search_decision 임계값 경계·폴백 | ✅ | `test_judgment_adapter.py` 0.49/0.50/0.51, 실패 3종+외부 wait_for → fallback 1회 |
| SC-5 | `off`에서 기존 테스트 무수정 통과 | ✅ | 전체 스위트 53 failed / 10,656 passed — FAILED test id 목록이 master 기준 53건과 diff 0 |
| SC-6 | AST 경계 테스트 + `_DECLARED_CONSUMERS` 근거 주석 | ✅ | `test_module_boundaries.py` 5건 통과(이전 skip 2건 해제) |
| SC-7 | `-m llm` 스모크 2종 작성, 실행 이월 | ✅ | `test_real_backend_smoke.py` — env 없을 때 2 skipped 확인 |
| SC-8 | 회귀 FAILED diff 0 | ✅ | 위 SC-5 |
| SC-9 | Design 확정 항목(AnyJev 스키마·SDK 버전·질문 문구) | ✅ | Design §0 D1~D3·D8, §4.5 |
| QC | 신규 모듈 커버리지 ≥ 90%(domain 100%) | ⚠️ | 합계 **96%** (adapter·factory 100%, jev/mapping 93%, value_objects **95%** — domain 100% 미달, 방어 분기 6줄), judgment_adapter 97% |

**Success Rate**: 8/10 Met, 2 Partial (SC-2, QC)

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | 소비 지점 1곳(search_decision), AnyJev HTTP만, 실패 시 LLM 폴백, typesafe-sdk, 임계값 config 1키 | ✅ | — |
| [Design] | D1 AnyJev Noul 네이티브 | ✅ | Plan 본문(§1.2·S3·FR-06)은 아직 "에뮬레이션" 문구 — 문서 동기화 필요 |
| [Design] | D3/D6 AnyJev 부가 필드 보존 위치 | ⚠️ | `extra["decisions"][i]["margin"]`(다중 질문 구조) — Design이 `extra["margin"]`로 적음(G2). `index/first_pass/reasoning_tokens` 미보존 |
| [Design] | D8 SDK 압축 | ⚠️ | Design 근거("미설치 시 비압축")가 SDK 동작과 다름 — 구현의 `compression=False`가 맞음(G6) |
| [Design] | D9 재시도 0, D10 예외 매핑 | ⚠️ | Jev 완전. AnyJev는 `httpx.DecodingError`·Choice 경로 `TypeError` 누락(G1) |
| [Design] | D11~D17 | ✅ | `StrEnum` 사용(사소), 나머지 일치 |

---

## 1. Analysis Overview

### 1.1 Purpose

Design D1~D17·§4 계약·§8 테스트 계획이 구현과 맞는지, Plan FR·DoD가 충족됐는지 확인하고, 이월 항목(실호출)을 명시한다.

### 1.2 Scope

- Design: `docs/02-design/features/judgment-backend.design.md`
- 구현: `src/domain/judgment/`, `src/infrastructure/judgment/`, `src/infrastructure/search_decision/{judgment_adapter,questions}.py`, `src/config.py`, `src/api/main.py`, `.env.example`, `pyproject.toml`
- 분석일: 2026-10-16

---

## 2. Gap Analysis

### 2.1 외부 계약 (§4 ↔ 어댑터)

| Design | Implementation | Status |
|--------|---------------|--------|
| §4.1 Jev `AsyncTypeSafeClient(api_key, base_url, model, timeout, retry=0, http_client)` | `jev/adapter.py:39-57` (+`compression=False`) | ✅ |
| §4.1 `system_one(state, questions, model=, timeout=)` → `answers[qid]` | `jev/adapter.py:61-67`, `jev/mapping.py:58-91` | ✅ |
| §4.2 AnyJev `POST /v1/decide {"items":[…]}` → `{"decisions":[…]}` | `anyjev/adapter.py:52-64`, `anyjev/mapping.py:43-59` | ✅ |
| §4.2 Noul `kind:"noul"`, probs Yes casefold | `anyjev/mapping.py:49,104-108` | ✅ |
| §4.2 Choice options=라벨, 설명 접기, confidence=max | `anyjev/mapping.py:36-40,112-120` | ✅ |
| §4.2 부가 필드 extra | `extra["decisions"][i]{qid,margin,route}` | ⚠️ G2 |
| §4.2 에러 정규화 | `httpx.TimeoutException`·`TransportError`·status≥400 처리, `DecodingError` 누락 | ⚠️ G1 |
| §4.3 Config 8키·기본값·docstring | `config.py` Judgment Backend 블록 | ✅ |
| §4.4 팩토리·`get_judgment_backend` 1회 조립·조립 분기·lifespan close | `factory.py`, `main.py` | ✅ |
| §4.5 소비 지점 어댑터 | `judgment_adapter.py` | ✅ |

### 2.2 Data Model (§3.1~3.3)

| VO/예외 | Status | Notes |
|---------|:------:|-------|
| `JudgmentBackendKind.from_string` | ✅ | `StrEnum` |
| `NoulQuestion`/`ChoiceQuestion(labels)` | ✅ | 중복·2개 미만 ValueError |
| `JudgmentRequest` state str/Mapping 검증·동결 | ✅ | 설계 외 추가 검증(값 문자열) |
| `NoulAnswer`/`ChoiceAnswer` 범위·합·choice∈labels | ✅ | |
| `JudgmentResponse.noul()/choice()` | ✅ | ProtocolError |
| 예외 3종 + `backend` 속성 | ✅ | 메시지에 키·state 미포함(테스트) |
| `JudgmentPort.judge/aclose` | ✅ | |

### 2.3 Component Structure (§11.1)

소스 18개·테스트 8개·픽스처 4개 전부 존재. 이름 차이 1건: Design `tests/api/test_judgment_wiring.py` → 실제 `tests/api/test_judgment_di.py`(G9).

### 2.4 Functional Depth

| File | Depth | Notes |
|------|:-----:|-------|
| domain 4파일 | 100 | TODO/placeholder 0 |
| anyjev/{adapter,mapping} | 90 | G1 예외 경로 |
| jev/{adapter,mapping} | 100 | |
| factory | 100 | 설계 외 timeout>0 검증·info 로그 |
| search_decision/judgment_adapter·questions | 100 | |
| main.py 조립 | 100 | |

**Shallow File Count**: 0

### 2.5 UI Checklist

해당 없음(백엔드 전용).

### 2.6 Contract Match

33개 검사 항목 중 31 일치 + 2 반점(G1, G2) = **97.0%**

### 2.7 Runtime Verification Results

| # | 검증 | 결과 | Pass |
|---|------|------|:----:|
| L1 | 신규 단위·계약 테스트 | 115 passed (Jev 테스트 skip 아님 — SDK 설치됨) | ✅ |
| L2 | 조립·결선 + 전체 회귀 | 53 failed / 10,656 passed, FAILED id 목록 master와 diff 0, 수집 ERROR 0 | ✅ |
| L3 | 실호출 스모크 | env 없음 → 2 skipped (**Plan 결정으로 이월**) | — |
| 커버리지 | 신규 모듈 | 96% (domain value_objects 95%) | ⚠️ |

**Runtime Match Rate**: L1 100 × 0.4 + L2 100 × 0.3 + L3(이월, 제외) → 실행된 항목 기준 **100%**

### 2.8 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  98.1%               │  (26.5 / 27)
│  Functional Match Rate:  93.9%               │  FR 96.7 · L1 100 · L2 87.5 · D 91.2 평균
│  Contract Match Rate:    97.0%               │  (32 / 33)
│  Runtime Match Rate:    100.0%               │  (L3 이월 제외)
│  ─────────────────────────────────────────── │
│  Overall (static only):  96.0%               │  0.2×98.1 + 0.4×93.9 + 0.4×97.0
│  Overall (with runtime): 97.4%               │  0.15×98.1 + 0.25×93.9 + 0.25×97.0 + 0.35×100
├─────────────────────────────────────────────┤
│  ❌ Critical: 0   ⚠️ Important: 1 (G1)        │
│  Minor: 10 (코드 5 · 테스트 4 · 문서 3 중복)   │
└─────────────────────────────────────────────┘
```

---

## 3. Gap List

| ID | 심각도 | 신뢰도 | 위치 | 내용 | 수정 제안 |
|----|:---:|:---:|------|------|------|
| G1 | **Important** | 75% | `anyjev/adapter.py:55-58`, `anyjev/mapping.py:83,117-119` | `httpx.DecodingError`(RequestError 하위, TransportError 아님)가 정규화되지 않고 빠져나감. Choice 경로에서 `answer`가 unhashable이거나 probs 값이 str/float 혼합이면 `TypeError` — `from_decisions`는 `ValueError`만 잡음. 소비 지점은 `JudgmentError`만 잡으므로 엑셀 분석 흐름 중단 가능(FR-08·가용성 NFR 위반) | `except httpx.RequestError` → Unavailable, `from_decisions`에서 `(ValueError, TypeError)` → Protocol. 회귀 테스트 2건 |
| G2 | Minor | 95% | `anyjev/mapping.py:85-91` | D6 `extra["margin"]` vs 구현 `extra["decisions"][i]["margin"]`; `index/first_pass/reasoning_tokens` 미보존 | 다중 질문엔 리스트가 맞음 → Design D3/D6 갱신 + `reasoning_tokens` 보존 |
| G3 | Minor | 90% | `tests/api/test_judgment_di.py:65-78` | L2 #6/#7이 AST 키워드 존재만 확인. None 분기·fallback 타입 런타임 단언 없음 | 조립을 `_build_search_decision()` 헬퍼로 분리해 monkeypatch 단언 |
| G4 | Minor | 85% | `test_judgment_adapter.py:125-131` | L2 #11 "폴백도 예외"를 실제로 시뮬레이션하지 않음 | 예외 던지는 provider를 가진 실제 `LLMSearchDecisionAdapter`를 fallback으로 |
| G5 | Minor | 70% | `judgment_adapter.py:39-40` ← `main.py` 조립 | 백엔드 on + 임계값 0~1 밖 → `ValueError`로 기동 실패. Design §4.3대로지만 §6.1 표에 없고 "조립 실패가 기동을 막지 않는다"와 어긋남 | 조립 분기에서 잡아 LLM 어댑터 + warning(prompt_guard mode 오타 선례와 동일) 또는 §6.1에 fail-fast 명시 |
| G6 | Minor(문서) | 85% | Design D8 | "zstd 미설치 시 비압축" 근거가 SDK 동작과 다름(미설치 시 TypeSafeError). 구현 `compression=False`가 맞음 | D8·§4.1에 `compression=False` 반영 |
| G7 | Minor | 60% | `factory.py:56` | `typesafe_base_url=None`이면 SDK가 `TYPESAFE_BASE_URL` env를 읽음 — FR-04 경계 사례(Settings가 같은 env를 읽어 실제 갈릴 일 거의 없음) | None일 때 SDK 기본 URL 상수를 명시 전달 |
| G8 | Minor | 90% | 두 어댑터 실패 테스트 | 실패 케이스가 Noul 요청만 | `_mixed_request`로 parametrize |
| G9 | Minor(문서) | 100% | Design §11.1 | 테스트 파일명 불일치 | `test_judgment_di.py`로 갱신 |
| G10 | Minor | 90% | `test_real_backend_smoke.py` | §8.4 #2 `/health` 선조건 미확인 | ok 아니면 skip |
| G11 | Minor | 85% | `main.py:_close_judgment_backend`, `test_judgment_di.py` | aclose 실패 warning 테스트 없음, singleton 테스트가 클라이언트 미정리 | fake aclose 예외 테스트 + `await backend.aclose()` |
| G12 | Minor(품질) | 100% | `value_objects.py:115,121,141,169,172,175` | domain 커버리지 95% (QC 목표 100%) — state 값 타입·questions 타입·model 빈 값 방어 분기 | 테스트 6줄 추가 |

**문서 동기화(코드 갭 아님)**: Plan §1.2·S3·FR-06의 "Noul 에뮬레이션" 문구 → D1 정정 반영. `.env.example` "오타는 off와 같다"에 "warning 1회 남음" 덧붙임.

---

## 4. Code Quality

- 함수 40줄·if 중첩 2단계 규칙 위반 0. 매핑은 순수 함수.
- ruff(E,F,I,N,W,UP) clean. `print` 0, TODO 0.
- 보안: API 키·state 원문이 로그·예외 메시지에 들어가지 않음(테스트로 고정). AnyJev 무인증은 config docstring·`.env.example`에 명시(D16).

---

## 5. Clean Architecture Compliance

| Layer | Expected | Actual | Status |
|-------|----------|--------|:------:|
| Domain `judgment` | stdlib만 | `math, collections.abc, dataclasses, enum, types, typing` | ✅ |
| Infrastructure `judgment` | domain·config·SDK/httpx | 동일, application/api 참조 0 | ✅ |
| Infrastructure `search_decision/judgment_adapter` | domain 포트만 | `src.infrastructure.judgment` 참조 0 | ✅ |
| Composition | main.py 1곳 | `_DECLARED_CONSUMERS` 2파일 외 참조 0 | ✅ |

**Architecture Compliance: 100%** (AST 테스트 5건이 CI에서 강제)

---

## 6. Recommended Actions

### 6.1 Immediate (이번 사이클, Act)

| Priority | Item | File |
|----------|------|------|
| 🟡 1 | G1 AnyJev 예외 정규화 (`RequestError`, `TypeError`) + 테스트 2건 | `anyjev/adapter.py`, `anyjev/mapping.py`, `test_anyjev_adapter.py` |
| 🟢 2 | G5 임계값 범위 오류를 조립 실패로 흡수 (prompt_guard 선례 일치) | `main.py` 조립 분기 |
| 🟢 3 | G12 domain 커버리지 100% | `test_value_objects.py` |
| 🟢 4 | G2·G6·G9 Design 동기화, Plan FR-06 문구 정정 | docs |

### 6.2 Short-term (후속 소형 사이클 또는 Report 이월)

- G3·G4·G8·G10·G11 테스트 보강, G7 base_url 명시
- **실호출 스모크(L3) + 양성 대조군 벤치 → 임계값 조정** — 환경 확보 시 (Plan 결정으로 이월)

---

## 6.3 Act-1 결과 (2026-10-16, 사용자 결정: Important + 즉시 항목)

| Gap | 조치 | 근거 |
|-----|------|------|
| G1 | `anyjev/adapter.py` `except httpx.RequestError`(DecodingError 포함) → Unavailable; `anyjev/mapping.py` `except (ValueError, TypeError)` → Protocol | `TestActOneExceptionNormalization` 3건(DecodingError·unhashable answer·타입 혼합 probs) |
| G2 | `reasoning_tokens` 보존, Design D3/D6를 리스트 구조로 갱신 | `test_reasoning_tokens_preserved` |
| G3·G5 | 조립을 `main.py _build_search_decision()` 헬퍼로 분리, 생성자 예외(임계값 범위 등)는 warning + LLM 어댑터로 흡수. Design §6.1 행 추가 | `test_search_decision_falls_back_to_llm_when_threshold_invalid`, `..._wraps_backend_when_enabled`(fallback 타입 런타임 단언), `..._is_llm_adapter_when_off` |
| G6 | Design D8·§4.1에 `compression=False` 반영 | 문서 |
| G9 | Design §11.1 파일명 `test_judgment_di.py` | 문서 |
| G12 | domain 방어 분기 테스트 6건 → `value_objects.py` 100% | 커버리지 재측정: domain 100%, 신규 모듈 합계 98% |
| Plan FR-06 | "에뮬레이션" 문구 → D1 정정 반영 | 문서 |

Act-1 후: 관련 테스트 **128 passed**(prompt_guard DI 회귀 포함), ruff clean, `main.py` diff 70(+)/1(−)로 한정.
이월(Report에 기록): G4(폴백 자체 예외 시뮬레이션), G7(base_url 명시), G8(실패 케이스 Choice parametrize), G10(`/health` 선조건), G11(aclose 실패 warning 테스트), 실호출 스모크(L3).

재산정: Functional — FR 15/15, L2 (11 + 0.5)/12 = 95.8, Decision (16 + 0.5)/17 = 97.1 → (100+100+95.8+97.1)/4 = **98.2%**; Contract 33/33 = **100%**; Structural 27/27 = **100%**.
**Overall (static) = 0.2×100 + 0.4×98.2 + 0.4×100 = 99.3%**, 런타임 포함 **99.5%**.

---

## 7. Next Steps

- [ ] Checkpoint 5 — 수정 범위 결정 (전부 / Important만 / 그대로)
- [ ] Act 후 재분석 없이 Report 가능 (Overall ≥ 90%)
- [ ] `judgment-backend.report.md` 작성

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-16 | 초기 분석 — 정적 96.0%, 런타임 포함 97.4%, Critical 0 / Important 1 | 배상규 |
| 0.2 | 2026-10-16 | Act-1 반영 — G1·G2·G3·G5·G6·G9·G12 해소, 정적 99.3% | 배상규 |
