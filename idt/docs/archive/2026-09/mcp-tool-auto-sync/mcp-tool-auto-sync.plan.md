# MCP Tool Auto Sync Planning Document

> **Summary**: MCP 서버 등록/수정 성공 직후 `SyncMcpToolsUseCase`를 best-effort로 호출해 도구가 별도 조작 없이 에이전트 도구 선택창에 나타나게 하고, sync 실패를 관리자에게 알리고 그 자리에서 재동기화할 수 있는 복구 경로를 함께 제공한다
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 0.1.0
> **Author**: 배상규
> **Date**: 2026-08-31
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 관리자가 `AdminMcpServersPage`에서 MCP 서버를 등록하면 `mcp_server_registry`에는 저장되지만 `tool_catalog`에는 단 한 행도 생기지 않는다. 카탈로그 반영의 유일한 경로인 `POST /api/v1/tool-catalog/sync`는 백엔드에만 존재하고 프론트에서 호출하는 코드가 전무하며(`API_ENDPOINTS`에 상수조차 없음), 이를 수행할 관리 화면도 없다. 결과적으로 **등록한 MCP 도구가 에이전트 생성 시 도구 선택창(`ToolPickerModal`)에 영원히 뜨지 않고**, 서버를 `is_active=0`으로 바꿔도 카탈로그 비활성화(설계 원안 Q5)가 동작하지 않는다 |
| **Solution** | **①자동화** — `RegisterMCPServerUseCase`·`UpdateMCPServerUseCase` 성공 직후 해당 서버 1개를 대상으로 `SyncMcpToolsUseCase`를 호출한다. sync 실패(MCP 서버 다운·인증 오류·네트워크 지연)는 **등록/수정 자체를 실패시키지 않는다** — 부팅 시 `seed_internal_tools_on_startup()`이 쓰는 `try/except → warning 로그` 패턴을 그대로 따른다. **②복구 경로** — sync 결과를 등록/수정 응답에 실어 실패를 화면에서 알리고, `AdminMcpServersPage`에 서버별 "도구 동기화" 버튼(기존 `POST /tool-catalog/sync` 재사용)을 두어 관리자가 그 자리에서 재시도하게 한다 |
| **Function/UX Effect** | 관리자가 MCP 서버를 등록하고 에이전트 생성 화면으로 이동하면 그 서버의 도구가 **MCP 배지와 함께 즉시 목록에 보인다.** 서버 정보를 수정하면 변경된 도구 목록이 반영되고, 비활성화하면 도구가 목록에서 사라진다. 정상 경로에서 관리자는 "동기화"라는 두 번째 조작을 배울 필요가 없고, **MCP 서버가 죽어 있어 실패한 경우에만** 안내 문구와 함께 동기화 버튼을 쓰면 된다 |
| **Core Value** | MCP 확장 경로의 마지막 끊긴 고리를 잇는다. 지금은 "MCP 서버 등록" 기능이 사실상 **화면상 무효과**인 상태이며, 이 갭 때문에 플랫폼의 외부 도구 확장성이 실사용에서 검증조차 되지 않았다. 등록→노출을 1스텝으로 만들어 MCP 기능을 실제로 사용 가능한 상태로 전환한다 |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | MCP 서버를 등록해도 `tool_catalog`에 반영되지 않아 도구 선택창에 노출되지 않는다. 반영 API는 있으나 호출자가 없다 |
| **WHO** | P2 — KB 운영자 / 에이전트 소유자 중 **MCP 서버를 등록하는 관리자(admin)**, 그리고 그 도구를 고르는 에이전트 생성자 |
| **RISK** | sync가 같은 DB 세션에서 실패하면 세션이 오염되어 **MCP 서버 등록 커밋 자체가 실패**할 수 있다 (best-effort 계약 위반) |
| **SUCCESS** | MCP 서버 등록 후 추가 조작 없이 `GET /api/v1/tool-catalog`에 해당 서버 도구가 나타나고, MCP 서버가 응답하지 않아도 등록은 201로 성공하며, **그 실패가 화면에 표시되고 동기화 버튼으로 복구된다** |
| **SCOPE** | 백엔드(application 레이어 + DI 배선 + 응답 스키마 1필드) + 프론트(sync 훅·서버별 동기화 버튼·실패 안내). 스케줄러·자동 재시도는 범위 밖 |

---

## 1. Overview

### 1.1 Purpose

MCP 서버 등록/수정 시 `tool_catalog` 반영을 자동화하여, 관리자가 등록한 MCP 도구가 에이전트 도구 선택창에 노출되도록 한다.

### 1.2 Background

`tool_catalog`은 내부 도구(`TOOL_REGISTRY`)와 MCP 도구를 UI 노출용으로 통합한 파생 캐시다. 두 소스의 반영 방식이 비대칭이다.

| 소스 | 진실원 | 반영 트리거 | 현재 상태 |
|------|--------|------------|----------|
| internal | `domain/agent_builder/tool_registry.py`의 `TOOL_REGISTRY` (코드) | 앱 부팅 시 `seed_internal_tools_on_startup()` → `SyncInternalToolsUseCase` | ✅ 자동 |
| mcp | `mcp_server_registry` 테이블 | `POST /api/v1/tool-catalog/sync` (admin 수동) | ❌ **호출자 없음** |

원 설계(`docs/archive/2026-04/shared-custom-agent/shared-custom-agent.design.md` §2 Open Questions)에서 MCP sync는 다음과 같이 확정되었다.

> | 1 | MCP sync 전략 | **수동 API** (`POST /api/v1/tool-catalog/sync`) — admin이 명시적으로 호출. 스케줄러는 이번 범위 아님 |
> | 5 | MCP 서버 비활성화 시 도구 연동 | 서버 `is_active=0` 시 해당 tool_catalog 레코드도 자동 `is_active=0` (**sync API 내 처리**) |

즉 "수동 호출"은 의도된 설계였으나, **그 수동 호출을 수행할 관리 화면이 끝내 만들어지지 않아** 기능이 미완결 상태로 남았다. 부작용으로 Q5의 비활성화 연동도 함께 죽어 있다.

등록과 sync를 분리한 원래 이유 자체는 여전히 유효하다.

- MCP 서버 1개 = 도구 N개이며, N은 서버에 실제 접속해 `list_tools()`를 해야만 알 수 있다
- 등록 트랜잭션 안에서 외부 접속을 강제하면 MCP 서버 장애 시 **등록 자체가 실패**한다

본 기능은 이 두 관심사를 유지한 채(등록은 DB 쓰기, sync는 네트워크 I/O) **호출 시점만 자동화**하고, sync 실패가 등록으로 전파되지 않도록 격리한다.

### 1.3 Related Documents

- 규칙: `docs/rules/tool-and-mcp.md` (TOOL-MCP-001) — 도구 등록 경로·tool_id 규약
- 규칙: `docs/rules/db-session.md` (DB-001) — 세션/트랜잭션 경계
- 원 설계: `docs/archive/2026-04/shared-custom-agent/shared-custom-agent.design.md` §2, §8-3
- 관련 기능: `docs/archive/2026-08/builtin-tools/` — `is_builtin` 보존 계약(D2)

---

## 2. Scope

### 2.1 In Scope

**① 백엔드 자동화**

- [ ] `RegisterMCPServerUseCase.execute()` 성공 후 해당 서버 1개 대상 sync 호출
- [ ] `UpdateMCPServerUseCase.execute()` 성공 후 해당 서버 1개 대상 sync 호출
- [ ] sync 실패 시 **예외를 삼키고 warning 로그**(request_id·server_id 포함) — 등록/수정은 정상 응답
- [ ] sync 실패가 MCP 서버 저장 트랜잭션을 오염시키지 않도록 세션 경계 분리
- [ ] `main.py` DI 배선 — 두 UseCase에 sync 의존성 주입 (미주입 시 기존 동작 유지)

**② 복구 경로 (사용자 확정: 동기화 버튼 + 실패 알림)**

- [ ] `MCPServerResponse`에 sync 결과 필드 추가 (등록/수정 응답으로 실패를 화면에 전달)
- [ ] 프론트 `API_ENDPOINTS.TOOL_CATALOG_SYNC` 상수 + `toolCatalogService.syncMcpTools()` 추가
- [ ] `useSyncMcpTools()` mutation 훅 — 성공 시 `queryKeys.toolCatalog.all` 캐시 무효화
- [ ] `AdminMcpServersPage` 서버별 "도구 동기화" 버튼 + sync 실패 시 안내 표시
- [ ] 프론트 `McpServer` 타입에 sync 결과 필드 반영 (API 계약 동기화 — 루트 CLAUDE.md §4-1)

**③ 검증**

- [ ] TDD: sync 성공/실패/미주입 3경로 단위 테스트 + 라우터 통합 테스트
- [ ] 프론트: Vitest + MSW로 동기화 버튼·실패 안내 렌더링 테스트

### 2.2 Out of Scope

- **sync 자동 재시도** (사용자 확정) — 1회 시도 후 실패하면 로그/알림까지. MCP 서버가 죽어 있으면 즉시 재시도해도 실패하고 등록 API 응답만 더 느려진다(R-03 악화). 복구는 수동 동기화 버튼으로
- **스케줄러/주기적 sync** — 원 설계에서도 범위 밖으로 명시됨
- **삭제 시 sync** — `tool_catalog.mcp_server_id` FK가 `ON DELETE CASCADE`(V006)라 자동 정리됨
- **`CatalogTool.mcp_server_name` 계약 불일치 수정** — 프론트 타입에만 존재하고 백엔드가 반환하지 않는 별건 드리프트
- **내부 도구(`TOOL_REGISTRY`) 동기화 경로 변경** — 이미 부팅 자동화로 정상 동작 중
- **`ToolAdminPage`(`/tool-admin`) 목업 화면의 실서비스화**
- **전체 서버 일괄 동기화 UI** — `POST /tool-catalog/sync`는 `mcp_server_id` 생략 시 전체 sync를 지원하지만, 이번엔 서버별 버튼만 노출한다

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `RegisterMCPServerUseCase`가 서버 저장 성공 후 해당 `server_id`로 MCP 도구 sync를 호출한다 | High | Pending |
| FR-02 | `UpdateMCPServerUseCase`가 서버 수정 성공 후 해당 `server_id`로 MCP 도구 sync를 호출한다 | High | Pending |
| FR-03 | sync 중 발생한 모든 예외는 포착되어 warning 로그로 기록되고, 등록/수정 응답은 정상(201/200)으로 반환된다 | High | Pending |
| FR-04 | sync 대상은 **방금 등록/수정한 서버 1개**로 한정한다 (`mcp_server_id` 지정). 전체 sync는 호출하지 않는다 — 무관한 서버의 장애가 전파되는 것을 막는다 | High | Pending |
| FR-05 | sync 실패가 MCP 서버 저장 트랜잭션의 커밋을 방해하지 않는다 (세션 오염 차단) | High | Pending |
| FR-06 | sync 의존성이 주입되지 않은 경우(테스트·부분 배선) 두 UseCase는 sync를 건너뛰고 기존과 동일하게 동작한다 | Medium | Pending |
| FR-07 | 기존 `POST /api/v1/tool-catalog/sync` 수동 API는 시그니처·동작 변경 없이 유지된다 | Medium | Pending |
| FR-08 | `is_active=false`로 수정 시 `deactivate_by_mcp_server`가 실행되어 해당 서버 도구가 카탈로그에서 비활성화된다 (원 설계 Q5 복구) | Medium | Pending |
| FR-09 | 등록/수정 응답(`MCPServerResponse`)에 sync 성공 여부와 동기화된 도구 수가 포함된다 | High | Pending |
| FR-10 | `AdminMcpServersPage`에서 sync 실패 시 해당 서버 행에 실패 상태가 표시되고, 원인을 짐작할 수 있는 안내 문구가 제공된다 | High | Pending |
| FR-11 | `AdminMcpServersPage`의 서버별 "도구 동기화" 버튼이 `POST /api/v1/tool-catalog/sync`(`mcp_server_id` 지정)를 호출하고, 성공 시 도구 카탈로그 캐시를 무효화한다 | High | Pending |
| FR-12 | 동기화 버튼은 sync 실패 여부와 무관하게 **항상 노출**된다 — MCP 서버 쪽이 나중에 도구를 추가·변경한 경우의 재동기화 수단이기도 하다 | Medium | Pending |
| FR-13 | sync는 실패해도 **자동 재시도하지 않는다** (1회 시도) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 가용성 | MCP 서버가 무응답이어도 등록 API는 성공한다 | 연결 불가 endpoint로 등록 → 201 확인 (단위 테스트에서 loader mock이 예외 발생) |
| 응답성 | 등록 API 응답 시간이 MCP 서버 응답 지연에 비례해 늘어난다는 점을 인지하고 상한을 둔다 | Design에서 타임아웃 전략 확정 (§7.2 D-03) |
| 관측성 | sync 실패 시 `request_id`, `server_id`, 예외 메시지가 구조화 로그에 남는다 | LOG-001 준수 — `/verify-logging` |
| 아키텍처 | domain → infrastructure 역참조 없음, 라우터에 비즈니스 로직 없음 | `/verify-architecture` |
| 트랜잭션 | Repository 내부 `commit()`/`rollback()` 호출 없음, UseCase 내 세션 혼용 금지 규칙 준수 | DB-001 대조 + 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-13 전부 구현
- [ ] MCP 서버 등록 → 추가 조작 없이 `GET /api/v1/tool-catalog` 응답에 해당 서버 도구가 `source="mcp"`, `tool_id="mcp:{server_id}:{tool}"`로 포함됨
- [ ] 도달 불가 endpoint로 등록해도 `201 Created` 반환 + warning 로그 1건
- [ ] **위 실패가 `AdminMcpServersPage`에 표시되고, "도구 동기화" 버튼으로 재시도 후 도구가 카탈로그에 나타남** (막다른 길 없음)
- [ ] `is_active=false` 수정 → 해당 서버 도구가 카탈로그 목록에서 사라짐
- [ ] 단위 테스트: sync 성공 / sync 예외 / sync 미주입 3경로 (TDD Red → Green)
- [ ] 라우터 통합 테스트: `POST /api/v1/mcp-registry` 성공 경로에서 sync가 호출됨을 검증
- [ ] 프론트 테스트: 동기화 버튼 클릭 → sync 호출 + 카탈로그 캐시 무효화, sync 실패 응답 → 안내 렌더링
- [ ] `tests/application/mcp_registry/` 기존 테스트 전부 통과 (회귀 없음)
- [ ] Design 문서 작성 및 승인

### 4.2 Quality Criteria

- [ ] `pytest tests/application/mcp_registry tests/application/tool_catalog tests/api/test_mcp_registry_router.py tests/api/test_tool_catalog_router.py` 전부 통과
- [ ] `/verify-architecture` 통과 (레이어 위반 0)
- [ ] `/verify-logging` 통과 (`print()` 0, 스택 트레이스 누락 0)
- [ ] `/verify-tdd` 통과 (변경 모듈 대응 테스트 존재)
- [ ] 함수 40줄 초과 없음, if 중첩 2단계 초과 없음

---

## 5. Risks and Mitigation

| ID | Risk | Impact | Likelihood | Mitigation |
|----|------|--------|------------|------------|
| **R-01** | **세션 오염** — sync가 같은 `AsyncSession`에서 `upsert_by_tool_id()` 도중 실패하면 세션이 `PendingRollbackError` 상태가 되어, 예외를 삼켜도 MCP 서버 등록 커밋이 실패한다. FR-03/FR-05의 "실패해도 등록은 성공" 계약이 깨진다 | High | Medium | Design에서 세션 경계를 명시 결정한다. 후보: ①sync를 별도 세션(`get_session_factory()`)에서 실행 ②라우터 레벨이 아닌 오케스트레이션 UseCase가 순차 호출 ③등록 커밋 이후(after-commit) 실행. **DB-001의 "한 UseCase 안에서 repository별 서로 다른 세션 사용 금지" 조항과의 정합성을 반드시 대조할 것** |
| **R-02** | **~~조용한 실패~~ (해소됨)** — 초안에서는 sync 실패 시 관리자가 등록 성공 메시지만 보고 도구가 왜 안 뜨는지 알 수 없었다. 게다가 복구 수단이 "서버 수정창을 열어 그대로 저장"(FR-02가 우연히 sync를 재실행) / "삭제 후 재등록" / "curl 직접 호출"뿐이라, 사실상 **한 번 실패하면 영원히 등록 못 하는 막다른 길**이었다 | ~~High~~ | — | **FR-09~FR-12로 범위에 편입해 해소.** 응답에 sync 결과를 실어 실패를 화면에 알리고, 서버별 "도구 동기화" 버튼으로 그 자리에서 재시도한다. 버튼은 실패 여부와 무관하게 상시 노출되므로 **MCP 서버가 나중에 도구를 추가한 경우의 재동기화 수단**도 겸한다 |
| **R-07** | **프론트 API 계약 변경** — `MCPServerResponse`에 필드가 추가되므로 프론트 `McpServer` 타입도 함께 고쳐야 한다. 누락 시 루트 CLAUDE.md §4-1(API 계약 동기화) 위반 | Medium | Low | 필드는 **optional로 추가**해 기존 소비자(`AdminMcpServersPage` 목록/수정 흐름)가 깨지지 않게 한다. `/api-contract-sync` 스킬로 백엔드↔프론트 타입 동기화 확인 |
| **R-08** | **버튼 오용** — 관리자가 동기화 버튼을 반복 클릭해 MCP 서버에 과도한 `list_tools()` 요청이 나갈 수 있다 | Low | Low | 진행 중 버튼 비활성화(mutation `isPending`)로 중복 클릭 차단. 서버별 단건 sync라 부하 범위가 한정됨 |
| **R-03** | **등록 API 응답 지연** — 느린 MCP 서버에 `list_tools()`가 매달리면 등록 요청이 수 초간 블로킹된다 | Medium | Medium | Design에서 타임아웃 상한 또는 `BackgroundTasks` 전환을 결정한다. 다만 백그라운드 전환 시 "등록 직후 목록에 보인다"는 UX 보장이 약해지므로 트레이드오프 판단 필요 |
| **R-04** | **`is_builtin` 덮어쓰기** — sync 호출 빈도가 늘어 관리자가 토글한 빌트인 플래그가 초기화될 우려 | Low | Low | `ToolCatalogRepository.upsert_by_tool_id()`의 UPDATE 분기가 `is_builtin`을 SET 절에서 의도적으로 제외한다(builtin-tools D2 보존 계약). 회귀 방지를 위해 **"sync 반복 후 is_builtin 유지" 테스트를 추가** |
| **R-05** | **암호화 키 미설정 환경** — `MCP_SECRET_KEY` 미설정 시 `_mcp_cipher()`가 `None`이라 `streamable_http` 서버의 `auth_config` 복호화가 불가하고 sync가 실패할 수 있다 | Low | Low | R-01/FR-03의 best-effort 경로로 흡수됨(등록은 성공). 로그 메시지에 원인 힌트 포함 |
| **R-06** | **`'Session terminated'` 오해** — sync 실패 로그가 이 메시지로 나타나면 세션 만료로 오진하기 쉽다. 실제로는 대부분 HTTP 404(빈 `api_key`가 URL에서 누락) | Low | Medium | TOOL-MCP-001 §3의 진단 힌트를 로그 메시지에 반영 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `RegisterMCPServerUseCase` | Application UseCase | sync 의존성 추가(선택적) + 저장 성공 후 sync 호출 |
| `UpdateMCPServerUseCase` | Application UseCase | 동일 |
| `create_mcp_registry_factories()` (`api/main.py:4200`) | DI 배선 | 두 factory에 sync 의존성 주입 |
| `SyncMcpToolsUseCase` | Application UseCase | **시그니처 변경 없음** — 신규 호출자만 추가 |
| `MCPServerResponse` (`application/mcp_registry/schemas.py`) | API Schema | sync 결과 필드 추가 (**optional**, FR-09) + `to_response()` 조립 |
| `tool_catalog` 테이블 | DB | 스키마 변경 없음. 쓰기 빈도만 증가 |
| `mcp_server_registry` 테이블 | DB | 변경 없음 |
| `idt_front/src/constants/api.ts` | Frontend Const | `TOOL_CATALOG_SYNC` 상수 추가 |
| `idt_front/src/services/toolCatalogService.ts` | Frontend Service | `syncMcpTools(mcpServerId)` 추가 |
| `idt_front/src/hooks/useToolCatalog.ts` | Frontend Hook | `useSyncMcpTools()` mutation 추가 (`queryKeys.toolCatalog.all` 무효화) |
| `idt_front/src/types/mcpServer.ts` | Frontend Type | `McpServer`에 sync 결과 필드 반영 (optional) |
| `idt_front/src/pages/AdminMcpServersPage/index.tsx` | Frontend Page | 서버별 "도구 동기화" 버튼 + sync 실패 안내 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `RegisterMCPServerUseCase` | CREATE | `api/routes/mcp_registry_router.py:42` `POST /api/v1/mcp-registry` | **Needs verification** — 응답 지연 가능(R-03), 응답 스키마는 불변 |
| `RegisterMCPServerUseCase` | CREATE | `tests/application/mcp_registry/test_register_mcp_server_use_case.py` | **Needs verification** — 생성자 시그니처 변경 시 기존 테스트 깨짐 → 신규 인자를 기본값 `None`으로(FR-06) |
| `RegisterMCPServerUseCase` | CREATE | `tests/application/mcp_registry/test_register_streamable_http.py` | Needs verification (동일) |
| `UpdateMCPServerUseCase` | UPDATE | `api/routes/mcp_registry_router.py:80` `PUT /api/v1/mcp-registry/{id}` | Needs verification |
| `UpdateMCPServerUseCase` | UPDATE | `tests/application/mcp_registry/test_update_delete_use_cases.py` | Needs verification (동일) |
| `SyncMcpToolsUseCase` | CREATE/UPDATE | `api/routes/tool_catalog_router.py:65` `POST /api/v1/tool-catalog/sync` (admin) | **None** — 기존 경로 유지(FR-07). 프론트 동기화 버튼이 이 경로를 **처음으로 실사용**하므로 admin 권한(`require_role("admin")`) 하에서 동작하는지 확인 필요 |
| `MCPServerResponse` | READ | `POST`/`PUT`/`GET /api/v1/mcp-registry` 3개 라우트 응답 | **Needs verification** — 필드 추가는 후방 호환이나, `GET` 목록/단건은 sync를 수행하지 않으므로 값이 비어 있음(§7.2 D-08) |
| `MCPServerResponse` | READ | `tests/api/test_mcp_registry_router.py` | Needs verification — 응답 스키마 단언이 있으면 갱신 |
| `McpServer` (프론트 타입) | READ | `AdminMcpServersPage` 목록 렌더링·수정 폼 프리필 | **None** — optional 필드 추가라 기존 렌더링 불변 |
| `queryKeys.toolCatalog.all` | INVALIDATE | 기존 `useSetToolBuiltin` (빌트인 토글) | **None** — 동일 키를 신규 mutation이 추가로 무효화할 뿐 |
| `tool_catalog` | READ | `ListToolCatalogUseCase.execute()` → `GET /api/v1/tool-catalog` | None — 읽기 계약 불변 |
| `tool_catalog` | READ | 프론트 `useToolCatalog()` → `ToolPickerModal`, `AdminToolsPage`, `LeftConfigPanel`, `ToolsStep`, `buildGraph` | **None (긍정적 변화)** — 항목 수가 늘어날 뿐 스키마 동일 |
| `tool_catalog` | UPDATE | `SetBuiltinToolUseCase` → `PATCH /api/v1/tool-catalog/builtin` | **Needs verification** — `is_builtin` 보존 계약(R-04) 회귀 여부 확인 |
| `tool_catalog` | UPDATE | `SyncInternalToolsUseCase` (부팅) | None — `source='internal'`만 다루므로 간섭 없음 |
| `tool_catalog` | DELETE | FK `ON DELETE CASCADE` (V006) — MCP 서버 삭제 시 | None — 자동 정리, 변경 불필요 |
| `mcp_server_registry` | READ | `MCPToolLoader.load_by_tool_id()` (에이전트 런타임 실행 경로) | **None** — 런타임은 `tool_catalog`을 조회하지 않고 레지스트리에서 라이브 로드 |

### 6.3 Verification

- [ ] 위 소비자 전부가 변경 후에도 동작함을 확인
- [ ] `RegisterMCPServerUseCase`/`UpdateMCPServerUseCase` 생성자 변경이 기존 테스트를 깨지 않음 (기본값 `None`)
- [ ] MCP 서버 등록 실패 시나리오(잘못된 endpoint)에서 등록 API가 여전히 201을 반환
- [ ] `is_builtin` 토글값이 반복 sync 후에도 보존됨
- [ ] `POST /api/v1/tool-catalog/sync` 수동 경로 회귀 없음 + 프론트에서 admin 권한으로 호출 성공
- [ ] `MCPServerResponse` 필드 추가가 백엔드↔프론트 양쪽에 반영됨 (`/api-contract-sync`)
- [ ] 응답 필드 추가로 기존 프론트 목록/수정 화면이 깨지지 않음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| Starter | 단순 구조 | 정적 사이트 | ☐ |
| Dynamic | 기능 모듈 + BaaS | 웹앱 MVP | ☐ |
| **Enterprise** | 레이어 분리, DI, Thin DDD | 본 프로젝트(FastAPI + LangGraph, `domain`/`application`/`infrastructure`/`interfaces`) | ☑ |

### 7.2 Key Architectural Decisions

| ID | Decision | Options | 잠정 선택 | Rationale |
|----|----------|---------|-----------|-----------|
| D-01 | sync 호출 위치 | ①UseCase 내부 ②라우터 ③신규 오케스트레이션 UseCase | **①UseCase 내부** (Design에서 확정) | 라우터에 비즈니스 로직 금지(CLAUDE.md §6). ③은 레이어가 하나 늘어 과도한 추상화 우려 |
| D-02 | **세션 경계** | ①같은 세션 공유 ②sync 전용 별도 세션 ③after-commit 훅 | **Design에서 확정 필요 (R-01 핵심)** | ①은 DB-001 정합적이나 sync 실패 시 세션 오염 위험. ②는 격리는 완전하나 "한 UseCase 안 세션 혼용 금지" 조항과 충돌 소지 → 조항의 의도(도메인 일관성) 대비 해석 필요 |
| D-03 | 실행 방식 | ①동기(응답 전) ②`BackgroundTasks` | **①동기** (잠정) | "등록 직후 도구가 보인다"는 UX 보장이 이 기능의 목적. ②는 R-03을 해소하지만 목적을 약화 |
| D-04 | 의존성 주입 형태 | ①UseCase 인스턴스 주입 ②콜러블 주입 ③팩토리 주입 | **Design에서 확정** | D-02의 세션 결정에 종속. 별도 세션이면 팩토리 형태가 자연스러움 |
| D-05 | sync 범위 | ①해당 서버만 ②전체 서버 | **①해당 서버만** (FR-04) | 무관한 서버의 장애·지연 전파 차단 |
| D-06 | 하위 호환 | ①필수 인자 ②선택 인자(기본 `None`) | **②선택 인자** (FR-06) | 기존 테스트 6개 파일 무수정 통과 |
| D-07 | 실패 시 재시도 | ①재시도 없음 ②1회 재시도 | **①재시도 없음** (FR-13, 사용자 확정) | MCP 서버가 죽어 있으면 즉시 재시도해도 실패하고 등록 응답만 느려진다(R-03 악화). 복구는 수동 버튼이 담당 |
| D-08 | sync 결과 표현 형태 | ①`sync_ok: bool` + `synced_tool_count: int` ②중첩 객체 `tool_sync: {...}` ③에러 메시지까지 노출 | **Design에서 확정** | `GET`(sync 미수행) 응답에서의 기본값 의미가 관건. ③은 MCP 서버 내부 오류 메시지를 그대로 노출하므로 정보 노출 범위 검토 필요 |
| D-09 | 동기화 버튼 위치 | ①서버 행 액션 ②수정 모달 안 ③목록 상단 일괄 | **①서버 행 액션** (FR-11/FR-12) | 서버별 단건 sync이므로 행 단위가 자연스럽다. 상시 노출이라 재동기화 용도로도 발견하기 쉬움 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

[백엔드 idt/]
┌──────────────────────────────────────────────────────────────┐
│ interfaces/  api/routes/mcp_registry_router.py               │
│              → 변경 없음 (라우터에 로직 추가 금지)              │
│              api/routes/tool_catalog_router.py               │
│              → 변경 없음 (기존 /sync 재사용, FR-07)            │
├──────────────────────────────────────────────────────────────┤
│ application/ mcp_registry/register_mcp_server_use_case.py  ◀ │
│              mcp_registry/update_mcp_server_use_case.py    ◀ │
│              mcp_registry/schemas.py (MCPServerResponse)   ◀ │
│              tool_catalog/sync_mcp_tools_use_case.py         │
│              → 재사용, 변경 없음                               │
├──────────────────────────────────────────────────────────────┤
│ domain/      변경 없음 (규칙 추가 없음)                        │
├──────────────────────────────────────────────────────────────┤
│ infrastructure/ 변경 없음                                     │
├──────────────────────────────────────────────────────────────┤
│ api/main.py  create_mcp_registry_factories()  ◀ DI 배선       │
└──────────────────────────────────────────────────────────────┘

[프론트엔드 idt_front/]
┌──────────────────────────────────────────────────────────────┐
│ constants/api.ts        TOOL_CATALOG_SYNC                  ◀ │
│ services/toolCatalogService.ts  syncMcpTools()             ◀ │
│ hooks/useToolCatalog.ts         useSyncMcpTools()          ◀ │
│ types/mcpServer.ts              McpServer sync 필드        ◀ │
│ pages/AdminMcpServersPage/      동기화 버튼 + 실패 안내     ◀ │
└──────────────────────────────────────────────────────────────┘
◀ = 수정 대상
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md`에 레이어 책임·금지 사항 정의됨
- [x] `docs/rules/db-session.md` (DB-001) — 세션/트랜잭션 규칙
- [x] `docs/rules/logging.md` (LOG-001) — 구조화 로깅
- [x] `docs/rules/tool-and-mcp.md` (TOOL-MCP-001) — 도구/MCP 규칙
- [x] `docs/rules/testing.md` — TDD 절차
- [x] `pyproject.toml` — pytest 설정

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| best-effort 부수효과 패턴 | 존재 (`seed_internal_tools_on_startup()`의 `try/except → warning`) | 동일 패턴 재사용 — 새 규칙 불필요 | High |
| 세션 경계 (부수효과 UseCase) | DB-001에 명시 조항 있으나 **본 케이스(교차 UseCase 호출) 해석은 미정** | Design에서 결정 후 필요 시 DB-001에 사례 추가 | High |
| 로그 필드 | LOG-001 준수 | sync 실패 로그에 `server_id` 포함 | Medium |
| 프론트 상수 위치 | 규칙 존재 | 컴포넌트 파일에서 런타임 상수를 export하지 않는다 — 엔드포인트는 `constants/api.ts`, `as const` 타입 상수는 `src/types/*.ts` | Medium |
| API 계약 동기화 | 루트 CLAUDE.md §4-1 | 백엔드 스키마 변경 시 프론트 `src/types/` 동시 수정 (`/api-contract-sync`) | High |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `MCP_SECRET_KEY` | `streamable_http` `auth_config` 암복호화 (기존) | Server | ☐ (기존) |

**신규 환경변수 없음.**

### 8.4 Pipeline Integration

해당 없음 — 9-phase Development Pipeline이 아닌 단일 기능 PDCA 사이클.

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`/pdca design mcp-tool-auto-sync`) — **D-02 세션 경계 결정이 최우선 안건**, 이어서 D-08 sync 결과 표현 형태
2. [ ] 3가지 아키텍처 옵션 비교 및 선택
3. [ ] TDD 구현 (`/pdca do mcp-tool-auto-sync`) — 백엔드 → 프론트 순
4. [ ] `/api-contract-sync`로 `MCPServerResponse` ↔ `McpServer` 타입 동기화 확인
5. [ ] Gap 분석 (`/pdca analyze mcp-tool-auto-sync`)
6. [ ] 후속 검토: `CatalogTool.mcp_server_name` 계약 불일치 정리, MCP 도구 주기적 재동기화(스케줄러)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-08-31 | 초안 작성 | 배상규 |
| 0.2 | 2026-08-31 | **복구 경로 부재 지적 반영** — sync 1회 실패 시 되살릴 수단이 없어 "영원히 등록 불가"가 되는 문제(R-02)를 해소. 동기화 버튼 + 실패 알림(FR-09~FR-12)을 범위에 편입, 자동 재시도는 제외(FR-13). 프론트 변경 범위·계약 리스크(R-07/R-08) 추가 | 배상규 |
