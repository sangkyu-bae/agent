# mcp-identity-header Design Document

> **Summary**: 신원 헤더가 설정된 MCP 서버로 나가는 모든 tool 호출에, 실행 주체의 `users` 레코드로 만든 HS256 토큰을 **세션을 열기 직전** 발급해 싣는다
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규 / Claude
> **Date**: 2026-09-26
> **Status**: Draft
> **Planning Doc**: [mcp-identity-header.plan.md](./mcp-identity-header.plan.md)
> **Selected Architecture**: Option C — Pragmatic Balance

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 공용 MCP 서버 하나가 여러 사용자의 개인 자원을 다루려면 "누구의 자원인가"를 LLM이 아닌 플랫폼이 호출마다 보증해야 한다 |
| **WHO** | P2(에이전트 소유자): 메일 에이전트 구성 / 관리자: 회원 메일함·서버 신원 설정 / 최종 사용자: 본인 메일 조회·발송 |
| **RISK** | MCP 호출 경로 누락(한 곳이라도 헤더 없이 나가면 서버 거부 또는 설정 오류로 타인 메일함) · 5분 토큰이 로드 시점에 고정되어 긴 실행에서 만료 |
| **SUCCESS** | 서로 다른 두 사용자가 같은 에이전트로 `list_messages` 호출 시 각자 메일함 결과 / 메일함 미등록 사용자는 호출 전 idt가 명확한 오류로 거부 / 신원 미설정 서버는 기존과 바이트 동일 동작 |
| **SCOPE** | M1 도메인·스키마 → M2 토큰 발급·호출 시점 주입 → M3 관리자 API → M4 관리자 화면 |

---

## 1. Overview

### 1.1 Design Goals

1. **단일 주입 지점**: 헤더 병합은 `MCPClientFactory.create_session` 한 곳. 워커 어댑터·승인 집행기가 같은 지점을 지난다.
2. **호출 시점 발급**: 토큰은 `call_tool` 세션을 열기 직전에 만든다. 로드 시점·클라이언트 생성 시점에 만들지 않는다.
3. **명시적 주체 전달**: 실행 주체는 `subject_user_id` 인자로 흐른다. 앱 싱글톤의 가변 필드(`ToolFactory._auth_ctx` 방식)는 쓰지 않는다.
4. **미설정 서버 무영향**: `identity_config`가 없는 서버는 헤더 공급자 자체가 만들어지지 않는다 (FR-08).
5. **실패는 네트워크 전**: 주체·메일함이 없으면 MCP 서버에 연결하기 전에 끝낸다 (FR-07).

### 1.2 Design Principles

- **일반화**: 코드에 "Outlook"·"메일"이 등장하지 않는다. 클레임 소스는 사용자 속성 이름(`mailbox_upn`/`email`)으로 추상화.
- **신뢰 경계**: 클레임 값의 출처는 `users` 행뿐. LLM 인자·정적 헤더·요청 본문은 덮지 못한다 (발급 헤더가 병합 순서상 최후).
- **시크릿 수명주기 분리**: 서명 비밀은 `auth_config`와 다른 컬럼. `auth_config` 전체 교체(PUT)가 서명 비밀을 지우지 않는다.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | A: Minimal | B: Clean | **C: Pragmatic** |
|----------|:-:|:-:|:-:|
| 신원 설정 저장 | `auth_config.identity` | 전용 컬럼 + 전용 API | **전용 컬럼, 기존 등록 API 확장** |
| 발급 시점 | 도구 로드 시 | 호출 직전 | **호출 직전** |
| 주체 전달 | 인자 | ContextVar RunContext | **인자** |
| 신규 파일 | 2 | 8+ | **4** |
| R-2 토큰 만료 | ❌ 미해결 | ✅ | ✅ |
| PUT 시 비밀 유실 | ❌ 위험 | ✅ | ✅ |
| 누락 추적성 | 중 | 낮음 (ContextVar 경계 누락이 조용함) | **높음 (인자 누락은 테스트·타입에서 드러남)** |
| **Recommendation** | 빠른 PoC | 신원 소비 서버 다수 시 | **Default choice** |

**Selected**: Option C — 사용자 결정 (2026-09-26 Checkpoint 3).

### 2.1 Component Diagram

```
┌──────────── 실행 진입 ────────────┐
│ RunAgentUseCase (대화/스케줄/백그라운드/웹훅)   request.user_id
│ ApproveDecide / ExecuteScheduler               approval.requested_by
└──────┬──────────────────────────────┬──────────┘
       │ subject_user_id              │ subject_user_id
       ▼                              ▼
WorkflowCompiler.compile        CompositeActionExecutor.execute
  (재귀 sub-agent 포함)              ▼
       ▼                        McpActionExecutor
ToolFactory.create_all_async          │ client_factory(registration, subject)
       ▼                              ▼
MCPToolLoader.load(reg, subject) ─► IdentityHeaderProviderFactory.for_(reg, subject)
       │                                 │  None  ← identity_config 없음
       ▼                                 ▼
MCPToolRegistry → MCPToolAdapter   MCPCallClient(call_headers=provider)
       │ header_provider                  │
       └───────────────┬──────────────────┘
                       ▼  call_tool 세션에서만
          MCPClientFactory.create_session(..., header_provider=p)
             headers = static ⊕ auth ⊕ await p()   ← 발급 헤더 최후 병합
                       │
      p(): users 조회(session-scoped) → IdentityClaimPolicy → HS256 서명
```

### 2.2 Data Flow

```
tool 호출 → provider() → [주체 없음 | 사용자 없음/비활성 | 클레임 소스 비어 있음]
              │                     → IdentityUnavailableError (네트워크 전)
              │                        · 워커: 안내 문자열을 ToolMessage 로 반환
              │                        · 집행기: status="blocked"
              ▼
          claims = {iss, aud, sub, iat, exp=iat+ttl, <claim_name>: <값>}
              ▼
          sign HS256 → {<header_name>: token}
              ▼
          SSE/Streamable HTTP 세션 헤더 → MCP 서버 검증 → 해당 메일함만 조회
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `IdentityHeaderConfig` (domain VO) | 없음 | 설정 값·검증 |
| `IdentityClaimPolicy` (domain) | `User`, VO | 클레임 조립·가용성 판정 (순수) |
| `HmacIdentityTokenSigner` (infra) | `python-jose` | HS256 서명 |
| `IdentityHeaderProviderFactory` (infra) | session-scoped user repo, signer, policy | 서버·주체별 provider 생성 |
| `MCPClientFactory` | provider (callable) | 세션 헤더 병합 |

---

## 3. Data Model

### 3.1 Entity Definition

```python
# domain/auth/entities.py — 필드 추가
@dataclass
class User:
    ...
    mailbox_upn: Optional[str] = None   # 관리자 지정 메일함 UPN. 로그인 email 과 독립

# domain/mcp_registry/identity.py — 신규
class ClaimSource(str, Enum):
    MAILBOX_UPN = "mailbox_upn"
    EMAIL = "email"

@dataclass(frozen=True)
class IdentityHeaderConfig:
    secret: str                        # 32자 이상
    audience: str                      # 서버 MCP_IDENTITY_AUDIENCE 와 일치
    issuer: str = "agent-builder"
    header_name: str = "X-MCP-Identity"
    claim_name: str = "preferred_username"
    claim_source: ClaimSource = ClaimSource.MAILBOX_UPN
    ttl_seconds: int = 300             # 1..300

    @classmethod
    def from_dict(cls, raw: dict) -> "IdentityHeaderConfig": ...   # 검증 실패 ValueError
    def to_dict(self) -> dict: ...
    def masked(self) -> dict: ...                                   # secret → "****"

# domain/mcp_registry/schemas.py — MCPServerRegistration 필드 추가
    identity_config: IdentityHeaderConfig | None = None
    @property
    def requires_identity(self) -> bool: return self.identity_config is not None
```

`IdentityClaimPolicy` (domain, 순수):

```python
class IdentityUnavailableError(Exception):
    reason: Literal["no_subject", "user_not_found", "user_inactive", "claim_empty"]

class IdentityClaimPolicy:
    RESERVED = {"iss", "aud", "sub", "iat", "exp", "nbf", "jti"}
    @staticmethod
    def resolve_claim_value(user: User | None, source: ClaimSource) -> str: ...   # 실패 시 IdentityUnavailableError
    @staticmethod
    def build_claims(cfg, subject_user_id: str, claim_value: str, now: int) -> dict: ...
    @staticmethod
    def user_message(reason) -> str: ...   # 사용자 안내 문구 (§6.1)
```

- `claim_name`이 `RESERVED`에 속하면 `IdentityHeaderConfig.from_dict`에서 거부.
- `approved` 상태가 아닌 사용자는 `user_inactive`.

### 3.2 Entity Relationships

```
[User] 1 ──── (runtime lookup by subject_user_id) ──── N [MCP tool call]
[MCPServerRegistration] 1 ──── 0..1 [IdentityHeaderConfig]  (암호화 JSON 컬럼)
```

### 3.3 Database Schema

`V076__add_mailbox_upn_to_users.sql`

```sql
ALTER TABLE users
    ADD COLUMN mailbox_upn VARCHAR(255) NULL
    COMMENT '관리자가 지정한 사내 메일함 UPN(소문자). 신원 헤더 MCP 호출의 클레임 소스. 로그인 email 과 독립, NULL 이면 메일함 미등록';
```

`V077__add_identity_config_to_mcp_server_registry.sql`

```sql
ALTER TABLE mcp_server_registry
    ADD COLUMN identity_config_enc TEXT NULL
    COMMENT '호출자 신원 헤더 설정(header_name·claim_name·claim_source·issuer·audience·secret·ttl) 암호화 JSON. NULL 이면 신원 헤더 미사용 — 기존 동작과 동일';
```

- ORM: `UserModel.mailbox_upn`, `MCPServerModel.identity_config_enc`에 동일 `comment=`.
- 인덱스 없음 (조회는 PK).
- `identity_config_enc` 저장 시 `SecretCipher` 필수. cipher 없으면 등록/수정 400 (`requires_secret_storage`와 같은 규칙).

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/admin/users` | 목록 응답 항목에 `mailbox_upn` 추가 | admin |
| **PATCH** | `/api/v1/admin/users/{user_id}/mailbox` | 메일함 설정·해제 (신규) | admin |
| POST | `/api/v1/mcp-registry` | 요청에 `identity_config` 선택 필드 | 기존 |
| PUT | `/api/v1/mcp-registry/{id}` | `identity_config` 부분 수정 규칙(§4.2) | 기존 |
| GET | `/api/v1/mcp-registry[/{id}]` | 응답에 `identity_config`(마스킹) | 기존 |

### 4.2 Detailed Specification

#### `PATCH /api/v1/admin/users/{user_id}/mailbox`

```json
// Request
{ "mailbox_upn": "Kim@Corp.com" }      // null 이면 해제
// Response 200
{ "id": 7, "email": "kim@login.local", "mailbox_upn": "kim@corp.com" }
```

| Status | 조건 |
|--------|------|
| 400 | 이메일 형식 아님 / 255자 초과 |
| 404 | 사용자 없음 |
| 403 | admin 아님 |

- 소문자 정규화·trim. 중복 허용 (공유 메일함 가능성, 유니크 제약 없음).
- UseCase: `UpdateUserMailboxUseCase` (application/auth), repository `update_mailbox(user_id, value)` — commit 없음.

#### MCP 등록 `identity_config`

```json
// POST / PUT Request
"identity_config": {
  "audience": "mcp-outlook-server",
  "secret": "<32자 이상>",
  "issuer": "agent-builder",
  "header_name": "X-MCP-Identity",
  "claim_name": "preferred_username",
  "claim_source": "mailbox_upn",
  "ttl_seconds": 300
}
// GET Response (마스킹)
"identity_config": { "audience": "mcp-outlook-server", "issuer": "agent-builder",
  "header_name": "X-MCP-Identity", "claim_name": "preferred_username",
  "claim_source": "mailbox_upn", "ttl_seconds": 300, "secret": "****" }
```

PUT 규칙 (`auth_config`의 통째 교체와 다름 — 비밀 유실 방지):

| 요청 값 | 동작 |
|---|---|
| 필드 없음 | 변경 없음 |
| `null` | 신원 헤더 해제 (컬럼 NULL) |
| 객체, `secret` 없음/빈 값 | 기존 secret 유지 + 나머지 필드 교체. 기존 설정이 없으면 400 |
| 객체, `secret` 있음 | 전체 교체 |

검증 (`MCPRegistrationPolicy.validate_identity`):
- `secret` ≥ 32자, `audience` 비어있지 않음, `ttl_seconds` 1..300
- `header_name`이 RFC 7230 token, `auth_config.headers`에 같은 이름(대소문자 무시)이 있으면 400 (R-6)
- `claim_name` ∉ RESERVED

---

## 5. UI/UX Design

### 5.1 Screen Layout

**AdminUsersPage — 전체 사용자 표**

```
| 이메일 | 이름 | 부서 | 역할 | 상태 | 메일함              | 가입일 |
| kim@.. | 김.. | 여신 | user | 승인 | kim@corp.com  [편집] | ...    |
| lee@.. | 이.. | 심사 | user | 승인 | —            [등록] | ...    |
```
편집 → 인라인 입력 + 저장/취소 (LoadingButton). 빈 값 저장 = 해제.

**AdminMcpServersPage — 등록/수정 폼 하단 섹션**

```
[ ] 호출자 신원 헤더 사용
    audience*      [mcp-outlook-server      ]
    서명 비밀*     [••••••••  ] (수정 시 비우면 기존 유지)
    클레임 소스    (●) 메일함  ( ) 로그인 이메일
    ▸ 고급: header_name / claim_name / issuer / ttl
```

### 5.2 User Flow

관리자: 회원 메일함 등록 → MCP 서버 편집에서 신원 헤더 켜기·비밀 입력 → 저장
P2: 에이전트에 `list_messages` 도구 추가 (변경 없음)
사용자: "내 안 읽은 메일 보여줘" → 본인 메일함 결과 / 미등록이면 안내 문구

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `UserMailboxCell` | `src/components/admin/UserMailboxCell.tsx` | 메일함 표시·인라인 편집 |
| `McpIdentityFields` | `src/components/admin/McpIdentityFields.tsx` | 신원 헤더 폼 섹션 |
| `useUpdateUserMailbox` | `src/hooks/useAdminUsers.ts` (기존 파일) | PATCH 뮤테이션 + 목록 무효화 |

### 5.4 Page UI Checklist

#### AdminUsersPage
- [ ] 전체 사용자 표에 "메일함" 열 (값 또는 `—`)
- [ ] 편집/등록 버튼 → 입력창·저장·취소
- [ ] 저장 버튼은 `LoadingButton` (isPending 가드)
- [ ] 400 오류 시 입력창 아래 서버 메시지 표시
- [ ] 저장 성공 시 목록 재조회 반영

#### AdminMcpServersPage
- [ ] "호출자 신원 헤더 사용" 체크박스 (기존 설정 있으면 켜진 상태로 로드)
- [ ] audience·서명 비밀 필수 표시, 비밀은 password 입력
- [ ] 수정 모드 비밀 placeholder "비우면 기존 유지"
- [ ] 클레임 소스 라디오 2개 (메일함 기본)
- [ ] 고급 접기: header_name·claim_name·issuer·ttl (기본값 채움)
- [ ] 체크 해제 후 저장 → `identity_config: null` 전송
- [ ] 목록 카드/행에 "신원 헤더" 배지

---

## 6. Error Handling

### 6.1 Error Code Definition

| 코드 | 발생 지점 | 사용자에게 보이는 문구 (워커 ToolMessage / 승인 결과) |
|------|----------|------------------------|
| `IDENTITY_NO_SUBJECT` | provider | "이 도구는 사용자 신원이 필요한데 실행 사용자를 알 수 없습니다." |
| `IDENTITY_USER_NOT_FOUND` | provider | "실행 사용자 정보를 찾을 수 없습니다." |
| `IDENTITY_USER_INACTIVE` | provider | "승인되지 않은 사용자는 이 도구를 사용할 수 없습니다." |
| `IDENTITY_CLAIM_EMPTY` | provider | "메일함이 등록되지 않았습니다. 관리자에게 등록을 요청하세요." (source=email 이면 "로그인 이메일") |
| 서버 `IDENTITY_INVALID` | MCP 응답 | 서버 문구 그대로 (설정 불일치 신호 — 로그 WARN) |

### 6.2 Error Handling Rules

- **워커 경로**: `MCPToolAdapter._arun`이 `IdentityUnavailableError`를 잡아 `IdentityClaimPolicy.user_message()` 문자열을 반환 (placeholder 차단과 같은 패턴 — 예외가 아니라 ToolMessage). 로그 `MCP tool call blocked (identity)` WARNING, `reason`, `server`, `subject` 포함, 스택 불필요(예상 경로).
- **집행 경로**: `McpActionExecutor._call`에서 `IdentityUnavailableError` → `status="blocked"` (서버에 보내지 않았음이 확실). 그 외 예외는 기존대로 `unknown`.
- **서명·배선·설정 손상 실패** → `create_session` 이 `HeaderProviderError` 로 감싼다(연결 전). 워커는 일반 도구 오류로 격리, 집행기는 `blocked`, call client 는 재시도하지 않는다 (Check G-2).
- **저장된 설정을 읽을 수 없음**(키 누락·교체·손상) → `identity_config_unreadable=True`, `requires_identity=True` 로 취급(fail-closed). 공급자는 `IdentityConfigUnreadableError`. 수정 API 는 필드 없는 PUT 을 거부해 저장값이 조용히 지워지지 않게 한다 (Check G-3).
- 토큰 원문·secret은 어떤 로그에도 남기지 않는다 (FR-10). 기록: `identity_sub`, `identity_source`, `identity_header`, `server_id`.

---

## 7. Security Considerations

- [x] 클레임 값은 `users` 행에서만 — 도구 인자·정적 헤더 경로 없음
- [x] 발급 헤더는 병합 최후 순위 (정적 헤더 동명 키 무력화, 등록 시에도 차단)
- [x] HS256 고정, 서버별 secret·audience → 다른 서버용 토큰 재사용 불가
- [x] exp ≤ iat+300, 호출마다 신규 발급 (캐시 없음)
- [x] secret 암호화 저장(`SecretCipher`), 응답 마스킹, 로그 제외
- [x] 비승인 사용자 차단
- [x] 승인 집행은 **요청자** 신원 (승인자 아님) — 승인자가 자기 메일함으로 보내는 혼동 방지
- [ ] 웹훅: 외부 입력으로 소유자 메일함 조회 가능 — Plan R-5 수용, 발송은 승인 게이트

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1 단위 | domain VO/Policy, signer, provider factory, client_factory 병합 | pytest | Do |
| L1 API | admin mailbox PATCH, mcp-registry identity_config | pytest + TestClient | Do |
| L2 UI | AdminUsersPage 메일함, AdminMcpServersPage 신원 섹션 | Vitest + RTL + MSW | Do |
| L3 실런 | identity 모드 Outlook 서버(8006) 두 사용자 | 스크립트 (TestClient 인프로세스) | Check |

### 8.2 L1 Key Cases (backend)

| # | 대상 | 케이스 | 기대 |
|---|------|--------|------|
| 1 | `IdentityHeaderConfig.from_dict` | secret 31자 / ttl 301 / claim_name="sub" | ValueError |
| 2 | `IdentityClaimPolicy.resolve_claim_value` | mailbox 없음 / pending 사용자 / None | 각 reason 의 IdentityUnavailableError |
| 3 | `build_claims` | now=1000, ttl=300 | exp=1300, iss/aud/sub/claim 정확 |
| 4 | signer | jose 로 decode(aud 지정) | 클레임 일치, alg=HS256 |
| 5 | **교차 검증** | idt 발급 토큰을 `mcp_shared.auth.HmacTokenVerifier` 규칙(alg·aud·iss·lifetime)으로 검증 | 통과 (verifier 가 import 불가하면 동등 규칙 재현 테스트) |
| 6 | `MCPClientFactory` | static `{X-MCP-Identity: evil}` + provider `{X-MCP-Identity: good}` | good |
| 7 | `MCPClientFactory` | provider=None | 헤더 dict 기존과 동일 (FR-08 스냅샷) |
| 8 | provider 호출 시점 | adapter `_arun` 2회 | provider 2회 호출 (캐시 없음) |
| 9 | `MCPToolAdapter` | provider 가 IdentityUnavailableError | 안내 문자열 반환, create_session 미호출 |
| 10 | `MCPToolLoader.load` | identity 없는 등록 + subject | provider None |
| 11 | `WorkflowCompiler` | subject_user_id 가 create_all_async 에 전달, sub-agent 재귀에도 전달 | 인자 확인 |
| 12 | `McpActionExecutor` | list_tools 는 provider 없음, call_tool 은 provider 사용 / Identity 오류 → blocked | |
| 13 | decide/execute_scheduler | `requested_by` 가 executor 로 전달 | |
| 14 | PATCH mailbox | 대문자 입력 / 형식 오류 / 없음 / 비관리자 | 소문자 저장 / 400 / 404 / 403 |
| 15 | mcp-registry PUT | secret 생략 → 기존 유지, null → 해제, 필드 없음 → 불변 | |
| 16 | mcp-registry GET | secret 마스킹 | "****" |
| 17 | DDL | V076·V077 COMMENT | `test_migration_ddl_comments` 통과 |

### 8.3 L2 UI

| # | Page | Action | Expected |
|---|------|--------|----------|
| 1 | AdminUsers | 메일함 편집 → 저장 | PATCH body `{mailbox_upn}`, 목록 반영 |
| 2 | AdminUsers | 저장 중 | 버튼 disabled (isPending) |
| 3 | AdminMcpServers | 신원 체크 + audience·비밀 입력 → 생성 | POST body `identity_config` 포함 |
| 4 | AdminMcpServers | 수정, 비밀 비움 | PUT `identity_config` 에 secret 키 없음 |
| 5 | AdminMcpServers | 체크 해제 → 저장 | PUT `identity_config: null` |
| 6 | AdminMcpServers | 신원 미사용 서버 수정 | PUT 에 `identity_config` 키 없음 (기존 P-3 테스트와 같은 원칙) |

### 8.4 L3 실런 (Check 단계)

| # | Scenario | Expected |
|---|----------|----------|
| 1 | 사용자 A(mailbox=test@), B(mailbox=sender@) 가 같은 에이전트로 "받은 메일 3개" | 각자 메일함 결과 (SC-1) |
| 2 | 사용자 C(mailbox 없음) | 안내 문구, Outlook 로그에 요청 없음 (SC-2) |
| 3 | 스케줄 1회 트리거 | 스케줄 생성자 메일함 (SC-3) |
| 4 | Scrap MCP 호출 | 헤더 변화 없음 (SC-4) |

### 8.5 Seed Data Requirements

| Entity | Minimum | Key Fields |
|--------|:-------:|------------|
| users | 3 | A·B mailbox 서로 다름, C mailbox NULL, 모두 approved |
| mcp_server_registry | Outlook 1건 | identity_config: audience=mcp-outlook-server, secret=서버 env 와 동일 |

---

## 9. Clean Architecture

### 9.4 This Feature's Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `IdentityHeaderConfig`, `ClaimSource`, `IdentityClaimPolicy`, `IdentityUnavailableError` | Domain | `src/domain/mcp_registry/identity.py` |
| `User.mailbox_upn`, `MailboxPolicy.normalize` | Domain | `src/domain/auth/entities.py`, `policies.py` |
| `UpdateUserMailboxUseCase` | Application | `src/application/auth/update_user_mailbox_use_case.py` |
| identity_config 해석(등록/수정 3상태·충돌·읽을 수 없음 가드) | Application | `src/application/mcp_registry/identity_config.py` (Do module-3 추가 — UseCase 40줄 규칙) |
| `HeaderProviderError` (공급자 단계 실패 — 연결 전) | Infrastructure | `src/infrastructure/mcp/client_factory.py` (Check G-2) |
| `IdentityConfigUnreadableError`, `identity_config_unreadable` 플래그 | Infrastructure / Domain | `identity_headers.py`, `domain/mcp_registry/schemas.py` (Check G-3) |
| subject 전달 배선 | Application | `workflow_compiler.py`, `run_agent_use_case.py`, `approval/decide_use_case.py`, `approval/execute_scheduler.py` |
| `HmacIdentityTokenSigner` | Infrastructure | `src/infrastructure/mcp_registry/identity_token.py` |
| `IdentityHeaderProviderFactory`, `SessionScopedUserReader` | Infrastructure | `src/infrastructure/mcp_registry/identity_headers.py` |
| 헤더 병합 | Infrastructure | `src/infrastructure/mcp/client_factory.py` |
| 라우터·스키마 | Interfaces | `admin_user_router.py`, `interfaces/schemas/auth/*`, `application/mcp_registry/schemas.py` |

- domain 은 `jose`·SQLAlchemy 를 import 하지 않는다. 시각(`now`)은 인자로 받는다.
- provider 는 `Callable[[], Awaitable[dict[str, str]]]` 구조 타입 — domain 포트 신설하지 않음 (Option C, 과도한 추상화 회피).
- `SessionScopedUserReader` 는 `SessionScopedMcpServerRepository` 와 같은 패턴 (tool-and-mcp §3 허용 패턴, 읽기 전용).

---

## 10. Coding Convention Reference

### 10.4 This Feature's Conventions

| Item | Convention Applied |
|------|-------------------|
| 인자 이름 | `subject_user_id: str \| None = None` (키워드 전용, 기본 None → 하위호환) |
| 로깅 | `identity_sub`, `identity_source`, `identity_header`, `server_id`. 토큰·secret 금지 |
| Design 참조 주석 | `# Design Ref: mcp-identity-header §x` |
| 프론트 상수 | 기본값(`X-MCP-Identity` 등)은 `src/types/mcpServer.ts` 의 `as const` (컴포넌트 파일 export 금지) |
| 함수 길이 | 40줄 이하 — `McpActionExecutor._call` 분기 추가 시 헬퍼 분리 |

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── db/migration/V076__add_mailbox_upn_to_users.sql                     (new)
├── db/migration/V077__add_identity_config_to_mcp_server_registry.sql   (new)
├── src/domain/mcp_registry/identity.py                                  (new)
├── src/domain/mcp_registry/{schemas,policies}.py                        (mod)
├── src/domain/auth/{entities,policies,interfaces}.py                    (mod)
├── src/infrastructure/mcp_registry/identity_token.py                    (new)
├── src/infrastructure/mcp_registry/identity_headers.py                  (new)
├── src/infrastructure/mcp_registry/{models,mcp_server_repository,mcp_tool_loader}.py (mod)
├── src/infrastructure/mcp/{client_factory,tool_adapter,tool_registry,call_client}.py (mod)
├── src/infrastructure/auth/{models,user_repository}.py                  (mod)
├── src/infrastructure/agent_builder/tool_factory.py                     (mod)
├── src/infrastructure/approval/{mcp_executor,composite_executor}.py     (mod)
├── src/domain/approval/interfaces.py                                    (mod: execute(subject_user_id=None))
├── src/application/agent_builder/{workflow_compiler,run_agent_use_case}.py (mod)
├── src/application/approval/{decide_use_case,execute_scheduler}.py      (mod)
├── src/application/auth/update_user_mailbox_use_case.py           (new)
├── src/application/mcp_registry/{schemas,register_*,update_*,load_mcp_tools_*}.py (mod)
├── src/application/mcp_registry/identity_config.py                      (new, Do module-3)
├── src/api/routes/admin_user_router.py, src/api/main.py                 (mod: DI)
└── src/interfaces/schemas/auth/{request,response}.py                    (mod)
idt_front/src/
├── types/{auth,mcpServer}.ts, constants/api.ts                          (mod)
├── services/{adminService,mcpServerService}.ts, hooks/useAdminUsers.ts  (mod)
├── components/admin/{UserMailboxCell,McpIdentityFields}.tsx             (new)
└── pages/{AdminUsersPage,AdminMcpServersPage}/index.tsx                 (mod)
```

### 11.2 Implementation Order

1. [ ] domain: `identity.py` (VO·Policy·Error) + `User.mailbox_upn` + `MailboxPolicy`
2. [ ] DDL V076/V077 + ORM comment + repository 매핑(identity_config 암복호화, mailbox)
3. [ ] signer + provider factory + session-scoped user reader
4. [ ] `MCPClientFactory.create_session(header_provider=)` + adapter/registry/call_client 전달
5. [ ] 주체 배선: RunAgent → compile(재귀 포함) → ToolFactory → Loader / approval → executor
6. [ ] API: admin mailbox PATCH, mcp-registry identity_config (PUT 부분 수정 규칙)
7. [ ] 프론트: 타입·서비스·훅 → 컴포넌트 → 페이지
8. [ ] L3 실런 준비: Outlook 서버 identity 모드 전환 (부록 A)

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 데이터·도메인 | `module-1` | identity.py, User.mailbox_upn, V076/V077, ORM·repository 매핑 | 20-25 |
| 런타임 주입 | `module-2` | signer, provider factory, client_factory 병합, adapter/call_client, 주체 배선(compile·approval) | 35-45 |
| 관리자 API | `module-3` | PATCH mailbox, mcp-registry identity_config 스키마·검증·PUT 규칙, DI | 20-25 |
| 관리자 화면 | `module-4` | 타입·서비스·훅, UserMailboxCell, McpIdentityFields, 페이지 | 25-30 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `--scope module-1` | 20-25 |
| Session 2 | Do | `--scope module-2` | 35-45 |
| Session 3 | Do | `--scope module-3` | 20-25 |
| Session 4 | Do | `--scope module-4` | 25-30 |
| Session 5 | Check + L3 실런 | 전체 | 30-40 |

---

## Appendix A. Outlook 서버 identity 모드 전환 체크리스트 (agent_mcp, 범위 밖 운영 작업)

현재 `agent_mcp/docker-compose.yml`은 `OUTLOOK_MAILBOX_RESOLVER=fixed`, `MCP_IDENTITY_AUDIENCE`에 메일 주소가 들어가 있다 (Plan R-4).

1. [ ] `OUTLOOK_MAILBOX_RESOLVER: identity`
2. [ ] `MCP_IDENTITY_AUDIENCE: mcp-outlook-server` — idt 등록 `identity_config.audience`와 동일
3. [ ] `MCP_IDENTITY_ISSUER: agent-builder`
4. [ ] `MCP_IDENTITY_SECRET`: 32자 이상 신규 생성, compose 평문 대신 `.env` 참조 권장. 같은 값을 idt 관리자 화면에 입력
5. [ ] `OUTLOOK_IDENTITY_CLAIM: preferred_username` (idt `claim_name` 과 동일)
6. [ ] Application Access Policy 허용 그룹에 테스트 사용자 메일함 추가 (`Test-ApplicationAccessPolicy` = Granted)
7. [ ] 컨테이너 재기동 → `verify-mcp-connections` 로 list_tools OK 확인 (list_tools 는 신원 불필요)

## Appendix B. MCP 호출 경로 전수 (R-1)

| # | 경로 | 호출 | 주체 출처 | 이번 변경 |
|---|------|------|----------|----------|
| 1 | 워커 도구 | `workflow_compiler.py:782` → `create_all_async` → Adapter `_arun` | `RunAgentRequest.user_id` | subject 전달 |
| 2 | sub-agent 재귀 | `workflow_compiler.py:1236` `self.compile` | 상위 compile 인자 | subject 전달 |
| 3 | 승인 즉시 집행 | `decide_use_case._execute_now` → executor | `approval.requested_by` | subject 전달 |
| 4 | 승인 예약 집행 | `execute_scheduler` → executor | `approval.requested_by` | subject 전달 |
| 5 | 미들웨어 에이전트 | `run_middleware_agent_use_case.py:44` `create_async` | 없음 (요청에 user 필드 없음, 라우트 미사용) | 변경 없음 → 신원 서버면 `IDENTITY_NO_SUBJECT` |
| 6 | 문서 변환 | `document_conversion_adapter.py:155` | 해당 없음 (Doc Convert 는 신원 미설정) | 변경 없음 |
| 7 | 연결 테스트 / 도구 동기화 | list_tools | 해당 없음 | 신원 미주입 (Plan Out of Scope) |
| 9 | 승인 재개 컴파일 (`run_agent_use_case.resume_from_snapshot` → `_resume_graph`) | compile | `approval.requested_by` | subject 전달 |
| 10 | 평가 헤드리스 런 (`main.py` agent 대상 평가 실행기) | `RunAgentUseCase.execute` | 평가 요청 user_id (= viewer) | #1 과 동일 경로 |
| 8 | 일반 채팅 (Do module-2 에서 발견) | `general_chat/tools.py` `MCPToolCache` → `LoadMCPToolsUseCase` → `loader.load` | 없음 — 도구를 **전 사용자 공용 키 `__all__`로 600초 캐시** | 공급자 **미배선 유지**. 사용자별 공급자가 캐시되면 신원이 섞인다. **Check 결정(2026-09-26): 일반 채팅 도구 목록에서 신원 서버를 제외** (`LoadMCPToolsUseCase(exclude_identity_servers=True)`) — 메일 등 사용자별 자원은 에이전트로만 사용 |

**실행 주체 신뢰 (Check G-1)**: 모든 진입점에서 `RunAgentRequest.user_id` 는 인증 주체와 같아야 한다. WebSocket(`user.id`)·스트림(불일치 403)·스케줄·웹훅·백그라운드는 시스템이 채운다. `POST /agents/{id}/run` 은 본문 값을 토큰 사용자로 덮어쓴다(기존 클라이언트 호환).

**미배선 로더 규칙 (Do module-2 결정)**: 신원 필요 서버인데 로더에 공급자 팩토리가 없으면 헤더 없이 보내지 않고, 도구 호출 시점에 `McpIdentityWiringError` 로 실패한다. 목록 조회 전용 로더(동기화·연결 테스트·`/tools`)는 도구를 부르지 않으므로 영향이 없다. 배선된 로더는 에이전트 빌더 런타임(`main.py` `_mcp_tool_loader`)·미들웨어 에이전트·승인 집행기 3곳이다.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-26 | Initial draft — Option C 선택 | 배상규 / Claude |
| 0.2 | 2026-09-26 | Appendix B #8 일반 채팅 경로 추가, 미배선 로더 규칙 명시 (Do module-2) | 배상규 / Claude |
| 0.3 | 2026-09-26 | Check 반영 — G-1 주체 신뢰 규칙, G-2 HeaderProviderError, G-3 읽을 수 없는 설정 fail-closed, 일반 채팅 제외 결정, 부록 B #9·#10, §9.4·§11.1 누락 파일 | 배상규 / Claude |
