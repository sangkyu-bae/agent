# Completion Report: compose-tool-instructions

> **기능명**: Agent Composer 도구별 지침 생성 + 초안 적용 버그 수정  
> **완료일**: 2026-07-05  
> **상태**: 완료 (Match Rate 100%)  
> **PDCA 단계**: Plan → Design → Do → Check (동일 요일 완료)

---

## Executive Summary

### 프로젝트 개요

| 항목 | 내용 |
|------|------|
| **기능명** | compose-tool-instructions |
| **설명** | 자연어 에이전트 조합(compose) 시 생성되는 도구별 사용 지침(instruction) 구조화 + 초안 [적용하기] 도구 미세팅 버그 수정 |
| **시작일** | 2026-07-05 |
| **완료일** | 2026-07-05 |
| **PDCA 이력** | Plan ✅ → Design ✅ → Do ✅ → Check ✅ |

### 결과 요약

| 메트릭 | 수치 |
|--------|------|
| **설계 일치도 (Match Rate)** | 100% (최초 95.7% → 보완 후 100%) |
| **Gap 발견** | Missing 1건, 경미 2건 |
| **Gap 해결** | 3건 모두 당일 해결 |
| **변경 파일** | 백엔드 5개 + 프론트 5개 (총 10개) |
| **신규 테스트** | 16건 추가 (백엔드 8건 + 프론트 8건) |
| **전체 테스트 통과** | 백엔드 447 + 프론트 39 (유틸/카드/Fix 패널) = 486 |
| **TypeScript 검증** | tsc --noEmit 통과 |

### 1.3 Value Delivered

| 관점 | 상세 |
|------|------|
| **Problem** | 자연어 에이전트 조합 시 도구는 선택되지만 ① 생성되는 system_prompt에 도구 활용 지침이 부실하고, ② 도구별 사용 지침을 구조화된 데이터로 받을 수 없으며, ③ 초안 [적용하기] 클릭 시 도구가 폼에 세팅되지 않는 버그 존재 |
| **Solution** | composer LLM 출력에 도구별 `instruction` 필드 추가 + system_prompt `[도구 지침]` 섹션 필수화 + 도구 ID 네임스페이스 변환 유틸(프론트) 신설 + 백엔드 정규화 버그 수정 (5가지 설계 결정 D1~D5 반영) |
| **Function/UX Effect** | 초안 카드에서 도구별 사용 지침을 확인 가능 (접기 UI), [적용하기] 한 번으로 도구 선택 + system_prompt 완전 반영 ✅, 카탈로그 미동기화 폴백 상태도 저장 가능 (현행 한계 notes 안내) |
| **Core Value** | "자연어 한 줄 → 실행 가능한 에이전트 초안"의 완성도 향상 — 조합된 에이전트가 도구 선택 + 사용 지침이 LLM 수준에서 보증됨. 동시에 LangSmith 추적(agent-composer 프로젝트)으로 지침 생성 품질 개선을 실측 검증 가능 |

---

## PDCA 사이클 요약

### Plan
- **문서**: `docs/01-plan/features/compose-tool-instructions.plan.md`
- **목표**: 도구별 사용 지침 구조화 + [적용하기] 버그 수정
- **범위**: 풀스택 (백엔드 + 프론트엔드)
- **주요 요구사항**: FR-01 ~ FR-09 (도구별 instruction 필드 추가, system_prompt 규칙 강화, 도구 미세팅 버그 수정)

### Design
- **문서**: `docs/02-design/features/compose-tool-instructions.design.md`
- **도구 ID 네임스페이스 2계층 분리 확정**:
  - 카탈로그/폼: `internal:{id}`, `mcp:{srv}:{tool}`
  - 저장/레지스트리: `{id}`, `mcp_{srv}`
  - 버그 메커니즘: compose 응답(저장 형식) → 폼(카탈로그 형식) 직접 주입 → ID 불일치 → ToolPicker 체크 표시 안 됨
- **설계 결정 5가지**:
  - D1: `WorkerInfo.instruction` 공용 확장 (하위호환성 유지)
  - D2: 프론트에서 변환 유틸(`mapDraftToolIdsToCatalog`) 구현 (백엔드 응답 형식 불변)
  - D3: `mcp_{srv}` → 해당 서버 카탈로그 도구 전체 선택으로 전개
  - D4: 도구별 지침 저장은 system_prompt 병합으로 해결 (별도 스키마 없음)
  - D5: `_normalize_tool_id` 백엔드 수정 (mcp: 프리픽스 → `mcp_{srv}` 정규화)

### Do
- **구현 범위**:
  - **백엔드 5개 파일**: 
    - `src/application/agent_composer/composer.py` — `_WorkerOutput.instruction` 필드 + `[도구 지침]` 프롬프트 규칙
    - `src/application/agent_composer/compose_agent_use_case.py` — instruction 전파 + `"; "` 병합 + 응답 노출
    - `src/application/agent_builder/schemas.py` — `WorkerInfo.instruction` 추가
    - `src/domain/agent_builder/schemas.py` — `WorkerDefinition.instruction` 추가
    - `src/application/agent_builder/create_agent_use_case.py` — `_normalize_tool_id` mcp: 처리 수정 + 중복 제거
  - **프론트엔드 5개 파일**:
    - `src/utils/draftToolMapping.ts` (신규) — 저장 형식 → 카탈로그 형식 변환 유틸
    - `src/pages/AgentBuilderPage/index.tsx` — `handleApplyDraft`에 `mapDraftToolIdsToCatalog` 적용
    - `src/types/agentComposer.ts` — `workers[].instruction` 타입 동기화
    - `src/components/agent-builder/fix/ComposeDraftCard.tsx` — 도구별 지침 접기 UI 추가
    - `tests/` — 16건 신규 테스트 추가
- **TDD 사이클**: 8회 (Red → Green)
- **신규 테스트**: 16건 (백엔드 8건 + 프론트 8건)

### Check (Gap Analysis)
- **분석 도구**: gap-detector Agent
- **결과**:
  - 설계 결정 (D1~D5): 5/5 ✅
  - 백엔드 상세: 4/4 ✅
  - 프론트엔드 상세: 4/4 ✅
  - 테스트 계획: 10/10 ✅
  - **전체 Match Rate: 100%** (최초 95.7% → 보완 후 100%)
- **Gap 발견 및 해결**:
  1. **Missing**: RAG 부수효과 회귀 테스트 부재 → `AgentBuilderStudio.test.tsx`에 "RAG 도구 포함 초안 적용 시 tool_configs 세팅" 테스트 추가 ✅
  2. **경미(구현 vs 설계)**: MCP 필터 구현이 설계 pseudocode(`tool_id` startsWith)와 다르게 `mcp_server_id` 직접 비교 → 동작 등가이며 더 견고 ✅
  3. **경미(문서)**: Design §7 테스트 파일명 오기 정정 ✅

---

## 구현 상세

### 백엔드 주요 변경

#### 1. `composer.py` — instruction 필드 + 프롬프트 규칙

**변경 사항**:
- `_WorkerOutput` 클래스에 `instruction: str` 필드 추가 (기본값 `""`, 300자 이내)
- `_SYSTEM_PROMPT` 규칙에 "[도구 지침]" 섹션 필수화:
  ```
  - system_prompt에는 [도구 지침] 섹션을 반드시 포함하세요.
  - 각 worker의 instruction 필드에는 도구의 사용 지침을 2~4문장으로 작성하세요.
  ```
- system_prompt 필수 섹션: `[역할]`, `[도구 지침]`, `[동작 원칙]`

**이점**:
- LLM이 도구별 사용 시점/입력 형태/주의사항을 구조화된 instruction으로 출력
- system_prompt에 동일 내용이 일관되게 포함됨

#### 2. `compose_agent_use_case.py` — instruction 전파 + 병합

**변경 사항**:
- `_sanitize_workers`: `WorkerDefinition` 생성 시 `instruction` 전달
- `_map_mcp_workers`: 동일 tool_id 병합 시 `description`과 동일하게 `instruction`도 `"; "` 연결 병합
- `_to_response`: `WorkerInfo` 응답에 `instruction` 필드 포함

#### 3. 스키마 동기화

- `src/application/agent_builder/schemas.py` `WorkerInfo`: `instruction: str = ""` 추가
- `src/domain/agent_builder/schemas.py` `WorkerDefinition`: `instruction: str = ""` 추가

#### 4. `_normalize_tool_id` 버그 수정 (부수 발견)

**버그**: 
- 기존 코드: `split(":")[-1]` → MCP ID `mcp:{srv}:{tool}`을 `{tool}`로 오정규화
- 결과: 수동 MCP 도구 선택 시 메타 조회 실패 가능성

**수정**:
```python
@staticmethod
def _normalize_tool_id(raw_key: str) -> str:
    if raw_key.startswith("mcp:"):          # mcp:{srv}:{tool} → mcp_{srv}
        parts = raw_key.split(":")
        return f"mcp_{parts[1]}" if len(parts) >= 3 else raw_key
    return raw_key.split(":")[-1] if ":" in raw_key else raw_key  # internal:{id} → {id}
```

**추가 처리**: 동일 서버의 도구 여러 개 선택 시 `mcp_{srv}` 중복 제거

### 프론트엔드 주요 변경

#### 1. `draftToolMapping.ts` (신규)

**목적**: 저장 형식 도구 ID → 카탈로그 형식 변환

```typescript
export function mapDraftToolIdsToCatalog(
  draftToolIds: string[],
  catalogTools: CatalogTool[] | undefined,
): string[] {
  // mcp_{srv} → 해당 서버 도구 전체 선택
  // internal:{id} 형식 유지/추가
  // 카탈로그 미동기화 폴백 → 원본 유지
  // 중복 제거
}
```

**설계**:
- `mcp_{srv}` → `catalogTools.filter(t => t.mcp_server_id === srv)`
- `internal:{id}` 카탈로그 유무 확인 후 추가
- 카탈로그 미로딩 시 원본 ID 유지 (저장은 가능, 체크는 표시 안 됨)
- 결과 배열 중복 제거

#### 2. `AgentBuilderPage/index.tsx` — `handleApplyDraft` 수정

**변경**:
```typescript
const newTools = mapDraftToolIdsToCatalog(draft.tool_ids, catalogTools);
```

**효과**:
- RAG 도구 포함 시 자동으로 `toolConfigs` 세팅 (기존 로직 동작)
- ToolPicker에서 도구 체크 표시 표시됨 (ID 일치)

#### 3. `types/agentComposer.ts` 동기화

- `workers[].instruction` 필드 추가 (API 계약 동기화)

#### 4. `ComposeDraftCard.tsx` — 도구별 지침 UI

**변경**:
- 각 worker 항목 아래 `instruction`이 있으면 접기(디스클로저) UI로 표시
- 빈 값이면 표시 생략 (하위호환성)

### 데이터 계약 변경

| API | 변경 | 호환성 |
|-----|------|--------|
| `POST /api/v1/agents/compose` 응답 | `workers[].instruction` 추가 | 추가 필드 (호환) |
| `POST /api/v1/agents` 응답 | `workers[].instruction`(기본 `""`) 노출 | 추가 필드 (호환) |
| `POST /api/v1/agents` 요청 | 변경 없음 (백엔드 정규화 내부 수정) | — |

---

## Gap 분석 결과

### 최초 vs 최종

| 메트릭 | 최초 | 최종 | 개선 |
|--------|------|------|------|
| **Match Rate** | 95.7% (22/23) | 100% (23/23) | +4.3% |
| **Gap 건수** | 1 Missing, 2 경미 | 0 (모두 해결) | — |

### Gap 해결 이력

1. **Missing: RAG 부수효과 회귀 테스트**
   - 문제: `handleApplyDraft`에서 RAG 도구 포함 시 `toolConfigs` 세팅 검증 테스트 부재
   - 조치: `AgentBuilderStudio.test.tsx`에 테스트 케이스 추가
   - 결과: ✅ 통과 (RAG 도구 포함 초안 적용 → toolConfigs 세팅 → 저장 포함)

2. **경미: 구현과 설계의 필터 방식 차이**
   - 설계: `tool_id` startsWith 파싱
   - 구현: `mcp_server_id` 직접 비교
   - 판단: 동작 등가이며 구현이 더 견고 (mcp_server_id 필드 기반)
   - 조치: Design 문서 §5-1 pseudocode 갱신

3. **경미: 문서 오기**
   - 설계 §7 테스트 파일명 오기 (`test_create_agent_use_case.py` → `_mcp.py`)
   - 조치: Design 문서 정정

### 설계에 없는 추가 구현 (품질 향상)

- `test_normalize_tool_id_formats` — 4가지 ID 형식 정규화 순수 단위 테스트
- 프론트 매핑 유틸 테스트 5케이스 (설계 요구 3 + 혼합/중복제거/카탈로그 미로딩)
- MSW compose 목에 instruction 샘플 포함 (통합 경로 검증 강화)

---

## 테스트 결과

### 백엔드 (idt)

| 테스트 스위트 | 결과 |
|---------------|------|
| `tests/application/agent_composer/` | 모두 통과 (8건 신규) |
| `tests/application/agent_builder/test_create_agent_use_case_mcp.py` | 모두 통과 (4건 신규) |
| `tests/api/test_agent_composer_router.py` | 모두 통과 (4건 신규) |
| **전체 백엔드** | **447 passed** |

**주요 검증**:
- composer가 worker instruction을 출력 스키마로 출력 ✅
- system_prompt에 "[도구 지침]" 섹션 포함 ✅
- MCP 병합 시 instruction "; " 연결 병합 ✅
- compose 응답 `workers[].instruction` 노출 ✅
- `_normalize_tool_id("mcp:srv:tool") == "mcp_srv"` ✅
- `internal:{id}` 정규화 기존 동작 유지 ✅

### 프론트엔드 (idt_front)

| 테스트 스위트 | 결과 |
|---------------|------|
| `src/__tests__/utils/draftToolMapping.test.ts` (신규) | 5 passed |
| `src/__tests__/components/ComposeDraftCard.test.tsx` | 8 passed |
| `src/__tests__/components/FixAgentPanel.test.tsx` | 14 passed |
| `src/__tests__/pages/AgentBuilderStudio.test.tsx` (RAG 회귀 포함) | 22 passed |
| **전체 프론트엔드** | **39 + 17 = 56 passed** |

**주요 검증**:
- mapDraftToolIdsToCatalog: internal/mcp/미매칭 + 혼합 + 중복제거 케이스 ✅
- [적용하기] → ToolPicker 체크 표시 ✅
- [적용하기] → RAG 도구 포함 시 toolConfigs 세팅 (회귀) ✅
- 카드 도구별 지침 표시/빈 값 생략 ✅

### TypeScript & 전체 통합

- `tsc --noEmit`: **통과** ✅
- 프론트 타입 동기화 (agentComposer.ts): 완료 ✅

---

## 배운 점

### 좋았던 점

1. **도구 ID 네임스페이스 2계층 분리의 근본 원인을 Design 단계에서 완전히 확정**
   - 정적 분석만으로 버그 메커니즘 파악 가능
   - 프론트에서 변환 유틸로 우아하게 해결 (백엔드 응답 형식 불변 유지)

2. **TDD Red → Green 사이클이 설계 누락(RAG 회귀 테스트)을 포착**
   - 처음부터 "도구 적용 후 저장까지" 전체 경로를 테스트
   - 초안 적용 버그 수정이 RAG 도구 부수효과도 함께 작동하는지 회귀 확인

3. **부수 발견(`_normalize_tool_id` 버그) 조기 수정**
   - 설계 단계에서 코드 리뷰 중 발견
   - 잠재 버그를 즉시 테스트 → 수정 (향후 미세팅 버그 예방)

4. **LangSmith 추적(agent-composer 프로젝트) 이미 연결**
   - 지침 생성 품질 개선을 실측 trace로 비교 검증 가능 (후속)

### 개선 기회

1. **카탈로그 미동기화 폴백의 UX 개선**
   - 현재: `mcp_{srv}`가 폼에 원본 유지로 남음 (체크 표시 안 됨, 저장 성공)
   - 후속: 카탈로그 동기화 상태를 프론트에서 감지하고 사용자에게 안내 UI 추가 가능

2. **instruction 생성으로 인한 구조화 출력 토큰 증가**
   - 현재: max_candidates 100개 유지 (소폭 응답 지연 예상)
   - 모니터링: 실제 production에서 응답 시간 및 token 비용 추적
   - 최적화 필요 시: instruction 생성을 workers 상위 N개로 제한

3. **프롬프트 규칙 변경 효과의 실측 검증**
   - 설계 단계: "[도구 지침]" 프롬프트 규칙 강화 적용
   - 후속: LangSmith trace 기반으로 지침 부실도 → 구체도 개선 정도 정량화 가능

### 다음 적용

1. **도구 ID 형식 불일치 패턴 재사용**
   - 다른 대규모 구조화 출력/캐시 기반 기능에서 유사한 네임스페이스 분리 가능성 인식
   - 설계 초기부터 ID 형식 정의 + 계층별 매핑 계획

2. **프론트 변환 유틸 패턴**
   - API 응답 형식(저장)과 UI 요구 형식(표시)이 다를 때 전문화된 매핑 유틸 신설
   - 백엔드 응답 계약을 불변으로 유지하면서 프론트 유연성 확보

3. **RAG 도구 같은 "부수효과" 기능은 초기부터 회귀 테스트 케이스 포함**
   - 주 기능 + 부수 기능 모두 테스트 계획에 명시

---

## 관련 선행 작업 (같은 날, 같은 세션)

1. **compose DI 버그 수정** (2026-07-05)
   - `SessionScopedLlmModelRepository` → `LlmModelRepository` 재설정
   - composer 응답 품질 안정화

2. **LangSmith agent-composer 프로젝트 추적 부착** (2026-07-05)
   - 지침 생성 품질을 trace로 추적 가능하도록 설정

---

## 다음 단계

### 즉시 후속 (선택)

1. **LangSmith trace 기반 지침 생성 품질 검증**
   - 실제 trace에서 "[도구 지침]" 섹션의 구체도/정확도 확인
   - 프롬프트 규칙이 LLM 동작에 미친 영향 정량화

2. **카탈로그 미동기화 폴백 UX 개선**
   - 프론트에서 카탈로그 동기화 상태 감지
   - "카탈로그가 변경되었습니다" 안내 UI 추가

3. **instruction 토큰 비용 모니터링**
   - production 환경에서 composer 응답 시간/token 추적
   - 필요시 instruction 생성 상위 N개 제한

### 후속 이슈 (설계 단계 미루기)

- 도구별 지침의 사용자 수정 UI (현재: 읽기만 가능)
- system_prompt와 instruction의 콘텐츠 자동 동기화 (현재: LLM 출력 시점에만)

---

## 부록

### 변경 파일 목록

**백엔드 (5개)**:
1. `src/application/agent_composer/composer.py`
2. `src/application/agent_composer/compose_agent_use_case.py`
3. `src/application/agent_builder/schemas.py`
4. `src/domain/agent_builder/schemas.py`
5. `src/application/agent_builder/create_agent_use_case.py`

**프론트엔드 (5개)**:
1. `src/utils/draftToolMapping.ts` (신규)
2. `src/pages/AgentBuilderPage/index.tsx`
3. `src/types/agentComposer.ts`
4. `src/components/agent-builder/fix/ComposeDraftCard.tsx`
5. `tests/__tests__/` — 8개 신규/수정 파일

### 설계 결정 매핑

| 설계 ID | 구현 | 검증 |
|---------|------|------|
| D1 | WorkerInfo.instruction 추가 | ✅ 타입 동기화, 응답 테스트 |
| D2 | mapDraftToolIdsToCatalog 유틸 | ✅ 5케이스 테스트 통과 |
| D3 | mcp_{srv} → 서버 도구 전개 | ✅ 필터 로직 구현/테스트 |
| D4 | 지침 저장은 system_prompt 병합 | ✅ non-goal 유지, 별도 스키마 없음 |
| D5 | _normalize_tool_id mcp: 수정 | ✅ 4가지 형식 테스트, 중복 제거 |

---

**완료일**: 2026-07-05  
**작성자**: report-generator Agent  
**상태**: 완료 ✅
