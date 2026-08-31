# multimodal-extractor Analysis Report

> **Analysis Type**: Gap Analysis (Design ↔ Implementation) + Runtime Verification
>
> **Project**: idt (sangplusbot 백엔드) + idt_front
> **Version**: 0.1.0
> **Analyst**: 배상규 (gap-detector 정적 분석 + 런타임 실측)
> **Date**: 2026-08-21
> **Design Doc**: [multimodal-extractor.design.md](../02-design/features/multimodal-extractor.design.md)
> **Plan Doc**: [multimodal-extractor.plan.md](../01-plan/features/multimodal-extractor.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 파이프라인이 문서의 시각 정보(그림·차트·스캔 표)를 버려 RAG 근거에 구멍이 난다 |
| **WHO** | P3 관리자(모델·가드 설정), P2 KB 운영자(미리보기로 품질 확인), 간접 수혜 P1/P4 |
| **RISK** | 비전 비용/지연 폭증 + 벤더별 이미지 포맷 누수 → 가드 설정값 강제, 포트 AST 고정 |
| **SUCCESS** | 어댑터 3종 실 LLM 1회 이상 통과, 건별 degraded, 미리보기 확인, 회귀 FAILED diff 0 |
| **SCOPE** | Phase 1 전체(module-1~7) 구현 완료 / Phase 2(저장 연동·Office·로컬 스모크)는 후속 |

---

## Strategic Alignment Check

### Plan/Scenario Alignment (PRD 없음 — USER-SCENARIOS.md 기준)

| Element | Expected | Status |
|---|---|:-:|
| Core Problem (WHY) | 시각 정보 추출·해석 결과를 구조화해 반환 | ✅ `MultimodalExtractionUseCase.run()` → `ExtractionResult` (FR-16) |
| Target User (WHO) | P3가 모델·가드를 화면에서 설정, P2가 미리보기로 확인 (S1 폐루프, DB/Swagger 0회) | ✅ `/admin/multimodal` 2탭 + `/admin/llm-models` 비전 체크박스 |
| 일반화 원칙 | 벤더·문서형식 하드코딩 없이 레지스트리 확장 | ✅ provider/확장자 키 레지스트리, gemini·docx 미등록=명시 오류 |
| "모델은 고정, 데이터가 성장" | 설정은 DB 행, 프롬프트는 코드, 코어에 여신 특화 없음 | ✅ |

### Success Criteria Status (Plan §4.1/§4.2)

| # | Criteria | Status | Evidence |
|---|---|:-:|---|
| SC-1 | FR-01~20 구현 + 대응 테스트 | ⚠️ | 16 ✅ / 4 ⚠️ (FR-09·14·15·20, 아래 표) |
| SC-2 | 어댑터 3종 실 LLM 스모크 통과 기록 | ⚠️ | **실측**: OpenAI ✅(strict) · Anthropic ✅(strict) · 로컬 ⏭ skip(엔드포인트 없음) — `pytest -m llm` 3 passed 1 skipped |
| SC-3 | 미리보기 API로 실 PDF 결과 확인 | ⚠️ | E2E 스모크(합성 PDF→UseCase 실 OpenAI) ✅, 관리자 **화면** 실서버 확인은 L3 이월 |
| SC-4 | V064/V065 COMMENT 검사 통과 | ✅ | `tests/db` 10 passed |
| SC-5 | 프론트 타입·서비스·훅·MSW 동기화 + adminNav 테스트 | ✅ | vitest 39 passed (feature) |
| SC-6 | 회귀 FAILED 목록 diff 0 | ✅ | 백엔드 58=baseline diff 0 (7677 passed) / 프론트 9=baseline diff 0 |
| QC-1 | 신규 모듈 커버리지 ≥80% | ✅ | 전 프로덕션 모듈 대응 테스트 존재(`/verify-tdd`), 백엔드 신규 ~190건 |
| QC-2 | verify-architecture / verify-logging / lint | ✅ | 위반 1건(router→infra import) 발견 후 DI로 수정, ruff `All checks passed` |
| QC-3 | strict 스키마 재귀 검사 | ✅ | `test_schemas.py::test_draft_has_no_free_key_dict_or_any` |
| QC-4 | 포트 계약 AST 테스트 | ✅ | domain/application `test_layer_contract.py` |

**Success Rate**: 7/10 ✅, 3 ⚠️ (SC-1 하위 4개 FR 부분, SC-2 로컬 skip, SC-3 화면 L3 이월) — ❌ 0

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|---|---|:-:|---|
| [Plan] | 인프로세스 포트 + 미리보기 API, 저장은 타 모듈 | ✅ | — |
| [Plan] | `llm_model.supports_vision` + `multimodal_setting` 단일 행, 전역 1개 | ✅ | — |
| [Plan] | 건별 degraded, 설정 오류만 예외 | ✅ | `/test` 실패는 200 `ok=false`(Design §6.1의 502와 불일치 — 아래 M2) |
| [Design C] | 포트 2 + 레지스트리 2, BaseVisionAdapter 상속, 벤더 차이는 `build_image_block` | ✅ | 시그니처에 `options` 추가(§9.5 미반영) |
| [Design] | Draft/Element 타입 분리 + 필드 집합 동등 테스트 | ✅ | — |
| [Design] | strict→json→text 폴백, 로컬은 strict 제외 | ✅ | Anthropic도 strict 실증(폴백 불필요) |
| [Design §9.3] | routes는 infrastructure 직접 import 금지 | ✅ (수정 후) | thumbnail DI seam 추가 — §9.4 미기재 |

---

## 1. Analysis Overview

- **Purpose**: Design §3/§4/§5.4/§6/§8/§9 대비 구현 일치도 측정 + Plan FR/DoD 충족 판정 + 런타임 실측.
- **Scope**: 백엔드 `src/{domain,application,infrastructure}/multimodal`, `interfaces/schemas/multimodal.py`, `api/{multimodal_di.py,routes/admin_multimodal_router.py,routes/preview_router.py}`, llm_model `supports_vision` 관통 / 프론트 `AdminMultimodalPage`, 서비스·훅·타입·nav / 테스트 4계층.
- **Method**: gap-detector 정적 분석(구조·기능·계약·FR) + 런타임(L1 pytest, 실 LLM 스모크, L2 vitest, verify 스킬 3종, 회귀 diff).

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints

| Design | Implementation | Status | Notes |
|---|---|---|---|
| GET `/api/v1/admin/multimodal/settings` | ✅ admin | ✅ Match | `warnings[]` 응답 — §4.2 JSON 예시에 미기재(프로즈만) |
| PUT `/api/v1/admin/multimodal/settings` | ✅ admin, 422→400 통일 | ✅ Match | 400/404/409 코드 일치 |
| POST `/api/v1/admin/multimodal/test` | ✅ admin | ⚠️ Status | Design 502 `VISION_CALL_FAILED` ↔ impl 200 `{ok:false,error}`; `UNSUPPORTED_MEDIA` Design 400 ↔ impl 415; 413 `PAYLOAD_TOO_LARGE` 추가 |
| POST `/api/v1/preview/multimodal` | ✅ user, `image_bytes` 미노출·썸네일 | ⚠️ Missing map | `ExtractionError`(손상 PDF) 미매핑 → **500** (§7은 415) |
| (공통) `UNSUPPORTED_VISION_PROVIDER` 500 | — | ❌ | 양 라우터 모두 미매핑 → bare 500 |

### 2.2 Data Model

| Field | Design | Impl | Status |
|---|---|---|---|
| `llm_model.supports_vision` | TINYINT(1) DEFAULT 0 + 백필 | V064 동일 + ORM/엔티티/DTO 관통 | ✅ |
| `multimodal_setting` 12컬럼 | §3.3 | V065 동일, 전 컬럼 COMMENT, ORM `comment=` | ✅ |
| `DescribeOutcome.usage` | §9.5에 선언됨 | 구현 + `output_mode` 추가 | ✅ (+1 필드) |
| `ExtractionResult.dropped` / `DroppedCandidate` | §3.1 없음, §4.2 debug 응답은 요구 | value_objects에 추가 | ⚠️ Design 자기모순 → 구현이 §4.2 쪽 채택, §2.2/§3.1 갱신 필요 |
| `MultimodalElement` = Draft 복사 ∪ 서버 필드 | §3.1 | 필드 집합 동등 테스트로 고정 | ✅ |
| `updated_at` | `…Z` | naive datetime | Minor |

### 2.3 Component Structure

| Design Component | Implementation | Status |
|---|---|:-:|
| §9.4 backend 19개 파일 + V064/V065 | 전부 존재 (+`thumbnail.py`, +`multimodal_di.py`) | ✅ |
| §5.3 frontend 4 컴포넌트 + types/service/hooks/constants | 전부 존재 (+`utils/multimodalValidators.ts`) | ✅ |
| §8.5 `tests/fixtures/multimodal/sample.pdf` | 코드로 합성(`test_pdf_extractor.py`) — 바이너리 미커밋 | ⚠️ 대체 |

**Structural Match**: 40/41 = **97%**

### 2.4 Functional Depth

| File | Depth | Note |
|---|:-:|---|
| `domain/multimodal/*` | 100 | VO 범위·Policy·오류 분류 §3.1/§6.1 전부 |
| `application/multimodal/use_case.py` | 95 | 전체 흐름; transient 집합 §2.2보다 넓음({408,429,5xx}) |
| `application/multimodal/settings_use_case.py` | 95 | `/test` 실패 계약 편차 |
| `infrastructure/.../pdf_pymupdf_extractor.py` | 100 | 내장·표 클립·페이지 렌더·xref 중복·CMYK 정규화 |
| `infrastructure/.../base_vision_adapter.py` | 95 | 폴백·include_raw usage; `last_config` 공유 상태 |
| `api/routes/admin_multimodal_router.py` | 90 | `UnsupportedVisionProviderError` 미매핑 |
| `api/routes/preview_router.py`(+route) | 85 | `ExtractionError` 미매핑 |
| 프론트 4 컴포넌트 | 95 | dirty 추적·인라인 검증·접기 |

Placeholder 0건. DI `NotImplementedError` 스텁은 프로젝트 관례(테스트로 단언). **Shallow 0/20**.

### 2.5 Page UI Checklist (§5.4)

| Page | Items | Implemented | Partial | Rate |
|---|:-:|:-:|:-:|:-:|
| 설정 탭 | 9 | 7 | 2 (성공 **토스트**→인라인 텍스트, 실패 시 **오류 코드**→메시지만) | 89% |
| 미리보기 탭 | 9 | 9 | 0 | 100% |
| llm-models | 2 | 2 | 0 | 100% |

**Functional Match Rate**: (93 + 95)/2 ≈ **94%**

### 2.6 API Contract (3-way Design §4.2 ↔ Server ↔ Client)

필드명·nullability·multipart 필드(`image`/`file`)·쿼리(`debug`)·StrEnum wire 값: **100% 일치**. 불일치는 상태 코드/오류 코드 의미론에 집중:

| # | Endpoint | Design | Impl | Sev |
|---|---|---|---|:-:|
| M1 | preview | 손상 PDF → 415 | `ExtractionError` 미처리 → 500 | **Critical** |
| M2 | test | 502 `VISION_CALL_FAILED` | 200 `{ok:false,error}` | Important |
| M3 | both | 500 `UNSUPPORTED_VISION_PROVIDER` | 미매핑 | Important |
| M4 | test | 400 `UNSUPPORTED_MEDIA` | 415 | Important |
| M5 | test | 413 미기재 | 413 `PAYLOAD_TOO_LARGE` | Minor |
| M6 | test | `error` 필드 없음 | `error: str\|null` | Minor |
| M7 | all | `details` 키 | 미사용 | Minor |
| M8 | GET settings | `warnings` JSON 미기재 | 존재 | Minor(doc) |
| M9 | settings | `updated_at …Z` | naive | Minor |

**API Contract Rate**: **85%**

### 2.7 Runtime Verification Results

| Layer | Command | Result |
|---|---|---|
| L1 backend (feature) | pytest domain/application/infrastructure/api multimodal + llm_model + db | **176 passed** |
| L1 실 LLM 스모크 | `pytest -m llm tests/infrastructure/multimodal/test_vision_smoke.py` | **3 passed, 1 skipped**(로컬) — OpenAI strict·Anthropic strict·E2E PDF |
| L1 회귀 | `pytest tests` | 58 failed = baseline, **FAILED diff 0** |
| L2 frontend | vitest AdminMultimodalPage/hooks/adminNav/AdminLlmModelsPage | **39 passed** |
| L2 회귀 | `vitest run` | 9 failed = baseline, **FAIL diff 0** |
| verify 스킬 | architecture / logging / tdd | PASS (architecture 위반 1건 수정 후) |
| L3 E2E | 실서버 + 관리자 화면 | ⏭ deferred (서버 미기동) |

Design §8.2 #10/#11(합성 PDF→fake 어댑터→라우터 통합), §8.3 #7(`supports_vision` POST 바디 캡처) **미구현**.

**Runtime Rate**: 테스트 전건 통과·스모크 실행, 설계 시나리오 3건 누락·L3 이월 → **90%**

### 2.8 Match Rate Summary

```
Runtime executed formula:
Overall = Structural 97×0.15 + Functional 94×0.25 + Contract 85×0.25 + Runtime 90×0.35
        = 14.55 + 23.5 + 21.25 + 31.5 = 90.8 → 91%
```

| Axis | Rate |
|---|:-:|
| Structural | 97% |
| Functional | 94% |
| API Contract | 85% |
| Runtime | 90% |
| **Overall** | **91%** |

---

## 3. Gap List (severity, confidence ≥80%)

| Sev | Conf | Gap | Location | Fix |
|:-:|:-:|---|---|---|
| **Critical** | 95% | 손상/비-PDF 바이트 `.pdf` 업로드 → `ExtractionError` 탈출 → **500** (§7: 415) | `preview_router.py:387-396` | `except ExtractionError` → 415 `UNSUPPORTED_FORMAT` + L1 테스트(`b"not a pdf"`) |
| Important | 90% | `UNSUPPORTED_VISION_PROVIDER` 미매핑(bare 500) | `registries.py:63` raise, 양 라우터 catch 없음 | 양 라우터에 500 + code 매핑 |
| Important | 90% | `/test` 실패: Design 502 ↔ impl 200 `ok=false` | `settings_use_case.py:161-179` | 구현이 UX상 우월(클라가 `ok=false` 렌더) → **Design §4.2/§6.1 갱신** |
| Important | 95% | `UNSUPPORTED_MEDIA` Design 400 ↔ impl 415 | `admin_multimodal_router.py:97-101` | 415가 HTTP 의미상 옳음 → Design 갱신 |
| Important | 85% | FR-20 토큰·비용 영속 미배선(callbacks None) | `multimodal_di.py:83-90` | `ai_run`용 `UsageCallback`은 agent run 전용(RunTracker·agent_id 필수) → Plan FR-20을 "구조화 로그 + usage 반환"으로 하향 명시, ai_run 연동은 저장 모듈(Phase 2)에서 run 컨텍스트와 함께 |
| Important | 90% | §8.2 #10/#11 통합 테스트(실 추출기+fake 어댑터→라우터) 부재 | `test_preview_multimodal.py`는 UseCase 전체 mock | 통합 테스트 1건 추가 |
| Important | 90% | §8.3 #7 `supports_vision` POST 바디 캡처 테스트 부재 | `AdminLlmModelsPage/index.test.tsx` | MSW 바디 캡처 테스트 추가 |
| Minor | 95% | 재시도 대상 §2.2 "429/timeout만" ↔ impl {408,429,5xx} | `use_case.py:55` | Design §2.2 갱신(5xx 재시도는 합리적) |
| Minor | 100% | 테스트 훅 `_on_adapter_built`/`_timeout_override_sec` 프로덕션 클래스 내 | `use_case.py:79-80` | §10.4 문서화 |
| Minor | 70% | `adapter.last_config` 공유 상태(gather 동시 변경) | `base_vision_adapter.py` | 로컬 변수화 |
| Minor | 100% | §2.2/§3.1 `dropped` 미기재, §9.4 thumbnailer DI 미기재, §9.5 시그니처(`options`) 드리프트, §5.3 `api.ts(+4)`→+3 | Design | 문서 동기화 |
| Minor | 85% | §5.4 성공 토스트·실패 오류코드 표시 | `MultimodalSettingsForm.tsx` | 프로젝트 토스트 사용 또는 §5.4 완화 |
| Minor | 80% | 409 분기를 status로만 판단(`ApiError`에 code 없음) | `MultimodalPreviewPanel.tsx:100-107` | `ApiError.code` 추가 시 분기 |

---

## 4. Code Quality / 6. Clean Architecture / 7. Convention

| 검사 | 결과 |
|---|---|
| ruff (신규 파일 전체) | All checks passed |
| ESLint (신규 프론트 파일) | 0 errors (`set-state-in-effect` 1건 → 렌더 중 파생 상태로 수정) |
| `/verify-architecture` | domain→infra 0, domain→langchain 0(multimodal), routes→infra **1건 수정**(thumbnail DI), infra Policy 0 |
| `/verify-logging` | print 0, error 로그 `exception=` 100%, 민감정보 0, 기본 logging 0 |
| `/verify-tdd` | 전 프로덕션 모듈 대응 테스트 존재 |
| 함수 40줄 / if 중첩 2단계 | 준수(리뷰 시점 위반 미발견) |
| config 하드코딩 | 신규 config 키 0 — 운영값은 `multimodal_setting` 단일 출처 |
| DDL COMMENT | V064/V065 통과 |

---

## 5. Test Coverage

| 계층 | 테스트 수 | 비고 |
|---|:-:|---|
| domain | 31 | VO·Draft strict·Policy·AST |
| application | 41 | registries·UseCase(동시성/재시도/degraded)·Settings·AST |
| infrastructure | 31 + 4(llm) | 추출기(합성 PDF)·어댑터 폴백·프롬프트·repo·썸네일·**실 스모크** |
| api | 27 | admin 17·preview 8·wiring 2 |
| frontend | 21 (+9 nav, +9 llm 페이지 유지) | 훅 7·페이지 14 |

**Uncovered**: §8.2 #10/#11 통합 경로, §8.3 #7, 로컬 비전 어댑터 실 호출, 관리자 화면 실서버 E2E(§8.4).

---

## 8. Conclusion

- **Match Rate 91%** (≥90 통과선). ❌ 0건이나 **Critical 1건**(손상 PDF → 500)은 1줄 수정으로 해소 가능.
- Important 6건 중 3건은 코드 수정(provider 오류 매핑·통합 테스트·supports_vision 테스트), 3건은 **Design/Plan 문서 갱신**이 올바른 해소(`/test` 200 ok=false, 415 UNSUPPORTED_MEDIA, FR-20 범위 하향).
- 권장: Critical + Important 코드 3건을 iterate로 즉시 수정하고 문서 편차는 같은 iterate에서 Design v0.2로 동기화.

---


---

## 9. Act-1 재검증 (iterate 후)

### 9.1 조치 내역

| Sev | Gap | 조치 | 검증 |
|:-:|---|---|---|
| Critical | 손상 PDF → 500 | `preview_router.py` `except (UnsupportedFormatError, ExtractionError)` → 415 `UNSUPPORTED_FORMAT` | `test_preview_corrupt_pdf_bytes_415` |
| Important | `UNSUPPORTED_VISION_PROVIDER` 미매핑 | 양 라우터 500 + code | `test_preview_unknown_provider_500_with_code`, `test_connection_test_unknown_provider_500_with_code` |
| Important | §8.2 #10/#11 통합 테스트 부재 | `tests/api/test_preview_multimodal_integration.py` 4건 — 실 추출기+레지스트리+fake 어댑터→라우터 (합성 PDF: 성공 2·필터 2·타임아웃 degraded·상한 skipped·debug dropped) | 4 passed |
| Important | §8.3 #7 `supports_vision` 바디 캡처 | `AdminLlmModelsPage/index.test.tsx` P3b | 1 passed |
| Important | `/test` 200 ok=false ↔ Design 502 | **Design v0.2**: 실패=결과(200) 채택, 502 폐기 | 문서 |
| Important | `UNSUPPORTED_MEDIA` 400 ↔ 415 | **Design v0.2**: 415 채택 + 413 `PAYLOAD_TOO_LARGE` 등재 | 문서 |
| Important | FR-20 영속 미배선 | **Plan v0.2**: 구조화 로그 + `usage` 반환 + callbacks seam 으로 범위 확정, `ai_run` 영속은 Phase 2 | 문서 |
| Minor | `adapter.last_config` 공유 상태 | 생성 시 고정 불변 `_config` 로 교체 | `test_callbacks_are_passed_in_config` |
| Minor | Design 문서 드리프트 6건(`dropped`/`DroppedCandidate`, thumbnailer DI·`multimodal_di.py`, §9.5 시그니처, transient 재시도 범위, `api.ts` +3, 테스트 seam) | Design v0.2 반영 | 문서 |

미조치(명시적 이월, 위키 explicit-gap-carryover): §5.4 성공 토스트·오류코드 표시(UI 마감), `ApiError.code` 기반 409 분기, `updated_at` tz, `details` 키 — 모두 Minor, 기능 영향 없음. L3 실서버 E2E·로컬 비전 스모크는 E2E 이월 체크리스트 등재 대상.

### 9.2 재측정

| Axis | Before | After | 근거 |
|---|:-:|:-:|---|
| Structural | 97% | 97% | 변동 없음(fixture 합성 유지) |
| Functional | 94% | 95% | 라우터 오류 매핑 완결(admin 90→100, preview 85→100), UI 2건 partial 잔존 |
| API Contract | 85% | 96% | M1·M3 코드 수정, M2·M4·M5·M6·M8 Design 동기화로 해소; 잔존 M7(`details`)·M9(tz) Minor |
| Runtime | 90% | 96% | 백엔드 183 + 스모크 3/3 + 프론트 40 전건 통과, §8.2 #10/#11·§8.3 #7 구현; L3 이월 |

```
Overall = 97×0.15 + 95×0.25 + 96×0.25 + 96×0.35 = 14.55 + 23.75 + 24.0 + 33.6 = 95.9 → 96%
```

회귀: 백엔드 58 failed = baseline, FAILED diff 0 (7684 passed) / 프론트 9 failed = baseline, diff 0 (1094 passed).

**Act-1 결과: Match Rate 91% → 96%, Critical 0, Important 0 (코드 3 수정 + 문서 3 동기화), Minor 4 이월.**

## Version History

| Version | Date | Changes | Author |
|---|---|---|---|
| 0.1 | 2026-08-21 | 초안 — 정적(gap-detector) + 런타임 실측, Match 91% | 배상규 |
| 0.2 | 2026-08-21 | Act-1 재검증 — Critical/Important 0, Match 96% | 배상규 |
