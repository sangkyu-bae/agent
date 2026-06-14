# Gap Analysis: supervisor-viz-routing

> Created: 2026-06-11
> Phase: Check
> Design: `docs/02-design/features/supervisor-viz-routing.design.md`
> Analyzer: gap-detector
> **Match Rate: 100%**

---

## 1. 분석 개요

- 대상: supervisor-viz-routing (시각화 요청 시 search → data_analysis 경유 보장 라우팅)
- 구현 파일: `supervisor_hooks.py`, `supervisor_nodes.py`, `workflow_compiler.py`, `test_supervisor_viz_routing.py`
- 검증 항목 7개 전부 Match (D1~D4=4/4, §2-1~2-3=3/3, §3 가드=5/5, TC-1~11=11/11, §6 비변경 충족)

---

## 2. 검증 항목별 판정

### 2-1. §0 설계 결정 D1~D4 — MATCH (4/4)

| 결정 | 설계 기대 | 구현 확인 | 판정 |
|---|---|---|---|
| D1 | AttachmentRoutingHooks 제자리 확장, `viz_policy` 옵셔널 주입 | hooks.py 생성자 `viz_policy: ... = None` | Match |
| D2 | viz 키워드 감지 시에만 prompt 블록 | nodes.py `viz_policy is None or not ids → ""`, `explicit_request` 가드 | Match |
| D3 | 검색결과 없으면 Hook 침묵 | hooks.py `any(is_search_result(m) ...)` — 없으면 False | Match |
| D4 | search 강제 라우팅 없음 | search 워커 force 코드 없음, prompt 유도만 | Match |

핵심 일관성 근거도 충족: Hook·prompt 블록·chart_router가 모두 동일 `VisualizationRoutingPolicy.explicit_request`를 공유.

### 2-2. §2-1 supervisor_hooks.py — MATCH

- 가드 순서: 빈 ids → `last_worker_id == target` → `visualization_done` → attachment → viz_intent. 설계와 동일 순서.
- `_viz_intent_with_search_results`: `viz_policy None` → False, `explicit_request` False → False, `is_search_result` any. 동일.
- 하위호환(`viz_policy=None`) 분기로 보장.

### 2-3. §2-2 supervisor_nodes.py — MATCH

- `_render_viz_guidance_block(messages, analysis_worker_ids, viz_policy)` 시그니처/조건/블록 문구 일치.
- `create_supervisor_node` 옵셔널 파라미터 2개 일치.
- 블록 삽입 위치: `{attachment_block}{viz_block}` — 첨부 블록 뒤 확인.
- 표현 차이(무영향): 설계 스니펫의 지연 import 대신 모듈 상단 import로 통일 — 설계 주석이 허용하는 형태.

### 2-4. §2-3 workflow_compiler.py — MATCH

- viz_policy 생성 조건(`if analysis_worker_ids:`), DefaultHooks `isinstance` 체크 유지, `create_supervisor_node` 전달 인자(`analysis_worker_ids=sorted(...)`, `viz_policy`) 모두 일치.
- `VisualizationRoutingPolicy` 기존 import 재사용, 추가 import 없음.

### 2-5. §3 루프 안전성 가드 — MATCH (5/5)

| 시나리오 | 방어 | 구현 확인 |
|---|---|---|
| 재강제(visualization_done) | done 가드 + skip_workers | hooks.py |
| 분석 직후 복귀 | `last_worker_id == target` | hooks.py |
| 분석 2회 잔여리스크 | iteration 상한 (수용된 리스크) | nodes.py |
| 멀티턴 초기화 | build_initial_state done=False/last="" | nodes.py |
| 품질피드백 오인 방지 | latest_user_question의 PREFIX 제외 | search_pipeline.py |

### 2-6. §4 테스트 TC-1~11 — MATCH (11/11 + 회귀/단위 4)

TC-1~11 전부 존재 + 추가 강건성 테스트 4건(엑셀 강제 회귀, 블록 단위 3건) = 15건. 전체 통과 확인됨(Do 단계에서 396건 회귀 포함).

### 2-7. §6 비변경 확인 — MATCH

- `chart_router.py` / `chart_builder_node.py`: 수정 없음.
- `VisualizationRoutingPolicy`: 기존 `explicit_request` read-only 재사용만.
- `_create_analysis_node` / `final_answer`: 본문 기존 로직 그대로, viz-routing 신규 코드 없음.

---

## 3. Gap 리스트

**실질적 갭 없음.** 아래는 설계 발췌와 구현 간 표현 차이(무영향)로 갭 미분류:

| 심각도 | 위치 | 설계 표기 | 실제 구현 | 평가 |
|---|---|---|---|---|
| Info | nodes.py 상단 | 함수 내부 지연 import (스니펫) | 모듈 상단 import | 설계 주석이 허용 — 갭 아님 |
| Info | hooks.py | 스니펫에 Protocol/DefaultHooks 생략 | 기존 코드 그대로 존재 | 발췌 축약 — 갭 아님 |

---

## 4. 결론

**Match Rate 100% — Check 통과 기준(90%) 초과.**
iterate(Act) 불필요. 다음 단계: `/pdca report supervisor-viz-routing`
