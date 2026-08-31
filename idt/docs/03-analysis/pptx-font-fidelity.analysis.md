# pptx-font-fidelity Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: idt v0.x (blueprint 모듈)
> **Analyst**: 배상규
> **Date**: 2026-08-24
> **Design Doc**: [pptx-font-fidelity.design.md](../02-design/features/pptx-font-fidelity.design.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 생성 PPTX의 폰트·스타일이 골든 샘플과 달라 산출물을 실무 보고에 쓸 수 없음 |
| **WHO** | P2 (KB 운영자/에이전트 소유자) |
| **RISK** | python-pptx가 `a:ea` 설정 API 미제공 → lxml 직접 조작, 렌더러 단위 테스트로 통제 |
| **SUCCESS** | 폰트명이 실존 패밀리명이고 `a:latin`=`a:ea`, 소제목·헤더가 원본 계층대로 출력, 기존 테스트 통과 |
| **SCOPE** | 렌더러 + FontCatalog + SlotContent 스키마 + 슬롯 작성 프롬프트 |

---

## Strategic Alignment Check

### 핵심 문제 해결 여부

| 요소 | 기대 | 구현 상태 |
|------|------|:---------:|
| Core Problem (WHY) | 골든 샘플 대비 폰트·스타일 깨짐 제거 | ✅ 해결 — 골든 샘플 재생성 실측으로 4개 원인 모두 해소 확인 |
| Target User (WHO) | P2가 산출물을 그대로 보고에 사용 | ✅ 해결 — 폰트 대체 없이 원본 서체·계층 재현 |
| Value Proposition | "원본 스타일 재현" 신뢰도 확보 | ✅ 전달 |

**실측 근거** (골든 샘플 재생성, `samples/golden_sample_report.pdf` → PPTX 재파싱):

```
font_mapping: {'Malgun Gothic Bold': 'Malgun Gothic', 'Malgun Gothic Regular': 'Malgun Gothic'}
폰트 경고: 없음

slide 1  34pt bold #FFFFFF  latin=ea=cs=Malgun Gothic | 2026년 3분기 여신 리스크 보고
slide 2  24pt bold #1F3A5F  latin=ea=cs=Malgun Gothic | 4. 향후 대응 방안       ← 섹션 헤더
         16pt bold #1F3A5F  latin=ea=cs=Malgun Gothic | 심사 기준 강화           ← 소제목(FR-03)
         13pt      #222222  latin=ea=cs=Malgun Gothic | • 제조·도소매 심사 강화
slide 3  24pt bold #1F3A5F  latin=ea=cs=Malgun Gothic | 2. 연체율 추이 분석     ← 폴백 복원(FR-04)
```

원본 PDF의 값(24pt #1F3A5F 헤더 / 13pt #222222 본문 / Malgun Gothic)과 일치한다.

### Success Criteria Status (Plan §4.1)

| # | 기준 | 상태 | 근거 |
|---|------|:----:|------|
| SC-1 | 타입페이스가 실존 패밀리명이고 `a:latin`=`a:ea` | ✅ Met | 실측 전 run에서 latin=ea=cs="Malgun Gothic"; `test_golden_sample_fidelity.py::test_fr02_every_run_sets_east_asian_typeface` |
| SC-2 | 소제목이 h3 스타일로 렌더 | ✅ Met | `pptx_renderer.py:313` `_heading_line`; 실측 16pt bold #1F3A5F |
| SC-3 | 비표지 슬라이드에 24pt 헤더 존재 | ✅ Met | `pptx_renderer.py:152` `_with_title_fallback`; `test_fr04_every_body_slide_has_a_header_title` |
| SC-4 | FR-01~05 단위 테스트 작성·통과 | ⚠️ Partial | 설계 §8.2 시나리오 18건 중 **17건 자동화** — #18(스키마 하위호환) 미작성 |
| SC-5 | 기존 테스트 회귀 없음 | ✅ Met | 전체 7,966 passed / 58 failed, **blueprint 실패 0건**; 실패 58건은 전부 HEAD 상태 파일의 기존 실패 |

**Success Rate**: 4.5 / 5 (SC-4만 부분 충족)

### Decision Record Verification

| 출처 | 결정 | 준수 | 비고 |
|------|------|:----:|------|
| [Plan] | 폰트 전략 = 정규화 (FONT_DIR 구성은 범위 밖) | ✅ | `src/config.py` 무변경 (기존 diff는 선행 golden-sample-blueprint 것) |
| [Plan] | 소제목 = heading 필드 (SlotKind 신설 안 함) | ✅ | `SlotKind` 열거형 변경 없음 |
| [Design] | 정규화 규칙은 domain 정책 | ✅ | `policies.py:645` `FontFamilyPolicy` |
| [Design] | oxml 조작은 renderer 헬퍼 1곳으로 격리 | ✅ | `grep`상 `src/` 전체에서 oxml 사용 파일은 `run_fonts.py` 단 하나 |
| [Design] | domain은 pptx/lxml 미참조 (Thin DDD) | ✅ | `src/domain/`에 pptx/lxml import 0건; layer contract 테스트 4건 통과 |

---

## 1. Analysis Overview

### 1.1 목적

설계 문서가 규정한 4개 요구사항(FR-01~04)과 하위호환(FR-05)이 실제 코드로 구현됐는지, 그리고 골든 샘플 재현이라는 본래 목적을 달성했는지 검증한다.

### 1.2 범위

- Design: `docs/02-design/features/pptx-font-fidelity.design.md`
- 구현 경로: `src/domain/blueprint/`, `src/infrastructure/blueprint/`, `src/application/blueprint/`
- 분석일: 2026-08-24

---

## 2. Gap Analysis

### 2.1 Structural Match — 설계 명시 파일/심볼

| 설계 §9.1 항목 | 구현 위치 | 상태 |
|----------------|-----------|:----:|
| `FontFamilyPolicy` (domain) | `policies.py:645` | ✅ |
| `FontCatalog` 정규화 경유 | `fonts.py` (suggest / propose_mapping / _normalized_or_none) | ✅ |
| `run_fonts.set_run_font` (신규 파일) | `renderer/run_fonts.py:17` | ✅ |
| 렌더러 헬퍼 적용 | `pptx_renderer.py:366`(텍스트박스), `:395`(표 셀) | ✅ |
| `SlotContent.heading` | `value_objects.py` (기본값 None) | ✅ |
| `SlotContentDraft.heading` | `schemas.py` (Optional) | ✅ |
| heading 렌더 | `pptx_renderer.py:292` `_bullets`, `:313` `_heading_line` | ✅ |
| 타이틀 폴백 | `pptx_renderer.py:152` `_with_title_fallback` | ✅ |
| 빈 슬라이드 스킵 | `generation_use_case.py:144` `_drop_empty`, `:343` `_has_renderable` | ✅ |
| 프롬프트 heading 안내 | `prompts_generation.py` `_WRITE_SYSTEM` | ✅ |

**Structural Match Rate: 10/10 = 100%**

### 2.2 Functional Depth — 요구사항별 구현 깊이

| FR | 요구사항 | 깊이 | 근거 |
|----|----------|:----:|------|
| FR-01 | 폰트명 정규화 | 100 | 서브셋 프리픽스 제거 + 접미사 토큰 반복 제거 + 전부-토큰 예외 + bold 힌트 반환. 미설치 시에도 family 채택(`_normalized_or_none`) |
| FR-02 | latin/ea/cs 동일 폰트 | 100 | `set_run_font`가 3슬롯 원자적 설정, 중복 요소 미생성. 텍스트박스·표 셀 양쪽 적용 |
| FR-03 | heading → h3 소제목 | 100 | `_Line` NamedTuple 도입으로 문단별 스타일 지원, `_styled_textbox` 분리. TOC 패턴은 기존 규칙 유지 |
| FR-04 | 타이틀 폴백 + 빈 슬라이드 스킵 | 100 | 표지 제외 조건 명시, 폴백 불가 시 UseCase가 warning 기록 |
| FR-05 | 하위호환 | 100 | heading Optional 기본 None; `SlotContent`가 `serialization.py`에 미등장(직렬화 대상 아님) — 설계 §3.4 가정 코드로 확증 |

**Shallow(60점 미만) 파일: 0건.** placeholder·TODO·미구현 스텁 없음.

**Functional Match Rate: 100%**

### 2.3 API Contract

이번 변경의 HTTP 계약 영향은 **없음**이 확인됐다.

| 검증 항목 | 결과 |
|-----------|------|
| `heading`이 `interfaces/schemas/blueprint.py`에 노출되는가 | ❌ 미노출 |
| `heading`이 `api/routes/admin_blueprint_router.py`에 노출되는가 | ❌ 미노출 |
| `/fonts` 관리 API 응답 형태 변경 | 없음 (`FontsResponse` 무변경) |
| 프론트 타입 동기화 필요 여부 | **불필요** |

`SlotContent`는 LLM ↔ 렌더러 사이의 내부 VO이며 응답 스키마에 포함되지 않는다. Plan §6.2에서 "확인 필요"로 남긴 두 항목(직렬화 하위호환, 프론트 동기화)이 모두 해소됐다.

**Contract Match Rate: 해당 없음 → 감점 없음 (100%)**

### 2.4 설계 §8.2 테스트 시나리오 매핑

| # | 설계 시나리오 | 실제 테스트 | 상태 |
|---|---------------|-------------|:----:|
| 1~3 | 정규화 Regular/Bold/ExtraBold Italic | `test_normalize_strips_subfamily_tokens` (파라미터 6종) | ✅ |
| 4 | PDF 서브셋 프리픽스 | `test_normalize_removes_pdf_subset_prefix` | ✅ |
| 5 | 토큰만으로 구성된 이름 | `test_normalize_keeps_name_made_only_of_tokens` | ✅ |
| 6 | 미설치 + 정규화 가능 | `test_propose_mapping_normalizes_subfamily_without_catalog` | ✅ |
| 7 | 미설치 + 정규화 불가 | `test_propose_mapping_warns_only_when_name_is_unchanged` | ✅ |
| 8 | 설치 폰트 매칭 | `test_suggest_matches_installed_font_after_normalization` | ✅ |
| 9 | set_run_font 3슬롯 | `test_sets_latin_ea_and_cs_to_same_typeface` | ✅ |
| 10 | 2회 호출 중복 없음 | `test_second_call_updates_without_duplicating_elements` | ✅ |
| 11 | heading h3 렌더 | `test_bullets_heading_is_rendered_as_h3_subheading` | ✅ |
| 12 | heading 없는 bullets | `test_bullets_without_heading_are_unchanged` | ✅ |
| 13 | TOC heading 무시 | `test_toc_pattern_ignores_heading` | ✅ |
| 14 | 타이틀 폴백 | `test_missing_title_content_falls_back_to_plan_title` | ✅ |
| 15 | 표 셀 ea | `test_table_cell_runs_also_set_east_asian_typeface` | ✅ |
| 16 | 공백 heading → None | `test_blank_heading_becomes_none` | ✅ |
| 17 | 빈 슬라이드 스킵 | `test_slide_without_any_renderable_content_is_skipped_with_warning` | ✅ |
| 18 | **heading 없는 LLM JSON 파싱 (하위호환)** | **없음** | ❌ |

**설계 대비 커버리지: 17/18 = 94.4%**

설계에 없던 추가 테스트 9건도 작성됐다: 전체 run ea 검증, 표지 제목 날조 방지, plan.title만 있는 슬라이드 보존, heading+bullets 문단 순서, 빈 이름 무시, 멱등성, alias_key, 그리고 골든 샘플 통합 검증 5건.

### 2.5 Runtime Verification (pytest)

> 이 기능은 HTTP 엔드포인트 변경이 없어 L1(curl)·L2/L3(Playwright)은 해당 없음. 백엔드 라이브러리 기능이므로 pytest 실행이 런타임 검증에 해당한다.

| 항목 | 결과 |
|------|------|
| blueprint 관련 테스트 | **235 passed / 0 failed** |
| 골든 샘플 §5.4 산출물 체크리스트 | **7/7 통과** (ea 3슬롯, 접미사 없음, 표 셀 ea, 헤더 존재, 소제목 스타일 등) |
| 전체 스위트 | 7,966 passed / 58 failed / 2 skipped |
| 회귀 여부 | **blueprint 실패 0건** — 58건은 전부 이번 변경과 무관 |

**기존 실패 58건 내역** (전부 HEAD 상태 파일, 미수정):

| 파일 | 건수 | 원인 |
|------|:----:|------|
| `test_pymupdf4llm_parser.py` | 21 | 파서 라이브러리 |
| `test_agent_builder_router_stream.py` | 9 | FastAPI 버전 드리프트 |
| `test_parent_child_retriever.py` | 7 | 리트리버 |
| `test_general_chat_router.py` | 7 | 라우터 |
| `test_run_agent_use_case_observability.py` | 5 | 관측성 |
| `test_collection_router_embedding.py` | 4 | 임베딩 |
| `test_ws_router_auth_context.py` | 2 | WS 인증 |
| `test_es_client.py` / `test_main_logging.py` / `test_main.py` | 각 1 | ES `http_auth` deprecation, `_IncludedRouter.path` 속성 제거 |

표본 확인한 오류 메시지(`AttributeError: '_IncludedRouter' object has no attribute 'path'`, `assert 'http_auth' not in {...}`, `assert 422 == 500`)는 모두 라이브러리 버전 변화에 따른 것으로 폰트·렌더링과 무관하다.

**Runtime Match Rate: 97%** (실행 결과는 전부 통과이나, 설계 시나리오 1건 미자동화를 반영)

### 2.6 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  100%                │
│  Functional Match Rate:  100%                │
│  Contract Match Rate:    100% (해당 없음)     │
│  Runtime Match Rate:      97%                │
│  ─────────────────────────────────────────── │
│  Overall Match Rate:      99%                │
│  = (100 × 0.15) + (100 × 0.25)               │
│    + (100 × 0.25) + (97 × 0.35)              │
├─────────────────────────────────────────────┤
│  ✅ Match:           10 항목 (100%)           │
│  ⚠️ Shallow:          0 항목                  │
│  ❌ Not implemented:  0 항목                  │
└─────────────────────────────────────────────┘
```

---

## 3. Code Quality

### 3.1 규칙 준수

| 규칙 (idt/CLAUDE.md) | 결과 |
|----------------------|------|
| 함수 40줄 초과 금지 | ✅ 위반 0건 — `generate`가 43줄이 되어 `_result` 헬퍼로 분리 |
| print() 금지 / logger 사용 | ✅ `_drop_empty`는 `logger.warning` 사용 |
| 명시적 타입 | ✅ `_Line` NamedTuple, `str \| None` 등 |
| config 하드코딩 금지 | ✅ 신규 env 없음 |
| lint (ruff check) | ✅ 변경 파일 전부 통과 |

### 3.2 Code Smells

발견된 스멜 없음. 리팩터링 성격의 변경 1건이 있다:

| 유형 | 위치 | 설명 | 심각도 |
|------|------|------|:------:|
| 구조 개선 | `pptx_renderer.py` `_textbox` | 단일 스타일 전제였던 함수를 `_styled_textbox`(문단별 스타일) 위로 얇게 재작성 — 기존 호출부 시그니처 유지 | 🟢 정보 |

### 3.3 보안

| 항목 | 결과 |
|------|------|
| LLM 출력(heading) 처리 | ✅ 데이터로만 렌더 — 마크업·지시 해석 없음 (기존 §7 원칙 유지) |
| 폰트명 정규화 | ✅ 문자열 치환만, 경로·명령 미사용 |
| 신규 외부 입력 / 인증·권한 변경 | ✅ 없음 |

---

## 5. Test Coverage

| 모듈 | 커버리지 | 미커버 라인 |
|------|:--------:|-------------|
| `renderer/run_fonts.py` | 100% | — |
| `infrastructure/blueprint/fonts.py` | 100% | — |
| `renderer/pptx_renderer.py` | 99% | L165 — `plan.title`까지 빈 경우의 폴백 포기 분기 |
| `application/.../generation_use_case.py` | 99% | L348 — IMAGE 슬롯 보유 패턴의 보존 분기 |
| `domain/blueprint/policies.py` | 98% | 미커버 10줄 전부 기존 `SlotContentPolicy` 코드. `FontFamilyPolicy`는 100% |

프로젝트 목표(80%)를 크게 상회한다. 이번에 추가한 코드 중 미커버는 방어적 분기 2줄뿐이다.

---

## 6. Clean Architecture Compliance

### 6.1 레이어 의존 검증

| 레이어 | 기대 의존 | 실제 | 상태 |
|--------|-----------|------|:----:|
| Domain (`policies`, `value_objects`, `schemas`) | 없음 (순수) | pptx/lxml import 0건 | ✅ |
| Infrastructure (`fonts`) | Domain only | `FontFamilyPolicy` 참조 | ✅ |
| Infrastructure (`run_fonts`, `pptx_renderer`) | Domain only | pptx + domain VO | ✅ |
| Application (`generation_use_case`) | Domain, Infrastructure | 기존과 동일 | ✅ |

**의존 위반 0건.** `tests/domain/blueprint/test_layer_contract.py`, `tests/application/blueprint/test_layer_contract.py` 4건 통과.

### 6.2 Architecture Score

```
┌─────────────────────────────────────────────┐
│  Architecture Compliance: 100%               │
├─────────────────────────────────────────────┤
│  ✅ 설계대로 배치:      10/10 심볼            │
│  ⚠️ 의존 위반:          0                    │
│  ❌ 잘못된 레이어:      0                    │
└─────────────────────────────────────────────┘
```

---

## 8. Overall Score

```
┌─────────────────────────────────────────────┐
│  Overall Score: 97/100                       │
├─────────────────────────────────────────────┤
│  Design Match:        99 points              │
│  Code Quality:        95 points              │
│  Security:           100 points              │
│  Testing:             94 points              │
│  Architecture:       100 points              │
│  Convention:         100 points              │
└─────────────────────────────────────────────┘
```

---

## 9. Recommended Actions

### 9.1 Important (권장)

| 우선순위 | 항목 | 위치 | 사유 |
|----------|------|------|------|
| 🟡 1 | 설계 §8.2 #18 테스트 추가 — heading 필드 없는 LLM JSON이 파싱되고 `heading=None`이 되는지 | `tests/domain/blueprint/test_schemas.py` | FR-05 하위호환의 유일한 자동화 공백. Do 단계에서 수동 확인만 했으므로 회귀를 잡아 줄 장치가 없다 |

### 9.2 Nice to have (백로그)

| 항목 | 위치 | 비고 |
|------|------|------|
| 미커버 방어 분기 2줄 테스트 | `pptx_renderer.py:165`, `generation_use_case.py:348` | 커버리지 99% → 100% |
| bullets `max_chars`에 heading 길이 합산 검토 | `policies.py` `_check_bullets` | 현재 heading은 글자수 제한에 미포함(기존 동작 보존). 소제목이 길면 박스 넘칠 가능성 |

---

## 10. 설계 문서 갱신 필요 항목

| 항목 | 설계 기술 | 실제 구현 | 조치 |
|------|-----------|-----------|------|
| "빈 슬라이드"의 정의 | 슬롯 내용이 전무하면 제외 | 타이틀 폴백이 있으므로 `plan.title`까지 비어야 제외 | 설계 §6.1 표 문구 보정 권장 |
| FR-05 직렬화 | "`serialization.py` 변경 없음 — Do에서 테스트로 재확인" | 확인 완료: `SlotContent`는 직렬화 대상 아님 | 확정 사항으로 기록 |
| `_textbox` 확장 방식 | "bullets 전용 조립 함수로 분리" | `_Line` + `_styled_textbox`로 일반화 (동작 동일) | 설계 §12.2 실제 구현으로 갱신 |

---

## 11. Next Steps

**Checkpoint 5 결정 (2026-08-24): 「그대로 진행」** — Match Rate 99%가 기준(90%)을 충족하므로 수정 없이 report 단계로 진행한다. §9.1의 테스트 공백 1건은 백로그로 이월한다.

- [x] Checkpoint 5 — 현 상태 수용
- [ ] (백로그) 설계 §8.2 #18 테스트 추가 — FR-05 하위호환 자동화 공백
- [ ] (백로그) 미커버 방어 분기 2줄 테스트
- [ ] 설계 문서 §6.1 / §12.2 문구 보정
- [ ] 완료 보고서 작성 (`/pdca report pptx-font-fidelity`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-24 | 최초 분석 — Match Rate 99%, 테스트 공백 1건 식별 | 배상규 |
