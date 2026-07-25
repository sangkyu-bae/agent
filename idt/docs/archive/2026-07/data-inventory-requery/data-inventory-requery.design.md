# Data Inventory Requery Design Document

> **Summary**: 시각화 강제 라우팅의 재주입분 오탐 제거 구현 설계 — 재주입 판정·질문 추출은 domain 정책에 단일 출처화(D1), hooks는 현재 턴 수집분만 트리거(D2), 보유 데이터 블록은 수집 구분·원 질문이 보이는 인벤토리로 강화(D3), 스냅샷 누적 경로는 무변경 확인(D4), skip 관측성은 optional logger로 additive 주입(D5)
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-07-22
> **Status**: Draft
> **Plan Reference**: `docs/01-plan/features/data-inventory-requery.plan.md`

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 이전 턴 재주입 검색결과가 `is_search_result()`를 통과해 `_viz_intent_with_search_results`가 분석 워커를 강제 — supervisor LLM의 재사용/재수집 판단이 구조적으로 우회됨 |
| **Solution** | 재주입 식별·질문 추출을 `AnalysisSnapshotPolicy`에 단일 출처화하고, hooks 트리거를 "현재 턴 수집분 존재"로 좁히며, 인지 블록을 항목별 [이번 턴 수집/이전 턴 보유]+원 질문 인벤토리로 강화 |
| **Function/UX Effect** | 범위 확대 재질문은 LLM 판단으로 재검색 경유, 동일 범위 재질문은 재검색 없이 분석 직행 — 양쪽 모두 차트 경로(검색 후 강제 라우팅) 보존 |
| **Core Value** | 결정적 강제(확실 신호)와 LLM 판단(불확실 판단)의 책임 분리 — 변경 3파일·구조 변경 0·마이그레이션 0 |

---

## 1. Design Overview

수정 대상은 3개 파일. 그래프 구조·메시지 규약(`is_search_result`)·스냅샷 저장 정책은 무변경.

```
analysis_snapshot_policy.py (domain)
    ├── [기존] REINJECTED_MARKER · is_reinjected()          ← 재사용 (규약 단일 출처)
    └── [신규] extract_reinjected_question()                 ← D1: 재주입 헤더에서 원 질문 파싱
            │
            ├── supervisor_hooks.py  _viz_intent_with_search_results
            │       └── D2: is_reinjected 제외 필터 + D5: optional logger
            └── supervisor_nodes.py  _render_data_context_block
                    └── D3: 인벤토리 렌더 (수집 구분 + 원 질문 + 요약)

workflow_compiler.py:273  AttachmentRoutingHooks(...)        ← D5: logger 전달 (1줄)
```

**영향 범위 실측 (2026-07-22)**:
- `_viz_intent_with_search_results` 소비처: `AttachmentRoutingHooks.force_worker` 1곳뿐
- 기존 테스트: `test_supervisor_viz_routing.py` TC-1~11(현재 턴 수집 시나리오만 — 재주입 케이스 없음),
  `test_supervisor_data_context.py`(블록 단언: `[보유 분석 데이터]`·`범위를 벗어나면`·`검색 워커`),
  `test_supervisor_hooks.py`(Default/Custom hooks 계약)
- D3 문구는 기존 단언 substring(`범위를 벗어나면`, `검색 워커`)을 보존해 **기존 테스트 무수정 통과** 목표
- `AttachmentRoutingHooks` 생성처: `workflow_compiler.py:273` 1곳 + 테스트 헬퍼 — logger 기본값 None으로
  기존 생성 코드 전부 무변경

---

## 2. D1 — 재주입 질문 추출 헬퍼 (domain 단일 출처)

### 2.1 결정

재주입 본문의 렌더(`render_reinjection_body`)와 파싱을 같은 모듈에 둔다.
supervisor_nodes에서 마커 문자열을 직접 파싱하면 렌더 형식 변경 시 조용히 깨진다.

### 2.2 analysis_snapshot_policy.py 추가

```python
@staticmethod
def extract_reinjected_question(content: str) -> str:
    """재주입 본문 헤더의 원 질문 추출 — render_reinjection_body와 쌍.

    형식: "{REINJECTED_MARKER} (질문: {q})\n..." → q. 비재주입/형식 불일치 시 "".
    """
```

- 구현: 첫 `REINJECTED_MARKER` 라인에서 `(질문: ` 이후 ~ 마지막 `)` 이전 추출.
  `is_reinjected(content)`가 False면 즉시 `""` (방어적 가드 1단 — 중첩 규칙 준수)
- 순수 함수·외부 의존 0 (domain 규칙 유지)

---

## 3. D2 — hooks 트리거를 현재 턴 수집분으로 제한

### 3.1 supervisor_hooks.py 변경

```python
from src.domain.conversation.analysis_snapshot_policy import AnalysisSnapshotPolicy

def _viz_intent_with_search_results(self, state: SupervisorState) -> bool:
    """시각화 의도 + '현재 턴에서 수집한' 검색 결과 → 분석 강제 대상.

    data-inventory-requery D2: 재주입분(이전 턴 스냅샷)은 트리거에서 제외 —
    재주입분만 있으면 첫 라우팅은 supervisor LLM이 인벤토리를 근거로
    재사용/재수집을 판단한다 (검색 실행 후에는 기존대로 강제).
    """
    if self._viz_policy is None:
        return False
    messages = state.get("messages", []) or []
    if not self._viz_policy.explicit_request(latest_user_question(messages)):
        return False
    has_current = any(
        is_search_result(m)
        and not AnalysisSnapshotPolicy.is_reinjected(getattr(m, "content", ""))
        for m in messages
    )
    if not has_current and self._logger is not None and any(
        is_search_result(m) for m in messages
    ):
        self._logger.info(
            "viz force-routing skipped: only reinjected data present",
        )
    return has_current
```

- 함수가 40줄 근접 시 `has_current` 계산을 모듈 함수 `_has_current_turn_search_result(messages)`로
  분리 (구현 시 판단)
- **레이어 근거**: application → domain 참조는 허용 방향. 마커 재정의(이중 출처) 금지
- 엑셀 첨부 트리거(`_has_routable_attachment`)·공통 가드(last_worker/visualization_done)는 무변경 (FR-03)

### 3.2 시나리오 매트릭스 (결정적 동작)

| state 상황 | 변경 전 | 변경 후 |
|-----------|--------|--------|
| viz 의도 + 현재 턴 수집 검색결과 | 분석 강제 | 분석 강제 (불변, FR-02) |
| viz 의도 + 재주입분만 | **분석 강제 (결함)** | 강제 없음 → LLM 판단 (FR-01) |
| viz 의도 + 재주입분 + 현재 턴 수집분 | 분석 강제 | 분석 강제 (검색 직후 턴 내 상황) |
| viz 의도 + 검색결과 없음 | 강제 없음 (D3 침묵) | 불변 |
| 엑셀 첨부 | 분석 강제 | 불변 (FR-03) |

2턴 기대 주행: 재주입분만 → 강제 없음 → LLM이 인벤토리(D3) 보고 "전체 사용자 = 범위 밖" →
search 워커 → 현재 턴 수집분 생성 → 다음 supervisor 진입 시 강제 라우팅 발동 → 분석 → chart_router → 차트.

---

## 4. D3 — 데이터 인벤토리 블록

### 4.1 supervisor_nodes.py `_render_data_context_block` / `_summarize_data_entry` 변경

항목 렌더 형식 (한 줄 유지 — 토큰 절약 원칙 계승):

```
[보유 분석 데이터]
1. [이전 턴 보유] search_w — 원 질문: "나의 남은 휴가 개수와 월별 사용 현황" — 남은 휴가: 15일 … (1830자)
2. [이번 턴 수집] search_w — 남은 휴가 전체 사용자: 배상규 15일, … (2140자)
- 위 목록을 항목별로 순회하며 현재 요청의 대상·기간·집단을 보유 데이터가 커버하는지 확인하세요.
- 전부 커버하면 데이터 재수집 없이 분석 워커를 호출하세요.
- 하나라도 범위를 벗어나면(대상·기간·집단 확대 등) 먼저 검색 워커로 새 데이터를 수집한 뒤 분석 워커를 호출하세요.
```

- 수집 구분: `AnalysisSnapshotPolicy.is_reinjected(content)` → `[이전 턴 보유]` / `[이번 턴 수집]`
- 원 질문: 재주입 항목만 `extract_reinjected_question(content)` (D1) — `_QUESTION_MAX_CHARS`로
  이미 절단돼 있어 추가 절단 불필요. 추출 실패(`""`) 시 라벨만 표기
- 요약 head: 재주입 항목은 마커 헤더 라인을 **건너뛰고** 실제 데이터 첫 줄에서 추출
  (현재 구현은 마커 라인이 head 80자를 잠식 — 이 결함도 함께 해소)
- 지시 문구는 기존 테스트 단언 substring `범위를 벗어나면`·`검색 워커`를 보존 (§1 무수정 통과 목표)
- `_summarize_data_entry`는 (index, msg) → 라벨·질문·head 조립으로 확장하되 40줄 이내 유지 —
  초과 시 `_entry_label`/`_entry_head` 보조 함수 분리

### 4.2 비변경 확인

- 블록 생성 조건(검색결과 0건 → `""`)·삽입 위치(decision_prompt 내)·viz_block과의 병렬 관계 불변
- `_render_viz_guidance_block`·첨부 블록·결정 선택지 문구 불변 (supervisor-overblock-fix 산출물 보존)

---

## 5. D4 — 스냅샷 누적 경로 (코드 무변경 확인)

Plan S3의 "인벤토리 리스트 누적"은 기존 체계가 이미 충족함을 실측 확인했다:

| 요구 | 기존 구현 | 확인 방법 |
|------|----------|----------|
| 재검색 수집분 영속 | `_snapshot_items`가 비재주입 검색결과만 수집 (`run_agent_use_case.py:863-871`) | 기존 테스트 + FR-05 시나리오 테스트 |
| 리스트 누적 | `select_recent`가 retention(기본 2)·상한 내 최신 스냅샷 복수 선별 (`analysis_snapshot_policy.py:131-152`) | 기존 테스트 커버 확인, 부족 시 1건 추가 |
| 다음 턴 제시 | `_inject_snapshot_messages` → 재주입 → D3 인벤토리 렌더 | TC-B 렌더 테스트 |

**한계 명시 (Design 확정)**: retention=2 기본값에서 3턴 이전 수집분은 인벤토리에서 탈락한다.
이는 기존 analysis-data-continuity 상한 정책이며 이번 범위에서 변경하지 않는다 (Plan Out of Scope).
E2E에서 부족이 실증되면 config(retention) 조정으로 대응 가능 — 코드 변경 불필요.

---

## 6. D5 — 강제 라우팅 skip 관측성 (optional logger)

- `AttachmentRoutingHooks.__init__(..., logger: LoggerInterface | None = None)` — additive,
  기본 None → 무로그 (기존 생성처·테스트 무변경, 독립 opt-in 관례)
- `workflow_compiler.py:273` 생성부에 `logger=self._logger` 전달 (1줄)
- 로그 시점: viz 의도 + 검색결과 존재 + 전부 재주입분 (= 변경 전이라면 강제됐을 상황) — info 레벨,
  LOG-001 structured (print 금지)

---

## 7. Test Specification (TDD 순서)

### 7.1 신규 테스트

| TC | 파일 | 검증 | FR |
|----|------|------|-----|
| TC-A1 | test_supervisor_viz_routing.py | viz 의도 + 재주입분만 → `force_worker` None | FR-01 |
| TC-A2 | 〃 | viz 의도 + 재주입분 + 현재 턴 수집분 → 분석 강제 | FR-02 |
| TC-A3 | 〃 | 재주입분만 + logger 주입 시 info 로그 1회 / logger 미주입 시 무로그·무예외 | NFR 로깅 |
| TC-A4 | 〃 (통합) | supervisor_node: 재주입분만 → LLM 호출됨(`with_structured_output` called) — TC-8의 역방향 | FR-01 |
| TC-B1 | test_supervisor_data_context.py | 재주입 항목 → `[이전 턴 보유]` + `원 질문:` + 원 질문 텍스트 렌더 | FR-04 |
| TC-B2 | 〃 | 현재 턴 항목 → `[이번 턴 수집]` 라벨 + 데이터 head (마커 미포함) | FR-04 |
| TC-B3 | 〃 | 지시 문구: 순회 지시 + `범위를 벗어나면` + `검색 워커` 포함 | FR-04 |
| TC-C1 | domain 테스트 (analysis_snapshot_policy) | `extract_reinjected_question`: 정상 추출 / 비재주입 → "" / 형식 불일치 → "" | D1 |
| TC-D1 | 기존 스냅샷 테스트 파일 | 재검색 수집분 + 이전 스냅샷이 select_recent로 함께 선별 (기존 커버 확인 후 부족 시만 추가) | FR-05 |

재주입 메시지 픽스처는 실제 경로와 동형으로 생성:
`AIMessage(name=w, content=format_search_result(w, policy.render_reinjection_body(snap, item)))`
— 문자열 하드코딩 픽스처 금지 (렌더 형식 변경 시 테스트가 함께 깨지도록).

### 7.2 기존 테스트 회귀 기준

- test_supervisor_viz_routing.py TC-1~11: **무수정 통과** (현재 턴 수집 픽스처는 마커 없음)
- test_supervisor_data_context.py: 무수정 통과 목표 (D3 문구가 단언 substring 보존) —
  `1. search_worker — 휴가 15일` 형식 단언은 없으므로 라벨 추가에 안전
- test_supervisor_hooks.py / test_supervisor_attachment.py: 무수정 통과 (트리거·가드 불변)
- 실행: Windows 이벤트 루프 flakiness 관례에 따라 파일 단위 격리 실행

---

## 8. Implementation Order

```
1. D1  domain 헬퍼: TC-C1 Red → extract_reinjected_question 구현 → Green
2. D2  hooks: TC-A1~A4 Red → 재주입 제외 + optional logger → Green (기존 TC-1~11 무회귀 확인)
3. D3  인벤토리 블록: TC-B1~B3 Red → _render_data_context_block/_summarize_data_entry 개선 → Green
4. D5  workflow_compiler logger 배선 (1줄) — 기존 compiler 테스트 무회귀
5. D4  FR-05 커버리지 확인 (기존 테스트 목록 대조, 부족 시 TC-D1 추가)
6. 전체 pytest 격리 실행 + verify-architecture / verify-logging / verify-tdd
7. E2E 수동 (FR-06/07): 1턴 "나의 남은 휴가 그래프" → 2턴 "전체 사용자 남은 휴가 그래프"
   (search step 존재·query·히트 확인) → 3턴 "방금 그 데이터 막대그래프로" (search step 부재 확인)
   — 2턴 검색 0건이면 rag-auth-payload-indexing 트랙으로 이관 (라우팅 수정과 분리)
```

---

## 9. 변경 파일 요약

```
idt/src/
├── domain/conversation/analysis_snapshot_policy.py     # D1: extract_reinjected_question (staticmethod)
├── application/agent_builder/supervisor_hooks.py       # D2·D5: 재주입 제외 + optional logger
├── application/agent_builder/supervisor_nodes.py       # D3: 인벤토리 렌더·순회 지시
├── application/agent_builder/workflow_compiler.py      # D5: logger 전달 1줄
└── tests/
    ├── domain/conversation/ (스냅샷 정책 테스트)         # TC-C1
    └── application/agent_builder/
        ├── test_supervisor_viz_routing.py               # TC-A1~A4
        └── test_supervisor_data_context.py              # TC-B1~B3
```

API 계약·DB 스키마·프론트엔드·환경변수 변경 없음.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-07-22 | Initial draft — 트리거 매트릭스·인벤토리 렌더 형식·기존 테스트 무수정 통과 전략 확정 | 배상규 |
