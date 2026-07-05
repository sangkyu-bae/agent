# Report: nl-agent-composer

> Created: 2026-07-04
> Phase: Report (완료 보고서)
> Plan: `docs/01-plan/features/nl-agent-composer.plan.md`
> Design: `docs/02-design/features/nl-agent-composer.design.md`
> Analysis: `docs/03-analysis/nl-agent-composer.analysis.md`

---

## Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| Feature | nl-agent-composer — 자연어 → 내부+MCP 도구 조합 에이전트 초안(무저장) API |
| 기간 | 2026-07-04 (Plan → Design → Do → Check → Report, 단일 세션) |
| 범위 | `idt/` 백엔드 전용 (프론트 프리필 UI는 후속 feature) |
| PDCA 사이클 | Plan ✅ → Design ✅ → Do ✅ → Check ✅ (95%) → Report ✅ |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| Match Rate (Design 대비) | **≈ 95%** (검증 항목 41개, Gap 5건 중 2건 즉시 수정·3건 수용) |
| Iteration | 0회 (90% 이상으로 iterate 불필요) |
| 신규 파일 | 12개 (src 6 + tests 6), 1,443줄 |
| 기존 확장 | 4개 파일 (agent_builder schemas/use case, main.py, config.py) + .env.example |
| 신규 테스트 | 38건 전부 통과 |
| 회귀 테스트 | agent_builder 390 passed, domain 1,923 passed (기존 실패 0건 추가) |
| 검증 스킬 | verify-architecture / verify-logging / verify-tdd 위반 0건 (신규 파일 기준) |

### 1.3 Value Delivered

| 관점 | 전달된 가치 (실측 기준) |
|------|------------------------|
| **Problem** | 자연어 에이전트 생성이 내부 도구 6개에 갇혀 있었고(MCP 미포함), LLM 결과가 확인 없이 즉시 DB 저장되었으며, "이 요청이 우리 도구로 가능한가" 판정이 없었다. 심지어 명시적 tool_ids 저장 경로는 `mcp_*` id를 거부하는 잠재 버그(`get_tool_meta` ValueError)가 있었다. |
| **Solution** | `POST /api/v1/agents/compose` 1회 호출로 내부+MCP(DB 카탈로그, 미동기화 시 서버 단위 폴백) 후보를 LLM에 전달해 초안을 조합하고, 환각 tool_id drop·도구 수/프롬프트 clamp·coverage(full/partial/none) 재산정을 **서버가 최종 결정**. DB 쓰기 0건. 저장은 기존 `POST /agents`가 `system_prompt` 프리필과 `mcp_*` tool_id를 수용하도록 최소 확장(FR-08/09)해 원자적 1회로 처리. |
| **Function/UX Effect** | 사용자는 "OOO 하는 에이전트 필요해" 한 문장으로 MCP 포함 구성을 즉시 미리보고, 커버 불가 역량은 `missing_capabilities`(사유+대안)로 안내받는다. 화면 수정 후 저장 시점에만 에이전트가 생성된다. 38건 단위 테스트로 혼합 조합·병합·폴백·환각 방어·무저장이 검증됨. |
| **Core Value** | "LLM은 제안, 서버가 판정, 사람이 확정" 3단 안전 구조를 기존 생성/실행 경로 무회귀(390+1,923 테스트 유지)로 확보. workflow_compiler 등 실행 공통단 무수정. |

---

## 2. PDCA 여정 요약

| 단계 | 산출물 | 핵심 결정 |
|------|--------|----------|
| Plan | plan.md (FR-01~10, 리스크 R1~R5) | 단발 draft API / 완전 신규 모듈 / 부분 초안+부족 역량 안내 / 백엔드 먼저 (사용자 확정 4건) |
| Design | design.md (D1~D7, 파일·테스트 설계) | D1 `CreateAgentRequest.system_prompt` 추가, D2 서버 단위 폴백, D3 LLM 1회 통합, D7 clamp+notes·coverage 서버 재산정 (사용자 확정 2건 + 자체 결정 5건) |
| Do | src 6 + tests 6 신규, 기존 4 확장 | TDD Red(4 collection error) → Green(38 passed). 검증 스킬 3종 통과 |
| Check | analysis.md (Match Rate 95%) | Gap 5건: Med 1(40줄 규칙)·Low 1(병합 sort_order) 즉시 수정, Low 3 수용 |

## 3. 구현 상세 (최종)

### 3-1. 신규 API

`POST /api/v1/agents/compose` (인증 필수, 200)

- 요청: `{user_request(≤1000), name?, llm_model_id?}`
- 응답: `coverage(full/partial/none)`, `name_suggestion`, `system_prompt`, `tool_ids`(mcp_* 포함, 저장 호환), `workers`, `flow_hint`, `llm_model_id`, `temperature`, `missing_capabilities[]`, `notes`
- 오류: ValueError→422, 인증 실패→401(전역)

### 3-2. 파이프라인

```
후보 수집(TOOL_REGISTRY + tool_catalog[mcp] | 폴백: mcp_registry 서버 메타)
 → AgentComposer LLM 1회 (structured output: 역량분해+도구선택+프롬프트+이름+notes)
 → 서버 보정: 환각 drop → mcp:{srv}:{tool}→mcp_{srv} 매핑·병합(min sort_order)
   → MAX_TOOLS(5) clamp → 프롬프트 4000자 clamp → coverage 재산정
 → 초안 응답 (DB 쓰기 0건)
```

### 3-3. 저장 연결 (기존 API 확장)

- `CreateAgentRequest.system_prompt`(≤4000, optional): 값 있으면 PromptGenerator 스킵
- `_build_skeleton_from_tool_ids` async 전환 + `mcp_` 분기: MCP 레지스트리에서 메타 해석, 미등록/비활성 ValueError(422)
- 내부 도구 경로 무변경, `mcp_server_repo` 미주입 시 기존 동작 100% 유지

## 4. 수용된 잔여 Gap / 후속 과제

| 항목 | 상태 |
|------|------|
| E2E 수동 확인 (compose → POST /agents → run, 실 LLM/DB) | 미실행 — 배포 전 1회 필요 |
| 프론트 프리필 UI + `/api-cotract` 타입 동기화 (`CreateAgentRequest.system_prompt` 추가분) | 후속 feature |
| MCP 서버 단위 워커의 개별 도구 필터링 (R1) | 후속 (런타임 변경 필요) |
| 라우터 401 단위 테스트 (Gap 3) | E2E로 이관 |
| 명확화 질문 하이브리드 (Plan 비목표 N2) | 필요 시 후속 |

## 5. 교훈 (Lessons Learned)

1. **기존 자산 조사 선행이 스코프를 줄였다**: interview 플로우·tool_catalog의 존재 확인으로 "초안 미리보기"와 "MCP 메타 소스"를 재발명하지 않고 갭 3개(MCP 후보/커버리지/무저장 단발)로 압축.
2. **저장 경로의 mcp_* 거부는 계획 단계 코드 리딩에서 발견**: 초안 API만 만들었으면 "초안은 나오는데 저장이 안 되는" 반쪽 기능이 됐을 것. Plan 단계의 `file:line` 수준 현황 분석이 유효했다.
3. **LLM 출력 보정을 도메인 정책으로 분리**(ComposePolicy)하니 환각/clamp/coverage 규칙이 순수 함수로 테스트 가능해졌고, gap-detector 검증도 용이했다.
4. **40줄 규칙은 조립 메서드에서 깨지기 쉽다**: `_assemble_draft`가 76줄로 성장 — 헬퍼 추출로 해결. 조립 로직은 처음부터 단계별 헬퍼로 설계하는 편이 낫다.
