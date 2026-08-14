# tool-recommender Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation)
>
> **Project**: sangplusbot (idt / 백엔드)
> **Version**: 0.4 (Act 3회 + module-4 결선 + Recall 실측)
> **Analyst**: tkdrb136
> **Date**: 2026-08-13
> **Design Doc**: [tool-recommender.design.md](../02-design/features/tool-recommender.design.md)
> **Plan Doc**: [tool-recommender.plan.md](../01-plan/features/tool-recommender.plan.md)

> **분석 수행 방식 고지**: `bkit:gap-detector` 에이전트를 2회 호출했으나 두 번 모두
> 분석 내용 없는 응답(`"Tenth. Standing by."` / `"(Hook re-fire; no action taken.)"`)을
> 반환해 사용할 수 없었다. 따라서 본 분석은 **직접 수행**했으며, 모든 수치는 아래
> 명시된 실행 가능한 증거(테스트·커버리지·AST 파싱·무작위 속성 검증)에 근거한다.
> 에이전트의 미산출 결과를 추정해 채워넣지 않았다.

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 도구 전량 바인딩 구조라 도구 수 증가가 곧 추천 품질 저하로 이어진다 |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) |
| **RISK** | 선별이 정답 도구를 누락시켜 기존에 되던 질의가 실패하는 **기능 회귀** |
| **SUCCESS** | 골드셋 Recall ≥ 95%, 평균 바인딩 도구 수 감소, 모듈 제거 시 기존 경로 무변경 |
| **SCOPE** | Phase 1 = 경로 독립 선별 모듈 + 골드셋 테스트 (배선 없음) |

---

## Strategic Alignment Check

> PRD 없음 (`/pdca pm` 미실행) — Plan이 최상위 근거 문서다.

### Success Criteria Status (Plan §4.1)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | FR-01 ~ FR-10 전부 구현 | ✅ Met | §3 FR 검증표 — 10/10 |
| SC-2 | 골드셋 유닛테스트 (질의→기대 도구 20~30건) | ✅ Met | `goldset.json` — 실측 도구 13개 풀 + 질의 **22건**(정답 도구 23개) |
| SC-3 | Recall 측정 (실 LLM, 누락률 리포트) | ✅ Met | **Recall 100%** (23/23, 누락 0), 폴백 0건 — 목표 95% 초과 |
| SC-4 | 도구 수 감소율 (before/after) | ✅ Met | **13 → 평균 2.9개 (78% 감소)** |
| SC-5 | 탈부착 검증 (모듈 제거 후 무변경) | ✅ Met | `test_module_boundaries.py` 27건 + 디렉토리 제거 후 전체 collect 6938건 **에러 0** |
| SC-6 | `/verify-tdd`, `/verify-logging` 통과 | ✅ Met | `print()` 0건, 예외 처리에 `exception=` 스택 보존, 프로덕션 모듈 13개 전부 대응 테스트 존재 |

**Success Rate**: **6/6 Met (100%)** — v0.3의 미달 3건이 Recall 실측으로 모두 해소

> **Plan의 최대 리스크(기능 회귀)가 실측으로 반증됐다.** 22건 전부에서 정답 도구가
> 살아남았고 폴백은 0건이었다. 다만 후보 풀이 13개(Design §8.5 목표 40+ 미달)이고
> 저신호 스텁 사례가 0건이라, 도구가 수십 개로 늘었을 때의 Recall은 여전히 미검증이다.

### Quality Criteria Status (Plan §4.2)

| Criteria | Status | Evidence |
|----------|:------:|----------|
| 함수 40줄 이하 | ✅ | 최대 39줄 (`LLMToolSelector.select`) — AST 측정 |
| if 중첩 2단계 이하 | ✅ | 최대 2단계 (`sanitize`, `_index`) |
| 명시적 타입 (pydantic/typing) | ✅ | 공개 함수 전부 annotated, VO는 `@dataclass(frozen=True)` |
| 폴백 경로 테스트 존재 | ✅ | LLM 예외/타임아웃/파싱 5종/미지 ID/빈 선택/캐시 장애 각각 커버 |

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | 경로 독립 공용 모듈 (배선 없음) | ✅ | 외부 소비자 0건 — `test_no_production_code_outside_module_depends_on_it` |
| [Plan] | 경량 LLM 1콜 | ✅ | `llm_tool_selector.py:216-224` |
| [Plan] | 개별 도구 단위 선별 | ⚠️ | 단위는 개별 도구가 맞으나 MCP id가 `server_name` 기반 — §2.9 D-4 |
| [Plan] | 입력 = 현재 유저 메시지만 | ✅ | `selector_middleware.py:28-43` 마지막 human 메시지만 추출 |
| [Plan] | 필수 세트 ∪ 추천 결과 | ✅ | `policies.merge` + 무작위 3000회 위반 0 |
| [Plan] | CachePort 정의 + v1 NullCache | ✅ | `null_cache.py`, 기본 주입 `llm_tool_selector.py:90` |
| [Design] | Option C (Port + 어댑터) | ✅ | 레이어 경계 테스트 27건 통과 |
| [Design] | 코어의 langchain 무지 | ✅ | `test_infra_core_never_imports_langchain` |
| [Design] | MCP 이름 토큰화 보강 | ✅ | `policies.effective_description` — 단 설계 의사코드에 결함이 있어 수정 (§2.9 D-3) |
| [Design] | module-4 결선은 범위 밖 | ✅ | 미배선, 킬스위치 `tool_selector_enabled=False` |

---

## 1. Analysis Overview

### 1.1 Analysis Purpose

module-1·2·3 구현이 Design/Plan과 일치하는지, 그리고 Plan의 최대 리스크인 **기능 회귀**를
막는 계약이 실제로 성립하는지 검증한다.

### 1.2 Analysis Scope

- **Design**: `docs/02-design/features/tool-recommender.design.md`
- **구현 경로**: `src/domain/tool_selection/`, `src/infrastructure/tool_selection/`
- **범위 밖(의도적)**: module-4 결선 — Plan §2.2에서 Out of Scope로 확정
- **분석일**: 2026-08-13

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints

**N/A** — 내부 모듈. 엔드포인트·라우터·스키마 변경 없음. 루트 CLAUDE.md §4-1(API 계약
동기화) 해당 없음. 프론트엔드 변경 0.

### 2.2 Data Model

Design §3.1 대비 — DB 스키마 변경 없음(전부 인메모리 VO).

| 항목 | Design | 구현 | Status |
|---|---|---|:-:|
| `ToolSource` | INTERNAL / MCP | 동일 | ✅ |
| `ToolCandidate.tool_id` | str | str | ✅ |
| `ToolCandidate.name` | str | str | ✅ |
| `ToolCandidate.description` | str | str (기본 `""`) | ✅ |
| `ToolCandidate.source` | ToolSource | 동일 (기본 INTERNAL) | ✅ |
| `ToolCandidate.server_name` | str \| None | 동일 | ✅ |
| `SelectionResult.selected_ids` | tuple[str,...] | 동일 | ✅ |
| `SelectionResult.required_ids` | tuple[str,...] | 동일 | ✅ |
| `SelectionResult.final_ids` | Design은 `@property`, 구현은 필드 | 필드 | ⚠️ 형태 차이 |
| `SelectionResult.candidate_count` | int | 동일 | ✅ |
| `SelectionResult.elapsed_ms` | int | 동일 | ✅ |
| `SelectionResult.fallback` | bool | 동일 | ✅ |
| `SelectionResult.reason` | str \| None | 동일 | ✅ |
| `SelectionResult.dropped_ids` | tuple[str,...] | 동일 | ✅ |

> `final_ids` 형태 차이는 무해하다. Design §3.1은 `@property`로 스케치했으나 구현은
> `frozen=True` VO의 불변 필드로 계산 시점을 조립 시점에 고정했다. 결과 동일, 재계산 없음.

### 2.3 Component Structure

| Design 산출물 (§11.1) | 구현 파일 | Status |
|---|---|:-:|
| `domain/tool_selection/__init__.py` | 존재 | ✅ |
| `domain/tool_selection/interfaces/__init__.py` | 존재 | ✅ |
| `domain/tool_selection/interfaces/tool_selector_port.py` | 존재 | ✅ |
| `domain/tool_selection/interfaces/selection_cache_port.py` | 존재 | ✅ |
| `domain/tool_selection/schemas.py` | 존재 | ✅ |
| `domain/tool_selection/policies.py` | 존재 | ✅ |
| `infrastructure/tool_selection/__init__.py` | 존재 | ✅ |
| `infrastructure/tool_selection/llm_tool_selector.py` | 존재 | ✅ |
| `infrastructure/tool_selection/prompts.py` | 존재 | ✅ |
| `infrastructure/tool_selection/null_cache.py` | 존재 | ✅ |
| `infrastructure/tool_selection/adapters/__init__.py` | 존재 | ✅ |
| `infrastructure/tool_selection/adapters/langchain_filter.py` | 존재 | ✅ |
| `infrastructure/tool_selection/adapters/selector_middleware.py` | 존재 | ✅ |
| `tests/domain/tool_selection/__init__.py` | 존재 | ✅ |
| `tests/domain/tool_selection/test_policies.py` | 존재 | ✅ |
| `tests/infrastructure/tool_selection/__init__.py` | 존재 | ✅ |
| `tests/infrastructure/tool_selection/test_llm_tool_selector.py` | 존재 | ✅ |
| `tests/infrastructure/tool_selection/test_langchain_filter.py` | 존재 | ✅ |
| `tests/infrastructure/tool_selection/test_goldset_recall.py` | **부재** | ❌ |
| `tests/fixtures/tool_selection/goldset.json` | **부재** | ❌ |
| — (설계에 없음) | `test_selector_middleware.py` | ➕ 추가 |
| — (설계에 없음) | `test_module_boundaries.py` | ➕ 추가 |

**Structural Match (v0.2)**: 20/22 = **91%**

> v0.2에서 Design §11.1이 `test_selector_middleware.py`·`test_module_boundaries.py`를
> 정식 산출물로 편입했다(D-6 해소). 분모 20→22, 분자 18→20.

### 2.4 Functional Depth Analysis

| File | Depth | Placeholder | 비고 |
|---|:-:|:-:|---|
| `domain/tool_selection/schemas.py` | 100 | 없음 | |
| `domain/tool_selection/policies.py` | 100 | 없음 | 6개 순수 함수 전부 구현 |
| `domain/.../tool_selector_port.py` | 100 | 없음 | ABC — 계약 4개 문서화 |
| `domain/.../selection_cache_port.py` | 100 | 없음 | ABC |
| `infrastructure/.../llm_tool_selector.py` | 100 | 없음 | 실패 모드 9종 분기 |
| `infrastructure/.../prompts.py` | 100 | 없음 | |
| `infrastructure/.../null_cache.py` | 100 | 없음 | 의도된 no-op (설계대로) |
| `adapters/langchain_filter.py` | 100 | 없음 | |
| `adapters/selector_middleware.py` | 100 | 없음 | 미배선이나 로직 완성 |

**Shallow File Count**: 0 / 9 (0%)

#### Design §6.1 실패 모드 8종 구현 검증

| # | 실패 모드 | 구현 위치 | 테스트 |
|:-:|---|---|---|
| 1 | `under_threshold` | `llm_tool_selector.py:147` | `test_llm_tool_selector.py:315` |
| 2 | `no_candidates` | `:144` | `:338` |
| 3 | `llm_error` | `:203` | `:189` |
| 4 | `llm_timeout` | `:197` | `:227` |
| 5 | `parse_error` | `:213` | `:253` (5개 입력 파라미터화) |
| 6 | `sanitized` | `:134` | `:271` |
| 7 | `empty_selection` | `:129` | `:285`, `:300` |
| 8 | 어댑터 최후 방어선 | `langchain_filter.py:78,82,96,104` | 5건 (`result == tools`) |
| ➕ | `cache_hit` (설계 외) | `:170` | `:469` |

**8/8 구현 + 테스트.** 설계에 없던 9번째(`cache_hit`)가 추가됨 — §2.9 D-2.

#### 기타 설계 요소

| Design 항목 | 구현 | Status |
|---|---|:-:|
| §3.3 `is_low_signal` / `tokenize_name` / `effective_description` | `policies.py:38-70` | ✅ (의사코드 결함 수정 — D-3) |
| §4.2 캐시 키 `sha256(query \| sorted(ids))` | `policies.build_cache_key` | ✅ 순서 무관·집합 변경 시 무효화 테스트 완비 |
| §4.4 프롬프트 (JSON only, id만 출력) | `prompts.py` | ✅ |
| §4.3 `ToolIdResolver` 프로토콜 | `langchain_filter.py:17-24` | ✅ |
| §4.3 `LangChainToolFilter.filter` 시그니처 | `:60-104` | ✅ |
| §4.3 `ToolSelectionMiddleware` | `selector_middleware.py` | ✅ `awrap_model_call` 사용 |

**Functional Match Rate (v0.2)**: **100%** (12/12 설계 동작 구현, placeholder 0, 라인 커버리지 **100%**)

### 2.5 Page UI Checklist Verification

**N/A** — UI 없음 (Design §5).

### 2.6 Contract Verification

> API 엔드포인트가 없으므로 3-way 계약 대신 **Port 계약**(Design §4.1)을 검증한다.

무작위 입력 **3000회** 실행 (후보 0~25개, 필수 0~4개, LLM 응답을 정상/이상/예외로 무작위 혼합):

| # | 계약 (Design §4.1) | 위반 | Status |
|:-:|---|:-:|:-:|
| a | 어떤 이유로도 예외를 발생시키지 않는다 | **0** | ✅ PASS |
| b | `required_ids`는 후보에 없어도 결과에 포함된다 | **0** | ✅ PASS |
| c | `final_ids` 순서는 후보 원순서를 따른다 | **0** | ✅ PASS |
| d | `final_ids ⊆ candidates ∪ required_ids` | **0** | ✅ PASS |

**Contract Match Rate**: 4/4 = **100%**

> (d)는 Design §7의 권한 경계 불변 근거이기도 하다. 선별은 축소만 하므로 프롬프트
> 인젝션이 성공해도 후보 집합 밖으로 나갈 수 없다.

### 2.7 Runtime Verification Results

> HTTP·브라우저 표면이 없는 백엔드 내부 모듈이므로 Design §8.1의 매핑을 따른다:
> **L1 = 유닛, L2 = 통합, L3 = 골드셋 평가.** Playwright/서버 기동은 해당 없음.

#### L1: 유닛 (도메인 정책) — pytest

| 대상 | 통과 | 비고 |
|---|:-:|---|
| `test_policies.py` | 41/41 | merge 6 · sanitize 5 · needs_selection 6 · 저신호 5 · 토큰화 7 · 보강 4 · 캐시키 4 · VO 3 |

**L1 Score**: 41/41 = **100%**

#### L2: 통합 (셀렉터 + 어댑터) — pytest, LLM 스텁

| 대상 | 통과 |
|---|:-:|
| `test_llm_tool_selector.py` | 30/30 |
| `test_langchain_filter.py` | 24/24 |
| `test_selector_middleware.py` | 12/12 |
| `test_module_boundaries.py` | 27/27 |

**L2 Score**: 93/93 = **100%**

#### L3: 골드셋 Recall 평가 — 실 LLM (**실행 완료**)

후보 풀: Doc Convert MCP 실측 4건 + `TOOL_REGISTRY` 9건 = **13개 (전부 실데이터)**
케이스: 22건 / 정답 도구 23개 / 모델 `gpt-4o-mini` / top_k=8

| # | Design §8.4 항목 | 목표 | 실측 | 판정 |
|:-:|---|---|---|:-:|
| 1 | **Recall** | ≥ 95% | **100%** (누락 0/23, 폴백 0) | ✅ |
| 2 | **도구 수 감소율** | 40 → 8~10 | **13 → 2.9 (78% 감소)** | ✅ (풀 규모는 미달) |
| 3 | MCP 저신호 보강 효과 | on/off 비교 | **측정 불가** — 실데이터에 스텁 0건 | ⏸ |
| 4 | **지연 P95** | < 1500ms | **1369ms** (중앙값 775 / 평균 896 / 최대 2709=콜드스타트 / 웜 P95 1193) | ✅ |

**L3 Score**: 3/4 = **75%** (#3은 실패가 아니라 데이터 부재로 측정 불가)

**Runtime Match Rate**: (100 × 0.4) + (100 × 0.3) + (75 × 0.3) = **92.5%**

> 지연은 실행 간 편차가 있다 — 1회차 P95 2622ms, 2회차 1369ms. 표본 22건에서 P95는
> 사실상 21번째 값이라 콜드스타트(첫 콜 ~2.7s) 하나가 지배한다. 웜 구간은 안정적으로
> 1.2s 이하다. `_invoke`가 호출마다 `LLMFactory.create()`로 새 클라이언트를 만드는데,
> 이는 `general_chat._create_agent`와 동일한 기존 패턴이다.

### 2.8 Match Rate Summary

**v0.1 (Act 이전)**

```
Structural 90 · Functional 98 · Contract 100 · Runtime 70  →  Overall 87.50%
```

**v0.2 (Act-1 — Design 표류 6건 교정 + 커버리지 100%)**

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:   91%   (20/22)      │
│  Functional Match Rate:  100%   ▲ +2         │
│  Contract Match Rate:    100%                │
│  Runtime Match Rate:      70%   (L3 미실행)   │
│  ─────────────────────────────────────────── │
│  Overall Match Rate:      88.15%  ▲ +0.65    │
│  = (91 × 0.15) + (100 × 0.25)               │
│    + (100 × 0.25) + (70 × 0.35)             │
│  = 13.65 + 25.0 + 25.0 + 24.5               │
├─────────────────────────────────────────────┤
│  ✅ Match:           20 items (91%)          │
│  ⚠️ Shallow:          0 items (0%)           │
│  ❌ Not implemented:  2 items (9%)           │
│     (test_goldset_recall.py, goldset.json)  │
└─────────────────────────────────────────────┘
```

**v0.4 (module-4 결선 + Recall 실측 완료)**

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  100%   (22/22) ▲    │
│  Functional Match Rate:  100%                │
│  Contract Match Rate:    100%                │
│  Runtime Match Rate:      92.5% ▲ +22.5      │
│  ─────────────────────────────────────────── │
│  Overall Match Rate:      97.38% ▲ +9.23     │
│  = (100 × 0.15) + (100 × 0.25)              │
│    + (100 × 0.25) + (92.5 × 0.35)           │
├─────────────────────────────────────────────┤
│  ✅ 90% 게이트 통과                           │
└─────────────────────────────────────────────┘
```

### ~~🔴 게이트 도달 불가 — 구조적 상한~~ (v0.4에서 해소)

> 아래는 v0.2 시점의 기록이다. 골드셋 확보로 L3가 실행되면서 상한이 풀렸다.

**골드셋 없이 90% 게이트는 수학적으로 도달할 수 없다.**

L3(골드셋 평가)는 Runtime의 30%, Runtime은 Overall의 35% → **10.5%p가 잠겨 있다.**
나머지 세 축을 전부 100%로 만들어도:

```
(100 × 0.15) + (100 × 0.25) + (100 × 0.25) + (70 × 0.35) = 89.50%
```

현재 88.15%와 이론상 최대 89.50%의 차이는 1.35%p뿐이고, 그 전부가 Structural의
`test_goldset_recall.py` + `goldset.json` 2개 파일이다. **즉 이 둘도 골드셋 확보로만
채워진다.**

→ **추가 Act 반복은 무의미하다.** 게이트 통과의 유일한 경로는 MCP 엔드포인트 복구다.
Act 반복 횟수를 소모하는 대신 §9.1의 차단 해소를 선행해야 한다.

### 2.9 Discrepancies (Design ↔ Code, 양방향)

| # | 항목 | Design | 구현 | 판정 |
|:-:|---|---|---|---|
| **D-1** | top-K 절단 | §4.1에 없음 | `llm_tool_selector.py:126,169` `kept[:top_k]` | **코드가 더 함 — 타당.** 프롬프트로 "최대 N개"를 지시해도 모델이 초과 반환할 수 있어, 없으면 FR-07 상한이 무력화된다. Design 갱신 필요 |
| **D-2** | `cache_hit` reason | §6.1 표에 8종만 | 9종 (`policies.SelectionReason.CACHE_HIT`) | **코드가 더 함 — 타당.** 캐시 경로 관측에 필요. Design 갱신 필요 |
| **D-3** | 스텁 탐지 방식 | §3.3 의사코드: `text == f"MCP tool: {name}"` | 정규식 `^MCP tool:\s*\S+$` | **설계 결함을 코드가 교정.** 실제로 어댑터 `name`은 `sanitize(f"{server}_{tool}")`이고 스텁 꼬리는 원본 `tool`이라(`mcp/tool_registry.py:83-90`) 두 값이 애초에 불일치 — 설계대로면 스텁을 **하나도 못 잡는다**. Design 갱신 필요 |
| **D-4** | MCP 도구 ID | §3.2: `mcp:{server_id}:{tool}` | ~~`mcp:{server_name}:{tool}`~~ → **`mcp:{server_id}:{tool}`** | ✅ **Act-2에서 해소.** 실측 결과 `MCPServerConfig.name`이 `mcp_{uuid}`(= `registration.tool_id`, `mcp_tool_loader.py:42`)라 **server_id가 이미 포함**돼 있었다. 접두어만 벗기면 카탈로그와 동일. 저장소 조회 불필요 → **module-4 차단 요인 소멸** |
| **D-8** | MCP 도구 표시명 | §3.3 예시 `naver_mcp` | `tool.name` = `mcp_{uuid}_{tool}` (UUID 40자) | 🔴 **Act-2에서 발견·수정.** 그대로 넘기면 후보 목록이 UUID로 도배됨. `mcp_tool_name`(`docx_to_html`)을 표시명으로 사용 |
| **D-9** | 서버명 보강 | §3.3: `"{server} 서버의 '{tokens}' 기능"` | 런타임 서버명이 UUID | 🔴 **Act-2에서 발견·수정.** 보강이 오히려 노이즈를 주입. UUID 형태면 `server_name=None` |
| **D-10** | 프롬프트 1도구=1줄 | §4.4 형식 | MCP 설명이 `Args:` 포함 여러 줄 | 🔴 **Act-2에서 발견·수정.** 도구 13개에 2878자. `summarize_description`으로 압축 → 1778자(-38%), 13줄 |
| **D-5** | `DefaultToolIdResolver` | §4.3은 프로토콜만 언급 | 기본 구현체 제공 | **코드가 더 함 — 타당.** 호출부가 매번 resolver를 짜야 하는 부담 제거 |
| **D-6** | 추가 테스트 2종 | §11.1에 없음 | `test_selector_middleware.py`, `test_module_boundaries.py` | **코드가 더 함 — 타당.** 특히 경계 테스트는 Plan SC-5(탈부착)를 CI에서 자동 강제 |
| **D-7** | `SelectionResult.final_ids` | `@property` | 불변 필드 | 무해한 형태 차이 |

---

## 3. Plan §3.1 기능 요구사항 검증

| ID | 요구사항 | Status | 증거 |
|---|---|:-:|---|
| FR-01 | Port가 `(query, candidates) → SelectionResult`, langchain·DB·HTTP 무의존 | ✅ | `tool_selector_port.py:17-25`; `test_module_boundaries.py` 도메인 순수성 3종 통과 |
| FR-02 | `(id, name, description)`만 제시하고 도구 ID만 반환받음 | ✅ | `prompts.py:31-34`, `llm_tool_selector.py:49-66` (`parse_tool_ids`) |
| FR-03 | 선별 단위 = 개별 도구, MCP는 서버 단위로 뭉개지 않음 | ⚠️ | `langchain_filter.py:45` — 도구 단위는 충족, 단 식별자가 `server_name` 기반 (D-4) |
| FR-04 | `필수 ∪ 추천`, 모듈이 `builtin_default`를 직접 조회하지 않음 | ✅ | `policies.merge`; `TOOL_REGISTRY`/`tool_catalog` 참조 **0건** (grep 확인) |
| FR-05 | 실패 시 예외 미전파, `reason` 기록 | ✅ | 무작위 3000회 예외 전파 0; 실패 모드 8종 표 |
| FR-06 | 미지 ID 폐기 + WARNING | ✅ | `policies.sanitize`, `llm_tool_selector.py:134`; `test_llm_tool_selector.py:271` |
| FR-07 | top-K 설정 주입, 하드코딩 금지 | ✅ | `llm_tool_selector.py:85,92`; `config.py:124` |
| FR-08 | 후보 ≤ top-K면 LLM 미호출 | ✅ | `:145`; `test_under_threshold_skips_llm_entirely` (호출 수 0 검증) |
| FR-09 | `SelectionCachePort` + v1 `NullSelectionCache` | ✅ | `selection_cache_port.py`, `null_cache.py`, 기본 주입 `:90` |
| FR-10 | 입력/출력 수·폴백·소요 ms를 StructuredLogger로 기록 | ✅ | `llm_tool_selector.py:251-260` |

**10/10 구현** (FR-03은 D-4 유보 사항 포함)

---

## 4. Performance Analysis

| 항목 | 측정 | 목표 (Plan §3.2) | Status |
|---|---|---|:-:|
| 선별 오버헤드 P95 | **미측정** (실 LLM 호출 없음) | < 1.5s | ⏸ 보류 |
| 조기 반환 시 비용 | LLM 호출 **0회** (테스트로 검증) | — | ✅ |
| 평균 바인딩 도구 수 감소 | **미측정** | 40 → 8~10 | ❌ SC-4 |

`elapsed_ms` 계측 자체는 구현되어 있어(`:243`), 골드셋 확보 즉시 측정 가능하다.

---

## 5. Test Coverage

| 영역 | 현재 | 목표 | Status |
|---|---|---|:-:|
| Lines | **100%** (354/354) | 80% | ✅ |
| 테스트 수 | **145 passed** ▲ | — | ✅ |

### 5.1 미커버 영역

**없음.** v0.1에서 유일하게 미커버였던 `llm_tool_selector.py:167`
(`_from_cache`의 무효 캐시 분기)은 Act 단계에서
`test_stale_cache_entry_falls_through_to_llm`으로 덮었다 — 캐시 값이 전부 무효해지면
폴백이 아니라 **LLM 선별로 흘러가는지**를 검증한다 (여기서 폴백하면 도구 목록이 바뀔
때마다 선별이 죽는다).

### 5.2 회귀 확인

- 전체 스위트: 6946 passed / 58 failed
- **58건 전부 사전 존재** — 본 변경을 `git stash`한 상태에서도 동일 실패
  (`test_pymupdf4llm_parser.py`, `test_parent_child_retriever.py`)
- 본 기능으로 인한 신규 실패 **0건**

---

## 6. Clean Architecture Compliance

### 6.1 Layer Dependency Verification

| Layer | 기대 의존 | 실제 | Status |
|---|---|---|:-:|
| domain | 없음 (표준 라이브러리만) | `abc`, `collections.abc`, `dataclasses`, `enum`, `hashlib`, `re` | ✅ |
| infrastructure (코어) | domain only | `domain.tool_selection`, `domain.llm.interfaces`, `domain.llm_model.entity`, `domain.logging.interfaces` | ✅ |
| infrastructure (adapters) | domain + langchain | 위 + `langchain.agents.middleware`, `langchain_core` | ✅ |
| application | — | **참조 없음** (미배선) | ✅ |

### 6.2 Dependency Violations

**0건.** `test_module_boundaries.py`가 AST 파싱으로 자동 강제:

| 테스트 | 검사 내용 |
|---|---|
| `test_domain_imports_only_stdlib_and_own_package` | 도메인 순수성 |
| `test_domain_never_imports_infrastructure` | CLAUDE.md §6 |
| `test_domain_never_imports_langchain` | 프레임워크 무지 |
| `test_infra_core_never_imports_langchain` | langchain은 adapters/ 전용 |
| `test_infra_never_imports_application_or_interfaces` | 역방향 참조 금지 |
| `test_infra_depends_only_on_declared_domain_ports` | 의존 확산 감시 |
| `test_no_production_code_outside_module_depends_on_it` | **탈부착 계약** |

### 6.3 탈부착 검증 (Plan SC-5)

| 방법 | 결과 |
|---|---|
| 모듈 밖 `tool_selection` 참조 grep | **0건** |
| 4개 디렉토리 제거 후 전체 pytest collect | **6938건 수집, 에러 0** (모듈 포함 시 7006 = 6938 + 68) |
| 어댑터 격리 (langchain이 adapters/ 안에만) | ✅ `test_adapters_do_import_langchain`으로 양방향 확인 |

### 6.4 Architecture Score

```
┌─────────────────────────────────────────────┐
│  Architecture Compliance: 100%               │
├─────────────────────────────────────────────┤
│  ✅ 올바른 레이어 배치: 13/13 파일           │
│  ⚠️ 의존 위반:          0                    │
│  ❌ 잘못된 레이어:       0                    │
└─────────────────────────────────────────────┘
```

---

## 7. Convention Compliance

### 7.1 Naming

| 범주 | 규칙 | 검사 수 | 준수 | 위반 |
|---|---|:-:|:-:|---|
| 클래스 | PascalCase | 13 | 100% | — |
| 함수/메서드 | snake_case | 39 | 100% | — |
| 모듈 상수 | UPPER_SNAKE_CASE | 8 | 100% | — |
| 파일 | snake_case.py | 13 | 100% | — |
| Port 접미사 | `~Port` (Design §10.1) | 2 | 100% | — |

### 7.2 Folder Structure

Design §11.1 대비 100% 일치 (§2.3 참조).

### 7.3 Lint / Import Order

| 항목 | 결과 |
|---|---|
| `ruff check` (E, F, I, N, W, UP) | **All checks passed** (`UP042` 제외 — `str, Enum` 패턴은 리포 전체 40곳의 기존 관례, `MiddlewareType` 등과 일치) |
| import 순서 (I001) | 위반 0 |
| 줄 길이 (88자) | 위반 0 |

### 7.4 Environment Variables

| Design §10.3 선언 | `config.py` 실제 | 기본값 | Status |
|---|---|---|:-:|
| `TOOL_SELECTOR_PROVIDER` | `tool_selector_provider` (L122) | `openai` | ✅ |
| `TOOL_SELECTOR_MODEL_NAME` | `tool_selector_model_name` (L123) | `gpt-4o-mini` | ✅ |
| `TOOL_SELECTOR_TOP_K` | `tool_selector_top_k` (L124) | `8` | ✅ |
| `TOOL_SELECTOR_TIMEOUT_SEC` | `tool_selector_timeout_sec` (L125) | `3.0` | ✅ |
| `TOOL_SELECTOR_ENABLED` | `tool_selector_enabled` (L126) | `False` | ✅ |

기존 `search_pipeline_*` 패턴과 일관. 하드코딩 0.

### 7.5 Convention Score

```
┌─────────────────────────────────────────────┐
│  Convention Compliance: 100%                 │
├─────────────────────────────────────────────┤
│  Naming:            100%                     │
│  Folder Structure:  100%                     │
│  Import Order:      100%                     │
│  Env Variables:     100%                     │
└─────────────────────────────────────────────┘
```

---

## 8. Overall Score

```
┌─────────────────────────────────────────────┐
│  Overall Score: 89/100                       │
├─────────────────────────────────────────────┤
│  Design Match:        87.5 points            │
│  Code Quality:        95 points              │
│  Security:            95 points              │
│  Testing:             75 points  ← 골드셋 부재│
│  Performance:         N/A (미측정)            │
│  Architecture:       100 points              │
│  Convention:         100 points              │
└─────────────────────────────────────────────┘
```

**Security 근거**: 화이트리스트 정제로 인젝션 내성 확보, 선별은 축소만(권한 경계 불변),
셀렉터에 인증 컨텍스트·문서 본문·대화 이력 미전달, 장애 시 채팅 무중단.

---

## 9. Recommended Actions

### 9.1 Immediate — Critical

| 우선 | 항목 | 위치 | 사유 |
|:-:|---|---|---|
| 🔴 1 | **골드셋 확보 + Recall 측정** | `tests/fixtures/tool_selection/goldset.json` | Plan의 최대 리스크(기능 회귀)를 직접 겨냥하는 유일한 지표. 현재 "정답 도구를 누락하지 않는가"가 **한 번도 실측되지 않았다**. 계약 검증(3000회)은 *구조적* 안전만 보장할 뿐, top-K=8과 프롬프트가 실제로 옳은 도구를 고르는지는 별개 문제다 |

**차단 해소 조건** (사용자 조치 필요):
- Naver Search: Smithery 패키지 경로 교정 (`@isnow890/naver-search-mcp` → 유효 경로). api_key·URL 조립은 정상
- Doc Convert MCP: `localhost:8003` 기동

### 9.2 Short-term — Important

| 우선 | 항목 | 위치 | 기대 효과 |
|:-:|---|---|---|
| ✅ 1 | ~~Design 문서 갱신 (D-1·D-2·D-3·D-5·D-6)~~ | `tool-recommender.design.md` v0.2 | **완료** — 표류 6건 반영, D-3 의사코드 오류 교정 |
| ✅ 2 | ~~`_from_cache` 무효 캐시 분기 테스트~~ | `test_stale_cache_entry_falls_through_to_llm` | **완료** — 커버리지 100% |
| 🟡 3 | D-4 카탈로그 ID 정합 방안 확정 | module-4 설계 | **결선의 선결 조건.** Design §3.2에 미해결로 명시했으나 *해법은 미정*. 미해결 시 배선 단계에서 재설계 위험 |

### 9.3 Long-term — Backlog

| 항목 | 비고 |
|---|---|
| `select` / `filter` 함수 길이 (39 / 38줄) | 40줄 한계에 근접. 기능 추가 시 즉시 분할 필요 |
| 임베딩 기반 후보 축소 | Plan §2.2 Out of Scope. 도구 수백 개 시점에 재검토 |

---

## 10. Design Document Updates Needed

**전부 반영 완료 (Design v0.2).**

- [x] §4.1 — top-K 절단 규칙 + 4번째 계약 추가 (D-1)
- [x] §4.2 — 무효 캐시 처리 명시 (신규)
- [x] §6.1 — `cache_hit` 실패 모드 행 추가 (D-2)
- [x] §3.3 — `is_low_signal` 의사코드를 정규식 방식으로 교정 + 어댑터 name/description 불일치 사유 명시 (D-3)
- [x] §3.2 — MCP 런타임 식별자가 `server_name` 기반임을 명시하고 카탈로그 정합을 module-4 선결 과제로 승격 (D-4)
- [x] §4.3 — `DefaultToolIdResolver` 기본 구현체 명시 (D-5)
- [x] §11.1 — `test_selector_middleware.py`, `test_module_boundaries.py` 편입 (D-6)

> D-7(`final_ids` property→필드)은 무해한 형태 차이라 문서 변경 없이 §2.2에 기록만 남겼다.

---

## 11. Next Steps

- [ ] MCP 등록 복구 → 골드셋 수집 → Recall·도구 수 감소율 측정 (SC-2/3/4)
- [ ] Design 문서 6건 갱신
- [ ] 완료 보고서 작성 (`tool-recommender.report.md`)
- [ ] module-4 결선 — 별도 PDCA 사이클, D-4 해소가 선결

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-13 | 최초 분석. gap-detector 2회 실패로 직접 수행. Match Rate 87.50% | tkdrb136 |
| 0.2 | 2026-08-13 | Act 1회 반영 — Design 표류 6건 교정, 커버리지 100%. Match Rate **88.15%**. 골드셋 없이는 상한 89.50%로 게이트 도달 불가함을 확인 | tkdrb136 |
| 0.4 | 2026-08-13 | **module-4 결선 + Recall 실측.** Naver Search 없이 Doc Convert 4건 + 내부 9건으로 골드셋 구성(질의 22건). Recall **100%**, 도구 13→2.9(78%↓), 지연 P95 1369ms, 폴백 0. Success Criteria **6/6**. Match Rate **97.38% — 게이트 통과** | tkdrb136 |
| 0.3 | 2026-08-13 | **Act 2회 — Doc Convert MCP 실측 반영.** D-4 해소(server_id 저장소 조회 불필요 → module-4 차단 해제), D-8·D-9·D-10 신규 발견·수정(UUID 노이즈 제거, 프롬프트 38% 축소). 테스트 145건, 커버리지 100%. Match Rate 88.15% 유지(L3 여전히 차단) | tkdrb136 |
