---
title: UTC naive 저장 시각은 오프셋을 붙여 응답한다 (KST 9시간 어긋남 방지)
status: approved
source_type: conversation
source_refs:
  - 커밋 012d6b1 (PR #136 — 스케줄 응답 시각 7개 + 작업함 스케줄 이력에 +00:00)
  - idt/src/application/agent_schedule/schemas.py (_iso)
  - idt/src/application/background_job/schemas.py (MyScheduleRunResponse._utc)
  - idt/src/interfaces/schemas/approval.py (_utc_iso + _UtcDatetimeModel field_serializer("*") — approval-gate Check G12 선례)
  - idt/src/application/agent_alert/schemas.py (_utc_iso — firewall-agent)
  - idt/tests/application/agent_schedule/test_schedule_response_utc.py
  - idt/db/migration/V071__create_approval_request.sql (DATETIME UTC naive 관례 주석)
confidence: 0.85
version: 1
created: 2026-11-27
updated: 2026-11-27
verified_at: bcf64b0
reviewer: 배상규
---

# UTC naive 저장 시각은 오프셋을 붙여 응답한다

## 문제

DB는 시각을 **UTC naive**(`DATETIME`, 시간대 정보 없음)로 저장한다. 이것을 pydantic 기본
직렬화로 내보내면 `2026-11-26T02:50:00`처럼 **오프셋 없는 문자열**이 나간다. 프론트의
`new Date("2026-11-26T02:50:00")`는 오프셋 없는 날짜+시각을 **브라우저 로컬(KST)** 로 해석하므로
화면이 9시간 이르게 보인다.

같은 결함이 두 번 났다.

- approval-gate Check G12: 승인 요청 시각 → `_UtcDatetimeModel`로 수정
- PR #136(2026-11-26): 스케줄 화면에서 11:50 회차가 02:50, 다음 실행 12:00이 03:00으로 표시 → 스케줄 응답 7개 필드와 작업함 스케줄 이력 수정

## 검증된 사실

1. **저장 관례는 UTC naive다.** `agent_schedule`·`agent_background_job`·`approval_request`·
   `agent_alert_*` 모두 같고, 쓰기 쪽은 `datetime.now(UTC).replace(tzinfo=None)`을 쓴다
   ([[erd-execution-triggers]]).
2. **고치는 곳은 백엔드 응답 직렬화 한 곳이다.** 화면 코드는 바꾸지 않았다 — `new Date()`가
   `+00:00`을 읽으면 로컬 표시는 자동으로 맞는다.
3. 규칙은 세 곳 모두 같다: `tzinfo is None`이면 `UTC`를 붙이고, 이미 오프셋이 있으면 그대로
   `isoformat()`. 결과 예 `2026-11-26T02:50:00+00:00`.
4. **공용 헬퍼가 없다.** 같은 함수가 `interfaces/schemas/approval.py`·`application/agent_schedule/schemas.py`·
   `application/agent_alert/schemas.py`·`application/background_job/schemas.py`에 따로 있다.
   승인 쪽만 `field_serializer("*", when_used="json")` 베이스 모델(`_UtcDatetimeModel`)이라
   새 datetime 필드가 자동으로 덮인다. 나머지는 필드 이름을 나열하므로 **필드를 추가할 때 빠뜨리기 쉽다.**
5. 다른 응답(에이전트 생성·수정 시각 등) 상당수는 아직 오프셋 없이 `isoformat()`을 쓴다.
   시:분을 보여 주는 화면이면 같은 결함 후보지만, 화면별로 확인하지는 않았다.

## 다음에 적용하는 법

1. **DB 시각을 응답에 내보내는 스키마를 만들 때** 오프셋을 붙인다. 필드가 여럿이면
   `_UtcDatetimeModel`처럼 `field_serializer("*", when_used="json")`으로 모델 전체에 거는 쪽이 안전하다.
2. 테스트는 "직렬화 결과 문자열이 `+00:00`으로 끝난다"를 필드마다 확인한다
   (`test_schedule_response_utc.py` 형식). 프론트에서 Date 객체로 비교하는 테스트는 테스트 실행 환경의
   시간대에 따라 이 결함을 놓친다.
3. 화면에서 시각이 정확히 9시간 어긋나면 프론트 포맷터보다 **API 응답 문자열에 오프셋이 있는지**부터 본다.
4. 공용 헬퍼로 모으는 정리는 아직 하지 않았다 — 하게 되면 이 문서를 갱신한다.

## 관련 문서

- [[erd-execution-triggers]] — UTC naive 저장 관례
- [[additive-contract-extension]] — 응답 형식 변경 시 소비자 영향 확인(오프셋 추가는 `new Date()` 소비자에게 호환)
