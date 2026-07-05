# nl-agent-composer API

> 자연어 요청 한 문장으로 내부+MCP 도구를 LLM이 조합한 에이전트 초안(무저장)을 반환하고, 사용자가 확정 시 기존 에이전트 생성 API로 저장하는 기능.

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | `/api/v1/agents` |
| Auth | Bearer JWT (`Authorization: Bearer <access_token>`, `get_current_user`) |
| 관련 문서 | `docs/archive/2026-07/nl-agent-composer/` (plan/design/analysis/report) |

**흐름**: `POST /compose`로 초안 수신 → 프론트가 생성 폼에 프리필 → 사용자 수정 → 저장 버튼 시 기존 `POST /api/v1/agents` 호출(초안의 `tool_ids` + `system_prompt` 그대로 전달). compose는 DB에 아무것도 저장하지 않는다.

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/v1/agents/compose` | 자연어 → 에이전트 초안 조합 (신규, 무저장) |
| POST | `/api/v1/agents` | 에이전트 생성 (기존 — `system_prompt` 프리필·`mcp_*` tool_id 수용 확장) |

---

## 상세 스펙

### POST /api/v1/agents/compose

자연어 요청을 단위 역량으로 분해하고, 후보 도구(내부 `TOOL_REGISTRY` + DB 등록 MCP 도구 카탈로그)만으로 에이전트 구성을 LLM이 제안한다. 서버가 환각 tool_id 제거·도구 수(최대 5)/프롬프트(최대 4,000자) 절단·coverage 재산정을 최종 수행한다. **DB 저장 없음.**

**Request**

```json
{
  "user_request": "tavily 검색 도구 추가해줘",
  "name": "재무 리포터",
  "llm_model_id": null,
  "current_config": {
    "name": "재무 리포터",
    "system_prompt": "당신은 재무 데이터 에이전트입니다.",
    "tool_ids": ["excel_export"],
    "llm_model_id": "model-default",
    "temperature": 0.7
  },
  "history": [
    { "role": "user", "content": "재무 에이전트 만들어줘" },
    { "role": "assistant", "content": "초안(coverage: full) — 이름: 재무 리포터 / 도구: excel_export" }
  ]
}
```

| 필드 | 타입 | 필수 | 제약 | 설명 |
|------|------|:---:|------|------|
| `user_request` | string | ✅ | 1~1000자 | 자연어 요청 |
| `name` | string \| null | — | ≤200자 | 에이전트 이름. 없으면 LLM 제안(`name_suggestion`) 사용 |
| `llm_model_id` | string \| null | — | 등록된 모델 id | 초안 에이전트의 **실행 모델**. 없으면 기본 모델 |
| `current_config` | object \| null | — | 아래 참조 | **(fix-agent-composer 신규)** 증분 수정용 현재 폼 스냅샷. 있으면 프롬프트에 현재 설정 블록+증분 수정 규칙("요청된 변경만 적용, 기존 도구 유지")이 주입된다. 미전송 시 기존 단발성 동작과 동일 |
| `history` | object[] \| null | — | ≤20턴 | **(fix-agent-composer 신규)** Fix 채팅 이전 대화. 서버가 **최근 6턴·턴당 500자**로 재절단 후 system과 user 사이 messages로 삽입 |

**`current_config` 필드** (모두 optional — 빈 폼 허용)

| 필드 | 타입 | 제약 |
|------|------|------|
| `name` | string \| null | ≤200자 |
| `system_prompt` | string \| null | ≤4000자 |
| `tool_ids` | string[] | ≤10개 |
| `llm_model_id` | string \| null | — |
| `temperature` | number \| null | 0.0~2.0 |

**`history` 턴**: `{ "role": "user" \| "assistant", "content": string(1~2000자) }` — assistant 턴은 초안 요약 텍스트(카드 JSON 아님) 권장.

**Response** — `200 OK`

```json
{
  "coverage": "partial",
  "name_suggestion": "재무 리포터",
  "system_prompt": "당신은 재무 데이터 수집·보고 에이전트입니다. ...",
  "tool_ids": ["tavily_search", "mcp_a1b2c3", "excel_export"],
  "workers": [
    {
      "tool_id": "tavily_search",
      "worker_id": "search_worker",
      "description": "웹에서 재무 데이터 검색",
      "sort_order": 0,
      "tool_config": null,
      "worker_type": "tool",
      "ref_agent_id": null,
      "ref_agent_name": null
    }
  ],
  "flow_hint": "tavily_search → mcp_a1b2c3 → excel_export",
  "llm_model_id": "model-default",
  "temperature": 0.7,
  "missing_capabilities": [
    {
      "capability": "사내 ERP 조회",
      "reason": "매칭되는 내부/MCP 도구 없음",
      "suggestion": "ERP MCP 서버 등록 필요"
    }
  ],
  "notes": "웹 수집은 Tavily로 대체했습니다."
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `coverage` | `"full"` \| `"partial"` \| `"none"` | 요청 역량 커버리지 (서버 재산정: 워커 0=none, 미커버 역량 존재=partial) |
| `name_suggestion` | string | 요청 `name`이 있으면 echo, 없으면 LLM 제안 |
| `system_prompt` | string | LLM 생성 프롬프트 (화면 수정 가능, ≤4000자 보장) |
| `tool_ids` | string[] | `CreateAgentRequest.tool_ids` 호환. MCP는 `mcp_{server_id}` 형태(서버 단위) |
| `workers` | WorkerInfo[] | 워커 상세 (같은 MCP 서버의 개별 도구는 1개 워커로 병합, description `"; "` join) |
| `flow_hint` | string | 실행 순서 힌트 (서버 보정 발생 시 tool_id 체인으로 재계산) |
| `llm_model_id` | string | 해석된 실행 모델 id |
| `temperature` | number | 프리필 기본값 0.70 |
| `missing_capabilities` | object[] | 커버 불가 역량 `{capability, reason, suggestion}` |
| `notes` | string | LLM 조합 근거 + 서버 보정 사유(환각 제외/상한 절단/MCP 카탈로그 미동기화 폴백 등) `"; "` join |

**`coverage: "none"`인 경우**: `tool_ids`/`workers`/`system_prompt`/`flow_hint`는 빈 값, `missing_capabilities`+`notes`만 채워진다.

```json
{
  "coverage": "none",
  "name_suggestion": "ERP 조회 도우미",
  "system_prompt": "",
  "tool_ids": [],
  "workers": [],
  "flow_hint": "",
  "llm_model_id": "model-default",
  "temperature": 0.7,
  "missing_capabilities": [
    { "capability": "사내 ERP 조회", "reason": "매칭 도구 없음", "suggestion": "ERP MCP 서버 등록 필요" }
  ],
  "notes": "현재 등록된 도구로는 요청을 수행할 수 없습니다."
}
```

**Error Codes**

| 코드 | 설명 |
|------|------|
| 401 | 인증 토큰 없음/무효 |
| 422 | 요청 검증 실패 (`user_request` 1~1000자 위반 등) 또는 `llm_model_id` 미존재 (`"LLM 모델을 찾을 수 없습니다: {id}"`) |
| 500 | LLM 호출 실패 등 내부 오류 (전역 핸들러) |

**동작 특성**

- 후보 도구 상한: `COMPOSER_MAX_CANDIDATES`(기본 100) 초과분은 절단 + 서버 경고 로그.
- MCP 후보는 tool_catalog(개별 도구, `POST /api/v1/tool-catalog/sync`로 동기화) 기준. 카탈로그에 MCP 항목이 없으면 MCP 레지스트리 서버 단위 메타로 폴백하며 `notes`에 동기화 안내가 포함된다.
- MCP 워커는 서버 단위(`mcp_{server_id}`)라 해당 서버의 모든 도구가 에이전트에 노출된다(개별 도구 필터링은 후속).

---

### POST /api/v1/agents (기존 API — 이 기능의 확장분만 기술)

초안 확정 저장 시 사용. 전체 스펙은 기존 Agent Builder 문서 참조. nl-agent-composer로 추가된 것:

**Request 추가 필드**

```json
{
  "user_request": "재무 데이터를 웹에서 수집하고 엑셀 보고서로 만드는 에이전트",
  "name": "재무 리포터",
  "tool_ids": ["tavily_search", "mcp_a1b2c3", "excel_export"],
  "system_prompt": "화면에서 수정한 초안 프롬프트",
  "llm_model_id": "model-default",
  "temperature": 0.7
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|:---:|------|
| `system_prompt` | string \| null | — | ≤4000자. **값이 있으면 LLM 프롬프트 자동 생성을 건너뛰고 그대로 저장** (초안 프리필용). `null`이면 기존대로 자동 생성 |
| `tool_ids` | string[] | — | **`mcp_{server_id}` 형태 수용** (신규). MCP 레지스트리에서 메타 해석 |

**Error Codes (확장분)**

| 코드 | 설명 |
|------|------|
| 422 | 미등록/비활성 MCP tool_id (`"등록되지 않았거나 비활성화된 MCP 도구입니다: mcp_xxx"`), `system_prompt` 4000자 초과 |
