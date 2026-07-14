# Plan: agent-builder-edit-mapping

> Created: 2026-07-13
> Status: Plan
> Scope: idt_front (표시 정합) + idt (선택적 — 수정 저장 확장)

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | `/agent-builder` 수정 화면 진입 시 (1) 모델이 표시명 대신 DB id(UUID)로 노출되고, (2) 도구함이 기존 부착 도구를 하나도 표시하지 못하며("추가된 도구가 없습니다"), (3) RAG 도구 설정도 기본값으로 초기화되어 보인다. 서브에이전트·스킬 매핑은 점검 결과 정상. |
| **Solution** | 수정 모드 폼 프라임(useEffect) 시 ① `llm_model_id → model_name` 역매핑, ② 저장 형식 tool_ids를 기존 유틸 `mapDraftToolIdsToCatalog`로 카탈로그 형식으로 변환, ③ `workers[].tool_config`에서 RAG 설정 복원. 프라임은 models/catalogTools 로딩 완료 후 1회만 수행. |
| **Function UX Effect** | 수정 화면이 저장된 에이전트의 실제 구성(모델 표시명, 부착 도구 목록, RAG 설정 배지)을 그대로 보여준다. 사용자가 "내 도구가 사라졌다"고 오인하는 상황 제거. |
| **Core Value** | 카탈로그/저장 tool_id 이중 네임스페이스 경계 규칙(변환 필수)을 수정 화면에도 일관 적용 — compose 초안 적용 경로에서 이미 검증된 변환 로직 재사용으로 리스크 최소화. |

## 1. 배경 — 조사 결과 (2026-07-13 코드 확인)

### 1-1. 이슈 ① 모델명이 id로 표시 (확인됨 — 버그)

- **프라임**: `idt_front/src/pages/AgentBuilderPage/index.tsx:96` — 수정 모드 진입 시
  `form.model = editDetail.llm_model_id` (DB id, UUID)를 그대로 대입.
- **표시**: `idt_front/src/components/agent-builder/LeftConfigPanel.tsx:150` —
  `models?.find((m) => m.model_name === form.model)` 으로 **model_name 기준** 조회.
  id ≠ model_name 이므로 매칭 실패 → fallback으로 `form.model`(raw id) 노출.
- **원인**: `form.model`의 의미가 경로별로 불일치.
  - 생성 경로: `form.model = model_name` (index.tsx:79 기본 모델, :180 저장 시 `m.model_name === form.model`로 id 역조회)
  - 초안 적용 경로: `models.find((m) => m.id === draft.llm_model_id)?.model_name`으로 **역매핑 선례 있음** (index.tsx:317)
  - 수정 경로: 역매핑 없이 id 대입 ← 유일하게 규칙 위반
- **부수 영향**: `ModelSettingsModal`의 현재 선택 표시도 같은 이유로 미선택 상태가 됨.

### 1-2. 이슈 ② 도구함 매핑 실패 (확인됨 — 버그)

- **프라임**: index.tsx:98 — `form.tools = editDetail.tool_ids` (저장 형식 그대로).
- **네임스페이스 계약** (`src/utils/draftToolMapping.ts` 주석 + 메모리 규칙):
  | 계층 | 형식 |
  |------|------|
  | 저장(DB worker.tool_id / GetAgentResponse.tool_ids) | `{id}`, `mcp_{server_id}` |
  | 카탈로그/폼(form.tools, ToolPicker, 도구함) | `internal:{id}`, `mcp:{srv}:{tool}` |
- **표시**: LeftConfigPanel.tsx:149 — `catalogTools.filter((t) => form.tools.includes(t.tool_id))`
  → 형식 불일치로 0건 매칭 → "추가된 도구가 없습니다" 표시.
- 동일 문제를 이미 해결한 변환 유틸 `mapDraftToolIdsToCatalog(draftToolIds, catalogTools)`가
  compose 초안 적용 경로(index.tsx:304)에서 사용 중 — **수정 프라임만 변환 누락**.

### 1-3. 이슈 ②-부속: RAG 등 도구 설정 미복원 (확인됨)

- 프라임 시 `toolConfigs: {}` 고정(index.tsx:100). `editDetail.workers[].tool_config`에
  저장된 RAG 설정(collection/kb/search_mode/top_k)이 있음에도 버림.
- 결과: 도구 매핑을 고쳐도 RAG 도구 행의 설정 요약 배지가 미표시, 설정 모달은 DEFAULT 값 표시.

### 1-4. 이슈 ③ 서브에이전트·스킬 매핑 (점검 결과 — 정상)

- **서브에이전트**: 정상. `GetAgentUseCase`(idt/src/application/agent_builder/get_agent_use_case.py:60-77)가
  `worker_type='sub_agent'` 워커의 `ref_agent_name`을 resolve(삭제 시 "(삭제됨)")해 내려주고,
  프라임(index.tsx:86-92)이 이를 `form.subAgents`로 매핑 → 화면 표시·저장(sub_agent_configs) 모두 동작.
- **스킬**: 정상. `skill_ids`(agent_skill 링크, skill_definition.id 체계)로 프라임하고
  `useSkills` 목록의 `s.id`와 같은 id 체계로 매칭 → 표시·저장 모두 동작.
- **경미한 엣지(관찰만, 수정 보류)**: 부착 스킬이 접근 가능 목록(`useSkills scope:'all', size:100`)에
  없으면(권한 밖 공유 스킬/삭제/100개 초과) 목록에서는 숨겨지지만 카운터(`스킬 N/6`)에는 포함되어 수치 불일치 가능.

### 1-5. 추가 발견 — 수정 저장 시 모델/도구 변경 무손실 폐기 (silent discard)

- 수정 모드 `handleSave`(index.tsx:150-178)는 `name / system_prompt / temperature /
  sub_agent_configs / skill_ids / document_template`만 전송. **모델·도구 변경은 전송 안 함.**
- 백엔드 `UpdateAgentRequest`(idt/src/application/agent_builder/schemas.py:102)에도
  `llm_model_id / tool_ids / tool_configs` 필드 자체가 없고, `UpdateAgentUseCase`는 도구 워커를 보존만 함.
- 현재는 도구함이 비어 보여 증상이 가려져 있으나, 본 수정(FR-2)으로 도구가 표시되면
  사용자가 도구를 토글/모델을 변경하고 저장해도 **조용히 무시**되는 UX 함정이 드러남.

## 2. 범위

### Phase 1 — 표시 정합 (본 Plan의 핵심, 프론트만)

| ID | 요구사항 | 구현 지점 |
|----|----------|-----------|
| FR-1 | 수정 프라임 시 `llm_model_id → model_name` 역매핑. 역매핑 실패(모델 레지스트리에서 삭제된 id) 시 raw id 유지 + 화면에 '미등록 모델' 안내 | `AgentBuilderPage/index.tsx` 프라임 effect |
| FR-2 | 수정 프라임 시 `tool_ids`(저장 형식) → 카탈로그 형식 변환. 기존 `mapDraftToolIdsToCatalog` 재사용 | 동일 effect |
| FR-3 | 수정 프라임 시 `workers[].tool_config` → `form.toolConfigs[RAG_TOOL_ID]` 복원 (RAG 워커 한정, kb_id/collection_name/search_mode/top_k/use_wiki_first) | 동일 effect |
| FR-4 | 프라임 타이밍 보정: `editDetail`·`models`·`catalogTools`가 모두 준비된 시점에 **1회만** 프라임 (이후 재실행으로 사용자 편집 내용을 덮어쓰지 않도록 가드) | 동일 effect + ref 가드 |

### Phase 2 — 수정 저장 확장 (스코프 결정 필요, 백엔드+프론트)

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-5 | `UpdateAgentRequest`에 `llm_model_id: str \| None` 추가(None=변경 안 함) + `apply_update` 반영 + 프론트 전송 | 기존 옵셔널 필드 선례(temperature 등)와 동일 패턴 — 기존 동작 무변경 |
| FR-6 | 도구 워커 교체 지원(`tool_ids`/`tool_configs`, None=변경 안 함) — 도구 형식 역변환(카탈로그→저장) 포함 | 영향 범위 큼(워커 재구성·RAG config 검증·visibility scope 재검증). **별도 feature로 분리 권장** |

**권장**: Phase 1 + FR-5까지 본 feature로 진행, FR-6은 후속 feature(`agent-builder-edit-tools-save`)로 분리.
FR-6 분리 시 임시 방어로 수정 모드 도구함에 "도구 변경은 저장되지 않습니다" 안내 또는 토글 비활성 여부를 Design에서 결정.

### 제외 (Out of Scope)

- 스킬 카운터/목록 불일치 엣지(§1-4) — 발생 조건이 좁고 데이터 손실 없음
- 문서추출기 템플릿의 서버 상태 복원(현재 sessionStorage 복원만) — 별도 feature
- 비주얼 캔버스(VisualCanvas)의 표시 로직 — form 데이터를 공유하므로 FR-1~3으로 자동 개선

## 3. 설계 방향 (Design 단계에서 상세화)

1. **프라임 함수 분리**: `mapDetailToForm(editDetail, models, catalogTools): AgentBuilderFormData`
   순수 함수로 추출 → 단위 테스트 용이(Vitest). 프라임 effect는 이 함수 호출 + 1회 가드만 담당.
2. **역매핑 규칙 재사용**: 모델은 초안 적용 경로(index.tsx:317)와 동일한
   `models.find((m) => m.id === llm_model_id)?.model_name ?? llm_model_id` 패턴.
3. **도구 변환 재사용**: `mapDraftToolIdsToCatalog` 그대로 사용 — 카탈로그 미동기화 시
   원본 유지 폴백이 이미 내장되어 있어 수정 화면에서도 저장 가능성 보존.
4. **레이어 영향**: Phase 1은 프론트 전용. FR-5는 application 스키마+엔티티 `apply_update`만
   (도메인 정책 변경 없음). DB 스키마 변경 없음.

## 4. TDD 절차

1. **Red**: `mapDetailToForm` 단위 테스트 신규 작성
   - id→model_name 역매핑 / 미등록 id 폴백
   - 저장 형식 tool_ids → 카탈로그 형식 (internal / mcp_{srv} / 카탈로그 미존재 폴백)
   - RAG worker tool_config → toolConfigs 복원 / RAG 워커 없으면 빈 객체
   - 서브에이전트·스킬 매핑 회귀 고정 (현행 정상 동작 보호)
2. **Green**: 프라임 effect 리팩토링 + 함수 구현
3. **회귀**: `LeftConfigPanel.test.tsx`, `AgentBuilderStudio.test.tsx` 통과 확인
   (실행: `npx vitest run --pool=threads` — Windows forks 타임아웃 회피)
4. FR-5 진행 시: 백엔드 `tests/application/agent_builder/test_update_agent*` Red→Green 선행

## 5. 리스크 / 영향

| 리스크 | 대응 |
|--------|------|
| 프라임 effect 재실행으로 사용자 편집 덮어씀 (models 늦게 도착 등) | FR-4: editingId 기준 1회 가드(ref). 의존성 배열에 models/catalogTools 추가하되 가드로 재프라임 차단 |
| 카탈로그 API 실패 시 도구 미표시 | `mapDraftToolIdsToCatalog` 원본 유지 폴백 + 기존 isToolsError 재시도 UI 활용 |
| FR-2 적용 후 "도구 토글해도 저장 안 됨" 함정 표면화 | §2 Phase 2 스코프 결정 필수 — 최소한 안내 문구 필요 |
| mcp_{server_id} → 서버 단위 다건 확장으로 도구 수 표시가 저장 개수와 달라 보임 | 기존 compose 경로와 동일 동작(일관성 우선), Design에서 표기 확정 |

## 6. 완료 기준 (Acceptance)

- [ ] 수정 화면 진입 시 모델 섹션에 `provider:model_name` 표시 (id 노출 없음)
- [ ] 수정 화면 도구함에 저장된 도구(내부/MCP)가 이름·MCP 배지와 함께 표시
- [ ] RAG 도구 행에 저장된 설정 요약 배지(컬렉션/모드/top_k) 표시
- [ ] 서브에이전트·스킬 목록 표시 회귀 없음 (테스트로 고정)
- [ ] (FR-5 포함 시) 수정 화면에서 모델 변경 후 저장 → 재진입 시 변경 모델 표시
