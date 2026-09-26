# mcp-identity-header Completion Report

> **Summary**: MCP 호출마다 실행 주체의 신원을 HS256 서명 토큰 헤더로 주입해, 공용 Outlook MCP 서버 하나가 사용자별 메일함을 안전하게 다루게 했다
>
> **Project**: sangplusbot (idt + idt_front)
> **Author**: 배상규 / Claude
> **Date**: 2026-09-26
> **Status**: Completed (Match Rate 96.5%, Act 1회)

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| Feature | mcp-identity-header |
| 기간 | 2026-09-26 (Plan → Design → Do 4모듈 → Check → Act-1 → Report, 단일 일자) |
| 범위 | 백엔드(도메인·런타임 주입·관리자 API) + 관리자 화면 2개 |
| 선택 설계 | Option C — 전용 암호화 컬럼, 호출 직전 발급, 주체 인자 전달 |

### 1.2 Results Summary

| 지표 | 결과 |
|------|------|
| Match Rate | 93% → **96.5%** (Act-1) |
| 기능 요구사항 | 11/11 |
| Success Criteria | 5/6 충족, 1 부분(SC-3 — 비가역 발송이라 단위 검증) |
| 신규 테스트 | 백엔드 18개 파일, 프론트 3개 파일 29건 — 전부 통과 |
| 회귀 | 백엔드 53건 실패 = master 상시 목록 (신규 0), 프론트 9건 = 기준선 (신규 0) |
| DB | V076 `users.mailbox_upn`, V077 `mcp_server_registry.identity_config_enc` (로컬 적용) |

### 1.3 Value Delivered

| 관점 | 계획 | 실제 결과 |
|------|------|-----------|
| **Problem** | Outlook MCP 는 사용자별 메일함을 지원하지만 idt 는 정적 헤더만 보내 공용 메일함 1개로만 운영 가능 | identity 모드 Outlook 서버가 idt 서명 토큰을 받아들이고 토큰의 메일함으로만 Graph 를 호출하는 것을 실런으로 확인 |
| **Solution** | 회원별 메일함 등록 + 호출 시점 서명 토큰 주입 (MCP 호출 계층 공통 기능) | `create_session` 단일 주입 지점. 에이전트 워커·서브에이전트·승인 즉시/예약 집행·승인 재개가 모두 같은 지점을 지난다 |
| **Function/UX Effect** | 관리자는 화면에서 설정, 사용자는 "내 메일 보여줘"로 본인 메일함 조회 | 관리자가 실제로 화면에서 메일함을 등록했다. 미등록 사용자는 "메일함이 등록되지 않았습니다. 관리자에게 등록을 요청하세요." 안내로 끝나고 서버에 요청이 가지 않는다 |
| **Core Value** | 메일함 결정권을 LLM·편집값에서 플랫폼 인증 경로로 이동 | 클레임 출처는 `users` 행뿐. Check 에서 `/run` 본문 `user_id` 위조 경로(G-1)를 발견해 토큰 사용자로 강제했다 |

## 1.4 Success Criteria Final Status

| SC | 기준 | 상태 | 증거 |
|----|------|:----:|------|
| SC-1 | 두 사용자가 각자 메일함 결과 | ✅ | 실런: 신원 A(sender@)·B(test@) 가 서로 다른 메일함으로 해석. 에이전트 실런도 토큰 수용 |
| SC-2 | 미등록 사용자는 서버 요청 없음 | ✅ | 실런: 사용자 8 → 안내문, call 세션 0회 |
| SC-3 | 스케줄·승인 집행이 생성자·요청자 신원 | ⚠️ | 단위 테스트 3건 (승인자가 아닌 요청자). send_mail 실발송은 비가역이라 생략 |
| SC-4 | 미설정 서버 무변화 | ✅ | 실런: Scrap MCP 헤더 공급자 없음 |
| SC-5 | 관리자가 화면만으로 설정 | ✅ | Vitest L2 전 항목 + 실사용 |
| SC-6 | 비밀·토큰 원문 미노출 | ✅ | 실 PUT 응답 `secret: "****"`, 로그 필드 제한 테스트 |

**Success Rate**: 5/6 (83%) 충족 + 1 부분

## 1.5 Decision Record Summary

| 단계 | 결정 | 준수 | 결과 |
|------|------|:----:|------|
| Plan | 메일 전용 노드가 아니라 MCP 호출 계층 공통 기능 | ✅ | 일반화 원칙 준수. 다른 사용자별 MCP 도 같은 설정으로 재사용 가능 |
| Plan | 메일함 = `users.mailbox_upn` (로그인 email 과 분리) | ✅ | V076 |
| Plan | HS256 + 서버별 비밀·audience | ✅ | 서버 `HmacTokenVerifier` 규칙 교차 테스트 통과 |
| Plan | 신원 소스 = 실행 요청 사용자 ID (스케줄엔 인증 컨텍스트 없음) | ✅ (Act 보강) | `/run` 은 토큰 사용자로 강제 |
| Plan | 전 실행 경로 허용 | ⚠️ 변경 | Check 에서 일반 채팅은 **제외**로 결정 (전 사용자 공용 캐시) |
| Design | Option C: 전용 컬럼 / 호출 직전 발급 / 인자 전달 | ✅ | `ToolFactory._auth_ctx` 싱글톤 가변 필드 미사용 |
| Do | 미배선 로더는 헤더 없이 보내지 않고 배선 오류 | ✅ | Design 부록 B 에 규칙 명시 |
| Do | MCP 등록 검증 오류 422 유지 (Design 400) | 승인 편차 | 기존 라우터 관례 |

---

## 2. Related Documents

| 문서 | 경로 |
|------|------|
| Plan | `./mcp-identity-header.plan.md` |
| Design (v0.3) | `./mcp-identity-header.design.md` |
| Analysis (v0.2) | `./mcp-identity-header.analysis.md` |
| 서버 계약 | `agent_mcp/docs/02-design/features/mcp-outlook-server.identity-contract.md` |

## 3. Completed Items

### 3.1 Functional Requirements

FR-01 ~ FR-11 전부 완료 — 상세 근거는 Analysis §2.4.

### 3.2 Non-Functional Requirements

| 항목 | 결과 |
|------|------|
| 보안: 클레임 출처 `users` 행 한정, 발급 헤더 최후 병합(대소문자 무시) | ✅ |
| 보안: 토큰 ≤300초, HS256 고정, 호출마다 신규 | ✅ |
| 호환: 기존 MCP 서버 회귀 없음 | ✅ 전체 스위트 신규 실패 0 |
| 아키텍처: domain 에 jose·SQLAlchemy 없음 | ✅ |

### 3.3 Deliverables

| 구분 | 내용 |
|------|------|
| 백엔드 신규 | `domain/mcp_registry/identity.py`, `infrastructure/mcp_registry/identity_token.py`·`identity_headers.py`, `application/mcp_registry/identity_config.py`, `application/auth/update_user_mailbox_use_case.py` |
| 백엔드 수정 | 세션 팩토리·도구 어댑터·레지스트리·호출 클라이언트·로더·도구 팩토리·컴파일러·런 UseCase·승인 집행 체인·관리자/레지스트리 라우터·DI |
| 마이그레이션 | V076, V077 (테이블·컬럼 COMMENT, ORM `comment=` 일치) |
| 프론트 신규 | `UserMailboxCell`, `McpIdentityFields`, `utils/mcpIdentityForm.ts` |
| 프론트 수정 | `AdminUsersPage`(메일함 열), `AdminMcpServersPage`(신원 섹션·배지), 타입·서비스·훅·API 상수 |
| 문서 | Plan, Design v0.3, Analysis v0.2, 본 보고서 |

## 4. Incomplete Items

### 4.1 Carried Over

| 항목 | 이유 |
|------|------|
| SC-3 실집행(스케줄·승인 send_mail) 검증 | 실제 메일 발송은 비가역 — 테스트 수신자 합의 후 수행 |
| 사용자 7 메일함(sender@) 테넌트 접근 정책 추가 | 운영 작업 (Outlook 서버 런북 6단계). 현재 `MAILBOX_ACCESS_DENIED` |
| 서명 비밀 교체 | 이번 대화에 원문이 노출됨 — 실사용 전 컨테이너·관리자 화면 동시 교체 |
| 연결 테스트가 "서버 identity 모드 ↔ 등록 신원 미설정" 불일치를 알리는 기능 | Check 중 사용자 첫 실행에서 드러난 운영 함정. 현재는 서버 거부 메시지가 그대로 노출 |

### 4.2 Cancelled / Out of Scope

Entra SSO 연동, 비밀 무중단 회전, 범용 사용자 속성 테이블, list_tools 신원 주입 — Plan §2.2 그대로.

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Axis | Score |
|------|:-----:|
| Structural | 100% |
| Functional | 100% |
| Contract | 100% |
| Runtime | 90% |
| **Overall** | **96.5%** |

### 5.2 Resolved Issues (Act-1)

| # | 심각도 | 내용 | 조치 |
|---|:------:|------|------|
| G-1 | Critical | `POST /run` 본문 `user_id` 로 남의 메일함 토큰 발급 가능 | 토큰 사용자로 강제 |
| G-2 | Minor | 연결 전 공급자 실패가 승인 결과 '불명'으로 기록 | `HeaderProviderError` → `blocked` |
| G-3 | Minor | 복호화 실패 설정이 '미설정'으로 읽혀 다음 수정에서 삭제 | `identity_config_unreadable` fail-closed + 필드 없는 PUT 거부 |
| G-4 | Minor | 차단 로그에 주체 없음 | `identity_sub` |
| G-5 | Minor | 메일함 길이 오류 422/400 혼재 | 도메인이 400 으로 판정 |
| G-6 | Docs | 설계 문서 누락 | Design v0.3 |

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **서버 계약을 먼저 읽고 설계**: `mcp-outlook-server` 의 검증기 규칙(PyJWT 옵션·수명 상한)을 테스트로 그대로 재현해, 실런 전에 토큰 호환성을 확정했다.
- **호출 경로 전수 표(부록 B)**: 설계 때 경로를 표로 박제해 두어 Do 중 일반 채팅 경로(#8)를 새로 발견했을 때 바로 판단·기록할 수 있었다.
- **모듈마다 전체 스위트 대조**: master 상시 실패 목록과 `comm` 으로 대조해 4모듈 + Act 내내 회귀 0 을 수치로 확인했다.
- **실런 병행**: 단위 테스트가 통과한 뒤에도 실 DB·실 서버로 매 모듈을 확인해 `ApiError` 인터셉터 함정, 로컬 DB 미적용 위험을 초기에 잡았다.

### 6.2 What Needs Improvement (Problem)

- **입력 신뢰 경계를 Plan 에서 놓쳤다**: "주체 = 실행 요청 user_id" 로 정하면서 그 값을 누가 채우는지(진입점별)를 확인하지 않았다. `/run` 위조 경로(G-1)는 Check 에서야 드러났다.
- **"설정 누락"과 "설정 손상"을 같은 None 으로 표현**: 초기 구현이 복호화 실패를 미설정으로 읽어, 헤더 누락·설정 삭제 위험(G-3)을 만들었다.
- **운영 전환 체크리스트가 한쪽만**: 서버를 identity 모드로 바꾼 뒤 idt 등록 설정을 빠뜨리면 사용자에게 서버 오류가 그대로 보였다 — 사용자의 첫 실행이 이것이었다.

### 6.3 What to Try Next (Try)

- Plan 단계에서 "이 값의 출처(진입점별)와 위조 가능성" 표를 요구사항에 포함한다.
- 저장 경계의 "없음 / 못 읽음"을 처음부터 다른 상태로 모델링한다.
- 서버·플랫폼 양쪽 설정이 필요한 기능은 연결 테스트가 불일치를 진단하도록 설계에 넣는다.

## 7. Process Improvement Suggestions

| 영역 | 제안 |
|------|------|
| PDCA | gap-detector 에이전트는 파일 쓰기 도구가 없어 보고서 파일을 못 남기고 턴 한도에 걸렸다 — 범위를 축별로 나눠 병렬 호출하거나 요약 반환만 요구 |
| 테스트 | 프론트 전체 병렬 실행 시 부하 flake 2파일 — 기준선 판정은 단독 재실행과 병행 |
| 환경 | 로컬 DB 에 Flyway 이력이 없다 — 마이그레이션 적용이 수동 스크립트에 의존 |

## 8. Next Steps

### 8.1 Immediate

1. 서명 비밀 교체 (Outlook 컨테이너 `MCP_IDENTITY_SECRET` + 관리자 화면)
2. 테넌트 Application Access Policy 에 사용 메일함(sender@ 등) 추가
3. 커밋·PR — 작업 트리에 무관한 변경(거부 가드 등)이 섞여 있으므로 이 기능 파일만 선별

### 8.2 Next PDCA Cycle

- 연결 테스트의 신원 설정 불일치 진단
- 테스트 수신자 합의 후 SC-3 실집행 검증
- 다른 사용자별 MCP(캘린더·고객문의)에 같은 계약 적용 검토

## 9. Changelog

### v1.0.0 (2026-09-26)

- **Added**: MCP 서버별 호출자 신원 헤더(HS256, 호출 시점 발급), 회원 메일함 UPN, 관리자 메일함 PATCH API, 관리자 화면 메일함 열·신원 헤더 섹션
- **Changed**: 승인 집행 인터페이스에 요청자 주체 전달, 일반 채팅 도구 목록에서 신원 서버 제외
- **Fixed**: `POST /agents/{id}/run` 본문 `user_id` 를 토큰 사용자로 강제

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-09-26 | Completion report | 배상규 / Claude |
