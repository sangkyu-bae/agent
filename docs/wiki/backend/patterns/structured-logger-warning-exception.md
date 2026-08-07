---
title: logger.warning에도 exception kwarg로 스택 트레이스 기록 가능 — 인터페이스가 아니라 구현이 진실
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/infrastructure/logging/structured_logger.py (_log 107-134행 — exception 명시 파라미터 → exc_info)
  - idt/src/domain/logging/interfaces/logger_interface.py (warning은 **kwargs만 선언)
  - idt/src/application/agent_composer/compose_agent_use_case.py (_try_plan 폴백 경고 — 실사용 예)
  - docs/archive/2026-08/fix-agent-planner-hitl/fix-agent-planner-hitl.report.md (Lessons 4, Gap G2)
confidence: 0.9
version: 1
created: 2026-08-06
updated: 2026-08-07
verified_at: 18fd521e
---

# logger.warning의 exception kwarg — 인터페이스만 보고 판단하지 말 것

## 문제

`LoggerInterface` 시그니처상 `error`/`critical`만 `exception` 파라미터를 명시하고
`warning`/`info`는 `**kwargs`뿐이다. 그래서 "warning에는 스택 트레이스를 못 남긴다"고
오판해 `error=str(e)` 같은 문자열 컨텍스트로 때우기 쉽다 — 스택 트레이스가 유실된다
(fix-agent-planner-hitl Gap G2에서 실제 발생·수정).

## 검증된 사실

- `StructuredLogger.warning(message, **kwargs)`는 kwargs를 `_log`로 넘기는데,
  **`_log`가 `exception: Exception | None`을 명시 파라미터로 수취**해
  `exc_info=(type, exc, traceback)`로 스택 트레이스를 기록한다 (107-134행).
- 따라서 `logger.warning("...", exception=e, request_id=...)`가 **정상 동작**하며
  error와 동일한 품질의 트레이스가 남는다. 실사용 예:
  `compose_agent_use_case.py`의 Planner 폴백 경고.
- 나머지 kwargs는 LogRecord 예약 키와 충돌 시 `ctx_` 접두어로 치환되어 extra에 실린다.

## 다음에 적용하는 법

- 예외를 삼키고 폴백하는 경로의 warning에는 `exception=e`를 넘긴다.
  `error=str(e)` 문자열 요약은 스택 트레이스가 없어 진단 불가 — 사용 금지.
- 일반화: **인터페이스(Protocol/ABC) 시그니처만 보고 기능 유무를 판단하지 말고
  구현체를 확인**한다. `**kwargs` 통로 뒤에 명시 파라미터가 기다리는 패턴이 있다.
  (단, 이 동작은 StructuredLogger 구현 계약이므로 `_log`의 exception 처리를 지우는
  리팩토링은 warning 호출부 전체를 깨뜨린다.)
