# Plan: supervisor-viz-routing

> Created: 2026-06-11
> Phase: Plan
> Scope: `idt/` 백엔드 — Supervisor 그래프에서 시각화(그래프/차트) 요청 시 search → data_analysis 워커 경유를 보장하는 라우팅 개선

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | search + data_analysis 도구를 가진 에이전트에 "2026년 평균기온 그래프 그려줘" 같은 시각화 요청을 하면, supervisor가 search 워커 실행 후 곧바로 `FINISH`를 선택해 분석 워커를 타지 않는다. 차트 경로(`chart_router → chart_builder`)는 **analysis 워커 직후에만 배선**돼 있으므로 차트가 아예 생성되지 않는다. 분석 워커로의 결정적 강제 라우팅은 **엑셀 첨부 시에만** 존재한다(`AttachmentRoutingHooks._ROUTABLE_TYPES = ("excel",)`). |
| **Solution** | ① 시각화 의도 감지 시 분석 워커 강제 라우팅을 Hook으로 추가: 질문에 시각화 키워드(기존 `VisualizationRoutingPolicy.explicit_request` 재사용)가 있고, 검색 결과가 수집됐으며, 분석 워커가 아직 실행되지 않았으면 `force_worker`로 분석 워커를 결정적으로 태운다. ② supervisor decision prompt에 "차트는 분석 워커를 거쳐야만 생성된다"는 시각화 가이드 블록을 추가해 LLM 수준에서도 search → analysis 순서를 유도한다. |
| **Function UX Effect** | 엑셀 첨부 없이도 "○○ 그래프 그려줘" 요청이 검색 데이터 기반 분석 → 차트 생성으로 이어져 답변과 함께 차트가 화면에 표시된다. 기존 엑셀 첨부 경로·비시각화 질문 경로는 동작 불변. |
| **Core Value** | "분석 가능한 데이터가 있으면 LLM 판단에 맡기지 않고 결정적으로 라우팅한다"는 기존 설계 원칙(AttachmentRoutingHooks)을 시각화 의도까지 일관 확장. 차트 생성 경로의 예측 가능성 확보. |

---

## 1. 배경 / 문제 정의

### 1-1. 재현 시나리오

- 에이전트 구성: search 계열 워커(예: `web_search_worker`) + `data_analysis_worker` (category=`analysis`)
- 질문: "2026년 평균기온 그래프 그려줘" (엑셀 첨부 없음)

**현재 흐름**:
```
supervisor → search_worker → quality_gate → supervisor
                                               └ LLM이 FINISH 선택 (검색 결과로 충분하다고 판단)
                                                 → final_answer → END   ← 차트 미생성
```

**기대 흐름**:
```
supervisor → search_worker → quality_gate → supervisor
                                               └ data_analysis_worker (검색 결과를 데이터로 분석)
                                                 → chart_router → chart_builder → quality_gate
                                                 → supervisor(FINISH) → final_answer → END  ← 차트 포함
```

### 1-2. 코드 근거

1. **분석 노드는 엑셀 없이도 이미 동작한다** — `workflow_compiler.py:587 _create_analysis_node`:
   엑셀 첨부가 없으면 `_analyze_context`(L669)로 분기하여 **직전 검색 결과가 있으면 그것을 데이터로** 질문을 분석한다. 즉 "search 데이터로 데이터분석" 능력 자체는 구현돼 있고, **그 노드까지 도달하지 못하는 라우팅이 문제**다.
2. **차트 경로는 analysis 워커 직후에만 배선된다** — `workflow_compiler.py:373~378`:
   `analysis_worker_ids`에 속한 워커만 `worker → chart_router` 엣지를 갖고, 그 외 워커(search 포함)는 `quality_gate` 직결. `chart_builder`(L344~358)도 chart_router 뒤에만 있다.
3. **결정적 강제 라우팅은 엑셀 첨부 한정** — `supervisor_hooks.py:20 AttachmentRoutingHooks`:
   `_ROUTABLE_TYPES = ("excel",)`. 첨부 없는 시각화 요청에는 `force_worker`가 `None`을 반환한다.
4. **supervisor decision prompt에 시각화 안내 부재** — `supervisor_nodes.py:122~134`:
   첨부 인지 블록(`_render_attachment_block`)은 있으나, "그래프/차트 요청은 분석 워커를 거쳐야 생성된다"는 정보가 없다. LLM은 검색 결과가 메시지에 쌓이면 자연스럽게 `FINISH`를 선택한다.
5. **루프 방지 장치는 이미 존재** — `chart_builder`가 `visualization_done=True` 세팅(`chart_builder_node.py:51`) → `skip_workers`가 분석 워커를 제외(`supervisor_hooks.py:49~54`). 신규 강제 라우팅도 이 플래그와 `last_worker_id` 가드를 재사용하면 무한 루프 없음.

### 1-3. 시각화 의도 감지 수단 (기존 자산 재사용)

`src/domain/visualization/policies.py VisualizationRoutingPolicy.explicit_request(question)`:
"그래프, 차트, 시각화, 그려, 도표, 추이, plot, chart, graph, visualize" 키워드 매칭 (LLM 불필요, 도메인 정책). chart_router가 이미 사용하는 휴리스틱과 동일 기준이라 판단 일관성도 확보된다.

---

## 2. 목표 / 비목표

### 2-1. 목표
- **G1.** 첨부 없는 시각화 요청 시, 검색 결과 수집 후 분석 워커가 **결정적으로** 실행되도록 강제 라우팅 Hook 추가.
- **G2.** supervisor decision prompt에 시각화 가이드 블록 추가 — "차트 생성은 분석 워커 경유 필수, 데이터 필요 시 검색 → 분석 순서" (LLM 수준 보강).
- **G3.** 기존 경로 무회귀: 엑셀 첨부 강제 라우팅, 비시각화 질문, `visualization_done` 루프 방지 동작 유지.
- **G4.** TDD — Hook 단위 테스트 + supervisor 통합 라우팅 테스트 작성 후 구현.

### 2-2. 비목표
- **N1.** chart_router / chart_builder / VisualizationRoutingPolicy 자체 로직 변경 (재사용만 한다).
- **N2.** search 워커가 없는 에이전트의 시각화 품질 개선 (분석 노드의 대화 문맥 fallback은 기존 동작 유지).
- **N3.** 프론트엔드 차트 렌더링 변경 (백엔드 charts 페이로드 형식 불변 → API 계약 변경 없음).
- **N4.** General Chat / Excel standalone 경로 변경.

---

## 3. 해결 방안 (옵션 비교)

| 옵션 | 내용 | 장점 | 단점 |
|------|------|------|------|
| **A (권장)** | **Hook 강제 + prompt 가이드 하이브리드.** `AttachmentRoutingHooks`를 확장(또는 `VizIntentRoutingHooks` 신설)해 "시각화 의도 + 검색 결과 존재 + 분석 미실행 + `visualization_done` False"일 때 분석 워커 강제. 동시에 decision prompt에 시각화 안내 블록 추가. | 핵심 케이스(search 후 FINISH 이탈)를 **결정적으로** 차단. 기존 설계 패턴(첨부 강제 라우팅)과 일관. prompt 보강은 search 우선 호출도 유도. | Hook 조건이 1개 늘어남(복잡도 소폭 증가). |
| **B** | prompt 가이드만 추가 (Hook 없음). | 변경 최소. | LLM 판단 의존 → 비결정적. 모델/온도에 따라 재발 가능. 기존 코드가 "LLM이 첨부를 인지 못해 거부하는 것을 결정적으로 차단한다"며 prompt만으로는 부족함을 이미 경험. |
| **C** | 그래프 배선 변경 — search 워커 직후 conditional edge로 시각화 의도 시 분석 워커 직결. | 구조적 보장. | search→analysis 결합이 그래프에 고정돼 supervisor 오케스트레이션 원칙 훼손(워커 간 직접 엣지 없음이 현 설계). 아키텍처 변경에 해당해 AI 자율 수행 범위 초과. |

**권장: Option A.** 엑셀 첨부 라우팅과 동일한 "결정적 Hook + LLM 인지 블록" 패턴을 그대로 확장한다. 그래프 토폴로지는 건드리지 않는다.

---

## 4. 목표 동작 설계 (Option A)

### 4-1. Hook 강제 조건 (force_worker 확장)

```
다음을 모두 만족하면 분석 워커 강제:
  1. 분석 워커가 존재 (analysis_worker_ids 비어있지 않음)
  2. 최근 사용자 질문에 시각화 의도 (VisualizationRoutingPolicy.explicit_request)
  3. messages에 검색 결과 존재 (search_pipeline.is_search_result 재사용)
     → 검색이 아직 안 됐으면 강제하지 않음 (supervisor가 search를 먼저 선택하도록 둠)
  4. 분석 워커 미실행 (last_worker_id != 대상 워커 — 기존 가드 재사용)
  5. visualization_done == False (차트 생성 완료 후 재강제 금지)
```

- 기존 엑셀 첨부 강제 조건은 그대로 유지 (엑셀 우선 → 시각화 의도 순으로 평가).
- 워커 1회 실행 후에는 강제하지 않아 LLM이 종합/FINISH 하도록 두는 기존 원칙 유지.

### 4-2. prompt 시각화 가이드 블록 (supervisor_nodes)

`_render_attachment_block`과 동일한 패턴으로, 분석 워커가 있을 때 decision prompt에 추가:

```
[시각화 안내]
그래프/차트/시각화 요청은 분석 워커를 거쳐야만 차트가 생성됩니다.
외부 데이터가 필요하면 먼저 검색 워커로 데이터를 수집한 뒤,
반드시 분석 워커를 호출하세요. 검색 결과만으로 FINISH 하지 마세요.
```

- 시각화 키워드가 질문에 있을 때만 블록을 삽입할지(노이즈 최소화), 분석 워커 존재 시 상시 삽입할지는 Design에서 확정.

### 4-3. 배선 (workflow_compiler)

- `compile()`의 `effective_hooks` 결정부(L240~242)에서 신규 Hook으로 대체.
- Hook 생성에 필요한 의존성: `analysis_worker_ids`(기존), `VisualizationRoutingPolicy`(domain), `latest_user_question`/`is_search_result`(search_pipeline) — 모두 application 레이어에서 import 가능 (domain 정책 재사용이라 레이어 위반 없음).

---

## 5. 영향 범위 (Affected Files)

| 파일 | 변경 |
|------|------|
| `src/application/agent_builder/supervisor_hooks.py` | `AttachmentRoutingHooks.force_worker`에 시각화 의도 강제 조건 추가 (또는 확장 클래스 신설) |
| `src/application/agent_builder/supervisor_nodes.py` | decision prompt에 시각화 가이드 블록 렌더 함수 추가 (`_render_attachment_block` 패턴) |
| `src/application/agent_builder/workflow_compiler.py` | `effective_hooks` 조립부 — 신규 Hook 주입 (정책/헬퍼 전달) |
| (변경 없음) `src/domain/visualization/policies.py` | `explicit_request` 재사용만 |
| (변경 없음) `chart_router` / `chart_builder` / `_create_analysis_node` | 기존 경로 그대로 사용 |

### 5-1. 테스트 영향
- `tests/application/agent_builder/test_supervisor_hooks.py` (또는 기존 hooks 테스트) — 신규 강제 조건 5종 단위 테스트: 시각화 의도 O/X, 검색 결과 유/무, 분석 실행 전/후, visualization_done, 엑셀 첨부와의 우선순위.
- `tests/application/agent_builder/test_supervisor_node.py` — prompt에 시각화 가이드 블록 포함 검증.
- `tests/application/agent_builder/test_workflow_compiler.py` — 통합: search 결과가 쌓인 state에서 supervisor가 분석 워커로 강제 라우팅되는 시나리오, 차트 생성 후 재강제 없음(루프 방지) 회귀.

### 5-2. Cross-Project (API 계약)
- 응답 스키마 변경 **없음** — charts 페이로드 형식(`ChartConfig`) 그대로. `/api-contract-sync` 불필요.

---

## 6. 작업 분해 (TDD: Red → Green → Refactor)

1. **(Red)** Hook 시각화 강제 조건 단위 테스트 작성 — 5개 조건 조합별 force_worker 반환값 단언.
2. **(Green)** `supervisor_hooks.py` 강제 조건 구현 (`VisualizationRoutingPolicy.explicit_request` + `is_search_result` 재사용).
3. **(Red)** supervisor decision prompt 시각화 블록 테스트 작성.
4. **(Green)** `supervisor_nodes.py` 가이드 블록 추가.
5. **(Red→Green)** `workflow_compiler.py` Hook 조립 변경 + 통합 라우팅 테스트.
6. **(회귀)** 엑셀 첨부 강제 라우팅·비시각화 질문·visualization_done 루프 방지 기존 테스트 통과 확인.
7. **(Refactor/verify)** `verify-architecture`, `verify-logging`, 관련 pytest 격리 실행 (Windows 이벤트 루프 flakiness 회피 — 메모리 참조).

---

## 7. 리스크 / 주의사항

- **R1. 무한 루프** — 강제 라우팅 후 분석 → 차트 → supervisor 복귀 시 재강제되면 루프. → `last_worker_id` 가드 + `visualization_done` 체크 + 기존 `skip_workers`(visualization_done 시 분석 워커 제외) 3중 방어. 통합 테스트로 단언.
- **R2. 검색 결과 없는 시각화 요청** — search 워커가 없는 에이전트이거나 supervisor가 search를 건너뛴 경우, 강제 조건 3(검색 결과 존재) 미충족으로 Hook은 침묵하고 prompt 가이드에만 의존. 분석 노드의 대화 문맥 fallback이 동작하지만 데이터 품질은 낮을 수 있음 — 비목표(N2)로 명시, Design에서 "검색 결과 없으면 분석 강제 안 함"이 맞는지 재확인.
- **R3. 키워드 오탐** — "그려" 등 키워드가 비시각화 맥락에서 매칭될 수 있음. 다만 강제 대상이 분석 워커 1회 실행뿐이라 부작용은 분석 1회 추가 수준 (chart_router가 다시 휴리스틱+LLM으로 판단하므로 차트 오생성은 아님).
- **R4. 멀티턴** — 이전 턴에서 차트를 이미 생성한 대화에서 새 질문이 오면 `visualization_done`이 초기 state에서 리셋되는지 확인 필요 (`build_initial_state`는 매 run마다 False로 초기화 — OK, Design에서 재확인).
- **R5. forced 경로의 skipped 미반환** — `supervisor_node`의 forced 분기(L110~115)는 `skipped_workers`를 갱신하지 않음. 기존 동작이지만 신규 강제와 상호작용 점검.

---

## 8. Design 단계 Open Questions

1. **Hook 형태** — `AttachmentRoutingHooks` 확장 vs `VizIntentRoutingHooks` 신설 후 체인 구성. (단일 클래스 확장이 단순하나 책임 분리 관점 검토)
2. **prompt 블록 삽입 조건** — 분석 워커 존재 시 상시 vs 시각화 키워드 감지 시에만.
3. **검색 결과 없는 시각화 요청 처리** — Hook 침묵(권장) vs 분석 워커라도 강제(대화 문맥 fallback 활용).
4. **search 우선 유도** — 시각화 의도 + 검색 결과 없음 + search 워커 존재 시 search 워커를 강제할지 (범위 확대라 기본은 prompt 유도만).

---

## 9. 다음 단계

```
/pdca design supervisor-viz-routing
```
