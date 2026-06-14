# Design: supervisor-viz-routing

> Created: 2026-06-11
> Phase: Design
> Plan: `docs/01-plan/features/supervisor-viz-routing.plan.md`
> Scope: `idt/` 백엔드 — 시각화 요청 시 search → data_analysis 워커 경유를 보장하는 Supervisor 라우팅 개선

---

## 0. 확정된 설계 결정 (Plan Open Questions 답변)

| # | Open Question | 결정 |
|---|---------------|------|
| **D1** | Hook 형태 (확장 vs 신설) | **`AttachmentRoutingHooks` 제자리 확장.** 이 클래스의 실제 책임은 "분석 워커로의 결정적 라우팅"이며 시각화 의도는 동일 책임의 추가 트리거다. 생성자에 `viz_policy: VisualizationRoutingPolicy | None = None`을 **옵셔널 주입** — `None`이면 기존 동작(엑셀 첨부만) 그대로라 하위호환·기존 테스트 무수정. 클래스 신설/리네임은 import 변경 범위만 키우므로 배제. |
| **D2** | prompt 블록 삽입 조건 | **시각화 키워드 감지 시에만 삽입.** `_render_attachment_block`과 동일하게 "필요할 때만 인지 블록" 패턴 유지(프롬프트 노이즈 최소화). 판단 기준은 Hook과 동일한 `VisualizationRoutingPolicy.explicit_request` — 강제 라우팅·프롬프트·chart_router가 **같은 도메인 정책 하나로 정렬**된다. |
| **D3** | 검색 결과 없는 시각화 요청 | **Hook 침묵 확정.** 검색 결과가 없는데 분석을 강제하면 대화 문맥 fallback이 데이터 없는 차트(환각 위험)를 만든다. 이 경우 prompt 가이드 블록(D2)만으로 "검색 먼저 → 분석" 순서를 유도한다. |
| **D4** | search 우선 강제 여부 | **prompt 유도만, search 강제 라우팅 없음.** search 워커 강제는 "어떤 search 워커를 고를지"(web/internal/mcp 복수 가능) LLM 판단 영역을 침범하고 범위를 확대한다. 비범위(Plan N2) 유지. |

### 결정의 핵심 일관성 근거

강제 라우팅 발동 조건(`explicit_request`)과 chart_router의 즉시 visualize 판정 조건이 **동일 정책 메서드**다. 따라서 **강제로 태운 분석은 chart_router에서 반드시 `visualize`로 판정**되어 chart_builder까지 도달한다(애매구간 LLM 분류로 빠질 수 없음) → "강제했는데 차트가 안 나오는" 어정쩡한 상태가 구조적으로 불가능.

---

## 1. 설계 개요

### 1-1. 목표 흐름

```
질문: "2026년 평균기온 그래프 그려줘" (search + data_analysis 워커, 첨부 없음)

supervisor ──(LLM: 데이터 필요 + viz 가이드 블록 → search 선택)──▶ search_worker
   ▲                                                                    │
   └────────────── quality_gate ◀───────────────────────────────────────┘
   │
   │  [신규] force_worker: viz 의도 + 검색결과 존재 + 분석 미실행 + !visualization_done
   ▼
data_analysis_worker (_analyze_context: 검색 결과를 데이터로 분석 — 기존 코드)
   │
chart_router (explicit_request → 즉시 "visualize" — 기존 코드)
   │
chart_builder (charts 생성 + visualization_done=True — 기존 코드)
   │
quality_gate → supervisor (visualization_done → 분석워커 skip, LLM이 FINISH)
   │
final_answer (charts 메타 포함 답변 — 기존 코드) → END
```

신규 코드는 **supervisor 복귀 시점의 강제 라우팅 1개 + prompt 블록 1개**뿐이며, 분석/차트/최종답변 경로는 전부 기존 코드를 그대로 사용한다.

### 1-2. 변경 파일 (3개)

| 파일 | 변경 |
|------|------|
| `src/application/agent_builder/supervisor_hooks.py` | `AttachmentRoutingHooks`에 viz 의도 강제 조건 추가 (`viz_policy` 옵셔널 주입) |
| `src/application/agent_builder/supervisor_nodes.py` | `_render_viz_guidance_block` 추가 + `create_supervisor_node` 옵셔널 파라미터 2개 |
| `src/application/agent_builder/workflow_compiler.py` | Hook/supervisor 노드 조립부에 `VisualizationRoutingPolicy()` 및 `analysis_worker_ids` 전달 |

레이어 검증: `supervisor_hooks`(application) → `domain.visualization.policies` import는 application→domain 의존으로 **허용**. `search_pipeline`의 `is_search_result`/`latest_user_question` 재사용은 application 내부 의존 — `search_pipeline`은 `supervisor_hooks`를 import하지 않으므로 **순환 없음**.

---

## 2. 변경 상세

### 2-1. `supervisor_hooks.py` — AttachmentRoutingHooks 확장

```python
"""Supervisor 루프 확장을 위한 Hook 프로토콜."""
from typing import Protocol

from src.application.agent_builder.search_pipeline import (
    is_search_result,
    latest_user_question,
)
from src.application.agent_builder.supervisor_state import SupervisorState
from src.domain.visualization.policies import VisualizationRoutingPolicy


class AttachmentRoutingHooks:
    """분석 가능한 데이터가 있으면 분석 워커로 결정적 강제 라우팅.

    트리거 2종:
    - 엑셀 등 분석 가능한 첨부 (기존, supervisor-attachment-routing)
    - 시각화 의도 + 수집된 검색 결과 (신규, supervisor-viz-routing)
      → supervisor LLM이 검색 결과만으로 FINISH 해 차트 경로
        (analysis → chart_router → chart_builder)를 건너뛰는 것을 차단.

    분석 워커 1회 실행 후에는 강제하지 않아(루프 방지) LLM이 종합/FINISH 하도록 둔다.
    """

    _ROUTABLE_TYPES = ("excel",)

    def __init__(
        self,
        analysis_worker_ids: list[str],
        viz_policy: VisualizationRoutingPolicy | None = None,  # None=viz 강제 비활성
    ) -> None:
        self._analysis_worker_ids = analysis_worker_ids
        self._viz_policy = viz_policy

    def force_worker(self, state: SupervisorState) -> str | None:
        if not self._analysis_worker_ids:
            return None
        target = self._analysis_worker_ids[0]
        # 공통 가드: 분석 워커 직후 재강제 금지 + 시각화 완료 후 재강제 금지
        if state.get("last_worker_id") == target:
            return None
        if state.get("visualization_done"):
            return None
        if self._has_routable_attachment(state):
            return target
        if self._viz_intent_with_search_results(state):
            return target
        return None

    def _has_routable_attachment(self, state: SupervisorState) -> bool:
        attachments = state.get("attachments", []) or []
        return any(a.get("type") in self._ROUTABLE_TYPES for a in attachments)

    def _viz_intent_with_search_results(self, state: SupervisorState) -> bool:
        """시각화 의도 + 검색 결과 수집 완료 → 분석 강제 대상 (D3: 검색결과 없으면 침묵)."""
        if self._viz_policy is None:
            return False
        messages = state.get("messages", []) or []
        if not self._viz_policy.explicit_request(latest_user_question(messages)):
            return False
        return any(is_search_result(m) for m in messages)

    def skip_workers(self, state: SupervisorState) -> list[str]:
        # (기존 그대로) visualization_done 시 분석 워커 skip — 재라우팅 결정적 차단
        if state.get("visualization_done"):
            return list(self._analysis_worker_ids)
        return []
```

**기존 대비 동작 차이 정리**:

| 케이스 | 기존 | 신규 |
|--------|------|------|
| 엑셀 첨부 | 강제 | 강제 (동일) |
| 엑셀 첨부 + `visualization_done=True` | 강제 (단, `last_worker_id` 가드로 사실상 미발동) | **강제 안 함** — 명시 가드 추가 (안전성 강화, 의미 변화 없음) |
| viz 의도 + 검색결과 존재 | 강제 없음 → LLM FINISH 가능 | **강제** (신규) |
| viz 의도 + 검색결과 없음 | 강제 없음 | 강제 없음 (D3 — prompt 유도만) |
| `viz_policy` 미주입 | — | 기존과 100% 동일 (하위호환) |

### 2-2. `supervisor_nodes.py` — viz 가이드 블록

`_render_attachment_block` 바로 아래에 동일 패턴으로 추가:

```python
def _render_viz_guidance_block(
    messages: list,
    analysis_worker_ids: list[str],
    viz_policy,  # VisualizationRoutingPolicy | None
) -> str:
    """시각화 요청 감지 시 supervisor decision용 인지 블록 (아니면 빈 문자열).

    차트는 분석 워커 직후 경로(chart_router → chart_builder)에서만 생성되므로,
    LLM이 검색 결과만으로 FINISH 하지 않도록 경로 제약을 명시한다 (D2).
    """
    if viz_policy is None or not analysis_worker_ids:
        return ""
    from src.application.agent_builder.search_pipeline import latest_user_question
    if not viz_policy.explicit_request(latest_user_question(messages)):
        return ""
    ids = ", ".join(analysis_worker_ids)
    return (
        f"\n\n[시각화 안내]\n"
        f"사용자가 그래프/차트 시각화를 요청했습니다. "
        f"차트는 분석 워커({ids})를 거쳐야만 생성됩니다.\n"
        f"외부 데이터가 필요하면 먼저 검색 워커로 데이터를 수집한 뒤, "
        f"반드시 분석 워커를 호출하세요. "
        f"검색 결과만 모은 상태에서 FINISH 하지 마세요."
    )
```

`create_supervisor_node` 시그니처 확장 (옵셔널 — 기존 호출부/테스트 무수정):

```python
def create_supervisor_node(
    llm, workers, supervisor_prompt, hooks, logger,
    analysis_worker_ids: list[str] | None = None,   # ★ 신규
    viz_policy: VisualizationRoutingPolicy | None = None,  # ★ 신규
):
    ...
    async def supervisor_node(state):
        ...
        attachment_block = _render_attachment_block(state.get("attachments", []))
        viz_block = _render_viz_guidance_block(            # ★ 신규
            state["messages"], analysis_worker_ids or [], viz_policy,
        )
        decision_prompt = (
            f"{supervisor_prompt}\n\n"
            f"사용 가능한 워커:\n{worker_descriptions}"
            f"{attachment_block}"
            f"{viz_block}\n\n"          # ★ 첨부 블록 뒤에 삽입
            f"다음 중 선택하세요:\n..."
        )
```

> import는 모듈 상단 `from src.domain.visualization.policies import VisualizationRoutingPolicy` (타입 힌트용). `latest_user_question`은 이미 search_pipeline에서 supervisor_nodes가 `QUALITY_FEEDBACK_PREFIX`를 import하고 있으므로 같은 모듈에서 추가 import — 순환 없음 (search_pipeline은 supervisor_nodes를 import하지 않음).

### 2-3. `workflow_compiler.py` — 조립부

`compile()` L240~250 변경:

```python
# 첨부/시각화 라우팅: analysis 워커가 있고 외부 주입 훅이 없을(기본) 때만
# AttachmentRoutingHooks로 대체. 명시적 주입 훅은 존중(테스트/확장).
effective_hooks = self._hooks
viz_policy = None
if analysis_worker_ids:
    viz_policy = VisualizationRoutingPolicy()      # ★ chart_router와 동일 정책
    if isinstance(self._hooks, DefaultHooks):
        effective_hooks = AttachmentRoutingHooks(
            sorted(analysis_worker_ids), viz_policy=viz_policy,   # ★
        )

supervisor_fn = create_supervisor_node(
    llm=llm,
    workers=workers_for_supervisor,
    supervisor_prompt=effective_supervisor_prompt,
    hooks=effective_hooks,
    logger=self._logger,
    analysis_worker_ids=sorted(analysis_worker_ids),  # ★ viz 블록용
    viz_policy=viz_policy,                            # ★ 분석워커 없으면 None → 블록 미삽입
)
```

- `VisualizationRoutingPolicy`는 이미 본 모듈이 import 중 (chart_router 조립용) — 추가 import 없음.
- 분석 워커가 없는 에이전트: `viz_policy=None` → Hook·prompt 모두 기존 동작.

---

## 3. 루프 안전성 분석

| 시나리오 | 방어 |
|----------|------|
| 강제 → 분석 → 차트 → supervisor 복귀 후 재강제 | `visualization_done=True` 가드 + `skip_workers`가 분석 워커 제외 (2중) |
| 강제 → 분석 직후 복귀 (chart_builder 비활성: `chart_max_count=0`) | `last_worker_id == target` 가드. `visualization_done`은 미설정이지만 분석 직후라 재강제 불가 |
| 분석 후 LLM이 search를 또 선택 → search 후 재강제 | 이론상 분석 2회 가능하나 `iteration_count >= max_iterations` 상한으로 유한. viz 의도 질문에서 LLM이 분석 결과를 두고 재검색할 유인 낮음 — 잔여 리스크로 수용 |
| 멀티턴: 이전 턴에서 차트 생성 완료 후 새 질문 | `build_initial_state`가 매 run `visualization_done=False`, `last_worker_id=""` 초기화 → 새 턴에서 정상 재강제 가능 (의도된 동작) |
| 품질검증 재시도 피드백을 질문으로 오인 | `latest_user_question`이 `QUALITY_FEEDBACK_PREFIX` 메시지를 제외 (기존 D5 규약 재사용) |

---

## 4. 테스트 설계 (TDD — Red 먼저)

### 4-1. 신규: `tests/application/agent_builder/test_supervisor_viz_routing.py`

기존 `test_supervisor_attachment.py`의 `_make_state`/`_llm_returning` 헬퍼 패턴 재사용. 검색결과 메시지는 `AIMessage(name="search_w", content=format_search_result("search_w", "2026년 기온 데이터..."))`로 구성 (메시지 규약 단일 출처 재사용).

| TC | 시나리오 | 기대 |
|----|----------|------|
| TC-1 | viz 의도("그래프 그려줘") + 검색결과 존재 + 분석 미실행 | `force_worker == "data_analysis"` |
| TC-2 | viz 의도 없음("기온 알려줘") + 검색결과 존재 | `None` |
| TC-3 | viz 의도 + 검색결과 없음 (D3) | `None` |
| TC-4 | viz 의도 + 검색결과 + `last_worker_id == "data_analysis"` | `None` (루프 방지) |
| TC-5 | viz 의도 + 검색결과 + `visualization_done=True` | `None` |
| TC-6 | `viz_policy=None` (미주입) + viz 의도 + 검색결과 | `None` (하위호환) |
| TC-7 | 엑셀 첨부 + `visualization_done=True` | `None` (신규 공통 가드) |
| TC-8 | supervisor_node 통합: LLM mock이 FINISH 반환해도 검색결과+viz 의도면 분석 워커로 강제, LLM 미호출 | `next_worker == "data_analysis"`, `with_structured_output.assert_not_called()` |
| TC-9 | prompt: viz 의도 시 system 메시지에 `[시각화 안내]` 포함 | 블록 존재 + 분석 워커 id 포함 |
| TC-10 | prompt: viz 의도 없으면 `[시각화 안내]` 미포함 | 블록 부재 |
| TC-11 | prompt: `analysis_worker_ids` 미전달(기존 호출 형태) | 블록 부재 + 기존 동작 |

### 4-2. 회귀 확인 (기존 테스트 무수정 통과)

- `test_supervisor_hooks.py`, `test_supervisor_attachment.py` — Hook 시그니처가 옵셔널 추가라 무수정 통과해야 함.
- `test_supervisor_nodes.py`, `test_workflow_compiler.py`, `test_analysis_node.py` — supervisor 노드 시그니처 옵셔널 확장 회귀.
- 실행: pytest **격리 실행** (Windows 이벤트 루프 teardown flakiness — 메모리 참조).

---

## 5. 구현 순서

1. **(Red)** `test_supervisor_viz_routing.py` TC-1~7 작성 → 실패 확인
2. **(Green)** `supervisor_hooks.py` 확장 구현 → TC-1~7 통과
3. **(Red)** TC-8~11 작성 → 실패 확인
4. **(Green)** `supervisor_nodes.py` viz 블록 + 시그니처 확장 → 통과
5. **(Green)** `workflow_compiler.py` 조립부 연결 (TC-8이 조립 경로까지 커버하도록 보강)
6. **(회귀)** `tests/application/agent_builder/` 격리 실행 전체 통과
7. **(verify)** `/verify-architecture`, `/verify-logging`, `/verify-tdd`

---

## 6. 비변경 확인 (No-Regression Surface)

- `chart_router` / `chart_builder` / `VisualizationRoutingPolicy` / `_create_analysis_node` / `final_answer` — **수정 없음**, 재사용만.
- API 응답 스키마/charts 페이로드 — 변경 없음 → `/api-contract-sync` 불필요.
- General Chat / Excel standalone / sub_agent(depth>0) 경로 — 변경 없음 (sub_agent도 분석 워커가 있으면 동일 Hook이 적용되나, 이는 기존 AttachmentRoutingHooks와 동일한 적용 범위).

---

## 7. 다음 단계

```
/pdca do supervisor-viz-routing
```
