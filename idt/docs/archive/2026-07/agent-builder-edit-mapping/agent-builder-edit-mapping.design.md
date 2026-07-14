# Design: agent-builder-edit-mapping

> Created: 2026-07-13
> Plan: `docs/01-plan/features/agent-builder-edit-mapping.plan.md`
> Scope: Phase 1(표시 정합, 프론트) + FR-5(모델 저장, 백+프론트). FR-6(도구 저장)은 후속 feature.

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 수정 화면 프라임이 `llm_model_id`(id)와 저장 형식 `tool_ids`를 무변환 대입하고 `toolConfigs`를 버려, 모델이 id로 노출·도구함 0건·RAG 설정 초기화로 보인다. 수정 저장은 모델 변경을 전송조차 하지 않는다. |
| **Solution** | 순수 함수 `mapDetailToForm(detail, models, catalogTools)`로 프라임 매핑을 일원화(모델 역매핑 + `mapDraftToolIdsToCatalog` 재사용 + RAG worker config 복원)하고, 쿼리 3종 settled 후 1회만 프라임한다. 백엔드는 `UpdateAgentRequest.llm_model_id`(None=무변경) 옵셔널 확장으로 모델 저장을 지원한다. |
| **Function UX Effect** | 수정 화면이 저장된 구성을 그대로 표시하고, 모델 변경이 실제로 저장된다. 도구 토글은 저장되지 않음을 배너로 명시해 무손실 폐기 함정을 제거한다. |
| **Core Value** | 검증된 변환 유틸 재사용 + 기존 옵셔널 필드 패턴(temperature 선례) 준수로 기존 동작 무변경(additive) 확장. |

---

## 1. 아키텍처 개요

```
[수정 진입]
GET /agents/{id} ──► editDetail(AgentDetail) ─┐
GET /llm-models  ──► models ──────────────────┼─► mapDetailToForm() ─► form (1회 프라임)
GET /tool-catalog ─► catalogTools ────────────┘        │
                                                        ├─ model: id → model_name 역매핑
                                                        ├─ tools: mapDraftToolIdsToCatalog()
                                                        └─ toolConfigs: RAG worker tool_config 복원
[수정 저장]
form ─► PATCH /agents/{id}  { ..., llm_model_id? }  ← FR-5 신규 필드
        └─ 백엔드: UpdateAgentRequest → UseCase 검증(llm_model_repo) → apply_update → repo.update 영속
```

레이어 영향: FE 전용 유틸 + application 스키마/UseCase + domain `apply_update` 파라미터 추가 + infrastructure repo update 1줄. DB 스키마 변경 없음(컬럼 기존재).

---

## 2. 프론트엔드 설계

### 2-1. `mapDetailToForm` 순수 함수 (신규) — FR-1/2/3

**파일**: `idt_front/src/utils/agentDetailMapping.ts` (신규)

```ts
import type { AgentDetail } from '@/types/agentStore';
import type { LlmModel } from '@/types/llmModel';
import type { CatalogTool } from '@/types/toolCatalog';
import type { AgentBuilderFormData } from '@/types/agentBuilder';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import { mapDraftToolIdsToCatalog } from './draftToolMapping';

/** 저장 형식 RAG worker tool_id (카탈로그 형식 internal:internal_document_search의 저장측) */
const RAG_WORKER_TOOL_ID = 'internal_document_search';
export const RAG_CATALOG_TOOL_ID = 'internal:internal_document_search';

export function mapDetailToForm(
  detail: AgentDetail,
  models: LlmModel[] | undefined,
  catalogTools: CatalogTool[] | undefined,
): AgentBuilderFormData
```

**매핑 규칙**:

| form 필드 | 소스 | 규칙 |
|-----------|------|------|
| `model` | `detail.llm_model_id` | `models?.find((m) => m.id === detail.llm_model_id)?.model_name ?? detail.llm_model_id` — 초안 적용 경로(index.tsx:317)와 동일 패턴. 역매핑 실패(레지스트리에서 삭제된 모델) 시 raw id 유지 → §2-4 라벨 폴백이 처리 |
| `tools` | `detail.tool_ids` | `mapDraftToolIdsToCatalog(detail.tool_ids, catalogTools)` — 기존 유틸 그대로. 카탈로그 미매칭 시 원본 유지 폴백 내장 |
| `toolConfigs` | `detail.workers` | RAG worker(`worker_type === 'tool' && tool_id === RAG_WORKER_TOOL_ID && tool_config`)가 있으면 `{ [RAG_CATALOG_TOOL_ID]: { ...DEFAULT_RAG_CONFIG, ...worker.tool_config } }`, 없으면 `{}`. DEFAULT 머지로 서버에 없는 신규 필드(use_wiki_first 등) 기본값 보장 |
| `subAgents` | `detail.workers` | 현행 로직 이동(worker_type='sub_agent' 필터 + ref_agent_name ?? ref_agent_id) — 동작 무변경, 함수로 흡수해 테스트 고정 |
| `skills` | `detail.skill_ids ?? []` | 현행 유지 |
| `name/description/systemPrompt/temperature` | detail 동명 필드 | 현행 유지 |
| `schedules` | — | `[]` (edit 모드 SchedulePanel 서버 직결, 현행 유지) |

- `RAG_TOOL_ID` 상수는 현재 index.tsx:39와 LeftConfigPanel.tsx:28에 중복 정의 — 본 유틸의 `RAG_CATALOG_TOOL_ID` export로 통합하고 두 파일은 import로 전환(중복 제거, 동작 무변경).

### 2-2. 프라임 effect 재구성 — FR-4

**파일**: `idt_front/src/pages/AgentBuilderPage/index.tsx` (기존 effect 84-107행 교체)

```ts
const primedAgentRef = useRef<string | null>(null);

useEffect(() => {
  if (view !== 'edit' || !editingId || !editDetail) return;
  if (isModelsLoading || isToolsLoading) return;   // 쿼리 settled 대기 (에러 종료 포함)
  if (primedAgentRef.current === editingId) return; // 1회 가드 — 사용자 편집 보호
  primedAgentRef.current = editingId;
  setForm(mapDetailToForm(editDetail, models, catalogTools));
}, [editDetail, models, catalogTools, isModelsLoading, isToolsLoading, view, editingId]);
```

- **settled 기준**: `isLoading === false`. 에러로 끝난 경우 `models`/`catalogTools`는 undefined로 전달 → 매핑 함수의 폴백(raw 유지)이 동작해 현행보다 나빠지지 않음. 재시도 성공 후에도 **재프라임하지 않음**(편집 내용 보호 우선) — 한계로 기록.
- `handleEdit`/`handleNew`에서 `primedAgentRef.current = null` 리셋 (같은 에이전트 재진입 시 최신 detail로 재프라임 허용 — react-query가 detail을 refetch하므로 stale 프라임 방지).
- 기본 모델 주입 effect(75-82행)는 create 전용이므로 `view === 'create'` 조건 추가(edit 프라임과의 경합 차단).

### 2-3. 수정 저장 시 모델 전송 — FR-5 (FE)

**파일**: `index.tsx` handleSave edit 분기, `types/agentBuilder.ts`

```ts
// types/agentBuilder.ts — UpdateBuilderAgentRequest에 추가
/** undefined = 모델 변경 안 함 */
llm_model_id?: string;

// handleSave edit 분기 — create 경로(index.tsx:180)와 동일한 역조회
llm_model_id: models?.find((m) => m.model_name === form.model)?.id,
```

- `form.model`이 미등록 raw id인 경우(역매핑 실패 상태) 역조회도 실패 → `undefined` 전송 → 백엔드 "변경 안 함" — 의도된 안전 동작.
- API 계약 동기화: `idt_front/src/types/agentBuilder.ts` ↔ `idt/src/application/agent_builder/schemas.py` (§3-1).

### 2-4. 미등록 모델 라벨 폴백 — FR-1 부속

**파일**: `LeftConfigPanel.tsx:150-153`

```ts
const currentModel = models?.find((m) => m.model_name === form.model);
const modelLabel = currentModel
  ? `${currentModel.provider}:${currentModel.model_name}`
  : form.model
    ? `${form.model} (미등록 모델)`
    : '모델 미선택';
```

### 2-5. 수정 모드 도구 변경 미저장 안내 배너 — FR-6 유예 방어

**결정**: 토글 비활성화가 아닌 **안내 배너** (기존 토글 동작 보존 — opt-in/무변경 선호 원칙, FR-6 구현 시 배너만 제거하면 됨).

**파일**: `LeftConfigPanel.tsx` 도구함 섹션. `isEditMode`(기존 prop, 현재 미사용으로 destructure 누락 상태 → 복원)일 때 도구함 목록 상단에 1줄 안내:

```tsx
{isEditMode && (
  <p className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-[11.5px] text-amber-700">
    도구 구성 변경은 아직 저장되지 않습니다 (모델·지침·서브에이전트·스킬은 저장됨)
  </p>
)}
```

---

## 3. 백엔드 설계 — FR-5 (모델 변경 저장)

### 3-1. UpdateAgentRequest 확장

**파일**: `idt/src/application/agent_builder/schemas.py:102`

```python
class UpdateAgentRequest(BaseModel):
    ...
    # agent-builder-edit-mapping FR-5: None = 모델 변경 안 함
    llm_model_id: str | None = None
```

### 3-2. UpdateAgentUseCase — 검증 + 적용

**파일**: `idt/src/application/agent_builder/update_agent_use_case.py`

- 생성자에 `llm_model_repo: LlmModelRepositoryInterface | None = None` 추가(옵셔널 — 기존 생성 코드 무변경).
- `execute()` 내 `apply_update` 호출 전에:

```python
if request.llm_model_id is not None:
    if self._llm_model_repo is None:
        raise ValueError("llm_model_id 수정에는 llm_model_repo 주입이 필요합니다")
    found = await self._llm_model_repo.find_by_id(request.llm_model_id, request_id)
    if found is None:
        raise ValueError(f"LLM 모델을 찾을 수 없습니다: {request.llm_model_id}")
```

- `agent.apply_update(..., llm_model_id=request.llm_model_id)` 전달.
- 검증 패턴은 `CreateAgentUseCase._resolve_llm_model_id`(create_agent_use_case.py:452)와 동일 — 단 default 폴백은 없음(None=무변경이므로 불필요).

### 3-3. 도메인 `apply_update` 파라미터 추가

**파일**: `idt/src/domain/agent_builder/schemas.py:121`

```python
def apply_update(
    self, ..., max_iterations: int | None = None,
    llm_model_id: str | None = None,
) -> None:
    ...
    if llm_model_id is not None:
        self.llm_model_id = llm_model_id
```

- 도메인은 문자열 대입만(존재 검증은 application 책임 — 레이어 규칙 준수).

### 3-4. Repository update 영속 (필수 — 누락 시 조용히 미저장)

**파일**: `idt/src/infrastructure/agent_builder/agent_definition_repository.py:95` `update()`

현재 update는 `system_prompt/name/visibility/department_id/temperature/max_iterations`만 컬럼 반영 → **`model.llm_model_id = agent.llm_model_id` 1줄 추가** (조사에서 확인된 누락 지점, 이 줄 없으면 FR-5 전체가 무효).

### 3-5. DI 배선

**파일**: `idt/src/api/main.py:2278` `update_uc_factory`

```python
return UpdateAgentUseCase(
    ...,
    llm_model_repo=_make_llm_model_repo(session),  # create 경로와 동일 팩토리 재사용
)
```

(create 경로에서 사용 중인 llm_model_repository 팩토리를 확인 후 동일 함수 재사용 — 신규 세션 생성 금지 규칙 준수.)

---

## 4. 변경 파일 총괄

| # | 파일 | 변경 | FR |
|---|------|------|----|
| 1 | `idt_front/src/utils/agentDetailMapping.ts` | **신규** — mapDetailToForm + RAG_CATALOG_TOOL_ID | 1,2,3 |
| 2 | `idt_front/src/pages/AgentBuilderPage/index.tsx` | 프라임 effect 교체 + primedAgentRef + 기본모델 effect create 한정 + edit 저장에 llm_model_id | 4,5 |
| 3 | `idt_front/src/components/agent-builder/LeftConfigPanel.tsx` | 모델 라벨 폴백 + isEditMode 배너 + RAG_TOOL_ID import 전환 | 1,6방어 |
| 4 | `idt_front/src/types/agentBuilder.ts` | UpdateBuilderAgentRequest.llm_model_id 추가 | 5 |
| 5 | `idt/src/application/agent_builder/schemas.py` | UpdateAgentRequest.llm_model_id | 5 |
| 6 | `idt/src/application/agent_builder/update_agent_use_case.py` | llm_model_repo 주입 + 검증 + apply_update 전달 | 5 |
| 7 | `idt/src/domain/agent_builder/schemas.py` | apply_update llm_model_id 파라미터 | 5 |
| 8 | `idt/src/infrastructure/agent_builder/agent_definition_repository.py` | update()에 llm_model_id 컬럼 반영 1줄 | 5 |
| 9 | `idt/src/api/main.py` | update_uc_factory에 llm_model_repo 배선 | 5 |

---

## 5. 테스트 설계 (TDD — Red 먼저)

### 5-1. FE 단위: `agentDetailMapping.test.ts` (신규)

| 케이스 | 검증 |
|--------|------|
| 모델 역매핑 성공 | llm_model_id=uuid, models에 매칭 → form.model = model_name |
| 모델 역매핑 실패 | models에 없는 id → form.model = raw id 유지 |
| models undefined | raw id 유지 (에러 settled 경로) |
| internal 도구 변환 | `['internal_document_search']` → `['internal:internal_document_search']` |
| mcp 도구 변환 | `['mcp_srv1']` → 해당 서버 카탈로그 도구들로 확장 |
| 카탈로그 미매칭 폴백 | 카탈로그에 없는 id → 원본 유지 |
| RAG config 복원 | RAG worker tool_config → toolConfigs[RAG_CATALOG_TOOL_ID], DEFAULT 머지 확인 |
| RAG worker 없음 | toolConfigs = {} |
| 서브에이전트 매핑 회귀 | sub_agent worker → subAgents(name=ref_agent_name, 폴백 ref_agent_id) |
| 스킬 매핑 회귀 | skill_ids → skills, 미존재 시 [] |

### 5-2. FE 컴포넌트: 기존 테스트 확장

- `LeftConfigPanel.test.tsx`: 미등록 모델 라벨 `(미등록 모델)` 표시 / isEditMode 배너 렌더링.
- `AgentBuilderStudio.test.tsx`(또는 페이지 테스트): edit 프라임 후 도구함에 도구명 표시 + 모델 표시명 렌더 + 1회 프라임(카탈로그 지연 도착 시 폼 리셋 없음) 시나리오.
- 실행: `npx vitest run --pool=threads` (Windows forks 타임아웃 회피), MSW는 파일별 listen 훅 직접 선언.

### 5-3. BE: `tests/application/agent_builder/test_update_agent_llm_model.py` (신규 또는 기존 update 테스트 확장)

| 케이스 | 검증 |
|--------|------|
| llm_model_id=None | 모델 무변경 (기존 값 유지) — 기존 테스트 회귀 보호 |
| 유효 id | agent.llm_model_id 갱신 + repo.update 호출 인자 확인 |
| 미존재 id | ValueError("LLM 모델을 찾을 수 없습니다") |
| repo 미주입 + id 전달 | ValueError(주입 필요) |
| domain 단위 | apply_update(llm_model_id=...) 반영 / None 무변경 |

- 실행: 해당 테스트 파일 격리 실행(Windows 이벤트루프 teardown 산발 실패 회피).

---

## 6. 구현 순서

1. **BE Red→Green** (5-3): 스키마 → 도메인 → UseCase → repo 1줄 → DI 배선
2. **FE Red→Green** (5-1): agentDetailMapping.ts 유틸 + 단위 테스트
3. **FE 배선** (5-2): 프라임 effect 교체 → LeftConfigPanel 라벨/배너 → edit 저장 llm_model_id
4. **회귀**: FE `vitest run --pool=threads` 전체(사전 실패 8건은 기존 이슈) / BE 대상 테스트 격리 실행
5. **수동 확인**: 기존 에이전트 수정 진입 → 모델 표시명·도구 목록·RAG 배지 확인 → 모델 변경 저장 → 재진입 확인

## 7. 엣지 케이스 / 한계

- **카탈로그 재시도 성공 후 미재프라임**: 도구가 raw id로 남을 수 있음(목록 미표시) — 편집 보호 우선, 화면 재진입으로 해소. 한계로 문서화.
- **mcp_{srv} → 다건 확장**: 저장 1건이 화면 N건으로 보임 — compose 초안 경로와 동일 동작(일관성 유지).
- **visibility 검증과의 상호작용 없음**: llm_model_id는 visibility scope 검증(§update_agent_use_case._validate_visibility_scope)과 무관 — 교차 영향 없음.
- **에이전트 실행 경로**: workflow_compiler가 저장된 llm_model_id로 모델 로드 — FR-5로 모델 변경 시 다음 실행부터 즉시 반영(추가 작업 불필요, 확인만).
