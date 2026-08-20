---
title: 동기+SSE 이중 노출 — 공유 async generator + 고정 단계(steps) 계약
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/application/agent_create_pipeline/use_case.py (모듈 docstring + run — 이벤트·최종 결과를 한 제너레이터가 yield) — ⚠️ 미커밋
  - idt/src/api/routes/agent_pipeline_router.py (run_pipeline=소진, _sse_stream=실시간, stage_failed 합성) — ⚠️ 미커밋
  - idt/src/domain/agent_create_pipeline/stages.py (PipelineStage/StageStatus StrEnum — value 가 wire 계약)
  - idt/src/domain/agent_create_pipeline/policies.py:113 (finalize_steps — 미도달 skipped 채움)
  - idt/tests/api/test_agent_pipeline_router.py:266 (test_sse_final_payload_equals_sync_response — 바이트 동일성)
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.report.md (§1.3, §6.1 FR-15)
confidence: 0.85
version: 1
created: 2026-08-19
updated: 2026-08-19
verified_at: 7c3ffdd
---

# 동기+SSE 이중 노출 — 공유 async generator + 고정 단계 계약

> ⚠️ **근거 코드 전량이 `7c3ffdd` 기준 미커밋 상태**다. 커밋 후 `verified_at` 재기록 필요.

## 문제

같은 작업을 동기 응답과 스트리밍(SSE) 두 엔드포인트로 노출하면, "두 경로의 최종 결과가
같다"는 계약을 지켜야 한다. 두 라우터가 각자 UseCase를 호출·조립하면 이 계약은 리뷰
규율에만 의존하게 되고 언젠가 표류한다. 또 화면이 단계 진행 바를 그리려면 "몇 단계가
어떤 순서로 오는가"가 응답마다 흔들리면 안 된다.

agent-create-pipeline(`POST /api/v1/agents/pipeline` + `/stream`)이 이 두 문제를
**코드 구조로** 해결했다 (FR-15, Match 97%).

## 검증된 사실

### 1. 의미 동일성은 리뷰가 아니라 구조로 강제한다

UseCase의 `run()`이 async generator 하나로 `StageEvent`(단계 시작/완료)들을 yield하고
**마지막에 `PipelineOutcome`을 yield**한다. 소비 방식만 다르다:

- 동기 라우터: 제너레이터를 소진하며 `PipelineOutcome`만 취해 응답으로 변환
- SSE 라우터: 각 항목을 실시간 송출, 마지막 outcome은 `pipeline_result` 이벤트로

두 경로가 **물리적으로 같은 객체**를 다루므로 "최종 payload 의미 동일"이 설계가 아니라
구조의 귀결이 된다. 그 위에 `test_sse_final_payload_equals_sync_response`가
직렬화 결과의 동일성까지 이중 확인한다.

기존 선례(General Chat의 transport-독립 `stream()`/`execute()` 래퍼)와 같은 계열이며,
이번에는 "이벤트 나열 + 최종 결과"를 한 제너레이터에 싣는 형태로 확장됐다.

### 2. steps는 항상 고정 N개 — 미도달은 skipped로 채운다

응답의 `steps[]`는 도달 여부와 무관하게 **항상 5개**(intent→tools→prompt→create→bind)다.
`PipelinePolicy.finalize_steps(records, skip_reason)`가 미도달 단계를
`skipped + reason`으로 채워 반환한다. need_input으로 중간에 멈춰도, 실패로 끊겨도 5개.

효과: 화면은 단계 바를 **고정 렌더**하고 상태(ok/degraded/failed/skipped)만 칠하면
된다 — "이번엔 3개만 왔다" 류의 프론트 방어 코드가 필요 없다.

### 3. wire 문자열은 StrEnum value — 변경 = 프론트 계약 파괴

단계명·상태명은 `PipelineStage`/`StageStatus`(StrEnum)의 `.value`가 그대로 wire에
실린다. stages.py 모듈 docstring이 "변경은 곧 프론트 계약 파괴"를 명시하고, 테스트가
문자열 값을 고정한다. 임의 dict 키나 f-string으로 흩어놓지 않는다.

### 4. 스트림 시작 후의 실패는 HTTP 에러가 될 수 없다 — SSE 레이어가 합성한다

UseCase는 저장 실패를 그대로 전파하는 것이 계약이다(try/except 금지 —
[[degradation-vs-failure-boundary]]). 그런데 SSE는 이미 200으로 스트림이 열린 뒤라
5xx를 줄 수 없다. 그래서 `_sse_stream`이 예외를 받아 `stage_failed` +
`pipeline_result(status=failed)`로 **합성**한다 — 어느 단계에서 죽었는지는 마지막
`stage_started` 기록으로 복원. 실패 표현의 책임이 동기(HTTP 상태코드)와
SSE(이벤트)로 갈리지만, 원천(UseCase의 예외 전파)은 하나다.

## 다음에 적용하는 법

1. 동기+스트리밍 이중 노출이 필요하면 엔드포인트별 구현 대신 **UseCase를
   async generator 하나**(이벤트… + 최종 결과)로 만들고 라우터는 소비 방식만 달리한다.
2. "두 응답 동일" 계약에는 직렬화 결과 동일성 테스트를 세트로 붙인다.
3. 화면용 다단계 상태는 **고정 단계 목록 + 미도달 skipped 채움**을 domain Policy로
   보장하고, 단계/상태 문자열은 StrEnum으로 단일화해 테스트로 고정한다.
4. 스트림 경로의 실패 표현(이벤트 합성)은 라우터/SSE 어댑터에 두고, UseCase의 예외
   전파 계약은 건드리지 않는다.

## 관련 문서

- heartbeat 구현의 함정: [[sse-heartbeat-async-generator]]
- degraded/전파 경계: [[degradation-vs-failure-boundary]]
- transport-독립 스트림 선례: [[architecture-overview]] §2(a)
