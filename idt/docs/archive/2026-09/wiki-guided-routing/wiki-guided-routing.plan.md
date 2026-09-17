# wiki-guided-routing Planning Document

> **Summary**: 에이전트 위키에 등록된 작업 지침(출처 URL·절차)이 있는데도 수퍼바이저가 위키를 건너뛰고 외부 수집 도구로 직행해 잘못된 결과를 내는 문제를 고친다. 기존 "목차 → LLM 판단 → wiki_read" 설계는 유지하고, LLM이 판단할 수 있는 신호를 보강한다.
>
> **Project**: sangplusbot / idt (백엔드)
> **Version**: HEAD a07ef09 기준
> **Author**: 배상규
> **Date**: 2026-09-11
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 소유자가 위키에 "금리 정보는 fsb.or.kr 특정 페이지를 스크래핑하라"는 지침을 승인 등록했는데, 채팅에서 "저축은행별 금리 전체 표"를 물으면 수퍼바이저가 위키를 열람하지 않고 scrape 워커로 직행해 URL을 지어내고(DNS 실패), 실패 후 위키 재확인 없이 "불가"로 종료했다. 목차 블록과 wiki_read 워커는 정상 동작 중이었으므로 기계적 결함이 아니라 **LLM 판단 신호 부족**이 원인이다. |
| **Solution** | (1) 목차 줄에 본문 발췌(앞부분)를 붙여 제목이 질문과 안 닿아도 관련성을 볼 수 있게 하고, (2) 목차 헤더·wiki 도구 설명·수퍼바이저 결정 규칙에 "작업 절차·출처 URL 지침도 위키에 있으며 외부 수집 전에 확인한다"를 명시하며, (3) 수집 워커 실패 시 위키 재확인 → 없으면 URL을 지어내지 말고 사용자에게 되묻는 폴백 규칙을 넣는다. (4) 부수로, 도구 변경 시 저장 프롬프트의 `## Tool Guidelines` 섹션만 재생성해 도구 목록 불일치를 없앤다. |
| **Function/UX Effect** | 위키에 경로·절차를 적어 두면 에이전트가 그 지침대로 움직인다. 지침이 없을 때는 URL을 추측하는 대신 사용자에게 대상을 묻는다. 에이전트 편집 화면에서 도구를 바꿔도 프롬프트의 도구 목록이 따라온다. |
| **Core Value** | P2(에이전트 소유자)가 코드 수정 없이 **위키 문서만으로 에이전트의 작업 경로를 통제**할 수 있다. 여신·금리 특화가 아니라 "위키 지침 우선"이라는 일반 규칙으로 해결한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 위키 목차가 제목 한 줄뿐이고 "지침도 위키에 있다"는 프레이밍이 없어, 수퍼바이저 LLM이 위키를 건너뛰고 외부 수집 도구를 추측 호출한다 (실제 런 `8ccc097f` 재현). |
| **WHO** | P2 에이전트 소유자(위키로 경로·절차를 등록하는 사람)와 그 에이전트를 쓰는 최종 사용자. |
| **RISK** | 프롬프트 규칙이 "위키 항상 먼저"로 과잉 적용되면 매 턴 wiki_read 왕복이 생겨 토큰·지연이 는다. 목록 프레이밍 금지 계약([[supervisor-graph-contracts]] §2)에 따라 "관련 항목이 있을 때만"으로 한정한다. |
| **SUCCESS** | 동일 에이전트·동일 질문 재실행 시 `ai_run_step`에 `wiki_read_worker` → 수집 워커(fsb.or.kr) 순서가 기록되고 최종 답변에 fsb.or.kr 출처 데이터가 포함된다. 기존 테스트 FAILED 목록 diff 0. |
| **SCOPE** | Phase 1: 목차 발췌 + 프레이밍 + 결정 규칙 + 실패 폴백(프롬프트 계층). Phase 2: Tool Guidelines 섹션 재생성(수정 UseCase). 표 추출 정확도·강제 라우팅·스키마 변경은 제외. |

---

## 1. Overview

### 1.1 Purpose

에이전트 소유자가 위키에 등록한 **작업 지침(어느 URL을, 어떤 절차로)** 을 수퍼바이저가 실제로 참조하도록 만든다. 기존 wiki-agentic-navigation 설계(목차 prepend → LLM이 필요 시 wiki_read 워커로 열람)는 그대로 두고, LLM이 "열람할 가치가 있다"고 판단할 수 있는 정보와 규칙을 보강한다.

### 1.2 Background

**재현 사실 (로컬 DB `ai_run` / `ai_run_step` / `ai_tool_call`, 2026-09-11)**

| 항목 | 값 |
|------|----|
| 에이전트 | `f41c622e-81c7-4098-baa1-8c688968fb0e` (브라우저 조작·스크래핑 에이전트) |
| 등록 도구 | Browser MCP 5종 + Scrap MCP `scrape_url` + 빌트인 `wiki_read`, `wiki_list` |
| 승인 위키 | 1건 — 제목 "작업요청시 경로참조", path "경로", 본문 "금리에 대한 정보를 원할시 https://www.fsb.or.kr/ratedepo_0100.act 페이지를 스크래핑 해서 관련 정보를 습득합니다" |
| 질문 | "현재 기준 각 저축은행별 금리에대한 전체 표로 보여 주세욥" |
| 실패 런 | `8ccc097f-5135-4b4a-9fc1-5242141ba91f` |

실패 런의 단계 기록:

1. supervisor iter=0 — "신뢰할 수 있는 외부 비교 서비스를 스크래핑해야 한다"고 판단, `scrape_url_worker` 선택. 위키는 언급 없음.
2. scrape 워커 — URL을 **추측**해 `https://fpb.fss.or.kr/fpbhub/ib20/mnu/FPMHPB2030.do` 호출 → `Name or service not known`.
3. supervisor iter=1 — "더 이상 호출할 수 있는 유효한 워커도 없다"며 FINISH. `wiki_read_worker`는 끝까지 후보로 고려되지 않음.

**동작 중이었던 것 (기계적 결함 아님을 확인)**

- `WikiTocProvider.render_block`을 같은 에이전트로 직접 렌더한 결과, 목차 블록은 정상 생성된다(`- (id: bafc3c7e-…) 경로/작업요청시 경로참조 — 갱신 2026-09-11`). 컴파일러는 이 블록을 수퍼바이저 프롬프트 앞에 붙인다 (`workflow_compiler.py:371-380`).
- `wiki_read_worker`는 `agent_tool`에 존재하고 결정 프롬프트의 "사용 가능한 워커" 목록에 포함된다 (`supervisor_nodes.py:202-204`).

**LLM 판단을 그르친 3가지 요인**

| # | 요인 | 근거 위치 |
|---|------|-----------|
| A | 목차 한 줄에 제목만 있어 "작업요청시 경로참조" ↔ "저축은행 금리" 사이 의미 연결이 없다 | `prompt_rendering.py` `_toc_line` |
| B | 목차 헤더와 `wiki_read` 설명이 위키를 "인용·상세 내용·결정사항·판단 기준"으로만 프레이밍한다. "어떤 URL/절차로 일할지" 같은 지침이 있을 수 있다는 힌트가 없다 | `prompt_rendering.py` `_TOC_HEADER`, `tool_registry.py` `wiki_read`/`wiki_list` |
| C | 결정 프롬프트에 "외부 수집 전 위키 확인" 규칙과 "수집 실패 후 위키 재확인·되묻기" 규칙이 없다. 강제 라우팅은 첨부·시각화·문서생성에만 있다 | `supervisor_nodes.py:242-268`, `workflow_compiler.py:674-690` |

**부수 문제 (범위 포함)**

- 저장된 `system_prompt`의 `## Tool Guidelines`가 빌드 시점 도구(browser 4종 + scrape_url)만 담고 있다. 이후 추가된 `browser_snapshot`·`wiki_*`는 빠져 있다. 도구 편집 UseCase(`update_agent_use_case.py:255-295`)가 워커와 `flow_hint`는 재구성하지만 프롬프트 본문은 손대지 않기 때문이다.

**부수 문제 (범위 제외 — 별도 사이클)**

- 정상 URL로 간 런(`88aa35cb`)에서도 `browser_extract`가 selector 없이 본문 전체를 잘라 와 평균금리만 나왔다. Browser/Scrap MCP 서버 소스는 이 워크스페이스에 없다.

### 1.3 Related Documents

- 위키: `docs/wiki/backend/patterns/supervisor-graph-contracts.md` (✅ 목록 프레이밍 금지·강제 라우팅 범위), `docs/wiki/backend/db/erd-wiki.md` (📝 agent_id 예약석·탐색 체인), `docs/wiki/conventions/config-single-source-at-consumption.md` (✅ 신규 config 규칙), `docs/wiki/conventions/false-green-quality-gates.md` (✅ 회귀 증명 방식)
- 선행 기능: wiki-agentic-navigation(목차 prepend·wiki_read 워커), wiki-folder-summaries(폴더 모드, 기본 off), worker-context-injection(워커 컨텍스트 블록·도구 사용 규범), mcp-tool-category-routing(카테고리·호출 예산), prompt-depth / prompt-composer(결정적 섹션 조립), agent-update-tool-editing(도구 편집 시 워커 재구성)
- 유저 시나리오: `docs/USER-SCENARIOS.md` — P2가 주인공, 특화 vs 일반화 충돌 시 일반화 우선

---

## 2. Scope

### 2.1 In Scope

- [ ] **목차 발췌**: 목차 줄에 본문 앞부분(설정 가능한 글자 수)을 붙인다. 본문 전체는 여전히 미조회(SQL 절단).
- [ ] **프레이밍 보정**: 목차 헤더, `wiki_read`·`wiki_list` 도구 설명, wiki 워커 지시문에 "작업 절차·출처 URL·경로 지침도 위키에 있다"를 명시.
- [ ] **결정 규칙**: 수퍼바이저 결정 프롬프트에 "목차에 관련 항목이 있으면 외부 수집(스크래핑·브라우저·웹검색) 전에 wiki_read로 확인하고, 위키가 지정한 URL/절차를 task에 명시"를 추가.
- [ ] **실패 폴백 규칙**: 수집 워커가 오류로 끝났을 때 (a) 위키 미확인이면 wiki_read 먼저, (b) 위키에도 없으면 URL·식별자를 추측하지 말고 FINISH+answer로 사용자에게 대상을 되묻기. 인터럽트 없이 기존 FINISH 경로 사용.
- [ ] **Tool Guidelines 섹션 재생성**: 도구 편집 시 저장 프롬프트에 `## Tool Guidelines` 섹션이 있으면 prompt_composer의 결정적 조립으로 그 섹션만 교체. 섹션이 없으면 무변경.
- [ ] **재현 검증**: 대상 에이전트로 동일 질문 재실행 → `ai_run_step` 순서·최종 답변 출처 확인.

### 2.2 Out of Scope

- 결정적 강제 라우팅(iter=0에 wiki_read 고정) — [[supervisor-graph-contracts]] §3 "결정적 라우팅=확실한 신호 전용"과 충돌, 매 턴 LLM 호출 증가.
- 짧은 문서 본문 통째 주입 — "목차로 판단" 설계와 이중 경로가 됨(사용자 결정으로 제외).
- `wiki_article` 스키마 변경(항상-주입 플래그 등).
- 폴더 모드(`wiki_folder_summaries_enabled`) 동작 변경.
- 표 추출 정확도(selector·페이지네이션·max_chars) — MCP 서버 외부.
- 프론트엔드 변경 — 목차 발췌는 프롬프트 전용 필드로, 트리 API 응답 계약은 additive 이외 변경 없음.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | 목차 항목에 본문 발췌(`excerpt`)를 additive optional 필드로 추가한다. 저장소는 본문 전체가 아니라 SQL 절단(SUBSTRING)으로 앞 N자만 조회한다. N은 소비 지점(prompt_rendering)이 읽는 신규 config(`wiki_toc_excerpt_chars`, 기본값 Design에서 확정)로 정한다. | High | Pending |
| FR-02 | `render_wiki_toc_block`이 발췌를 `— {excerpt}` 형태로 줄에 포함한다. 줄바꿈은 공백으로 치환하고 기존 `wiki_toc_max_bytes` 예산·절단 알림 규칙을 그대로 따른다. 발췌가 없으면(레거시/빈 본문) 기존 형식과 바이트 동일 출력. | High | Pending |
| FR-03 | 목차 헤더(`_TOC_HEADER`)·폴더 헤더, `wiki_read`/`wiki_list` `ToolMeta.description`, `_WIKI_WORKER_INSTRUCTION`에 "작업 절차·출처 URL·경로 같은 지침도 이 위키에 있다"는 문구를 추가한다. 목록 프레이밍 금지 원칙에 따라 "기본은 확인, 예외만 명시" 톤. | High | Pending |
| FR-04 | 수퍼바이저 결정 프롬프트에 규칙 추가: 목차에 질문과 관련된 항목이 있으면 외부 수집 워커(scrape·browser·웹검색 계열) 전에 `wiki_read` 워커를 먼저 선택하고, 열람한 지침에 URL·절차가 있으면 이후 워커의 `task`에 그 값을 그대로 적는다. 목차 블록이 없는 에이전트(wiki_read 미등록)에는 규칙 문구가 삽입되지 않는다(빈 문자열 무영향 패턴 재사용). | High | Pending |
| FR-05 | 실패 폴백: 직전 수집 워커 산출물이 도구 오류(예: `Error executing tool`, 접속 실패)를 담고 있을 때 결정 프롬프트에 "[직전 수집 실패]" 안내 블록을 렌더한다. 블록 내용: 위키를 아직 열람하지 않았으면 wiki_read 먼저, 위키에도 지침이 없으면 URL·식별자를 추측하지 말고 FINISH를 선택해 answer에 사용자가 지정할 대상 URL을 되묻는 문장을 쓴다. 실패 판정은 순수 함수(정책)로 두고 재주입분(REINJECTED_MARKER)은 제외한다. | High | Pending |
| FR-06 | 도구 편집(`tool_ids` 포함 update)이 워커를 재구성한 뒤, 적용 대상 `system_prompt`(요청에 `system_prompt`가 함께 오면 그 값, 아니면 저장값)에 `## Tool Guidelines` 헤딩이 있으면 현재 tool 워커 기준으로 `PromptAssemblyPolicy`가 조립한 섹션으로 그 섹션만 교체한다. 헤딩이 없으면 무변경. 다른 섹션의 사용자 편집분은 보존한다. | Medium | Pending |
| FR-07 | 재현 검증 절차를 문서화하고 실행한다: 대상 에이전트로 "저축은행별 금리 전체 표" 질문 → `ai_run_step`에 `wiki_read_worker`가 첫 워커로 기록되고, 이후 수집 워커의 `ai_tool_call.arguments_json`에 `fsb.or.kr/ratedepo_0100.act`가 담긴다. | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 토큰 | 목차 블록 총량은 기존 `wiki_toc_max_bytes`(4000) 상한 내. 발췌 추가로 인한 수퍼바이저 프롬프트 증가는 문서당 발췌 길이 × 항목 수를 넘지 않음 | 단위 테스트에서 바이트 상한 단언, 재현 런의 `ai_llm_call.total_tokens` 전후 비교 |
| 결정성 | 목차·섹션 재조립은 시간·랜덤 없이 동일 입력 → 바이트 동일 출력 (prompt-depth FR-08 계승) | 스냅샷 테스트 |
| 회귀 | 기존 테스트 FAILED 목록 diff 0 (pass/fail 개수가 아니라 정렬된 FAILED 목록 비교, [[false-green-quality-gates]]) | `pytest -q` 전후 FAILED 목록 diff |
| 성능 | 목차 조회는 본문 전체 미조회 유지 — SUBSTRING만 추가, 추가 쿼리 0 | 쿼리 문자열 테스트(`test_wiki_repository_toc`) 갱신 |
| 계약 보존 | 트리 API(`GET /api/v1/wiki/tree`) 응답은 기존 필드 불변. `excerpt`는 프롬프트 전용이며 API 응답 스키마에 노출하지 않거나 optional로만 추가 | 라우터 테스트 |
| 아키텍처 | domain → infrastructure 참조 금지, 실패 판정 규칙은 순수 함수, 라우터에 로직 없음 | `/verify-architecture` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-07 구현 및 각 FR에 대응하는 테스트(Red → Green) 존재
- [ ] 재현 시나리오(FR-07)에서 `wiki_read_worker` → 수집 워커(fsb.or.kr) 순서가 `ai_run_step`에 기록됨
- [ ] 위키 지침이 없는 에이전트로 접속 불가 URL 질문 시, URL을 지어내지 않고 사용자에게 대상 URL을 되묻는 답변이 나옴
- [ ] 도구 추가/삭제 후 저장 프롬프트의 `## Tool Guidelines`가 현재 도구와 일치하고, 다른 섹션 편집분이 보존됨
- [ ] 기존 테스트 FAILED 목록 diff 0
- [ ] 신규 config 키 docstring에 소비 지점 파일:라인 명기 ([[config-single-source-at-consumption]])

### 4.2 Quality Criteria

- [ ] 변경 모듈 전부 테스트 파일 존재 (`/verify-tdd`)
- [ ] 레이어 의존성 위반 0 (`/verify-architecture`)
- [ ] 로깅 규칙 준수, 예외 삼키는 경로는 `exception=` kwarg (`/verify-logging`)
- [ ] 함수 40줄·if 중첩 2단계 제한 준수

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| "위키 먼저" 규칙이 과잉 적용되어 무관한 질문에도 wiki_read 왕복 발생(토큰·지연 증가) | Medium | Medium | 규칙을 "목차에 관련 항목이 있을 때만"으로 한정. 목록 프레이밍 금지 계약 준수. 재현 런과 무관 질문 런의 step 수·토큰 비교를 DoD에 포함 |
| 발췌가 길어 목차가 `max_bytes`에서 잘려 뒤쪽 문서가 누락 | Medium | Medium | 발췌 길이를 config로 제한(기본값 짧게), 절단 알림 문구 기존 유지, 절단 테스트 추가 |
| 발췌에 지시문이 섞여 프롬프트 주입 표면 확대 | Low | Low | 승인(approved) 문서만 대상(기존 조건 유지). CONVERSATION 출처는 승인 전 노출 안 됨 |
| 실패 판정 휴리스틱이 오탐(정상 결과를 실패로) 또는 미탐 | Medium | Medium | 판정을 순수 함수로 분리해 케이스 테스트. 재주입분 제외([[supervisor-graph-contracts]] §3). 오탐 시 영향은 "안내 블록 1개 추가"에 그침 |
| Tool Guidelines 재생성이 사용자 편집 프롬프트를 덮어씀 | High | Low | 헤딩이 있을 때만 해당 섹션 한정 교체, 없으면 무변경. 교체 전후 다른 섹션 바이트 동일 테스트 |
| `test_wiki_repository_toc`가 쿼리 문자열을 고정하고 있어 SUBSTRING 추가로 실패 | Low | High | 의도된 변경 — 테스트를 먼저 갱신(Red)하고 구현 |
| 결정 프롬프트 변경이 첨부·시각화·문서생성 라우팅 등 다른 기능의 LLM 판단에 영향 | Medium | Low | 기존 블록 순서 유지, 신규 블록은 조건부 빈 문자열. 관련 통합 테스트 회귀 확인 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `WikiTreeItem` (`src/application/wiki/schemas.py`) | Schema (dataclass) | `excerpt: str \| None = None` additive 추가 |
| `WikiArticleRepository.list_searchable_tree_items` (`src/infrastructure/wiki/wiki_repository.py`) | Repository query | SELECT에 `SUBSTRING(content, 1, N)` 추가, 인터페이스 시그니처에 N 전달 방식은 Design에서 확정 |
| `prompt_rendering.py` (`_TOC_HEADER`, `_toc_line`, `render_wiki_toc_block`, `_FOLDER_HEADER`) | Prompt template | 발췌 포함, 프레이밍 문구 추가 |
| `tool_registry.py` (`wiki_read`, `wiki_list` ToolMeta.description) | Domain registry | 설명 문구 보정 |
| `workflow_compiler.py` (`_WIKI_WORKER_INSTRUCTION`, 수퍼바이저 노드 생성 시 규칙/블록 전달) | Application | 지시문 보정, 결정 규칙·실패 블록 주입 |
| `supervisor_nodes.py` (decision_prompt) | Application | 위키 우선 규칙(조건부)·"[직전 수집 실패]" 블록 렌더 |
| 신규 정책 함수 (수집 실패 판정) | Domain/Application 순수 함수 | 위치는 Design에서 확정 (`search_pipeline`의 메시지 규약과 인접) |
| `config.py` | Config | `wiki_toc_excerpt_chars` 추가 (소비 지점 docstring 명기) |
| `update_agent_use_case.py` | Application UseCase | 도구 재구성 후 Tool Guidelines 섹션 교체 호출 |
| `prompt_composer/policies.py` | Domain policy | 섹션 단위 교체 헬퍼(기존 `assemble`의 `_tool_block` 재사용) |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `WikiTreeItem` | READ | `src/application/wiki/query_use_case.py` (트리 API) → `src/api/routes/wiki_router.py` `GET /tree` | Needs verification — optional 필드 추가, API 응답 스키마(`api_schemas.py`) 노출 여부 확인 |
| `WikiTreeItem` | READ | `src/infrastructure/wiki/wiki_list_tool.py` (wiki_list 도구) | None (필드 무시) |
| `WikiTreeItem` | READ | `src/application/wiki/toc_provider.py` → `render_wiki_toc_block` | Breaking (의도) — 발췌 표시 |
| `list_searchable_tree_items` | READ | `toc_provider.py` 만 | Needs verification — 쿼리 문자열 고정 테스트 `tests/infrastructure/wiki/test_wiki_repository_toc.py` 갱신 |
| `_TOC_HEADER` / `render_wiki_toc_block` | READ | `tests/application/agent_run/test_prompt_rendering.py`, `tests/application/wiki/test_toc_provider*.py`, `tests/application/agent_builder/test_workflow_compiler_wiki_toc.py` | Needs verification — 문구·형식 단언 갱신 |
| `wiki_read`/`wiki_list` description | READ | 워커 스켈레톤 → 수퍼바이저 워커 목록, 카탈로그 API(`tests/api/test_tool_catalog_router.py`), `tests/application/agent_builder/test_worker_skeleton_builder.py` | Needs verification — 설명 문자열 단언 여부 |
| decision_prompt | READ | 모든 에이전트 실행 경로, `tests/application/agent_builder/test_workflow_compiler*.py`, `test_worker_context_injection.py` | Needs verification — 조건부 삽입으로 위키 미등록 에이전트는 바이트 동일 |
| `system_prompt` (agent_definition) | UPDATE | `update_agent_use_case.py` `_rebuild_tool_workers` 이후, `tests/application/agent_builder/test_update_agent_tool_editing.py` | Needs verification — 섹션 한정 교체 |
| `PromptAssemblyPolicy` | READ | `src/application/prompt_composer/compose_prompt_use_case.py` | None (기존 `assemble` 무변경, 헬퍼 추가) |

### 6.3 Verification

- [ ] 위 소비자 전수에 대해 변경 후 테스트 통과 또는 의도된 갱신 확인
- [ ] 인가·권한 변경 없음 (위키 조회 조건 approved+미만료 유지)
- [ ] 트리 API 응답 필드 추가/삭제로 프론트 타입(`idt_front/src/types`) 변경이 필요한지 확인 — 노출하지 않으면 프론트 무변경

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, BaaS | Web apps, SaaS MVPs | ☐ |
| **Enterprise** | Strict layer separation, DI | 기존 idt Thin DDD | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 위키 참조 보강 방식 | 강제 라우팅 / 본문 통째 주입 / 목차 발췌+프롬프트 규칙 | **목차 발췌 + 프롬프트 규칙** | 기존 "목차로 LLM 판단" 설계 유지, 결정적 라우팅은 확실한 신호 전용 계약 준수, 스키마 변경 0 |
| 발췌 조회 위치 | 앱에서 본문 전체 조회 후 절단 / SQL SUBSTRING | **SQL SUBSTRING** | 목차 조회의 "본문 미조회" 성능 계약 유지 |
| 발췌 길이 출처 | 하드코딩 / 신규 config | **신규 config (소비 지점 명기)** | [[config-single-source-at-consumption]] |
| 실패 폴백 | 인터럽트 HITL / FINISH+answer 되묻기 | **FINISH+answer** | 채팅 실행 경로에 인터럽트 기반 HITL이 없음. 기존 FINISH 경로로 충분 |
| 실패 판정 | 프롬프트만 / 순수 함수 + 조건부 블록 | **순수 함수 + 조건부 블록** | 확실한 신호(도구 오류 문자열)는 결정적으로 감지하고 판단은 LLM에 — 책임 분리 |
| Tool Guidelines 정합 | 저장 안 함(런타임 렌더) / 전체 재생성 / 섹션 한정 재생성 | **섹션 한정 재생성** | 사용자 편집 보존, 마이그레이션·프론트 무영향 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (기존 idt Thin DDD)

domain/          prompt_composer/policies.py (섹션 교체 헬퍼), agent_builder/tool_registry.py (설명)
                 + 수집 실패 판정 순수 함수 (위치 Design 확정)
application/     wiki/schemas.py (WikiTreeItem.excerpt), wiki/toc_provider.py,
                 agent_run/prompt_rendering.py, agent_builder/supervisor_nodes.py,
                 agent_builder/workflow_compiler.py, agent_builder/update_agent_use_case.py
infrastructure/  wiki/wiki_repository.py (SUBSTRING 조회)
interfaces/      변경 없음 (트리 API 계약 불변)
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규칙 (idt/CLAUDE.md)
- [x] `docs/rules/*.md` (db-session, logging, testing, tool-and-mcp)
- [x] pytest 기반 TDD 필수
- [ ] ESLint / Prettier / tsconfig — 프론트 무변경이므로 해당 없음

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 프롬프트 문자열 계약 | 헤더 태그(`WIKI_FOLDER_HEADER_TAG`)가 compiler 모드 판별에 쓰임 | 헤더 문구 변경 시 태그 상수는 유지 | High |
| 신규 config | `wiki_toc_*` 키 존재 | `wiki_toc_excerpt_chars` docstring에 소비 지점 명기 | High |
| 실패 판정 규약 | `is_search_result` 등 메시지 규약 공유 | 신규 판정 함수는 소비자 전수 확인 후 추가 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `WIKI_TOC_EXCERPT_CHARS` | 목차 발췌 글자 수 (Settings 필드 `wiki_toc_excerpt_chars`) | Server | ☑ (기본값 있음, .env 선택) |

### 8.4 Pipeline Integration

해당 없음 — 기존 기능의 결함 수정 사이클.

---

## 9. Next Steps

1. [ ] Design 작성 (`docs/02-design/features/wiki-guided-routing.design.md`) — 발췌 길이 기본값, 실패 판정 함수 위치·규칙, 섹션 교체 헬퍼 시그니처, 규칙 문구 확정
2. [ ] Red 테스트: `test_wiki_repository_toc`(쿼리), `test_prompt_rendering`(발췌·헤더), `test_workflow_compiler_wiki_toc`(규칙 조건부 삽입), 실패 판정 함수, `test_update_agent_tool_editing`(섹션 교체)
3. [ ] 구현 → 재현 시나리오(FR-07) 실행 → `ai_run_step` 확인
4. [ ] `/pdca analyze wiki-guided-routing`

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-11 | 초안 — 실패 런 재현·원인 분석·해결 방향 확정(사용자 Q&A 3회) | 배상규 |
