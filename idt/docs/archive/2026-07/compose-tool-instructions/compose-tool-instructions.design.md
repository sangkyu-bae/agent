# Design: compose-tool-instructions

> Plan: `docs/01-plan/features/compose-tool-instructions.plan.md`
> 작성일: 2026-07-05 | 상태: Design | 범위: 풀스택 (idt + idt_front)

---

## 1. 개요

compose(자연어 → 에이전트 초안)에 ① 도구별 사용 지침(instruction) 생성·노출,
② system_prompt [도구 지침] 섹션 필수화, ③ 초안 [적용하기] 시 도구 미세팅 버그
수정을 설계한다.

## 2. 버그 원인 확정 (FR-05/FR-08) — 정적 분석 완료

### 2-1. 도구 ID 네임스페이스가 2계층으로 분리되어 있다

| 계층 | internal 도구 | MCP 도구 | 사용처 |
|------|--------------|----------|--------|
| **카탈로그/폼 형식** | `internal:{id}` | `mcp:{server_id}:{tool}` | `GET /tool-catalog` 응답, `form.tools`, ToolPicker 체크 비교, `RAG_TOOL_ID`(`internal:internal_document_search`) |
| **저장/레지스트리 형식** | `{id}` | `mcp_{server_id}` | DB workers.tool_id, TOOL_REGISTRY, **compose 응답 `tool_ids`** |

근거:
- `sync_internal_tools_use_case.py:35` — 카탈로그 tool_id는 `internal:{id}` 규약
- `sync_mcp_tools_use_case.py:46` — `mcp:{server_id}:{tool.name}`
- `ToolPickerModal.tsx:71` — `selectedIds.includes(tool.tool_id)` (카탈로그 형식으로 비교)
- `compose_agent_use_case._map_mcp_workers` — 응답은 `mcp_{server_id}`로 변환 ("저장 호환")

### 2-2. 버그 메커니즘

`handleApplyDraft`(`AgentBuilderPage/index.tsx:286`)가 **저장 형식**의
`draft.tool_ids`를 그대로 `form.tools`에 주입한다:

1. ToolPicker/도구함은 카탈로그 형식과 비교 → **어떤 도구도 체크 표시되지 않음** (사용자 증상).
2. `newTools.includes(RAG_TOOL_ID)`(카탈로그 형식) 비교도 항상 false → RAG 설정 부수효과 미동작.

### 2-3. 부수 발견 (같이 수정)

`create_agent_use_case._normalize_tool_id` (line 318)는 `split(":")[-1]` 방식이라
카탈로그 형식 MCP ID `mcp:{srv}:{tool}`이 `{tool}`로 잘못 정규화된다
→ 수동으로 MCP 도구를 선택해 저장하면 `get_tool_meta({tool})` 실패 가능.
`mcp:` 프리픽스는 `mcp_{server_id}`로 정규화해야 한다.

## 3. 설계 결정

| ID | 결정 | 근거 |
|----|------|------|
| D1 | `WorkerInfo`(agent_builder 공용)에 `instruction: str = ""` 추가 (compose 전용 DTO 분리 안 함) | 기본값 하위호환, 가장 작은 변경. create/update 응답에도 자연 노출되나 무해 |
| D2 | 폼 반영용 ID 변환은 **프론트에서 수행** (`mapDraftToolIdsToCatalog` 유틸 신설) | compose 응답 형식은 "저장 호환" 계약 유지 — 백엔드 응답 형식 변경 시 저장 경로가 깨짐 |
| D3 | `mcp_{server_id}` → 해당 서버의 **활성 카탈로그 도구 전체** 선택으로 전개 | compose가 서버 단위로 병합하므로 역방향은 서버 소속 도구 전체가 의미상 등가 |
| D4 | 도구별 지침 저장은 system_prompt 병합으로 해결 (별도 저장 스키마 없음) | Plan Non-Goal 유지. workers[].instruction은 표시/추적용 |
| D5 | `_normalize_tool_id`의 `mcp:` 처리는 백엔드에서 수정 (`mcp:{srv}:{tool}` → `mcp_{srv}`) | 수동 MCP 선택 저장 경로의 잠재 결함 — 프론트 우회로는 부분 해결만 됨 |

## 4. 상세 설계 — 백엔드 (idt)

### 4-1. composer.py

```python
class _WorkerOutput(BaseModel):
    tool_id: str
    worker_id: str
    description: str
    sort_order: int
    instruction: str = Field(
        "", description="이 도구의 사용 지침 — 사용 시점, 입력 형태, 주의사항 (2~4문장, 300자 이내)"
    )
```

`_SYSTEM_PROMPT` 규칙 추가 (기존 규칙 블록에 append):

```
- system_prompt에는 [도구 지침] 섹션을 반드시 포함하세요. 각 워커의 도구에 대해
  언제 사용하는지, 어떤 입력으로 호출하는지, 주의사항을 instruction과 일관되게 쓰세요.
- 각 worker의 instruction 필드에는 해당 도구의 사용 지침을 2~4문장으로 쓰세요.
```

system_prompt 필수 섹션: `[역할]`, `[도구 지침]`, `[동작 원칙]`.

### 4-2. compose_agent_use_case.py

- `_sanitize_workers`: `WorkerDefinition` 생성 시 instruction 전달.
  - `WorkerDefinition`(domain)에 `instruction: str = ""` 필드 추가.
- `_map_mcp_workers`: 동일 tool_id 병합 시 description과 동일하게
  `instruction`도 `"; "` 연결 병합.
- `_to_response`: `WorkerInfo(instruction=w.instruction, ...)` 전달.

### 4-3. 스키마

- `src/application/agent_builder/schemas.py` `WorkerInfo`: `instruction: str = ""` 추가.
- `src/domain/agent_builder/schemas.py` `WorkerDefinition`: `instruction: str = ""` 추가.

### 4-4. `_normalize_tool_id` 수정 (create/update use case)

```python
@staticmethod
def _normalize_tool_id(raw_key: str) -> str:
    if raw_key.startswith("mcp:"):          # mcp:{srv}:{tool} → mcp_{srv}
        parts = raw_key.split(":")
        return f"mcp_{parts[1]}" if len(parts) >= 3 else raw_key
    return raw_key.split(":")[-1] if ":" in raw_key else raw_key  # internal:{id} → {id}
```

- `update_agent_use_case.py`에 동일 로직이 있으면 함께 수정 (구현 시 확인).
- 동일 서버 도구 여러 개 선택 시 `mcp_{srv}` 중복 → 스켈레톤 구성에서 중복 제거.

## 5. 상세 설계 — 프론트엔드 (idt_front)

### 5-1. 변환 유틸 (신규): `src/utils/draftToolMapping.ts`

```typescript
/** 저장 형식 draft tool_ids → 카탈로그 형식 form.tools */
export function mapDraftToolIdsToCatalog(
  draftToolIds: string[],
  catalogTools: CatalogTool[] | undefined,
): string[] {
  const catalog = catalogTools ?? [];
  const result: string[] = [];
  for (const id of draftToolIds) {
    if (id.startsWith('mcp_')) {
      const serverId = id.slice('mcp_'.length);
      // tool_id 문자열 파싱 대신 mcp_server_id 필드 직접 비교 (더 견고)
      const serverTools = catalog.filter(
        (t) => t.source === 'mcp' && t.mcp_server_id === serverId,
      );
      // 카탈로그 미동기화(서버 단위 폴백) 시 원본 유지 — 저장은 가능
      result.push(...(serverTools.length ? serverTools.map((t) => t.tool_id) : [id]));
    } else {
      const catalogId = `internal:${id}`;
      result.push(catalog.some((t) => t.tool_id === catalogId) ? catalogId : id);
    }
  }
  return [...new Set(result)];
}
```

### 5-2. `handleApplyDraft` 수정 (`AgentBuilderPage/index.tsx`)

```typescript
const newTools = mapDraftToolIdsToCatalog(draft.tool_ids, catalogTools);
```

- 이후 로직(RAG_TOOL_ID 부수효과, documentExtractorDraft)은 카탈로그 형식 기준으로
  기존 코드 그대로 동작하게 됨.

### 5-3. 타입 동기화 (`types/agentComposer.ts`)

```typescript
workers: Array<{ tool_id: string; worker_id: string; description: string;
  sort_order: number; instruction: string; ... }>;
```

### 5-4. `ComposeDraftCard` — 도구별 지침 표시

- 기존 도구 목록(workers) 항목에 instruction이 있으면 항목 아래 접기(디스클로저)로 표시.
- instruction 빈 문자열이면 표시 생략 (하위호환).

## 6. 데이터 계약 변경 (api-contract-sync)

| API | 변경 | 하위호환 |
|-----|------|----------|
| `POST /api/v1/agents/compose` 응답 | `workers[].instruction` 추가 | 추가 필드 — 호환 |
| `POST /api/v1/agents` 등 builder 응답 | `workers[].instruction`(기본 `""`) 노출 | 추가 필드 — 호환 |
| `POST /api/v1/agents` 요청 | 변경 없음 (카탈로그 형식 MCP ID 정규화는 서버 내부 수정) | — |

## 7. 테스트 계획 (TDD — 테스트 먼저)

### 백엔드

| 테스트 | 파일 | 검증 |
|--------|------|------|
| composer가 worker instruction을 출력 스키마로 받는다 | `test_agent_composer.py` | `_WorkerOutput.instruction` 전파 |
| 시스템 프롬프트에 [도구 지침] 규칙 포함 | `test_agent_composer.py` | `_SYSTEM_PROMPT` 내 "[도구 지침]" 문자열 |
| MCP 병합 시 instruction "; " 병합 | `test_compose_agent_use_case.py` | `_map_mcp_workers` |
| 응답 workers[].instruction 노출 | `test_compose_agent_use_case.py` / `test_agent_composer_router.py` | `_to_response` |
| `_normalize_tool_id("mcp:srv:tool") == "mcp_srv"` | `test_create_agent_use_case_mcp.py` | D5 |
| `internal:{id}` 정규화 기존 동작 유지 | 〃 | 회귀 |

### 프론트엔드

| 테스트 | 파일 | 검증 |
|--------|------|------|
| mapDraftToolIdsToCatalog: internal/mcp/미매칭 3케이스 | `draftToolMapping.test.ts` (신규) | D2/D3 |
| 적용하기 → ToolPicker/도구함에 체크 표시 | `AgentBuilderStudio.test.tsx` | FR-08 회귀 |
| 적용하기 → RAG 도구 포함 시 toolConfigs 세팅 | 〃 | 부수효과 회귀 |
| 카드에 도구별 지침 표시/빈 값 생략 | `ComposeDraftCard.test.tsx` | FR-07 |

## 8. 구현 순서

1. **BE** `_normalize_tool_id` mcp: 처리 (테스트 → 수정) — 독립 버그 수정
2. **BE** WorkerDefinition/WorkerInfo instruction 필드 (테스트 → 수정)
3. **BE** composer instruction 생성 + 프롬프트 규칙 (테스트 → 수정)
4. **BE** use case 전파/병합 (테스트 → 수정)
5. **FE** mapDraftToolIdsToCatalog 유틸 (테스트 → 구현)
6. **FE** handleApplyDraft 적용 + 타입 동기화
7. **FE** ComposeDraftCard 지침 표시
8. 전체 테스트 (백: pytest 격리 실행 / 프론트: vitest --pool=threads)

## 9. 리스크 / 주의

- `WorkerDefinition`은 dataclass — 필드 추가 시 기존 저장 데이터(workers JSON)
  역직렬화 경로에 기본값 처리 확인 필요 (repository의 row→entity 변환부).
- 카탈로그 미동기화 상태(MCP 폴백)에서는 `mcp_{srv}`가 폼에 원본 유지로 남음 —
  체크 표시는 안 되지만 저장은 성공 (현행 폴백 한계, notes로 안내됨).
- instruction으로 structured output 토큰 증가 — max_candidates 100개 유지 시
  응답 지연 소폭 증가 예상. 문제 시 instruction 생성을 workers 상위 N개로 제한.
- LangSmith 추적(`agent-composer` 프로젝트)이 이미 붙어 있어 프롬프트 규칙 변경
  효과를 trace로 비교 검증 가능.
