# MCP Tool Auto Sync Completion Report

> **Status**: Complete (검증 공백 2건은 QA 이관)
>
> **Project**: sangplusbot (idt 백엔드 + idt_front)
> **Version**: 0.1.0
> **Author**: 배상규
> **Completion Date**: 2026-09-01
> **PDCA Cycle**: #1

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | mcp-tool-auto-sync — MCP 서버 등록/수정 시 도구 카탈로그 자동 반영 |
| Start Date | 2026-08-31 |
| End Date | 2026-09-01 |
| Duration | 2일 (Plan → Design → Do → Check → Report) |
| Iteration | 0회 (Match Rate 98%로 첫 Check에서 목표 초과) |

### 1.2 Results Summary

```
┌──────────────────────────────────────────────┐
│  Match Rate: 98%          (목표 90%)          │
├──────────────────────────────────────────────┤
│  ✅ 요구사항 완료:   13 / 13 (FR-01~FR-13)     │
│  ✅ UI 체크리스트:    9 / 9                    │
│  ✅ Success Criteria: 6 / 8 완전, 2 부분       │
│  ❌ Critical 갭:      0건                      │
│  ⚠️ Important 갭:     2건 (실서버 검증 공백)    │
└──────────────────────────────────────────────┘

테스트: 백엔드 123 passed / 프론트 17 passed (신규 26건)
회귀:   백엔드 0건 / 프론트 0건 (baseline 대조)
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | MCP 서버를 등록해도 `tool_catalog`에 단 한 행도 생기지 않아 **도구 선택창에 영원히 뜨지 않았다.** 반영 경로인 `POST /tool-catalog/sync`는 백엔드에만 존재하고 호출자가 전무했으며(프론트에 상수조차 없음), 부작용으로 원 설계 Q5(서버 비활성화 시 도구 비활성화)도 함께 죽어 있었다. 결과적으로 "MCP 서버 등록" 기능이 **화면상 무효과** 상태였다 |
| **Solution** | 등록/수정 UseCase가 같은 DB 세션으로 `SyncMcpToolsUseCase`를 호출하되, 예외를 `SQLAlchemyError`(재전파)와 그 외(흡수)로 **분류**해 세션 오염 없이 best-effort를 보장했다. 결과를 `SyncOutcome` → 응답 `tool_sync`로 실어 관리 화면이 실패를 인지하게 하고, 서버별 [동기화] 버튼으로 복구·재동기화 경로를 열었다 |
| **Function/UX Effect** | 관리자 조작 **2회 → 0회** (정상 경로). 실서버 실측으로 **MCP 서버가 죽어 있어도 등록 HTTP 201 유지** 확인. 실패 시 amber 배너 + 진단 힌트가 뜨고 버튼 1회로 재시도된다. 원 설계 Q5 비활성화 연동도 되살아났다 |
| **Core Value** | MCP 확장 경로의 **마지막 끊긴 고리**를 이었다. 이 갭 때문에 플랫폼의 외부 도구 확장성이 실사용에서 검증조차 되지 않았는데, 이제 등록→노출이 1스텝이고 실패해도 막다른 길이 없다 |

---

## 1.4 Success Criteria Final Status

| # | Criteria (Plan §4.1) | 상태 | 근거 |
|---|---------------------|:----:|------|
| SC-1 | FR-01~FR-13 전부 구현 | ✅ Met | Analysis §2 대조표 13/13 |
| SC-2 | 등록 → 추가 조작 없이 `mcp:{id}:{tool}` 노출 | ✅ Met | `sync_mcp_tools_use_case.py:47` + `test_register_tool_sync.py` |
| SC-3 | 도달 불가 endpoint여도 201 + warning 1건 | ✅ Met | **실서버 실측 HTTP 201** + `tool_sync.ok=false` |
| SC-4 | 실패 표시 + 버튼 복구 (막다른 길 없음) | ⚠️ Partial | L1(응답)·L2(UI mock) 검증. 실서버 버튼 클릭 복구 미실행 → **G-01** |
| SC-5 | `is_active=false` → 도구가 목록에서 사라짐 | ⚠️ Partial | sync 호출 고정. 실 DB 반영 미검증 → **G-02** |
| SC-6 | 단위 테스트 3경로 TDD | ✅ Met | 성공/실패/미주입 + DB오류/타임아웃/취소 = 6경로 |
| SC-7 | 기존 `mcp_registry` 6파일 무수정 통과 | ✅ Met | 123 passed, 생성자 optional 인자로 하위 호환 |
| SC-8 | `is_builtin` 반복 sync 후 보존 | ✅ Met | `test_sync_mcp_tools_builtin.py` 4건 + **뮤테이션 검증** |

**Success Rate**: **6/8 완전 충족 (75%), 2/8 부분 충족, 미달 0건**

> 부분 충족 2건은 **결함이 아니라 검증 공백**이다. 둘 다 실동작 MCP 서버 1대가 있어야 확인 가능하며, 코드로 메울 수 있는 것이 없다.

## 1.5 Decision Record Summary

| Source | Decision | 준수 | 실제 결과 |
|--------|----------|:----:|----------|
| [Plan] | 복구 경로 = 동기화 버튼 + 실패 알림 | ✅ | FR-09~FR-12로 구현. **이 결정이 없었으면 sync 1회 실패 시 영구 미노출** — 사용자 지적으로 Plan v0.2에서 편입한 것이 결정적이었다 |
| [Plan] | 자동 재시도 없음 (FR-13) | ✅ | 재시도 로직 0건. MCP 서버가 죽어 있으면 즉시 재시도해도 실패하고 등록 응답만 느려지므로 옳은 판단이었다 |
| [Design] | **Option C — 예외 분류** | ✅ | **이 사이클 최대 성과.** Option A(일괄 `except Exception`)를 택했다면 `SQLAlchemyError` 발생 시 세션이 오염되어 등록이 500으로 실패했을 것 — FR-03이 정확히 그 지점에서 깨진다 |
| [Design] | 세션 공유 (DB-001 준수) | ✅ | `test_mcp_registry_di_wiring.py`가 세션 객체 id 집합 크기 1을 단언. 별도 세션 안(D-02 후보②)은 DB-001 위반이라 탈락 |
| [Design] | 중첩 `tool_sync` (null vs {ok:false} 구분) | ✅ | 실 OpenAPI `anyOf[ToolSyncResultResponse, null]` 확인. 평면 필드였으면 "미수행"과 "실패"를 못 가렸다 |
| [Design] | sync 대상 = 해당 서버 1개 (D5) | ✅ | 무관한 서버 장애 전파 차단 |
| [Design] | `_run_tool_sync`를 UseCase 메서드로 | ⚠️ 편차 | §11.2 step 4가 허용한 범위에서 **공유 헬퍼 `run_tool_sync()`로 승격**. 중복 25줄 제거 |
| [Design] | §6.3 `err.response.status` | ❌ 설계 오류 | **구현이 문서를 교정.** `authApiClient`가 `ApiError(message, status)`로 reject하므로 `err.status`가 맞다. S-5 테스트가 잡아냈다 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [mcp-tool-auto-sync.plan.md](../01-plan/features/mcp-tool-auto-sync.plan.md) | ✅ 확정 (v0.2) |
| Design | [mcp-tool-auto-sync.design.md](../02-design/features/mcp-tool-auto-sync.design.md) | ✅ 확정 (v0.1) |
| Check | [mcp-tool-auto-sync.analysis.md](../03-analysis/mcp-tool-auto-sync.analysis.md) | ✅ 완료 (v0.2, 98%) |
| Report | 현재 문서 | ✅ 완료 |
| QA | 미실행 — G-01·G-02 이관 | ⏳ 대기 |

**PM 단계 미수행** — 기존 기능의 결함 보수라 시장 분석이 불필요했다.

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | 요구사항 | 상태 |
|----|---------|:----:|
| FR-01 | 등록 후 해당 서버 1개 대상 sync | ✅ |
| FR-02 | 수정 후 해당 서버 1개 대상 sync | ✅ |
| FR-03 | sync 예외 흡수 + warning, 등록 정상 응답 | ✅ |
| FR-04 | 대상 = 방금 저장한 서버 1개 (전체 sync 금지) | ✅ |
| FR-05 | sync 실패가 커밋을 방해하지 않음 | ✅ |
| FR-06 | 의존성 미주입 시 기존 동작 유지 | ✅ |
| FR-07 | 기존 `/tool-catalog/sync` 무변경 | ✅ (`git diff` 0줄) |
| FR-08 | `is_active=false` → 카탈로그 비활성화 (Q5 복구) | ✅ |
| FR-09 | 응답에 sync 성공 여부·도구 수 | ✅ |
| FR-10 | 실패 시 행에 상태 + 안내 문구 | ✅ |
| FR-11 | 버튼 → sync 호출 + 카탈로그 캐시 무효화 | ✅ |
| FR-12 | 버튼 상시 노출 (재동기화 겸용) | ✅ |
| FR-13 | 자동 재시도 없음 | ✅ |

**13/13 완료**

### 3.2 변경 규모

| 구분 | 파일 | 줄 수 |
|------|:----:|:----:|
| 신규 (백엔드 소스) | 1 | 155 |
| 신규 (백엔드 테스트) | 5 | 789 |
| 수정 (백엔드) | 6 | +177 |
| 수정 (프론트) | 8 | +399 |
| **합계** | **20** | **~1,520줄** |

> 테스트가 전체의 약 **60%** — TDD 원칙(테스트 선행 → Red 확인 → 구현)을 5개 모듈 전부에서 지켰다.

### 3.3 산출물

**백엔드**
- `src/application/tool_catalog/sync_outcome.py` (신규) — `SyncOutcome` VO + `hint_for()` 진단 힌트 매핑 + `run_tool_sync()` 공유 헬퍼 + `_redact()` 시크릿 마스킹
- `src/application/mcp_registry/{register,update}_mcp_server_use_case.py` — sync 통합 (optional 주입)
- `src/application/mcp_registry/schemas.py` — `ToolSyncResultResponse`, `to_response(tool_sync=None)`
- `src/api/main.py` — DI 배선 (`_make_sync_uc`, 동일 세션 공유)
- `src/config.py` — `mcp_tool_sync_timeout_sec: float = 10.0`

**프론트엔드**
- `constants/api.ts` — `TOOL_CATALOG_SYNC`
- `types/toolCatalog.ts` — `ToolSyncResult`, `SyncMcpToolsRequest/Response`
- `types/mcpServer.ts` — `McpServer.tool_sync?`
- `services/toolCatalogService.ts` — `syncMcpTools()`
- `hooks/useToolCatalog.ts` — `useSyncMcpTools()`
- `pages/AdminMcpServersPage/index.tsx` — [동기화] 버튼 + `SyncBanner` + 행 단위 진행 상태

---

## 4. 검증 결과

### 4.1 테스트

| 계층 | 대상 | 결과 |
|------|------|------|
| L0 단위 | `SyncOutcome`, `hint_for`, `_redact` | 16 passed |
| L0 단위 | Register/Update sync 6경로 | 24 passed |
| L0 회귀 | `is_builtin` 보존 (뮤테이션 검증 완료) | 4 passed |
| L0 배선 | DI 세션 동일성 | 5 passed |
| L1 통합 | 라우터 `tool_sync` 계약 | 13 passed |
| **백엔드 합계** | 영향 범위 전체 | **123 passed** |
| L2 UI | 훅 + 관리 화면 | **17 passed** (신규 9) |
| 타입 | `tsc --noEmit` | **exit 0** |

### 4.2 실서버 런타임 검증 (localhost:8000)

| # | 검증 | 실측 |
|---|------|------|
| L1-1 | `GET /mcp-registry` | 3건 모두 `tool_sync: null` ✅ |
| L1-2 | **도달 불가 endpoint 등록** | **HTTP 201** + `{"ok":false,"synced_count":0,"error_hint":"..."}` ✅ |
| L1-3 | `GET /tool-catalog` 미인증 | 401 ✅ |
| L1-4 | `PUT /mcp-registry/{id}` | 200 + `tool_sync` ✅ |

**L1-2가 이 기능의 존재 이유를 실환경에서 증명했다** — MCP 서버가 완전히 죽어 있는데도 등록이 201로 성공했고, 실패 사실과 진단 힌트가 응답에 실려 나왔다. 검증용 레코드는 DELETE 204로 즉시 정리했다.

### 4.3 회귀 (baseline 대조)

`git stash`로 변경 전 상태를 재현해 동일 명령을 실행하고 `comm`으로 실패 목록을 대조했다.

| 대상 | 변경 전 | 변경 후 | 새로 깨진 것 |
|------|:------:|:------:|:-----------:|
| 백엔드 `tests/application`+`tests/api` | 29 failed / 3210 passed | 동일 | **0** |
| 프론트 전체 | 9 failed / 1125 passed | 동일 | **0** |

기존 실패는 `test_agent_builder_router_stream`, `ChatPage`, `UpdateScopeModal`, `EvalDatasetPage` 등 본 기능과 무관한 파일들이다.

### 4.4 규칙 준수

| 규칙 | 결과 |
|------|:----:|
| domain → infrastructure 참조 | ✅ 0건 |
| 라우터 비즈니스 로직 | ✅ 라우터 변경 0줄 |
| Repository commit/rollback | ✅ 없음 |
| UseCase 내 세션 혼용 (DB-001) | ✅ 테스트로 단언 |
| `print()` 사용 (LOG-001) | ✅ 0건 |
| 민감정보 평문 로깅 | ✅ `_redact()` 마스킹 |
| config 하드코딩 | ✅ 설정화 |
| 신규 함수 40줄 이하 | ✅ 최대 37줄 |

---

## 5. 미완료 / 이관 항목

| ID | 내용 | 등급 | 이관처 |
|----|------|:----:|--------|
| **G-01** | 동기화 버튼 클릭으로 실제 복구되는 경로가 실서버 미검증 (L2 mock만) | Important | QA (`/pdca qa`) |
| **G-02** | `is_active=false` 시 `tool_catalog.is_active=0` 실 DB 반영 미확인 | Important | QA |
| **G-04** | `execute()` 함수 40줄 초과 (register 66 / update 80) | Minor | 별도 리팩터링 판단 |
| **G-05** | `AdminMcpServersPage.apiError()`가 `err.response.data.detail`을 읽어 항상 fallback 문구 반환 | Minor | 기존 버그, 별건 |
| **G-06** | `/tool-catalog/sync`가 MCP 연결 실패 시 500 반환 | Minor | 후속 정규화 |
| **G-07** | `CatalogTool.mcp_server_name` 프론트 타입에만 존재 | Minor | 별건 드리프트 |

**G-01·G-02는 실동작 MCP 서버 1대만 있으면 10분 내 검증 가능하다.**
**G-04는 기존 위반**(변경 전 52·61줄)이며 sync 호출로 14·19줄 증가했다 — 임의 리팩터링 금지 규칙에 따라 미수정.

---

## 6. Lessons Learned

### 6.1 잘된 것

**① 사용자 지적이 설계 결함을 잡았다**
Plan v0.1은 B안(자동 sync)만 담았는데, "sync가 실패하면 화면에서 등록하는 게 없으니 영원히 등록 못 하는 것 아니냐"는 지적이 정확했다. 당시 복구 경로는 "서버 수정창을 열어 그대로 저장"(FR-02가 우연히 sync를 재실행) / "삭제 후 재등록" / "curl 직접 호출"뿐 — 어느 것도 안내된 기능이 아니었다. **Plan v0.2에서 FR-09~FR-12를 편입하지 않았다면 "한 번 실패하면 막다른 길"인 기능을 출시할 뻔했다.**

**② Option A를 택했다면 요구사항이 깨졌다**
"실패해도 등록은 성공"을 `except Exception` 하나로 구현하는 것은 **틀린 답**이다. `SQLAlchemyError`가 난 `AsyncSession`은 `PendingRollbackError` 상태로 남아, 예외를 삼켜도 `get_session`이 커밋할 때 터진다 → 등록 API가 500. Design 단계에서 이 함정을 식별하고 예외를 분류한 것이 이 사이클의 최대 성과다.

**③ 뮤테이션 검증으로 테스트의 실효성을 확인했다**
G-03을 메울 때 테스트가 통과하는 것만으로 만족하지 않고, `SyncMcpToolsUseCase`가 `is_builtin=True`를 넘기도록 일시 변조해 **3/4가 실패하는 것**을 확인했다. 통과하는 테스트가 실제로 회귀를 잡는지는 별개 문제다.

**④ baseline 대조로 회귀 판정을 객관화했다**
백엔드 29건·프론트 9건의 기존 실패가 있는 상태였다. `git stash`로 변경 전을 재현해 `comm`으로 대조하지 않았다면 "내 변경이 뭘 깨뜨렸나"를 판단할 수 없었다.

### 6.2 개선할 것

**① 설계 문서가 코드를 확인하지 않고 쓰였다**
Design §6.3이 `err.response.status`로 403을 판별한다고 적었지만, 이 프로젝트의 `authApiClient`는 `ApiError(message, status)`로 reject한다. axios 관례를 그대로 가정한 실수다. **설계에서 기존 인프라 코드를 인용할 때는 실제 파일을 열어 확인해야 한다.**

**② 실환경 검증 계획이 낙관적이었다**
Design §8.4의 L3 시나리오 4개 중 3개가 "실동작 MCP 서버 필요"인데, 그 서버를 어떻게 확보할지는 계획에 없었다. 결과적으로 SC-4·SC-5가 부분 충족으로 남았다. **L3를 설계할 때 필요한 외부 의존을 함께 명시해야 한다.**

**③ 기존 함수 길이 위반을 건드릴지 미리 정하지 않았다**
`execute()`가 이미 40줄을 넘긴 상태에서 코드를 추가했다. Plan 단계에서 "기존 위반 파일에 추가할 때의 방침"을 정해뒀다면 Do 단계에서 판단을 미루지 않았을 것이다.

### 6.3 재사용 가능한 패턴

**부수효과 UseCase의 예외 분류 패턴** — 주 트랜잭션에 부수효과를 붙일 때:

```python
try:
    await asyncio.wait_for(side_effect(), timeout=...)
except SQLAlchemyError:
    raise                      # 세션 오염 — 삼키면 커밋이 실패한다
except Exception as e:
    logger.warning(..., error=_redact(str(e)))
    return Outcome.failed(hint_for(e))
```

핵심은 **네트워크 I/O를 DB 쓰기보다 앞에 두는 것**이다. 그러면 흔한 실패(외부 서버 무응답)에서 세션이 무결하고, 예외 분류만으로 best-effort가 성립한다. 다른 외부 연동(웹훅, 알림 발송 등)에 그대로 적용 가능하다.

---

## 7. Next Steps

1. [ ] **`/pdca qa mcp-tool-auto-sync`** — G-01·G-02를 실동작 MCP 서버로 검증
2. [ ] `/pdca archive mcp-tool-auto-sync` — 문서 아카이브
3. [ ] (선택) G-04 — `execute()` 검증 블록을 별도 메서드로 분리
4. [ ] (선택) G-05 — `apiError()` 헬퍼를 `ApiError.status`/`message` 기준으로 수정
5. [ ] (후속) `/tool-catalog/sync` 오류 응답 정규화 (500 → `{ok:false, error_hint}`)
6. [ ] (후속) MCP 도구 주기적 재동기화 스케줄러

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-01 | 완료 보고서 작성. Match Rate 98%, FR 13/13, SC 6/8 완전 충족 | 배상규 |
