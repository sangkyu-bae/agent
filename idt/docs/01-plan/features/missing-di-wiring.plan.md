# MISSING-DI-WIRING: main.py 누락 DI 배선 일괄 수정

> 상태: Plan
> Task ID: DI-WIRING-001
> 의존성: MCP-REG-001, AGENT-005, EXCEL-EXPORT-001, HTML-TO-PDF-001, AGENT-004, LOG-001
> 작성일: 2026-04-21
> 우선순위: Critical (런타임 에러 유발)

---

## 1. 문제 정의 (Problem Statement)

`src/api/main.py`의 `create_app()`에서 다음 라우터/DI placeholder가 누락되어,
해당 API 호출 시 **NotImplementedError 런타임 에러**가 발생한다.

### 1-1. 미등록 라우터 (include_router 누락) — 4건

| 라우터 파일 | prefix | Task ID | 누락 DI placeholders |
|------------|--------|---------|---------------------|
| `mcp_registry_router.py` | `/api/v1/mcp-registry` | MCP-REG-001 | register, list, update, delete (4개) |
| `middleware_agent_router.py` | `/api/v2/agents` | AGENT-005 | create, get, run, update (4개) |
| `excel_export_router.py` | `/api/v1/excel` | EXCEL-EXPORT-001 | excel_export (1개) |
| `pdf_export_router.py` | `/api/v1/pdf` | HTML-TO-PDF-001 | html_to_pdf (1개) |

### 1-2. 등록 라우터의 DI override 누락 — 1건

| 라우터 파일 | 누락 dependency | 사용 엔드포인트 |
|------------|----------------|---------------|
| `agent_builder_router.py` | `get_load_mcp_tools_use_case` | GET `/api/v1/agents/tools` |

**총 누락: 라우터 4개 + DI override 1개 = 14개 dependency_overrides 미연결**

---

## 2. 목표 (Goal)

1. 4개 누락 라우터를 `create_app()`에 `include_router()` 등록
2. 14개 DI placeholder에 대한 팩토리 함수 작성 및 `dependency_overrides` 연결
3. DB-001 §10.2 패턴 준수 (Depends(get_session) 주입, repo 간 동일 세션 공유)
4. LOG-001 준수 (StructuredLogger 주입)

---

## 3. Non-Goals

- UseCase/Repository/Domain 로직 변경 (이미 구현 완료)
- 새로운 테스트 작성 (DI 배선은 통합 테스트 레벨, 기존 단위 테스트 영향 없음)
- 프론트엔드 변경

---

## 4. 변경 대상 파일

### 4-1. `src/api/main.py` (단일 파일 수정)

#### A. import 추가

```python
# MCP Registry
from src.api.routes.mcp_registry_router import (
    router as mcp_registry_router,
    get_register_use_case as get_mcp_register_use_case,
    get_list_use_case as get_mcp_list_use_case,
    get_update_use_case as get_mcp_update_use_case,
    get_delete_use_case as get_mcp_delete_use_case,
)
from src.application.mcp_registry.register_mcp_server_use_case import RegisterMCPServerUseCase
from src.application.mcp_registry.list_mcp_servers_use_case import ListMCPServersUseCase
from src.application.mcp_registry.update_mcp_server_use_case import UpdateMCPServerUseCase
from src.application.mcp_registry.delete_mcp_server_use_case import DeleteMCPServerUseCase

# Middleware Agent
from src.api.routes.middleware_agent_router import (
    router as middleware_agent_router,
    get_create_use_case as get_mw_create_use_case,
    get_get_use_case as get_mw_get_use_case,
    get_run_use_case as get_mw_run_use_case,
    get_update_use_case as get_mw_update_use_case,
)
from src.application.middleware_agent.get_middleware_agent_use_case import GetMiddlewareAgentUseCase
from src.application.middleware_agent.run_middleware_agent_use_case import RunMiddlewareAgentUseCase
from src.application.middleware_agent.update_middleware_agent_use_case import UpdateMiddlewareAgentUseCase
from src.application.middleware_agent.middleware_builder import MiddlewareBuilder

# Excel Export
from src.api.routes.excel_export_router import (
    router as excel_export_router,
    get_excel_export_use_case as get_excel_export_uc,
)
from src.application.use_cases.excel_export_use_case import ExcelExportUseCase
from src.infrastructure.excel_export.pandas_excel_exporter import PandasExcelExporter

# PDF Export
from src.api.routes.pdf_export_router import (
    router as pdf_export_router,
    get_html_to_pdf_use_case as get_html_to_pdf_uc,
)
from src.application.use_cases.html_to_pdf_use_case import HtmlToPdfUseCase
from src.infrastructure.pdf_export.weasyprint_converter import WeasyPrintConverter

# Agent Builder 추가 (load_mcp_tools)
from src.api.routes.agent_builder_router import get_load_mcp_tools_use_case
```

#### B. 팩토리 함수 추가

| 팩토리 | 패턴 | 의존성 |
|--------|------|--------|
| `create_mcp_registry_factories()` | per-request (DB session) | MCPServerRepository, 4 UseCase |
| `create_middleware_agent_factories()` | per-request (DB session) | MiddlewareAgentRepository, ToolFactory, MiddlewareBuilder, 4 UseCase |
| `create_excel_export_use_case()` | singleton (stateless) | PandasExcelExporter |
| `create_html_to_pdf_use_case()` | singleton (stateless) | WeasyPrintConverter |
| `create_load_mcp_tools_factory()` | per-request (DB session) | MCPServerRepository, MCPToolLoader, LoadMCPToolsUseCase |

#### C. include_router + dependency_overrides 추가

```python
# MCP Registry
app.include_router(mcp_registry_router)

# Middleware Agent
app.include_router(middleware_agent_router)

# Excel Export
app.include_router(excel_export_router)

# PDF Export
app.include_router(pdf_export_router)

# Agent Builder - load_mcp_tools
app.dependency_overrides[get_load_mcp_tools_use_case] = ...
```

---

## 5. 구현 순서

1. `create_app()` 내 import 문 추가
2. 팩토리 함수 5개 작성 (DB-001 §10.2 준수)
3. `dependency_overrides` 14개 연결
4. `include_router` 4개 추가
5. 서버 기동 테스트 (`uvicorn` 정상 시작 확인)

---

## 6. 완료 기준 (Definition of Done)

- [ ] 4개 누락 라우터 `include_router` 등록
- [ ] 14개 DI placeholder 전부 `dependency_overrides` 연결
- [ ] `uvicorn src.api.main:app` 정상 기동 (import error 없음)
- [ ] 각 엔드포인트 curl/Swagger 호출 시 NotImplementedError 발생하지 않음
- [ ] DB-001 §10.2 (Depends(get_session) 패턴) 준수
- [ ] LOG-001 (StructuredLogger 주입) 준수
- [ ] 기존 테스트 깨지지 않음

---

## 7. 리스크

| 리스크 | 영향 | 대응 |
|--------|------|------|
| WeasyPrint 미설치 환경 | PDF export import 실패 | 조건부 import 또는 서버 기동 경고 |
| mcp_registry_router의 DI 함수명이 auth_router와 충돌 (`get_register_use_case`) | import alias 필요 | `as get_mcp_register_use_case` 등 alias 사용 |
| middleware_agent_router가 /api/v2 prefix | 기존 /api/v1 라우터와 혼재 | 의도된 설계 (AGENT-005), 변경 불필요 |
