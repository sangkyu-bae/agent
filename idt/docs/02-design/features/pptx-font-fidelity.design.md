# pptx-font-fidelity Design Document

> **Summary**: 블루프린트 PPTX 생성물의 폰트(정규화 + 한글 ea 슬롯)·소제목 계층·헤더 폴백을 복원하는 설계 — Option C (Pragmatic Balance)
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: idt v0.x (blueprint 모듈)
> **Author**: 배상규
> **Date**: 2026-08-24
> **Status**: Draft
> **Planning Doc**: [pptx-font-fidelity.plan.md](../../01-plan/features/pptx-font-fidelity.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 생성 PPTX의 폰트·스타일이 골든 샘플과 달라 산출물을 실무 보고에 쓸 수 없음 |
| **WHO** | P2 (KB 운영자/에이전트 소유자) — 블루프린트로 보고서 PPTX를 생성하는 사용자 |
| **RISK** | python-pptx가 `a:ea` 설정 API를 제공하지 않아 lxml 직접 조작 필요 → 회귀 위험은 렌더러 단위 테스트로 통제 |
| **SUCCESS** | 골든 샘플 재생성 시 폰트명이 실존 패밀리명으로 기록되고(`a:latin`=`a:ea`), 소제목·헤더가 원본 계층대로 출력, 기존 테스트 전부 통과 |
| **SCOPE** | 렌더러(infrastructure) + FontCatalog + SlotContent 스키마(domain) + 슬롯 작성 프롬프트. 추출 파이프라인(크기·색 추출)은 변경 없음 |

---

## 1. Overview

### 1.1 Design Goals

1. **폰트 해석 가능성**: PPTX에 기록되는 타입페이스가 항상 "OS가 해석 가능한 패밀리명"이 되도록 정규화 (FR-01)
2. **한글 렌더 충실도**: 모든 텍스트 run의 `a:latin`·`a:ea`·`a:cs`가 동일 폰트로 설정 (FR-02)
3. **계층 재현**: 소제목(heading) → h3 스타일, 섹션 헤더 → 항상 출력 (FR-03/04)
4. **무해성**: 기존 저장 블루프린트·기존 테스트에 대한 완전 하위호환 (FR-05)

### 1.2 Design Principles

- 규칙(정규화)은 domain 정책의 순수 함수로 — I/O 없음, 단독 테스트 가능
- oxml(lxml) 조작은 infrastructure 렌더러 패키지의 헬퍼 1곳으로 격리
- LLM 출력 스키마 변경은 Optional 필드만 — 파싱 실패 시 기존 동작으로 degrade
- 렌더러는 데이터만 그린다 — 콘텐츠 보정(빈 슬라이드 스킵·경고)은 UseCase 책임 (기존 D5/§6.3 경계 유지)

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | 기존 파일 내 수정만 | 정책·oxml·heading 렌더 모듈 전부 분리 | 정규화=domain 정책, oxml=renderer 헬퍼 1개 |
| **New Files** | 0 | 3 | 1 |
| **Modified Files** | 7 | 7 | 7 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | Low (규칙이 infra에 커플링) | Low (변경 범위 큼) | Low (balanced) |

**Selected**: **Option C** — **Rationale**: Thin DDD 원칙(규칙은 domain, 어댑터는 infra)과 정합. 렌더러 40줄 함수 규칙상 oxml 조작 헬퍼 분리가 자연스러움. 버그수정 규모 대비 과도한 분리(B) 회피. (Checkpoint 3 사용자 확정)

### 2.1 Component Diagram

```
[extraction]                       [generation]
PDF/PPTX 샘플                      SlidePlanner ──► SlotWriter(LLM)
  │                                    │ SlidePlanDraft   │ SlideContentDraft(+heading)
  ▼                                    ▼                  ▼
extraction_use_case ──────► generation_use_case ──► PptxSlideRenderer
  │ propose_mapping                │ 빈 슬라이드 스킵+warning   │ _textbox/_style_cell
  ▼                                │ heading 매핑              ▼
FontCatalog (infra)                │                    run_fonts.set_run_font()  ← 신설
  │ suggest/propose_mapping        │                      ├ a:latin = name
  ▼                                │                      ├ a:ea    = name
FontFamilyPolicy (domain) ← 신설 규칙│                      └ a:cs    = name
  normalize("Malgun Gothic Regular")
    → "Malgun Gothic"
```

### 2.2 Data Flow

```
샘플 추출:  span.font("Malgun Gothic Bold")
  → FontFamilyPolicy.normalize → "Malgun Gothic"
  → FontCatalog.propose_mapping → font_mapping {"Malgun Gothic Bold": "Malgun Gothic"}
  → blueprint 저장

생성:  StyleTokens.fonts[role] (원본명) → ctx.font(role) (font_mapping 경유 → 정규화명)
  → set_run_font(run, name) → rPr에 latin/ea/cs 3슬롯 기록
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `FontCatalog` (infra) | `FontFamilyPolicy` (domain) | 매핑 제안 전 폰트명 정규화 |
| `pptx_renderer._textbox` / `_style_cell` | `renderer/run_fonts.py` (신설) | run 3슬롯 폰트 설정 |
| `generation_use_case` | `SlotContentDraft.heading` | LLM heading → `SlotContent.heading` 매핑 |
| `pptx_renderer._bullets` | `SlotContent.heading` | 소제목 문단 렌더 |
| `pptx_renderer._render_slide` | `SlideContent.plan.title` | title 슬롯 폴백 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# src/domain/blueprint/value_objects.py — 필드 1개 추가 (기본값으로 하위호환)
@dataclass(frozen=True)
class SlotContent:
    slot_id: str
    text: str | None
    bullets: tuple[str, ...] | None
    table: TableSpec | None
    chart: ChartSpec | None
    heading: str | None = None      # ★ 신규 — bullets 슬롯의 소제목 (FR-03)

# src/domain/blueprint/schemas.py — LLM 출력 Draft (Optional, 기본 None)
class SlotContentDraft(_Strict):
    slot_id: str
    text: str | None
    bullets: list[str] | None
    table: TableDraft | None
    chart: ChartDraft | None
    heading: str | None = None      # ★ 신규
```

### 3.2 FontFamilyPolicy (domain 정책 — 신규 규칙)

```python
# src/domain/blueprint/policies.py 에 추가 (순수 함수, I/O 없음)
class FontFamilyPolicy:
    """PDF/PPTX 추출 폰트명 → OS 해석 가능한 패밀리명 정규화 (FR-01).

    규칙 (순서대로):
    1. PDF 서브셋 프리픽스 제거: "ABCDEF+MalgunGothic" → "MalgunGothic"
    2. 뒤쪽 서브패밀리 토큰 반복 제거 (case-insensitive, 공백/하이픈 구분):
       regular|bold|italic|oblique|light|thin|medium|semibold|demibold|
       extrabold|black|heavy|semilight|condensed
       예: "Malgun Gothic Semilight Italic" → "Malgun Gothic"
    3. 전부 제거되어 빈 문자열이 되면 원본 유지 (예: 폰트명이 "Black"뿐인 경우)
    4. 결과와 함께 bold 힌트 반환: 제거된 토큰에 bold 계열 포함 여부

    @staticmethod
    def normalize(name: str) -> tuple[str, bool]:  # (family, bold_hint)
```

- **bold_hint 용도**: v1은 렌더러가 role 기반 bold(제목=True)를 이미 결정하므로 렌더에는 미사용. `font_mapping` 값에는 family만 기록. (Plan 리스크 "세미볼드 표현 손실" 수용)
- **camelCase 분리 보정**: "MalgunGothicBold" 같은 무공백 명칭은 토큰 경계가 없어 2번 규칙 미적용 → `_norm()` 비교키에서 접미사 제거를 함께 수행 (`_strip_suffix_tokens(key)`)해 alias 매칭엔 걸리도록 함. family 문자열 자체는 원형 유지.

### 3.3 FontCatalog 변경 (infra)

```
suggest(source_font):
  family, _ = FontFamilyPolicy.normalize(source_font)
  key = _norm(family)                       # ← 기존: _norm(source_font)
  1) key ∈ installed(norm)      → 설치 폰트명
  2) _FAMILY_ALIASES[key] 계열  → 계열 후보 (기존 로직, bold 분기 제거)
  3) None

propose_mapping(source_fonts):
  target = suggest(f)
        or (family if family != f else None)   # ★ 미설치라도 정규화됐으면 family 채택
        or f or default
  warning 은 "정규화도 매핑도 안 된" 경우에만 기록
```

- `_FAMILY_ALIASES` 키 매칭 전 접미사 제거로 `"malgungothicregular"` → `"malgungothic"` 매칭 가능
- 결과 예: `{"Malgun Gothic Regular": "Malgun Gothic", "Malgun Gothic Bold": "Malgun Gothic"}`

### 3.4 직렬화 하위호환 (FR-05)

- `SlotContent`는 DB에 직렬화되지 않음(블루프린트만 저장, 슬라이드 내용은 휘발) → `serialization.py`는 **변경 없음**. Do 단계에서 SlotContent 직렬화 부재를 테스트로 재확인만 한다.
- 기존 저장 블루프린트의 `font_mapping`은 옛 폰트명 그대로 유지 — 재추출 전까지는 기존 동작(경고 포함). 마이그레이션은 범위 외.

---

## 4. API Specification

REST API 변경 없음. `heading`은 LLM ↔ 서버 내부 스키마(`SlotContentDraft`)에만 추가되며 HTTP 응답에 노출되지 않는다 (blueprint 조회 응답은 patterns/style만 포함 — SlotContent 미노출 확인됨). → 프론트 타입 동기화 불필요. `/fonts` 관리 API 응답 형태 불변.

---

## 5. UI/UX Design

해당 없음 (백엔드 전용). 산출물 검증 관점의 "Page UI Checklist"를 §5.4에 PPTX 슬라이드 체크리스트로 대체 정의한다.

### 5.4 산출물 검증 체크리스트 (Gap Detector 용)

#### 생성 PPTX (골든 샘플 재생성 기준)

- [ ] 모든 텍스트 run rPr: `<a:latin>`·`<a:ea>`·`<a:cs>` 3슬롯 존재, 타입페이스 동일
- [ ] 타입페이스 값에 `Regular`/`Bold` 등 서브패밀리 접미사 미포함
- [ ] 표지 제외 모든 콘텐츠 슬라이드에 h2(24pt) 헤더 타이틀 텍스트박스 존재
- [ ] heading이 있는 bullets 슬롯: 첫 문단이 h3 크기·heading 폰트·bold·primary 색
- [ ] heading 문단과 bullets 사이 시각 구분(문단 간격) 존재
- [ ] 내용 전무 슬라이드 미생성 + warnings에 스킵 사유 기록
- [ ] 표 셀 폰트도 ea 슬롯 설정 (…`_style_cell` 경유 확인)

---

## 6. Error Handling

### 6.1 오류/저하(degraded) 시나리오

| 시나리오 | 처리 | 계층 |
|----------|------|------|
| LLM이 heading 필드 누락/None | 기존 bullets 동작 (소제목 없음) — 오류 아님 | schemas (Optional) |
| LLM이 빈 문자열 heading | `heading=None` 취급 (strip 후 빈 값 무시) | generation_use_case 매핑 |
| title 슬롯 내용 없음 (비표지) | `plan.title`로 폴백 렌더 | renderer `_render_slide` |
| `plan.title`도 빈 값 | 타이틀 미출력 (기존 동작) + UseCase warning | use case |
| 슬라이드 전체 슬롯 내용 전무 (비표지·비이미지) | 렌더 대상에서 제외 + `warnings` 기록 | use case `_write_all` 후 필터 |
| sizes에 h3 없음 (`StyleTokens.size("h3")` 폴백) | 기존 size() 폴백 체인 그대로 사용 (TOC와 동일 경로) | domain StyleTokens |
| rPr oxml 조작 실패 (예외) | 발생 시 해당 run은 latin만 설정된 상태로 두지 않는다 — 헬퍼는 원자적으로 3슬롯 설정, 예외는 상위 전파(스택 트레이스 로깅 규칙 준수) | renderer 헬퍼 |

### 6.2 로깅

- 빈 슬라이드 스킵: `logger.warning("blueprint.render slide skipped — no renderable content", slide_index=...)` + PresentationResult.warnings
- 폰트 미정규화·미설치: 기존 `"font '{f}' not installed — kept as-is"` 경고 유지 (정규화 성공 시엔 미발생)

---

## 7. Security Considerations

- [x] LLM 출력 heading은 데이터로만 렌더 (기존 §7 원칙 — 마크업/지시 해석 없음)
- [x] 폰트명 정규화는 문자열 치환만 — 경로/명령 미사용
- [x] 신규 외부 입력 없음, 인증/권한 변경 없음

---

## 8. Test Plan

> 백엔드 전용 — pytest 단위/통합 테스트로 구성 (L2/L3 Playwright 해당 없음). TDD: 테스트 먼저 작성.

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1: 단위 (domain) | `FontFamilyPolicy.normalize` | pytest | Do |
| L1: 단위 (infra) | `FontCatalog.suggest/propose_mapping` 정규화 경유 | pytest | Do |
| L1: 단위 (infra) | `run_fonts.set_run_font` XML 3슬롯 검증 | pytest + lxml | Do |
| L1: 단위 (infra) | 렌더러 heading/타이틀 폴백 출력 검증 | pytest + python-pptx 재파싱 | Do |
| L1: 단위 (app) | heading 매핑·빈 슬라이드 스킵 + warning | pytest | Do |
| L4: 통합 | 골든 샘플 재생성 충실도 | `tests/integration/blueprint/test_golden_sample_fidelity.py` 확장 | Check |

### 8.2 L1: 단위 테스트 시나리오

| # | Target | Test Description | Expected |
|---|--------|-----------------|----------|
| 1 | FontFamilyPolicy | `"Malgun Gothic Regular"` | `("Malgun Gothic", False)` |
| 2 | FontFamilyPolicy | `"Malgun Gothic Bold"` | `("Malgun Gothic", True)` |
| 3 | FontFamilyPolicy | `"NanumSquare ExtraBold Italic"` | `("NanumSquare", True)` |
| 4 | FontFamilyPolicy | `"ABCDEF+MalgunGothicBold"` (서브셋) | family에 `+` 프리픽스 없음 |
| 5 | FontFamilyPolicy | `"Black"` (토큰만으로 구성) | 원본 유지 `("Black", ...)` |
| 6 | FontCatalog | 미설치 + 정규화 가능 | mapping 값 = family, 경고 없음 |
| 7 | FontCatalog | 미설치 + 정규화 불가(변화 없음) | 원본 유지 + 기존 경고 |
| 8 | FontCatalog | installed에 "MalgunGothic.ttf" 존재 시 `"Malgun Gothic Bold"` | 설치 폰트명 매칭 |
| 9 | run_fonts | set_run_font(run, "맑은 고딕") | rPr에 latin=ea=cs="맑은 고딕" |
| 10 | run_fonts | 동일 run에 2회 호출 | ea/cs 중복 요소 없이 갱신 |
| 11 | renderer | heading 있는 bullets 슬롯 | 첫 문단 h3·bold·primary, 이후 문단 body |
| 12 | renderer | heading 없는 bullets 슬롯 | 기존과 동일 (회귀) |
| 13 | renderer | TOC 패턴 + heading | heading 무시 (TOC는 기존 규칙 유지) |
| 14 | renderer | title 슬롯 내용 None + plan.title 존재 | plan.title로 h2 타이틀 렌더 |
| 15 | renderer | 표 셀 run | ea 슬롯 설정 확인 |
| 16 | use case | Draft.heading 공백 문자열 | SlotContent.heading=None |
| 17 | use case | 전 슬롯 빈 비표지 슬라이드 | 렌더 제외 + warnings 1건 |
| 18 | schemas | heading 필드 없는 LLM JSON | 파싱 성공, heading=None (하위호환) |

### 8.3 통합 테스트 (Check 단계 실행)

| # | Scenario | Steps | Success Criteria |
|---|----------|-------|-----------------|
| 1 | 골든 샘플 재생성 | 샘플 PDF 추출 → 블루프린트 → 생성 → PPTX 재파싱 | §5.4 체크리스트 전 항목 통과 |
| 2 | 기존 테스트 회귀 | `pytest tests/` 전체 | 전부 통과 |

### 8.5 Seed Data Requirements

| Entity | Minimum Count | Key Fields Required |
|--------|:------------:|---------------------|
| 샘플 파일 | 1 | `samples/golden_sample_report.pdf` (기존 재사용) |
| LLM 스텁 | - | SlideContentDraft에 heading 포함/미포함 케이스 각 1 |

---

## 9. Clean Architecture

### 9.1 이 기능의 레이어 배치

| Component | Layer | Location | 비고 |
|-----------|-------|----------|------|
| `FontFamilyPolicy` | Domain | `src/domain/blueprint/policies.py` | 순수 함수, 신규 클래스 |
| `SlotContent.heading` | Domain | `src/domain/blueprint/value_objects.py` | 기본값 None |
| `SlotContentDraft.heading` | Domain (schema) | `src/domain/blueprint/schemas.py` | Optional |
| `FontCatalog` 정규화 경유 | Infrastructure | `src/infrastructure/blueprint/fonts.py` | domain 정책 호출 |
| `run_fonts.set_run_font` | Infrastructure | `src/infrastructure/blueprint/renderer/run_fonts.py` | ★ 신규 파일 (유일) |
| 렌더러 heading·타이틀 폴백 | Infrastructure | `src/infrastructure/blueprint/renderer/pptx_renderer.py` | |
| heading 매핑·빈 슬라이드 스킵 | Application | `src/application/blueprint/generation_use_case.py` | |
| 슬롯 작성 프롬프트 heading 안내 | Infrastructure | `src/infrastructure/blueprint/prompts.py` | |

### 9.2 Dependency Rules 준수

- infra(FontCatalog) → domain(FontFamilyPolicy): 허용 방향 ✅
- domain은 pptx/lxml 미참조 (oxml은 renderer 헬퍼에만) ✅ — `tests/domain/blueprint/test_layer_contract.py`로 검증
- Repository/세션 변경 없음 ✅

---

## 10. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 함수 길이 | 40줄 이하 — `set_run_font` 헬퍼 분리 사유 |
| 네이밍 | 기존 renderer 모듈 스타일 (snake_case 함수, `_` private) |
| 로깅 | LoggerInterface 경유, print 금지, 스택 트레이스 포함 |
| 타입 | 명시적 typing (`str | None`, frozen dataclass) |
| oxml 조작 | `pptx.oxml.ns.qn` 네임스페이스 헬퍼 사용, 매직 문자열 금지 — 이 기능이 첫 사례이므로 `run_fonts.py` docstring에 규칙 명시 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
src/
├── domain/blueprint/
│   ├── policies.py            (수정) FontFamilyPolicy 추가
│   ├── value_objects.py       (수정) SlotContent.heading
│   └── schemas.py             (수정) SlotContentDraft.heading
├── infrastructure/blueprint/
│   ├── fonts.py               (수정) 정규화 경유 suggest/propose_mapping
│   ├── prompts.py             (수정) 슬롯 작성 프롬프트 heading 안내
│   └── renderer/
│       ├── run_fonts.py       (신규) set_run_font — latin/ea/cs 3슬롯
│       └── pptx_renderer.py   (수정) 헬퍼 적용·heading 렌더·타이틀 폴백
└── application/blueprint/
    └── generation_use_case.py (수정) heading 매핑·빈 슬라이드 스킵
tests/
├── domain/blueprint/test_policies.py          (수정) 정규화 케이스 1~5
├── domain/blueprint/test_schemas.py           (수정) heading 하위호환 18
├── infrastructure/blueprint/test_fonts.py     (수정) 케이스 6~8
├── infrastructure/blueprint/test_run_fonts.py (신규) 케이스 9~10
├── infrastructure/blueprint/test_pptx_renderer.py (수정) 케이스 11~15
├── application/blueprint/test_generation_use_case.py (수정) 케이스 16~17
└── integration/blueprint/test_golden_sample_fidelity.py (수정) §5.4 체크리스트
```

### 11.2 Implementation Order (TDD)

1. [ ] **FontFamilyPolicy** — 테스트(1~5) → 구현 → 통과
2. [ ] **FontCatalog 정규화 경유** — 테스트(6~8) → 구현 → 통과
3. [ ] **run_fonts 헬퍼** — 테스트(9~10, lxml 검증) → 구현 → `_textbox`/`_style_cell` 적용(15)
4. [ ] **SlotContent/Draft.heading + 프롬프트** — 테스트(18) → 스키마·프롬프트 수정
5. [ ] **use case heading 매핑·빈 슬라이드 스킵** — 테스트(16~17) → 구현
6. [ ] **렌더러 heading 렌더·타이틀 폴백** — 테스트(11~14) → 구현
7. [ ] **통합**: 골든 샘플 충실도 테스트 확장 → 전체 pytest 회귀 확인

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 폰트 정규화 | `module-1` | FontFamilyPolicy + FontCatalog + run_fonts 헬퍼 + 렌더러 적용 (FR-01/02) | 15-20 |
| 계층 복원 | `module-2` | heading 필드 전파 + 렌더러 소제목/타이틀 폴백 + 빈 슬라이드 스킵 (FR-03/04) | 15-20 |
| 통합 검증 | `module-3` | 골든 샘플 충실도 테스트 확장 + 회귀 | 5-10 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `--scope module-1,module-2` (규모가 작아 단일 세션 권장) | 30-40 |
| Session 2 | Check + Report | 전체 | 20-30 |

---

## 12. 핵심 구현 상세 (참조용)

### 12.1 run_fonts.set_run_font

```python
# src/infrastructure/blueprint/renderer/run_fonts.py (신규)
"""run 폰트 3슬롯 설정 — a:latin 은 python-pptx, a:ea/a:cs 는 oxml 직접 설정.

python-pptx 는 East Asian 타입페이스 API 를 제공하지 않는다. 한글 글리프는
a:ea 를 따르므로 미설정 시 테마 기본값으로 폴백해 폰트가 깨진다 (FR-02).
"""
from pptx.oxml.ns import qn

def set_run_font(run, name: str) -> None:
    run.font.name = name                      # <a:latin>
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        el = rpr.find(qn(tag))
        if el is None:
            el = rpr.makeelement(qn(tag), {})
            rpr.append(el)
        el.set("typeface", name)
```

주의: `<a:rPr>` 자식 순서는 스키마상 latin→ea→cs 순이 표준이나 PowerPoint는 순서 위반에 관대함 — 단위 테스트는 존재·값만 검증하고, 순서까지 강제하지 않는다(과도한 결합 회피). `run.font.name` 선행 호출로 latin이 먼저 생성되므로 실제 순서도 표준과 일치.

### 12.2 렌더러 heading 렌더 (_bullets 확장 스케치)

```
_bullets(ctx, slide, pattern, slot, content):
  TOC: 기존 그대로 (heading 무시)
  일반:
    paragraphs = []
    if content.heading: 첫 문단 = heading (size=h3, font=ctx.font("heading"),
                                   bold=True, color=palette["primary"], space_after=6pt)
    이후 문단 = "• " + bullet (size=body, 기존 스타일)
```

`_textbox`가 단일 스타일 전제이므로, heading 혼합 문단은 `_textbox` 시그니처 확장 대신 **bullets 전용 조립 함수**로 분리해 40줄 규칙 준수 (형태는 Do 단계 재량, 동작은 테스트 11~13이 고정).

### 12.3 타이틀 폴백 (_render_slide 확장 스케치)

```
_render_slide:
  for slot in pattern.slots:
    if slot.kind is TITLE and 비표지:
        text = (by_slot[slot.id].text if 존재) or content.plan.title
        text 있으면 _title(...) 강제 호출
```

빈 슬라이드 스킵은 use case에서: `renderable_content(slide, pattern)` 판정 — 비표지이면서 모든 슬롯 내용이 비고 pattern에 asset 기반 image 슬롯도 없으면 제외 + warning.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-24 | Option C 기반 초안 — 정규화 정책·run_fonts 헬퍼·heading 전파·타이틀 폴백 설계 | 배상규 |
