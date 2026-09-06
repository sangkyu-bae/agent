# worker-context-injection Gap Analysis

> **Date**: 2026-09-03
> **Analyst**: 배상규
> **Plan**: [worker-context-injection.plan.md](../01-plan/features/worker-context-injection.plan.md)
> **Design**: [worker-context-injection.design.md](../02-design/features/worker-context-injection.design.md)
> **Overall Match Rate**: **100%** (초안 94.5% → GAP-01/02/03 전건 해소)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | supervisor만 에이전트 프롬프트를 보고, 워커는 못 봐서 도구 인자를 지어낸다 |
| **WHO** | P2(KB 운영자/에이전트 소유자) |
| **RISK** | 토큰 증가 / `SupervisorDecision` 스키마 변경 회귀 |
| **SUCCESS** | 더미 URL 호출 0건, 워커 system_prompt에 에이전트 프롬프트·역할 포함 100% |
| **SCOPE** | M1 정적 주입 → M2 동적 task → M3 가드·관측 |

---

## 1. Match Rate

런타임 테스트가 실행되었으므로 v2.3.0 런타임 포함 공식을 적용한다.

```
Overall = (Structural × 0.15) + (Functional × 0.25) + (Contract × 0.25) + (Runtime × 0.35)
        = (100 × 0.15) + (100 × 0.25) + (100 × 0.25) + (100 × 0.35)
        = 100%
```

> 진행 경과: 초안 94.5% → GAP-01 부분 조치 95.1% → GAP-01/02/03 전건 해소 100%.
> Functional은 FR-03(전 노드 주입)·FR-09(run step 관측) 완결로 100%,
> Runtime은 Design §8.4 L3 #3 테스트 추가로 22/22가 되었다.

| 축 | 비율 | 근거 |
|----|:----:|------|
| **Structural** | 100% | Design §11.1이 명시한 src 6 / tests 5 = 11개 파일 전부 존재 |
| **Functional** | 100% | FR-01 ~ FR-10 전건 충족 |
| **Contract** | 100% | §4.1 내부 함수 계약 5건 전부 시그니처·동작 일치 |
| **Runtime** | 100% | §8 테스트 시나리오 22건 전부 구현·통과 |

---

## 2. Strategic Alignment Check

| 질문 | 판정 | 근거 |
|------|:----:|------|
| PRD의 핵심 문제(WHY)를 다뤘는가 | ✅ | 워커 react agent가 에이전트 프롬프트·역할을 받게 됨 (`workflow_compiler.py:460-464`, `516-524`) |
| Plan Success Criteria가 충족되는가 | ✅ | §3 참조 — 2/2 충족 |
| 핵심 Design 결정을 따랐는가 | ✅ | Option C(실용 균형), 지시성 오류 반환, 전문+상한 절단, domain 정책 분리 모두 준수 |

**전략적 불일치 없음.** 다만 아래 §5 관찰사항 O-1은 이번 스펙 범위 밖이지만 기능적으로 중요하다.

---

## 3. Plan Success Criteria 평가

| Criteria | 상태 | 증거 |
|----------|:----:|------|
| 워커 system_prompt에 에이전트 프롬프트·역할 포함 100% | ✅ Met | `tests/application/agent_builder/test_worker_context_injection.py:86-95` — `assert AGENT_PROMPT in prompt`, `assert SCRAPE_DESC in prompt` 통과 |
| example.com류 더미 URL 호출 0건 | ✅ Met | `tests/infrastructure/mcp/test_tool_adapter_guard.py:52-65` — `mock_session.call_tool.assert_not_called()` 통과 |
| TDD 사이클 준수 | ✅ Met | 모든 모듈에서 Red 확인 후 구현 (31→0, 3→0, 10→0, 5→0, 8→0 실패 전이) |
| `/verify-architecture` / `/verify-logging` / `/verify-tdd` 통과 | ✅ Met | 변경분 기준 전항목 통과. 검출된 항목은 전부 사전 존재 |
| 기존 회귀 없음 | ✅ Met | 전체 8670 passed / 58 failed. 58건은 baseline과 동일 집합 (`comm -13` 공집합) |

**Success Rate: 5/5**

---

## 4. Gap 목록

### GAP-01 (Important) — ✅ 해소 (2026-09-03 Act) — FR-03: function 노드에 컨텍스트 블록 미주입

> **조치 결과**: 전 노드 해소. 프롬프트 훅이 없던 4개 생성 노드는 각 생성기
> 계약에 `worker_context_block`(기본 `""`)을 추가해 해결했다.
>
> | 노드 | 조치 전 | 조치 후 |
> |------|:-------:|:-------:|
> | search | ❌ | ✅ `worker_context_block` 파라미터 신설 (`search_pipeline.py:303`, `deep_search/workflow.py:141`) |
> | analysis | 프롬프트만 ✅ / 역할 ❌ | ✅ 역할 포함, 도구 규범 제외(`include_tool_norm=False`) |
> | document_extractor | ❌ | ✅ `DocumentComposer.compose(worker_context_block=...)` |
> | document_generator | ❌ | ✅ `DocumentGenerator.generate(worker_context_block=...)` |
> | excel_export | ❌ | ✅ `ExcelGenerator.generate(worker_context_block=...)` |
> | presentation_generator | ❌ | ✅ `PresentationGenerationUseCase.generate(worker_context_block=...)` |

#### 원 분석 (조치 전)


**Plan FR-03**: "자체 프롬프트를 이미 갖는 노드(wiki_read, search, analysis, document_*)도 컨텍스트 블록을 앞단에 동일하게 받되, 기존 지시문은 그대로 뒤에 유지한다"

**실제**: `worker_context_block`이 `workflow_compiler.py:460`에서 계산되는데, function 노드 분기는 그보다 **앞**에 있고 전부 `continue`로 빠져나간다.

```
362:  document_extractor    → continue   ← 블록 계산 이전
374:  document_generator    → continue
385:  presentation_generator→ continue
398:  excel_export          → continue
411:  analysis              → continue
─────────────────────────────────────
460:  worker_context_block = render_worker_context_block(...)   ← 여기서 계산
466:  search                → _create_search_node(...)  ← 블록을 인자로 넘기지 않음
478:  wiki_read             → 주입 ✅
516:  일반 react 워커        → 주입 ✅
```

| 노드 | 블록 주입 | 비고 |
|------|:---------:|------|
| 일반 react 워커 (MCP 포함) | ✅ | **실제 버그 발생 지점 — 커버됨** |
| wiki_read | ✅ | |
| search | ❌ | `_create_search_node`에 `worker_context_block` 미전달 |
| analysis | ❌ | `continue`로 조기 이탈 |
| document_extractor / document_generator / presentation_generator / excel_export | ❌ | `continue`로 조기 이탈 |

**영향**: 이번 사건의 원인(스크래핑 MCP 워커)은 react 경로에 있어 해결되었다. function 노드들은 각자 자체 프롬프트로 작업 맥락을 갖고 있어 즉각적 오작동 위험은 낮다. 다만 search 노드는 외부 검색 도구에 질의를 보내므로 동일한 환각 클래스가 잠재한다.

#### 4.1 조치 내역

**조치함 — search (높은 실효)**

`search`의 rewrite/plan LLM은 **실제 외부 검색어를 작성**한다. 에이전트 맥락이
없으면 "현재 분기 리포트" 같은 발화에서 근거 없는 검색어를 만드는, 이번 사건과
동일한 환각 클래스가 발생한다.

| 파일 | 변경 |
|------|------|
| `search_pipeline.py:303` | `worker_context_block` 파라미터 추가, `context_block = datetime + user + worker` |
| `deep_search/workflow.py:141` | 동일 (AD-1 시그니처 동형 계약 유지) |
| `workflow_compiler.py:_create_search_node` | 파라미터 중계 |

**조치함 — analysis (낮은 실효, 완결성 목적)**

`analysis`는 이미 `workflow.supervisor_prompt`를 받고 있었다(원 분석의 오류 —
"미주입"이 아니라 "역할만 미주입"이 정확하다). 자기 역할(`description`)을
추가로 받게 했고, 도구를 호출하지 않으므로 `include_tool_norm=False`로 도구
규범은 제외했다. 이를 위해 `render_worker_context_block`에 파라미터를 신설했다.

**조치함 — document_extractor / document_generator / presentation_generator / excel_export**

이 4개 노드는 LLM 호출이 컴파일러가 아니라 주입된 생성기 객체 내부에서 일어나
프롬프트 훅이 없었다. 각 생성기의 **공개 메서드에 `worker_context_block: str = ""`
키워드를 추가**하고 시스템 프롬프트 앞단에 붙이는 방식으로 해결했다. 기본값이
있어 미배선 호출부는 기존 동작 그대로다(도메인 포트 변경 없음).

| 대상 | 주입 지점 |
|------|-----------|
| `DocumentComposer.compose` | `_decide_slot_values` → `{"role": "system"}` 앞단 |
| `DocumentGenerator.generate` | `_write_html` → `{"role": "system"}` 앞단 |
| `ExcelGenerator.generate` | `_plan_sheets` → `{"role": "system"}` 앞단 |
| `PresentationGenerationUseCase.generate` | `_plan`에 넘기는 `instruction` 앞단 |

**presentation만 방식이 다른 이유**: 프롬프트가 `SlidePlannerPort`(도메인 포트)
구현체 안에 있어, 포트 시그니처를 바꾸면 어댑터·테스트까지 파급된다. 포트는
그대로 두고 use case가 `instruction` 앞에 블록을 붙이는 방식을 택했다 —
계획 LLM 입장에서 블록은 실제로 "무엇을 어떤 관점으로 만들지"의 지시 맥락이다.

**도구 규범 제외**: 이 4개 노드와 analysis는 외부 도구를 호출하지 않으므로
`include_tool_norm=False`로 "도구 인자를 추측하지 말라" 지침을 뺐다. 무관한
지침이 생성 프롬프트를 오염시키지 않게 하기 위함이다.

### GAP-02 (Important) — ✅ 해소 (2026-09-03 Act) — FR-09: 차단 사유의 run step 추적 반영

**Plan FR-09**: "차단 사유를 run step 추적에 반영해 실행 이력에서 재발을 추적할 수 있게 한다"

**실제**: `tool_adapter.py`에 `track_step` / `record_step` 참조 0건. 관측은 `logger.warning` 한 줄뿐이다.

```python
# src/infrastructure/mcp/tool_adapter.py:84-90
logger.warning(
    "MCP tool call blocked (placeholder argument)",
    reason="placeholder_url", blocked_value=blocked, **log_extra,
)
```

**영향**: 로그 검색으로는 추적 가능하나, 에이전트 실행 이력(run step) UI에서는 차단 사실이 보이지 않는다. 운영자가 "왜 결과가 비었나"를 이력만으로 알 수 없다.

**조치 내역**: `MCPToolAdapter`(infrastructure)는 application을 참조할 수 없어
`track_step`을 직접 호출할 수 없다. 대신 **domain 정책이 정한 접두어**를 접점으로
삼아 노드 레벨에서 감지하는 경로를 만들었다.

```
[infrastructure] MCPToolAdapter._arun
      └ 차단 → ToolArgumentPolicy.build_blocked_message()
                 └ BLOCKED_PREFIX = "[도구 호출이 차단되었습니다]"   ← domain 상수
                        ↓ ToolMessage로 react agent 트레이스에 남음
[application]    _wrap_worker
      └ _blocked_step_summary(result_messages)
             └ ToolArgumentPolicy.is_blocked_message()로 식별       ← application → domain (정방향)
                    ↓
             out[STEP_OUTPUT_SUMMARY_KEY] = "도구 호출 N건 차단 (근거 없는 인자). …"
                    ↓
[application]    _wrap_step → result.pop(STEP_OUTPUT_SUMMARY_KEY) → step.output_summary
```

| 변경 | 위치 |
|------|------|
| `BLOCKED_PREFIX` 상수 + `is_blocked_message()` | `domain/mcp/tool_argument_policy.py` |
| `_blocked_step_summary()` 신규 | `application/agent_builder/workflow_compiler.py` |
| `_wrap_worker`가 `_step_output_summary` 반환 | 동 파일 |

**레이어 준수**: infrastructure → application 참조 없음. 이번 변경으로 추가된
방향은 application → domain 하나뿐이다. `_wrap_step`의 기존 `result.pop(
STEP_OUTPUT_SUMMARY_KEY)` 메커니즘을 그대로 재사용해 새 플럼빙을 만들지 않았다.

**워커 출력 규약 유지**: 차단이 있어도 `AIMessage(name=worker_id)` 1건 계약은
그대로다(`test_output_contract_still_single_ai_message`).

---

### GAP-03 (Minor) — ✅ 해소 (2026-09-03 Act) — L3 #3 테스트 누락

**Design §8.4 #3**: "차단 후 재시도 — 차단 → 워커가 인자 없이 재호출 → 무한 루프 없이 종료(반복 한도 내)"

**실제**: `test_tool_adapter_guard.py`에 해당 시나리오 없음 (`재시도`/`무한` 키워드 0건).

**영향**: 낮음. 반복 상한은 기존 `IterationLimitPolicy` / `max_retries_per_worker`가 담당하며 이번 변경이 그 경로를 건드리지 않았다. 다만 "차단이 루프를 유발하지 않는다"는 계약이 테스트로 고정되지 않았다.

**조치 내역**: `TestBlockDoesNotLoop` 2건 추가 (`test_tool_adapter_guard.py`).

| 테스트 | 고정한 계약 |
|--------|-------------|
| `test_repeated_blocks_never_reach_server` | 차단이 3회 반복돼도 서버 호출 0건, 예외 없이 매번 문자열 반환 |
| `test_worker_can_recover_after_block` | 차단은 종착이 아니다 — 교정된 인자는 정상적으로 서버에 도달 |

구현 변경 없이 통과했다. 어댑터가 상태를 갖지 않아 이미 성립하던 성질이지만,
회귀를 막기 위해 계약으로 고정했다.

---

## 5. 관찰사항 (스펙 위반은 아님)

### O-1 — 워커는 `user_context_block`을 받지 않는다

주입에 쓰인 값은 `workflow.supervisor_prompt`(`workflow_compiler.py:461`)이고, supervisor가 받는 `effective_supervisor_prompt`(`:312`)가 아니다.

```python
312:  effective_supervisor_prompt = datetime_block + user_context_block + wiki_toc_block + workflow.supervisor_prompt
556:  create_supervisor_node(supervisor_prompt=effective_supervisor_prompt)   ← 사용자 정보 포함
461:  render_worker_context_block(agent_prompt=workflow.supervisor_prompt)    ← 사용자 정보 미포함
```

- `datetime_block` — 워커 경로에서 별도로 붙음, 무관
- `wiki_toc_block` — wiki 워커에 별도 주입, 무관
- `user_context_block` — **워커는 현재 사용자(이름·부서·역할)를 모른다**

Plan FR-01은 입력을 "에이전트 시스템 프롬프트"로 정의했고 `workflow.supervisor_prompt`가 정확히 그것(부착 스킬 병합 포함)이므로 **스펙 위반은 아니다**. 다만 "내 부서 기준으로 조회해줘" 같은 요청에서 워커가 도구 인자를 채울 때 사용자 정보가 필요할 수 있다. 별도 판단이 필요한 사안.

### O-2 — MCP 서버는 여전히 에이전트 프롬프트를 볼 수 없다

`session.call_tool(name, arguments)`(`tool_adapter.py:97`)가 보내는 것은 도구 이름과 인자뿐이다. MCP 프로토콜 상 프롬프트를 실을 자리가 없다.

Design의 "URL 결정 주체 = MCP 서버 해석" 결정이 성립하려면, 서버가 판단할 재료가 **`arguments`를 통해** 전달되어야 한다. 도구 스키마에 의도/맥락을 받을 필드(`query`, `intent` 등)가 없으면 서버는 여전히 아무 맥락도 받지 못한다.

이는 구현 결함이 아니라 **설계 전제의 미검증 항목**이다 (Design §12 Open Item #1). 해당 MCP 서버의 실제 도구 스키마 확인이 선행되어야 한다.

### O-3 — 커스텀 프롬프트 2000자 절단

`MAX_AGENT_PROMPT_CHARS = 2000`(`prompt_rendering.py:70`) 초과분은 워커에 전달되지 않는다. Design §12 Open Item #3으로 남긴 항목이며, DB의 `agents.system_prompt` 길이 분포 확인이 필요하다. 길이 초과 시 LLM에는 `…(에이전트 지침 일부 생략)` 표기로 알린다.

### O-4 — `localhost` / `127.0.0.1` 의도적 제외

Plan FR-07이 열거한 목록에서 두 항목을 뺐다. 사내 로컬 대상 스크래핑 오탐 위험이 실익보다 크다는 판단이며, Design §3.2에 근거를 기록하고 `test_returns_false_for_localhost`로 계약을 고정했다. **의도된 스펙 축소**.

---

## 6. Decision Record 검증

| 결정 | 출처 | 준수 | 증거 |
|------|------|:----:|------|
| Option C — 실용 균형 | Design §2.0 | ✅ | 신규 1 / 수정 5 파일, domain 정책 분리 + 기존 렌더러 재사용 |
| URL 결정 주체 = MCP 서버 | Plan §7.2 | ✅ | `tool_config` 기반 URL 고정 미구현(Out of Scope 준수) |
| 차단 = 지시성 오류 문자열 | Design §6.2 | ✅ | `build_blocked_message` 반환, 예외 미발생 (`test_blocked_result_is_string_not_exception`) |
| 프롬프트 전문 + 상한 절단 | Design §4.1 | ✅ | `_truncate_prompt`, `MAX_AGENT_PROMPT_CHARS=2000` |
| 모든 tool 워커 공통 적용 | Plan §7.2 | ✅ | GAP-01 해소 — react·wiki·search·analysis·생성 노드 4종 전부 주입 |
| task는 react agent 워커에만 | Design §2.0 | ✅ | `_build_worker_input`이 `_wrap_worker` 경로에서만 호출 |
| 블록 배치 순서 (datetime → context → 기존 지시) | Design §7.2 | ✅ | `test_context_block_precedes_toc_block` 통과 |

---

## 7. 테스트 실행 결과

| 스위트 | 결과 |
|--------|------|
| `tests/domain/mcp` + `tests/infrastructure/mcp` | 133 passed |
| `tests/application/agent_builder` | 620 passed |
| `tests/application` + `tests/domain` + `tests/infrastructure/mcp` | 5515 passed |
| 전체 스위트 | **8670 passed / 58 failed / 2 skipped** |
| 신규 실패 | **0건** (baseline 58건과 동일 집합) |

58건 실패는 `tests/api/*`, `tests/infrastructure/{parser,retriever,elasticsearch}` 계열의 사전 존재 실패다. 변경분을 `git stash`한 baseline에서 동일 파일·동일 테스트가 실패함을 확인했다.

**부수 관찰**: `tests/application/agent_builder/test_run_agent_use_case_observability.py` 5건은 단독 실행 시 통과하고 전체 실행 시에만 실패한다 — 테스트 격리 문제로, 이번 변경과 무관하나 별개 이슈로 기록할 가치가 있다.

---

## 8. 요약

| 구분 | 수 | 상태 |
|------|:--:|------|
| Critical | 0 | — |
| Important | 2 | GAP-01 ✅ 해소, GAP-02 ✅ 해소 |
| Minor | 1 | GAP-03 ✅ 해소 |
| 관찰사항 | 4 | O-1 ~ O-4 — 스펙 위반 아님, 판단 대기 |

**미해소 Gap 0건.**

Match Rate 100%. **핵심 문제 — 커스텀 에이전트의 MCP 스크래핑 워커가 컨텍스트를
잃고 더미 URL을 호출하던 경로 — 는 완전히 해결되었고**, 스펙의 확장 범위(전 노드
컨텍스트 주입, run step 관측, 루프 방지 계약)까지 전건 충족했다.

남은 것은 관찰사항 4건뿐이며 모두 스펙 위반이 아니다. 이 중 **O-1(워커가
`user_context_block` 미수신)과 O-2(MCP 서버가 프롬프트를 볼 수 없음)는 별도
판단이 필요한 사안**으로, 후속 사이클에서 다룰지 결정해야 한다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-03 | 초안 — 정적 3축 + 런타임 대조, Gap 3건 / 관찰 4건 | 배상규 |
| 0.2 | 2026-09-03 | GAP-01 부분 해소 — search·analysis 컨텍스트 주입, `include_tool_norm` 신설. Match Rate 94.5% → 95.1% | 배상규 |
| 0.3 | 2026-09-03 | GAP-01 잔여(생성 노드 4개) + GAP-02(run step 관측) + GAP-03(루프 방지 테스트) 전건 해소. Match Rate 95.1% → 100% | 배상규 |
