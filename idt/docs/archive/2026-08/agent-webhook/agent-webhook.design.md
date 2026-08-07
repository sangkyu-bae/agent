# Agent Webhook Design Document

> **Feature**: agent-webhook (Plan: `docs/01-plan/features/agent-webhook.plan.md`)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-08-07
> **Status**: Draft
> **Milestone**: M1=Inbound (본 문서 §2~§8), M2=Outbound (§9 — M1 완료 후 착수)

---

## 1. 설계 요약

에이전트별 opt-in 웹훅 채널. 신규 1:1 테이블 `agent_webhook`에 시크릿(해시)·활성 상태를 저장하고,
JWT 없는 공개 라우터가 **HMAC-SHA256 서명 + 타임스탬프 검증** 후 기존 `RunAgentUseCase`로
**소유자 신원 동기 실행**한다. M2에서 실행 완료 결과를 등록 URL로 서명 POST 발송한다.

### 코드 확인으로 확정된 사실 (2026-08-07)

| 사실 | 근거 |
|------|------|
| run 실행은 `use_case.execute(agent_id, RunAgentRequest, request_id, auth_ctx=, viewer_user_id=, viewer_department_ids=)` | agent_builder_router.py:270-293 |
| `auth_ctx`는 keyword-only optional — 스케줄은 auth_ctx 없이 `viewer_user_id=owner`로 실행하는 선례 존재 | run_agent_use_case.py:353, trigger_due_schedules_use_case.py:141-146 |
| `AuthContext`는 frozen VO, `AssembleAuthContextUseCase.execute(user, request_id)`로 조립 가능 (profile+부서+권한 3회 조회) | domain/agent_run/auth_context.py, application/permission/assemble_auth_context.py |
| 소유자 검증 선례: `agent.user_id != user_id → PermissionError` (라우터에서 403 변환) | application/agent_schedule/access.py:11-21 |
| 라우터 DI는 "플레이스홀더 함수 + main.py `dependency_overrides`" 패턴 | agent_builder_router.py:54-97, main.py:4166-4176 |
| 스케줄 트리거 `_run_one`이 실행 성공/실패 분기점 — M2 outbound 발송 훅 지점 | trigger_due_schedules_use_case.py:95-126 |
| 최신 마이그레이션 V056 → 이번 V057(M1)·V058(M2). FK CHARSET/COLLATE 금지, 전 컬럼 COMMENT | V056__create_middleware_catalog.sql 선례 |
| 설정 탭 Webhook 스텁: `SETTINGS_STUB` 배열 `id:'webhook'` 항목(disabled 토글) — info 문구가 "Bearer dbuilder_xxx"로 본 설계(HMAC)와 다름 → 교체 대상 | SettingsPanel.tsx:21-26 |
| 프론트 엔드포인트 상수는 `constants/api.ts`의 함수형 패턴 (`AGENT_SCHEDULES: (agentId) => ...`) | api.ts:219-225 |

---

## 2. 설계 결정 (Decisions)

| # | 결정 | 선택 | 근거 |
|---|------|------|------|
| D1 | 서명 명세 | `X-Webhook-Timestamp`(unix epoch 초) + `X-Webhook-Signature: sha256=<hex>` = HMAC-SHA256(secret, `"{timestamp}.{raw_body}"`), 허용창 **±300초**, 비교는 `hmac.compare_digest` | Stripe/GitHub 동형 표준. raw body 바이트 기준 서명(재직렬화 금지) |
| D2 | 시크릿 형식·저장 | `whsec_` + `secrets.token_urlsafe(32)` (총 ~49자). DB에 **평문 저장**(`secret` 컬럼) + 끝 4자 hint. 응답 노출은 발급/rotate 1회, 이후 hint만 | HMAC 검증은 서버가 시크릿 원문으로 서명을 **재계산**해야 하므로 단방향 해시 저장과 양립 불가. MCP 레지스트리 api_key 평문 보관(V032)과 동급 보안 수준 — 유출 시 rotate 대응. AES 암호화는 앱 키 관리 신설 비용 대비 과함(선례 없음) |
| D3 | 실행 신원 | **소유자 AuthContext 조립 주입** — owner User 로드 → `AssembleAuthContextUseCase` → `run_uc.execute(auth_ctx=owner_ctx, viewer_user_id=owner_id, viewer_department_ids=owner_depts)` | UI 실행과 **동작 동등성** 확보(RAG 권한 필터 등 auth_ctx 의존 경로가 소유자 기준으로 동작). auth_ctx=None인 스케줄 선례는 기존 동작이므로 **무변경** — 웹훅만 조립 |
| D4 | inbound body 계약 | `{query: str(1..2000), session_id?: str}` — **user_id는 받지 않음**(서버가 owner로 강제, 외부 신원 주장 차단). 응답은 `RunAgentResponse` 동형 | 외부 계약 최소화 + 신원 위조 원천 차단 |
| D5 | 검증 순서 | ① 헤더 2종 존재 → ② timestamp 파싱·허용창 → ③ `agent_webhook` 조회(미존재/disabled→404) → ④ HMAC 검증(→401) → ⑤ body 파싱(→422) → ⑥ 실행 | 저비용 검사 선행, LLM 실행 비용은 검증 통과 후에만. 404로 존재 비노출 |
| D6 | POST(발급) 멱등성 | 이미 채널 존재 시 **409** ("이미 활성화됨 — 재발급은 rotate") — 묵시적 rotate 금지 | 실수로 기존 키 무효화되는 사고 방지 |
| D7 | DELETE 의미 | 행 삭제(채널 해제) — 재활성화하려면 재발급(신규 키). 일시 중지는 PATCH `enabled:false` | 삭제=키 폐기 명확화, 이원화(삭제/토글)로 운영 유연성 |
| D8 | 에러 메시지 | 401은 사유 비구분("서명 검증 실패"), 404는 미설정/비활성/에이전트없음 동일 문구 | 오라클 공격 방지 (어떤 단계에서 실패했는지 비노출) |
| D9 | 프론트 노출 시점 | Webhook 섹션 실기능은 **edit 모드 전용** — create 모드에서는 "에이전트 저장 후 설정 가능" 안내 유지(스텁 잔존) | agent_id가 있어야 채널 생성 가능. 스킬/스케줄 탭과 동일 제약 패턴 |
| D10 | 상수 위치 | 허용창(300초)·시크릿 프리픽스·헤더명은 `domain/agent_webhook/policies.py` 클래스 상수. 프론트 안내 문구 상수는 `constants/agentSettings.ts` 병설 | config 하드코딩 금지 규칙 — 정책 값의 SoT는 domain |

---

## 3. DB 설계 — V057 (M1)

```sql
-- agent-webhook D1: 에이전트별 웹훅 채널 (1:1, opt-in).
-- FK 참조 테이블(agent_definition)은 SQLAlchemy 생성 — CHARSET/COLLATE 명시 금지,
-- ENGINE=InnoDB만 지정 (MySQL errno 3780 선례, V037/V056 주석 참조).
CREATE TABLE agent_webhook (
    id               VARCHAR(36)  NOT NULL COMMENT 'PK (UUID)',
    agent_id         VARCHAR(36)  NOT NULL COMMENT '에이전트 FK (agent_definition.id) — 에이전트당 1채널',
    enabled          TINYINT(1)   NOT NULL DEFAULT 1 COMMENT 'inbound 수신 활성 여부 — false면 호출 404',
    secret           VARCHAR(64)  NOT NULL COMMENT '시크릿 원문 — HMAC 서명 재계산용 (D2). 조회 응답·로그 노출 금지, hint만 노출',
    secret_hint      VARCHAR(8)   NOT NULL COMMENT '시크릿 끝 4자 — UI 식별용 표시',
    outbound_url     VARCHAR(500) NULL COMMENT 'outbound 발송 대상 URL (M2, http/https만) — NULL이면 미등록',
    outbound_enabled TINYINT(1)   NOT NULL DEFAULT 0 COMMENT 'outbound 발송 활성 여부 (M2)',
    created_by       VARCHAR(36)  NOT NULL COMMENT '채널 생성자 user_id (감사용)',
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '생성 시각',
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '수정 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_agent_webhook_agent (agent_id),
    CONSTRAINT fk_agent_webhook_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition (id) ON DELETE CASCADE
) ENGINE=InnoDB
  COMMENT='에이전트 웹훅 채널 — 외부 시스템 inbound 호출 인증(시크릿 해시)과 outbound 발송 설정 (소유자 opt-in)';
```

- SQLAlchemy 모델 `AgentWebhookModel` 동반 (`comment=` 전 컬럼 동일 반영 — `tests/db/test_migration_ddl_comments.py` V054+ 검사 대상).
- M2 컬럼(outbound_url·outbound_enabled)을 V057에 선포함 — M2에서 ALTER 불필요, M1 코드는 미사용.

---

## 4. 백엔드 설계 (M1)

### 4-1. 파일 구조 (신규/수정)

```
idt/
├── db/migration/V057__create_agent_webhook.sql          # 신규 (§3)
├── src/
│   ├── domain/agent_webhook/
│   │   ├── __init__.py
│   │   ├── entity.py            # AgentWebhook dataclass (모델↔엔티티)
│   │   ├── policies.py          # WebhookSecretPolicy · WebhookSignaturePolicy (stdlib만)
│   │   └── interfaces.py        # AgentWebhookRepositoryInterface
│   ├── application/agent_webhook/
│   │   ├── __init__.py
│   │   ├── schemas.py           # 요청/응답 pydantic (§4-4)
│   │   ├── access.py            # ensure_owned_agent (agent_schedule/access.py 동형)
│   │   ├── manage_webhook_use_cases.py   # Enable/Get/Rotate/Update/Disable (5개 UseCase, 파일 1본)
│   │   └── invoke_webhook_agent_use_case.py  # 검증 + 소유자 ctx 조립 + run 위임
│   ├── infrastructure/db/repositories/agent_webhook_repository.py  # 신규 (commit 금지 규칙)
│   └── api/routes/
│       ├── agent_webhook_router.py       # 관리 5본 (JWT) — prefix /api/v1/agents
│       └── webhook_public_router.py      # inbound 1본 (JWT 없음) — prefix /api/v1/webhooks
└── src/api/main.py               # 라우터 등록 + DI 배선 (create_agent_webhook_factories)
```

### 4-2. 도메인 정책 (`domain/agent_webhook/policies.py`)

```python
class WebhookSecretPolicy:
    PREFIX = "whsec_"
    HINT_LEN = 4

    @staticmethod
    def generate() -> str:            # PREFIX + secrets.token_urlsafe(32)
    @staticmethod
    def hash(secret: str) -> str:     # hashlib.sha256(...).hexdigest()
    @staticmethod
    def hint(secret: str) -> str:     # secret[-4:]

class WebhookSignaturePolicy:
    HEADER_TIMESTAMP = "X-Webhook-Timestamp"
    HEADER_SIGNATURE = "X-Webhook-Signature"
    TOLERANCE_SECONDS = 300
    SIGNATURE_PREFIX = "sha256="

    @staticmethod
    def sign(secret: str, timestamp: int, raw_body: bytes) -> str:
        # "sha256=" + HMAC_SHA256(secret, f"{timestamp}.".encode() + raw_body).hexdigest()
    @staticmethod
    def is_timestamp_valid(timestamp: int, now: int) -> bool:   # |now - ts| <= 300
    @staticmethod
    def verify(secret: str, timestamp: int, raw_body: bytes, signature: str) -> bool:
        # hmac.compare_digest(sign(...), signature) — 상수 시간
```

stdlib(hmac/hashlib/secrets)만 사용 — domain 금지 사항(외부 API·DB·LangChain) 저촉 없음.
Outbound(M2) 발송 서명도 `sign()`을 그대로 재사용한다.

### 4-3. UseCase 설계

**관리 5종** (`manage_webhook_use_cases.py`) — 공통: `access.ensure_owned_agent`로 소유자 검증
(`agent.user_id != viewer_user_id → PermissionError` → 라우터 403. 미존재 → ValueError → 404).

| UseCase | 동작 | 예외 |
|---------|------|------|
| `EnableWebhookUseCase` | 채널 미존재 시 생성: secret 생성→hash/hint 저장→**평문 포함 응답**(1회) | 기존재 → `ValueError("이미 활성화")` → 409 (D6) |
| `GetWebhookUseCase` | 설정 조회 (hint만, 평문 없음). 미설정 시 `configured:false` 응답 (404 아님 — 프론트 분기 단순화) | — |
| `RotateWebhookSecretUseCase` | 새 secret 생성→hash/hint 교체→평문 포함 응답. 구키 즉시 무효(해시 교체로 자동) | 미설정 → ValueError → 404 |
| `UpdateWebhookUseCase` | `enabled` 토글 (M1). M2에서 outbound_url(http/https 검증)·outbound_enabled 추가 | 미설정 → 404 |
| `DisableWebhookUseCase` | 행 삭제 (D7) | 미설정 → 404 |

**Invoke** (`invoke_webhook_agent_use_case.py`) — 공개 경로의 심장:

```
execute(agent_id, raw_body: bytes, timestamp_header: str|None, signature_header: str|None, request_id)
  1. 헤더 결측/timestamp 비정수        → WebhookAuthError     (라우터: 401)
  2. is_timestamp_valid 실패           → WebhookAuthError     (401)
  3. webhook_repo.find_by_agent_id — 미존재 or not enabled
                                       → WebhookNotFoundError (404, D8 단일 문구)
  4. WebhookSignaturePolicy.verify(webhook.secret, ts, raw_body, signature)
     실패                              → WebhookAuthError     (401)
  5. body 파싱(WebhookInvokeRequest)   → ValidationError      (422)
  6. owner = user_repo.find_by_id(agent.user_id) → assemble_auth_context_uc.execute(owner)
  7. run_uc.execute(agent_id, RunAgentRequest(query, user_id=owner_id, session_id), request_id,
     auth_ctx=owner_ctx, viewer_user_id=str(owner_id),
     viewer_department_ids=list(owner_ctx.department_ids))
  8. RunAgentResponse 반환
```

> 서명 검증(4단계)이 저장된 **시크릿 원문**을 사용하는 이유는 D2 참조 — HMAC은 서버 측 재계산이
> 필요해 단방향 해시 저장과 양립하지 않는다 (설계 중 Plan의 "해시 저장" 가정을 정정한 지점).

### 4-4. API 계약

**관리 (JWT, `agent_webhook_router.py`, prefix `/api/v1/agents`, tags=["Agent Webhook"])**

| Method/Path | 요청 | 응답 | 오류 |
|---|---|---|---|
| `POST /{agent_id}/webhook` | (body 없음) | `201 WebhookSecretResponse{secret(1회), secret_hint, enabled, inbound_path, created_at}` | 403 비소유자 / 404 에이전트 없음 / 409 기존재 |
| `GET /{agent_id}/webhook` | — | `200 WebhookConfigResponse{configured, enabled, secret_hint, inbound_path, outbound_url, outbound_enabled, created_at}` (미설정 시 `configured:false` 나머지 null) | 403 / 404 |
| `POST /{agent_id}/webhook/rotate` | — | `200 WebhookSecretResponse` (새 평문 1회) | 403 / 404 |
| `PATCH /{agent_id}/webhook` | `{enabled: bool}` (M2: `outbound_url?`, `outbound_enabled?`) | `200 WebhookConfigResponse` | 403 / 404 / 422 |
| `DELETE /{agent_id}/webhook` | — | `204` | 403 / 404 |

`inbound_path` = `/api/v1/webhooks/agents/{agent_id}` — 프론트가 `VITE_API_BASE_URL`과 조합해 전체 URL 표시.

**공개 inbound (`webhook_public_router.py`, prefix `/api/v1/webhooks`, 인증 의존성 없음)**

```
POST /agents/{agent_id}
Headers: X-Webhook-Timestamp: 1754500000
         X-Webhook-Signature: sha256=<hex>
Body:    {"query": "...", "session_id": "..."}   # session_id optional — 멀티턴 opt-in
→ 200: RunAgentResponse 동형 {agent_id, query, answer, tools_used, request_id, session_id, run_id}
→ 401 {"detail":"서명 검증 실패"} / 404 {"detail":"웹훅을 찾을 수 없습니다"} / 422
```

라우터는 `await request.body()`로 raw bytes를 받아 use case에 그대로 전달 (서명은 바이트 기준 — pydantic 파싱은 검증 통과 후 use case 내부에서).

**외부 호출자 서명 생성 예시 (문서·설정 탭 안내용)**:

```bash
TS=$(date +%s); BODY='{"query":"안녕"}'
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')
curl -X POST "$BASE/api/v1/webhooks/agents/$AGENT_ID" \
  -H "X-Webhook-Timestamp: $TS" -H "X-Webhook-Signature: sha256=$SIG" \
  -H "Content-Type: application/json" -d "$BODY"
```

### 4-5. DI 배선 (main.py)

- `create_agent_webhook_factories()` — 기존 팩토리 패턴 동형: per-request `Depends(get_session)`으로
  세션 주입, repo/use case 조립. Invoke는 `run_agent_uc_builder`(스케줄 DI `_build_run_agent_uc` 재사용)
  + `assemble_auth_context_uc` + `user_repo` 주입.
- 라우터 2본 `app.include_router` 등록. 공개 라우터는 인증 의존성 미포함 확인 테스트 동반(무JWT 200/401 실측 — wiki-tree-performance 교훈).

---

## 5. 프론트엔드 설계 (M1)

### 5-1. 파일 구조

```
idt_front/src/
├── constants/api.ts                 # AGENT_WEBHOOK / AGENT_WEBHOOK_ROTATE / WEBHOOK_INBOUND_PATH 추가
├── types/agentWebhook.ts            # 신규: WebhookConfig, WebhookSecretIssue, UpdateWebhookRequest
├── services/agentWebhookService.ts  # 신규: get/create/rotate/update/remove (기존 apiClient 사용)
├── hooks/useAgentWebhook.ts         # 신규: useQuery + 4 mutation (queryKey: ['agentWebhook', agentId])
└── components/agent-builder/settings/
    ├── SettingsPanel.tsx            # webhook 스텁 항목 분리 → WebhookSection 렌더 (mcp/telegram 스텁 유지)
    ├── WebhookSection.tsx           # 신규 (§5-2)
    └── WebhookSection.test.tsx      # 신규
```

### 5-2. WebhookSection 동작

| 상태 | UI |
|------|----|
| create 모드 (agentId 없음) | 기존 스텁과 동일한 비활성 카드 + "에이전트를 먼저 저장하면 설정할 수 있습니다" (D9) |
| edit + 미설정 (`configured:false`) | 설명문(HMAC 안내로 교체 — 기존 "Bearer dbuilder_xxx" 문구 폐기) + **[웹훅 활성화]** 버튼(LoadingButton, isPending 가드) |
| 활성화/재발급 직후 | **시크릿 모달**: 평문 1회 표시 + 복사 버튼 + "다시 볼 수 없습니다. 분실 시 재발급하세요" 경고. 닫으면 hint만 |
| edit + 설정됨 | 수신 URL(전체 URL 표시+복사) · 시크릿 `whsec_····{hint}` · enabled 토글(PATCH) · [키 재발급](confirm 후 rotate) · [웹훅 삭제](confirm 후 DELETE) · 경고문 "이 에이전트는 소유자(나)의 권한으로 실행됩니다" |

- 저장 모델: 웹훅 설정은 **탭 내 즉시 반영**(서버 상태 — TanStack Query mutation) — StudioHeader 폼 저장과 무관.
  maxIterations(폼 상태)와 관리 주체가 다름을 컴포넌트 주석으로 명시.
- SettingsPanel props에 `agentId?: string` 추가 (create 모드 undefined) — AgentTestPanel → StudioLayout 경유 전달.

### 5-3. 테스트 함정 선반영

- MSW per-file listen 3종 훅, vitest `--pool=threads`.
- 토글·버튼 pending 가드는 LoadingButton(isPending) 패턴 — disabled+userEvent 검증 함정 회피, 핸들러 지연 mock으로 단언.
- 클립보드: `navigator.clipboard.writeText` mock.

---

## 6. 테스트 설계 (TDD — 구현 전 작성)

### 백엔드

| 파일 | 케이스 |
|------|--------|
| `tests/domain/agent_webhook/test_policies.py` | 시크릿 형식(`whsec_` 프리픽스·길이)·hint, 서명 생성 재현성, 유효 서명 통과, 위조 서명 거부, 타임스탬프 ±300s 경계(±299 통과/±301 거부), sha256= 프리픽스 처리 |
| `tests/application/agent_webhook/test_manage_webhook.py` | enable: 평문 1회 응답+저장값 hint 일치 / 기존재 409(ValueError) / 비소유자 PermissionError / rotate: secret 교체·구서명 검증 실패 / update enabled 토글 / disable 행 삭제 |
| `tests/application/agent_webhook/test_invoke_webhook.py` | 헤더 결측 401류 / 만료 timestamp / 미설정·disabled → NotFound / 유효 요청 → run_uc.execute 위임 인자 검증(auth_ctx=owner, user_id=owner, session_id 전달) / body 파싱 실패 422류 |
| `tests/api/test_agent_webhook_router.py` | 5 엔드포인트 상태코드 매핑(403/404/409/422), JWT 필수 |
| `tests/api/test_webhook_public_router.py` | **무토큰 호출 가능**(인증 의존성 부재 실측), 401/404/422/200 매핑, raw body 그대로 서명 검증됨(공백·유니코드 body) |

### 프론트

| 파일 | 케이스 |
|------|--------|
| `WebhookSection.test.tsx` | create 모드 안내 / 미설정→활성화 버튼→모달 평문+복사 / 설정됨 렌더(hint·URL) / 토글 PATCH 호출 / rotate confirm→새 모달 / 삭제 confirm→미설정 상태 복귀 |
| `SettingsPanel.test.tsx` (수정) | webhook 스텁 단언 제거→WebhookSection 렌더 단언, mcp/telegram 스텁 유지 단언 |

---

## 7. 구현 순서 (M1)

1. **V057 마이그레이션 + AgentWebhookModel** (D2 반영: `secret` 평문 컬럼) — DDL comment 테스트 자동 검증
2. **domain**: entity·policies·interfaces + 정책 단위 테스트 (Red→Green)
3. **infrastructure**: repository (find_by_agent_id/insert/update/delete — commit 금지)
4. **application**: access + 관리 5종 + invoke + 테스트
5. **interfaces**: 라우터 2본 + main.py DI·등록 + API 테스트
6. **프론트**: types/constants/service/hook → WebhookSection(테스트 선행) → SettingsPanel 배선
7. **E2E 수동**: 설정 탭 활성화 → curl 서명 호출 → 응답/ai_run 관측 확인, rotate 후 구키 401

## 8. 영향 범위 / 주의사항

- **기존 코드 수정 최소**: agent_builder_router·run_agent_use_case·스케줄 무변경(M1). SettingsPanel만 스텁 교체.
- **공개 라우터 보안**: 인증 미들웨어 전역 적용이 아닌 per-route 의존 구조라 등록만으로 공개됨 — 반대로 실수로 `get_current_user`를 넣지 않도록 리뷰 포인트. rate limit 부재는 Plan §5 수용 리스크(후속).
- **시크릿 로깅 금지**: StructuredLogger 호출부에서 secret/signature 필드 자체를 로그 인자로 넘기지 않는다(마스킹이 아니라 미전달).
- **agent 삭제 시**: FK CASCADE로 채널 자동 소멸 — 별도 정리 코드 불필요.
- API 계약 동기화: 신규 엔드포인트 6본 → api.ts/types/service/hook 동반 (§5-1) — api-contract-sync 체크리스트 수행.

---

## 9. M2 — Outbound 설계 (M1 완료 후 착수, 개요 확정본)

### 9-1. DB — V058

```sql
CREATE TABLE agent_webhook_delivery (
    id          VARCHAR(36)   NOT NULL COMMENT 'PK (UUID)',
    agent_id    VARCHAR(36)   NOT NULL COMMENT '에이전트 FK (agent_definition.id)',
    run_id      VARCHAR(36)   NULL COMMENT '연계 ai_run id (실행 관측 조인용)',
    url         VARCHAR(500)  NOT NULL COMMENT '발송 대상 URL (발송 시점 스냅샷)',
    trigger_source VARCHAR(20) NOT NULL COMMENT '발송 계기 (schedule | webhook)',
    success     TINYINT(1)    NOT NULL COMMENT '최종 성공 여부 (재시도 소진 후)',
    status_code INT           NULL COMMENT '마지막 응답 HTTP 상태코드 (연결 실패 시 NULL)',
    attempts    INT           NOT NULL COMMENT '시도 횟수 (1~4)',
    error       VARCHAR(2000) NULL COMMENT '마지막 오류 메시지 (성공 시 NULL)',
    duration_ms INT           NOT NULL COMMENT '총 소요 시간(ms, 재시도 포함)',
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '기록 시각',
    PRIMARY KEY (id),
    KEY idx_awd_agent_created (agent_id, created_at),
    CONSTRAINT fk_awd_agent FOREIGN KEY (agent_id)
        REFERENCES agent_definition (id) ON DELETE CASCADE
) ENGINE=InnoDB
  COMMENT='웹훅 outbound 발송 이력 — 실패 진단·전송 상태 노출용';
```

### 9-2. 발송

- **payload**: `{"event":"agent.run.completed","agent_id","run_id","session_id","answer","tools_used","triggered_by":"schedule|webhook","timestamp"}` — 동일 시크릿으로 D1 스킴 서명 헤더 부착 (수신측 검증 가능).
- **sender**: `infrastructure/webhook/outbound_sender.py` — httpx.AsyncClient(timeout 10s), 재시도 3회 지수 백오프(1/2/4s), 결과를 delivery 레코드로 반환(저장은 use case).
- **훅 지점 2곳**: ① `TriggerDueSchedulesUseCase._run_one` 성공 직후 ② `InvokeWebhookAgentUseCase` 실행 완료 직후. 각각 try/except로 격리 — 발송 실패는 로그+이력 기록만, 실행 결과에 불영향(FR-13). 스케줄 use case에는 optional 의존성으로 주입(미주입 시 무동작 — 하위호환, agent-memory 무회귀 패턴).
- **URL 검증**: `UpdateWebhookUseCase`에서 http/https 스킴만 허용(도메인 정책 `WebhookOutboundPolicy.is_valid_url`). 사내망 IP 차단은 하지 않음(사내 수신이 정상 유스케이스) — Plan 리스크 문서화로 수용.
- **관리 API 확장**: PATCH body에 `outbound_url`(null=해제)·`outbound_enabled` 추가, `GET /{agent_id}/webhook/deliveries?limit=20` 신설.
- **프론트**: WebhookSection에 outbound URL 입력+토글, 최근 전송 이력 테이블(시각·상태코드·성공 배지).
