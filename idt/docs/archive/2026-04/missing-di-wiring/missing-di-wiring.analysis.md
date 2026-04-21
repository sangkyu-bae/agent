# Gap Analysis: missing-di-wiring

> Analysis Date: 2026-04-21
> Plan Document: `docs/01-plan/features/missing-di-wiring.plan.md`
> Implementation: `src/api/main.py` (commit 7fd2e694)
> Overall Match Rate: **92%**

---

## 1. Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 88% | WARN |
| Architecture Compliance (DB-001, LOG-001) | 100% | PASS |
| Convention Compliance | 95% | PASS |
| **Overall** | **92%** | **PASS** |

---

## 2. Router Registration (include_router) — 4/4 ✅

| Router | Plan | Implementation | Status |
|--------|:----:|:--------------:|:------:|
| `mcp_registry_router` | Required | Line 1535 | PASS |
| `middleware_agent_router` | Required | Line 1536 | PASS |
| `excel_export_router` | Required | Line 1537 | PASS |
| `pdf_export_router` | Required | Line 1538 | PASS |

---

## 3. dependency_overrides — 11/11 (Plan 항목 기준) ✅

| Area | Plan 항목 수 | 구현 수 | Status |
|------|:-----------:|:------:|:------:|
| MCP Registry | 4 | 4 (lines 1492-1495) | PASS |
| Middleware Agent | 4 | 4 (lines 1501-1504) | PASS |
| Excel Export | 1 | 1 (line 1508) | PASS |
| PDF Export | 1 | 1 (line 1512) | PASS |
| Agent Builder load_mcp_tools | 1 | 1 (line 1433) | PASS |

### 불일치: Plan 문서 산술 오류

Plan 문서에서 "14개 dependency_overrides"라고 3회 기재(lines 31, 140, 149)했으나, 실제 항목별 합산은 **11개**. 구현은 항목별 명세에 정확히 일치.

### 추가 구현 (Plan 외)

| Override | Location | 설명 |
|----------|----------|------|
| `get_auto_build_create_agent_uc` | Line 1456 | AutoBuild 라우터의 CreateMiddlewareAgentUseCase 연결 |

---

## 4. Factory Functions — 5/5 ✅

| Factory | Plan | 구현 | Pattern | Status |
|---------|:----:|:----:|---------|:------:|
| `create_mcp_registry_factories()` | O | Line 1242 | per-request | PASS |
| `create_middleware_agent_factories()` | O | Line 1264 | per-request | PASS |
| `create_excel_export_use_case()` | O | Line 1296 | singleton | PASS |
| `create_html_to_pdf_use_case()` | O | Line 1303 | singleton | PASS |
| `create_load_mcp_tools_factory()` | O | Line 1310 | per-request | PASS |

---

## 5. DB-001 §10.2 준수 — PASS ✅

모든 per-request 팩토리가 `Depends(get_session)` 패턴 사용, repository 간 동일 세션 공유.

---

## 6. LOG-001 준수 — PASS ✅

모든 팩토리가 `get_app_logger()` 호출 후 UseCase/Repository에 logger 전달.

---

## 7. 발견된 차이점

### YELLOW — 추가 구현 (Plan X, 구현 O)

| 항목 | 설명 | 영향 |
|------|------|------|
| `get_auto_build_create_agent_uc` override | AutoBuild 라우터용 CreateMiddlewareAgentUseCase 배선 | 낮음 |
| `create_middleware_agent_use_case_factory()` | 위 override용 팩토리 함수 | 낮음 |

### BLUE — Plan 문서 오류

| 항목 | Plan | 실제 | 영향 |
|------|------|------|------|
| Override 총 수 | "14" (3회 기재) | 11 (항목별 합산) | 중간 — 산술 오류 |
| Converter 클래스명 | `WeasyPrintConverter` | `WeasyprintConverter` | 낮음 — 오타 |

### GREEN — 누락 항목: 없음

Plan의 모든 기능 항목이 구현에 존재.

---

## 8. 권장 조치

### Plan 문서 수정 필요

1. Lines 31, 140, 149의 "14" → "11"로 수정
2. Line 99의 `WeasyPrintConverter` → `WeasyprintConverter`로 수정

### 코드 수정: 불필요

구현은 완전하며 DB-001, LOG-001 모두 준수.

---

## 9. Match Rate: 92%

- 기능 구현 일치: 100% (모든 Plan 항목 구현 완료)
- 문서 정합성: -8% (Plan 산술 오류, 미기재 추가 항목)
