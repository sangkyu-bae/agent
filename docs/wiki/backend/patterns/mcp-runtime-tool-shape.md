---
title: MCP 런타임 도구 객체의 실제 형태 (이름은 UUID다)
status: draft
source_type: conversation
source_refs:
  - idt/src/infrastructure/mcp_registry/mcp_tool_loader.py:34-45 (MCPServerConfig.name = registration.tool_id = "mcp_{uuid}")
  - idt/src/infrastructure/mcp/tool_registry.py:82-90 (MCPToolAdapter.name = sanitize(f"{config.name}_{mcp_tool.name}"))
  - idt/src/infrastructure/tool_selection/adapters/langchain_filter.py:16-51,174-196 (_server_id/_server_label/_to_candidate) — ⚠️ 12c69b4 시점 미커밋
  - docs/archive/2026-08/tool-recommender/tool-recommender.report.md (§5.2 D-4·D-8·D-9·D-10, §6.2)
confidence: 0.85
version: 2
created: 2026-08-14
updated: 2026-08-14
verified_at: 12c69b4
---

# MCP 런타임 도구 객체의 실제 형태 (이름은 UUID다)

> **근거의 커밋 상태** — §1·§2(이 문서의 핵심 주장)의 근거인 `mcp_tool_loader.py`·
> `tool_registry.py`는 `12c69b4`에 **커밋되어 있어** 표류 검사가 정상 작동한다.
> §3의 duck typing 사례와 §5 실측치의 근거인 `tool_selection/`만 당시 워킹트리
> 미커밋 상태였다 — 이 두 절은 해당 코드 커밋 후 `verified_at` 재기록이 필요하다.

## 문제

MCP 도구를 다루는 코드를 쓸 때 "서버 이름"과 "도구 이름"이 사람이 읽는 문자열일
거라고 가정하기 쉽다. **실제 런타임 객체는 전혀 그렇지 않다.** tool-recommender
사이클은 이 가정 위에서 설계를 마쳤다가, MCP 서버 **1대**를 실제로 붙여 도구 4개를
수집한 순간 설계 오류 4건(D-4·D-8·D-9·D-10)이 한꺼번에 드러났다.

## 검증된 사실

### 1. `MCPServerConfig.name`은 사람이 읽는 이름이 아니라 저장 tool_id다

```python
# mcp_tool_loader.py:34-45
MCPServerConfig(name=registration.tool_id, ...)   # tool_id = "mcp_{uuid}"
```

DB의 `registration.name`("Doc Convert MCP")은 **런타임 도구 객체까지 오지 않는다.**
로더 로그에만 남는다. 그래서 서버명을 프롬프트나 UI 문구에 끼워 넣으면
`"6dd5c675-... 서버의 기능"` 같은 노이즈가 된다.

**부수 효과 (유용함)**: 카탈로그 표기의 `server_id`는 `mcp_` 접두어만 벗기면
얻어진다 — 저장소 조회가 필요 없다.

```python
mcp_id = f"mcp:{config.name.removeprefix('mcp_')}:{tool.mcp_tool_name}"
```

### 2. `BaseTool.name`은 UUID 40자가 앞에 붙은 합성 이름이다

```python
# tool_registry.py:82-85
tool_name = MCPConnectionPolicy.sanitize_tool_name(f"{config.name}_{mcp_tool.name}")
MCPToolAdapter(name=tool_name, ..., mcp_tool_name=mcp_tool.name)
```

`tool.name` = `mcp_{uuid}_{원본도구명}`. LLM에게 후보 목록으로 그대로 넘기면
UUID가 목록을 도배해 선별 신호가 묻힌다. **표시용 이름은 반드시
`tool.mcp_tool_name`(원본)** 을 쓴다.

### 3. MCP 도구 식별은 duck typing으로 (import 금지)

`DefaultToolIdResolver`는 `MCPToolAdapter`를 import 하지 않고
`server_config`/`mcp_tool_name` 속성 유무만 본다. import 하는 순간 해당 모듈이
mcp 인프라에 묶여 탈부착 계약이 약해지기 때문
([[detachable-module-seam]]).

### 4. "MCP description은 스텁이다"는 전제가 실제로는 틀렸다

Design 단계에서 "MCP 도구는 설명이 부실하니 보강해야 한다"고 가정했으나, 실측한
도구 4개는 **전부 충실한 docstring을 보유**했다. 진짜 문제는 반대였다 —
설명이 여러 줄 docstring이라 1줄 전제의 프롬프트 형식을 깼고, 요약 처리로
2878자 → 1778자(-38%)로 줄여야 했다. 저신호 보강 로직(`is_low_signal`)은 사실상
발동하지 않는다.

### 5. 규모 관련 실측치 (참고 좌표)

도구 13개 후보에서 경량 LLM 선별 시: 평균 2.9개 생존(78% 감소), Recall 100%(22질의),
지연 P95 1369ms / 중앙값 775ms. **후보가 수십 개로 늘었을 때는 미검증**이다.

## 다음에 적용하는 법

1. **MCP 관련 설계는 서버 1대를 실제로 붙여보고 확정한다.** 전수 검증(골드셋)이
   막혀도 표본 1건은 대개 얻을 수 있고, 이번엔 그 1건이 설계 오류 4건을 잡았다.
2. **표시·프롬프트용 이름은 `mcp_tool_name`, 식별자는 `mcp:{server_id}:{tool}`,
   저장은 `mcp_{srv}`** — 세 표기를 섞지 말 것 ([[router-map]] 계약 주의,
   [[erd-agent]]).
3. **서버명이 UUID 형태면 사용하지 않는다** (`_server_label`이 정규식으로 판정 후
   `None` 반환). 사람이 읽는 서버명이 꼭 필요하면 `registration.name`을 런타임까지
   전달하는 별도 작업이 필요하다.
4. MCP 등록이 죽어 있으면 조용히 남아 나중 작업을 막는다 —
   `python -m scripts.verify_mcp_connections`로 먼저 확인.

## 관련 문서

- 라우터 경계의 ID 변환: `backend/api/router-map.md`
- 저장 표기: `backend/db/erd-agent.md`
- 도구 규칙 원본: `idt/docs/rules/tool-and-mcp.md`
