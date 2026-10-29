# agent-memory-injection Planning Document

> **Summary**: 부서 배포 에이전트 실행 경로(RunAgentUseCase → WorkflowCompiler)에 General Chat과 동일한 개인∪부서 메모리 상주 주입을 배선한다.
>
> **Project**: sangplusbot — idt (백엔드)
> **Version**: 기준 커밋 fcabcde
> **Author**: 배상규 + Claude
> **Date**: 2026-10-29
> **Status**: Draft
> **원천**: `docs/proposals/2026-10-15.md` 후보 #3

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 사용자 메모리(소속·용어·선호)는 General Chat 경로에만 주입된다. 심사역이 실제로 쓰는 부서 배포 에이전트는 메모리를 전혀 받지 못해 매 대화 사내 용어를 재설명해야 한다. |
| **Solution** | `WorkflowCompiler.compile()`의 사용자 컨텍스트 prepend 자리에 `memory_block` kwarg를 한 항 추가하고, `RunAgentUseCase`가 대화 실행 직전 1회 `MemoryContextAssembler.build_block()`을 호출해 넘긴다. 실패는 `""`로 격리한다. |
| **Function/UX Effect** | 에이전트 답변이 사용자가 등록한 용어·선호를 반영한다. 화면·API·DB 변경 없음. `include_user_context=False`인 시스템 봇은 그대로다. |
| **Core Value** | growing-agent Phase 1 검증 목표 "메모리 주입이 답변 품질을 올리는가"를 주 경로(에이전트 실행)에서 측정 가능하게 만든다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 메모리 주입이 General Chat 한정이라 부서 배포 에이전트 사용자(P1)는 혜택이 없다 |
| **WHO** | P1 심사역(부서 배포 에이전트로 대화) · P2 에이전트 소유자(include_user_context로 제어) |
| **RISK** | 개인 메모리가 스케줄·웹훅 산출물이나 서브에이전트로 새어 나가는 노출 범위 확대 |
| **SUCCESS** | 대화 실행 런의 supervisor 프롬프트에 메모리 블록 포함 · 조립 실패 시 런 정상 · include_user_context=False 시 미주입 · 기존 compiler·run_agent 테스트 무수정 통과 |
| **SCOPE** | 백엔드 3파일(컴파일러 kwarg 1 · 유스케이스 호출 1 · main.py DI 1) + 테스트. 서브에이전트·검색 파이프라인·비대화 경로 제외 |

---

## 1. Overview

### 1.1 Purpose

에이전트 실행 경로에서 supervisor 시스템 프롬프트에 사용자 메모리 블록을 상주 주입한다. General Chat 경로(`general_chat/use_case.py`)에 이미 있는 "agent 생성 직전 1회 조립 → 프롬프트 prepend" 동작을 에이전트 경로에 동형으로 옮긴다.

### 1.2 Background

- agent-memory(2026-07-20, Phase 1)는 General Chat을 "순수 검증 무대"로 한정해 주입을 배선했다. 이후 org-scope·extraction이 같은 경로 위에 쌓였고 에이전트 경로 확장 사이클은 없었다.
- USER-SCENARIOS S2 "심사역이 사내 용어로 질문 → 메모리 자동 주입"의 주인공은 부서 배포 에이전트 사용자다. 현재 상태로는 시나리오가 성립하지 않는다.
- 코드 확인(2026-10-29): `memory_block|memory_assembler` 참조는 `general_chat/use_case.py`·`api/main.py`뿐이다. `workflow_compiler.py`·`run_agent_use_case.py`는 0건.
- 이음매는 이미 있다. `workflow_compiler.py:594-640`이 "날짜 → 사용자 → wiki 목차 → supervisor_prompt" 순으로 prepend하고, 사용자 블록은 `include_user_context`로 게이팅된다. `main.py:2516 get_memory_assembler()` 싱글톤도 재사용 가능하다.

### 1.3 Related Documents

- 원천 제안: `docs/proposals/2026-10-15.md` §2-3
- 선례(General Chat 주입): `idt/docs/archive/2026-07/agent-memory/agent-memory.design.md` §3-3 결정 ③
- 조립기: `idt/src/application/memory/context_assembler.py`
- 블록 순서 선례: runtime-datetime-context(`idt/docs/archive/2026-08/_INDEX.md`), rag-auth-filter-fix D5
- 비전: `idt/docs/architecture/growing-agent-vision.md` §5 Phase 1
- 위키: `docs/wiki/backend/architecture-overview.md` §2(a) "메모리 상주 주입은 General Chat 경로에만"

---

## 2. Scope

### 2.1 In Scope

- [ ] `WorkflowCompiler.compile()`에 `memory_block: str = ""` keyword-only 인자 추가. 사용자 블록 뒤, wiki 목차 앞에 prepend한다.
- [ ] `include_user_context=False`면 memory_block도 prepend하지 않는다(컴파일러 내부 게이팅, 호출자 실수 방어).
- [ ] `RunAgentUseCase.__init__`에 `memory_assembler=None` optional 의존성 추가. 대화 실행 경로(`_prepare_graph`, auth_ctx 존재)에서 compile 직전 1회 `build_block(request.user_id, request_id, dept_ids=auth_ctx.department_ids)` 호출.
- [ ] `main.py` `_build_run_agent_uc`에 `memory_assembler=get_memory_assembler()` 1줄 추가.
- [ ] 테스트: 컴파일러 prepend 순서·게이팅, 유스케이스 호출 조건(auth_ctx 유무·include_user_context), 실패 격리, DI 배선.
- [ ] 위키 `architecture-overview.md` §2(a) 문구 갱신은 **사용자가 `/wiki update`를 호출할 때만** (자동 갱신 금지).

### 2.2 Out of Scope (사용자 확정 2026-10-29)

- **서브에이전트 주입**: 최상위(depth=0)만. `_compile_sub_agent` 재귀에 memory_block을 넘기지 않는다. 서브에이전트는 부모가 넘긴 task로 동작하므로 개인 메모리 노출 범위를 넓히지 않는다(wiki 목차·미들웨어 플랜과 같은 정책).
- **비대화 경로**: 스케줄·웹훅·백그라운드·승인 재개(`_resume_graph`)에는 주입하지 않는다. 소유자 개인 메모리가 스케줄·웹훅 산출물에 섞여 나가는 것을 막는다.
  > Act-1 정정(Analysis G1): 당초 "auth_ctx가 없으므로"로 적었으나 **웹훅은 소유자 `owner_ctx`를, 백그라운드 잡은 요청자 `ctx`를 auth_ctx로 넘긴다**. 따라서 auth_ctx 유무로 대화 여부를 판정하지 않고, 대화 라우트(WS·REST·SSE)만 `inject_memory=True`로 opt-in한다(기본 False, fail-closed).
- **검색 파이프라인(rewrite→search→validate)**: 사용자 블록은 들어가지만 메모리는 넣지 않는다. 용어 메모리가 검색어 재작성에 유용한지는 실측 후 후속.
- 에이전트별 별도 플래그(`include_memory`)·전역 킬스위치: `include_user_context` 게이팅만 쓴다. 마이그레이션·프론트 변경 0.
- 워커 LLM 프롬프트·생성 노드(문서/발표/엑셀) 주입.
- 메모리 자동 추출 kickoff(에이전트 경로): Phase 3 항목, 별도 사이클.
- 주입 여부의 ai_run 기록·관측 필드 추가.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `compile(..., memory_block="")`이 주어진 블록을 사용자 블록 뒤·wiki 목차 앞에 prepend한다 (순서: 날짜 → 사용자 → 메모리 → wiki 목차 → 본문) | High | Pending |
| FR-02 | `include_user_context=False`면 memory_block이 비어 있지 않아도 prepend하지 않는다 | High | Pending |
| FR-03 | memory_block은 `_compile_sub_agent` 재귀 호출에 전달되지 않는다 (depth=0 한정) | High | Pending |
| FR-04 | `RunAgentUseCase`는 호출자가 `inject_memory=True`로 opt-in한 대화 실행 경로(WS·REST·SSE 라우트)에서만 `build_block()`을 호출한다. 웹훅·백그라운드·스케줄·RAGAS·`_resume_graph`는 호출 0회 (Act-1 정정: auth_ctx 유무는 기준이 아니다) | High | Pending |
| FR-05 | `build_block` 호출은 런당 1회, compile 직전. `dept_ids=list(auth_ctx.department_ids)` 전달(개인∪부서 병합) | High | Pending |
| FR-06 | `memory_assembler=None`(미주입)이면 기존 동작과 바이트 동일 — 기존 테스트 무수정 통과 | High | Pending |
| FR-07 | 조립 실패(예외)는 `""`로 격리되어 런이 정상 진행된다. 조립기 FR-07 선례와 동형(warning 로그, 스택 포함) | High | Pending |
| FR-08 | 검색 파이프라인 `user_context_block`에는 메모리를 포함하지 않는다 | Medium | Pending |
| FR-09 | `agent.include_user_context=False`면 유스케이스 단계에서 `build_block` 호출 자체를 생략한다(불필요 DB 조회 회피) | Medium | Pending |
| FR-10 | main.py DI: `_build_run_agent_uc`가 `get_memory_assembler()`를 주입한다 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 성능 | 런당 추가 DB 조회 2회(개인·부서) 이내, 프롬프트 증가 ≤ `memory_inject_token_cap`(800자) | 조립기 캡 로직 재사용, 단위 테스트로 호출 횟수 고정 |
| 회귀 | 기존 `tests/application/agent_builder/`·`run_agent` 스위트 무수정 통과 | `uv run python -m pytest tests/application/agent_builder tests/application/general_chat` |
| 격리 | 메모리 조회·조립 실패가 런 실패로 전파되지 않음 | 예외 주입 테스트 |
| 보수성 | 블록 헤더의 "모순·불확실 시 사용자에게 확인" 지침 그대로 유지(금융 도메인 오염 방지) | 조립기 `_BLOCK_HEADER` 무수정 |
| 로깅 | 주입 시 `memory block injected`(count) 로그 기존 유지, request_id 포함 | 조립기 로그 재사용 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-10 구현 및 테스트 통과 (테스트 선행 작성, Red → Green)
- [ ] `test_workflow_compiler.py`·`test_workflow_compiler_sub_agent.py`·`test_identity_subject_wiring.py` 등 기존 스위트 무수정 통과
- [ ] General Chat 주입 테스트(`tests/application/general_chat/test_memory_injection.py`) 무영향
- [ ] main.py import 및 앱 기동 확인
- [ ] 실경로 확인 1건: 메모리 등록 → 에이전트 대화 → LangSmith/로그에서 supervisor 프롬프트에 `[사용자 메모리]` 블록 확인 (환경 가능 시, 불가 시 E2E 이월 체크리스트에 추가)

### 4.2 Quality Criteria

- [ ] 함수 40줄·if 중첩 2단계 규칙 준수 (compile()은 이미 길므로 블록 조립을 헬퍼로 분리 검토)
- [ ] 코드 주석에 `Design Ref:` 연결
- [ ] 신규 파일 0 · 마이그레이션 0 · 프론트 diff 0 · API 계약 변경 0

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 개인 메모리가 의도치 않은 경로(스케줄·웹훅·서브에이전트)로 노출 | High | Low | FR-03·FR-04로 구조적 차단, 각 경로 호출 0회 테스트 고정 |
| 프롬프트 길이 증가로 supervisor 라우팅 품질 저하 | Medium | Low | 800자 캡 유지, 블록 위치는 본문 앞(supervisor_prompt 무변경) |
| 메모리 내용이 에이전트 지침과 충돌(예: 포맷 선호 vs 에이전트 출력 규칙) | Medium | Medium | 블록 헤더 "모순 시 사용자에게 확인" 지침 유지. 충돌 사례는 Phase 2 👎 환류로 수집 |
| `compile()` 인자 추가가 다른 호출자(테스트 더블·`_resume_graph`)를 깨뜨림 | Medium | Low | keyword-only + 기본값 `""`, 기존 호출자 무수정 |
| 조립기 세션(session_factory per-call)이 런 요청 세션과 별개 — 트랜잭션 경계 혼선 | Low | Low | 읽기 전용 조회, General Chat 선례 동일. 요청 세션에서 commit 금지 규칙 무관 |
| 에이전트 소유자가 메모리 주입을 끄고 싶은데 `include_user_context`를 끄면 사용자 정보도 빠짐 | Low | Medium | 이번 사이클은 수용(사용자 확정). 요구 발생 시 별도 플래그 후속 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `WorkflowCompiler.compile()` | Application 메서드 시그니처 | keyword-only `memory_block: str = ""` 추가, prepend 순서에 한 항 삽입 |
| `RunAgentUseCase.__init__` | Application 생성자 | optional `memory_assembler=None` 추가 |
| `RunAgentUseCase._prepare_graph` | Application 흐름 | compile 직전 `build_block` 1회 호출(조건부) |
| `main.py _build_run_agent_uc` | DI | `memory_assembler=get_memory_assembler()` 1줄 |
| `MemoryContextAssembler` | 재사용 | 변경 없음. 호출자 2개(General Chat + 에이전트)로 증가 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `compile()` | CALL | `run_agent_use_case.py:751` `_prepare_graph` (대화 실행) | memory_block 전달 — **변경 지점** |
| `compile()` | CALL | `run_agent_use_case.py:1040` `_resume_graph` (승인 재개) | 미전달(기본 `""`) — None |
| `compile()` | CALL | `workflow_compiler.py:1319` `_compile_sub_agent` 재귀 | 미전달 — None (FR-03) |
| `compile()` | CALL | 테스트 더블·`tests/application/agent_builder/*` | 기본값으로 무수정 — None |
| `RunAgentUseCase(...)` | CONSTRUCT | `main.py:3235` | DI 1줄 — Needs verification(import·기동) |
| `RunAgentUseCase(...)` | CONSTRUCT | 테스트 `_make_uc` 류, 스케줄·웹훅·백그라운드 잡 팩토리 | `memory_assembler` 기본 None — None |
| `get_memory_assembler()` | CALL | `main.py:2724` General Chat DI | 싱글톤 공유 — None |
| `search_pipeline user_context_block` | READ | `workflow_compiler.py` → `search_pipeline.py:359` | 메모리 미포함(FR-08) — None |

### 6.3 Verification

- [ ] 위 호출자 전부 기본값으로 무수정 통과 확인
- [ ] 권한·인증 변경 없음(auth_ctx 읽기만)
- [ ] API·스키마·DB 변경 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (Thin DDD: domain → application → infrastructure) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 블록 조립 위치 | (a) 유스케이스가 조립해 컴파일러에 문자열 전달 / (b) 컴파일러가 assembler를 의존성으로 받아 내부 조립 | **(a)** | General Chat 선례 동형. 컴파일러는 user_id·auth_ctx 해석 책임이 없고, `_resume_graph`·서브에이전트 미주입이 호출자 선택으로 자연스럽게 표현됨 |
| 게이팅 | include_user_context 재사용 / 신규 agent 필드 / 전역 플래그 | **include_user_context 재사용** | 사용자 확정. 마이그레이션·프론트 0. "사용자 개인화 블록" 범주가 같다 |
| 서브에이전트 | depth=0만 / 체인 전파 / 항상 전파 | **depth=0만** | 사용자 확정. 노출 범위 최소·토큰 절약 |
| 비대화 경로 | auth_ctx 있을 때만 / user_id 기준 / 재개만 포함 | **auth_ctx 있을 때만** | 사용자 확정. 스케줄 산출물 오염 방지, 재개는 스냅샷 원문 유지 |
| 검색 파이프라인 | supervisor만 / 검색도 | **supervisor만** | 사용자 확정. S 규모 유지, 효과는 실측 후 |
| 블록 순서 | 사용자 뒤·wiki 앞 / wiki 뒤 | **사용자 뒤·wiki 앞** | General Chat "사용자 → 메모리 → 규칙"과 일치. wiki 목차는 도구 사용 힌트라 본문에 더 가깝다 |
| 실패 격리 | 조립기 내부 try(기존) + 유스케이스 외곽 try | **둘 다** | 조립기가 이미 `""` 반환하지만 DI 오류 등 조립기 밖 예외도 런을 죽이지 않도록 유스케이스에서 한 번 더 감쌈(미들웨어 prepare 선례) |

### 7.3 Clean Architecture Approach

```
interfaces/   (변경 없음)
application/
  agent_builder/workflow_compiler.py   compile(memory_block=)  ← prepend 1항
  agent_builder/run_agent_use_case.py  _prepare_graph: build_block 1회 → compile
  memory/context_assembler.py          재사용 (무변경)
infrastructure/ (변경 없음 — MemoryRepository 재사용)
api/main.py    DI 1줄
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` 코딩 규칙(함수 40줄·중첩 2단계·logger 필수·세션 규칙)
- [x] `docs/rules/db-session.md` — 조립기 session_factory per-call 읽기 패턴 준수
- [x] `docs/rules/logging.md` — warning에 exception= 전달
- [x] `docs/rules/testing.md` — TDD, `uv run python -m pytest`

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 코드 주석 | `Design Ref:` 관례 존재 | 변경 3곳에 `Design Ref: agent-memory-injection §…` 부착 | Medium |
| optional 의존성 | None 기본 선례(chart·tracker·memory_assembler·prompt_guard) | 동일 패턴 유지 | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (없음) | `memory_inject_token_cap` 등 기존 설정 재사용 | Server | ☐ |

---

## 9. Next Steps

1. [ ] `/pdca design agent-memory-injection` — 컴파일러 prepend 헬퍼 분리 여부, 유스케이스 호출 지점·테스트 플랜 확정
2. [ ] Do: 테스트 선행 → 구현 3파일 → 회귀 스위트
3. [ ] 실경로 확인 또는 `docs/wiki/ops/e2e-carryover-checklist.md` 메모리 절에 항목 추가
4. [ ] 후속 후보 기록: 검색 파이프라인 주입, 에이전트 경로 메모리 추출 kickoff, 별도 `include_memory` 플래그

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-29 | 초안. 사용자 확정 4건(게이팅=include_user_context, 서브에이전트 제외, auth_ctx 있을 때만, 검색 파이프라인 제외) 반영 | 배상규 + Claude |
