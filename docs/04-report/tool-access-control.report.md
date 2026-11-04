# tool-access-control Completion Report

> **Feature**: 부서·사용자별 도구 권한
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-04
> **Status**: Completed (Check 95.0%, Act 1회) — 미커밋, worktree `wt/tool-access-control`, 브랜치 `feature/tool-access-control`

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| 문제 | 도구 카탈로그·실행에 부서·사용자 조건이 없어, 로그인한 누구나 MCP·코드 실행기 등 모든 도구로 사내 시스템과 자료에 접근할 수 있었다. |
| 범위 | 백엔드(판정 정책·저장소·관리 API·목록·저장·포크·실행·승인 집행) + 프론트(관리자 화면·빌더·채팅·포크 안내) |
| 기간 | 2026-11-03 Plan → 2026-11-04 Report |

### 1.2 Results Summary

| 항목 | 결과 |
|------|------|
| Match Rate | 90.2% → **95.0%** (Act-1) |
| 성공 기준 | 9개 중 ✅ 6 · ⚠️ 2 · ❓ 1 (§1.4) |
| 회귀 | 백엔드 실패 53건 = master 상시 실패 동일, 프론트 vitest 실패 9건 동일·tsc/eslint 새 오류 0 |
| 런타임 확인 | 인프로세스 스모크 4회(관리 API, 목록·저장·포크, 에이전트 실런 REST·WS, 일반 채팅 실런) + 브라우저 확인 1회 |

### 1.3 Value Delivered

| 관점 | 전달된 내용 |
|------|------------|
| **Problem** | 권한과 관계없이 모든 도구가 열려 있던 상태를 기본 차단으로 바꿨다. 판정 대상은 에이전트 실행 8경로(채팅 REST·SSE·WS, 웹훅, 잡, 스케줄, 승인 재개, RAGAS)와 일반 채팅(REST·WS), 승인 집행이다. |
| **Solution** | 기본 허용 세트 ∪ 부서 허용 ∪ 사용자 허용(합집합)을 테이블 3개(FK CASCADE)에 저장하고, 판정 정책 1개를 목록·저장·포크·실행·승인 집행이 함께 쓴다. 배포 시 현재 카탈로그 도구를 전부 기본 세트로 시드해 동작 변화가 없다. |
| **Function/UX Effect** | 관리자는 `/admin/tool-access`에서 부서·사용자를 고르고 도구를 체크한다(기본·부서 상속분은 잠금 배지). 일반 사용자는 허용 도구만 고를 수 있고, 권한 없는 도구가 붙은 에이전트는 그 도구만 빠진 채 실행되며 답변 아래에 안내가 나온다. 빌더는 붙어 있으나 권한 없는 도구를 "권한 없음" 칩으로 보여 준다. |
| **Core Value** | P2가 만든 에이전트를 전 부서에 배포해도 각 사용자는 자신에게 허용된 도구로만 자료에 접근한다. 접근 범위 조정은 코드 수정 없이 관리자 화면에서 한다. |

## 1.4 Success Criteria Final Status

| # | 기준 (Plan §4) | 상태 | 근거 |
|---|----------------|:----:|------|
| SC-1 | FR-01~17 구현 + 테스트 | ✅ | §3.1 |
| SC-2 | 모든 실행 경로·서브에이전트에서 권한 없는 도구 미바인딩 | ✅ | 단일 조립점(`_build_run_agent_uc`) 주입, compile 첫머리 워커 필터, AST 계약 테스트, 컴파일 그래프 테스트, 에이전트 실런(REST·WS), 일반 채팅 실런 |
| SC-3 | 시드 후 기존 동작 변화 0건 | ⚠️ | 카탈로그 37 = 기본 세트 37 확인. 단 **미동기화 MCP 서버는 시드에서 빠짐**(G-08) → 배포 전 MCP 전체 동기화가 전제. 전용 동치 테스트 없음 |
| SC-4 | 백엔드↔프론트 타입 동기화 | ✅ | `types/toolAccess.ts`, `agentStore.ts`, `websocket.ts`, `chat.ts` |
| SC-5 | 배포 의존성 문서 반영 대상 기록 | ✅ | §8.1 (위키 갱신은 `/wiki update` 호출 시) |
| SC-6 | 수동 E2E 1회 | ✅ | 브라우저: 관리자 화면 3탭·빌더 칩·채팅 안내(실 LLM) |
| QC-1 | 신규 코드 커버리지 80% | ❓ | 미측정 |
| QC-2 | 신규 실패 0건 | ✅ | FAILED 목록 diff |
| QC-3 | DDL 검사 | ⚠️ | `tests/db` 통과·로컬 MySQL 적용 확인, FK·CASCADE 자동 테스트는 없음(SQLite 는 FK 미강제) |

**Success Rate**: 6/9 ✅

## 1.5 Decision Record Summary

| 출처 | 결정 | 준수 | 결과 |
|------|------|:----:|------|
| Plan | 부서 + 사용자 합집합 (deny 없음) | ✅ | 판정 규칙 단순, `PermissionResolver`와 같은 방식 |
| Plan | 기본 차단 + 살아있는 기본 세트, 현재 도구 전부 시드 | ✅ | 배포 직후 에이전트 동작 동일. 미동기화 서버는 예외(G-08) |
| Plan | 목록·저장·실행 3지점 판정 | ✅ | Check 에서 일반 채팅 경로 누락을 찾아 Act-1 에서 추가 |
| Plan | 권한 없는 도구는 빼고 실행 + 안내 | ✅ | 실런에서 도구 미호출 + 안내 확인 |
| Plan | 저장은 신규 추가 도구만 검증, 포크는 제외 복제 | ✅ | 다른 부서원이 쓰던 도구가 소유자 저장으로 사라지지 않음 |
| Plan | 관리 주체는 시스템 관리자, 화면은 부서·사용자 중심 | ✅ | |
| Design | 설계안 C (정책 1 + Resolver 1, compile 첫머리 필터) | ✅ | 전용 노드·서브에이전트까지 한 지점에서 처리 |
| Design | 테이블 3개 + FK CASCADE, tool_catalog 컬럼 추가 없음 | ✅ | sync 코드 무변경, 삭제 시 규칙 자동 정리 |
| Design | auth_ctx 없는 경로는 user_id 로 판정 | ✅ | 스케줄·승인 재개·RAGAS 의 기존 동작(메모리 주입 등) 무변경 |
| Design | 승인 집행 직전 재확인 | ✅ | 승인 대기 중 권한 회수 시 외부 호출 전 차단 |
| Do | MCP 레지스트리 조회도 admin | ✅ | 사내 서버 주소 비노출 |
| Do | 추천 후보(파이프라인·컴포저)도 필터 | ✅ | 추천과 저장 기준 일치 |
| Check | 미동기화 MCP 서버는 배포 절차로 해결 | ✅ | 코드 변경 없음, §8.1 |

## 2. Related Documents

- Plan: `docs/01-plan/features/tool-access-control.plan.md` (v0.2)
- Design: `docs/02-design/features/tool-access-control.design.md` (v0.6)
- Analysis: `docs/03-analysis/tool-access-control.analysis.md` (v0.2)

## 3. Completed Items

### 3.1 Functional Requirements

| FR | 내용 | 상태 |
|----|------|:----:|
| FR-01 | 규칙 저장(기본·부서·사용자) + 부여자·시각 | ✅ |
| FR-02 | 판정 정책(admin 전부, 그 외 합집합, 익명 차단) | ✅ |
| FR-03 | 현재 카탈로그 전부 시드, 이후 sync 도구는 기본 차단 | ✅ (G-08 운영 전제) |
| FR-04 | 관리자 조회·PUT API (사용자 상속분 출처 포함) | ✅ |
| FR-05 | 카탈로그 조회 필터 | ✅ |
| FR-06 | 저장 시 신규 도구 검증 (403 TOOL_ACCESS_DENIED + tool_ids) | ✅ |
| FR-07 | 권한 없는 빌트인 미주입 | ✅ |
| FR-08 | 포크 제외 복제 + excluded_tools + 도구 안내 블록 재생성 | ✅ |
| FR-09 | 실행 시점 필터 (메인·서브에이전트·카테고리·전용 노드) | ✅ |
| FR-10 | 실행 주체 (채팅 사용자·등록자·소유자·요청자) | ✅ |
| FR-11 | 제외 안내 (모델 지시문 + 응답 필드 + 로그) | ✅ (실행 기록은 구조화 로그로 한정) |
| FR-12 | 레거시 서버 단위 MCP 는 허용 도구만 | ✅ |
| FR-13 | 상세 `tool_access` + 빌더 "권한 없음" 칩 | ✅ |
| FR-14 | 관리자 화면 (3탭, 잠금·배지, 서버별 일괄 선택) | ✅ |
| FR-15 | 상태 배지 (기본 세트 아님·빌트인 비기본·승인 필요) | ✅ ("미지정(차단)" → "기본 세트 아님") |
| FR-16 | MCP 레지스트리 인증 (조회 포함 admin) | ✅ |
| FR-17 | 도구·부서·사용자 삭제 시 규칙 정리 | ✅ (DDL CASCADE, 로컬 MySQL 확인) |
| 추가 | 레거시 `/api/v2/agents`·`/api/v3/agents/auto` admin 잠금, 일반 채팅 판정, 추천 후보 필터, `wiki_list` 동봉 판정 | ✅ |

### 3.2 Non-Functional Requirements

| 항목 | 결과 |
|------|------|
| Security — 서버 판정이 화면 필터와 독립 | ✅ API 직접 호출 403 확인 |
| Security — MCP 레지스트리 무인증 401 / 비관리자 403 | ✅ 라우트 순회 계약 테스트 |
| Compatibility — 응답은 optional 필드 추가만 | ✅ 프론트 회귀 0 |
| Performance — 실행당 판정 조회 1~3회 | ✅ auth_ctx 경로 1회(UNION), user_id 경로 3회 |
| Regression — FAILED diff 신규 0 | ✅ |

### 3.3 Deliverables

| 구분 | 내용 |
|------|------|
| DB | `V082__create_tool_access_tables.sql`, `V083__seed_tool_access_default.sql` |
| 백엔드 | `domain/tool_access/`, `application/tool_access/`(resolver·admin UseCase·validation·checker), `infrastructure/tool_access/`, `api/routes/admin_tool_access_router.py`, compile·ToolFactory·RunAgentUseCase·GeneralChatUseCase·Create/Update/Fork/Get·카탈로그·파이프라인·컴포저·승인 집행기 수정, `main.py` DI(`make_tool_access_resolver` 단일 생성 함수) |
| 프론트 | `pages/AdminToolAccessPage`, `components/admin/tool-access/ToolAccessChecklist`, `hooks/useToolAccess`, `services/toolAccessService`, `types/toolAccess`, `utils/toolAccess`, 빌더 칩·저장 403 안내·채팅 안내·포크 안내, `ApiError.detail` |
| 테스트 | 도메인·Resolver·저장소(aiosqlite)·관리 UseCase·라우터·인증 계약·DI 배선(AST 포함)·컴파일 그래프·실행·일반 채팅·승인 집행 / 프론트 훅·체크리스트·페이지·빌더·채팅·포크 모달 |

## 4. Incomplete Items

### 4.1 Carried Over

| 항목 | 이유 |
|------|------|
| 빌더 테스트 패널(TestChatView) 제외 안내 | Design 범위 밖, 화면 단독 작업 |
| 승인 재개 답변의 제외 안내 (G-07) | 재개 답변은 저장만 되는 경로라 안내를 실을 응답이 없음 |
| 채팅 안내 히스토리 유지 | `excluded_tools` 미저장 — 저장하려면 메시지 스키마 변경 필요 |
| 경로별 전용 테스트(웹훅·잡·스케줄·RAGAS), 시드 동치 테스트(R13), CASCADE 자동 테스트 | 공통 경로 테스트·로컬 DB 확인으로 대체 |
| 커버리지 측정, `tsc -b` | 미실행 |

### 4.2 Out of Scope (Plan §2.2 유지)

deny 규칙, 부서 관리자 역할, 서버 단위 규칙, 역할 그룹, 권한 변경 이력 화면.

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | 점수 |
|----|:----:|
| Structural | 97 |
| Functional | 95 |
| Contract | 98 |
| Runtime | 92 |
| **Match Rate** | **95.0%** |

### 5.2 Resolved Issues (Check → Act-1)

| ID | 내용 | 조치 |
|----|------|------|
| G-01 (Critical) | 일반 채팅이 모든 MCP 도구를 권한 없이 바인딩 | `GeneralChatUseCase._permitted_tools` |
| G-02 (Important) | `/api/v3/agents/auto` 무인증 | 라우터 admin 잠금 |
| G-03 | 강등 답변에 excluded_tools 누락 | 스트림 상태 공유 |
| G-04 | 정규화 규칙 사본 | 도메인 함수 위임 |
| G-06 | Design DDL 예시 | 문구 정정 |
| G-08 (운영) | 미동기화 MCP 서버가 시드에서 빠짐 | 배포 절차 + 로컬 DB 보정 |

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **Design 단계에서 Plan 가정을 코드로 다시 확인했다.** "비대화 실행은 모두 auth_ctx 를 넘긴다"는 가정이 틀렸음을 Design §0 에서 찾아, 스케줄·승인 재개·RAGAS 를 user_id 판정으로 설계에 반영했다.
- **판정 지점을 compile 첫머리 한 곳에 둔 것이 유효했다.** `ToolFactory`를 거치지 않는 전용 노드와 서브에이전트가 별도 작업 없이 함께 처리됐다.
- **배선 계약 테스트(AST)로 "주입이 빠지면 판정이 조용히 사라지는" 위험을 고정했다.**
- **모듈마다 실제 앱 스모크를 돌렸다.** 단위 테스트로는 보이지 않던 사실(MCP 레지스트리 조회 응답의 서버 주소 노출, 미동기화 서버의 시드 누락)을 찾았다.

### 6.2 What Needs Improvement (Problem)

- **실행 경로 조사를 `RunAgentUseCase` 호출자로만 한정해 일반 채팅 경로를 놓쳤다.** 가장 노출이 큰 메인 채팅이 Check 까지 무방비였다. 도구를 바인딩하는 모든 UseCase 를 기준으로 조사했어야 했다.
- **실런 스모크 중 WS 실행이 대화 이력을 남긴다는 사실을 놓쳐**, "이력을 남기지 않는다"는 안내와 다르게 테스트 메시지가 저장됐다(이후 해당 행만 삭제).
- 저장소 FK·CASCADE 는 SQLite 로 검증되지 않아 로컬 MySQL 수동 확인에 의존했다.

### 6.3 What to Try Next (Try)

- 접근 통제 기능의 Design §0 에는 "호출자 목록"이 아니라 **"자원(도구)을 실제로 바인딩·호출하는 지점 목록"**을 grep 으로 만들고 시작한다(`create_agent(`, `bind_tools`, `ToolFactory`, `load_mcp` 등).
- 배포 시드가 다른 데이터(카탈로그 동기화 상태)에 의존하는지 Plan 리스크에 넣는다.

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

- Check 의 gap-detector 를 메인 세션 결론 없이 독립 실행한 것이 일반 채팅 누락을 찾는 데 결정적이었다 — 접근 통제·보안 기능은 독립 대조를 기본으로 한다.

### 7.2 Tools/Environment

- 프론트 브라우저 확인은 CORS 가 5173 으로 고정돼 있어 스크래치 런처로 출처를 추가해야 했다. CORS 허용 출처를 설정으로 빼면 worktree 병행 확인이 쉬워진다(별도 소형 사이클 후보).

## 8. Next Steps

### 8.1 Immediate — 배포 체크리스트 (필수)

1. **배포 전 모든 MCP 서버 카탈로그 동기화** (`/admin/mcp-servers` 또는 `POST /api/v1/tool-catalog/sync`) — 동기화 안 된 서버의 도구는 V083 시드에서 빠져 배포 직후 일반 사용자가 잃는다.
2. V082 → V083 순서 적용. V082 는 `tool_catalog`·`users`·`departments` FK 를 참조한다(CHARSET/COLLATE 명시 금지 규칙 준수).
3. 배포 후 관리자가 기본 세트에서 민감 도구(MCP 쓰기·메일·코드 실행 등)를 빼고 부서·사용자로 좁힌다 — 시드 직후에는 기존과 같이 전부 열려 있다.
4. `docs/wiki/ops/migration-deploy-deps.md` 에 V082·V083 과 위 1번 의존성을 추가 (`/wiki update` 시).
5. 로컬 DB 는 V082·V083 적용 완료(재적용 금지), Doc Convert MCP 동기화 및 기본 세트 추가 완료(기본 세트 41).

### 8.2 Next PDCA Cycle 후보

- 빌더 테스트 패널 제외 안내, 채팅 안내 영구 저장
- 경로별 테스트 보강(웹훅·잡·스케줄·RAGAS, R13 시드 동치, CASCADE 통합)
- `USE_WEB_SEARCH` 권한 코드 정리(정의만 있고 확인 코드 없음 — Plan 단계 보고 사항)
- CORS 허용 출처 설정화

## 9. Changelog

### v1.0.0 (2026-11-04)

- 추가: 도구 허용 규칙(기본·부서·사용자), 관리자 도구 권한 API·화면, 목록·저장·포크·실행·일반 채팅·승인 집행 판정, 제외 안내(응답·모델 지시문·화면)
- 변경: MCP 레지스트리·레거시 `/api/v2/agents`·`/api/v3/agents/auto` admin 전용, 카탈로그 조회는 실행자 기준
- DB: V082(테이블 3개), V083(기본 세트 시드)

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-11-04 | 완료 보고 — Match 95.0%, 성공 기준 6/9, 배포 체크리스트 포함 | 배상규 |
