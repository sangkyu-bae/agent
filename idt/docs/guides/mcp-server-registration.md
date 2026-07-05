# MCP 서버 등록 가이드 (제공자용)

> **Audience**: 우리 플랫폼에 연결할 **MCP 서버를 직접 만드는 개발자/제공자**
> **Last Updated**: 2026-06-30
> **Related**: `src/application/mcp_registry/schemas.py`, `src/domain/mcp_registry/policies.py`, `src/infrastructure/mcp_registry/smithery_url.py`

이 문서는 **당신이 만든 MCP 서버를 우리 플랫폼(Agent Builder)에 등록할 때 어떤 JSON을 제공해야 하는지**를 정의합니다.
MCP 서버를 다 만든 뒤, 아래 형식에 맞춰 **등록 JSON 한 벌**을 우리 쪽(운영자/관리자 UI 또는 API)에 전달하면 됩니다.

---

## 1. 한눈에 보기 — 무엇을 제공해야 하나

| 항목 | 필수 | 설명 |
|------|:---:|------|
| `name` | ✅ | 서버 표시 이름 (1~255자) |
| `description` | ✅ | 서버/도구 설명 (1~2000자). 에이전트가 도구 선택에 참고 |
| `endpoint` | ✅ | MCP 접속 URL (`http`/`https`, 최대 512자) |
| `transport` | ✅ | 연결 방식: `"sse"` 또는 `"streamable_http"` |
| `auth_config` | 조건부 | 플랫폼 인증 정보. `streamable_http`는 `api_key` **필수** |
| `server_config` | 선택 | 다운스트림 서버에 넘길 설정값 (예: `NAVER_CLIENT_ID`) |
| `input_schema` | 선택 | 입력 파라미터 JSON Schema (문서/검증용) |
| `user_id` | ✅ | 등록 소유자 ID (우리 쪽에서 채워주는 값) |

> ⚠️ **시크릿 주의**: `auth_config` / `server_config`의 값은 저장 시 암호화되고, 조회·로그 응답에서는 `****`로 마스킹됩니다. **평문 키를 문서/이슈/슬랙에 그대로 붙여넣지 마세요.**

---

## 2. transport 두 종류 — 어느 쪽인지 먼저 정하기

당신의 MCP 서버가 어떤 방식으로 노출되는지에 따라 제공할 JSON이 달라집니다.

### 2-1. `sse` — 일반 SSE MCP 서버

가장 단순한 경우. 인증이 URL 자체에 들어있거나 인증이 없는 자체 호스팅 서버.

```json
{
  "name": "My Weather MCP",
  "description": "도시명으로 현재 날씨를 조회하는 MCP 서버",
  "endpoint": "https://mcp.example.com/sse",
  "transport": "sse"
}
```

- `endpoint`는 **그대로** 접속에 사용됩니다 (경로 보정 없음).
- 인증이 필요하면 URL 쿼리/경로에 직접 포함하거나, 아래 `auth_config.headers`를 사용하세요.
- `auth_config`는 SSE에서 **필수가 아님** (검증 통과).

### 2-2. `streamable_http` — Smithery 호스팅 형식

Smithery 같은 플랫폼에서 호스팅되는 Streamable HTTP 서버. **`api_key`가 필수**입니다.

```json
{
  "name": "Naver Search MCP",
  "description": "네이버 검색(블로그/뉴스/지역) MCP 서버",
  "endpoint": "https://server.smithery.ai/@author/naver-search",
  "transport": "streamable_http",
  "auth_config": {
    "api_key": "smithery-platform-api-key",
    "profile": "your-profile-id"
  },
  "server_config": {
    "NAVER_CLIENT_ID": "xxxx",
    "NAVER_CLIENT_SECRET": "yyyy"
  }
}
```

우리 플랫폼이 이 JSON으로 실제 호출 URL을 **자동 조립**합니다
(`src/infrastructure/mcp_registry/smithery_url.py`):

1. `endpoint` 경로 끝이 `/mcp`가 아니면 자동으로 `/mcp`를 붙임
   → `https://server.smithery.ai/@author/naver-search/mcp`
2. `auth_config.api_key`, `auth_config.profile` → URL 쿼리 파라미터로 추가
3. `server_config` → JSON 직렬화 후 **base64**로 인코딩하여 `config` 쿼리로 추가
4. `auth_config.headers` → 정적 HTTP 헤더로 추가 (예: `Authorization`)

즉 제공자는 **base64 인코딩이나 URL 조립을 직접 할 필요가 없습니다.** 원본 값만 위 구조로 넘기면 됩니다.

---

## 3. 필드별 상세 규칙

### `endpoint`
- `http://` 또는 `https://` 스킴만 허용, 최대 512자.
- `streamable_http`는 `/mcp` 경로가 자동 보정되므로 base URL만 줘도 됩니다.

### `auth_config` (플랫폼/접속 인증)
```jsonc
{
  "api_key": "...",        // streamable_http 필수, 공백만이면 거부
  "profile": "...",        // 선택 (Smithery profile)
  "headers": {             // 선택 — 정적 HTTP 헤더
    "Authorization": "Bearer ..."
  }
}
```
- `sse`: 생략 가능. `headers`만 쓰고 싶을 때도 여기에.
- `streamable_http`: `api_key` 없으면 **422 등록 거부**.

### `server_config` (다운스트림 서버 설정)
- MCP 서버가 동작하기 위해 필요한 서버측 설정값 (API 키, 클라이언트 ID 등).
- key-value dict로 제공. 우리 쪽에서 base64로 인코딩해 전달합니다.
- 예: 네이버 검색 서버의 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`.

### `input_schema` (선택)
- 도구 입력 파라미터를 설명하는 **JSON Schema**. 문서화/검증 용도.
- 실제 도구 스펙은 연결 시 `list_tools`로 가져오므로 필수는 아닙니다.

```json
{
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "검색어" }
    },
    "required": ["query"]
  }
}
```

---

## 4. 등록 API (운영자/관리자가 호출)

제공받은 JSON은 아래 엔드포인트로 등록됩니다. (`user_id`는 등록자 쪽에서 채움)

```http
POST /api/v1/mcp-registry
Content-Type: application/json
```

```json
{
  "user_id": "<등록자 ID>",
  "name": "Naver Search MCP",
  "description": "네이버 검색 MCP 서버",
  "endpoint": "https://server.smithery.ai/@author/naver-search",
  "transport": "streamable_http",
  "auth_config": { "api_key": "...", "profile": "..." },
  "server_config": { "NAVER_CLIENT_ID": "...", "NAVER_CLIENT_SECRET": "..." }
}
```

**응답(201)**: 저장된 서버 정보. 시크릿은 `****`로 마스킹되며, 내부 도구 ID는 `mcp_{uuid}` 형태로 부여됩니다.

### 등록 후 연결 테스트
```http
POST /api/v1/mcp-registry/{id}/test
```
- 실제로 서버에 붙어 `list_tools`를 수행하고, 노출되는 도구 목록을 돌려줍니다.
- 연결/조회 실패는 예외가 아닌 `200 + { "ok": false, "error": "..." }`로 반환됩니다.

| 메서드 | 경로 | 용도 |
|--------|------|------|
| `POST` | `/api/v1/mcp-registry` | 등록 |
| `GET` | `/api/v1/mcp-registry?user_id=` | 목록 조회 |
| `GET` | `/api/v1/mcp-registry/{id}` | 단건 조회 |
| `PUT` | `/api/v1/mcp-registry/{id}` | 수정 |
| `DELETE` | `/api/v1/mcp-registry/{id}` | 삭제 |
| `POST` | `/api/v1/mcp-registry/{id}/test` | 연결 테스트 |

---

## 5. 자주 막히는 부분 (Troubleshooting)

| 증상 | 원인 | 해결 |
|------|------|------|
| 등록 시 `422 api_key required for streamable_http` | `streamable_http`인데 `auth_config.api_key` 누락/공백 | `auth_config.api_key`를 채워 제공 |
| 등록 시 `MCP_SECRET_KEY가 설정되지 않아...` | 서버에 암호화 키 미설정 | 운영자: `.env`에 `MCP_SECRET_KEY` 설정 후 재시도 |
| 연결 테스트 `Session terminated` / 404 | endpoint 404 — 주로 `api_key` 오타/누락 또는 `/mcp` 경로 문제 | `api_key` 값과 endpoint 경로 확인 |
| `Invalid endpoint URL` | 스킴이 http/https가 아니거나 512자 초과 | URL 형식 점검 |

> 참고: `Session terminated`는 세션 만료가 아니라 **HTTP 404**를 의미합니다. 대부분 빈/잘못된 `api_key`가 Smithery URL에서 빠진 경우입니다.

---

## 6. 제공자에게 요청할 때 쓰는 템플릿

MCP 서버 제공자에게 아래 양식 그대로 채워달라고 요청하세요.

```json
{
  "name": "<서버 이름>",
  "description": "<무슨 일을 하는 서버인지>",
  "endpoint": "<http(s):// 접속 URL>",
  "transport": "<sse | streamable_http>",
  "auth_config": {
    "api_key": "<streamable_http면 필수>",
    "profile": "<선택>",
    "headers": { }
  },
  "server_config": {
    "<KEY>": "<VALUE>"
  },
  "input_schema": null
}
```

> 시크릿(api_key/secret)은 **보안 채널**로 따로 전달하고, 위 JSON에는 자리표시자만 남겨두는 것을 권장합니다.
