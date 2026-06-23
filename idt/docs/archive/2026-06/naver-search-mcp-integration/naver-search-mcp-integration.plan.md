# Naver Search MCP (Smithery) 연동 — Planning Document

> **Summary**: Smithery 호스팅 **Naver Search MCP**(`@jikime/py-mcp-naver-search` 계열, Streamable HTTP transport)를 우리 프로젝트의 `mcp_registry` 흐름으로 등록·로드·호출할 수 있게 만든다. 현재 우리 등록/로더는 **SSE 고정 + 인증·config 주입 경로 부재**라 Smithery 서버(Streamable HTTP + `api_key`/`profile` 쿼리 + `NAVER_CLIENT_ID/SECRET` config)를 그대로 붙일 수 없다. 본 사이클은 ① 선행 모듈 [`mcp-http-call-module`](./mcp-http-call-module.plan.md)이 추가하는 `STREAMABLE_HTTP` transport를 전제로, ② DB/도메인/등록 UseCase/로더에 **transport 선택 + 인증헤더·config 주입**을 확장하고, ③ Naver Search 서버 1종을 **레퍼런스 연동**으로 검증한다.
>
> **Project**: sangplusbot (idt)
> **Version**: 1.0
> **Author**: 배상규
> **Date**: 2026-06-16
> **Status**: Draft
> **Target server**: https://smithery.ai/servers/naver/search (Smithery hosted, Streamable HTTP)
> **Depends on**: `mcp-http-call-module.plan.md` (STREAMABLE_HTTP transport + `MCPCallClient` 코어 선행)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | Smithery의 Naver Search MCP를 우리 플랫폼에서 호출할 수 없다. ① 등록 UseCase가 `MCPTransportType.SSE`로 **하드코딩**(`register_mcp_server_use_case.py:49`)되고 도메인 enum에 SSE만 존재, ② `MCPToolLoader`가 SSE 고정 + **헤더/쿼리 주입 불가**(`mcp_tool_loader.py:32-37`), ③ DB `mcp_server_registry`에 **인증 토큰·config 컬럼이 없음**(`models.py`), ④ Smithery는 `api_key`+`profile` 쿼리와 `NAVER_CLIENT_ID/SECRET` config를 요구하는 **Streamable HTTP** 서버라 현재 경로로는 연결·인증이 모두 불가. |
| **Solution** | (1) `mcp-http-call-module` 사이클이 제공하는 `MCPTransport.STREAMABLE_HTTP`/`MCPCallClient`를 전제로, (2) `mcp_server_registry`에 `transport` 활용 + **`auth_config`/`server_config`(암호화 JSON) 컬럼 추가**(비파괴 마이그레이션), (3) 등록 Request/UseCase/Policy를 transport·인증·config 입력을 받도록 확장, (4) `MCPToolLoader`가 DB의 transport·인증·config를 읽어 Streamable HTTP `MCPServerConfig`를 조립하도록 변경, (5) Naver Search 서버를 시드 등록해 `search_blog`/`search_news` 등 1~2개 tool 호출을 E2E로 검증. |
| **Function/UX Effect** | 사용자는 MCP 등록 API에 Smithery URL·`api_key`·`profile`·Naver 자격증명을 넣어 Naver Search 서버를 등록하면, Agent 대화에서 `mcp_{id}` 도구로 네이버 블로그/뉴스/쇼핑 검색 결과를 받을 수 있다. 인증정보는 응답에서 마스킹되고 로그엔 `request_id`만 남는다. |
| **Core Value** | "SSE 전용·인증 없음" 등록 파이프라인을 **transport 선택 + 시크릿 주입형**으로 일반화하여, Naver Search를 첫 사례로 Smithery 마켓플레이스의 임의 Streamable HTTP MCP를 안전하게 붙일 수 있는 토대를 만든다. |

---

## 1. Overview

### 1.1 Purpose

외부 마켓플레이스(Smithery)에 호스팅된 **Naver Search MCP 서버**를 우리 `mcp_registry` 등록/로드/호출 경로로 연동한다. 이 서버를 첫 레퍼런스로 삼아, 향후 다른 Streamable HTTP MCP도 동일 경로로 붙일 수 있도록 등록 파이프라인을 transport·인증·config 주입형으로 확장한다.

### 1.2 대상 서버 분석 (Smithery Naver Search)

| 항목 | 내용 |
|------|------|
| Transport | **Streamable HTTP** (Smithery는 SSE deprecated, Streamable HTTP 권장) |
| Endpoint 형태 | `https://server.smithery.ai/{qualifiedName}/mcp` (예: `@jikime/py-mcp-naver-search`) |
| 플랫폼 인증 | 쿼리 파라미터 `api_key`(Smithery API Key) + `profile`(Smithery profile) |
| 서버 config | `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` (Naver Developers 발급) — Smithery에 `config`(base64 JSON) 또는 dot-notation 쿼리로 전달 |
| 제공 tool(예시) | 블로그/뉴스/도서/이미지/쇼핑/웹 검색, 페이지네이션·오타교정 등 (실제 목록은 `list_tools()`로 런타임 확정) |

> 정확한 `qualifiedName`·config 키·tool 이름은 Design 단계에서 Smithery 서버 페이지/`list_tools()` 실측으로 고정한다(§9 Open Questions).

### 1.3 현재 상태 (As-Is)

| 위치 | 현재 | 한계 |
|------|------|------|
| `domain/mcp_registry/schemas.py:7-9` | `MCPTransportType`에 **`SSE`만** 존재 | Streamable HTTP 선택 불가 |
| `application/.../register_mcp_server_use_case.py:49` | `transport=MCPTransportType.SSE` **하드코딩** | 등록 시 transport 지정 불가 |
| `application/mcp_registry/schemas.py:7-14` | Request에 `endpoint`만, **인증/config 필드 없음** | api_key/profile/Naver 키 주입 불가 |
| `infrastructure/mcp_registry/models.py` | 컬럼: transport(default sse)/input_schema. **auth·config 없음** | 시크릿 저장 위치 없음 |
| `infrastructure/mcp_registry/mcp_tool_loader.py:32-37` | `MCPTransport.SSE` + `SSEServerConfig(url=...)` 고정, **headers 미전달** | Streamable HTTP·인증헤더 조립 불가 |
| `domain/mcp/value_objects.py:12-17` | `MCPTransport`에 **STREAMABLE_HTTP 없음** | (선행 모듈에서 추가 예정) |

### 1.4 선행 의존성

본 사이클은 별도 PDCA [`mcp-http-call-module.plan.md`](./mcp-http-call-module.plan.md)가 다음을 제공한다고 **전제**한다:
- `MCPTransport.STREAMABLE_HTTP` + `StreamableHTTPServerConfig`(url/headers/타임아웃)
- `MCPClientFactory`의 streamable HTTP 세션 생성 + 헤더/타임아웃 주입
- (선택) `MCPCallClient` 순수 호출 코어

선행 모듈이 아직 미완이면 본 사이클 M1을 **그 일부(transport+factory)만 우선 흡수**하는 것으로 축소 가능(§7 Risks).

---

## 2. Scope

### 2.1 In Scope (이번 사이클)

- `domain/mcp_registry`: `MCPTransportType`에 `STREAMABLE_HTTP` 추가, `MCPServerRegistration`에 `auth_config`/`server_config`(선택 dict) 필드 + 마스킹 규칙.
- DB: `mcp_server_registry`에 **비파괴 컬럼 추가**(`auth_config` JSON, `server_config` JSON) + Flyway 마이그레이션 파일.
- `application/mcp_registry`: `RegisterMCPServerRequest`/`UpdateMCPServerRequest`에 `transport`·`auth_config`·`server_config` 추가, UseCase가 transport 선택·시크릿 저장, **Response는 시크릿 마스킹**.
- `domain/mcp_registry/policies`: transport 화이트리스트 검증, Smithery URL/필수 인증 필드 검증.
- `infrastructure/mcp_registry/mcp_tool_loader.py`: DB transport·auth·config를 읽어 **Streamable HTTP `MCPServerConfig`**(헤더/쿼리 포함) 조립.
- 시드/문서: Naver Search 서버 등록 예시(`gen-seed` 또는 등록 API 호출 가이드) + `.env` 키 정의.
- 위 전부 pytest(TDD Red→Green) — Smithery 실호출은 mock, 1건만 옵트인 E2E(수동).

### 2.2 Out of Scope (후속 분리)

- 선행 `MCPCallClient` 호출 코어 자체의 설계/구현(별도 PDCA).
- `ToolFactory`/`WorkflowCompiler`의 도구 라우팅 구조 변경(기존 `mcp_` 경로 그대로 사용).
- 프론트엔드 MCP 등록 UI(별도 풀스택 사이클 — `/api-contract-sync` 후속).
- 다중 Naver tool 전부 검증 — 본 사이클은 대표 1~2개만.
- 시크릿 KMS/Vault 연동(이번엔 앱 레벨 암호화 또는 `.env` 참조 키 저장까지).

### 2.3 비파괴 원칙 (Non-breaking)

- 기존 SSE 등록/로드 동작·시그니처 보존. `transport` 미지정 시 기본 `SSE` 유지.
- DB는 **nullable 컬럼 추가만** — 기존 행/쿼리 무영향.
- `RegisterMCPServerRequest` 신규 필드는 모두 `Optional` 기본값 → 기존 호출자 무수정 통과.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | 요구사항 | 수용 기준(요약) |
|----|----------|----------------|
| FR-1 | `MCPTransportType.STREAMABLE_HTTP` 추가 + 등록 시 transport 선택 | `transport="streamable_http"`로 등록·조회 왕복 성공 |
| FR-2 | 등록 Request에 `auth_config`(api_key/profile/headers)·`server_config`(Naver 키 등) 수용 | 등록 API가 해당 필드 저장, 422 없이 통과 |
| FR-3 | DB `mcp_server_registry`에 `auth_config`/`server_config` 컬럼 추가 | 마이그레이션 적용 후 기존 행 정상 + 신규 필드 저장/조회 |
| FR-4 | Response에서 시크릿 **마스킹** | `auth_config`/`server_config` 값이 `****` 또는 키만 노출 |
| FR-5 | `MCPToolLoader`가 Streamable HTTP `MCPServerConfig` 조립 | transport=streamable_http일 때 url+헤더(api_key/profile/Authorization) 반영 |
| FR-6 | Naver Search 서버 등록→tool 로드→호출 E2E | mock 세션에서 `search_*` tool 호출 결과 텍스트 반환 |
| FR-7 | 등록 Policy: transport 화이트리스트·필수 인증필드 검증 | 누락/비허용 transport 시 명확한 422 |

### 3.2 Non-Functional Requirements

| ID | 요구사항 |
|----|----------|
| NFR-1 (Arch) | DDD 준수: domain은 외부 의존 0, loader/repository는 infrastructure. LangChain은 infra에서만. `verify-architecture` 통과 |
| NFR-2 (Security) | 시크릿 평문 로그 금지, Response 마스킹, 저장 시 앱 레벨 암호화(또는 env 참조키). 시크릿은 vector/대화 DB 저장 금지 |
| NFR-3 (Log) | LOG-001: 모든 등록/로드에 `request_id` 포함, 실패 시 스택 트레이스. `verify-logging` 통과 |
| NFR-4 (TDD) | 구현 전 테스트, Smithery 네트워크 비의존(mock). `verify-tdd` 통과 |
| NFR-5 (Config) | Smithery api_key·Naver 키 하드코딩 금지 — `.env`/`src/config`. (CLAUDE.md §3) |
| NFR-6 (Contract) | DB 스키마/Request 변경 시 `db-migration`·`api-contract` 스킬로 동기화 |

---

## 4. 제안 변경 구조 (High-level, 상세는 Design)

```
domain/mcp_registry/
  schemas.py        (~) MCPTransportType += STREAMABLE_HTTP
                    (~) MCPServerRegistration += auth_config / server_config (Optional dict)
                    (+) 시크릿 마스킹 헬퍼
  policies.py       (~) validate_transport(), validate_auth(transport, auth_config)

application/mcp_registry/
  schemas.py        (~) RegisterMCPServerRequest += transport / auth_config / server_config
                    (~) to_response(): 시크릿 마스킹 적용
  register_mcp_server_use_case.py  (~) 하드코딩 SSE 제거 → request.transport 사용

infrastructure/mcp_registry/
  models.py         (~) auth_config: JSON nullable, server_config: JSON nullable
  mcp_tool_loader.py(~) transport 분기 → STREAMABLE_HTTP: StreamableHTTPServerConfig
                        (url + api_key/profile 쿼리 + Authorization 헤더 + Naver config)
  db/migration/     (+) V0xx__alter_mcp_server_registry_add_auth_config.sql

domain/mcp/ + infrastructure/mcp/   ← 선행 모듈(mcp-http-call-module)이 제공
                    STREAMABLE_HTTP transport, StreamableHTTPServerConfig, factory 세션
```

> Smithery URL 조립 규칙(`/mcp` 경로 + `api_key`/`profile` 쿼리 + `config` base64 vs dot-notation)은 Design에서 실측 후 단일 헬퍼로 고정한다.

---

## 5. Test Strategy (TDD 개요)

- **도메인 단위**: `MCPTransportType` 확장, `validate_transport`/`validate_auth` 분기, 마스킹 헬퍼(시크릿 값 비노출), `MCPServerRegistration` 신규 필드 기본값.
- **application 단위**: 등록 UseCase가 transport·auth·config를 저장하고 SSE 하드코딩이 사라졌는지, `to_response` 마스킹.
- **infrastructure 단위**: `MCPToolLoader`가 transport별로 올바른 `MCPServerConfig`(SSE vs StreamableHTTP, 헤더/쿼리 포함)를 조립하는지 — `MCPClientFactory.create_session`/`get_tools` patch로 검증.
- **마이그레이션**: 기존 행 보존 + 신규 컬럼 nullable 확인(`db-migration` 산출물 리뷰).
- **E2E(옵트인)**: 실제 Smithery Naver Search 1콜은 `@pytest.mark.e2e`로 분리, 기본 CI 제외.
- **Windows 주의**: 교차 실행 이벤트 루프 teardown flakiness 알려짐 → 본 모듈 비동기 테스트는 **격리 실행**으로 회귀 판정(메모리 `backend-test-eventloop-flakiness`).

---

## 6. Milestones

| # | 단계 | 산출물 |
|---|------|--------|
| M0 | 선행 확인 | `mcp-http-call-module`의 STREAMABLE_HTTP/factory 가용 여부 점검(없으면 최소 흡수) |
| M1 | 도메인·정책 | `MCPTransportType` 확장 + auth/config 필드 + 마스킹 + 정책 테스트 |
| M2 | DB·마이그레이션 | `models.py` 컬럼 추가 + Flyway 마이그레이션(`db-migration`) |
| M3 | 등록 파이프라인 | Request/UseCase/Response 확장 + `api-contract` 동기화 + 테스트 |
| M4 | 로더 | `MCPToolLoader` Streamable HTTP 조립 + 헤더/쿼리 주입 + 테스트 |
| M5 | Naver 연동 검증 | 시드 등록 + tool 로드/호출(mock) + 옵트인 E2E + `/pdca analyze` |

---

## 7. Risks & Mitigations

| 리스크 | 영향 | 완화 |
|--------|------|------|
| 선행 `mcp-http-call-module` 미완 | M1~M4 블로킹 | M0에서 점검, 미완 시 transport+factory만 본 사이클로 최소 흡수 후 추후 통합 |
| Smithery URL/config 전달 규칙(base64 vs dot-notation) 가정 오류 | 로더 재작업 | Design에서 Smithery 서버 페이지+실 `list_tools()`로 실측 고정 |
| 시크릿(Naver/Smithery 키) 저장·노출 | 보안 사고 | 앱 레벨 암호화 또는 env 참조키, Response 마스킹, 로그 금지(NFR-2) |
| Naver Developers API 자격증명 미보유 | E2E 불가 | E2E 옵트인 분리, 기본은 mock으로 그린 판정 |
| SSE→Streamable HTTP 혼재로 기존 등록 영향 | 회귀 | transport 기본값 SSE 유지, nullable 컬럼, 기존 테스트 보존 |
| 재시도/타임아웃이 비멱등 검색에 영향 | 중복 호출 | 검색은 멱등에 가깝지만 재시도는 연결단계 한정(선행 모듈 정책 준수) |

---

## 8. 영향 범위 / 후속 작업

- **이번 사이클 변경(예상)**: `domain/mcp_registry/{schemas,policies}.py`, `application/mcp_registry/{schemas,register_mcp_server_use_case,update_mcp_server_use_case}.py`, `infrastructure/mcp_registry/{models,mcp_tool_loader}.py`, `db/migration/V0xx__*.sql`, 대응 `tests/`, `.env` 키.
- **계약 동기화**: 등록 Request/Response 변경 → 프론트 `idt_front/src/types`·`services`(`/api-contract-sync`)는 후속 UI 사이클에서.
- **후속(별도 PDCA)**: ① MCP 등록/실행 프론트 UI, ② 시크릿 KMS/Vault 이관, ③ 다중 Naver tool 전수 검증·캐싱, ④ `MCPToolAdapter`를 `MCPCallClient` 소비로 리팩토링.

---

## 9. Open Questions (Design 단계에서 확정)

1. Naver Search 서버 `qualifiedName` 확정(`@jikime/py-mcp-naver-search` vs `@isnow890/naver-search-mcp`)과 노출 tool 이름.
2. Smithery config 전달 방식: URL `config` base64 JSON vs dot-notation 쿼리 vs 헤더 — 실측 후 단일 규칙.
3. 시크릿 저장 전략: 앱 레벨 대칭암호화 vs `.env` 참조키(`server_config`엔 키 이름만) 중 택1.
4. `auth_config`/`server_config`를 별도 2컬럼으로 둘지, 단일 `config` JSON 하나로 합칠지.
5. transport 기본값/마이그레이션 시 기존 행 `transport` 백필 정책(현 default "sse" 유지로 충분한지).
