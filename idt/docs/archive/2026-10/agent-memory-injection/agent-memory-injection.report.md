# agent-memory-injection Completion Report

> **Status**: Complete (코드 미커밋 · R2 실런 1건 E2E 이월)
>
> **Project**: sangplusbot — idt (백엔드)
> **Version**: 기준 커밋 fcabcde + 워킹트리
> **Author**: 배상규 + Claude
> **Completion Date**: 2026-10-29
> **PDCA Cycle**: #1 (Plan → Design → Do → Check 87% → Act-1 → 95%)
> **원천**: `docs/proposals/2026-10-15.md` 후보 #3

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | agent-memory-injection — 에이전트 실행 경로 메모리 상주 주입 |
| Start Date | 2026-10-29 |
| End Date | 2026-10-29 |
| Duration | 1일(단일 세션: Plan·Design·Do·Check·Act-1·Report) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Completion Rate: 95% (Match Rate, 런타임 포함) │
├─────────────────────────────────────────────┤
│  ✅ FR Met:        9 / 10                     │
│  ⚠️ FR Partial:    1 / 10 (FR-06 픽스처 1줄)  │
│  ❌ Not Met:       0 / 10                     │
│  실런: R1·R3 통과, R2 이월                    │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 사용자 메모리(소속·용어·선호)가 General Chat에만 주입되어, 심사역이 실제로 쓰는 부서 배포 에이전트는 사내 용어를 매번 재설명해야 했다. |
| **Solution** | `WorkflowCompiler.compile(memory_block=)` 한 항 + `RunAgentUseCase._build_memory_block` 1회 조립 + DI 1줄. 대화 라우트(WS·REST·SSE)만 `inject_memory=True`로 opt-in, 그 외 경로는 fail-closed. |
| **Function/UX Effect** | 실런 R1: 메모리 "ETC = 외부 여신 한도" 등록 후 에이전트 답변이 "ETC는 '외부 여신 한도'를 의미하는 사내 약어입니다"로 바뀜. 웹훅 동형 R3는 메모리 미반영("et cetera"). 화면·API·DB 변경 0. |
| **Core Value** | growing-agent Phase 1 검증 목표 "메모리 주입이 답변 품질을 올리는가"를 주 경로(에이전트 실행)에서 측정 가능해졌다. 노출 범위는 호출자 opt-in으로 구조적으로 닫혔다. |

---

## 1.4 Success Criteria Final Status

| # | Criteria | Status | Evidence |
|---|---------|:------:|----------|
| FR-01 | 순서 날짜 → 사용자 → 메모리 → wiki 목차 → 본문 | ✅ Met | `_render_prepend_blocks` prefix · C1/C6 · 실런 R1 prefix idx 날짜 0 → 사용자 → 메모리 370 |
| FR-02 | include_user_context=False면 메모리 생략 | ✅ Met | 컴파일러 `effective_memory` 게이팅 · C2 |
| FR-03 | 서브에이전트 재귀 미전달 | ✅ Met | `_compile_sub_agent` 호출에 memory_block 없음 · C4 |
| FR-04 | 대화 경로에서만 호출, 비대화 0회 | ✅ Met (Act-1) | `inject_memory` opt-in · U7~U9 · W2/W3 · 실런 R3 `build_block` 0회 |
| FR-05 | 런당 1회, compile 직전, dept_ids 전달 | ✅ Met | U1 · 실런 R1 `build_block('7', ['f1cb4caa…'])` 1회 |
| FR-06 | assembler None이면 동작 동일, 기존 테스트 무수정 | ⚠️ Partial | 운영 동작 동일(기본 None). `test_identity_subject_wiring.py` `__new__` 픽스처에 `uc._memory_assembler = None` 1줄 추가(의도된 편차) |
| FR-07 | 예외 → "" + warning(exception=) | ✅ Met | `_build_memory_block` try/except · U5 |
| FR-08 | 검색 파이프라인 메모리 미포함 | ✅ Met | C5 |
| FR-09 | include_user_context=False면 조회 생략 | ✅ Met | U4 |
| FR-10 | main.py DI | ✅ Met | W1 AST 계약 · `import src.api.main` OK |

**Success Rate**: 9/10 Met + 1 Partial (95%)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan] | 게이팅 = `include_user_context` 재사용(신규 플래그·마이그레이션 0) | ✅ | 프론트·DB 변경 0으로 완료 |
| [Plan] | 서브에이전트 제외(depth=0만) | ✅ | C4로 고정 |
| [Plan] | 검색 파이프라인 제외 | ✅ | C5로 고정 |
| [Plan] | "auth_ctx 있을 때만 주입 = 대화 경로만" | ❌ → 정정 | **전제 오류**: 웹훅은 `owner_ctx`, 백그라운드는 `ctx`를 넘긴다. Check에서 Critical로 발견 → Act-1에서 호출자 opt-in(`inject_memory`)으로 교체, Plan·Design 정정 |
| [Design] | Option C(헬퍼 2 + DI 1) | ✅ | `_render_prepend_blocks` 39줄 · `_build_memory_block` 30줄 — 40줄 규칙 안 |
| [Design] | D2 3-튜플 반환 + `_render_wiki_toc` 분리 | ⚠️ 편차 | 4-튜플(wiki 목차 재사용 필요) + 인라인. Design 정정 |
| [Design] | D8 `_resume_graph` 무수정 | ✅ | U6 |
| [Check] | 사용자 결정 "지금 모두 수정"(G1+G2) | ✅ | 웹훅·백그라운드 모두 차단 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [agent-memory-injection.plan.md](../01-plan/features/agent-memory-injection.plan.md) | ✅ Finalized (Act-1 정정 반영) |
| Design | [agent-memory-injection.design.md](../02-design/features/agent-memory-injection.design.md) | ✅ Finalized v0.2 |
| Check | [agent-memory-injection.analysis.md](../03-analysis/agent-memory-injection.analysis.md) | ✅ Complete v0.2 (87% → 95%) |
| Act | Current document | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

§1.4 참조. 10건 중 9 Met, 1 Partial.

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|--------|
| 성능 | 런당 추가 DB 조회 ≤ 2, 프롬프트 증가 ≤ 800자 | 조회 2회(개인·부서, 조립기 내부) · R1 메모리 블록 131자 | ✅ |
| 회귀 | 기존 스위트 무수정 통과 | 1522 passed, 11 failed(전부 기준선 상시 실패) · 픽스처 1줄 편차 | ✅(편차 기록) |
| 격리 | 조립 실패가 런 실패로 전파되지 않음 | U5 + 조립기 FR-07 | ✅ |
| 보수성 | `_BLOCK_HEADER` 지침 유지 | 조립기 무수정 | ✅ |
| 로깅 | `memory block injected`(count, request_id) | 조립기 로그 재사용 + D7 warning 1종 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | Change |
|-------------|----------|--------|
| 컴파일러 | `src/application/agent_builder/workflow_compiler.py` | `compile(memory_block=)` kwarg · `_render_prepend_blocks` 헬퍼 (+84/−29 포함 주석) |
| 유스케이스 | `src/application/agent_builder/run_agent_use_case.py` | `memory_assembler=None` · `_build_memory_block` · `stream/execute/_prepare_graph(inject_memory=False)` (+63) |
| DI | `src/api/main.py` | `memory_assembler=get_memory_assembler()` (+3) |
| 대화 라우트 | `src/api/routes/ws_router.py` · `src/api/routes/agent_builder_router.py` | `inject_memory=True` 3곳 (+6) |
| 테스트 | `tests/application/agent_builder/test_workflow_compiler_memory.py`(C1~C6) · `test_run_agent_memory_wiring.py`(U1~U9+생성자) · `tests/api/test_memory_injection_di.py`(W1~W3) · `test_identity_subject_wiring.py` 픽스처 1줄 | 신규 3파일 · 24 passed |
| 문서 | Plan · Design v0.2 · Analysis v0.2 · 본 Report | — |
| 마이그레이션 / 프론트 / API 계약 | — | **0** |

---

## 4. Incomplete Items

### 4.1 Carried Over

| Item | Reason | Priority | Note |
|------|--------|----------|------|
| R2 실런: include_user_context=False 에이전트에서 `[사용자 메모리]` 부재 확인 | user 7 소유 에이전트 전부 include_user_context=1, PATCH API에 필드 없음 | Low | 단위 C2/U4로 고정. `docs/wiki/ops/e2e-carryover-checklist.md` 메모리 절 항목 후보(위키 갱신은 `/wiki update` 호출 시) |
| G7 `_prepare_graph` 70줄 | 기존부터 40줄 초과, 이번 +6줄 | Low | 후속 리팩토링 후보 |
| 위키 `docs/wiki/backend/architecture-overview.md` §2(a) "메모리 상주 주입은 General Chat 경로에만" 문구 | 사실이 바뀜 | Medium | 사용자 `/wiki update` 호출 시 갱신 |
| 코드 커밋 | 사용자 지시 없음 | — | 변경 6파일 + 신규 3 테스트 + 문서 4 |

### 4.2 후속 후보 (Plan §9)

| Item | Note |
|------|------|
| 검색 파이프라인(rewrite LLM) 메모리 주입 | 용어 메모리가 검색어 재작성에 유용한지 실측 후 |
| 에이전트 경로 메모리 자동 추출 kickoff | growing-agent Phase 3 항목 |
| 별도 `include_memory` 에이전트 플래그 | 사용자 정보는 유지하고 메모리만 끄고 싶을 때 |

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Check | Act-1 후 |
|--------|--------|-------|---------|
| Structural | — | 95% | 100% |
| Functional | — | 90% | 95% |
| Contract | — | 80% | 100% |
| Runtime | — | 미실행 | 90% (R1·R3 통과, R2 이월) |
| **Overall Match Rate** | 90% | **87%** | **95%** |
| Critical 결함 | 0 | 1 (G1 웹훅 주입) | 0 |

### 5.2 Resolved Issues

| Issue | Resolution | Result |
|-------|------------|--------|
| G1 웹훅 런에 소유자 메모리 주입·외부 발송 | `inject_memory` opt-in(기본 False), 대화 라우트 3곳만 True | ✅ 실런 R3 0회 |
| G2 백그라운드 잡 주입 | 동일(기본 False) + W3 소스 계약 | ✅ |
| G3 문서 전제("auth_ctx 없음 = 비대화") 오류 | Plan §2.2·FR-04, Design §2.1·§6·§8·§9·§12, 코드 주석 정정 | ✅ |
| G5 D2 반환 형태·헬퍼 분리 불일치 | Design 정정 | ✅ |
| G6 테스트 파일명 불일치 | Design 정정 | ✅ |

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **선례 동형 이식**: General Chat 주입 패턴(agent 생성 직전 1회 조립 → prepend, optional 의존성 None 기본)을 그대로 옮겨 신규 파일 0·마이그레이션 0으로 끝냈다.
- **gap-detector가 실결함을 잡았다**: 정적 분석이 "auth_ctx 유무" 가정을 호출자 전수(웹훅·백그라운드·스케줄·RAGAS·재개)로 대조해 Critical을 찾았다. Plan 단계 질문에서 사용자와 함께 확정한 전제였는데도 틀렸다.
- **인프로세스 실런(코드 무수정 관찰)**: `TestClient(app)` + 메서드 래핑으로 prefix와 호출 횟수를 그대로 찍어, 단위 테스트가 못 보여주는 "답변이 실제로 바뀌는가"(ETC → 외부 여신 한도 vs et cetera)를 한 번에 증명했다.

### 6.2 What Needs Improvement (Problem)

- **간접 신호로 경로를 판정했다**: "auth_ctx가 있으면 대화"는 유스케이스를 공유하는 다른 호출자를 보지 않은 가정이었다. Plan 질문 단계에서 `run_uc.execute` 호출자 전수를 먼저 열어봤어야 했다.
- **FR-06 "기존 테스트 무수정"은 `__new__` 픽스처와 충돌한다**: 생성자를 우회하는 테스트 더블은 새 optional 속성을 모른다. 성공 기준을 "운영 동작 바이트 동일 + 픽스처 보정은 허용"으로 적는 편이 정확하다.

### 6.3 What to Try Next (Try)

- 노출 범위를 좁히는 기능은 **호출자 명시 opt-in(기본 fail-closed)** 으로 설계하고, 비대화 호출자 소스에 플래그가 없음을 AST 계약 테스트로 고정한다(W2/W3 패턴).
- Plan의 "비대화 경로 제외" 같은 주장은 Plan 작성 시 `grep "\.execute(\|\.stream("`로 호출자 표를 §6.2 Impact Analysis에 전수 기재한다.

---

## 7. Process Improvement Suggestions

| Phase | Current | Improvement |
|-------|---------|-------------|
| Plan | 호출 경로 가정을 사용자 질문으로 확정 | 질문 전에 호출자 전수 표를 먼저 제시(가정이 아니라 코드 사실로 선택지 구성) |
| Check | gap-detector 정적 + 수동 실런 | 실런 스크립트(메서드 래핑 관찰)를 재사용 가능한 스크래치 템플릿으로 유지 |
| 공통 | Task 도구 부재로 `[Phase]` Task 미생성 | 상태 파일만으로 진행 — 영향 없음 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 커밋(사용자 지시 시): 변경 6파일 + 신규 테스트 3 + 문서 4. `.bkit/` 런타임 파일 제외
- [ ] `/pdca archive agent-memory-injection`
- [ ] `/wiki update`(사용자 호출 시): architecture-overview §2(a), E2E 체크리스트 메모리 절 R2 항목

### 8.2 Next PDCA Cycle (제안서 2026-10-15)

| Item | Priority | Note |
|------|----------|------|
| `agent-run-turn-index-fix` (#1) | High | #2 선행 결함 |
| `agent-run-feedback-wiring` (#2) | High | 메모리 주입 효과를 👎 환류로 측정하는 짝 |

---

## 9. Changelog

### v1.0.0 (2026-10-29)

**Added:**
- `WorkflowCompiler.compile(memory_block="")` + `_render_prepend_blocks` (날짜 → 사용자 → 메모리 → wiki 목차 → 본문)
- `RunAgentUseCase(memory_assembler=None)` + `_build_memory_block` + `stream/execute(inject_memory=False)`
- 대화 라우트(WS·REST·SSE) `inject_memory=True`
- 테스트 24건(C1~C6, U1~U9+생성자, W1~W3)

**Changed:**
- `main.py` `_build_run_agent_uc`에 `memory_assembler=get_memory_assembler()`
- `test_identity_subject_wiring.py` 픽스처 `uc._memory_assembler = None`

**Fixed (Act-1):**
- 웹훅·백그라운드 잡 런에 소유자/요청자 메모리가 주입되던 결함(Analysis G1/G2)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-10-29 | Completion report | 배상규 + Claude |
