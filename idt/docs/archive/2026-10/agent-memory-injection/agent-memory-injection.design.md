# agent-memory-injection Design Document

> **Summary**: 에이전트 실행 경로(RunAgentUseCase → WorkflowCompiler)의 supervisor 프롬프트에 개인∪부서 메모리 블록을 상주 주입한다. 신규 파일 0, 수정 3파일(컴파일러·유스케이스·main.py DI) + 테스트.
>
> **Project**: sangplusbot — idt (백엔드)
> **Version**: 기준 커밋 fcabcde
> **Author**: 배상규 + Claude
> **Date**: 2026-10-29
> **Status**: Draft
> **Planning Doc**: [agent-memory-injection.plan.md](../../01-plan/features/agent-memory-injection.plan.md)

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

### 1.1 Design Goals

1. General Chat 주입(`general_chat/use_case.py` "agent 생성 직전 1회 조립 → prepend")을 에이전트 경로에 **동형**으로 옮긴다. 조립기·정렬·캡·실패 격리는 전부 재사용한다.
2. 기존 호출자(승인 재개·서브에이전트 재귀·테스트 더블·스케줄/웹훅 팩토리)는 **무수정**으로 동작이 바이트 동일해야 한다. optional 의존성(None 기본) + keyword-only 기본값 `""` 패턴.
3. 게이팅·격리 조건을 **헬퍼 한 곳**에 고정해 테스트 단위를 작게 만든다(C안).

### 1.2 Design Principles

- **탈착형 이음매**: `memory_assembler=None`이면 호출 0회, 프롬프트 불변 (`docs/wiki/backend/patterns/detachable-module-seam.md`).
- **노출 최소**: auth_ctx 없음 · depth>0 · include_user_context=False 중 하나라도 해당하면 주입하지 않는다.
- **실패는 degradation**: 조립 실패는 "" — 런 실패로 승격하지 않는다 (`degradation-vs-failure-boundary.md`).
- **컨텍스트 캡 불변**: `memory_inject_token_cap`(800자) 그대로.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | compile kwarg + `_prepare_graph` 인라인 호출 | prepend 조립 포트 추출, GC·검색 파이프라인까지 통일 | compile kwarg + 유스케이스 헬퍼 1 + 컴파일러 prepend 헬퍼 1 |
| **New Files** | 0 | 2~3 | 0 |
| **Modified Files** | 3 | 5~6 | 3 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium (`_prepare_graph` 비대) | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | 함수 40줄 규칙 충돌 | Plan 범위 초과, 회귀 면 확대 | Low |
| **Recommendation** | 핫픽스 | prepend 3벌 통합 사이클 | **선택** |

**Selected**: Option C — **Rationale**: 사용자 확정(2026-10-29). 게이팅·격리 조건이 `_build_memory_block` 한 곳에 모여 테스트가 단순하고, 컴파일러 prepend 순서가 헬퍼로 묶여 40줄 규칙을 지킨다. prepend 3벌(GC·컴파일러·검색) 통합은 범위 밖으로 남긴다.

### 2.1 Component Diagram

```
WS/REST/SSE 대화 라우터 ──auth_ctx + inject_memory=True──▶ RunAgentUseCase.stream/execute
                                │
                                ▼ _prepare_graph(inject_memory=…)
                     ┌──────────────────────────────┐
                     │ _build_memory_block(agent,   │   memory_assembler (optional)
                     │   request, auth_ctx, req_id, │──▶ MemoryContextAssembler.build_block
                     │   inject_memory=)            │     (user_id, request_id, dept_ids)
                     │  · inject_memory False → ""  │     개인∪부서 병합 · 800자 캡 · 실패 ""
                     │  · assembler None → ""       │
                     │  · auth_ctx None → ""        │
                     │  · include_user_context F→"" │
                     │  · 예외 → warning + ""       │
                     └──────────────┬───────────────┘
                                    │ memory_block: str
                                    ▼
              WorkflowCompiler.compile(..., memory_block=)
                     _render_prepend_blocks(auth_ctx, include_user_context,
                                            memory_block, wiki_toc_block)
                     → datetime + user_ctx + memory + wiki_toc + supervisor_prompt
                                    │
                     _compile_sub_agent(...)  ← memory_block 미전달 (depth>0 "")
                     search_pipeline(user_context_block=…) ← 메모리 미포함

_resume_graph / 스케줄 / 웹훅(auth_ctx=owner_ctx) / 백그라운드(auth_ctx=ctx) / RAGAS
   → inject_memory 미전달(기본 False) → memory_block "" — 주입 없음 (Act-1, Analysis G1)
```

> **Act-1 정정**: 당초 "auth_ctx 없음 = 비대화"로 가정했으나 웹훅·백그라운드 잡은 auth_ctx를 조립해 넘긴다. 대화 여부는 **호출자 opt-in(`inject_memory=True`)** 으로만 판정한다. 기본 False(fail-closed).

### 2.2 Data Flow

```
request.user_id + auth_ctx.department_ids
  → MemoryRepository.find_active_by_user(scope='user') ∪ find_active_by_departments
  → MemoryPolicy.sort_for_injection_scoped → truncate_to_budget(800)
  → "[사용자 메모리]\n…\n---\n\n"  (0건이면 "")
  → compile(memory_block=…)
  → effective_supervisor_prompt = datetime + user_ctx + memory + wiki_toc + body
  → supervisor / final_answer LLM system prompt
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `RunAgentUseCase` | `MemoryContextAssembler` (optional, duck-typed `build_block`) | 블록 조립 1회 |
| `WorkflowCompiler.compile` | `memory_block: str` (값만) | prepend. 조립기·user_id를 알지 않는다 |
| `main.py _build_run_agent_uc` | `get_memory_assembler()` 싱글톤 | DI (General Chat과 같은 인스턴스 공유) |

---

## 3. Data Model

변경 없음. `agent_memory`(V050) 읽기만. 마이그레이션 0.

---

## 4. API Specification

변경 없음. 요청·응답·이벤트 payload 모두 동일. `api-contract-sync` 불필요.

---

## 5. UI/UX Design

해당 없음(프론트 diff 0). Design Anchor 섹션 제거.

---

## 6. Detailed Design

### 6.1 `WorkflowCompiler.compile()` — `src/application/agent_builder/workflow_compiler.py`

**D1. 시그니처**: keyword-only `memory_block: str = ""` 추가 (`subject_user_id` 뒤).

**D2. prepend 헬퍼 분리** — 현재 compile() 본문에 흩어진 날짜·사용자·wiki 목차 조립을 묶는다.

```python
async def _render_prepend_blocks(
    self, *, auth_ctx, include_user_context: bool, memory_block: str,
    workflow, agent_id, request_id,
) -> tuple[str, str, str]:
    """(user_context_block, datetime_block, prefix) — prefix는 supervisor_prompt 앞에 붙는 전체.

    Design Ref: agent-memory-injection §6.1 D3 — 순서: 날짜 → 사용자 → 메모리 → wiki 목차.
    memory_block은 include_user_context 게이팅을 사용자 블록과 공유한다(FR-02).
    """
    user_context_block = render_user_context_block(auth_ctx) if include_user_context else ""
    effective_memory = memory_block if include_user_context else ""
    datetime_block = render_datetime_block(self._agent_timezone, logger=self._logger)
    wiki_toc_block = await self._render_wiki_toc(workflow, agent_id, request_id)
    prefix = datetime_block + user_context_block + effective_memory + wiki_toc_block
    return user_context_block, datetime_block, prefix
```

- 반환 중 `user_context_block`·`datetime_block`은 기존대로 검색 파이프라인·워커에 전달된다. **메모리는 prefix에만** 들어간다(FR-08).
- 구현 정정(Analysis G5): 실제 반환은 **4-튜플** `(user_context_block, datetime_block, wiki_toc_block, prefix)` — wiki 목차는 wiki_read 워커 prompt 이중 주입에 재사용되므로 따로 돌려준다. `_render_wiki_toc` 소형 헬퍼는 만들지 않고 조건(`has_wiki_read and provider and agent_id`)을 헬퍼 안에 인라인했다(39줄, 40줄 규칙 안).

**D3. 순서**: `datetime → user_context → memory → wiki_toc → supervisor_prompt`. General Chat "날짜 → 사용자 → 메모리 → 규칙"과 정합. wiki 목차는 도구 사용 힌트라 본문에 가깝게 둔다.

**D4. 서브에이전트 미전달**: `_compile_sub_agent(...)` 호출에 `memory_block`을 넘기지 않는다 → 재귀 compile은 기본값 `""`. 명시적 주석으로 의도를 고정한다(FR-03).

**D5. 회귀 불변식**: `memory_block=""`(기본)이면 prefix 문자열이 변경 전과 바이트 동일.

### 6.2 `RunAgentUseCase` — `src/application/agent_builder/run_agent_use_case.py`

**D6. 생성자**: `memory_assembler=None` optional 인자 추가, `self._memory_assembler`에 보관. docstring에 "None이면 주입 비활성(하위호환)".

**D7. 헬퍼**

```python
async def _build_memory_block(
    self, agent, request, auth_ctx, request_id: str,
) -> str:
    """Design Ref: agent-memory-injection §6.2 D7 — 대화 실행 경로 전용 조립.

    Plan FR-04/FR-09: auth_ctx 없음(스케줄·웹훅·재개) 또는
    include_user_context=False면 조회 자체를 건너뛴다.
    Plan FR-07: 조립기 밖 예외(DI·속성 오류)도 런을 죽이지 않는다.
    """
    # Act-1 (Analysis G1): 대화 라우트만 opt-in — 웹훅·백그라운드도 auth_ctx 를 넘긴다.
    if not inject_memory or self._memory_assembler is None or auth_ctx is None:
        return ""
    if not agent.include_user_context:
        return ""
    try:
        return await self._memory_assembler.build_block(
            request.user_id, request_id,
            dept_ids=list(auth_ctx.department_ids),
        )
    except Exception as e:
        self._logger.warning(
            "memory block build failed — run continues without",
            request_id=request_id, agent_id=agent.id, exception=e,
        )
        return ""
```

**D8. 호출 지점**: `_prepare_graph`에서 `compile()` 직전 1회. `_resume_graph`는 **수정하지 않는다**(기본 ""). 호출 순서는 `_inject_attached_skills` 뒤·compile 앞 — 스킬 병합과 독립.

**D9. user_id 출처**: `request.user_id` (General Chat `request.user_id`와 동형). `auth_ctx.user_id`가 아닌 이유: 대화 경로에서는 둘이 같고, 조립기 계약이 user_id 문자열이며 `subject_user_id`와도 일치한다.

### 6.3 `main.py` — `_build_run_agent_uc`

**D10.** `memory_assembler=get_memory_assembler(),` 1줄 추가. 주석 `# agent-memory-injection D10: General Chat과 같은 싱글톤 공유`.

### 6.4 변경하지 않는 것(명시)

| 대상 | 이유 |
|------|------|
| `MemoryContextAssembler` | 계약 그대로 재사용. `_BLOCK_HEADER` 지침 무수정 |
| `search_pipeline.py` | 메모리 미포함(Plan 확정) |
| `_compile_sub_agent` 시그니처 | 전달하지 않으므로 인자 불필요 |
| `_resume_graph` | auth_ctx 없음 → 미주입 |
| `AgentDefinition` 스키마 | 별도 플래그 없음 |
| General Chat 유스케이스 | 무영향 |

---

## 7. Error Handling

| 상황 | 처리 | 결과 |
|------|------|------|
| 메모리 조회 DB 오류 | 조립기 내부 FR-07 → warning + "" | 런 정상, 메모리 없이 답변 |
| 조립기 밖 예외(속성·DI) | D7 try/except → warning(exception=) + "" | 런 정상 |
| 메모리 0건 | 조립기 FR-06 → "" (빈 헤더 금지) | 프롬프트 불변 |
| 캡 초과 | 조립기 절단 + debug 로그 | 800자 이내 |
| auth_ctx None | 조회 생략 | 프롬프트 불변 |

로깅: 기존 `memory block injected`(count, request_id) 재사용. 신규 로그는 D7 warning 1종.

---

## 8. Security Considerations

- [x] 개인 메모리 노출 범위: 대화 실행 런 최상위 supervisor만. 스케줄·웹훅·백그라운드·재개·RAGAS·서브에이전트 차단(FR-03·FR-04) — 호출자 opt-in(`inject_memory=True`, 기본 False) + 테스트(U7~U9, W2·W3)로 고정. Act-1에서 "auth_ctx 유무" 게이팅이 웹훅·백그라운드를 통과시키던 결함(G1/G2)을 수정.
- [x] 부서 메모리는 `auth_ctx.department_ids`(서버 조립 권한 컨텍스트)로만 결정. 요청 본문 값 사용 없음.
- [x] 블록 헤더의 보수적 지침("모순·불확실 시 사용자에게 확인") 유지 — 금융 도메인 오염 방지.
- [x] prompt-guard 검사 지점(그래프 생성 전)은 사용자 입력 대상이며 메모리 블록은 사용자가 승인·등록한 데이터라 추가 검사 없음. 간접 인젝션 확장은 별도 후보(제안서 §5).

---

## 9. Test Plan

> 테스트 선행(Red) → 구현(Green). 기존 스위트는 무수정 통과가 회귀 0의 증거다.

### 9.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| 단위 (컴파일러) | prepend 순서·게이팅·서브에이전트 미전달·기본값 불변 | pytest + `_make_compiler` 패턴 | Do |
| 단위 (유스케이스) | `_build_memory_block` 조건 4종 + 호출 횟수 + 실패 격리 | pytest + `_bare_run_uc` 패턴(`test_identity_subject_wiring.py`) | Do |
| 배선 | main.py `_build_run_agent_uc`가 assembler를 넘김 | AST/소스 계약 테스트 또는 import 검사 | Do |
| 회귀 | `tests/application/agent_builder`, `tests/application/general_chat` | pytest | Check |
| 실경로 | 메모리 등록 → 에이전트 대화 → 프롬프트 확인 | 로컬 서버 + LangSmith/로그 | Check(가능 시) 또는 E2E 이월 |

### 9.2 컴파일러 — `tests/application/agent_builder/test_workflow_compiler_memory.py` (신규)

| # | 테스트 | 기대 |
|---|--------|------|
| C1 | `memory_block="[사용자 메모리]…"` 전달, include_user_context=True | supervisor system prompt에 블록 포함, 사용자 블록 **뒤**·wiki 목차/본문 **앞** |
| C2 | include_user_context=False + 비어 있지 않은 memory_block | 프롬프트에 블록 없음(FR-02) |
| C3 | memory_block 미전달 | 프롬프트가 변경 전과 동일(D5) — 기존 `test_e2e_final_answer_includes_user_context_block`과 같은 패치로 비교 |
| C4 | sub_agent 워커 포함 워크플로우 + memory_block 전달 | 재귀 compile 호출의 `memory_block` 인자 없음/"" (`test_workflow_compiler_sub_agent.py` 픽스처 재사용) |
| C5 | 검색 워커 + memory_block | search 파이프라인에 전달된 `user_context_block`에 메모리 문자열 없음(FR-08) |
| C6 | 날짜·사용자·메모리·wiki 목차 4종 모두 존재 | 인덱스 순서 datetime < user < memory < toc < body |

### 9.3 유스케이스 — `tests/application/agent_builder/test_run_agent_memory_wiring.py` (신규)

| # | 테스트 | 기대 |
|---|--------|------|
| U1 | assembler 주입 + auth_ctx(부서 2개) + include_user_context=True | `build_block(user_id, request_id, dept_ids=[d1,d2])` 1회, compile에 `memory_block=반환값` 전달 |
| U2 | assembler None | build_block 호출 없음, compile `memory_block` 미전달 또는 "" |
| U3 | auth_ctx None (스케줄 동형) | 호출 0회(FR-04) |
| U4 | agent.include_user_context=False | 호출 0회(FR-09) |
| U5 | build_block이 예외 | warning 로그 1회, compile은 `memory_block=""`로 정상 호출(FR-07) |
| U6 | `_resume_graph` 경로 | 호출 0회, compile에 memory_block 미전달 |
| U7 | inject_memory=False + auth_ctx 있음 (Act-1) | 호출 0회, memory_block "" |
| U8 | `_prepare_graph` 기본 호출(inject_memory 미전달) — 웹훅·백그라운드 동형 (Act-1) | 호출 0회 |
| U9 | `stream`/`execute` 시그니처 (Act-1) | `inject_memory` keyword-only, 기본 False |
| U10 | 기존 `test_identity_subject_wiring.py` 전체 | 통과 (픽스처 1줄 `uc._memory_assembler = None` 추가 — 의도된 편차) |

### 9.4 배선 — `tests/api/test_memory_injection_di.py` (신규; 파일명은 Analysis G6 반영)

| # | 테스트 | 기대 |
|---|--------|------|
| W1 | `_build_run_agent_uc` 소스에 `memory_assembler=get_memory_assembler()` 존재 (AST 계약, `ast-source-contract-tests.md` 선례) | 통과 |
| W2 | 대화 라우트(ws_router 1곳, agent_builder_router 2곳)의 `stream/execute(auth_ctx=…)` 호출이 `inject_memory=True`를 넘김 (Act-1) | 통과 |
| W3 | 웹훅·백그라운드·스케줄 유스케이스 소스에 `inject_memory` 없음 (Act-1) | 통과 |

### 9.5 Seed / 실경로 확인

| 항목 | 내용 |
|------|------|
| 데이터 | `/api/v1/memories`로 용어 메모리 1건 등록(예: "ETC = 외부 여신 한도") |
| 절차 | include_user_context=True 에이전트로 대화 → 로그 `memory block injected count=1` + LangSmith supervisor system prompt에 `[사용자 메모리]` 확인 |
| 대조 | include_user_context=False 에이전트에서 로그 없음 |
| 불가 시 | `docs/wiki/ops/e2e-carryover-checklist.md` 메모리 절에 항목 추가(위키 갱신은 사용자 `/wiki update` 호출 시) |

---

## 10. Clean Architecture

### 10.1 This Feature's Layer Assignment

| Component | Layer | Location | 변경 |
|-----------|-------|----------|------|
| `WorkflowCompiler.compile` / `_render_prepend_blocks` | Application | `src/application/agent_builder/workflow_compiler.py` | 수정 |
| `RunAgentUseCase._build_memory_block` | Application | `src/application/agent_builder/run_agent_use_case.py` | 수정 |
| `MemoryContextAssembler` | Application | `src/application/memory/context_assembler.py` | 무변경 |
| `MemoryRepository` | Infrastructure | `src/infrastructure/memory/repository.py` | 무변경 |
| DI | Interfaces/Composition | `src/api/main.py` | 1줄 |

의존 방향: application → application(동일 레이어 협력자, duck-typed) / infrastructure는 조립기 내부에서만 지연 import(기존). domain → infrastructure 참조 없음.

---

## 11. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| optional 의존성 | `None` 기본 + 생성자 주석 "None이면 비활성(하위호환)" — chart·tracker·prompt_guard 선례 |
| 함수 길이 | `_render_prepend_blocks`·`_build_memory_block` 각 ≤ 25줄. compile() 본문은 헬퍼 추출로 순감 |
| 로깅 | `self._logger.warning(..., exception=e)` — StructuredLogger가 exc_info로 변환 |
| 주석 | `Design Ref: agent-memory-injection §6.x Dn` / `Plan SC: FR-nn` |
| 테스트 명명 | 기존 파일 관례(한글 메서드명 허용) 따름 |
| 실행 | `uv run python -m pytest tests/application/agent_builder tests/application/general_chat -q` |

---

## 12. Implementation Guide

### 12.1 File Structure

```
src/application/agent_builder/workflow_compiler.py      (수정: D1~D5)
src/application/agent_builder/run_agent_use_case.py     (수정: D6~D9)
src/api/main.py                                          (수정: D10)
tests/application/agent_builder/test_workflow_compiler_memory.py   (신규: C1~C6)
tests/application/agent_builder/test_run_agent_memory_wiring.py    (신규: U1~U6)
tests/api/test_memory_injection_di.py                              (신규: W1~W3)
src/api/routes/ws_router.py · src/api/routes/agent_builder_router.py (Act-1: 대화 라우트 inject_memory=True 3곳)
```

### 12.2 Implementation Order

1. [ ] C1~C6 테스트 작성 → 실패 확인
2. [ ] 컴파일러 D1~D5 구현 → C1~C6 통과 + 기존 compiler 스위트 통과
3. [ ] U1~U6 테스트 작성 → 실패 확인
4. [ ] 유스케이스 D6~D9 구현 → U1~U7 통과
5. [ ] W1 테스트 → main.py D10 → 통과 + `python -c "import src.api.main"` 확인
6. [ ] 회귀: `tests/application/agent_builder` + `tests/application/general_chat` 전체
7. [ ] 실경로 확인(가능 시) 또는 E2E 이월 기록

### 12.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 컴파일러 prepend | `module-1` | D1~D5 + C1~C6 | 15-20 |
| 유스케이스 조립 + DI | `module-2` | D6~D10 + U1~U7 + W1 | 15-20 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | 전체(`module-1,module-2` — S 규모라 한 세션 권장) | 30-40 |
| Session 2 | Check + Report | 전체 | 20-30 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-29 | 초안. Option C 선택(사용자 확정). D1~D10, 테스트 C/U/W 플랜 | 배상규 + Claude |
| 0.2 | 2026-10-29 | Act-1: Analysis G1/G2 반영 — `inject_memory` opt-in(대화 라우트만 True), §2.1·§6.1 D2·§6.2 D7·§8·§9·§12 정정, 테스트 U7~U9·W2·W3 추가 | 배상규 + Claude |
