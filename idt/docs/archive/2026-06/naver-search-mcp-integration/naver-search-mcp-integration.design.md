# naver-search-mcp-integration Design Document

> **Summary**: Smithery 호스팅 Naver Search MCP(Streamable HTTP)를 우리 `mcp_registry` 등록→로드→호출 경로에 붙이기 위한 상세 설계. transport 선택 일반화, 시크릿(`auth_config`/`server_config`) 주입·암호화·마스킹, Smithery URL 빌더, `MCPToolLoader`의 Streamable HTTP 분기를 정의한다.
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-06-16
> **Status**: Draft
> **Planning Doc**: [naver-search-mcp-integration.plan.md](../../01-plan/features/naver-search-mcp-integration.plan.md)
> **Depends on**: [mcp-http-call-module.plan.md](../../01-plan/features/mcp-http-call-module.plan.md) — `MCPTransport.STREAMABLE_HTTP` + `StreamableHTTPServerConfig` + factory 세션

---

## 1. Overview

### 1.1 Design Goals

- 등록 파이프라인을 **SSE 전용 → transport 선택형**으로 일반화(기본값 SSE 보존, 비파괴).
- Smithery 플랫폼 인증(`api_key`/`profile`)과 다운스트림 서버 config(`NAVER_CLIENT_ID/SECRET`)를 **분리 저장·암호화·마스킹**.
- `MCPToolLoader`가 DB의 transport·auth·config를 읽어 **Streamable HTTP `MCPServerConfig`**(URL+헤더)를 조립.
- Naver Search 1종을 레퍼런스로 등록→tool 로드→호출까지 검증(E2E는 옵트인).

### 1.2 Design Principles

- **비파괴 확장**: 신규 컬럼 nullable, 신규 Request 필드 Optional, transport 기본값 유지.
- **DDD 경계 준수**: domain은 외부 의존 0(암호화/네트워크 금지), 암호화·URL빌더·로더는 infrastructure.
- **시크릿 안전**: 평문 로그 금지, Response 마스킹, 저장 시 대칭암호화(Fernet), vector/대화 DB 저장 금지.
- **단일 책임 헬퍼**: Smithery URL 조립과 시크릿 암복호화는 각각 전용 모듈로 격리.

---

## 2. Architecture

### 2.1 Component Diagram

```
[Client/등록 API]
      │  POST /api/v1/mcp-registry  {transport, auth_config, server_config}
      ▼
RegisterMCPServerUseCase ──(validate)── MCPRegistrationPolicy
      │  encrypt(secrets)
      ▼
MCPServerRepository ──▶ mcp_server_registry  (auth_config_enc, server_config_enc 컬럼 추가)
                                  ▲
[Agent 실행: tool_id="mcp_{id}"]  │ find_by_id
      ▼                           │
ToolFactory.create_async ──▶ MCPToolLoader.load_by_tool_id
                                  │  decrypt + build config
                                  ▼
                          SmitheryUrlBuilder ── StreamableHTTPServerConfig
                                  ▼
              MCPToolRegistry ─▶ MCPClientFactory.create_session(STREAMABLE_HTTP)
                                  ▼
                       Smithery: server.smithery.ai/@.../mcp  ─▶ Naver Search API
```

### 2.2 Data Flow

```
등록:  Request → Policy 검증 → 시크릿 암호화 → DB 저장 → Response(마스킹)
실행:  tool_id → DB 조회 → 시크릿 복호화 → Smithery URL 조립 → StreamableHTTP 세션 → call_tool → 결과 텍스트
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `MCPToolLoader` | `SmitheryUrlBuilder`, `SecretCipher`, `MCPToolRegistry` | transport별 config 조립·복호화 |
| `RegisterMCPServerUseCase` | `SecretCipher`, `MCPRegistrationPolicy` | 시크릿 암호화·검증 |
| `SmitheryUrlBuilder` | (없음, infra 순수 함수) | `/mcp` URL + api_key/profile/config 쿼리 |
| `SecretCipher` | `cryptography.Fernet`, `settings.MCP_SECRET_KEY` | 대칭 암복호화 |
| `MCPClientFactory` | 선행 모듈의 `streamablehttp_client` | Streamable HTTP 세션 |

---

## 3. Data Model

### 3.1 Domain Entity 변경 (`domain/mcp_registry/schemas.py`)

```python
class MCPTransportType(str, Enum):
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"   # (+) 신규

@dataclass
class MCPServerRegistration:
    id: str
    user_id: str
    name: str
    description: str
    endpoint: str
    transport: MCPTransportType
    input_schema: dict | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    # (+) 신규 — 평문 dict(앱 메모리). 저장 직전 암호화, 조회 직후 복호화.
    auth_config: dict | None = None      # 플랫폼 인증: {"api_key","profile","headers":{...}}
    server_config: dict | None = None    # 다운스트림: {"NAVER_CLIENT_ID","NAVER_CLIENT_SECRET"}

    def masked_auth(self) -> dict | None: ...    # (+) 값 → "****", 키만 노출
    def masked_server_config(self) -> dict | None: ...
```

> **결정(Open Q4)**: `auth_config`(플랫폼)와 `server_config`(다운스트림)를 **2개 분리**. 책임이 다르고(우리 Smithery 계정 키 vs 사용자 Naver 키) 마스킹/회전 주기가 다르기 때문. 단일 JSON 대비 약간의 컬럼 증가는 수용.

### 3.2 DB Schema 변경 (비파괴, `infrastructure/mcp_registry/models.py`)

```python
class MCPServerModel(Base):
    __tablename__ = "mcp_server_registry"
    # ... 기존 컬럼 유지 ...
    transport: Mapped[str] = mapped_column(String(20), nullable=False, default="sse")  # 값만 확장
    auth_config_enc:   Mapped[str | None] = mapped_column(Text, nullable=True)  # (+) Fernet 암호문
    server_config_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # (+) Fernet 암호문
```

### 3.3 Migration (`db/migration/V032__alter_mcp_server_registry_add_secrets.sql`)

```sql
-- V032: MCP 서버 등록에 transport별 인증/서버 config(암호문) 컬럼 추가 (비파괴)
ALTER TABLE mcp_server_registry
    ADD COLUMN auth_config_enc   TEXT NULL AFTER input_schema,
    ADD COLUMN server_config_enc TEXT NULL AFTER auth_config_enc;
-- 기존 행: 두 컬럼 NULL, transport 기존값('sse') 유지 → 동작 불변
```

> 최신 마이그레이션 V031 기준 다음 번호 **V032**. `db-migration` 스킬로 모델→DDL 동기화 검증.

### 3.4 시크릿 저장 전략 (Open Q3 결정)

- **앱 레벨 대칭암호화(Fernet)** 채택. 키는 `settings.MCP_SECRET_KEY`(.env, 32B urlsafe base64).
- 저장: `auth_config`/`server_config` dict → JSON → `Fernet.encrypt` → `*_enc` 컬럼(Text).
- 조회: `*_enc` → `Fernet.decrypt` → JSON → dict(앱 메모리 한정, 로더에서만 사용).
- `.env` 참조키 방식은 다중 사용자가 각자 Naver 키를 넣는 본 요건과 맞지 않아 제외. KMS/Vault 이관은 후속(plan §8).

---

## 4. API Specification

### 4.1 Endpoint (기존 라우터 확장, 경로 불변)

| Method | Path | 변경 |
|--------|------|------|
| POST | `/api/v1/mcp-registry` | Request에 `transport`/`auth_config`/`server_config` 추가 |
| GET | `/api/v1/mcp-registry`, `/{id}` | Response 시크릿 **마스킹** |
| PUT | `/api/v1/mcp-registry/{id}` | 동일 신규 필드 수용 |

### 4.2 Request/Response 스키마 (`application/mcp_registry/schemas.py`)

```python
class RegisterMCPServerRequest(BaseModel):
    user_id: str
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    endpoint: str
    input_schema: dict | None = None
    transport: str = Field(default="sse")                    # (+) "sse" | "streamable_http"
    auth_config: dict | None = None                          # (+) {"api_key","profile","headers"}
    server_config: dict | None = None                        # (+) {"NAVER_CLIENT_ID","NAVER_CLIENT_SECRET"}

class MCPServerResponse(BaseModel):
    # ... 기존 필드 ...
    transport: str
    auth_config: dict | None        # to_response에서 masked_auth() 적용
    server_config: dict | None      # to_response에서 masked_server_config() 적용
```

**Naver Search 등록 예시 (POST):**
```json
{
  "user_id": "u-123",
  "name": "Naver Search",
  "description": "네이버 블로그/뉴스/쇼핑 검색 MCP (Smithery)",
  "endpoint": "https://server.smithery.ai/@isnow890/naver-search-mcp/mcp",
  "transport": "streamable_http",
  "auth_config": { "api_key": "smithery_xxx", "profile": "my-profile" },
  "server_config": { "NAVER_CLIENT_ID": "xxx", "NAVER_CLIENT_SECRET": "yyy" }
}
```
**Response (201, 마스킹):**
```json
{
  "transport": "streamable_http",
  "auth_config": { "api_key": "****", "profile": "****" },
  "server_config": { "NAVER_CLIENT_ID": "****", "NAVER_CLIENT_SECRET": "****" }
}
```

> **Open Q1/Q2(Design 실측 확정 필요)**: `qualifiedName`은 `@isnow890/naver-search-mcp` 가정(대안 `@jikime/py-mcp-naver-search`). config 전달은 Smithery 표준 **base64 JSON `config` 쿼리** 우선, 실패 시 dot-notation으로 폴백 — `SmitheryUrlBuilder`가 단일 지점에서 처리.

---

## 5. 핵심 모듈 설계

### 5.1 `SmitheryUrlBuilder` (`infrastructure/mcp_registry/smithery_url.py`)

```python
def build_streamable_http(endpoint: str, auth_config: dict | None,
                          server_config: dict | None) -> tuple[str, dict[str, str]]:
    """Smithery /mcp URL + 헤더 반환.
    - endpoint 끝이 /mcp 아니면 보정
    - api_key/profile → 쿼리 파라미터
    - server_config → base64(JSON) 'config' 쿼리
    - auth_config['headers'] → 추가 HTTP 헤더(Authorization 등)
    return (url_with_query, headers)
    """
```
- 순수 함수(네트워크 X), 40줄·if중첩2 이내. URL 조립 규칙을 여기 한 곳에만 둔다.

### 5.2 `SecretCipher` (`infrastructure/security/secret_cipher.py`)

```python
class SecretCipher:
    def __init__(self, key: str): self._f = Fernet(key)
    def encrypt_dict(self, data: dict | None) -> str | None: ...
    def decrypt_dict(self, token: str | None) -> dict | None: ...
```
- `settings.MCP_SECRET_KEY` 주입. 키 미설정 시 명시적 설정 에러(하드코딩 금지, NFR-5).

### 5.3 `MCPToolLoader` 분기 (`infrastructure/mcp_registry/mcp_tool_loader.py`)

```python
async def load(self, registration, request_id):
    if registration.transport == MCPTransportType.STREAMABLE_HTTP:
        url, headers = build_streamable_http(
            registration.endpoint, registration.auth_config, registration.server_config)
        config = MCPServerConfig(
            name=registration.tool_id,
            transport=MCPTransport.STREAMABLE_HTTP,
            streamable_http=StreamableHTTPServerConfig(url=url, headers=headers),
        )
    else:  # SSE (기존 경로 보존)
        config = MCPServerConfig(name=registration.tool_id,
            transport=MCPTransport.SSE, sse=SSEServerConfig(url=registration.endpoint))
    registry = MCPToolRegistry(configs=[config])
    return await registry.get_tools(request_id=request_id)
```
- `load_by_tool_id`는 시그니처 유지. 복호화는 **repository `_to_entity`에서 SecretCipher로 수행**(loader는 평문 dict만 사용) → DI로 cipher 주입.

### 5.4 복호화 시점 (Repository)

`mcp_server_repository._to_entity`에 `SecretCipher` 주입 → `auth_config_enc`/`server_config_enc` 복호화하여 엔티티 평문 필드 채움. `_to_model`은 암호화 적용. (UseCase는 평문 dict만 다룸, 암복호화는 infra 경계에 격리.)

---

## 6. Error Handling

| 상황 | 코드 | 처리 |
|------|------|------|
| 비허용 transport | 422 | Policy `validate_transport` 거부, 메시지 명시 |
| streamable_http인데 `auth_config.api_key` 누락 | 422 | Policy `validate_auth(transport, auth_config)` |
| `MCP_SECRET_KEY` 미설정 | 500(기동/등록 시) | 설정 에러 명시, 시크릿 미저장 |
| 복호화 실패(키 회전 등) | 500 + 로그 | `request_id`·server_id 로그, 스택트레이스 포함 |
| Smithery 401/4xx | tool 결과 `is_error` | `MCPToolRegistry`가 서버 단위 격리(빈 tool), 로그 경고 |
| Naver 자격증명 오류 | tool 결과 텍스트 | 호출 결과로 전파, 등록 자체는 성공 |

> 시크릿은 어떤 에러 로그에도 평문 출력 금지(마스킹 후 로깅).

---

## 7. Security Considerations

- [x] 시크릿 저장 시 Fernet 대칭암호화(`*_enc` 컬럼)
- [x] Response 마스킹(`masked_auth`/`masked_server_config`)
- [x] 로그에 시크릿 평문 금지, `request_id`만
- [x] HTTPS 강제(Smithery endpoint, Policy `ALLOWED_SCHEMES`에 https 보장 — http 허용 유지하되 streamable_http는 https 권장 경고)
- [x] 시크릿 vector/대화 DB 저장 금지(CLAUDE.md §6)
- [ ] 키 회전/KMS — 후속(plan §8)

---

## 8. Test Plan

### 8.1 Scope

| Type | Target | Tool |
|------|--------|------|
| Unit (domain) | `MCPTransportType` 확장, `masked_*`, Policy `validate_transport/validate_auth` | pytest |
| Unit (infra) | `SmitheryUrlBuilder`(쿼리/헤더/base64), `SecretCipher`(왕복), loader 분기 | pytest + mock |
| Unit (app) | RegisterUseCase transport 사용·암호화 호출, `to_response` 마스킹 | pytest |
| Migration | V032 적용 후 기존 행 보존·신규 컬럼 nullable | 리뷰/스테이징 |
| E2E (opt-in) | 실제 Smithery Naver Search 1콜 | `@pytest.mark.e2e` |

### 8.2 Key Test Cases

- [ ] Happy: streamable_http 등록 → `_enc` 저장 → 복호화 → `build_streamable_http`가 `/mcp?api_key=...&profile=...&config=base64` + headers 생성.
- [ ] SSE 회귀: transport 미지정 등록이 기존과 동일 동작(SSEServerConfig, `_enc` NULL).
- [ ] Masking: Response에 시크릿 평문 부재(`****`).
- [ ] Policy: streamable_http + api_key 누락 → 422.
- [ ] Cipher: encrypt→decrypt 동일 dict, None→None.
- [ ] Edge: endpoint가 `/mcp` 없이 들어와도 보정.
- [ ] Windows 이벤트 루프 flakiness → 비동기 테스트 **격리 실행** 회귀 판정.

---

## 9. Clean Architecture

### 9.1 Layer Assignment (This Feature)

| Component | Layer | Location |
|-----------|-------|----------|
| `MCPTransportType`, `MCPServerRegistration`(+필드/마스킹) | Domain | `src/domain/mcp_registry/schemas.py` |
| `MCPRegistrationPolicy`(+validate_transport/auth) | Domain | `src/domain/mcp_registry/policies.py` |
| `RegisterMCPServerRequest/Response`, UseCase | Application | `src/application/mcp_registry/` |
| `MCPServerModel`(+컬럼), Repository(암복호화) | Infrastructure | `src/infrastructure/mcp_registry/` |
| `SmitheryUrlBuilder`, `MCPToolLoader`(분기) | Infrastructure | `src/infrastructure/mcp_registry/` |
| `SecretCipher` | Infrastructure | `src/infrastructure/security/` |
| `StreamableHTTPServerConfig`, factory 세션 | Infrastructure | `src/{domain,infrastructure}/mcp/` (선행 모듈) |

### 9.2 Dependency Rules 준수

- domain(`schemas`/`policies`)은 `cryptography`·`mcp`·네트워크 **import 금지** — 마스킹은 순수 dict 변환만.
- 암복호화는 **infrastructure 경계(Repository)** 에서만. UseCase는 평문 dict만 취급.
- `verify-architecture`로 domain→infra 역참조 0 검증.

---

## 10. Coding Convention Reference

| Item | Convention |
|------|-----------|
| 함수 길이 | 40줄 이내 (`build_streamable_http`는 헬퍼 분할) |
| if 중첩 | 2단계 이내 (transport 분기는 early-return) |
| 타입 | pydantic/typing 명시, `dict | None` 일관 |
| config | `MCP_SECRET_KEY`·기본 타임아웃은 `src/config.settings` (하드코딩 금지) |
| 로깅 | LOG-001, `request_id` 필수, 시크릿 마스킹 후 |
| env 키 | `MCP_SECRET_KEY`(.env, 서버 전용) |

---

## 11. Implementation Guide

### 11.1 변경/신규 파일

```
src/domain/mcp_registry/schemas.py        (~) enum/엔티티/마스킹
src/domain/mcp_registry/policies.py       (~) validate_transport/validate_auth
src/application/mcp_registry/schemas.py    (~) Request/Response/to_response
src/application/mcp_registry/register_mcp_server_use_case.py  (~) transport·암호화
src/application/mcp_registry/update_mcp_server_use_case.py    (~) 동일
src/infrastructure/mcp_registry/models.py  (~) *_enc 컬럼
src/infrastructure/mcp_registry/mcp_server_repository.py (~) 암복호화(_to_model/_to_entity)
src/infrastructure/mcp_registry/mcp_tool_loader.py (~) transport 분기
src/infrastructure/mcp_registry/smithery_url.py    (+) URL 빌더
src/infrastructure/security/secret_cipher.py       (+) Fernet 암복호화
db/migration/V032__alter_mcp_server_registry_add_secrets.sql (+)
src/config/settings.py                     (~) MCP_SECRET_KEY
tests/...                                   (+) 각 단위테스트
```

### 11.2 Implementation Order (TDD Red→Green)

1. [ ] **M0** 선행 `mcp-http-call-module`의 `STREAMABLE_HTTP`/`StreamableHTTPServerConfig`/factory 가용 확인 (없으면 최소 흡수)
2. [ ] **M1** domain: enum 확장 + 마스킹 + Policy 검증 (+테스트)
3. [ ] **M2** `SecretCipher` + `settings.MCP_SECRET_KEY` (+왕복 테스트)
4. [ ] **M3** models `*_enc` 컬럼 + V032 마이그레이션(`db-migration`)
5. [ ] **M4** Request/UseCase/Response + Repository 암복호화 + `api-contract` 동기화 (+테스트)
6. [ ] **M5** `SmitheryUrlBuilder` + `MCPToolLoader` 분기 (+테스트)
7. [ ] **M6** Naver Search 시드 등록 + tool 로드/호출(mock) + 옵트인 E2E
8. [ ] **검증** `verify-architecture`/`verify-logging`/`verify-tdd` → `/pdca analyze`

### 11.3 의존성

- `cryptography`(Fernet) — 설치 여부 확인, 없으면 `requirements`에 추가.
- 선행 모듈 산출물(STREAMABLE_HTTP) — M0 게이트.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-16 | Initial draft | 배상규 |
