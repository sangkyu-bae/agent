# Search Node Query Pipeline Planning Document

> **Summary**: Supervisor 그래프의 search 노드에 Query Rewrite → 검색 → 결과 검증(최대 3회 루프) → 압축 파이프라인을 내장하여 검색 품질과 컨텍스트 효율을 개선한다
>
> **Project**: sangplusbot (idt)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-06-10
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | search 노드가 `state["messages"][-1]`의 대화체 문장 전체("대한민국 2025년 실업률 정보를 가지고 월별 %별 그래프를 그려줄 수 있니?")를 그대로 검색 쿼리로 사용해 무관한 결과가 섞이고, 결과 검증·압축 없이 원문 전체가 LLM 컨텍스트로 유입된다 |
| **Solution** | search 노드 내부에 4단계 파이프라인 내장: ① 경량 LLM으로 검색 최적화 쿼리 재작성 → ② 도구 검색 → ③ 결과 관련성 검증, 부적합 시 쿼리 재작성 후 재검색(총 3회 한도) → ④ 임계 길이 초과 시 질문 관련 정보만 압축 |
| **Function/UX Effect** | 대화체 질문에서도 핵심 검색어("대한민국 2025년 월별 실업률 통계")로 정확한 자료가 검색되고, final_answer/analysis 노드가 노이즈 없는 압축 컨텍스트를 받아 답변·차트 품질이 향상된다 |
| **Core Value** | 검색 정확도(Precision) 향상 + 컨텍스트 토큰 절감 → 답변 신뢰도 개선과 토큰 비용 절감을 동시에 달성 |

---

## 1. Overview

### 1.1 Purpose

`WorkflowCompiler._create_search_node`(`src/application/agent_builder/workflow_compiler.py:563`)의 현재 동작에는 세 가지 문제가 있다:

1. **쿼리 미가공**: `state["messages"][-1].content`를 그대로 `tool.ainvoke({"query": ...})`에 전달한다. 사용자의 대화체 요청 전체(시각화 요구 포함)가 검색 쿼리가 되어 rag_search/web_search(Tavily) 모두 무관한 결과를 반환하는 경우가 잦다. 또한 마지막 메시지가 사용자 질문이 아니라 quality_gate 피드백이나 supervisor 산출물일 수도 있다.
2. **결과 검증 부재**: 검색 결과가 질문과 무관해도 그대로 AIMessage로 흘러간다. quality_gate는 형식 수준 검증만 수행하며, 검색 결과의 "관련성"은 판단하지 못한다.
3. **압축 부재**: 검색 결과 원문 전체가 final_answer/analysis 노드의 컨텍스트로 들어가 토큰을 낭비하고 노이즈를 키운다.

본 기능은 search 노드 내부에 **rewrite → search → validate(루프, 최대 3회 시도) → compress** 파이프라인을 내장하여 이를 해결한다.

### 1.2 Background

- **재현 시나리오**: "대한민국 2025년 실업률 정보를 가지고 월별 %별 그래프를 그려줄 수 있니?" → 현재는 이 문장 전체가 Tavily/Qdrant 쿼리가 됨 → "그래프 그리는 법" 류의 무관한 결과 혼입 → 분석/차트 품질 저하
- **기대 동작**: 위 질문에서 검색 의도만 추출해 "대한민국 2025년 월별 실업률 통계"로 검색하고, 결과가 부적합하면 쿼리를 보완해 재검색(최대 3회), 통과한 결과는 핵심 수치·날짜 중심으로 압축해 전달
- **기존 자산**: `src/application/multi_query/`의 Multi-Query Rewrite 워크플로우가 있으나 이는 Hybrid Search(내부 문서 RAG) 경로 전용으로, agent_builder의 search 노드와는 별개 경로다. 본 기능은 이를 재사용하지 않고 search 노드에 특화된 단일-쿼리 파이프라인을 구현한다 (프롬프트 패턴은 참조).

### 1.3 Related Documents

- 대상 코드: `src/application/agent_builder/workflow_compiler.py` — `_create_search_node`, `_latest_user_question`, `_is_search_result`
- 참조 코드: `src/application/agent_builder/supervisor_nodes.py` — structured output 패턴(`SupervisorDecision`)
- 참조 코드: `src/domain/agent_builder/policies.py` — Policy 배치 위치
- 참조 코드: `src/infrastructure/multi_query/prompts.py` — 쿼리 재작성 프롬프트 패턴
- 참조 문서: `docs/01-plan/features/multi-query-rewrite.plan.md` (Hybrid Search 경로, 본 기능과 별개)

---

## 2. Scope

### 2.1 In Scope

- [ ] **Query Rewrite**: 최근 사용자 질문 + 대화 맥락에서 검색 의도를 추출해 검색 최적화 쿼리 생성 (LLM structured output)
- [ ] **결과 검증 루프**: 검색 결과의 질문 관련성을 LLM으로 판정, 부적합 시 개선 쿼리로 재검색 — 검색 시도 총 3회 한도, 소진 시 마지막 결과로 진행 + warning 로그
- [ ] **결과 압축**: 검증 통과 결과가 임계 길이 초과 시에만 질문 관련 정보(수치·날짜·단위·출처 보존)로 LLM 압축, 이하면 원문 유지
- [ ] **경량 LLM 분리**: 파이프라인 전용 경량 모델(config 지정, 기본 gpt-4o-mini)을 LLMFactory로 생성, 생성 실패 시 per-run 에이전트 LLM으로 fallback
- [ ] **적용 범위**: category=="search" 전체 (rag_search, web_search) — `_create_search_node` 공통 경로 교체
- [ ] **Domain Policy**: 최대 시도 횟수(3), 압축 임계 길이를 Policy로 정의 (하드코딩 금지)
- [ ] **파이프라인 모듈 분리**: `search_pipeline.py` 신설 후 `_create_search_node`가 위임 (함수 40줄 제한 준수)
- [ ] TDD 단위 테스트 (fake LLM/tool 기반)

### 2.2 Out of Scope

- 그래프 구조(StateGraph 노드/엣지) 변경 — 파이프라인은 search 노드 함수 내부에서만 동작
- `src/application/multi_query/` 워크플로우 재사용·통합 (Hybrid Search 경로 전용 유지)
- Multi-Query 병렬 검색(1→N 쿼리 확장) — 본 기능은 단일 쿼리 재작성 + 재시도 루프
- analysis/sub_agent/action 워커 변경 (search 카테고리 한정)
- 프론트엔드 변경 (검색결과 메시지 규약 `[{worker_id} 검색결과]` 유지로 영향 없음)
- quality_gate 정책 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | Query Rewrite: 최근 user 질문(`_latest_user_question`) + 최근 대화 맥락을 입력으로 검색 최적화 쿼리 생성. 시각화/출력형식 요구("그래프 그려줘")는 제거하고 검색 의도만 추출 | High | Pending |
| FR-02 | 검색 실행은 재작성된 쿼리로 `tool.ainvoke({"query": rewritten})` 호출. rewrite LLM 실패 시 원본 질문으로 graceful fallback | High | Pending |
| FR-03 | 결과 검증: LLM structured output으로 관련성 판정(`relevant: bool`, `reason`, `improved_query`). 부적합 시 `improved_query`로 재검색 | High | Pending |
| FR-04 | 재시도 한도: 검색 시도 총 3회(최초 1 + 재시도 2). 소진 시 마지막 결과로 진행하고 warning 로그 기록 (그래프 비중단) | High | Pending |
| FR-05 | 압축: 검증 통과 결과가 임계 길이(기본 4,000자) 초과 시에만 LLM 압축. 수치·날짜·단위·출처는 보존하도록 프롬프트에 명시. 이하면 원문 그대로 | High | Pending |
| FR-06 | 경량 LLM: config(`search_pipeline_provider`/`search_pipeline_model_name`, 기본 openai/gpt-4o-mini)로 LlmModel 구성, composition root(main.py)에서 WorkflowCompiler에 주입. 미설정/생성 실패 시 per-run LLM fallback | High | Pending |
| FR-07 | 메시지 규약 유지: 결과는 `AIMessage(content="[{worker_id} 검색결과]\n...", name=worker_id)` — `_is_search_result` 식별 규약(prefix "검색결과") 절대 불변 | High | Pending |
| FR-08 | token_usage 집계: 검색 결과뿐 아니라 파이프라인 LLM 호출(rewrite/validate/compress) 추정 토큰도 `state["token_usage"]`에 반영 | Medium | Pending |
| FR-09 | 관측성: `STEP_OUTPUT_SUMMARY_KEY`로 step output_summary에 재작성 쿼리·시도 횟수·압축 여부 요약 기록 | Medium | Pending |
| FR-10 | Domain Policy: `SearchPipelinePolicy`(최대 시도 횟수, 압축 임계 길이)를 `src/domain/agent_builder/policies.py`에 정의 | Medium | Pending |
| FR-11 | 검색 도구 자체 실패(예외) 시 기존 동작 유지: `"검색 실패: {e}"` 메시지로 비중단 진행 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Performance | 정상 경로(1회 검색 + 압축 생략) 추가 지연 < 2초 — 추가 LLM 호출 2회(rewrite, validate)를 경량 모델로 처리 | 로그 타임스탬프 |
| Performance | 최악 경로(3회 검색 + 압축) 추가 LLM 호출 ≤ 5회 (rewrite 1 + validate 3 + compress 1) | 코드 리뷰 + 테스트 |
| Reliability | 파이프라인 모든 LLM 단계 실패 시에도 검색 자체는 수행되고 그래프가 중단되지 않음 (graceful degradation) | 에러 핸들링 테스트 |
| Compatibility | 기존 `_is_search_result` / final_answer / analysis 노드의 검색결과 소비 동작 회귀 없음 | 기존 테스트 통과 |
| Convention | 함수 40줄 이하, if 중첩 2단계 이하, logger 사용, config 하드코딩 금지 | 코드 리뷰 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] 재현 시나리오에서 재작성 쿼리가 검색 의도만 담는다 (예: "대한민국 2025년 월별 실업률 통계")
- [ ] 부적합 결과 → 재검색 루프가 최대 3회 시도에서 결정적으로 종료
- [ ] 임계 초과 결과만 압축되고, 압축본에 수치·날짜가 보존됨
- [ ] rewrite/validate/compress LLM 실패 시 각각 fallback 경로로 정상 진행
- [ ] 단위 테스트 작성 및 통과 (TDD: Red → Green → Refactor)
- [ ] 기존 supervisor/final_answer/analysis 관련 테스트 회귀 없음

### 4.2 Quality Criteria

- [ ] 신규 모듈 테스트 커버리지 80% 이상
- [ ] 레이어 의존성 규칙 준수 (domain은 LangChain/외부 API 미참조 — Policy는 순수 규칙만)
- [ ] `verify-architecture`, `verify-logging`, `verify-tdd` 스킬 검증 통과

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 검색당 LLM 호출 증가(정상 2회, 최악 5회)로 지연 증가 | Medium | High | 경량 모델(gpt-4o-mini) 사용, 압축은 임계 초과 시만, validate 프롬프트 최소화 |
| 경량 모델 provider 키 미설정 환경에서 생성 실패 | Medium | Medium | composition root에서 생성 실패 감지 → per-run LLM fallback + warning 로그 |
| 압축 과정에서 핵심 수치/날짜 손실 | High | Medium | 보존 규칙(수치·날짜·단위·출처)을 프롬프트에 명시, 임계 이하 원문 유지, 테스트로 검증 |
| validate LLM이 과도하게 "부적합" 판정 → 루프 낭비 | Medium | Medium | 3회 한도 + 소진 시 마지막 결과 채택(결과 없음보다 노이즈 있는 결과가 낫다는 보수적 선택), 판정 기준을 "질문과 명백히 무관할 때만 부적합"으로 프롬프트 명시 |
| `[검색결과]` prefix 규약 훼손 시 final_answer/analysis 컨텍스트 분류 깨짐 | High | Low | FR-07로 규약 고정, prefix 검증 테스트 추가 |
| rewrite가 멀티턴 맥락(이전 답변 참조 질문)을 놓침 | Medium | Medium | 최근 대화 맥락(워커 산출물 제외)을 rewrite 입력에 포함 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps with backend | ☐ |
| **Enterprise** | Strict layer separation, DI | High-traffic systems | ☑ |

### 6.2 Key Architectural Decisions (사용자 확정)

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 구현 위치 | search_node 내부 파이프라인 / 별도 그래프 노드 분리 | **search_node 내부 파이프라인** | compile() 그래프 구조·라우팅·quality_gate 불변, 변경 범위 최소. 관측성은 step output_summary로 보완 |
| 압축 시점 | 항상 / 임계 길이 초과 시만 | **임계 길이 초과 시만** | 짧은 결과에 대한 불필요한 LLM 호출·정보 손실 방지 |
| 파이프라인 LLM | per-run 에이전트 LLM 재사용 / 경량 모델 별도 지정 | **경량 모델 별도 지정** | rewrite/validate/compress는 복잡 추론 불필요 — 저비용 모델로 충분, 호출 횟수 증가분 상쇄 |
| 적용 범위 | search 카테고리 전체 / web_search만 | **search 카테고리 전체** | `_create_search_node`가 category=="search" 공통 경로이므로 일괄 적용이 자연스러움 |
| 모듈 배치 | workflow_compiler 내 inline / 별도 모듈 | 별도 모듈 `search_pipeline.py` | 함수 40줄 제한 준수, workflow_compiler 비대화 방지, 단위 테스트 용이 |

### 6.3 Pipeline Design (search_node 내부)

```
supervisor ──> [search_node] ──> quality_gate ──> supervisor
                   │
                   │  ① rewrite_query (경량 LLM, structured output)
                   │     입력: 최근 user 질문 + 대화 맥락
                   │     출력: 검색 최적화 쿼리
                   │     실패 시: 원본 질문 사용
                   │
                   │  ② tool.ainvoke({"query": q})        ◄──┐
                   │                                          │
                   │  ③ validate_result (경량 LLM)            │ improved_query로
                   │     relevant? ── No (시도 < 3) ──────────┘ 재검색
                   │        │ Yes / 시도 소진
                   │        ▼
                   │  ④ compress_result (경량 LLM)
                   │     len(result) > threshold 일 때만
                   │
                   └─ AIMessage("[{worker_id} 검색결과]\n{본문}", name=worker_id)
                      + token_usage 반영 + step summary 기록
```

**구조화 출력 스키마 (application 레이어)**:
```python
class RewrittenQuery(BaseModel):
    query: str          # 검색 최적화 쿼리
    reasoning: str      # 재작성 근거 (관측용)

class SearchResultVerdict(BaseModel):
    relevant: bool      # 질문과 관련 있는가 (명백히 무관할 때만 False)
    reason: str
    improved_query: str # 부적합 시 개선 쿼리 (relevant=True면 빈 문자열)
```

### 6.4 Layer Mapping (Thin DDD)

```
src/
├── domain/agent_builder/
│   └── policies.py                  # + SearchPipelinePolicy (max_attempts=3, compress_threshold)
│
├── application/agent_builder/
│   ├── search_pipeline.py           # 신설: create_search_pipeline_node(worker_id, tool, pipeline_llm, policy, logger)
│   │                                #   + RewrittenQuery / SearchResultVerdict 스키마
│   └── workflow_compiler.py         # _create_search_node → search_pipeline 위임,
│                                    #   __init__에 pipeline_llm_model: LlmModel | None 주입
│
├── config.py                        # + search_pipeline_provider / search_pipeline_model_name
│                                    # + search_compress_threshold
│
└── api/main.py (composition root)   # settings → 파이프라인용 LlmModel 구성 → WorkflowCompiler 주입
```

- **domain**: 시도 한도·임계 길이 등 순수 규칙만 (LangChain 미참조)
- **application**: 파이프라인 흐름 제어 + LLM 호출 오케스트레이션
- **composition root**: config → LlmModel 구성 → DI (compiler가 config를 직접 읽지 않음)

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] Thin DDD 레이어 분리 확립 (`idt/CLAUDE.md` §2)
- [x] structured output 패턴 확립 (`SupervisorDecision` 참조)
- [x] 노드 graceful degradation 패턴 확립 (search 실패 시 메시지 반환, 그래프 비중단)
- [x] pytest TDD 워크플로우 확립

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 메시지 규약 | `[{worker_id} 검색결과]` prefix가 암묵 규약 | prefix 상수화 또는 테스트로 고정 | High |
| LLM fallback | classifier 등에서 try/except 산재 | 파이프라인 단계별 fallback 패턴 일관화 | Medium |
| 토큰 추정 | `len(text) // 4` 관행 | 파이프라인 LLM 호출에도 동일 관행 적용 | Low |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `SEARCH_PIPELINE_PROVIDER` | 파이프라인 경량 LLM provider (기본 openai) | Server | ☑ 신규 |
| `SEARCH_PIPELINE_MODEL_NAME` | 파이프라인 경량 모델명 (기본 gpt-4o-mini) | Server | ☑ 신규 |
| `SEARCH_COMPRESS_THRESHOLD` | 압축 발동 임계 길이 (기본 4000자) | Server | ☑ 신규 |
| `OPENAI_API_KEY` | 경량 모델 호출 | Server | ☑ (기존) |

---

## 8. Implementation Order

### Phase 1: Domain Layer (TDD)
1. `tests/domain/agent_builder/test_search_pipeline_policy.py` — 시도 한도·임계 길이 규칙 테스트
2. `src/domain/agent_builder/policies.py` — `SearchPipelinePolicy` 추가

### Phase 2: Application Layer — 파이프라인 핵심 (TDD)
3. `tests/application/agent_builder/test_search_pipeline.py` — fake LLM/tool 기반:
   - rewrite 정상/실패 fallback
   - validate 부적합 → 재검색 → 3회 소진 시 마지막 결과 채택
   - 임계 초과 시만 압축 / 수치 보존
   - `[{worker_id} 검색결과]` prefix·token_usage·step summary 검증
4. `src/application/agent_builder/search_pipeline.py` — `create_search_pipeline_node` + 스키마 구현

### Phase 3: Integration
5. `src/application/agent_builder/workflow_compiler.py` — `_create_search_node`를 파이프라인 위임으로 교체, `pipeline_llm_model` 생성자 파라미터 추가 (None이면 per-run LLM 사용 = 하위호환)
6. `src/config.py` — 신규 설정 3종 추가
7. `src/api/main.py` — composition root에서 파이프라인 LlmModel 구성·주입
8. `.env.example` — 신규 환경변수 문서화

### Phase 4: Regression & Verify
9. 기존 agent_builder 테스트 회귀 확인 (Windows 이벤트 루프 이슈로 모듈 격리 실행)
10. `/verify-architecture`, `/verify-logging`, `/verify-tdd` 검증

---

## 9. Next Steps

1. [ ] Design 문서 작성 (`/pdca design search-node-query-pipeline`) — 프롬프트 문안, 스키마 상세, fallback 분기 확정
2. [ ] Plan 리뷰 및 확정
3. [ ] TDD 사이클로 구현 시작

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-06-10 | Initial draft — 구현 위치/압축 시점/LLM 분리/적용 범위 사용자 확정 반영 | 배상규 |
