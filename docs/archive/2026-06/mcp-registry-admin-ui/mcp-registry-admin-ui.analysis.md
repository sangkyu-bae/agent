# Gap Analysis: MCP 서버 등록/관리 (Admin UI + 연결 테스트)

> Created: 2026-06-18
> Feature: mcp-registry-admin-ui
> Phase: Check
> Design: docs/02-design/features/mcp-registry-admin-ui.design.md

---

## Match Rate: 100% (최초 98% → 갭 해소)

설계와 구현이 완전히 일치한다. 백엔드·프론트·테스트가 모두 설계 스펙을 구현했다.
최초 분석에서 −2% 차감 사유였던 **페이지 컴포넌트 테스트(`AdminMcpServersPage.test.tsx`) 부재**를
후속으로 추가하여 갭을 해소했다 (아래 §갭 해소 참조).

```
[Plan] ✅ → [Design] ✅ → [Do] ✅ → [Check] ✅ (100%) → [Report] ⏳
```

---

## ✅ 완전 구현 (Fully Implemented)

### 백엔드
- `MCPConnectionTestResponse` (ok/tools/error/elapsed_ms) — `src/application/mcp_registry/schemas.py`
- `MCPConnectionTestUseCase` — `MCPCallClient.list_tools` 직접 사용, 미존재 시 None, 예외 시 ok=False + `logger.error` — `src/application/mcp_registry/mcp_connection_test_use_case.py`
- 라우터 `POST /{id}/test` + `get_test_use_case` + 404 매핑, CRUD는 PUT — `src/api/routes/mcp_registry_router.py`
- DI: `test_factory`(5-tuple) + override + import — `src/api/main.py`

### 프론트엔드
- 타입 매핑(items/total, masked secret) — `types/mcpServer.ts`
- 서비스 get/create/update(**PUT**)/delete/testConnection — `services/mcpServerService.ts`
- 훅 4종(쿼리+뮤테이션 invalidate, test는 무효화 없음) — `hooks/useMcpServers.ts`
- 페이지: 목록 테이블, 두 transport 동적 폼, **시크릿 병합(빈값=PUT 제외, **** 재전송 안 함)**, 연결 테스트(행+모달)+결과 패널, 삭제 확인, `user_id: String(authStore user id)` — `pages/AdminMcpServersPage/index.tsx`
- 상수/쿼리키/내비/라우트 — `constants/api.ts`, `lib/queryKeys.ts`, `constants/adminNav.ts`, `App.tsx`(AdminRoute>AdminLayout)

### 테스트
- 백엔드 use case 3 케이스(성공/연결실패+logger/미존재) — `tests/application/mcp_registry/test_test_connection_use_case.py` → 23 passed
- 프론트 훅 6 케이스 + 엔드포인트 상수 — `hooks/useMcpServers.test.ts` → 12 passed
- MSW 핸들러 5종(마스킹 페이로드) — `__tests__/mocks/handlers.ts`

---

## 🔶 편차 (Deviations — 모두 low)

| 항목 | 설계 | 구현 | 판정 |
|------|------|------|------|
| UseCase 클래스명 | `TestMCPConnectionUseCase` (§2-3) | `MCPConnectionTestUseCase` | pytest `Test*` 수집 충돌 회피 — 의도적 개선, 전체 일관 |
| `elapsed_ms` | 측정 optional (§8.1) | 성공·실패 모두 측정 | 긍정적 편차 |
| server_config 병합 | "동일 규칙"(§4-1) | omit-when-empty 적용 확인 | 정확 (갭 아님) |

---

## ✅ 갭 해소 (Resolved)

- **`AdminMcpServersPage.test.tsx`** 신규 추가 (5 케이스, 전부 통과):
  - P-1 목록 렌더 / P-2 SSE 등록(user_id 주입 검증) / **P-3 수정 시 시크릿 미입력 → auth_config·server_config 미전송 검증(핵심)** / P-4 행 연결 테스트 성공 패널 / P-5 삭제 확인 후 DELETE 호출.
  - 결과: 페이지 5 + 훅 6 + 내비 6 = **17 passed** (`--pool=threads`).
- `mcpServerService.test.ts` 별도 파일은 두지 않음 — 서비스는 훅 테스트 + 페이지 테스트 + MSW로 동등 이상 커버 (중복 회피).

---

## 📝 Notes (코드 리딩 중 발견)

1. **행 테스트 에러 매핑**: `handleRowTest`가 네트워크/404 오류를 일괄 `'요청 실패'`로 표시 →
   서버 삭제(404)와 연결 실패를 구분하지 않음. 경미한 UX 엣지(설계 위반 아님).
2. **수정 모달 테스트 범위**: 저장된 서버(`server.id`) 기준이라 미저장 시크릿 편집은 테스트에 미반영 —
   설계 §8.4(저장 전 테스트는 후속) 그대로. 이슈 아님.
3. **백엔드 RBAC 부재**(R1, §8.3): 의도적 범위 밖. 프론트 AdminRoute로만 보호. 후속 권고 유지.

---

## 결론 및 다음 단계

Match Rate **100%** → 품질 게이트 통과, 갭 없음.

- 다음: `/simplify` (코드 정리, 선택) → `/pdca report mcp-registry-admin-ui` (완료 보고서)
