# Agent Webhook Outbound (M2) Design Document

> **Feature**: agent-webhook-outbound (Plan: `docs/01-plan/features/agent-webhook-outbound.plan.md`)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-07
> **Status**: Draft
> **선행**: M1 아카이브 `docs/archive/2026-08/agent-webhook/` — 본 문서는 M1 Design §9 개요의 상세 확정본

---

## 1. 설계 요약

에이전트 실행(스케줄 트리거·inbound 웹훅) 성공 완료 시, `outbound_enabled`면 등록 URL로
**M1과 동일 스킴으로 서명된** 결과 payload를 POST 발송한다. 발송은 **싱글턴 디스패처**
(`session_factory` 보유, 요청 세션 비의존)가 수행하며, 실패해도 실행 결과에 절대 전파되지 않는다.
모든 시도 결과는 V058 `agent_webhook_delivery`에 기록되고 설정 탭에서 조회된다.

### 코드 확인으로 확정된 사실 (2026-08-07)

| 사실 | 근거 |
|------|------|
| httpx **0.28.1 기존재** — 신규 의존성 0 | `.venv` import 실측 |
| V057에 `outbound_url`(NULL)·`outbound_enabled`(FALSE) 선포함 — ALTER 불필요 | V057__create_agent_webhook.sql:12-13 |
| `WebhookSignaturePolicy.sign(secret, ts, raw_body)` 재사용 가능 (스킴 공용) | domain/agent_webhook/policies.py |
| 요청 수명 밖 DB 작업의 선례: `DbScheduleRunSink(session_factory, logger)` — 싱글턴이 회차별 짧은 세션 생성 | infrastructure/agent_schedule/run_sink.py, main.py:2790 |
| 훅 ① 지점: `TriggerDueSchedulesUseCase._run_one` success 분기 (`response` 보유 — session_id·run_id) | trigger_due_schedules_use_case.py:100-108 |
| 훅 ② 지점: `InvokeWebhookAgentUseCase.execute` — `run_agent_uc.execute` 반환 직전 | invoke_webhook_agent_use_case.py:74-85 |
| invoke의 repo들은 **요청 스코프 세션** — 응답 후 실행되는 태스크에서 사용 금지 (디스패처가 자체 세션 필요) | main.py invoke_f (Depends(get_session)) |
| `RunAgentResponse{agent_id, query, answer, tools_used, request_id, session_id, run_id}` — payload 소스 | application/agent_builder/schemas.py:172-179 |
| M1 `UpdateWebhookRequest{enabled: bool}` 필수 필드 — M2 확장 시 하위호환 필요 (FR-17) | application/agent_webhook/schemas.py:43-44 |
| 프론트 이력 lazy 조회 선례: `useScheduleRuns(..., {enabled})` — 펼침 시에만 fetch | hooks/useAgentSchedules.ts:84-96 |

---

## 2. 설계 결정 (Decisions)

| # | 결정 | 선택 | 근거 |
|---|------|------|------|
| D11 | 디스패처 수명 | **앱 수명 싱글턴** `DispatchOutboundWebhookUseCase(session_factory, …)` — 요청 세션 비의존 | inbound 비차단 태스크가 응답 후 실행되므로 요청 스코프 세션 사용 불가. DbScheduleRunSink 선례 |
| D12 | 발송 방식 | **스케줄 = 인라인 await**, **inbound = `spawn(coro)` 비차단** (spawn 기본값 `asyncio.create_task`, 테스트에서 동기 실행자로 교체 주입) | 배치는 지연 무해·순서 보장, inbound는 호출자 응답에 재시도 지연(최대 ~17s) 미전가. spawn 주입으로 테스트 가능성 확보 |
| D13 | 재시도 정책 | 총 시도 최대 4회(최초 1 + 재시도 3), 백오프 1/2/4초, 요청 타임아웃 10초. **5xx·네트워크 오류만 재시도, 4xx는 즉시 중단**(수신측 명시 거부 — 재시도 무의미) | 표준 웹훅 관례. 상수는 `WebhookOutboundPolicy` (config 하드코딩 금지) |
| D14 | payload·서명 | body = `{event:"agent.run.completed", agent_id, run_id, session_id, query, answer, tools_used, triggered_by, timestamp}` JSON bytes. 헤더 = M1과 동일 `X-Webhook-Timestamp`/`X-Webhook-Signature`, 서명 대상은 **전송 바이트 그대로** | 수신측이 M1 inbound 검증 코드와 동일 로직으로 검증 가능 (FR-15) |
| D15 | 무발송 판정 | 디스패처가 자체 세션으로 `agent_webhook` 재조회 — 미설정·`outbound_enabled=False`·`outbound_url` NULL이면 **조용히 return** (이력 미기록) | 훅 호출측은 웹훅 상태를 몰라도 됨(항상 호출) — 판단 단일화. 비활성 무발송은 이력 노이즈 방지 |
| D16 | 오류 격리 | `dispatch()`는 **절대 raise하지 않는다** — 최외곽 try/except + `logger.error`(스택 포함). 훅 측도 방어적 try/except 이중화 | FR-13. 이력 기록 실패조차 실행에 미전파 |
| D17 | PATCH 확장 | `UpdateWebhookRequest`를 **전 필드 optional**로 확장(`enabled?`, `outbound_url?`, `outbound_enabled?`) + `model_fields_set`으로 "미지정 vs null(해제)" 구분. `outbound_enabled=True` 요청 시 URL 부재면 422 | additive — M1 프론트(`{enabled}` 단독 전송)는 무수정 통과 (FR-17). null=해제 의미론은 fields_set으로만 구현 가능 |
| D18 | URL 검증 | `WebhookOutboundPolicy.is_valid_url`: `http://`/`https://` 스킴 + `urllib.parse` 호스트 존재 확인만. 내부 IP 차단 없음 | Plan Out of Scope 유지 (사내망 수신이 정상 유스케이스) |
| D19 | 에러 계약 | M2 신규 라우터 분기는 **전용 예외** `WebhookValidationError`(→422) 사용. M1 코드의 `"이미"` 문자열 매칭은 **소급하지 않음** | G5 교훈 반영 + 소급 churn 회피 (M1 무수정 원칙) |
| D20 | delivery repo | `AgentWebhookDeliveryRepository` **별도 클래스·동일 파일군**(`infrastructure/agent_webhook/`) — insert + list_by_agent(desc, limit)만 | 책임 분리하되 파일 산개 방지. update/delete 없음 (이력 불변) |
| D21 | 이력 조회 UX | 프론트 이력은 **접힘 기본, 펼침 시에만 fetch** (`useWebhookDeliveries(agentId, {enabled})`) | useScheduleRuns 선례. 설정 탭 진입마다 이력 조회 방지 |

---

## 3. DB 설계 — V058

```sql
-- agent-webhook-outbound D20: outbound 발송 이력 (불변 — INSERT only).
-- COMMENT 문자열에 최상위 콤마 금지 (test_migration_ddl_comments 파서 제약 — M1 함정).
-- FK 참조 테이블은 SQLAlchemy 생성 — CHARSET/COLLATE 명시 금지, ENGINE=InnoDB만 (V037/V056/V057 선례).
CREATE TABLE agent_webhook_delivery (
    id             VARCHAR(36)   NOT NULL COMMENT 'PK (UUID)',
    agent_id       VARCHAR(36)   NOT NULL COMMENT '에이전트 FK (agent_definition.id)',
    run_id         VARCHAR(36)   NULL COMMENT '연계 ai_run id — 실행 관측 조인용 (실행측 미발급 시 NULL)',
    url            VARCHAR(500)  NOT NULL COMMENT '발송 대상 URL (발송 시점 스냅샷 — 이후 변경과 무관)',
    trigger_source VARCHAR(20)   NOT NULL COMMENT '발송 계기 (schedule | webhook)',
    success        TINYINT(1)    NOT NULL COMMENT '최종 성공 여부 (재시도 소진 후 판정)',
    status_code    INT           NULL COMMENT '마지막 응답 HTTP 상태코드 (연결 실패 시 NULL)',
    attempts       INT           NOT NULL COMMENT '총 시도 횟수 (1~4)',
    error          VARCHAR(2000) NULL COMMENT '마지막 오류 메시지 (성공 시 NULL)',
    duration_ms    INT           NOT NULL COMMENT '총 소요 시간 ms (재시도·백오프 포함)',
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '기록 시각',
    PRIMARY KEY (id),
    KEY idx_awd_agent_created (agent_id, created_at),
    CONSTRAINT fk_awd_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition (id) ON DELETE CASCADE
) ENGINE=InnoDB
  COMMENT='웹훅 outbound 발송 이력 — 실패 진단·전송 상태 노출용 (불변 레코드)';
```

- `AgentWebhookDeliveryModel` 동반 (`comment=` 전 컬럼 미러). 엔티티 `WebhookDelivery`는 `domain/agent_webhook/entity.py`에 추가.
- FK는 `agent_webhook`이 아닌 **`agent_definition`** 참조 — 웹훅 채널 삭제/재발급 후에도 이력 보존 (에이전트 삭제 시에만 CASCADE).

---

## 4. 백엔드 설계

### 4-1. 파일 구조 (신규/수정)

```
idt/
├── db/migration/V058__create_agent_webhook_delivery.sql   # 신규 (§3)
├── src/
│   ├── domain/agent_webhook/
│   │   ├── entity.py                    # 수정: WebhookDelivery 추가
│   │   ├── policies.py                  # 수정: WebhookOutboundPolicy 추가 (§4-2)
│   │   └── interfaces.py               # 수정: AgentWebhookDeliveryRepositoryInterface + OutboundSenderInterface
│   ├── infrastructure/
│   │   ├── agent_webhook/
│   │   │   ├── models.py               # 수정: AgentWebhookDeliveryModel
│   │   │   └── delivery_repository.py  # 신규 (D20 — insert·list_by_agent)
│   │   └── webhook/
│   │       ├── __init__.py
│   │       └── outbound_sender.py      # 신규: HttpxOutboundSender (§4-3)
│   ├── application/agent_webhook/
│   │   ├── schemas.py                  # 수정: UpdateWebhookRequest 확장 + WebhookDeliveryResponse + OutboundResult
│   │   ├── manage_webhook_use_cases.py # 수정: Update 확장(D17) / 신규 ListWebhookDeliveriesUseCase
│   │   ├── dispatch_outbound_use_case.py  # 신규 (§4-4 — 심장)
│   │   ├── invoke_webhook_agent_use_case.py  # 수정: 훅 ② (optional dispatcher + spawn)
│   │   └── errors.py                   # 신규: WebhookValidationError (D19)
│   ├── application/agent_schedule/
│   │   └── trigger_due_schedules_use_case.py  # 수정: 훅 ① (optional dispatcher, 인라인)
│   └── api/
│       ├── routes/agent_webhook_router.py  # 수정: GET deliveries + 422 매핑(D19)
│       └── main.py                         # 수정: 디스패처 싱글턴 + DI 확장
└── tests/ (§6)
```

### 4-2. 도메인 — `WebhookOutboundPolicy` (policies.py 추가)

```python
class WebhookOutboundPolicy:
    ALLOWED_SCHEMES = ("http", "https")
    MAX_RETRIES = 3          # 최초 1회 + 재시도 3회 = 총 4회
    BACKOFF_SECONDS = (1.0, 2.0, 4.0)
    REQUEST_TIMEOUT_SECONDS = 10.0
    ERROR_MESSAGE_MAX = 2000
    EVENT_RUN_COMPLETED = "agent.run.completed"

    @staticmethod
    def is_valid_url(url: str) -> bool:
        # urllib.parse.urlparse — scheme in ALLOWED_SCHEMES and netloc 존재
    @staticmethod
    def should_retry(status_code: int | None) -> bool:
        # None(연결 실패) 또는 5xx → True / 2xx·3xx·4xx → False (D13)
```

### 4-3. 발송기 — `HttpxOutboundSender` (infrastructure/webhook/)

```python
class OutboundSenderInterface(ABC):            # domain/agent_webhook/interfaces.py
    async def send(self, url, body: bytes, headers: dict, request_id) -> OutboundResult: ...

@dataclass
class OutboundResult:                          # application/agent_webhook/schemas.py (내부 DTO)
    success: bool
    status_code: int | None
    attempts: int
    error: str | None
    duration_ms: int
```

- `httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS)` — 시도마다 컨텍스트 생성(장수 커넥션 풀 상태 회피, 발송 빈도상 오버헤드 무시 가능).
- 루프: 시도 → 2xx면 성공 종료 → `should_retry`면 `asyncio.sleep(BACKOFF[i])` 후 재시도 → 소진/4xx면 실패 종료.
- 성공 판정: **2xx만 성공**. 오류 메시지는 `ERROR_MESSAGE_MAX` 절단. **body·시크릿·서명 값은 로그 인자 미전달**(url·status_code·attempts만).

### 4-4. 디스패처 — `DispatchOutboundWebhookUseCase` (싱글턴, D11)

```python
class DispatchOutboundWebhookUseCase:
    def __init__(self, session_factory, webhook_repo_builder, delivery_repo_builder,
                 sender: OutboundSenderInterface, logger): ...

    async def dispatch(self, agent_id: str, run: RunAgentResponse,
                       triggered_by: str, request_id: str) -> None:
        try:
            # [tx1] 자체 세션: webhook 조회 — 미설정/outbound off/url None → return (D15)
            # payload 조립(D14) → json.dumps(...).encode() → ts=int(time.time())
            #   → WebhookSignaturePolicy.sign(webhook.secret, ts, body)
            # result = await self._sender.send(url, body, headers, request_id)   # 세션 미보유 구간
            # [tx2] 자체 세션: delivery insert (url 스냅샷·trigger_source·result 필드)
            # logger.info("outbound dispatched", agent_id=, success=, attempts=, status_code=)
        except Exception as e:
            self._logger.error("outbound dispatch failed", exception=e, ...)  # 절대 재raise 금지 (D16)
```

**훅 배선 (optional 의존성 — 미주입 무동작, FR-16)**:

| 훅 | 위치 | 방식 |
|----|------|------|
| ① 스케줄 | `TriggerDueSchedulesUseCase.__init__(..., outbound_dispatcher=None)` — `_run_one`의 success 분기(`on_finished` 이후)에서 `if self._outbound_dispatcher: await dispatch(schedule.agent_id, response, "schedule", request_id)` | 인라인 await (D12) — try/except 이중 격리, 실패해도 이력 success 유지 |
| ② invoke | `InvokeWebhookAgentUseCase.__init__(..., outbound_dispatcher=None, spawn=None)` — `run_agent_uc.execute` 결과 확보 후 `if dispatcher: (spawn or asyncio.create_task)(dispatcher.dispatch(agent_id, result, "webhook", request_id))` → 응답 즉시 반환 | 비차단 (D12). dispatch가 절대 raise하지 않으므로 태스크 예외 누수 없음 |

### 4-5. 관리 API 확장

**PATCH `/{agent_id}/webhook`** (D17):

```python
class UpdateWebhookRequest(BaseModel):     # 전 필드 optional (additive)
    enabled: bool | None = None
    outbound_url: str | None = None        # null 명시 = 해제 (fields_set으로 구분)
    outbound_enabled: bool | None = None
```

`UpdateWebhookUseCase` 처리 규칙 (`body.model_fields_set` 기준):
- `enabled` 지정 시 반영 (M1 동작 유지).
- `outbound_url` 지정: 문자열이면 `is_valid_url` 검증(실패 → `WebhookValidationError` → 422),
  null이면 해제 + **`outbound_enabled`도 강제 False**.
- `outbound_enabled=True` 지정: 반영 후 URL이 없으면 `WebhookValidationError("outbound URL을 먼저 등록하세요")`.
- 라우터: `except WebhookValidationError → 422` 분기 추가 (기존 ValueError 매핑 유지 — M1 무수정, D19).

**GET `/{agent_id}/webhook/deliveries?limit=20`** (신규, JWT·소유자 전용):
- `ListWebhookDeliveriesUseCase.execute(agent_id, viewer_user_id, limit, request_id)` —
  `ensure_owned_agent` → `delivery_repo.list_by_agent(agent_id, limit)` (created_at desc).
- `limit`: Query(20, ge=1, le=100).
- 응답: `list[WebhookDeliveryResponse{id, trigger_source, success, status_code, attempts, error, duration_ms, created_at}]` (url은 응답 제외 — 소유자 화면에 이미 표시 중, 노출 최소화).

### 4-6. DI (main.py)

- `create_agent_webhook_factories`에 추가: delivery repo builder + **디스패처 싱글턴**
  (`session_factory=get_session_factory()`, `sender=HttpxOutboundSender(logger)`) 생성 후
  ① `create_agent_schedule_factories(build_run_agent_uc, outbound_dispatcher=dispatcher)`로 전달(트리거 싱글턴 주입),
  ② invoke 팩토리에 주입, ③ deliveries 조회 팩토리 추가·오버라이드.
- 기존 스케줄 팩토리 시그니처 변경은 **기본값 None**으로 하위호환 (`outbound_dispatcher=None`).

---

## 5. 프론트엔드 설계

### 5-1. 타입·서비스·훅 (additive)

```ts
// types/agentWebhook.ts 추가
export interface UpdateWebhookRequest {          // 전 필드 optional로 변경 (백엔드 D17 미러)
  enabled?: boolean;
  outbound_url?: string | null;                  // null = 해제
  outbound_enabled?: boolean;
}
export interface WebhookDelivery {
  id: string; trigger_source: 'schedule' | 'webhook'; success: boolean;
  status_code: number | null; attempts: number; error: string | null;
  duration_ms: number; created_at: string;
}
```

- `agentWebhookService.listDeliveries(agentId, limit=20)` → `GET AGENT_WEBHOOK_DELIVERIES(agentId)`.
- `constants/api.ts`: `AGENT_WEBHOOK_DELIVERIES: (id) => …/webhook/deliveries` 추가.
- `queryKeys.agentWebhook.deliveries(agentId)` 추가.
- `useUpdateWebhook` 시그니처 확장: `{agentId, data: UpdateWebhookRequest}` (M1 호출부 `{agentId, enabled}` → `{agentId, data:{enabled}}`로 정리 — WebhookSection 내부 한정 수정).
- `useWebhookDeliveries(agentId, {enabled})` — 펼침 시에만 fetch (D21).

### 5-2. WebhookSection — Outbound 하위 섹션 (설정됨 상태에서만 노출)

```
[설정됨 카드 내 기존 항목 아래]
─ 결과 발송 (Outbound) ─────────────────
  ⓘ 실행 결과를 아래 URL로 자동 발송합니다 (스케줄·웹훅 실행 시).
  [URL 입력 input          ] [저장(LoadingButton)]   ← 저장 시 update({outbound_url})
    · 형식 오류 422 → 인라인 에러 (extractWebhookError)
    · URL 등록됨 + [해제] 텍스트 버튼 → update({outbound_url: null})
  결과 발송 활성화        [토글 switch]              ← update({outbound_enabled: !v})
    · URL 미등록 상태에서 토글 → 서버 422 메시지 인라인 표출
  ▸ 최근 전송 이력 (disclosure, 접힘 기본 — D21)
    ┌ 시각 · 계기(스케줄/웹훅) · 상태코드 · 시도 횟수 · [성공|실패] 배지
    ├ 실패 행 확장 시 error 메시지
    └ 0건: "아직 발송 이력이 없습니다"
```

- outbound UI는 `config.configured === true`일 때만 렌더 (미설정/create 모드에는 없음).
- URL 입력은 로컬 draft state + 저장 버튼 확정 (매 키입력 PATCH 방지) — Recursion Limit draft 패턴 동형.

---

## 6. 테스트 설계 (TDD — 구현 전 작성)

### 백엔드

| 파일 | 케이스 |
|------|--------|
| `tests/domain/agent_webhook/test_outbound_policy.py` | is_valid_url(http/https 통과·ftp/스킴없음/호스트없음 거부), should_retry(None·500 → True / 200·404 → False), 상수 값 |
| `tests/infrastructure/agent_webhook/test_outbound_sender.py` | 2xx 1회 성공 / 500→500→200 (attempts=3·success) / 4회 소진 실패 / 4xx 즉시 중단(attempts=1) / 연결오류 status_code None / duration_ms 기록 — httpx MockTransport |
| `tests/application/agent_webhook/test_dispatch_outbound.py` | outbound off·url None → sender 미호출·이력 미기록 (D15) / 성공 → 서명 헤더가 M1 verify로 검증됨 (FR-15) / payload 필드 스키마 / sender 예외 → **raise 없음** + 이력 실패 기록 / 이력 insert 예외 → raise 없음 (D16) |
| `tests/application/agent_webhook/test_manage_webhook.py` (추가) | PATCH 확장: enabled 단독(M1 동작 유지) / outbound_url 등록·검증 실패 WebhookValidationError / null 해제 시 outbound_enabled 강제 off / URL 없이 enabled=True → 에러 (D17) |
| `tests/application/agent_webhook/test_invoke_webhook.py` (추가) | dispatcher 주입 시 spawn 호출(인자: agent_id·"webhook") / 미주입 시 무동작 / spawn 동기 실행자 주입 검증 |
| `tests/application/agent_schedule/…` (추가) | 훅 ①: dispatcher 주입 시 success 후 dispatch 호출("schedule") / dispatch 예외에도 이력 success 유지 (FR-13) / 미주입 무동작 |
| `tests/api/test_agent_webhook_router.py` (추가) | PATCH 422(WebhookValidationError) / GET deliveries 200·limit 검증·403 |

### 프론트

| 파일 | 케이스 |
|------|--------|
| `WebhookSection.test.tsx` (추가) | outbound UI는 설정됨 상태에서만 / URL 저장 → update({outbound_url}) / 해제 → null / 토글 → outbound_enabled / 422 인라인 에러 / 이력 펼침 시에만 fetch + 행 렌더(성공·실패 배지) / 0건 문구 |

## 7. 구현 순서

1. V058 + 모델 + `WebhookDelivery` 엔티티 (DDL comment 콤마 함정 주의)
2. domain: `WebhookOutboundPolicy` + 인터페이스 2종 + 테스트
3. infrastructure: `delivery_repository` + `HttpxOutboundSender`(MockTransport 테스트 선행)
4. application: `errors.py` → `dispatch_outbound_use_case` → PATCH 확장·ListDeliveries → 훅 2곳 (optional)
5. interfaces: 라우터 확장 + main.py DI (스케줄 팩토리 시그니처 기본값 None)
6. 프론트: types/constants/service/hook → WebhookSection outbound 하위 섹션 (테스트 선행)
7. 수동 E2E: 로컬 수신 서버로 발송 왕복 + 서명 재현 + 다운 시 재시도 이력 (M1 G7과 묶어 수행)

## 8. 영향 범위 / 주의사항

- **M1 코드 수정 최소**: invoke·manage·라우터는 additive 확장만, M1 테스트는 무수정 통과가 목표 (FR-17).
  프론트 `useUpdateWebhook` 시그니처 변경만 예외 — 호출부가 WebhookSection 1곳이라 반경 한정.
- **스케줄 팩토리 시그니처**: `create_agent_schedule_factories(build_run_agent_uc, outbound_dispatcher=None)` —
  기본값으로 기존 호출·테스트 하위호환.
- **비차단 태스크**: dispatch는 절대 raise하지 않으므로 create_task 예외 누수 없음. 단 테스트에서는
  spawn 주입으로 동기 실행해 단언한다 (이벤트 루프 잔여 태스크 경고 방지).
- **세션 규칙**: 디스패처는 HTTP 발송 구간에서 세션을 보유하지 않는다 (tx1 조회 → 닫음 → 발송 → tx2 기록).
- **이력 불변**: delivery는 INSERT only — update/delete 경로 자체를 만들지 않는다.
- api-contract-sync: PATCH body 확장 + deliveries 신설 → 프론트 types/service/hook 동반 (§5-1).
