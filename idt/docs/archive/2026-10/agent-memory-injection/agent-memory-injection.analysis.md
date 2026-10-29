# agent-memory-injection Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) — Check 정적 87% → Act-1 후 런타임 포함 95%
>
> **Project**: sangplusbot — idt (백엔드)
> **Version**: 기준 커밋 fcabcde + 미커밋 워킹트리
> **Analyst**: 배상규 + Claude (gap-detector 에이전트 보고 기반, 핵심 지적은 코드로 재확인)
> **Date**: 2026-10-29
> **Design Doc**: [agent-memory-injection.design.md](../02-design/features/agent-memory-injection.design.md)

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

## Strategic Alignment Check

### Plan Alignment

| Element | Expected | Status |
|---------|----------|:------:|
| Core Problem (WHY) | 에이전트 경로에 메모리 주입 | ✅ Addressed — 대화 런 supervisor/final_answer 프롬프트에 블록 포함 |
| Target User (WHO) | P1 심사역 · P2 소유자 제어 | ✅ Addressed — include_user_context 게이팅 |
| RISK (노출 범위) | 웹훅·스케줄·서브에이전트 차단 | ❌ **웹훅·백그라운드 잡 런에 주입됨** (아래 G1/G2) |

### Success Criteria Status (Plan FR-01~FR-10)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| FR-01 | 순서 날짜 → 사용자 → 메모리 → wiki 목차 → 본문 | ✅ | `workflow_compiler.py` `_render_prepend_blocks` prefix 조립, `compile()` `prefix + workflow.supervisor_prompt` · 테스트 C1/C6 |
| FR-02 | include_user_context=False면 메모리 생략 | ✅ | `effective_memory = memory_block if include_user_context else ""` · C2 |
| FR-03 | 서브에이전트 재귀 미전달 | ✅ | `_compile_sub_agent(...)` 호출에 memory_block 없음 · C4 |
| FR-04 | 대화 경로에서만 호출, 비대화 경로 0회 | ✅ (Act-1) | Check 시점 ❌: 웹훅(`invoke_webhook_agent_use_case.py:78-96` `auth_ctx=owner_ctx`)·백그라운드 잡(`worker.py:290-308` `auth_ctx=ctx`)이 auth_ctx를 넘겨 주입됨. **Act-1**: `stream/execute(inject_memory=False)` opt-in 도입, 대화 라우트 3곳만 True · U7~U9, W2·W3 · 실런 R3(웹훅 동형) build_block 0회 |
| FR-05 | 런당 1회, compile 직전, dept_ids 전달 | ✅ | `_prepare_graph` compile 직전 1회, `dept_ids=list(auth_ctx.department_ids)` · U1 |
| FR-06 | assembler None이면 동작 동일, 기존 테스트 무수정 통과 | ⚠️ | 운영 동작은 동일(생성자 기본 None, 조기 반환). 기존 테스트 `test_identity_subject_wiring.py` 픽스처에 `uc._memory_assembler = None` 1줄 추가(`__new__` 우회 픽스처) |
| FR-07 | 예외 → "" + warning(exception=) | ✅ | `_build_memory_block` try/except · U5 |
| FR-08 | 검색 파이프라인 메모리 미포함 | ✅ | `_create_worker_node_for_category(user_context_block=…)`에 사용자 블록만 · C5 |
| FR-09 | include_user_context=False면 조회 생략 | ✅ | `_build_memory_block` 조기 반환 · U4 |
| FR-10 | main.py DI | ✅ | `_build_run_agent_uc` `memory_assembler=get_memory_assembler()` · W1 |

**Success Rate**: Check 시점 8/10 Met · 1 Partial · 1 Not Met → **Act-1 후 9/10 Met · 1 Partial(FR-06 픽스처 1줄)**

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | 게이팅 = include_user_context 재사용 | ✅ | — |
| [Plan] | 서브에이전트 제외(depth=0만) | ✅ | — |
| [Plan] | auth_ctx 있을 때만 주입 = 대화 경로만 | ❌ → ✅ (Act-1) | **전제 오류**: 웹훅·백그라운드도 auth_ctx를 조립해 넘긴다. Act-1에서 "호출자 opt-in(`inject_memory=True`)"으로 판정 기준을 바꾸고 Plan §2.2·FR-04를 정정 |
| [Plan] | 검색 파이프라인 제외 | ✅ | — |
| [Design] | Option C (헬퍼 2 + DI 1) | ✅ | D2 헬퍼는 4-튜플 반환(wiki_toc_block을 워커 prompt 이중 주입에 재사용해야 함), `_render_wiki_toc` 소형 헬퍼는 인라인 — 문서 갱신 대상 |
| [Design] | D7 `_build_memory_block` 로직 | ✅ | 코드 스니펫·로그 키 일치 |
| [Design] | D8 `_resume_graph` 무수정 | ✅ | — |
| [Design] | §2.1/§8 노출 범위 계약 | ❌ | G1/G2 |

---

## 1. Analysis Overview

- **Design Document**: `docs/02-design/features/agent-memory-injection.design.md`
- **Implementation**: `src/application/agent_builder/workflow_compiler.py`, `src/application/agent_builder/run_agent_use_case.py`, `src/api/main.py`
- **Tests**: `tests/application/agent_builder/test_workflow_compiler_memory.py`(C1~C6), `tests/application/agent_builder/test_run_agent_memory_wiring.py`(U1~U6+생성자), `tests/api/test_memory_injection_di.py`(W1)
- **Method**: gap-detector 정적 분석 + 핵심 지적(G1/G2) 코드 재확인. 런타임 검증은 Act 뒤로 미룸(아래 §2.7)

---

## 2. Gap Analysis

### 2.1 API Endpoints

변경 없음(설계와 일치). 외부 계약 무변경.

### 2.2 Data Model

변경 없음(설계와 일치).

### 2.3 Component Structure

| Design Component | Implementation | Status |
|------------------|----------------|--------|
| `compile(memory_block="")` keyword-only | `workflow_compiler.py` compile 시그니처 | ✅ |
| `_render_prepend_blocks` | `workflow_compiler.py` | ✅ (4-튜플, `_render_wiki_toc` 인라인 — Minor) |
| `RunAgentUseCase.__init__(memory_assembler=None)` | `run_agent_use_case.py` | ✅ |
| `_build_memory_block` | `run_agent_use_case.py` | ✅ |
| `_prepare_graph` 호출 1회 | `run_agent_use_case.py` | ✅ |
| main.py DI | `_build_run_agent_uc` | ✅ |
| `test_main_memory_injection_wiring.py` | `tests/api/test_memory_injection_di.py` | ✅ (파일명 상이 — Minor) |

### 2.4 Functional Depth

| File | Depth | Notes |
|------|:-----:|-------|
| workflow_compiler.py (변경분) | 100 | placeholder 없음 |
| run_agent_use_case.py (변경분) | 90 | 로직 완성. 단, 게이팅 전제(auth_ctx)가 비대화 경로 2곳을 통과시킴 |
| main.py (변경분) | 100 | — |

### 2.6 Contract Verification

| # | Contract | Status |
|---|----------|:------:|
| 1 | `compile(..., memory_block=)` 시그니처 | ✅ |
| 2 | `build_block(user_id, request_id, dept_ids=)` 조립기 계약 | ✅ (`context_assembler.py` 일치) |
| 3 | DI 싱글톤 공유(General Chat과 동일 인스턴스) | ✅ |
| 4 | 외부 API·이벤트 payload 무변경 | ✅ |
| 5 | 노출 범위 계약(Design §2.1/§8: 웹훅·백그라운드·스케줄·재개·서브에이전트 차단) | ❌ → ✅ (Act-1: opt-in + W2/W3 + 실런 R3) |

**Contract Match Rate**: Check 4/5 = 80% → **Act-1 후 5/5 = 100%**

### 2.7 Runtime Verification (Act-1 후, 인프로세스 `TestClient(app)` 실런)

실 MySQL·OpenAI 경로. 관찰은 코드 무수정 — `WorkflowCompiler._render_prepend_blocks`와 `MemoryContextAssembler.build_block`을 스크립트에서 감싸 prefix·호출 기록. 메모리는 `POST /api/v1/memories`로 등록(id=1, domain_term "ETC는 '외부 여신 한도'를 뜻하는 우리 회사 약어다") 후 `DELETE`로 정리(204). 대상 에이전트 `2110b539…`(고객문의 답글 작성, user 7, include_user_context=1).

| # | 시나리오 | 결과 | 증거 |
|---|----------|:----:|------|
| R1 | 대화 REST `POST /agents/{id}/run` (persist_conversation=false) | ✅ | status 200 · `build_block('7', dept_ids=['f1cb4caa…'])` **1회** · prefix 순서 `[현재 날짜]`(0) → `[현재 사용자 정보]` → `[사용자 메모리]`(370) → 본문 · 답변: "상상인플러스저축은행에서 ETC는 '외부 여신 한도'를 의미하는 사내 약어입니다." |
| R3 | 웹훅 동형 `uc.execute(auth_ctx=owner_ctx, viewer…)` **inject_memory 미전달** | ✅ | `build_block` **0회** · prefix에 `[사용자 메모리]` 없음(len 372) · 답변: "ETC는 라틴어 'et cetera'의 약자로…" — 메모리 미반영 확인 |
| R2 | include_user_context=False 에이전트 | ⏭ 미실행 | user 7 소유 에이전트가 전부 include_user_context=1이고 PATCH API에 해당 필드가 없음. 단위 C2/U4로 고정. E2E 이월 체크리스트 메모리 절 후보 |

**Runtime Match Rate**: 실행 2/2 통과, 1건 이월 → 90%

### 2.8 Match Rate Summary

```
Check (static, Act 전):
  Structural 95% · Functional 90% · Contract 80%  → Overall 87%

Act-1 후 (runtime 포함):
  Structural Match Rate:  100%  (G5/G6 문서 정정으로 해소)
  Functional Match Rate:   95%  (FR 9 Met + FR-06 Partial)
  Contract Match Rate:    100%
  Runtime Match Rate:      90%  (R1·R3 통과, R2 이월)
  Overall = 100×0.15 + 95×0.25 + 100×0.25 + 90×0.35 = 95%
```

---

## 3. Gap List

| # | Severity | Confidence | Gap | Action |
|---|----------|:---------:|-----|--------|
| G1 | **Critical** | 95% | **웹훅 런에 소유자 개인·부서 메모리가 주입**되고 결과가 외부로 발송됨(`invoke_webhook_agent_use_case.py:78-98`). 외부 호출자가 query로 메모리 내용을 유도할 수 있음 | ✅ **Act-1 해소**: `stream()/execute()` keyword-only `inject_memory: bool = False` + `_prepare_graph`/`_build_memory_block` 전파. 대화 라우트 3곳(ws_router WS, agent_builder_router REST·SSE)만 True. 테스트 U7~U9·W2·W3, 실런 R3 0회 |
| G2 | Important | 90% | 백그라운드 잡 런에 요청자 메모리가 주입됨(`worker.py:303`). Plan은 "백그라운드 제외"로 확정, outbound 발송 대상 | ✅ **Act-1 해소**(사용자 결정: 모두 수정) — 기본 False로 자동 차단, W3로 고정 |
| G3 | Important(문서) | 95% | Plan §2.2·Design §2.1/§8·테스트 docstring의 전제("auth_ctx 없음 = 비대화")가 틀림 | ✅ Plan §2.2·FR-04, Design §2.1·§6.2·§8·§9·§12, 코드 주석 정정 |
| G4 | Minor | 90% | FR-06 "기존 테스트 무수정" — 픽스처 1줄 추가 | 의도된 편차로 기록(Design §9.3 U10). 프로덕션 getattr 방어 코드는 넣지 않음 |
| G5 | Minor | 95% | D2: 4-튜플 반환, `_render_wiki_toc` 미분리 | ✅ Design §6.1 D2 정정 |
| G6 | Minor | 95% | W1 테스트 파일명 상이 | ✅ Design §9.4/§12.1 정정 |
| G7 | Minor | 80% | `_prepare_graph` 70줄(기존 초과, +6줄) | 이월 — 후속 리팩토링 후보 |

Added(설계에 없고 구현에 있는 것): 없음.

---

## 4. Code Quality

| Item | Result |
|------|--------|
| 신규 헬퍼 길이 | `_render_prepend_blocks` 39줄, `_build_memory_block` 30줄 — 40줄 규칙 준수 |
| 로깅 | warning에 `exception=` 전달 — LOG 규칙 준수 |
| 레이어 | application → application 협력(duck-typed), domain→infra 참조 없음 — 준수 |
| 주석 | `Design Ref:` 7곳 부착 |

---

## 5. Test Results

| 시점 | Suite | Result |
|------|-------|--------|
| Check | 신규 C1~C6 / U1~U6+생성자 / W1 | 14 passed |
| Check | 회귀 `agent_builder` + `general_chat` + DI 계약 | 1191 passed |
| Check | 회귀 `approval` | 178 passed |
| Act-1 | 신규 C1~C6 / U1~U9+생성자 / W1~W3 + `test_identity_subject_wiring` | 24 passed |
| Act-1 | 회귀 `agent_builder`·`general_chat`·`agent_webhook`·`background_job`·`agent_schedule`·`approval`·`api/test_ws_router*`·`api/test_agent_builder_router*` | 1522 passed, 11 failed — 전부 기준선 상시 실패(SSE 인증 placeholder 9, WS `AttachmentResolver not initialized` 2, 메모리 기록과 일치) |
| Act-1 | 실런 R1·R3 (§2.7) | 2/2 통과 |
| — | `import src.api.main` | OK |

---

## 6. Recommendation

Act-1로 G1·G2·G3·G5·G6 해소, Overall **95%**(런타임 포함). 남은 항목은 G4(픽스처 1줄, 의도된 편차)·G7(기존 함수 길이)·R2(include_user_context=False 실런, E2E 이월)뿐이다. `/pdca report`로 진행한다.

**교훈**: "auth_ctx 유무"처럼 간접 신호로 호출 경로를 판정하면 같은 유스케이스를 공유하는 다른 호출자(웹훅·백그라운드)가 조용히 통과한다. 노출 범위를 좁히는 기능은 **호출자가 명시적으로 opt-in**하는 플래그(기본 fail-closed)로 설계하고, 비대화 호출자 소스에 플래그가 없음을 계약 테스트로 고정하는 편이 안전하다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-29 | 정적 분석 87%, G1 Critical(웹훅 주입) 발견 | 배상규 + Claude |
| 0.2 | 2026-10-29 | Act-1 반영: opt-in 플래그, 테스트 24 pass, 실런 R1·R3 통과 → 95% | 배상규 + Claude |
