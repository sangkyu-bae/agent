# tool-recommender Planning Document

> **Summary**: 바인딩 직전 유저 질의에 맞는 도구만 골라내는 경로 독립적 선별 모듈 — 도구가 늘어나도 추천 품질이 무너지지 않게 한다.
>
> **Project**: sangplusbot (idt / 백엔드)
> **Version**: 0.1
> **Author**: tkdrb136
> **Date**: 2026-08-13
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | General Chat이 활성 MCP 서버의 도구를 **전부** 한 번에 `create_agent(tools=[...])`로 바인딩한다 (`general_chat/tools.py:98`). 도구 수 상한이 없어 서버가 늘수록 프롬프트에 수십~수백 개 도구 설명이 실리고, LLM이 엉뚱한 도구를 고르기 시작한다. |
| **Solution** | 경량 LLM 1콜로 후보 도구를 top-K 선별하는 **독립 모듈**(`ToolSelectorPort` + LLM 구현체)을 만든다. 어떤 실행 경로에도 종속되지 않고, 호출부는 "도구 목록 → 도구 목록" 한 줄. 결과는 **필수 세트 ∪ 추천 결과**로 합집합 처리해 기능 회귀를 원천 차단. |
| **Function/UX Effect** | 바인딩 도구 수가 유의미하게 감소해 도구 오선택이 줄고, 프롬프트 토큰·응답 지연이 함께 개선된다. 사용자가 체감하는 변화는 "엉뚱한 도구를 부르지 않는다" 하나. |
| **Core Value** | **도구 카탈로그 확장성의 잠금 해제.** 지금은 MCP 서버를 늘리는 것이 곧 품질 저하지만, 선별 레이어가 생기면 도구를 늘려도 에이전트가 망가지지 않는다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 도구 전량 바인딩 구조라 도구 수 증가가 곧 추천 품질 저하로 이어진다 (General Chat은 상한 자체가 없음) |
| **WHO** | P2 (KB 운영자 / 에이전트 소유자) — MCP 서버를 계속 추가하려는 운영자. 부차적으로 General Chat 최종 사용자 |
| **RISK** | 선별이 정답 도구를 누락시켜 기존에 되던 질의가 실패하는 **기능 회귀** |
| **SUCCESS** | 골드셋 Recall ≥ 95% (필수 세트 포함 기준), 평균 바인딩 도구 수 감소, 모듈 제거 시 기존 경로 무변경 동작 |
| **SCOPE** | Phase 1 = 경로 독립 선별 모듈 + 골드셋 테스트 (배선 없음). Phase 2(별건) = 실제 경로 결선 |

---

## 1. Overview

### 1.1 Purpose

에이전트에 바인딩되는 도구 집합을 **런타임에 유저 질의 기준으로 좁히는** 선별 모듈을 만든다.
"도구를 추천하는 책임"을 실행 그래프·유스케이스에서 분리해, 이후 어떤 경로에든 붙였다 뗐다 할 수 있는 단일 모듈로 응집시킨다.

### 1.2 Background

현 구조를 조사한 결과, **도구 선별 레이어가 존재하지 않는다.**

| 경로 | 현재 바인딩 방식 | 근거 | 상태 |
|------|-----------------|------|------|
| **General Chat** | 활성 MCP 서버 전체의 도구 + 내부 도구 2종을 한 번에 바인딩 | `general_chat/tools.py:92-98` → `load_mcp_tools_use_case.py:25-50` (`find_all_active` 전량 순회) → `use_case.py:275,392` | **문제 발생 중.** 도구 수 캡 없음 — `MCPConnectionPolicy.MAX_SERVERS=20`(`domain/mcp/policy.py:21`)은 *서버* 상한일 뿐 |
| **커스텀 에이전트** | 빌드 타임에 사용자가 ≤5개 수동 선택 → worker 1개당 도구 1개 | `policies.py:87-110` (`MAX_TOOLS=5`), `workflow_compiler.py:352,359` | 캡 덕에 당장은 무사. 런타임 선별은 없고 LLM supervisor가 *worker* 단위로만 라우팅 (`supervisor_nodes.py`) |

즉 문제의 진원지는 General Chat이지만, 근본 원인은 **"질의와 무관하게 도구를 통째로 넘긴다"**는 공통 설계다.
LangChain의 `wrap_model_call` + `request.override(tools=...)` 필터링 패턴은 스킬 문서(`.claude/skills/langchain-middleware/SKILL.md:658`)에만 있고 `src/`에서 미사용이다.

### 1.3 Related Documents

- 도구·MCP 규칙 (ID 체계·등록 절차): `idt/docs/rules/tool-and-mcp.md`
- 내부 도구 단일 원천: `src/domain/agent_builder/tool_registry.py`
- 아키텍처 규칙: `idt/CLAUDE.md` §2, §6
- 후속: `docs/02-design/features/tool-recommender.design.md` (미작성)

---

## 2. Scope

### 2.1 In Scope

- [ ] `ToolSelectorPort` — domain 계층 인터페이스 (`select(query, candidates) -> list[SelectedTool]`)
- [ ] `LLMToolSelector` — 경량 모델 1콜 구현체 (infrastructure)
- [ ] `ToolCandidate` / `SelectionResult` VO — 실행 프레임워크(LangChain `BaseTool`)에 의존하지 않는 순수 데이터 형태
- [ ] **개별 도구 단위** 식별자 처리 — `internal:{id}` / `mcp:{server_id}:{tool_name}`
- [ ] 필수 세트(`builtin_default`) ∪ 추천 결과 합집합 정책
- [ ] 실패·타임아웃 시 폴백 (필수 세트 보장, 절대 예외 전파 안 함)
- [ ] `SelectionCachePort` 인터페이스 + `NullCache` (v1 no-op 구현체)
- [ ] 골드셋 기반 유닛 테스트 (LLM stub) + 아키텍처 테스트
- [ ] Recall 측정용 평가 스크립트 (수동 실행, CI 제외)

### 2.2 Out of Scope

- **실제 경로 결선** — General Chat / workflow_compiler 어디에 어떻게 붙일지는 Design 단계(Option A/B/C)에서 확정하고, 배선은 별도 Phase
- 임베딩 기반 후보 축소 (하이브리드) — 도구 수백 개 시점에 재검토
- 대화 이력 기반 선별 — v1은 **현재 유저 메시지만** 입력
- 캐시 실구현 (TTL·무효화) — 인터페이스만 정의
- Agent Builder UI의 빌드 타임 도구 추천 (별개 기능)
- MCP ID 정규화 버그(`create_agent_use_case.py:453-463`에서 MCP를 서버 단위로 뭉개 도구명 소실) 수정 — 아래 §5에 리스크로 기록하되 본 기능에서 고치지 않음
- 기존 `MAX_TOOLS=5` 캡 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `ToolSelectorPort`는 `(query: str, candidates: list[ToolCandidate]) -> SelectionResult`를 반환한다. LangChain 타입·DB 세션·HTTP 컨텍스트에 의존하지 않는다 | High | Pending |
| FR-02 | `LLMToolSelector`는 후보의 `(id, name, description)`만 경량 모델에 제시하고 **도구 ID 목록만** 반환받는다 | High | Pending |
| FR-03 | 선별 단위는 **개별 도구**다. MCP 도구는 `mcp:{server_id}:{tool_name}`으로 구분되며 서버 단위로 뭉개지 않는다 | High | Pending |
| FR-04 | 최종 결과 = `필수 세트 ∪ 추천 결과`. 필수 세트는 호출부가 주입한다 (모듈이 `builtin_default`를 직접 조회하지 않음 — 결합도 차단) | High | Pending |
| FR-05 | LLM 실패·타임아웃·파싱 실패 시 예외를 전파하지 않고 **필수 세트만** 담은 `SelectionResult`를 반환하며, 폴백 사유를 `reason` 필드에 남긴다 | High | Pending |
| FR-06 | 모델이 반환한 미지의 ID는 조용히 버리고 WARNING 로그를 남긴다 (환각 방지) | High | Pending |
| FR-07 | top-K 상한은 설정값으로 주입한다. 하드코딩 금지 (CLAUDE.md §3) | High | Pending |
| FR-08 | 후보 수가 top-K 이하면 LLM을 호출하지 않고 전량 통과시킨다 (불필요 비용 차단) | Medium | Pending |
| FR-09 | `SelectionCachePort` 인터페이스를 정의하고 v1은 `NullSelectionCache`를 주입한다 | Medium | Pending |
| FR-10 | 선별 결과(입력 후보 수 / 출력 수 / 폴백 여부 / 소요 ms)를 StructuredLogger로 기록한다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| **정확도 (최우선)** | 골드셋 Recall ≥ 95% — 정답 도구가 최종 집합에서 누락되지 않을 것 | 평가 스크립트, 실 LLM 호출 |
| **효율** | 평균 바인딩 도구 수 감소 (목표: 40개 후보 → 8~10개 수준) | 로그 집계 (FR-10) |
| **지연** | 선별 오버헤드 P95 < 1.5s (경량 모델 1콜) | 로그의 소요 ms |
| **가용성** | 셀렉터 장애가 에이전트 실행을 중단시키지 않을 것 (100% 폴백) | 예외 주입 테스트 |
| **아키텍처** | domain → infrastructure 참조 0건 | `/verify-architecture` |
| **관측성** | print() 0건, 에러 처리 시 스택 트레이스 포함 | `/verify-logging` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-10 전부 구현
- [ ] **골드셋 유닛테스트**: 질의→기대 도구 케이스 20~30개, LLM은 stub 응답 주입. TDD(Red→Green) 준수
- [ ] **Recall 측정**: 실 LLM으로 평가셋 1회 실행, 누락률 리포트를 Design/Report에 첨부
- [ ] **도구 수 감소율**: 대표 질의 세트 기준 before/after 평균 도구 수 기록
- [ ] **탈부착 검증**: 모듈 디렉토리를 제거해도 기존 경로가 그대로 동작함을 확인 (v1은 미배선이므로 자명해야 함) + `/verify-architecture` 통과
- [ ] `/verify-tdd`, `/verify-logging` 통과

### 4.2 Quality Criteria

- [ ] 함수 40줄 이하, if 중첩 2단계 이하 (CLAUDE.md §3)
- [ ] 모든 공개 함수에 명시적 타입 (pydantic / typing)
- [ ] 폴백 경로에 대한 테스트 존재 (LLM 예외 / 타임아웃 / 잘못된 JSON / 미지 ID 각각)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **선별이 정답 도구를 누락 → 기능 회귀** | High | Medium | 필수 세트 합집합(FR-04)으로 baseline 보장 + 골드셋 Recall 게이트. top-K를 넉넉히(8~10) 시작해 점진 축소 |
| 경량 모델이 존재하지 않는 도구 ID 환각 | Medium | High | 화이트리스트 대조 후 미지 ID 폐기(FR-06). 테스트 케이스로 고정 |
| 매 턴 LLM 1콜의 지연·비용 누적 | Medium | High | FR-08 조기 반환 + CachePort로 나중에 교체 가능한 자리 확보(FR-09) |
| **MCP ID 체계 불일치** — 저장/런타임은 `mcp_{server_id}`로 서버 단위 정규화(`create_agent_use_case.py:453-463`)라 도구명이 이미 소실됨. 개별 도구 단위 선별과 어긋남 | High | High | v1 모듈은 카탈로그 ID(`mcp:{server}:{tool}`)만 다루고 **변환 책임을 호출부에 남긴다**. 저장 스키마는 건드리지 않음 (CLAUDE.md §4 "DB 스키마 임의 변경 금지"). 배선 Phase에서 정면으로 다룸 |
| 도구 description 품질이 낮아 선별 근거 부족 | Medium | Medium | 내부 도구는 `tool_registry.py`가 이미 상세 설명 보유. MCP는 서버 제공 description에 의존 — 품질 미달 시 리포트에 기록 |
| 모듈이 결국 특정 경로에 얽혀 탈부착 불가해짐 | High | Low | domain Port 의존만 허용하고 아키텍처 테스트로 강제. 필수 세트를 모듈이 직접 조회하지 않는 것(FR-04)이 핵심 방어선 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/domain/tool_selection/` (신규) | Domain 인터페이스·VO | `ToolSelectorPort`, `SelectionCachePort`, `ToolCandidate`, `SelectionResult` 신규 추가 |
| `src/infrastructure/tool_selection/` (신규) | Infrastructure | `LLMToolSelector`, `NullSelectionCache`, 프롬프트 템플릿 |
| `tests/domain/tool_selection/`, `tests/infrastructure/tool_selection/` (신규) | Test | 골드셋 + 폴백 테스트 |
| **기존 파일** | — | **Phase 1에서 변경 없음** (미배선) |

### 6.2 Current Consumers

Phase 1은 신규 모듈만 추가하므로 기존 소비자가 없다. 아래는 **Phase 2 배선 시 영향받을 지점의 사전 인벤토리**다.

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| 도구 목록 (General Chat) | READ | `general_chat/tools.py:75-98` `ChatToolBuilder.build` → `use_case.py:275,392` `_create_agent` | Phase 2에서 Needs verification — 여기가 유력 결선 지점 |
| 도구 목록 (MCP 전량 로드) | READ | `application/mcp_registry/load_mcp_tools_use_case.py:25-50` | None (선별은 이 뒤에서 일어남) |
| 도구 인스턴스화 | READ | `infrastructure/agent_builder/tool_factory.py:78,170` `ToolFactory.create/create_async` | None (Phase 1) |
| 워커 컴파일 | READ | `application/agent_builder/workflow_compiler.py:306-310,352,359` | Phase 2에서 Needs verification |
| 미들웨어 선택 | READ | `workflow_compiler.py:239-243` `MiddlewareProvider.prepare` | Design Option에 따라 결선 후보 |
| 도구 ID 정규화 | READ | `create_agent_use_case.py:453-463` `_normalize_tool_id` | Phase 2에서 **Breaking 가능성** — §5 리스크 참조 |
| 도구 카탈로그 | READ | `application/tool_catalog/sync_*_use_case.py`, `GET /api/v1/tool-catalog` | None (읽기만) |

### 6.3 Verification

- [ ] Phase 1 완료 시 기존 테스트 전량 통과 (신규 모듈이 아무것도 건드리지 않았음의 증명)
- [ ] `/verify-architecture` — domain이 infrastructure를 참조하지 않음
- [ ] 신규 모듈 디렉토리 제거 후에도 `pytest` 전량 통과 (탈부착 검증)
- [ ] DB 스키마·API 계약 변경 없음 → 프론트 동기화 불필요 (루트 CLAUDE.md §4-1 해당 없음)

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| Starter | 단순 구조 | 정적 사이트 | ☐ |
| Dynamic | 기능 단위 모듈 | 백엔드 있는 웹앱 | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DI | 복잡한 아키텍처 | **☑** |

기존 프로젝트가 Thin DDD (domain / application / infrastructure / interfaces) 구조이므로 이를 따른다.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 적용 범위 | General Chat / 커스텀 에이전트 / 공용 모듈 | **경로 독립 공용 모듈** | 사용자 결정 — 붙이는 곳은 나중에 조합. "탈부착 용이" 요구의 직접적 귀결 |
| 선별 방식 | LLM 1콜 / 임베딩 / 하이브리드 / 규칙 | **경량 LLM 1콜** | 사용자 결정 — 구현 단순 + 의도 추론 정확. 임베딩 후보축소는 도구 수백 개 시점에 추가 |
| 선별 단위 | 개별 도구 / MCP 서버 / 계층적 | **개별 도구** | 사용자 결정 — "도구 많아지면 이상한 추천" 문제를 직접 해결. 서버 단위는 50개짜리 서버 하나에 무력 |
| 입력 컨텍스트 | 현재 메시지 / +대화이력 / +시스템프롬프트 | **현재 유저 메시지만** | 사용자 결정 — 순수 함수라 캡싱·테스트·재현이 모두 쉬움 |
| 폴백 정책 | 전체 폴백 / 필수만 / **합집합** / 에러 | **필수 세트 ∪ 추천 결과** | 사용자 결정 — 회귀 위험 최소화와 이상 추천 억제를 동시에 |
| 캐싱 | 없음 / TTL 캐시 / 인터페이스만 | **CachePort 정의 + v1 NullCache** | 사용자 결정 — 교체만 하면 되는 구조. 탈부착 원칙과 일관 |
| **결합 지점** | 미들웨어 / UseCase 서비스 / 그래프 노드 | **Design에서 확정** | 사용자 결정 — Plan은 요구사항·성공기준까지. `/pdca design`의 Option A/B/C 비교로 결정 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

src/
├── domain/tool_selection/          ← 신규. 외부 의존 0
│   ├── interfaces/
│   │   ├── tool_selector_port.py       ToolSelectorPort (ABC)
│   │   └── selection_cache_port.py     SelectionCachePort (ABC)
│   ├── schemas.py                      ToolCandidate, SelectedTool, SelectionResult
│   └── policies.py                     top-K 기본값, 합집합 규칙
│
├── infrastructure/tool_selection/  ← 신규. LLM·로거 여기서만
│   ├── llm_tool_selector.py            LLMToolSelector(ToolSelectorPort)
│   ├── prompts.py                      선별 프롬프트 템플릿
│   └── null_cache.py                   NullSelectionCache(SelectionCachePort)
│
└── application/                     ← Phase 1에서 변경 없음 (배선은 Phase 2)
```

**탈부착 계약**: 이 두 디렉토리를 통째로 지워도 나머지 코드가 컴파일·테스트를 통과해야 한다.
반대로 붙일 때는 호출부에서 `selector.select(...)` 한 줄 + 필수 세트 주입만 하면 된다.
모듈이 `TOOL_REGISTRY`·DB·LangChain을 직접 아는 순간 이 계약은 깨진다.

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` 코딩 규칙 존재 (§3 함수 40줄·중첩 2단계·config 하드코딩 금지)
- [x] `idt/docs/rules/logging.md` — StructuredLogger, print() 금지
- [x] `idt/docs/rules/tool-and-mcp.md` — 도구 ID 체계 (`internal:{id}` / `mcp:{server_id}:{tool}`)
- [x] `idt/docs/rules/testing.md` — TDD Red→Green→Refactor
- [x] pytest 설정 (`pyproject.toml`)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 도구 ID 표기 | 존재 (`tool-and-mcp.md`) — 단 카탈로그/저장 이중 체계 | 모듈 내부는 **카탈로그 표기 단일 사용**으로 고정 | High |
| 폴더 구조 | 존재 (Thin DDD) | `tool_selection` 패키지 배치 (위 7.3) | High |
| 셀렉터 프롬프트 | 없음 | 프롬프트 버전 관리 방식 (상수 vs 파일) | Medium |
| 골드셋 형식 | 없음 | 평가셋 파일 포맷·위치 (`tests/fixtures/tool_selection/`) | Medium |
| 에러 처리 | 존재 (`logging.md`) | 폴백 시 로그 레벨 (WARNING) 통일 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `TOOL_SELECTOR_MODEL` | 셀렉터용 경량 모델 ID | Server | ☑ |
| `TOOL_SELECTOR_TOP_K` | 선별 상한 (기본 8) | Server | ☑ |
| `TOOL_SELECTOR_TIMEOUT_SEC` | LLM 타임아웃 (기본 3) | Server | ☑ |
| `TOOL_SELECTOR_ENABLED` | 배선 후 킬스위치 | Server | ☑ (Phase 2) |

`OPENAI_API_KEY`는 기존 사용분 재사용.

### 8.4 Pipeline Integration

해당 없음 (기존 파이프라인 내 모듈 추가).

---

## 9. Next Steps

1. [ ] `/pdca design tool-recommender` — **결합 지점 Option A/B/C 비교 확정** (미들웨어 `wrap_model_call` / UseCase 서비스 / 그래프 노드)
2. [ ] 골드셋 질의 20~30개 수집 (실제 General Chat 로그에서 추출 권장)
3. [ ] `TOOL_SELECTOR_MODEL` 후보 모델 결정
4. [ ] Design 승인 후 `/pdca do tool-recommender`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-13 | 최초 작성. 코드베이스 조사 + 사용자 확인 8건 반영 | tkdrb136 |
