# agent-create-pipeline Completion Report

> **Status**: Complete
>
> **Project**: sangplusbot (idt — 백엔드)
> **Author**: 배상규
> **Completion Date**: 2026-08-19
> **PDCA Cycle**: Plan(08-18) → Design(08-18) → Do ×2세션(08-19) → Check → Act-1 → Report(08-19)

---

## Executive Summary

### 1.1 Project Overview

| Item | Content |
|------|---------|
| Feature | agent-create-pipeline — 의도 분석·도구 추천·프롬프트 생성·에이전트 생성을 엮는 단일 엔드포인트 |
| Start Date | 2026-08-18 |
| End Date | 2026-08-19 |
| Duration | 2일 (Plan/Design 1일 + Do/Check/Act 1일) |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 97% (최초 92% → Act-1)          │
├─────────────────────────────────────────────┤
│  ✅ FR 완료:      15 / 15                    │
│  ✅ 기능 테스트:  101 / 101 통과             │
│  ✅ 회귀:         0건 (baseline 58건 외 없음)│
│  ⏳ 명시 이월:    1건 (E2E GET 재확인 #15)   │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 최근 세 사이클의 재료 모듈(intent·tool_selection·prompt_composer)이 배선 없이 각자 떠 있었고, 에이전트 자동 생성은 API 4~5개를 순서대로 알아야 가능했다 → **해소**: 한 엔드포인트가 전 과정을 오케스트레이션 |
| **Solution** | `POST /api/v1/agents/pipeline`(동기) + `/stream`(SSE) — 되묻기 stateless 왕복 후 `agent_definition` 실생성 + 프롬프트 세션 자동 바인딩. 기존 자동 생성 경로 2종 물리적 무변경 (회귀 0 실측) |
| **Function/UX Effect** | 화면 구현 없이도(스코프 제외) 프론트 계약 완비 — steps 5개 고정, 단계별 ok/degraded/failed/skipped + reason, SSE 실시간 이벤트 + 15초 heartbeat. 동기/SSE 최종 payload 바이트 동일(FR-15)을 테스트로 증명 |
| **Core Value** | "재료 모듈의 첫 완주 배선" — 각 모듈의 degraded 계약을 그대로 유지한 채 조합 UseCase 하나로 end-to-end 가치 증명. 단계 전이 규칙은 순수 domain Policy로 남아 후속 R1 수렴 자산 |

---

## 1.4 Success Criteria Final Status

| # | Criteria (Plan §4.1) | Status | Evidence |
|---|---------|:------:|----------|
| SC-1 | 되묻기 왕복 완주 (need_input → answers 재호출 → 생성) | ✅ Met | `test_clarification_round_trip_completes_creation` (Act-1 보강) |
| SC-2 | 미충족 없는 요청 1차 호출로 agent_id | ✅ Met | `test_happy_path_emits_five_stages_then_created_outcome` 외 |
| SC-3 | 생성된 agent_id 조회·프롬프트/도구 일치 | ⏳ 이월 | 실 DB 필요 — E2E 체크리스트로 명시 이월 (Analysis §8.2) |
| SC-4 | prompt_session에 agent_id 바인딩 | ✅ Met | bind_calls 단언 + 실패 시 `bind_ok=false` 계약 |
| SC-5 | LLM 3단계 실패 각 200+degraded / 저장 실패 5xx | ✅ Met | 시나리오 #4~#8 테스트 전부 통과 |
| SC-6 | steps 5개 고정·SSE 순서·failed 식별·동기=SSE payload | ✅ Met | 시나리오 #12/#13 + FR-15 동일성 테스트 |
| SC-7 | 기존 5경로 회귀 0 (FAILED 목록 diff) | ✅ Met | 전체 스위트 7,404건 — baseline 58건 외 신규 실패 0 |

**Success Rate**: 6/7 Met + 1 명시 이월 (86% + 이월 계획 확정)

## 1.5 Decision Record Summary

| Source | Decision | Followed? | Outcome |
|--------|----------|:---------:|---------|
| [Plan D1] | 신규 병렬 엔드포인트 (기존 경로 무변경) | ✅ | 회귀 0 실측. 규칙 3벌 공존(R1)은 후속 수렴 방향 명문화로 관리 |
| [Plan D2] | LLMToolSelector 재사용 | ✅ | `ToolSelectorPort` 계약(required 보존)이 FR-03을 공짜로 해결. 탈부착 계약 테스트에 선언 소비자로 등록 |
| [Plan D3] | 되묻기 stateless 왕복 | ✅ | 세션 테이블 0. 왕복 완주 테스트로 증명 |
| [Plan D4] | 실제 생성까지 + 세션 바인딩 | ✅ | `CreateAgentUseCase` 재사용, bind 실패는 생성을 뒤집지 않음 |
| [Plan D8] | 단계 상태 1급 계약 + SSE | ✅ | steps 5개 고정 + SSE 4이벤트 + heartbeat(Act-1) |
| [Design Option C] | domain 규칙 분리 + UseCase 직접 주입 | ✅ | Policy 8함수 순수 테스트 25건 — LLM 목 없이 규칙 검증 |
| [Design D6→G-02] | SlotLimits config 오버라이드 | ⚠️ 수정 | Act-1에서 **단일 출처(IntentConfig)로 변경** — 이원화가 dead config를 만들었음 (교훈 §6.2) |
| [Design §4.5] | 무인증 401 | ✅ | gap-detector의 403 주장을 실측으로 반증 — 문서가 옳았고 테스트로 고정 |

---

## 2. Related Documents

| Phase | Document | Status |
|-------|----------|--------|
| Plan | [agent-create-pipeline.plan.md](../01-plan/features/agent-create-pipeline.plan.md) v0.2 | ✅ |
| Design | [agent-create-pipeline.design.md](../02-design/features/agent-create-pipeline.design.md) v0.2 | ✅ |
| Check | [agent-create-pipeline.analysis.md](../03-analysis/agent-create-pipeline.analysis.md) v0.2 | ✅ |
| Act | 본 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements — 15/15

| ID | Requirement | Status |
|----|-------------|:------:|
| FR-01 | 단일 엔드포인트 (user_request+history+answers/round+tool_ids+name) | ✅ |
| FR-02 | 서버 소유 스펙 의도 판정 + need_input 분기 + 재clamp | ✅ |
| FR-03 | 전체 카탈로그 후보 추천, 사용자 tool_ids 항상 포함, 미지 ID 에코백 | ✅ (에코백은 Act-1 복원) |
| FR-04 | ComposePromptUseCase 재사용 + 버전 저장 | ✅ |
| FR-05 | CreateAgentUseCase로 실생성 + agent_id 반환 | ✅ |
| FR-06 | 세션 바인딩 (실패해도 생성 유지, bind_ok 명시) | ✅ |
| FR-07 | 단계별 degraded 정책 (intent/tools/prompt) | ✅ |
| FR-08 | 저장 실패 5xx 전파 | ✅ |
| FR-09 | 전 요청 인증 (401 고정) | ✅ |
| FR-10 | 입력 검증 상속 + history 20턴 상한 | ✅ |
| FR-11 | 기존 5경로 무변경 | ✅ |
| FR-12 | request_id 전파 + 구조화 로깅 (PII 미기록) | ✅ |
| FR-13 | steps[] 5개 고정 + degraded_stages | ✅ |
| FR-14 | SSE 4이벤트 + seq 단조 + heartbeat | ✅ |
| FR-15 | 동기/SSE 결과 의미 동일 (구조 강제 + 테스트) | ✅ |

### 3.2 Non-Functional Requirements

| Item | Target | Achieved | Status |
|------|--------|----------|:------:|
| 아키텍처 | Thin DDD 레이어 준수 | domain→domain만, try/except는 bind 1곳 | ✅ |
| 관측 | 단계별 reason/elapsed 로그+응답 | StageRecord + 구조화 로그 | ✅ |
| 지연 관리 | 단계별 타임아웃 + 끊김 방지 | 셀렉터 5s·intent 10s·prompt 20s + heartbeat 15s | ✅ |
| 테스트 | TDD 4계층 | Red→Green 사이클 준수, 101케이스 | ✅ |

### 3.3 Deliverables

| Deliverable | Location | 규모 |
|-------------|----------|------|
| domain (규칙) | `src/domain/agent_create_pipeline/` — stages·policies·spec·interfaces | 4파일 |
| application (조합) | `src/application/agent_create_pipeline/` — events·use_case (async generator) | 2파일 |
| infrastructure | `adapters.py`(후보 로더+Null 셀렉터)·`agent_create_pipeline_config.py` | 2파일 |
| API | `agent_pipeline_router.py`(POST+SSE)·`agent_pipeline.py`(스키마) | 2파일 |
| DI | `main.py` — 탈착형 조립(킬스위치 기본 off)·와일드카드 앞 등록·단일 세션 공유 | 수정 1 |
| Tests | 4계층 6본 + 경계 계약 갱신 | 101케이스 |

---

## 4. Incomplete Items

### 4.1 Carried Over (명시 이월 — explicit-gap-carryover 관례)

| Item | Reason | Priority |
|------|--------|----------|
| #15 생성 후 `GET /api/v1/agents/{id}` 일치 확인 | 실 DB·서버 기동 필요 | High — 실서버 E2E 시 최우선 |
| 프론트 배선 (진행 표시 UI·되묻기 폼) | 사용자 확정 스코프 제외 | High — 다음 사이클 |
| R1 수렴 (AgentComposer/v3 auto 경로를 파이프라인 모듈로 교체 검토) | 신규 경로 실사용 검증 선행 | Medium |
| 멱등 키(R7 중복 생성 방어 강화) | 실사용 데이터 확인 후 판단 | Low |

### 4.2 Cancelled — 없음

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| Metric | Target | Final | Change |
|--------|--------|-------|--------|
| Design Match Rate | 90% | **97%** | 92→97 (Act-1) |
| 기능 테스트 | 전 통과 | 101/101 | 58→101 (Act-1 보강) |
| 전체 스위트 회귀 | 0건 | 0건 (baseline 58 외) | ✅ |
| Critical/Important gap | 0 | 0 (Important 4건 전부 해소) | ✅ |

### 5.2 Resolved Issues (Act-1)

| Issue | Resolution |
|-------|------------|
| G-01 SSE heartbeat 부재 (R7 직결) | 15초 주기 heartbeat — `wait_for` 대신 task 유지+`asyncio.wait` (제너레이터 중단 방지) |
| G-02/03 되묻기 상한 config 이원화·무효 | `IntentConfig.slot_limits()` 단일 출처화, dead config 3종 삭제 |
| G-04 미지 tool_id 에코백 유실 (Plan→Design 단계 요구 유실) | `unknown_tool_ids` 응답 복원 |
| G-05/08/10 | started payload 축소·history 상한·skip_reason 정정 |
| G-06 (반증) | gap-detector의 "403" 주장을 실측 401로 반증 — 느슨한 단언을 `== 401`로 고정 |

---

## 6. Lessons Learned

### 6.1 What Went Well (Keep)

- **포트 계약 재사용의 배당**: `ToolSelectorPort`의 "required_ids 항상 포함" 계약이 FR-03(사용자 지정 도구 보존)을 설계 없이 해결 — 선행 사이클의 계약 투자 회수
- **규칙의 domain 분리(Option C)**: Policy 8함수가 LLM 목 없이 25케이스로 검증됨. 실패 매트릭스 7행이 전부 실코드·실테스트로 존재
- **FR-15를 구조로 강제**: 동기/SSE가 같은 제너레이터를 공유하게 한 설계 덕에 "두 응답 동일" 계약이 코드 구조 + 테스트 이중으로 성립
- **탈부착 계약 테스트가 실제로 작동**: 신규 소비자 등장을 AST 테스트가 즉시 적발 → 의식적 선언 갱신이라는 의도된 프로세스로 처리됨

### 6.2 What Needs Improvement (Problem)

- **Plan 요구가 Design에서 유실** (G-04): FR-03의 에코백이 Design §4.3 응답 필드에 빠졌고 구현은 Design에 충실해 함께 누락 — Design 작성 시 FR 역추적 체크 필요
- **config 이원화가 dead config를 낳음** (G-02/03): "오버라이드 가능하게"라는 선의의 설계가 실제 소비 지점과 어긋남 — 운영값은 소비 지점 기준으로 단일 출처 확인 필수
- **기존 패턴의 맹목 복사 위험**: run/stream의 `wait_for` heartbeat 패턴은 큐 기반 스트림 전제 — 직접 LLM을 await하는 제너레이터에 복사했으면 파이프라인이 중단됐다. 패턴 재사용 시 전제 확인
- **도구 판정도 검증 대상**: gap-detector의 G-06(403 주장)은 실측으로 반증됨 — 에이전트 분석 결과를 테스트로 확인하는 절차가 유효했다

### 6.3 What to Try Next (Try)

- Design 작성 시 "Plan FR → Design 절 매핑 표"를 두어 요구 유실을 구조적으로 방지
- 신규 config 추가 시 "소비 지점 파일:라인"을 config docstring에 명기

---

## 7. Process Improvement Suggestions

| Phase | 개선 제안 |
|-------|----------|
| Design | FR 역추적 매핑 표 추가 (G-04 재발 방지) |
| Check | gap-detector 판정 중 "기본 동작" 류 주장은 실측 테스트로 즉시 검증 (G-06 사례) |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] `AGENT_PIPELINE_ENABLED=1` + `TOOL_SELECTOR_PROVIDER/MODEL` 설정 후 실서버 스모크 (E2E 체크리스트: 파이프라인 생성 → GET 일치 확인 = 이월 #15)
- [ ] 커밋/PR (사용자 지시 시)

### 8.2 Next PDCA Cycle 후보

| Item | Priority |
|------|----------|
| 프론트 배선 — 단계 진행 바 + 되묻기 폼 (Design §5 화면 계약 기반) | High |
| R1 수렴 — 기존 자동 생성 경로 내부를 파이프라인 모듈로 교체 검토 | Medium |

---

## 9. Changelog

### v1.0.0 (2026-08-19)

**Added:**
- `POST /api/v1/agents/pipeline` — 의도 판정(되묻기 포함) → 도구 추천 → 프롬프트 생성·버전 저장 → 에이전트 생성 → 세션 바인딩 단일 호출
- `POST /api/v1/agents/pipeline/stream` — 단계 이벤트 SSE (stage_started/completed/failed + pipeline_result + heartbeat)
- 단계 상태 모델(`StageRecord`)·`PipelinePolicy` 8규칙·서버 소유 intent 스펙(슬롯 4축)
- `CatalogCandidateReader`·`NullToolSelector`·킬스위치 config (기본 off)

**Changed:**
- `main.py` DI 조립 블록 추가 (기존 경로 무변경)
- tool_selection 탈부착 계약 테스트 — 파이프라인 4파일을 선언 소비자로 등록

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-19 | 완료 보고서 | 배상규 |
