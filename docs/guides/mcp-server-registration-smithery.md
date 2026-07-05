# MCP 서버 등록 가이드 — Smithery.ai (예: Naver Search)

> 대상 페이지: **Admin → MCP 서버 관리** (`/admin/mcp-servers`)
> 예시 서버: https://smithery.ai/servers/naver/search
> 최종 수정: 2026-06-24 (검증 완료: `naver/search` 게이트웨이 방식)

이 문서는 Smithery.ai에서 호스팅되는 MCP 서버(예: Naver Search)를
관리자 화면에서 등록하는 방법을 단계별로 설명한다.

---

## 0. 빠른 시작 — 검증된 등록값 (A 방식)

> 2026-06-24 실측으로 **연결되는 것이 확인된** 최소 설정. 자세한 설명은 1장 이후 참조.

**핵심: `server.smithery.ai/naver/search` (게이트웨이 형식)으로 등록한다.**

| 입력 칸 | 값 | 비고 |
|---------|-----|------|
| 이름 | `Naver Search` | |
| 설명 | `네이버 검색 (Smithery 호스팅)` | |
| **엔드포인트** | `https://server.smithery.ai/naver/search` | ⚠️ `/mcp`·쿼리 붙이지 말 것 (시스템이 자동 부착) |
| Transport | `Streamable HTTP` | |
| **API Key** | Smithery API Key | 필수 |
| Profile | Smithery Profile | `server.smithery.ai` 게이트웨이는 보통 함께 필요 |
| **Server Config** | **비움** | `naver/search`는 자체 자격증명 보유 → NAVER 키 불필요 |

검증 결과:
```
POST https://server.smithery.ai/naver/search/mcp   → 401 (엔드포인트 존재, 키만 필요) ✅
POST https://server.smithery.ai/@isnow890/naver-search-mcp/mcp → 404 (원격 서버 없음) ❌
```

### ⚠️ 서버 선택 주의 — 원격(remote) vs 로컬(local)

Smithery 서버는 두 종류다. **streamable_http로 등록 가능한 것은 "원격 호스팅" 서버뿐이다.**

| 서버 | `remote` | 결과 |
|------|----------|------|
| `naver/search` | **true** (호스팅됨) | ✅ 등록·연결 가능 |
| `@isnow890/naver-search-mcp` | **false** (npx 로컬 실행 전용) | ❌ 원격 URL 없음 → 404 |

확인법:
```bash
curl https://registry.smithery.ai/servers/<qualifiedName>
# "remote": true 이고 "connections"에 type "http"가 있어야 streamable_http 등록 가능
```
`remote:false`(`connections:[]`)인 서버는 로컬 stdio 전용이라 **이 플랫폼(streamable_http/sse만 지원)으로는 등록 불가**다.

### ⚠️ `/mcp` 경로 자동 부착 주의

코드(`smithery_url.py:_ensure_mcp_path`)가 endpoint 끝에 **무조건 `/mcp`를 붙인다.**

- ✅ `https://server.smithery.ai/naver/search` → `.../naver/search/mcp` (정상)
- ❌ Smithery 페이지에 표시되는 `https://search--naver.run.tools` (run.tools 배포 URL)을 그대로 넣으면
  코드가 `https://search--naver.run.tools/mcp`로 바꿔 **404**가 난다. (run.tools 베이스는 `/mcp`가 없음)
- 그래서 A 방식에서는 **반드시 `server.smithery.ai/{namespace}/{slug}` 게이트웨이 형식**을 쓴다.

---

## 1. 개념 정리

### 1-1. 이 플랫폼의 MCP 등록 모델

MCP 서버 1건은 다음 3종류의 정보로 구성된다.

| 구분 | 설명 | 저장 방식 |
|------|------|-----------|
| **기본 정보** | name, description, endpoint, transport | 평문 |
| **인증 정보 (`auth_config`)** | 플랫폼(Smithery) 인증 — `api_key`, `profile`, `headers` | **Fernet 암호화** |
| **서버 설정 (`server_config`)** | 다운스트림 서버 자격증명 — 예: `NAVER_CLIENT_ID/SECRET` | **Fernet 암호화** |

- 시크릿(`auth_config`, `server_config`)은 DB에 **암호화 컬럼**(`auth_config_enc`, `server_config_enc`)으로 저장된다.
- 조회 응답에서는 모든 시크릿 값이 `****`로 **마스킹**되어 내려온다.
- 복호화된 평문은 **MCP 연결 시점에만 메모리에서** 사용된다.

> 암호화 키는 백엔드 환경변수 `MCP_SECRET_KEY`(urlsafe base64 32바이트 Fernet 키)로 설정한다.
> 미설정 시 등록/연결이 동작하지 않으므로 사전에 `.env`에 채워둔다.

### 1-2. Transport 종류

| 값 | 라벨 | 비고 |
|----|------|------|
| `sse` | SSE | 기본값. API Key 불필요 |
| `streamable_http` | Streamable HTTP | **Smithery 서버는 이 값** 사용. API Key 필수 |

Smithery 호스팅 서버는 **반드시 `Streamable HTTP`** 를 선택한다.

---

## 2. Smithery 서버는 어떻게 호출되는가

Smithery Streamable HTTP 서버는 다음 규칙으로 최종 URL이 조립된다.
(코드: `idt/src/infrastructure/mcp_registry/smithery_url.py` → `build_streamable_http()`)

```
{endpoint}/mcp ? api_key={api_key} & profile={profile} & config={base64(JSON(server_config))}
```

- `endpoint` path 끝이 `/mcp`가 아니면 자동으로 `/mcp`를 붙인다.
- `auth_config.api_key`, `auth_config.profile` → **쿼리 파라미터**
- `server_config`(dict) → **base64(JSON)** 로 인코딩되어 `config` 쿼리 파라미터
- `auth_config.headers` → 추가 HTTP 헤더(예: `Authorization`)

### 예시

> ⚠️ 아래는 **URL 조립 규칙(특히 server_config → base64 config)을 설명하기 위한 예시**일 뿐이다.
> `@isnow890/naver-search-mcp`는 `remote:false`(로컬 전용)라 실제로는 404가 나므로 등록 대상이 아니다.
> 실제 등록은 0장의 `server.smithery.ai/naver/search`(server_config 비움)를 사용한다.

입력(조립 규칙 설명용):
```jsonc
endpoint     = "https://server.smithery.ai/@isnow890/naver-search-mcp"
auth_config  = { "api_key": "sk_xxx", "profile": "default" }
server_config= { "NAVER_CLIENT_ID": "abc", "NAVER_CLIENT_SECRET": "xyz" }
```

조립된 호출 URL:
```
https://server.smithery.ai/@isnow890/naver-search-mcp/mcp?api_key=sk_xxx&profile=default&config=eyJOQVZFUl9DTElFTlRfSUQiOiJhYmMiLCJOQVZFUl9DTElFTlRfU0VDUkVUIjoieHl6In0=
```

> 즉, **endpoint에는 쿼리스트링을 직접 붙이지 않는다.** API Key·Profile·Config는 각 입력 칸에 따로 넣으면 시스템이 알아서 URL을 조립한다.

---

## 3. 사전 준비물

Naver Search MCP를 등록하려면 두 가지 자격증명이 필요하다.

1. **Smithery API Key** (+ 선택적으로 Profile)
   - https://smithery.ai → 로그인 → 계정 설정에서 API Key 발급
   - 등록할 서버 페이지(https://smithery.ai/servers/naver/search)의 **Connect** 탭에서
     Streamable HTTP 연결 URL(`https://server.smithery.ai/.../mcp`)을 확인
2. **Naver 개발자 자격증명** (다운스트림 서버용)
   - https://developers.naver.com → 애플리케이션 등록 → **검색 API** 사용 설정
   - `Client ID`, `Client Secret` 확보

---

## 4. 등록 절차 (UI)

> 화면: `/admin/mcp-servers` → 우측 상단 **「서버 등록」** 버튼

### 4-1. 입력 필드 매핑표

| 화면 입력 칸 | 값 (Naver Search 예시) | 필수 | 백엔드 매핑 |
|--------------|------------------------|:----:|-------------|
| **이름** | `Naver Search` | ✅ | `name` (≤255자) |
| **설명** | `네이버 블로그/뉴스/쇼핑 검색 (Smithery)` | ✅ | `description` |
| **엔드포인트** | `https://server.smithery.ai/naver/search` | ✅ | `endpoint` (http/https, ≤512자) |
| **Transport** | `Streamable HTTP` | ✅ | `transport` |
| **API Key** | `sk_...` (Smithery API Key) | ✅* | `auth_config.api_key` |
| **Profile** | Smithery profile | ⬜*** | `auth_config.profile` |
| **Headers** | (선택) `{"X-Custom":"value"}` | ⬜ | `auth_config.headers` |
| **Server Config** | (비움 — `naver/search`는 불필요) | ⬜** | `server_config` |

> `*` Streamable HTTP는 **신규 등록 시 API Key 필수**.
> `**` Server Config는 **다운스트림 자격증명을 직접 요구하는 서버**에서만 필요하다.
> `naver/search`처럼 Smithery가 자격증명을 내장한 서버는 비워둔다(configSchema가 비어있음).
> 만약 `remote:false`인 로컬 서버의 코드를 직접 호스팅한 경우에만 `NAVER_CLIENT_ID/SECRET`을 넣는다.
> `***` `server.smithery.ai` 게이트웨이는 보통 **profile을 함께 요구**한다. 401이 계속되면 profile을 채운다.

### 4-2. 단계

1. **「서버 등록」** 클릭 → 등록 모달이 열린다.
2. **이름 / 설명 / 엔드포인트** 입력.
   - 엔드포인트에는 Smithery Connect 탭의 base URL을 넣는다. (쿼리스트링 없이)
3. **Transport** 를 `Streamable HTTP` 로 변경.
   - 변경하면 **Profile**, **Server Config** 입력 칸이 추가로 나타난다.
   - API Key 칸에 `*` (필수) 표시가 붙는다.
4. **API Key** 에 Smithery API Key 입력. (password 타입 — 화면에 가려짐)
5. (선택) **Profile** — Smithery에서 프로필을 쓰는 경우 입력.
6. (선택) **Headers** — 추가 헤더가 필요하면 JSON 객체로 입력.
   ```json
   { "X-Custom-Header": "value" }
   ```
7. **Server Config** 에 Naver 자격증명을 JSON 객체로 입력.
   ```json
   {
     "NAVER_CLIENT_ID": "여기에_Client_ID",
     "NAVER_CLIENT_SECRET": "여기에_Client_Secret"
   }
   ```
   > Headers/Server Config는 **JSON 객체**여야 한다. (배열·문자열 불가 → 검증 에러)
8. **「등록」** 클릭.
   - 성공 시 목록 테이블에 새 행이 추가된다.

### 4-3. 연결 테스트

저장된 서버만 연결 테스트가 가능하다.

- **목록 테이블 → 「테스트」 버튼**: 행 단위로 즉시 테스트.
- **수정 모달 하단 → 「연결 테스트」**: 편집 중 테스트.

성공하면 서버가 제공하는 **도구(tool) 목록**과 응답 시간(ms)이 표시된다.
실패하면 에러 메시지가 표시된다. (API Key 오타, Naver 자격증명 누락 등)

---

## 5. 수정 시 주의사항 (시크릿 마스킹)

- 수정 모달을 열면 **시크릿 입력 칸은 비어 있다.** (기존 값은 `****`로 마스킹되어 표시 안 됨)
- **빈 칸으로 두면 기존 시크릿이 그대로 유지**된다.
- 시크릿을 바꾸려는 경우에만 새 값을 입력한다.
- 수정 시에는 API Key 필수 검증이 적용되지 않는다. (기존 값 유지 가능)

---

## 6. 등록 후 동작 (참고)

- 등록된 서버는 내부적으로 `tool_id = "mcp_{uuid}"` 로 식별된다.
- Agent 실행 시 `MCPToolLoader`가 시크릿을 복호화 → URL 조립 → LangChain `BaseTool` 목록으로 로딩한다.
- 따라서 등록·테스트가 성공하면 Agent가 해당 MCP 도구(예: 네이버 검색)를 사용할 수 있다.

---

## 7. 트러블슈팅

| 증상 | 원인 | 조치 |
|------|------|------|
| `Streamable HTTP는 API Key가 필요합니다.` | 신규 등록 시 API Key 미입력 | API Key 입력 |
| `이름·설명·엔드포인트는 필수입니다.` | 필수 칸 누락 | 3개 칸 모두 입력 |
| `Headers은(는) JSON 객체여야 합니다.` | JSON 형식 오류 / 배열·문자열 입력 | `{ ... }` 형태 객체로 수정 |
| 연결 테스트 실패 (인증 오류) | Smithery API Key 오타·만료 | API Key 재확인/재발급 |
| 연결 테스트 실패 (다운스트림 오류) | Naver Client ID/Secret 누락·오류 | Server Config 값 확인, 검색 API 사용 설정 확인 |
| 등록은 되나 연결 안 됨 | 백엔드 `MCP_SECRET_KEY` 미설정 | 백엔드 `.env`에 Fernet 키 설정 후 재시작 |
| `McpError: Session terminated` / 404 | **404를 SDK가 'Session terminated'로 변환**. 주로 (1) 원격이 아닌(`remote:false`) 서버 등록, (2) URL 경로 오류 | `registry.smithery.ai`로 `remote:true` 확인, 게이트웨이 `server.smithery.ai/{ns}/{slug}` 형식 사용 |
| api_key 입력했는데 NULL로 저장됨 | `MCP_SECRET_KEY` 미설정 시 시크릿이 암호화 못 돼 버려짐 (현재는 422로 거부) | `.env`에 유효한 Fernet 키 설정 후 재기동, 재등록 |
| 앱 기동 실패 `Fernet key must be 32 url-safe base64...` | `MCP_SECRET_KEY` 값이 Fernet 형식 아님 | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`로 재생성(44자, 끝 `=`) |
| run.tools URL 넣었는데 404 | 코드가 `/mcp` 자동 부착 → run.tools 베이스엔 `/mcp` 없음 | `server.smithery.ai/{ns}/{slug}` 게이트웨이 형식으로 등록 |

---

## 8. 관련 코드 위치

### 프론트엔드 (`idt_front/`)
| 역할 | 경로 |
|------|------|
| 관리 페이지 | `src/pages/AdminMcpServersPage/index.tsx` |
| 타입 | `src/types/mcpServer.ts` |
| 서비스 | `src/services/mcpServerService.ts` |
| 훅 | `src/hooks/useMcpServers.ts` |
| 엔드포인트 상수 | `src/constants/api.ts` (`MCP_SERVERS`, `MCP_SERVER_DETAIL`, `MCP_SERVER_TEST`) |

### 백엔드 (`idt/`)
| 역할 | 경로 |
|------|------|
| 라우터 | `src/api/routes/mcp_registry_router.py` |
| 요청/응답 스키마 | `src/application/mcp_registry/schemas.py` |
| 도메인 엔티티 | `src/domain/mcp_registry/schemas.py` |
| 검증 정책 | `src/domain/mcp_registry/policies.py` |
| DB 모델 | `src/infrastructure/mcp_registry/models.py` |
| 시크릿 암호화 | `src/infrastructure/security/secret_cipher.py` |
| Smithery URL 빌더 | `src/infrastructure/mcp_registry/smithery_url.py` |
| 도구 로더 | `src/infrastructure/mcp_registry/mcp_tool_loader.py` |
| 연결 테스트 UseCase | `src/application/mcp_registry/mcp_connection_test_use_case.py` |

### API 엔드포인트
| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/v1/mcp-registry` | 등록 |
| GET | `/api/v1/mcp-registry` | 목록 (user_id 필터 선택) |
| GET | `/api/v1/mcp-registry/{id}` | 단건 조회 |
| PUT | `/api/v1/mcp-registry/{id}` | 수정 |
| DELETE | `/api/v1/mcp-registry/{id}` | 삭제 |
| POST | `/api/v1/mcp-registry/{id}/test` | 연결 테스트 |
