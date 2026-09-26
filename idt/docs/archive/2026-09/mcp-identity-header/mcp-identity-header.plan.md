# mcp-identity-header Planning Document

> **Summary**: MCP 호출마다 실행 주체의 신원(메일함 UPN 등)을 HS256 서명 토큰 헤더로 주입해, 하나의 MCP 서버가 사용자별 자원(개인 메일함)을 안전하게 다루게 한다
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규 / Claude
> **Date**: 2026-09-26
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | Outlook Mail MCP는 사용자별 메일함을 지원(identity 모드)하지만, idt는 등록 시 고정한 정적 헤더만 보낼 수 있어 공용 메일함 1개(fixed 모드)로만 운영 가능하다. 메일함을 도구 인자로 넘기면 LLM·메일 본문 속 지시문이 타인 메일함을 고를 수 있다. |
| **Solution** | 관리자가 회원별 메일함 UPN을 등록하고, 신원 헤더가 켜진 MCP 서버를 호출할 때마다 idt가 실행 주체 기준으로 단수명 HS256 토큰을 발급해 `X-MCP-Identity` 헤더에 싣는다. 메일 전용 노드가 아니라 **MCP 호출 계층의 공통 기능**이다. |
| **Function/UX Effect** | 에이전트 소유자는 도구를 고르기만 하면 되고, 사용자는 "내 메일 보여줘"로 본인 메일함만 조회한다. 관리자 화면에서 메일함·서버 신원 설정을 DB/Swagger 없이 완료한다. |
| **Core Value** | 메일함 결정권을 LLM·사용자 편집값에서 플랫폼 인증 경로로 옮겨 "타인 메일함 접근 불가"를 코드 구조로 보장한다. 다른 사용자별 MCP(캘린더·고객문의 등)도 같은 설정으로 재사용한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 공용 MCP 서버 하나가 여러 사용자의 개인 자원을 다루려면 "누구의 자원인가"를 LLM이 아닌 플랫폼이 호출마다 보증해야 한다 |
| **WHO** | P2(에이전트 소유자): 메일 에이전트 구성 / 관리자: 회원 메일함·서버 신원 설정 / 최종 사용자: 본인 메일 조회·발송 |
| **RISK** | MCP 호출 경로 누락(한 곳이라도 헤더 없이 나가면 서버 거부 또는 설정 오류로 타인 메일함) · 5분 토큰이 로드 시점에 고정되어 긴 실행에서 만료 |
| **SUCCESS** | 서로 다른 두 사용자가 같은 에이전트로 `list_messages` 호출 시 각자 메일함 결과 / 메일함 미등록 사용자는 호출 전 idt가 명확한 오류로 거부 / 신원 미설정 서버는 기존과 바이트 동일 동작 |
| **SCOPE** | M1 도메인·스키마(users 컬럼, 등록 신원 설정) → M2 토큰 발급·호출 시점 주입(전 MCP 호출 경로) → M3 관리자 API → M4 관리자 화면 |

---

## 1. Overview

### 1.1 Purpose

MCP 서버 등록 단위로 "이 서버는 호출자 신원이 필요하다"를 설정할 수 있게 하고, 해당 서버로 나가는 **모든** tool 호출에 실행 주체의 신원 토큰을 idt가 발급·주입한다. 첫 소비자는 `mcp-outlook-server`(identity 모드)다.

### 1.2 Background

- **서버 쪽은 준비 완료.** `agent_mcp/mcp-outlook-server`는 `OUTLOOK_MAILBOX_RESOLVER=identity`에서 `X-MCP-Identity` 헤더의 HS256 JWT를 `mcp_shared.auth.HmacTokenVerifier`로 검증하고, 클레임의 UPN으로만 Graph를 호출한다. 헤더 없음/위조는 거부하며 고정 메일함으로 폴백하지 않는다. 계약: `agent_mcp/docs/02-design/features/mcp-outlook-server.identity-contract.md`.
- **idt는 정적 헤더만 지원.** `smithery_url.build_streamable_http`가 `auth_config.headers`를 등록 시점 값 그대로 싣고, SSE는 헤더를 아예 싣지 않는다(`MCPToolLoader._build_config`). 헤더는 도구 로드 시점의 `MCPServerConfig`에 고정되고 `MCPToolAdapter._arun`이 호출마다 그 설정으로 세션을 연다.
- **실행 주체는 전 경로에서 식별 가능**(조사 결과):

  | 경로 | 실행 주체 | 인증 컨텍스트 |
  |---|---|---|
  | 대화 실행 | 로그인 사용자 | 있음 |
  | 스케줄 (`trigger_due_schedules_use_case`) | 스케줄 생성자(=에이전트 소유자) | **없음** — `RunAgentRequest.user_id`만 |
  | 백그라운드 작업 (`background_job/worker`) | 제출자 | 있음 |
  | 웹훅 (`invoke_webhook_agent_use_case`) | 에이전트 소유자 대리 | 있음(소유자) |
  | 승인 후 집행 (`approval/mcp_executor`) | `requested_by` (요청자, 승인자 아님) | 없음 — 저장된 ID |

  → 신원 소스는 **인증 컨텍스트가 아니라 실행 요청의 사용자 ID**로 통일한다.
- **메일 전용 노드를 만들지 않는 이유**: MCP 도구는 워커·미들웨어 에이전트·승인 집행기 등 여러 경로에서 호출되므로 노드 하나로는 "무조건"을 보장할 수 없고, USER-SCENARIOS "일반화가 이긴다" 원칙상 코어에 Outlook을 하드코딩하지 않는다.

### 1.3 Related Documents

- 서버 계약: `agent_mcp/docs/02-design/features/mcp-outlook-server.identity-contract.md` (§2 헤더, §3 토큰, §7 열린 항목)
- 서버 구현: `agent_mcp/mcp-outlook-server/CLAUDE.md` (identity 모드)
- 선행: `docs/01-plan/features/approval-gate-phase2-mcp-executor.plan.md` (MCP 집행기, `requested_by`)
- 규칙: `docs/rules/tool-and-mcp.md` §3, `docs/rules/db-session.md`, `docs/rules/logging.md`
- 위키: `docs/wiki/backend/patterns/mcp-runtime-tool-shape.md`, `docs/wiki/frontend/screens/admin-screens.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] **M1 데이터·도메인**: `users.mailbox_upn` 컬럼(Flyway V076, COMMENT 필수) · User 엔티티 반영 · MCP 등록 신원 설정(헤더명·클레임명·audience·issuer·비밀) 도메인 모델과 검증 정책
- [ ] **M2 런타임 주입**: 호출 시점 토큰 발급기(HS256, `python-jose`) · 전 MCP tool 호출 경로에 실행 주체 전달 · 신원 필요 서버인데 주체/메일함이 없으면 호출 전 거부
- [ ] **M3 관리자 API**: 회원 메일함 조회·수정 · MCP 서버 등록/수정 요청·응답에 신원 설정(비밀은 마스킹)
- [ ] **M4 관리자 화면**: `AdminUsersPage` 메일함 입력 · `AdminMcpServersPage` 신원 헤더 설정 · 프론트 타입·서비스 동기화

### 2.2 Out of Scope

- **Outlook MCP 서버 수정·배포** (`agent_mcp` 저장소). 단, identity 모드 전환 절차는 Design에 운영 체크리스트로 기록 (§5 R-4)
- **Entra SSO 연동 / 메일함 자동 동기화** — 관리자 수동 입력으로 시작 (계약 §7-3의 결정: 사용자 레코드 기반)
- **비밀 무중단 회전** (계약 §7-2) — 회전 시 서버 재기동 전제
- **범용 사용자 속성 테이블** — 클레임 소스는 `users` 컬럼 고정 집합(`mailbox_upn`, `email`)
- **list_tools/도구 동기화/연결 테스트에 신원 주입** — 서버가 도구 목록 조회에는 신원을 요구하지 않음. 필요해지면 별도 항목
- **승인 화면에 대상 메일함 표시** — approval-gate-phase2 R-5와 동일하게 보류

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `users`에 nullable `mailbox_upn` 컬럼을 추가한다. 이메일 형식 검증, 소문자 정규화. 로그인 `email`과 독립 | High | Pending |
| FR-02 | 관리자는 회원별 `mailbox_upn`을 조회·설정·해제할 수 있다 (`require_role("admin")`) | High | Pending |
| FR-03 | MCP 서버 등록에 선택적 신원 설정을 둔다: 헤더명(기본 `X-MCP-Identity`), 클레임명(기본 `preferred_username`), 클레임 소스(`mailbox_upn`\|`email`), audience, issuer(기본 `agent-builder`), 서명 비밀(32자 이상) | High | Pending |
| FR-04 | 서명 비밀은 기존 `auth_config`와 같은 암호화 저장 경계(`SecretCipher`)를 거치고, 응답·로그에서는 마스킹한다 | High | Pending |
| FR-05 | 신원 설정이 있는 서버로 나가는 **모든 tool 호출**에 호출 직전 새 토큰을 발급해 헤더에 싣는다 (캐시 금지). 클레임: iss·aud·sub(플랫폼 사용자 ID)·iat·exp(≤ iat+300)·{클레임명}={클레임 소스 값} | High | Pending |
| FR-06 | 실행 주체는 실행 요청의 사용자 ID로 결정한다. 대화·스케줄·백그라운드·웹훅(소유자 대리)·승인 후 집행(`requested_by`) 전 경로 동일 | High | Pending |
| FR-07 | 신원 필요 서버 호출 시 주체 ID가 없거나, 해당 사용자의 클레임 소스 값이 비었거나, 비활성 사용자면 **MCP 서버로 요청을 보내지 않고** 사용자에게 읽히는 오류를 도구 결과로 반환한다 (예: "메일함이 등록되지 않았습니다. 관리자에게 요청하세요") | High | Pending |
| FR-08 | 신원 설정이 없는 서버는 기존 동작과 동일하다 (헤더·URL·세션 수 변화 없음) | High | Pending |
| FR-09 | 헤더는 SSE·Streamable HTTP 두 transport 모두에 실린다 (현재 SSE는 헤더 미전달) | High | Pending |
| FR-10 | 로그에는 토큰 값을 남기지 않는다. 발급 사실·서버 ID·sub·클레임 소스 종류만 기록 | Medium | Pending |
| FR-11 | 관리자 화면: 회원 목록/상세에서 메일함 입력·저장, MCP 서버 폼에서 신원 헤더 on/off와 설정 입력 (비밀은 입력 전용, 조회 시 마스킹) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Security | 메일함 값의 출처는 오직 `users` 레코드. LLM 인자·등록 정적 헤더·요청 본문으로 덮을 수 없다 | 단위 테스트: 도구 인자·정적 헤더에 같은 이름 헤더를 넣어도 발급 토큰이 우선 |
| Security | 토큰 수명 ≤ 300s, `alg`=HS256 고정 | 발급기 단위 테스트 + Outlook 서버 검증기로 교차 검증 |
| Performance | 호출당 추가 비용은 사용자 조회 1회 + HMAC 서명. 한 실행 내 사용자 조회는 캐시 가능(토큰은 캐시 금지) | 로그 타이밍 비교 |
| Compatibility | 기존 MCP 서버 7종 회귀 없음 | 기존 MCP 관련 테스트 + `/verify-mcp-connections` |
| Architecture | domain은 jose·DB 미참조, 토큰 서명은 infrastructure | `/verify-architecture` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] SC-1: 서로 다른 메일함을 가진 두 사용자가 같은 에이전트로 `list_messages`를 호출하면 각자의 메일함 결과를 받는다 (identity 모드 Outlook 서버 실런)
- [ ] SC-2: 메일함 미등록 사용자의 호출은 MCP 서버에 요청이 도달하지 않고 안내 메시지로 끝난다 (서버 로그에 `identity.rejected` 없음)
- [ ] SC-3: 스케줄 실행과 승인 후 `send_mail` 집행이 각각 스케줄 생성자·요청자의 메일함으로 나간다
- [ ] SC-4: 신원 미설정 MCP 서버(Scrap·Rate 등) 호출 결과·헤더가 변경 전과 동일하다
- [ ] SC-5: 관리자가 화면만으로 메일함 등록과 서버 신원 설정을 완료한다 (DB/Swagger 조작 0회)
- [ ] SC-6: 등록 조회 응답·로그 어디에도 서명 비밀과 토큰 원문이 나오지 않는다

### 4.2 Quality Criteria

- [ ] 신규 코드 TDD (Red → Green), 백엔드 pytest·프론트 Vitest+MSW
- [ ] master 상시 실패 목록 외 신규 실패 0건
- [ ] `/verify-architecture`, `/verify-logging`, `tests/db/test_migration_ddl_comments.py` 통과
- [ ] Gap 분석 Match Rate ≥ 90%

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| R-1 MCP 호출 경로 누락 — 한 경로라도 주체 없이 호출되면 서버 거부(가용성) | High | Medium | Design에서 호출 경로 전수 목록(워커 `create_all_async`·미들웨어 `create_async`·승인 `mcp_executor`·문서변환 어댑터)을 표로 박제하고 경로별 테스트. 신원 필요 서버인데 주체 누락 시 "배선 오류" 로그로 즉시 식별 |
| R-2 토큰이 로드 시점에 고정되어 5분 초과 실행에서 만료 | High | High | 헤더를 `MCPServerConfig` 정적 값이 아니라 **호출 시점 헤더 공급자**로 전달 (`MCPToolAdapter._arun`, `MCPCallClient` 세션 생성 직전 발급) |
| R-3 승인 대기 후 집행 시 요청자가 비활성화·메일함 변경 | Medium | Low | 집행 시점의 `users` 값으로 발급(승인 시점 스냅샷 아님). 비활성 사용자는 FR-07로 거부 |
| R-4 Outlook 서버 설정 불일치 — 현재 compose의 `MCP_IDENTITY_AUDIENCE`가 메일 주소로 들어가 있고 resolver가 `fixed` | High | High | Design 부록에 서버 전환 체크리스트(resolver=identity, audience=`mcp-outlook-server`, 비밀 32자+, 동일 비밀을 idt 등록에 입력). 연결 후 SC-1로 검증 |
| R-5 웹훅이 외부 시스템 입력으로 소유자 메일함을 읽음 | Medium | Medium | 결정 사항(전 경로 허용)으로 수용. 발송·답장은 기존 승인 게이트(`requires_approval=1`)가 차단. 사용자 가이드에 명시 |
| R-6 동일 이름 헤더가 정적 `auth_config.headers`에도 있으면 충돌 | Low | Low | 발급 헤더가 항상 우선. 등록 검증에서 정적 헤더와 신원 헤더명 중복 시 400 |
| R-7 users 컬럼 추가가 인증/회원 API 응답에 파급 | Medium | Low | nullable 추가, 기존 응답 스키마는 선택 필드만 추가 (§6 전수 확인) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `users` | DB | `mailbox_upn VARCHAR(255) NULL` 추가 (V076, COMMENT) |
| `User` 엔티티 / `UserModel` | Domain / ORM | 필드 추가 |
| `mcp_server_registry.auth_config_enc` | DB (암호화 JSON) | 신원 설정 하위 키 추가 가능 (스키마 변경 여부는 Design에서 결정: 기존 암호화 JSON 재사용 vs 전용 컬럼) |
| `MCPServerRegistration` | Domain | 신원 설정 접근자 + 검증 정책 |
| `MCPToolLoader` / `MCPToolAdapter` / `MCPCallClient` / `MCPClientFactory` | Infra | 호출 시점 헤더 공급자 수용, SSE 헤더 전달 |
| `ToolFactory.create_all_async` / `create_async` | Infra | 실행 주체 ID 인자 추가 |
| `WorkflowCompiler.compile` 이하 | Application | 실행 주체 ID 전달 |
| `approval/mcp_executor` | Infra | `requested_by`로 주체 전달 |
| 관리자 회원 API / MCP 레지스트리 API | API | 요청·응답 스키마 필드 추가, 회원 메일함 수정 엔드포인트 신설 |
| `AdminUsersPage` / `AdminMcpServersPage` / `adminService` / `mcpServerService` / `src/types` | Frontend | 입력 UI·타입 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `users` | READ | 로그인·JWT 발급 (`auth_router`, `jwt_adapter`) | None — 신규 nullable 컬럼 |
| `users` | READ | `admin_user_router` 목록 | Needs verification — 응답에 필드 추가 |
| `users` | CREATE | `admin_user_router` 생성 | None — 선택 입력 |
| `MCPServerRegistration.auth_config` | READ | `smithery_url.build_streamable_http` (Naver Search) | Needs verification — 신원 키가 쿼리/헤더로 새지 않아야 함 |
| `MCPServerRegistration` | READ | `mcp_connection_test_use_case`, `SyncMcpToolsUseCase` | None — list_tools는 신원 미주입 (Out of Scope) |
| MCP 호출 | EXECUTE | `workflow_compiler.py:782` `create_all_async` | Breaking 가능 — 인자 추가 (기본값으로 하위호환) |
| MCP 호출 | EXECUTE | `run_middleware_agent_use_case.py:44` `create_async` | Needs verification |
| MCP 호출 | EXECUTE | `approval/mcp_executor.py` `build_execution_client` | Needs verification |
| MCP 호출 | EXECUTE | `document_conversion_adapter.py:155` | None — 신원 미설정 서버(Doc Convert) |
| `auth_config` 마스킹 | READ | `to_response` → 프론트 MCP 서버 목록 | Needs verification — 중첩 마스킹 유지 |

### 6.3 Verification

- [ ] 위 소비자 전부 기존 테스트 통과 + 신원 미설정 경로 동작 동일
- [ ] 관리자 권한 가드 변경 없음
- [ ] 필드 추가가 프론트 기존 쿼리·뮤테이션을 깨지 않음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (Thin DDD: domain → application → infrastructure → interfaces) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 주입 위치 | 메일 전용 노드 / MCP 호출 계층 | **MCP 호출 계층** | 전 경로 보장, 일반화 원칙 |
| 메일함 저장 | users 컬럼 / 범용 속성 테이블 / 로그인 email 재사용 | **`users.mailbox_upn`** | 로그인 ID와 메일함 분리, 최소 스키마 |
| 헤더 방식 | HS256 서버별 비밀 / 전역 비밀 / 평문 | **HS256 서버별 비밀** | 서버 검증기 기구현, aud·비밀 서버별 격리, 8006 호스트 노출 대응 |
| 신원 소스 | 인증 컨텍스트 / 실행 요청 사용자 ID | **실행 요청 사용자 ID** | 스케줄·승인 집행에는 인증 컨텍스트가 없음 |
| 허용 경로 | 전 경로 / 웹훅 차단 / 대화만 | **전 경로, 실행 주체 메일함** | 스케줄 메일 요약 등 사용처 확보. 발송은 승인 게이트가 방어 |
| 발급 시점 | 로드 시점 / 호출 시점 | **호출 시점** | 5분 수명, 긴 실행·승인 대기 |
| 토큰 라이브러리 | python-jose / PyJWT 추가 | **python-jose** (기존 의존성) | 의존성 추가 없음 |
| 프론트 | 포함 / 제외 | **포함 (관리자 화면)** | SC-5, USER-SCENARIOS S1 "DB/Swagger 0회" |

### 7.3 Clean Architecture Approach

```
domain/
  auth/entities.py                 User.mailbox_upn
  mcp_registry/identity.py         IdentityHeaderConfig(VO) + IdentityPolicy(검증·클레임 조립 규칙, 순수)
application/
  (실행 주체 ID 전달 배선만: workflow_compiler / run_middleware_agent / approval 집행)
infrastructure/
  mcp_registry/identity_token.py   HS256 발급기 (python-jose)
  mcp_registry/identity_headers.py 주체 ID → users 조회 → 헤더 공급자
  mcp/{client_factory,tool_adapter,call_client}.py  호출 시점 헤더 병합, SSE 헤더
interfaces/
  admin_user_router / mcp registry router + schemas
idt_front/
  types · services · hooks · AdminUsersPage · AdminMcpServersPage
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `idt/CLAUDE.md` 코딩 규칙 (함수 40줄, if 중첩 2단계, print 금지, DDL COMMENT)
- [x] `docs/rules/tool-and-mcp.md` (MCP 소비·session-scoped 어댑터)
- [x] `docs/rules/db-session.md` (Repository commit 금지, UseCase 단일 세션)
- [x] `idt_front/CLAUDE.md`, 메모리: 컴포넌트 파일 런타임 상수 export 금지

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 신원 설정 저장 위치 | 없음 | 암호화 `auth_config` 하위 키 vs 전용 컬럼 (Design 결정) | High |
| 오류 코드 | MCP 친화 에러 매핑 존재 | `IDENTITY_UNAVAILABLE` 계열 idt 측 코드·문구 | Medium |
| 로깅 필드 | LOG-001 | `identity_sub`, `identity_source`, 토큰 원문 금지 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `MCP_SECRET_KEY` | 등록 시크릿(서명 비밀 포함) 암호화 | idt 서버 | ☐ (기존) |
| (없음) | 서명 비밀은 서버별 등록 정보에 암호화 저장 — 전역 env 신설 안 함 | — | — |

---

## 9. Next Steps

1. [ ] `/pdca design mcp-identity-header` — 3안 비교(특히 신원 설정 저장 위치·헤더 공급자 전달 방식), 호출 경로 전수 표, Outlook 서버 전환 체크리스트
2. [ ] `/pdca do mcp-identity-header --scope module-1` 부터 모듈 단위 구현
3. [ ] 구현 후 identity 모드 Outlook 서버로 SC-1~SC-3 실런

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-26 | Initial draft — 저장 위치·토큰 방식·허용 경로·프론트 범위 사용자 결정 반영 | 배상규 / Claude |
