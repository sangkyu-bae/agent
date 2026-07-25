# Wiki Agentic Navigation Planning Document

> **Summary**: 에이전트가 자기 위키를 벡터 검색(임베딩 top_k)으로만 만나는 현행 구조에, **목차 주입 + 명시적 열람 도구(`wiki_read`)** 라는 문서 탐색 계층을 추가 — 에이전트가 위키 전체상(폴더·최근 결정)을 인지하고 필요한 문서를 스스로 골라 읽게 하며, 열람 행위가 tool_call 로그로 남아 "읽었는지"가 결정적으로 관측되게 한다
>
> **Project**: sangplusbot (idt 백엔드 중심)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-23
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 위키 소비가 `use_wiki_first` 벡터 검색 단일 경로라 3가지 구조적 한계가 있음: ① 에이전트가 자기 위키에 뭐가 있는지 전체상을 모름(목차·최근 결정사항 질의 불가) ② 위키가 원본 청크와 같은 top_k 슬롯을 놓고 경쟁해 "정제된 상위 지식"이라는 위상이 반영 안 됨 ③ 검색 결과에 섞여 들어가므로 "위키를 읽고 참고했는지" 관측이 애매하고, 위키 hit이 LLM에게 `[출처: unknown]`으로 표시되는 결함까지 있음 (llm-wiki-runtime-flow.md §5) |
| **Solution** | ① 신규 내부 도구 `wiki_read` 등록 — 에이전트가 위키 문서를 id로 명시적으로 열람(승인+미만료+자기 agent_id만). 도구 선택 자체가 opt-in이라 신규 컬럼·마이그레이션 0 ② `wiki_read` 선택 에이전트의 시스템 프롬프트에 승인 위키 **목차 블록**(경로 트리·제목·갱신일, 상한 적용) 주입 — 기존 `list_tree_items`(V051) + user context block prepend 선례 재사용 ③ 기존 벡터 경로는 무변경 유지(독립 opt-in, 교차검증 기준선)하되 `[출처: unknown]` 표기만 위키 식별 표기로 편승 수정 |
| **Function/UX Effect** | "최근 결정사항 알려줘", "X 폴더 문서 기준으로 답해줘" 같은 구조적·시간적 질의가 목차 → `wiki_read` 드릴다운으로 처리 가능. 운영자는 run 상세의 tool_call 기록(`wiki_read` + article_id 인자)으로 어떤 위키 문서를 읽었는지 문서 단위로 확인 — 임베딩 경로에서 불가능했던 결정적 읽음 관측 확보 |
| **Core Value** | 위키를 "검색 결과의 경쟁자"에서 "항상 참조 가능한 상위 지식 계층"으로 격상 — 탐색(지도)과 벡터(의미 매칭)의 상호보완 구조. agentic retrieval 방향과 정합하며, 후속 인용 강제(attribution) 없이도 열람 관측이 설계 차원에서 해결됨 |

---

## 1. Overview

### 1.1 Purpose

에이전트별 LLM 위키의 소비 방식을 벡터 검색 단일 경로에서
**목차 인지 → 선택적 열람(agentic navigation)** 이중 계층으로 확장한다.
교체가 아니라 계층 추가다 — 기존 `use_wiki_first` 벡터 경로는 의미 매칭 폴백으로 유지한다.

### 1.2 Background (2026-07-23 코드 추적 기반 — `docs/llm-wiki-runtime-flow.md`)

**현행 구조**: 위키는 시스템 프롬프트에 로드되지 않는다. `use_wiki_first=True`인 RAG 도구가
검색을 실행할 때만 `RunScopedWikiSearch` → `WikiFirstSearchUseCase` → Qdrant `wiki_knowledge`
벡터 검색 → MySQL 하이드레이션(APPROVED+미만료 필터) 경로로 top_k 슬롯에 편입된다.

**구조적 한계 (벡터 검색이 못 푸는 문제)**:

1. **전체상 부재** — 에이전트는 top_k개 조각만 보며, 자기 위키에 어떤 폴더·문서·최근 결정이
   있는지 영원히 모른다. "최근 결정사항", "X 관련 문서 다 봐줘" 같은 구조적/시간적 질의는
   임베딩 유사도로 잡히지 않는다.
2. **위상 불일치** — 위키(정제된 결정사항)가 원본 청크와 동일한 검색 슬롯을 경쟁한다.
   위키 hit이 top_k를 채우면 원본 검색이 스킵되고, 반대로 유사도가 낮으면 위키가 아예 빠진다.
3. **관측 애매** — 검색 결과에 섞여 들어가므로 "읽었는지"는 `ai_retrieval_source.fusion_source='wiki'`
   로 추적 가능하나 "그 문서를 의도적으로 참고했는지"는 불투명. 명시적 열람 도구는 이 문제를
   tool_call 로그로 설계 차원에서 해결한다.
4. **기지 결함** — 위키 hit의 metadata에 `source` 키가 없어 `_format_results`가
   `[출처: unknown]`으로 렌더링 (`tools.py:431`). LLM이 위키인 줄 모른다.

**재사용 가능한 기존 부품**:

- `WikiArticleRepository.list_tree_items(agent_id)` — path 트리·제목·상태·갱신일 경량 목록
  (V051 wiki-user-facing). 단, **전체 status 반환**이므로 프롬프트 주입용 승인 필터 필요
- `workflow_compiler.py`의 `render_user_context_block` prepend 패턴 — 프롬프트 블록 주입 선례
- `RunScopedWikiSearch`의 per-call `session_factory` 패턴 — 싱글톤 ToolFactory에서 안전한 세션 수명
- `RunContext`(ContextVar)의 agent_id — 도구 레벨 에이전트 격리 선례
- `record_tool_call` 트래킹 — 도구 호출 자동 영속화 (`ai_tool_call`)

### 1.3 Related Documents

- 런타임 읽기 흐름 분석: `docs/llm-wiki-runtime-flow.md` (본 기능의 문제 정의 근거)
- 위키 도입: LLM-WIKI-001 (`src/application/wiki/*` docstring), wiki-user-facing (V051 path 트리)
- 도구 카탈로그·이중 네임스페이스: `docs/rules/tool-and-mcp.md` (내부 도구 추가 시 필수 확인)
- 프롬프트 블록 주입 선례: supervisor-overblock-fix plan §6.2 (user context block)

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. `wiki_read` 내부 도구 신규 등록**: `tool_registry`에 메타 추가 + `ToolFactory.create()`
      분기 + 도구 구현. 입력 `article_id` → RunContext의 agent_id 소유 검증 + APPROVED+미만료
      필터 통과 항목만 본문 반환(제목·경로·갱신일 포함). 불일치/미승인/만료 시 명확한 실패 텍스트
- [ ] **S2. 위키 목차 블록 주입**: `wiki_read`가 선택된 에이전트의 시스템 프롬프트에
      승인+미만료 위키의 경로 트리(제목·path·갱신일 내림차순)를 렌더링해 주입.
      건수·바이트 상한 적용(초과 시 최신순 절단 + 절단 표시). 위키 0건이면 블록 자체 미주입
- [ ] **S3. 승인 목차 조회 경로**: `list_tree_items`의 승인+미만료 필터 변형
      (신규 repo 메서드 또는 파라미터 — Design에서 확정). 기존 관리화면용 전체 목록 동작 불변
- [ ] **S4. `[출처: unknown]` 편승 수정**: `WikiFirstSearchUseCase._to_result`의 metadata에
      위키 식별 표기(예: `source="wiki:{title}"`) 추가 — 벡터 경로 위키 hit이 LLM에게 위키로 인지되게
- [ ] **S5. 열람 관측성 확인**: `wiki_read` 호출이 기존 tool_call 트래킹으로 `ai_tool_call`에
      (도구명 + article_id 인자) 기록됨을 테스트로 고정 — "어떤 위키 문서를 읽었는가" 조회 가능
- [ ] **S6. 테스트 (TDD)**: ① wiki_read 소유/승인/만료 가드 ② 목차 렌더링(상한·0건·승인 필터)
      ③ 프롬프트 조립(선택 시 주입·미선택 시 부재) ④ 기존 use_wiki_first 경로 무회귀
- [ ] **S7. E2E 수동 검증**: "최근 결정사항 알려줘" 류 질의가 목차 → `wiki_read` 경유로
      답변되는지 run 상세 tool_call 실측

### 2.2 Out of Scope

- 기존 `use_wiki_first` 벡터 경로 제거·변경 (S4 metadata 추가 제외 무변경 — 교차검증 기준선 유지)
- 위키 생성·증류·승인 플로우 변경 (읽기 계층만)
- general_chat 경로 적용 (custom agent(agent_builder) 경로 한정 — 효과 확인 후 후속)
- 인용 강제·groundedness 평가 등 답변 반영(attribution) 검증 (후속: wiki-usage-attribution)
- DB 스키마 변경 (마이그레이션 0 — 도구 선택이 opt-in이므로 신규 컬럼 불필요)
- 프론트 위키 관리 화면 변경 (도구 카탈로그 노출은 기존 카탈로그 API 경유 — §6.2 결정 참조)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `wiki_read`가 내부 도구 카탈로그에 등록되어 에이전트 편집에서 선택 가능하다 (이중 네임스페이스 규약 준수: 카탈로그 `internal:wiki_read` ↔ 저장 `wiki_read`) | High | Pending |
| FR-02 | `wiki_read(article_id)`는 RunContext agent_id 소유 + APPROVED + 미만료 항목만 본문을 반환하고, 그 외에는 사유가 드러나지 않는 일관된 실패 텍스트를 반환한다 (타 에이전트 위키 열람 차단) | High | Pending |
| FR-03 | `wiki_read` 선택 에이전트의 시스템 프롬프트에 승인 위키 목차 블록(제목·path·갱신일)이 주입된다 — 건수·바이트 상한 및 절단 표시 포함 | High | Pending |
| FR-04 | 승인 위키 0건이면 목차 블록이 주입되지 않고, `wiki_read` 미선택 에이전트의 프롬프트는 바이트 단위 불변이다 | High | Pending |
| FR-05 | `wiki_read` 호출이 `ai_tool_call`에 도구명+article_id 인자로 기록되어 run 조회 API로 열람 문서를 확인할 수 있다 | High | Pending |
| FR-06 | 기존 `use_wiki_first` 벡터 경로·미선택 에이전트·graph 외부 검색 호출의 동작이 무회귀다 | High | Pending |
| FR-07 | 벡터 경로 위키 hit이 `[출처: unknown]` 대신 위키 식별 표기로 LLM에 렌더링된다 | Medium | Pending |
| FR-08 | E2E: 목차 기반 질의("최근 결정사항")가 `wiki_read` 경유로 답변된다 (수동 — run tool_call 실측) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 토큰 예산 | 목차 블록 상한(건수 N + 바이트 상한, config화 — 하드코딩 금지) 초과 시 최신순 절단 | 렌더링 테스트 단언 |
| 아키텍처 | 도구 구현은 application/infrastructure 레이어(도메인에 LangChain 금지), 세션은 per-call session_factory (DB-001) | verify-architecture 스킬 |
| TDD | 테스트 선행 (Red → Green → Refactor) | verify-tdd 스킬 |
| 로깅 | 신규 로그 LOG-001 준수 (structured, print 금지) | verify-logging 스킬 |
| 마이그레이션 | 0건 (신규 테이블·컬럼 없음) | git diff 확인 |
| 성능 | 목차 조회는 본문 미포함 경량 쿼리(`list_tree_items` 계열) — 컴파일 경로에 본문 로드 금지 | 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] `wiki_read` 선택 에이전트에서 "최근 결정사항 알려줘" 질의 시 목차 인지 → `wiki_read`
      호출 → 해당 문서 기반 답변 (run 상세 tool_call 실측)
- [ ] run 조회로 "이 답변에서 어떤 위키 문서를 열람했는지"가 article_id 단위로 확인됨
- [ ] 미선택 에이전트·기존 벡터 경로 전부 무회귀 (기존 pytest, 사전 실패분 제외 기준)
- [ ] 벡터 경로 위키 hit이 위키 식별 출처로 렌더링됨 (테스트 단언)

### 4.2 Quality Criteria

- [ ] Gap 분석(Match Rate) >= 90%
- [ ] 함수 40줄·if 중첩 2단계 규칙 준수, 상한값 config화(하드코딩 금지)

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 프롬프트 조립 시점(compile)에 async DB 조회가 구조적으로 불가하거나 지연 유발 | High | Medium | Design에서 주입 지점 확정: compile 경로가 async면 그 자리에서, 아니면 그래프 시작 노드에서 state 주입(첨부 블록 선례). 경량 쿼리(본문 미포함)로 지연 최소화 |
| LLM이 목차만 보고 `wiki_read`를 호출하지 않음 (도구 설명 품질 의존) | Medium | Medium | 목차 블록에 "상세 내용은 wiki_read로 열람" 사용 지시 명시 + 도구 description에 목차와의 관계 서술. E2E(FR-08)로 실효 확인 |
| 목차가 커져 시스템 프롬프트 토큰 팽창 | Medium | Low | 건수·바이트 상한 + 최신순 절단(NFR). 에이전트당 위키는 현재 수십 건 규모 |
| 타 에이전트 위키 열람(수평 권한 상승) | High | Low | FR-02 소유 검증을 repo 쿼리 조건(agent_id)으로 강제 — 도구 인자 신뢰 금지. 가드 테스트 필수 |
| `list_tree_items` 필터 변형이 관리화면 목록에 회귀 | Medium | Low | 기존 메서드 시그니처 불변 — 신규 메서드/opt-in 파라미터로 추가 (독립 opt-in 관례). 기존 테스트 무회귀 확인 |
| 도구 카탈로그 노출 시 프론트 계약 어긋남 | Low | Medium | 이중 네임스페이스 규약(`internal:wiki_read` ↔ `wiki_read`) 준수 + 카탈로그 API 응답 확인. 프론트 코드 변경이 필요해지면 api-contract-sync 체크리스트 수행 |
| LLM 비결정성으로 E2E 불안정 | Medium | Medium | 단위 검증(가드·렌더링·조립)은 결정적으로, E2E는 보조 실측(FR-08)으로 한정 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules | Web apps | ☐ |
| **Enterprise** | Strict layer separation | 기존 프로젝트 구조 (Thin DDD) | ☑ |

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| opt-in 단위 | 신규 agent 컬럼 / RagToolConfig 필드 / **도구 선택 자체** | 도구 선택 (`wiki_read` 추가 여부) | 마이그레이션·신규 필드 0. 기존 도구 선택 메커니즘 재사용 — 도구가 선택되면 목차 주입도 활성화. "독립 opt-in, 기존 설정 보존" 관례 부합 |
| 목차 주입 지점 | compile 시 프롬프트 prepend / 그래프 시작 노드 state 주입 | Design에서 확정 | user context block(prepend)과 첨부 블록(노드) 양 선례 존재 — compile 경로의 async 가능 여부로 결정 |
| 열람 대상 식별자 | article_id / path 문자열 | article_id (목차에 id 병기) | path는 중복·개명에 취약. 목차 블록에 id를 함께 렌더링해 LLM이 그대로 인용 |
| 목차 조회 | `list_tree_items` 수정 / 승인 필터 신규 경로 | 신규 경로 (기존 불변) | 관리화면(전체 status 노출)과 프롬프트(승인만)는 요구가 다름 — 기존 호출부 무영향 |
| 벡터 경로 처리 | 제거 / 유지 | 유지 (S4 표기 수정만) | 탐색=지도, 벡터=의미 매칭으로 상호보완. 교차검증 기준선 보존 |
| 출처 표기 | `wiki` 고정 / `wiki:{title}` | Design에서 확정 | title 포함이 후속 인용 강제(attribution)에 유리하나 포맷 파괴 범위 확인 필요 |

### 6.3 변경 대상 파일 (예상)

```
idt/src/
├── domain/agent_builder/tool_registry.py            # S1: wiki_read 메타 등록
├── infrastructure/agent_builder/tool_factory.py     # S1: wiki_read 생성 분기 (session_factory 주입)
├── infrastructure/wiki/wiki_read_tool.py            # S1: 도구 구현 (신규 — RunScopedWikiSearch 패턴)
├── infrastructure/wiki/wiki_repository.py           # S3: 승인 목차/단건 열람 조회 경로
├── application/agent_run/prompt_rendering.py        # S2: render_wiki_toc_block (신규 함수)
├── application/agent_builder/workflow_compiler.py   # S2: 목차 블록 주입 (지점은 Design 확정)
├── application/wiki/wiki_first_search_use_case.py   # S4: metadata source 표기
└── tests/
    ├── infrastructure/wiki/ (도구 가드·목차 조회)     # S6: FR-01/02/05
    ├── application/agent_run/ (렌더링)               # S6: FR-03/04
    ├── application/agent_builder/ (조립)             # S6: FR-03/04/06
    └── application/wiki/ (출처 표기)                  # S6: FR-07
```

> 정확한 주입 지점·목차 포맷·상한값·출처 표기 형식은 Design 단계에서 확정.

---

## 7. Convention Prerequisites

- [x] 검증 스킬 존재: verify-architecture, verify-logging, verify-tdd
- [x] 백엔드 테스트 격리 실행 관례 (Windows 이벤트 루프 flakiness)
- [x] 도구 추가 시 `docs/rules/tool-and-mcp.md` 필수 확인 (이중 네임스페이스 포함)
- 환경변수 신규 없음(상한값은 기존 settings 패턴), **마이그레이션 0**, 프론트 계약은 카탈로그
  자동 노출 여부 확인 후 필요 시 api-contract-sync

---

## 8. Implementation Guide

### 8.1 구현 순서

```
1. FR-02/05  wiki_read 도구: 가드 테스트 먼저 (소유·승인·만료·실패 텍스트) → 도구 구현 → registry/factory 등록 (FR-01)
2. FR-03/04  목차: 승인 목차 조회 테스트 → repo 경로 추가 → 렌더링 테스트 → render_wiki_toc_block → 조립 테스트 → 주입 배선
3. FR-07     출처 표기: _to_result 테스트 갱신 → metadata 수정
4. FR-06     전체 pytest 무회귀 (격리 실행) + verify-architecture/logging/tdd
5. FR-08     E2E 수동: 목차 질의 → run 상세 tool_call(wiki_read + article_id) 실측
```

### 8.2 검증 자료

- 열람 확인: `GET /agents/runs/{run_id}` tool_calls에서 `wiki_read` + arguments.article_id
- 목차 주입 확인: LangSmith trace 시스템 프롬프트 전문 (또는 조립 테스트 단언)
- 재현 질의: "이 에이전트가 아는 최근 결정사항 알려줘" / "○○ 문서 내용 기준으로 답해줘"

---

## 9. Next Steps

1. [ ] Write design document (`/pdca design wiki-agentic-navigation`) — 주입 지점(compile vs 노드)·목차 포맷·상한 config·출처 표기 확정
2. [ ] 구현 (TDD)
3. [ ] Gap 분석 (`/pdca analyze wiki-agentic-navigation`)
4. [ ] 후속 검토: wiki-usage-attribution (인용 강제 — 답변 반영 여부 검증), general_chat 경로 확장

### 9.1 후속 진화 경로 (2026-07-23 설계 토론 확정 — 본 기능이 1단계 골격)

판단·요약은 쓰기 시점으로, 탐색은 질문 시점에 계층만 타게, 병렬 전체 읽기는 명시적
deep 모드로 격리한다. 트리거 조건 충족 전에는 착수하지 않는다 (YAGNI).

| 후속 기능 (가칭) | 내용 | 착수 트리거 |
|------------------|------|------------|
| **wiki-folder-summaries** | 쓰기 시점 폴더 요약 계층: 문서 승인/갱신 시 해당 폴더 설명을 증류하고 상위 폴더로 전파(기존 wiki distiller·피드백 팬아웃 패턴 재사용). 목차 블록을 "폴더 설명 목록"으로 교체 + `wiki_list(path)` 도구 추가 → 폴더 설명 → 진입 → 문서 목록 → `wiki_read` 뎁스 탐색. 라우팅 검색 4부작(청킹→섹션→문서 요약→라우팅)과 동일 설계 사상의 위키 적용 | 승인 위키가 목차 상한(`wiki_toc_max_items`/`max_bytes`)에 걸리기 시작할 때 |
| **deep-wiki-research** | "위키 전체를 뒤져서 정리해줘" 류 종합 질의 전용의 병렬 fan-out + map-reduce 종합 워커(별도 모드). 일상 챗 경로와 격리해 비용·지연 오염 방지 — supervisor 라우팅으로 분기 | 폴더 계층 도입 후, 종합형 질의 수요가 실측될 때 |
| **wiki-knowledge-promotion** | 에이전트 간 지식 승격: 개별 에이전트 위키의 검증된 지식을 부서/전사 공유 위키로 올리는 축 (agent-memory-org-scope Phase 3의 부서 공유 패턴을 위키에 적용) | 복수 에이전트가 동일 도메인 지식을 중복 축적하는 사례 확인 시 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-23 | Initial draft — llm-wiki-runtime-flow.md 코드 추적 + 탐색형 전환 설계 토론 기반 | 배상규 |
