# register-naver-search-mcp Plan Document

> **Feature**: register-naver-search-mcp
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규
> **Date**: 2026-06-18
> **Status**: Plan
> **Type**: 운영 등록 절차(Operational Runbook) — 신규 기능 개발 아님

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | Smithery 호스팅 Naver Search MCP(`https://smithery.ai/servers/naver/search`)를 우리 플랫폼 도구로 쓰려면 `/admin/mcp-servers`에서 어떤 transport·인증·config로 등록해야 하는지 절차가 정리돼 있지 않다. |
| **Solution** | 이미 완성된 두 기능(`naver-search-mcp-integration` 백엔드 + `mcp-registry-admin-ui` 관리 화면)을 그대로 사용해, **transport=Streamable HTTP** + **플랫폼 인증(api_key/profile)** + **다운스트림 server_config(NAVER_CLIENT_ID/SECRET)** 를 입력해 등록하고 **연결 테스트** 버튼으로 검증한다. |
| **Function/UX Effect** | 운영자가 GUI 폼에서 값만 채우면 등록 즉시 `list_tools`로 연결을 검증하고, 시크릿은 Fernet 암호화 저장 + 응답 마스킹(`****`)으로 안전하게 관리된다. |
| **Core Value** | 개발자 개입·코드 변경 없이 비개발 운영자가 Naver Search MCP를 self-service로 붙이고, 등록 시점에 연결 오류를 사전 차단한다. |

---

## 1. 현황 (이미 구축 완료)

| 영역 | 상태 | 근거 |
|------|------|------|
| Streamable HTTP transport 등록 파이프라인 | ✅ 완료 | `naver-search-mcp-integration` (100% match, 90 tests) |
| 시크릿 암호화/마스킹 (Fernet) | ✅ 완료 | `src/infrastructure/security/secret_cipher.py`, `MCP_SECRET_KEY` |
| Smithery URL 빌더 (`/mcp` + api_key/profile/base64 config) | ✅ 완료 | `src/infrastructure/mcp_registry/smithery_url.py` |
| `/admin/mcp-servers` 관리 화면 (CRUD + 동적 폼 + 연결 테스트) | ✅ 완료 | `mcp-registry-admin-ui` (100% match, 41 tests) |
| DB 컬럼 `auth_config_enc`/`server_config_enc` | ✅ 마이그레이션 | `db/migration/V032__alter_mcp_server_registry_add_secrets.sql` |

> **결론**: 코드 작업 불필요. **선행 설정 + 등록 입력값**만 갖추면 된다.

---

## 2. 사전 준비물 (등록 전 필수)

| # | 항목 | 획득처 | 비고 |
|---|------|--------|------|
| P1 | **Smithery api_key** | smithery.ai 계정 → API Keys | streamable_http 필수 (`MCPRegistrationPolicy.validate_auth`) |
| P2 | **Smithery profile** | smithery.ai 계정 프로필 식별자 | 선택(서버에 따라 필요) |
| P3 | **NAVER_CLIENT_ID / NAVER_CLIENT_SECRET** | developers.naver.com → 애플리케이션 등록(검색 API) | server_config로 다운스트림 전달 |
| P4 | **정확한 Smithery endpoint** | `https://smithery.ai/servers/naver/search` 의 "Connect/Streamable HTTP" URL | qualifiedName 실측 확정 필요(아래 §5 Open Q1) |
| P5 | **서버 `.env`의 `MCP_SECRET_KEY` 설정** | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | **빈 값이면 시크릿 암호화 비활성→등록 불가** (`config.py:100`, `main.py:341`) |

---

## 3. 등록 절차 (`/admin/mcp-servers`)

1. **선행**: 서버 `.env`에 `MCP_SECRET_KEY` 채우고 백엔드 재기동. V032 마이그레이션 적용 확인.
2. 관리자 계정으로 로그인 → 사이드바 **"MCP 서버"** → `/admin/mcp-servers` 진입.
3. **[등록]** 버튼 → 폼에서 transport를 **Streamable HTTP**로 선택 (동적 필드가 펼쳐짐).
4. 아래 값 입력:

| 폼 필드 | 입력 값(예시) |
|---------|--------------|
| name | `Naver Search` |
| description | `네이버 블로그/뉴스/쇼핑 검색 MCP (Smithery)` |
| endpoint | `https://server.smithery.ai/@isnow890/naver-search-mcp/mcp` *(§5 Open Q1 실측 확정)* |
| transport | `Streamable HTTP` |
| api_key *(필수)* | `<Smithery api_key>` |
| profile | `<Smithery profile>` |
| server_config | `NAVER_CLIENT_ID=<id>`, `NAVER_CLIENT_SECRET=<secret>` (KV/JSON) |

5. **[연결 테스트]** → `POST /api/v1/mcp-registry/{id}/test` 가 `list_tools`를 호출 → `ok:true` + 도구 목록(naver_blog_search 등) 확인.
6. 저장. 응답의 시크릿은 `****`로 마스킹되어 표시됨(정상).

> **참고 — 동등한 API 직접 등록(POST `/api/v1/mcp-registry`)**:
> ```json
> {
>   "user_id": "<admin-user-id>",
>   "name": "Naver Search",
>   "description": "네이버 검색 MCP (Smithery)",
>   "endpoint": "https://server.smithery.ai/@isnow890/naver-search-mcp/mcp",
>   "transport": "streamable_http",
>   "auth_config": { "api_key": "smithery_xxx", "profile": "my-profile" },
>   "server_config": { "NAVER_CLIENT_ID": "xxx", "NAVER_CLIENT_SECRET": "yyy" }
> }
> ```
> 빌더가 자동으로 `endpoint` 끝을 `/mcp`로 보정하고, `api_key`/`profile`을 쿼리로, `server_config`를 base64 JSON `config` 쿼리로 조립한다(`smithery_url.build_streamable_http`).

---

## 4. 검증 (Acceptance Criteria)

- [ ] AC1: `MCP_SECRET_KEY` 설정 상태에서 streamable_http 등록이 201로 성공한다.
- [ ] AC2: 연결 테스트가 `ok:true` 와 Naver 검색 도구 목록을 반환한다.
- [ ] AC3: 목록/상세 응답에서 `auth_config`·`server_config` 값이 `****`로 마스킹된다.
- [ ] AC4: 등록된 도구가 Agent 실행 시 `tool_id="mcp_{id}"`로 로드·호출된다.
- [ ] AC5: api_key 누락 시 422(`Invalid auth_config: api_key required for streamable_http`).

---

## 5. Risk & Open Questions

| # | 항목 | 영향 | 대응 |
|---|------|------|------|
| Open Q1 | 정확한 Smithery **qualifiedName/endpoint** (`@isnow890/naver-search-mcp` vs `naver/search` 공식 vs `@jikime/py-mcp-naver-search`) | 연결 실패 | Smithery 페이지의 Streamable HTTP Connect URL 실측 후 endpoint 확정 |
| Open Q2 | server_config 전달 방식(base64 `config` 쿼리 vs dot-notation) | 일부 서버 호환성 | 현재 base64 JSON 우선. 실패 시 `smithery_url.py` 단일 지점에서 폴백 추가 |
| R1 | 백엔드 `/admin` RBAC 미적용 (프론트 AdminRoute만) | 비인가 API 호출 가능 | `mcp_registry_router`에 admin 가드 추가(후속, ~2h) — `mcp-registry-admin-ui.report.md` R1 |
| R2 | `MCP_SECRET_KEY` 미설정 채로 등록 시도 | 시크릿 저장 불가/오류 | 등록 전 .env 확인을 절차 1단계로 강제(§3) |
| R3 | Naver Developers 키 일일 호출 한도 | 런타임 검색 실패 | 운영 모니터링, 결과는 tool `is_error`로 격리 |

---

## 6. Out of Scope

- 신규 코드/스키마 변경(이미 완료된 두 기능 재사용).
- 저장 전(server ID 없는) config 테스트 — `mcp-registry-admin-ui` Design §8.4 후속.
- KMS/Vault 시크릿 이관 — 후속.

---

## 7. Next Step

1. §2 사전 준비물(P1~P5) 확보 — 특히 **Open Q1 endpoint 실측**, **MCP_SECRET_KEY 설정**.
2. §3 절차대로 `/admin/mcp-servers`에서 등록 → 연결 테스트.
3. 필요 시 `/pdca design register-naver-search-mcp` 없이 바로 운영 적용 가능(개발 없음). RBAC 가드(R1)만 별도 백엔드 스프린트 권장.
