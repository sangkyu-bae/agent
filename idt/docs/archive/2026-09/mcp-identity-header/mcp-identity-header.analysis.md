# mcp-identity-header Analysis Report

> **Analysis Type**: Gap Analysis (static + runtime)
> **Project**: sangplusbot (idt + idt_front)
> **Analyst**: 배상규 / Claude (static axis: gap-detector agent, partial — gaps closed by orchestrator)
> **Date**: 2026-09-26
> **Design Doc**: [mcp-identity-header.design.md](./mcp-identity-header.design.md) (v0.2)
> **Plan Doc**: [mcp-identity-header.plan.md](./mcp-identity-header.plan.md)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 공용 MCP 서버 하나가 여러 사용자의 개인 자원을 다루려면 "누구의 자원인가"를 LLM이 아닌 플랫폼이 호출마다 보증해야 한다 |
| **WHO** | P2(에이전트 소유자) / 관리자(회원 메일함·서버 신원 설정) / 최종 사용자(본인 메일 조회·발송) |
| **RISK** | MCP 호출 경로 누락 · 5분 토큰 만료 |
| **SUCCESS** | 두 사용자가 각자 메일함 결과 / 미등록 사용자는 호출 전 거부 / 미설정 서버 무변화 |
| **SCOPE** | M1 도메인·스키마 → M2 호출 시점 주입 → M3 관리자 API → M4 관리자 화면 |

---

## Strategic Alignment Check

### Core problem (WHY)

구현은 핵심 문제를 해결한다. 실런에서 idt 가 서명한 토큰을 Outlook 서버(identity 모드)가 검증했고, 서버는 토큰 클레임의 메일함으로만 Graph 를 호출했다. **단, G-1(아래) 때문에 "주체를 플랫폼이 보증한다"는 전제가 `POST /agents/{id}/run` 한 경로에서 깨진다** — 핵심 가치와 직결되므로 Critical 로 분류한다.

### Success Criteria Status

| SC | 기준 | 상태 | 근거 |
|----|------|:----:|------|
| SC-1 | 두 사용자가 각자 메일함 결과 | ✅ | 실런: 사용자 7(sender@) 토큰 → 서버가 sender@ 로 해석, 테넌트 정책상 `MAILBOX_ACCESS_DENIED` / 신원 B(test@) → 메일 1건 반환. 에이전트 실런(`POST /run`, user 7)도 서버 로그에 `identity.rejected` 없이 sender@ 로 도달. *B 는 in-memory 사용자 레코드 — 실 사용자 2명 등록은 테넌트 정책 확장 후* |
| SC-2 | 미등록 사용자는 서버에 요청이 가지 않음 | ✅ | 실런: 사용자 8(메일함 NULL) → 안내문 반환, call 세션 0회. 단위 `test_신원_불가면_연결을_시도하지_않는다` |
| SC-3 | 스케줄·승인 집행이 생성자·요청자 신원 | ⚠️ | 단위만: `test_예약_집행도_요청자_신원으로`, `test_집행은_승인자가_아니라_요청자_신원으로`, `test_재개는_요청자를_실행_주체로_넘긴다`. 실 발송(send_mail)은 비가역이라 실런 생략. **G-1 로 `/run` 발 승인은 requested_by 가 위조 가능** |
| SC-4 | 미설정 서버 무변화 | ✅ | 실런: Scrap MCP 도구 3개 모두 header_provider 없음. 단위 `test_공급자가_없으면_기존과_같다` |
| SC-5 | 관리자가 화면만으로 설정 | ✅ | Vitest L2 6/6 + 메일함 셀 7건 통과. 실제로 사용자가 관리자 화면에서 메일함을 등록했다 (DB 반영 확인) |
| SC-6 | 응답·로그에 비밀·토큰 원문 없음 | ✅ | 실 PUT 응답 `secret: "****"`, 원문 미포함 확인. 단위 `test_발급_로그에_토큰과_비밀이_없다`, `test_repr에_secret이_나오지_않는다` |

**Success Rate**: 5/6 충족, 1 부분(SC-3)

### Decision Record Verification

| 결정 | 준수 | 비고 |
|------|:----:|------|
| [Plan] 메일함 = `users.mailbox_upn` | ✅ | V076 |
| [Plan] HS256 + 서버별 비밀 | ✅ | 서버 `HmacTokenVerifier` 규칙 재현 교차 테스트 통과 |
| [Plan] 전 실행 경로 허용, 실행 주체 기준 | ⚠️ | 배선은 완료. `/run` 의 주체 신뢰성 결함(G-1) |
| [Design] Option C — 전용 컬럼·호출 시점 발급·인자 전달 | ✅ | `ToolFactory._auth_ctx` 미사용, `create_session(header_provider=)` 단일 지점 |

---

## 1. Analysis Overview

- 정적: gap-detector 에이전트(턴 한도로 부분 완료) + 미검증 항목 orchestrator 직접 확인
- 런타임: 실 앱(TestClient 인프로세스)·실 DB·실 Outlook MCP(8006, identity 모드)·실 LLM

## 2. Gap Analysis

### 2.1 API Endpoints

| Design | Implementation | Status |
|--------|----------------|:------:|
| GET `/api/v1/admin/users` + `mailbox_upn` | `admin_user_router.py` list 매핑 | ✅ |
| PATCH `/api/v1/admin/users/{id}/mailbox` | `admin_user_router.py:181` | ✅ |
| POST/PUT/GET `/api/v1/mcp-registry` + `identity_config` | `application/mcp_registry/schemas.py`, `identity_config.py` | ✅ |

### 2.2 Data Model

V076 `users.mailbox_upn`, V077 `mcp_server_registry.identity_config_enc` — DDL COMMENT = ORM `comment=` 일치 (`test_migration_ddl_comments` 통과). 로컬 DB 적용 완료.

### 2.3 Component Structure

Design §11.1 전 파일 존재. Design 에 없는 신규 1개: `application/mcp_registry/identity_config.py` (UseCase 길이 규칙 준수용 흐름 헬퍼) → 문서 갱신 대상(G-6).

### 2.4 Functional Depth (FR)

| FR | Status | 근거 |
|----|:------:|------|
| FR-01 메일함 컬럼·정규화 | ✅ | `MailboxPolicy.normalize` |
| FR-02 관리자 조회·설정·해제 | ✅ | PATCH + 목록 필드, `require_role("admin")` |
| FR-03 서버 신원 설정 | ✅ | `IdentityHeaderConfig` 검증 |
| FR-04 비밀 암호화·마스킹 | ✅ | `SecretCipher`, `masked()` |
| FR-05 호출마다 새 토큰 | ✅ | `test_호출마다_새로_발급한다` |
| FR-06 실행 주체 = 실행 요청 사용자 | ⚠️ | 배선 ✅, `/run` 주체 위조 가능(G-1) |
| FR-07 네트워크 전 거부 + 안내 | ✅ | 실런 SC-2 |
| FR-08 미설정 서버 무변화 | ✅ | 실런 SC-4 |
| FR-09 SSE·HTTP 모두 헤더 | ✅ | SSE 실런 성공 |
| FR-10 토큰 원문 로그 금지 | ✅ | 발급 로그 필드 제한 |
| FR-11 관리자 화면 | ✅ | Vitest L2 전 항목 |

### 2.5 Page UI Checklist

AdminUsersPage 5/5 ✅ (메일함 열, 편집·등록, LoadingButton, 400 메시지, 저장 후 재조회 — `UserMailboxCell.test.tsx`). AdminMcpServersPage 7/7 ✅ (`identity.test.tsx` 배지·생성·검증·비밀 유지·해제·미사용 서버).

### 2.6 API Contract (3-way)

필드명·PUT 3상태(없음/null/객체)·`"****"` 마스킹이 Design §4.2 ↔ 백엔드 스키마 ↔ `types/mcpServer.ts`·`types/auth.ts` 에서 일치. 편차 2건은 §9 참조(422 승인 편차, 320자 초과 422 — G-5).

### 2.7 Runtime Verification Results

| # | 시나리오 | 결과 |
|---|----------|:----:|
| L1-1 | PATCH mailbox 대문자 → 200 소문자 | ✅ (module-3 실런) |
| L1-2 | 형식 오류 400 / 없는 사용자 404 / 해제 200 | ✅ |
| L1-3 | PUT identity_config → 200, 응답·GET `secret: "****"` | ✅ (실 등록 반영) |
| L3-1 | 에이전트 실런 user 7 → 서명 토큰 수용, 사용자 메일함으로 해석 | ✅ (Graph 거부는 테넌트 정책) |
| L3-2 | 신원 A/B → 서로 다른 메일함 | ✅ |
| L3-3 | 메일함 없는 사용자 → 안내문, call 세션 0 | ✅ |
| L3-4 | Scrap MCP 헤더 무변화 | ✅ |
| L3-5 | 스케줄·승인 실집행 | ⏭️ 생략 (send_mail 비가역) |

### 2.8 Match Rate Summary

| Axis | Score | 비고 |
|------|:-----:|------|
| Structural | 98% | 설계 외 헬퍼 1개 문서 누락 |
| Functional | 91% | FR-06 부분 |
| Contract | 95% | 320자 초과 422 |
| Runtime | 88% | SC-3 실런 생략, G-1 |
| **Overall** | **93%** | 0.15×98 + 0.25×91 + 0.25×95 + 0.35×88 |

> Match Rate 는 90% 를 넘지만 **G-1 은 Critical — 수정 전 Report 진행 비권장.**

---

## 3. Gaps

| # | Severity | Confidence | 내용 | 수정안 |
|---|:--------:|:----------:|------|--------|
| G-1 | **Critical** | 95% | `POST /api/v1/agents/{id}/run` 이 `body.user_id` 를 토큰 사용자와 대조하지 않는다 (`agent_builder_router.py:268-291`). 스트림 라우트는 불일치를 403 처리하고 생성 라우트는 덮어쓰지만 `/run` 은 둘 다 없다. `RunAgentUseCase` 가 이 값을 신원 주체(`subject_user_id`)와 승인 `requested_by` 로 쓰므로, 인증된 사용자가 남의 ID 를 넣으면 **그 사람 메일함 토큰이 발급**된다. 결함 자체는 기존이지만 이 기능이 메일함 사칭으로 격상시킨다. 실 악용 시연은 하지 않았다 | 라우트에서 `body.user_id` 를 토큰 사용자로 강제(스트림과 같은 403 또는 덮어쓰기) + 회귀 테스트 |
| G-2 | Minor | 95% | 승인 집행기에서 신원 불가 외의 공급자 실패(서명 오류, 배선 오류)가 `unknown` 으로 기록된다 (`mcp_executor.py:215`). 연결 전 실패라 Design §6.2 상 `blocked` 가 맞다 | 공급자 단계 예외를 구분해 `blocked` |
| G-3 | Minor | 90% | 복호화 불가(키 교체 등)로 신원 설정이 `None` 으로 읽힌 서버를, 이후 `identity_config` 필드 없이 PUT 하면 컬럼이 NULL 로 덮여 **저장된 설정이 조용히 삭제**된다 (`update_mcp_server_use_case.py`, repo `_to_model`). auth_config 에도 있는 기존 패턴 | 복호화 실패 시 원 암호문 보존 또는 수정 거부 |
| G-4 | Minor | 90% | 신원 차단 WARN 로그에 주체(`identity_sub`)가 없다 (`tool_adapter.py`). Design §6.2 는 subject 포함 | `IdentityUnavailableError` 에 주체 동봉 |
| G-5 | Minor | 95% | PATCH mailbox 320자 초과는 pydantic 이 422, 256~320자는 도메인 400 | `max_length` 제거(도메인이 판정) |
| G-6 | Docs | 95% | Design §9.4·§11.1 에 `identity_config.py` 누락, 부록 B 에 평가 헤드리스 런·승인 재개 경로 누락 | Design v0.3 갱신 |

**열린 결정 (갭 아님)**: 일반 채팅(부록 B #8) — 공용 캐시 때문에 미배선. 목록에서 신원 서버 제외 vs 사용자별 캐시.

**운영 메모 (코드 갭 아님)**: 사용자 7 메일함이 `sender@` 로 바뀌었고 Application Access Policy 가 `test@` 만 허용한다 → 현재 에이전트는 `MAILBOX_ACCESS_DENIED`. 정책 그룹에 sender@ 추가(런북 6단계) 또는 메일함을 test@ 로.

## 4. Test Coverage

| 영역 | 테스트 | 결과 |
|------|--------|------|
| 백엔드 신규 | 15개 파일, 123건 | 전부 통과 |
| 백엔드 전체 | module-3 후 | 53건 실패 = master 상시 목록과 동일 (신규 0) |
| 프론트 신규 | 3개 파일, 29건 | 전부 통과 |
| 프론트 전체 | module-4 후 | 기준 9건/4파일과 동일 (병렬 부하 flake 2파일 별도) |
| 타입·린트 | tsc 210건 = 기준, 수정 파일 lint 0 | 신규 0 |

Design §8.2 L1 #1~#17 과 §8.3 L2 #1~#6 은 모두 대응 테스트가 있다.

## 5. Clean Architecture Compliance

domain 은 jose·SQLAlchemy 를 import 하지 않는다. 서명은 infrastructure, 흐름은 application, 규칙(`IdentityClaimPolicy`·`merge_update`·`validate_identity_headers`)은 domain. Repository commit 없음. 위반 0.

## 6. Recommended Actions

1. **G-1 수정** (Critical) — `/run` 주체 강제 + 테스트
2. G-2 ~ G-5 (Minor) — 같은 iterate 에서 처리 가능, 각각 수 줄
3. G-6 — Design v0.3
4. 일반 채팅 처리 방향 결정

## 7. Act-1 Iteration (2026-09-26)

사용자 결정: "지금 모두 수정" + 일반 채팅은 "목록에서 제외".

| # | 수정 | 증거 |
|---|------|------|
| G-1 | `POST /agents/{id}/run` 이 `body.user_id` 를 토큰 사용자로 덮어쓴다 (`agent_builder_router.py`) | `test_run_agent_subject_binding.py` 2건. 실런(토큰 1·본문 7)은 에이전트 권한 검사로 403 — 공유 에이전트 시나리오는 단위 테스트로 검증 |
| G-2 | 공급자 단계 실패를 `HeaderProviderError` 로 감싼다. 집행기 `blocked`, call client 재시도 없음 | `test_identity_provider_failures.py`, `test_HeaderProviderError는_blocked` |
| G-3 | 복호화 실패·키 누락 시 `identity_config_unreadable=True` → `requires_identity=True`, 공급자는 `IdentityConfigUnreadableError`, 필드 없는 PUT 거부 | `test_identity_check_fixes.py` 4건, 매핑 테스트 3건 갱신 |
| G-4 | `IdentityUnavailableError.subject`, 차단 로그 `identity_sub` | `test_신원_차단_로그에_주체가_남는다` |
| G-5 | 요청 스키마 `max_length` 제거 — 길이는 도메인이 400 | `test_긴_값도_도메인이_판정해_400` |
| G-6 | Design v0.3 — §6.2·§9.4·§11.1·부록 B #9·#10·주체 신뢰 규칙 | 문서 |
| 결정 | 일반 채팅 `LoadMCPToolsUseCase(exclude_identity_servers=True)` | `TestGeneralChatExclusion` 2건 |

**회귀**: 백엔드 전체 53 failed / 10,034 passed — 실패 목록이 master 상시 목록과 동일(신규 0).

### Re-scored Match Rate

| Axis | Before | After |
|------|:------:|:-----:|
| Structural | 98% | 100% |
| Functional | 91% | 100% |
| Contract | 95% | 100% (422 는 승인 편차) |
| Runtime | 88% | 90% (SC-3 실집행은 비가역이라 단위 검증 유지) |
| **Overall** | **93%** | **96.5%** |

남은 항목 (갭 아님): SC-3 실집행 검증, 테넌트 정책에 sender@ 추가(운영), 서명 비밀 교체(대화에 노출됨).

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-26 | Initial analysis — 93%, Critical 1 (G-1) | 배상규 / Claude |
| 0.2 | 2026-09-26 | Act-1 — G-1~G-6 수정, 일반 채팅 제외, 96.5% | 배상규 / Claude |
