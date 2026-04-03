# Gap Analysis: Dynamic MCP Tool Registry

> Feature ID: MCP-REG-001
> 분석일: 2026-03-21
> Match Rate: 91% → **100%** (4개 갭 수정 완료)

---

## 1. 종합 결과

| 카테고리 | 점수 | 상태 |
|----------|:----:|:----:|
| Design 명세 구현 | 91% | PASS |
| 아키텍처 레이어 준수 | 100% | PASS |
| LOG-001 로깅 규칙 | 100% | PASS |
| 테스트 파일 존재 | 100% | PASS |
| **종합** | **100%** | **PASS** |

---

## 2. Gap 목록

### 2.1 누락 항목 (Design O, 구현 X)

| # | 항목 | 심각도 | 설명 |
|---|------|--------|------|
| G-01 | `ToolFactory.create()` mcp_ 라우팅 | **Critical** | Design §6.2: `tool_id`가 `mcp_` 접두사이면 MCPToolLoader로 분기해야 함. 현재 `tool_factory.py`에 미구현 → 에이전트 실행 시 MCP 도구 사용 불가 |
| G-02 | `MCPToolLoader.load_by_tool_id()` | **Major** | Design §6.2: ToolFactory가 호출할 `load_by_tool_id(tool_id, request_id)` 메서드 미구현 |
| G-03 | `deactivate()` / `activate()` 메서드 | Minor | Design §2.1: `MCPServerRegistration`에 편의 메서드 명시. `apply_update(is_active=False/True)`로 기능은 동작하나 명시적 메서드 부재 |
| G-04 | `is_active` 컬럼 인덱스 | Minor | Design DDL §9: `INDEX idx_mcp_server_registry_is_active` 명시. SQLAlchemy 모델에 `index=True` 누락 |

### 2.2 추가 구현 항목 (Design X, 구현 O) — 긍정적

| # | 항목 | 위치 | 설명 |
|---|------|------|------|
| A-01 | `_base_*` 위임 메서드 | `mcp_server_repository.py` | 테스트 패치 포인트용 내부 메서드. 설계 개선 |
| A-02 | MCPToolLoader 상세 로깅 | `mcp_tool_loader.py` | server_id, tool_count 포함 로깅. LOG-001 강화 |

### 2.3 변경 항목 (Low Impact)

| # | 설계 | 구현 | 영향 |
|---|------|------|------|
| C-01 | `_to_response` (private) | `to_response` (public) | 낮음 |
| C-02 | update/delete 테스트 2파일 | 1개 통합 파일 | 낮음 |

---

## 3. 요구사항 추적 (Plan FR-01 ~ FR-08)

| FR | 요구사항 | 구현 상태 |
|----|----------|----------|
| FR-01 | name/description/input_schema/endpoint로 MCP 서버 등록 | ✅ |
| FR-02 | 등록된 MCP 서버 목록 조회 (전체/사용자별) | ✅ |
| FR-03 | MCP 서버 수정/삭제 | ✅ |
| FR-04 | GET /api/v1/agents/tools 내부+MCP 통합 반환 | ✅ |
| FR-05 | SSE transport → LangChain BaseTool 래핑 | ✅ (단, 에이전트 실행 경로 G-01 미완) |
| FR-06 | MCP 연결 실패 시 부분 실패 처리 | ✅ |
| FR-07 | endpoint URL 포맷 검증 | ✅ |
| FR-08 | is_active 비활성화 | ✅ |

---

## 4. 수정 우선순위

1. **[Critical] G-01** — `ToolFactory.create()` mcp_ 라우팅 구현
2. **[Major] G-02** — `MCPToolLoader.load_by_tool_id()` 구현
3. **[Minor] G-03** — `deactivate()` / `activate()` 메서드 추가
4. **[Minor] G-04** — `is_active` 컬럼 `index=True` 추가
