---
title: SSE heartbeat — wait_for 는 큐 기반 스트림 전용, 직접 await 제너레이터는 asyncio.wait
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/api/routes/agent_pipeline_router.py (_sse_stream — docstring 에 사유 명시) — ⚠️ 미커밋
  - idt/src/api/routes/agent_builder_router.py:327-364 (run/stream 의 wait_for 패턴 — 큐 기반 전제)
  - idt/tests/api/test_agent_pipeline_router.py:344 (test_sse_emits_heartbeat_while_stage_is_slow — 이벤트 무손실 동시 단언)
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.analysis.md (§8.1 G-01)
  - docs/archive/2026-08/agent-create-pipeline/agent-create-pipeline.report.md (§6.2 "기존 패턴의 맹목 복사 위험")
confidence: 0.85
version: 1
created: 2026-08-19
updated: 2026-08-19
verified_at: 7c3ffdd
---

# SSE heartbeat — `wait_for` 패턴에는 전제 조건이 있다

> ⚠️ **근거 코드(`agent_pipeline_router.py`)는 `7c3ffdd` 기준 미커밋 상태**다.
> 커밋 후 `verified_at` 재기록 필요 ([[detachable-module-seam]] 선례와 동일).

## 문제

LLM을 여러 번 기다리는 SSE 스트림은 프록시 idle 타임아웃에 끊긴다 (파이프라인에서는
끊김 → 클라이언트 재시도 → **에이전트 중복 생성**이라는 실위험, Plan R7). 해법은 주기적
heartbeat인데, 코드베이스에 이미 검증된 선례(`run/stream`, 15초 주기)가 있어 그대로
복사하고 싶어진다.

**그 선례의 `asyncio.wait_for(stream.__anext__(), timeout)` 패턴은 전제 조건이 있다.**
agent-create-pipeline 사이클에서 맹목 복사했다면 파이프라인이 통째로 중단됐다.

## 검증된 사실

### 1. `wait_for`는 timeout 시 awaitable을 **취소**한다

`wait_for(gen.__anext__(), timeout)`이 타임아웃되면 `__anext__` task가 취소되고,
`CancelledError`가 **제너레이터 내부의 현재 await 지점으로 주입**된다.

- **큐 기반 스트림** (run/stream): 이벤트를 별도 태스크가 큐에 push하고 제너레이터는
  `queue.get()`을 기다릴 뿐이다. `queue.get()`이 취소돼도 생산자는 무사하므로 다음
  루프에서 다시 기다리면 된다 → **안전**.
- **직접 await 제너레이터** (파이프라인): 제너레이터 자신이 LLM 호출을 await 중이다.
  취소가 LLM await 지점에 꽂히면 그 단계 실행 자체가 죽고 제너레이터가 종료된다 →
  **heartbeat를 쏠 때마다 파이프라인이 죽는 구조**.

### 2. 안전한 형태 — task를 유지한 채 `asyncio.wait(timeout)`

`agent_pipeline_router.py::_sse_stream`의 구조:

```python
task = asyncio.ensure_future(anext(generator))
while True:
    done, _ = await asyncio.wait({task}, timeout=HEARTBEAT_SEC)
    if not done:
        yield b": heartbeat\n\n"   # task 는 취소되지 않고 계속 실행 중
        continue
    item = task.result()            # StopAsyncIteration/예외 처리 후
    ...
    task = asyncio.ensure_future(anext(generator))  # 다음 항목
```

`asyncio.wait`는 타임아웃돼도 **task를 취소하지 않는다** — heartbeat만 흘리고 같은
task를 계속 기다리므로 LLM 단계가 방해 없이 진행된다. 스트림 종료 시 `finally`에서
미완료 task를 명시적으로 `cancel()` 한다 (클라이언트 이탈 정리).

### 3. heartbeat 테스트는 "이벤트 무손실"을 함께 단언한다

`test_sse_emits_heartbeat_while_stage_is_slow`는 heartbeat 라인 존재만이 아니라
**느린 단계의 이벤트가 하나도 유실되지 않았음**을 같이 단언한다. heartbeat 구현이
스트림을 중단시키는 회귀(위 1번 함정)를 잡는 것이 이 테스트의 진짜 목적이다.

## 다음에 적용하는 법

1. SSE/스트림에 heartbeat·타임아웃을 붙이기 전에 먼저 묻는다 — **이 제너레이터는
   큐 소비자인가, 작업을 직접 await 하는가?** 후자면 `wait_for` 금지.
2. 직접 await 형이면 `ensure_future(anext(gen))` + `asyncio.wait({task}, timeout)` +
   미완료 시 heartbeat + `finally` cancel 구조를 쓴다 (형태는 `_sse_stream` 참조).
3. heartbeat 테스트에는 반드시 "본 이벤트 무손실" 단언을 세트로 넣는다.
4. 일반화: **검증된 사내 패턴도 전제(여기서는 "생산자가 별도 태스크")가 있다.**
   복사 전에 원본이 왜 안전한지 한 줄로 설명할 수 없으면 복사하지 않는다.

## 관련 문서

- 같은 라우터의 동기/SSE 이중 노출 구조: [[sync-sse-dual-exposure]]
