# shared-custom-agent API

> 통합 도구 카탈로그 API

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1` |
| Auth | Bearer Token (`get_current_user` / `AdminUser` dependency) |

---

## 엔드포인트 목록

| Method | Path | 설명 | 권한 |
|--------|------|------|------|
| GET | `/tool-catalog` | 도구 카탈로그 목록 (활성만) | CurrentUser |
---

## 상세 스펙
---
### GET /tool-catalog

활성 도구 카탈로그 목록. internal + MCP 도구 통합 반환.

**Response**
```json
{
  "tools": [
    {
      "tool_id": "internal:excel_export",
      "source": "internal",
      "name": "Excel 파일 생성",
      "description": "pandas로 데이터를 Excel(.xlsx) 파일로 저장합니다.",
      "mcp_server_id": null,
      "mcp_server_name": null,
      "requires_env": []
    },
    {
      "tool_id": "mcp:server-uuid:search",
      "source": "mcp",
      "name": "search",
      "description": "MCP 서버의 검색 도구",
      "mcp_server_id": "server-uuid",
      "mcp_server_name": "Search Server",
      "requires_env": []
    }
  ]
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |

---
