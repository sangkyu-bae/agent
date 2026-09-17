# wiki-guided-routing Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation) + Runtime Verification
>
> **Project**: sangplusbot / idt (백엔드)
> **Version**: HEAD a07ef09 + 작업 트리
> **Analyst**: 배상규 (Claude 보조)
> **Date**: 2026-09-12
> **Design Doc**: [wiki-guided-routing.design.md](./wiki-guided-routing.design.md)
> **Plan Doc**: [wiki-guided-routing.plan.md](./wiki-guided-routing.plan.md)

> 참고: gap-detector 에이전트 산출물이 2회 연속 유실(transcript 0바이트)되어, 동일 기준(구조·기능·계약·런타임)으로 메인 세션이 직접 분석했다. 근거는 전부 file:line·테스트·DB 트레이스로 남긴다.

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 위키 목차가 제목 한 줄뿐이고 "지침도 위키에 있다"는 프레이밍이 없어, 수퍼바이저 LLM이 위키를 건너뛰고 외부 수집 도구를 추측 호출한다 (실제 런 `8ccc097f` 재현). |
| **WHO** | P2 에이전트 소유자(위키로 경로·절차를 등록하는 사람)와 그 에이전트를 쓰는 최종 사용자. |
| **RISK** | 프롬프트 규칙이 "위키 항상 먼저"로 과잉 적용되면 매 턴 wiki_read 왕복이 생겨 토큰·지연이 는다. "관련 항목이 있을 때만"으로 한정한다. |
| **SUCCESS** | 동일 에이전트·동일 질문 재실행 시 `ai_run_step`에 `wiki_read_worker` → 수집 워커(fsb.or.kr) 순서가 기록되고 최종 답변에 fsb.or.kr 출처 데이터가 포함된다. 기존 테스트 FAILED 목록 diff 0. |
| **SCOPE** | 발췌·프레이밍·결정 규칙·실패 폴백(프롬프트 계층) + Tool Guidelines 섹션 재생성. 표 추출 정확도·강제 라우팅·스키마 변경 제외. |

---

## Strategic Alignment Check

### Plan 정렬 (PRD 없음)

| Element | Expected | Status |
|---------|----------|:------:|
| Core Problem (WHY) | 위키 지침을 수퍼바이저가 실제로 참조 | ✅ Addressed — 실런 `538164a4` iter=0 reasoning: "위키 목차에 전용 지침이 명시되어 있으므로 우선 해당 문서를 열람" |
| Target User (WHO) | P2 소유자가 위키만으로 경로 통제 | ✅ Addressed — 코드 수정 없이 위키 본문의 URL이 수집 워커 인자로 전달됨 |
| 일반화 원칙 | 금리 특화 하드코딩 금지 | ✅ 문구·규칙 전부 도메인 중립 ("지침·출처 URL·절차") |

### Success Criteria Status (Plan §4.1)

| # | Criteria | Status | Evidence |
|---|----------|:------:|----------|
| SC-1 | FR-01~FR-07 구현 + 대응 테스트 | ✅ | §2.3 표, 신규 테스트 2파일·확장 10파일 |
| SC-2 | 재현 시 `wiki_read_worker` → 수집 워커(fsb.or.kr) 순서 | ✅ | `ai_run_step` run `538164a4`: supervisor → wiki_read_worker → supervisor → scrape_url_worker; `ai_tool_call.arguments_json.url = https://www.fsb.or.kr/ratedepo_0100.act` |
| SC-3 | 위키 없는 에이전트 + 접속 불가 URL → URL 미추측·되묻기 | ✅ (Act-1) | 실런 `f7f41fe1`(에이전트 `51333f75`, 위키 0건): scrape 워커 DNS 실패 → supervisor reasoning "다른 URL을 추측해서 호출해서도 안 된다는 시스템 지침이 있습니다 … FINISH" → 최종 답변이 실제 URL을 되물음, 추측 URL 0건. 단위 테스트 `test_supervisor_worker_error.py` 11건 |
| SC-4 | 도구 편집 후 Tool Guidelines 정합 + 타 섹션 보존 | ✅ | `test_update_agent_tool_editing.py::test_d5_*` 6건 통과 |
| SC-5 | 기존 테스트 FAILED diff 0 | ✅ | 전체 스위트 baseline 62 failed → after 58 failed, 신규 실패 0건, 잔존 58건 = 기존 기준선 |
| SC-6 | 신규 config docstring에 소비 지점 명기 | ✅ | `src/config.py` `wiki_toc_excerpt_chars` 주석 |

**Success Rate**: 6/6 (Act-1 후)

### Decision Record Verification

| Source | Decision | Followed? | Deviation |
|--------|----------|:---------:|-----------|
| [Plan] | 기존 "목차 → LLM 판단 → wiki_read" 유지, 본문 통째 주입·강제 라우팅 기각 | ✅ | 없음 — 강제 훅 미추가, 목차는 발췌만 추가 |
| [Plan] | 실패 폴백은 FINISH+answer 되묻기(인터럽트 없음) | ✅ | `_render_worker_error_block` 문안이 FINISH·answer 경로 지시 |
| [Design] | Option C: state 필드 1개 + 도메인 순수 함수 + 기존 렌더 패턴, 신규 소스 파일 0 | ✅ | 신규 소스 파일 0, `SupervisorState.last_worker_error` 1개 |
| [Design D1] | `excerpt_chars=0`이면 기존 SELECT, provider가 kwarg 전달 | ⚠️ | provider는 값이 0보다 클 때만 kwarg를 넘긴다(구 시그니처 페이크 무회귀). 의도된 강화 — Design 문구 갱신 필요 |
| [Design D5] | ToolGuide name은 카탈로그 name | ⚠️ | 내부 도구는 `TOOL_REGISTRY` name, MCP는 tool_id 마지막 조각(= 카탈로그 name과 동일 값). 카탈로그 재조회 없이 동등 결과 |

---

## 1. Analysis Overview

- **Design Document**: `docs/02-design/features/wiki-guided-routing.design.md`
- **Implementation Path**: `src/{domain,application,infrastructure}` 15개 파일 (Design §12.1)
- **Analysis Date**: 2026-09-12

---

## 2. Gap Analysis (Design vs Implementation)

### 2.1 API Endpoints

| Design | Implementation | Status |
|--------|---------------|--------|
| 변경 없음 (`GET /api/v1/wiki/tree` 응답 불변) | 인프로세스 L1: 200, item keys `id,source_type,status,title,updated_at`, `excerpt` 미노출, 비인증 401 | ✅ Match |

### 2.2 Data Model

| Field | Design | Impl | Status |
|-------|--------|------|--------|
| `WikiTreeItem.excerpt: str \| None = None` | additive | `src/application/wiki/schemas.py` | ✅ |
| `SupervisorState.last_worker_error: str` | additive + initial "" | `supervisor_state.py`, `build_initial_state` | ✅ |
| DB 스키마 | 변경 없음 | 마이그레이션 0, `SUBSTRING` 조회만 | ✅ |

### 2.3 Component Structure (D1~D5)

| Design Component | Implementation | Status |
|------------------|----------------|--------|
| D1 `list_searchable_tree_items(excerpt_chars)` SUBSTRING | `src/infrastructure/wiki/wiki_repository.py` `func.substring(...).label("excerpt")`, `getattr(r,"excerpt",None)` | ✅ |
| D1 port 기본 인자 | `src/application/repositories/wiki_repository.py` | ✅ |
| D1 provider 전달 + main 배선 + config | `toc_provider.py` (`extra` kwarg), `main.py` `excerpt_chars=settings.wiki_toc_excerpt_chars`, `config.py` 120 | ✅ (kwarg 조건부 — 위 D1 편차) |
| D1 `_toc_line` 발췌 꼬리·`_normalize_excerpt` | `prompt_rendering.py` | ✅ 바이트 동일 테스트 통과 |
| D2 `_TOC_GUIDANCE_LINE` 헤더·폴더 헤더(태그 불변) | `prompt_rendering.py` | ✅ |
| D2 `wiki_read`/`wiki_list` 설명 | `tool_registry.py` | ✅ |
| D2 `_WIKI_INSTRUCTION_VERBATIM` 두 지시문 | `workflow_compiler.py` | ✅ |
| D3 `_render_wiki_guidance_block` 조건 3종 | `workflow_compiler.py` | ✅ 테스트 4건 |
| D3 `create_supervisor_node(wiki_guidance_block, wiki_worker_id)` + 조립 순서 | `supervisor_nodes.py`, 호출부 `workflow_compiler.py` | ✅ |
| D4 `ToolErrorPolicy` (domain, duck typing) | `src/domain/agent_builder/policies.py` | ✅ 9건 |
| D4 `_wrap_worker` / collect 노드 세팅 | `workflow_compiler.py`, `collect_pipeline.py` (`_BodyOutcome.failed`, `_worker_error_of`) | ✅ |
| D4 `_render_worker_error_block` + 이번 턴·재주입 제외 + 리셋 | `supervisor_nodes.py` (3개 반환 경로 모두 `""`) | ✅ 11건 |
| D5 `replace_tool_section` 헤딩 탐색·첫 헤딩만·빈 guides 제거 | `src/domain/prompt_composer/policies.py` | ✅ 6건 |
| D5 UseCase 호출(요청 프롬프트 우선) | `update_agent_use_case.py` `_rebuild_tool_workers` 말미 | ✅ 6건 |

**Structural Match Rate**: 15/15 = **100%**

### 2.4 Functional Depth Analysis

| File | Depth | Notes |
|------|:-----:|-------|
| wiki_repository.py / toc_provider.py / prompt_rendering.py | 100 | 실 SQL·실 렌더, 플레이스홀더 없음 |
| supervisor_nodes.py / workflow_compiler.py | 100 | 실런에서 블록 주입·라우팅 변화 확인 |
| collect_pipeline.py | 100 | 실패·차단·정상 3분기 테스트 |
| policies.py ×2 / update_agent_use_case.py | 100 | 결정적 순수 함수, 사용자 편집 보존 테스트 |
| Design §9.3 런타임 시나리오 #3(위키 없는 에이전트 되묻기), #4(위키 미등록 프롬프트 불변) | 100 | (Act-1) #3 실런 통과, #4 구조·단위 테스트로 증명 |

**Shallow File Count**: 0 / 15. **Functional Match Rate**: **98%** (G-04 soft 404 미감지는 의도된 범위이나 한계로 소폭 감점)

### 2.5 Page UI Checklist

해당 없음 (백엔드 전용).

### 2.6 API Contract Verification

| # | Endpoint | Design | Server | Client | Contract |
|---|----------|:------:|:------:|:------:|:--------:|
| 1 | `GET /api/v1/wiki/tree` | 불변 | 불변 (명시 매핑) | 프론트 무변경 | PASS |
| 2 | `POST /api/v1/agents/{id}/run` | 불변 | 불변 | 불변 | PASS |
| 3 | `PUT /api/v1/agents/{id}` (도구 편집) | 응답 `system_prompt`에 재생성 섹션 | `UpdateAgentResponse.system_prompt` | 프론트가 그대로 표시 | PASS |

**Contract Match Rate**: 3/3 = **100%**

### 2.7 Runtime Verification Results

#### L1: API / 실행 트레이스

| # | Test | Expected | Actual | Pass |
|---|------|----------|--------|:----:|
| 1 | 전체 pytest FAILED 목록 diff | 신규 실패 0 | 62 → 58 failed, 신규 0, 9042 passed | ✅ |
| 2 | 재현 실행(인프로세스 TestClient, 실 DB·LLM·MCP) 라우팅 순서 | wiki_read → 수집 | supervisor → wiki_read_worker → supervisor → scrape_url_worker → final_answer | ✅ |
| 3 | 수집 URL | 위키 지침 URL 그대로 | `https://www.fsb.or.kr/ratedepo_0100.act` | ✅ |
| 4 | 프롬프트에 신규 블록 포함(간접) | 첫 supervisor 호출 토큰 증가 | 4109(변경 전) → 4195(변경 후) | ✅ |
| 5 | 트리 API 계약 | 200, excerpt 미노출, 비인증 401 | 동일 | ✅ |
| 6 | 위키 없는 에이전트 + 접속 불가 URL 되묻기 (§9.3 #3) | 되묻기, 추측 URL 0 | (Act-1) run `f7f41fe1`: scrape 1회 DNS 실패 → FINISH+되묻기, 추가 워커 호출 0, 추측 URL 0 | ✅ |
| 7 | 위키 미등록 에이전트 결정 프롬프트 불변 (§9.3 #4) | 바이트 동일 | 구조 증명: 목차 빈 문자열 → `wiki_guidance_block=""`·`wiki_worker_id=""`(G-06 게이트), `last_worker_error=""` → 블록 3종 모두 빈 문자열. 단위 테스트 `test_no_blocks_when_no_error_and_no_guidance`, `test_wiki_worker_without_toc_passes_empty_worker_id`. 동일 질문 변경 전 런이 없어 토큰 실측은 생략 | ✅ (구조) |

**L1 Score**: 7/7. L2/L3: 해당 없음(백엔드 전용).

**Runtime Match Rate**: **97%** (#7 토큰 실측 미수행 소폭 감점)

### 2.8 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  100%                │
│  Functional Match Rate:   98%  (Act-1 후)     │
│  Contract Match Rate:    100%                │
│  Runtime Match Rate:      97%  (Act-1 후)     │
│  ─────────────────────────────────────────── │
│  Overall (0.15/0.25/0.25/0.35):  98%         │
│  (초회 Check: 95% → Act-1 후 98%)             │
└─────────────────────────────────────────────┘
```

---

## 3. Gap List

| ID | Severity | Confidence | Location | Gap | Fix |
|----|:--------:|:----------:|----------|-----|-----|
| G-01 | Important | 90% | `update_agent_use_case.py:_rebuild_tool_workers` (65줄), `wiki_repository.py:list_searchable_tree_items` (48줄, docstring 포함) | CLAUDE.md 40줄 규칙 — 두 함수는 변경 전부터 초과였고 이번 변경으로 각각 +7·+10줄 늘었다 | 프롬프트 재생성을 `_sync_tool_guidelines(agent, workers)`로, 컬럼 구성을 `_toc_columns(excerpt_chars)`로 추출 |
| G-02 | Minor | 95% | `toc_provider.py` render_block | Design D1 문구("excerpt_chars 전달")와 달리 값이 0보다 클 때만 kwarg 전달 | 의도된 강화(구 페이크 무회귀). Design D1 문구 갱신 |
| G-03 | Minor | 85% | Design §9.3 #3·#4 | 런타임 시나리오 2건 미실행 | 위키 없는 에이전트로 1회 실행 + 토큰 비교(Report 전 또는 QA) |
| G-04 | Minor | 90% | `ToolErrorPolicy` | HTTP 200 + "404" 본문(soft 404)은 오류로 감지되지 않음(run `4829bde0` 관찰) | 설계상 "확실한 신호만" 원칙. 알려진 한계로 문서화, 확장은 별도 사이클 |
| G-05 | Minor | 90% | `update_agent_use_case.py:_tool_guides_from_workers` | MCP 도구 이름을 카탈로그 재조회 대신 tool_id 마지막 조각으로 사용 | 현재 카탈로그 name과 동일 값. Design D5 문구 갱신 |

Critical: 0 / Important: 1 / Minor: 4 (+ 분석 중 발견 G-06)

### 3.1 Act-1 처리 결과 (2026-09-12, 사용자 결정 "지금 모두 수정")

| ID | 처리 | 근거 |
|----|------|------|
| G-01 | ✅ 해소 | `_sync_tool_guidelines(agent, workers)` 추출(10줄) → `_rebuild_tool_workers` 59줄(변경 전 크기로 복귀, 기존 초과분은 이 사이클 범위 밖). `_toc_columns(excerpt_chars)` 추출(19줄) → `list_searchable_tree_items` 35줄 |
| G-02 | ✅ 해소 | Design D1에 "0보다 클 때만 kwarg 전달" 문구 추가 |
| G-03 | ✅ 해소 | §2.7 #6 실런 통과, #7 구조 증명 |
| G-04 | ✅ 문서화 | Design D4에 알려진 한계로 기재 |
| G-05 | ✅ 해소 | Design D5 문구 갱신 |
| G-06 (신규, Important) | ✅ 해소 | 빌트인 `wiki_read`는 문서 0건 에이전트에도 존재 → 목차가 비면 `wiki_worker_id=""`로 넘겨 실패 블록의 "위키 확인" 줄을 끈다. `workflow_compiler.py` 호출부 + 테스트 `test_wiki_worker_without_toc_passes_empty_worker_id` |

---

## 4. Clean Architecture / Convention

| Check | Result |
|-------|--------|
| domain → application/infrastructure/외부 라이브러리 import | 없음 (`policies.py` ×2 grep 확인) |
| Repository commit/rollback | 없음 |
| UseCase 세션 직접 생성 | 없음 |
| print() | 없음, 실패 경로는 기존 warning(`exception=`) 경유 |
| 신규 함수 40줄 | 신규 13개 함수 전부 ≤33줄. 기존 초과 함수 확장은 G-01 |
| 신규 config 소비 지점 명기 | ✅ |
| Design Ref / Plan SC 주석 | D1·D3·D4·D5 핵심 지점에 표기 |

---

## 5. Runtime Verification Plan (잔여)

1. 위키 미등록 에이전트(예: `QA-tool-editing-temp`)에 존재하지 않는 도메인 스크래핑 요청 → 최종 답변이 URL을 지어내지 않고 대상 URL을 되묻는지 확인 (G-03 #3).
2. 같은 에이전트의 첫 supervisor 호출 `ai_llm_call.total_tokens`를 변경 전 런과 비교 → ±0 (G-03 #4).
3. dev 서버 재시작 후(`--reload` 미반영 관찰) 채팅 UI에서 동일 질문 재확인.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-12 | 초회 분석 — Overall 95%, Gap 5건(Important 1) | 배상규 |
| 0.2 | 2026-09-12 | Act-1 반영 — G-01~G-06 처리, 런타임 #3 실런 통과, Overall 98% | 배상규 |
