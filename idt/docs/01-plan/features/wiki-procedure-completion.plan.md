# wiki-procedure-completion Planning Document

> **Summary**: 위키에 자연어로 적힌 다단계 수집 절차를 진행 체크리스트로 승격해, supervisor가 절차를 끝까지 완주하게 한다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 미지정
> **Author**: 배상규
> **Date**: 2026-09-16
> **Status**: Draft (선행 피처 `supervisor-early-finish-fix` 완료 후 착수)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 위키 지침이 "A 하고 → B 하고 → C 하라"는 다단계 절차여도, supervisor는 1단계만 수행하고 종료한다. 절차가 state에 남지 않아 미완 단계를 붙잡아둘 자리가 없다. |
| **Solution** | `wiki_read` 워커 산출에서 절차 단계를 추출해 state에 보관하고, supervisor 결정 프롬프트에 "[진행 중인 지침 절차] 완료/미완" 체크리스트로 주입한다. 미완 단계가 남은 채 FINISH를 시도하면 1회 되돌린다. |
| **Function/UX Effect** | 사용자는 "OOO URL에서 검색 눌러서 가져와주세요" 같은 **평범한 자연어**로 위키를 써도 절차 전체가 수행된다. 도구 이름을 알 필요가 없다. |
| **Core Value** | 위키가 "참고 텍스트"에서 "실행되는 작업 지시"로 격상된다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 자연어 위키 절차의 2단계 이후가 실행되지 않고 버려진다 (트레이스 `01a0a82b` 실증) |
| **WHO** | P2 — KB 운영자/에이전트 소유자. 도구 이름을 모른 채 자연어로 작업 지침을 등록하는 사용자 |
| **RISK** | 절차 파싱이 틀리면 존재하지 않는 단계를 기다리며 종료가 지연된다 |
| **SUCCESS** | 재현 시나리오에서 3단계 절차가 끝까지 수행된다. 위키 미등록 에이전트는 결정 프롬프트 바이트 동일 |
| **SCOPE** | 위키 지침 절차만 추적. supervisor 자체 계획·사용자 질문의 명시 동작은 범위 밖 |

---

## 1. Overview

### 1.1 Purpose

위키에 등록된 다단계 절차를 **끝까지 완주**시킨다. 사용자가 도구 이름 없이 자연어로만 절차를 적어도 동작해야 한다.

### 1.2 Background

트레이스 `01a0a82b-77db-7ea2-85a2-2aad1548f371` 분석:

위키 문서 `bafc3c7e-64eb-4e97-81d0-1bfc01edd848` 본문 (사용자가 직접 작성):

> 금리에 대한 정보를 원할시 - `https://www.fsb.or.kr/ratedepo_0100.act` 페이지를 스크래핑 해서 이후 검색버튼을 눌러 스크래핑해서 관련 정보를 습득합니다

`wiki_read_worker`는 이 문장을 **정확히 3단계로 파싱해냈다**:

> 2. 수집 방법
>    - 위 URL 페이지를 **스크래핑**합니다.
>    - 이후 페이지 내 **검색 버튼을 클릭**합니다.
>    - 검색 결과가 로딩된 뒤, 다시 해당 화면을 **스크래핑**해서 각 저축은행별 금리 정보를 수집합니다.

그런데 supervisor는 이 산출을 **참고 텍스트로만 취급**했다. 2번째 결정에서 *"scrape_url 워커로 수집한 뒤, 필요하면 브라우저 조작용 워커로 검색버튼을 누르는 단계를 진행한다"*고 계획까지 세워놓고, 1단계 결과가 비자 3번째 결정에서 그 계획을 폐기하고 FINISH했다.

즉 **절차는 정확히 인식됐으나 보관되지 않아 휘발**했다.

기존 `_render_wiki_guidance_block` (`workflow_compiler.py:1672`)은 이렇게만 지시한다:

> "열람한 지침에 URL·경로·절차가 적혀 있으면, 다음 워커의 task에 그 값을 그대로 적으세요."

**다음 워커 1개**에 값을 전달하라는 규칙은 있지만, **절차 전체의 완주를 보장하는 규칙은 없다.** 본 피처가 그 빈칸을 메운다.

### 1.3 Related Documents

- 선행 피처(의존): `supervisor-early-finish-fix` — FINISH 1회 되물음 메커니즘을 본 피처가 재사용
- 선행 설계: `wiki-guided-routing` D3 — 확장 대상인 `_render_wiki_guidance_block`
- 근거 트레이스: LangSmith `01a0a82b-77db-7ea2-85a2-2aad1548f371`
- 선례: `workflow_compiler.py:612-628` wiki 폴더 모드의 다단계 체인 처리

---

## 2. Scope

### 2.1 In Scope

- [ ] `wiki_read` 워커 산출에서 절차 단계 목록을 추출
- [ ] `SupervisorState`에 절차 단계와 완료 상태 보관
- [ ] supervisor 결정 프롬프트에 "[진행 중인 지침 절차]" 체크리스트 블록 렌더
- [ ] 워커 실행 결과에 따라 단계 완료를 표시하는 진행 규칙
- [ ] 미완 단계가 남은 채 FINISH 시도 시 1회 되물음 (선행 피처 메커니즘 재사용)
- [ ] 회귀 보호: 위키 미등록 에이전트 / 절차가 없는 단문 위키는 결정 프롬프트 바이트 동일

### 2.2 Out of Scope

- **supervisor 자체 계획 추적** — 위키와 무관하게 supervisor가 스스로 세운 다음 단계 (질의 결과 범위 밖)
- **사용자 질문의 명시 동작 추출** — "검색 눌러서", "로그인해서" 같은 질문 내 동작 (질의 결과 범위 밖)
- 절차 단계와 워커의 자동 매핑 강제 (어떤 워커가 어떤 단계에 대응하는지는 supervisor LLM 판단에 맡김)
- 위키 문서 작성 UI/가이드 변경
- 브라우저 도구군 번들링

### 2.3 미해결 — Design 단계에서 결정할 사항

절차 단계 추출 방식이 확정되지 않았다. Design에서 3안을 비교한다.

| 안 | 방식 | 장점 | 단점 |
|----|------|------|------|
| (a) | `wiki_read` 워커에 구조화 출력을 추가해 `steps: list[str]`를 반환받음 | 추출이 정확, 추가 LLM 호출 0 | 워커 계약 변경, wiki 워커만 특수해짐 |
| (b) | supervisor가 워커 산출 텍스트를 보고 프롬프트 블록 안에서만 단계 관리 | 코드 변경 최소 | 완료 상태가 state에 없어 결정적 보장 불가 — 현재 실패의 재발 |
| (c) | 경량 LLM 1회 호출로 절차 파싱 | 자연어 대응력 최고, 워커 계약 무변경 | 런당 호출 +1 (비용·지연) |

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `wiki_read` 워커 산출에서 순서 있는 절차 단계 목록을 추출한다. 절차가 없는 단문 위키면 빈 목록 | High | Pending |
| FR-02 | `SupervisorState`에 절차 단계 목록과 각 단계의 완료 여부를 보관한다 | High | Pending |
| FR-03 | supervisor 결정 프롬프트에 "[진행 중인 지침 절차]" 블록을 렌더한다. 각 단계의 완료/미완 표시와 "미완 단계가 남아 있으면 FINISH를 선택하지 마세요" 지시를 포함 | High | Pending |
| FR-04 | 워커 실행 후 어떤 단계가 완료됐는지 갱신한다. 판정 주체(LLM 자기보고 / 결정적 규칙)는 Design에서 확정 | High | Pending |
| FR-05 | 미완 단계가 남은 상태의 FINISH를 1회 되돌린다. 선행 피처 `supervisor-early-finish-fix`의 되물음 게이트를 재사용하고 사유만 구분한다 | High | Pending |
| FR-06 | 절차 단계 수에 상한을 둔다 (과도한 파싱 결과가 프롬프트를 잠식하지 않도록) | Medium | Pending |
| FR-07 | 위키 목차 블록이 렌더되지 않았거나 wiki 워커가 없으면 본 기능 전체가 무영향이다 (기존 D3 조건과 동일) | High | Pending |
| FR-08 | 절차 추출 결과와 단계 완료 전이를 구조화 로그로 남긴다 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 비용 | 추가 LLM 호출은 0회 또는 런당 최대 1회 (Design 선택안에 따름) | 트레이스의 LLM 런 수 대조 |
| 토큰 | 체크리스트 블록은 단계당 1줄, 전체 600자 이내 | 단위 테스트 |
| 회귀 | 위키 미등록·절차 없는 에이전트의 결정 프롬프트 바이트 동일 | 회귀 테스트 |
| 안전성 | 절차 완주 강제가 종료 불가 상태를 만들지 않음 (되물음 1회 상한 + `max_iterations` 우선) | 단위 테스트 |
| 아키텍처 | 절차 파싱 규칙은 domain, 흐름 제어는 application | `/verify-architecture` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-08 구현 완료
- [ ] TDD 준수
- [ ] **재현 시나리오**: 위키 본문 "…스크래핑 해서 이후 검색버튼을 눌러 스크래핑해서…"가 주어졌을 때 절차가 3단계로 추출되고, 1단계만 완료된 상태의 FINISH가 되돌려진다
- [ ] 절차가 없는 단문 위키에서 블록이 렌더되지 않음
- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과

### 4.2 Quality Criteria

- [ ] 함수 길이 40줄 이내, if 중첩 2단계 이내
- [ ] 신규 모듈에 대응 테스트 존재
- [ ] lint 오류 0

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **절차 파싱 오류** — 단계가 아닌 문장을 단계로 잡아 영원히 미완 상태가 된다 | High | Medium | 되물음 1회 상한으로 종료 불가 상태를 구조적으로 차단. 단계 수 상한(FR-06) |
| **단계 완료 판정 실패** — 워커가 단계를 수행했는데 미완으로 남는다 | Medium | Medium | Design에서 판정 주체를 명확히 확정. 되물음 1회라 최악이어도 1회 추가 왕복 |
| 자연어 표현 다양성 — "~한 뒤", "그 다음", 번호 목록 등 형태가 제각각 | Medium | High | 파싱을 정규식이 아닌 LLM 기반((a) 또는 (c))으로 두는 것을 우선 검토 |
| 선행 피처 미완 시 되물음 메커니즘 부재 | High | Low | 착수 순서를 `supervisor-early-finish-fix` 이후로 고정 (본 문서 Status에 명시) |
| 체크리스트 블록이 기존 위키 지침 블록과 중복 지시 | Low | Medium | 두 블록을 한 절로 합칠지 분리할지 Design에서 결정 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/application/agent_builder/supervisor_state.py` · `SupervisorState` | State 스키마 | 절차 단계·완료 상태 필드 추가 |
| `src/application/agent_builder/workflow_compiler.py` · `_render_wiki_guidance_block` | Prompt 블록 | 체크리스트 절 확장 (또는 신규 블록 분리) |
| `src/application/agent_builder/workflow_compiler.py` (wiki 워커 분기, 612-655행대) | Graph Compiler | (a)안 선택 시 wiki 워커 구조화 출력 배선 |
| `src/application/agent_builder/supervisor_nodes.py` | Graph Node | 체크리스트 블록 렌더 + 단계 완료 갱신 + FINISH 되물음 사유 분기 |
| `src/domain/agent_builder/policies.py` | Domain Policy | 절차 단계 상한·정규화 규칙 (신설 또는 기존 정책 확장) |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `_render_wiki_guidance_block` | READ | `workflow_compiler.py:726` → `create_supervisor_node(wiki_guidance_block=...)` | Needs verification |
| `_render_wiki_guidance_block` | READ | `tests/application/agent_builder/test_workflow_compiler_wiki_toc.py` | Breaking — 단언 갱신 필요 |
| `SupervisorState` | READ/WRITE | `supervisor_nodes.py` 전체 노드·라우팅 함수 | None — 필드 추가는 하위호환 |
| `SupervisorState` | READ | `run_agent_use_case.py` payload 구성 | Needs verification — 신규 필드 누출 여부 |
| wiki 워커 노드 (`workflow_compiler.py:635` `create_agent`) | WRITE | (a)안 선택 시 출력 계약 변경 | Breaking — (a) 선택 시에만 |
| `_WIKI_WORKER_INSTRUCTION` / `_WIKI_FOLDER_WORKER_INSTRUCTION` | READ | wiki 워커 system_prompt | Needs verification — (a) 선택 시 지시 추가 |
| FINISH 되물음 게이트 | READ/WRITE | 선행 피처가 생성한 코드 | Needs verification — 사유 구분 파라미터 추가 |

### 6.3 Verification

- [ ] 위 소비자 전부 정상 동작 확인
- [ ] wiki 폴더 모드(`wiki_list` 동봉 경로)가 깨지지 않음 확인
- [ ] 절차 없는 위키·위키 미등록 에이전트 무영향 확인
- [ ] 선행 피처의 되물음 상한이 두 사유(빈 결과 / 미완 절차) 합산으로 폭주하지 않음 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 구조 | 정적 사이트 | ☐ |
| **Dynamic** | 기능 모듈 + BaaS | 웹앱, SaaS MVP | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DI | 복잡한 아키텍처 | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 절차 추적 범위 | 위키 절차만 / +supervisor 자체 계획 / +사용자 질문 동작 | **위키 절차만** | 사용자 선택. 범위 명확, `wiki_toc_block` 유무로 무영향 보장이 쉬움 |
| FINISH 차단 강도 | 프롬프트 지시 / 결정적 차단 / 1회 되물음 | **1회 되물음** | 사용자 선택. 선행 피처와 동일 메커니즘 재사용 |
| 절차 추출 방식 | (a) 워커 구조화 출력 / (b) 프롬프트 내 관리 / (c) 경량 LLM 파싱 | **미정 — Design에서 3안 비교** | (b)는 state 보관이 없어 현재 실패의 재발 위험이 커 사실상 탈락 후보 |
| 단계 완료 판정 | LLM 자기보고 / 결정적 규칙 | **미정 — Design** | 결정적 규칙은 워커↔단계 매핑이 필요해 일반성이 떨어짐 |
| 블록 배치 | 기존 위키 블록 확장 / 신규 블록 분리 | **미정 — Design** | 중복 지시 회피와 무영향 보장의 트레이드오프 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

변경 위치:
┌─────────────────────────────────────────────────────┐
│ domain/agent_builder/policies.py                    │
│   └ 절차 단계 상한·정규화 규칙                       │
├─────────────────────────────────────────────────────┤
│ application/agent_builder/                          │
│   ├ supervisor_state.py   (절차·완료 상태 필드)      │
│   ├ supervisor_nodes.py   (체크리스트 렌더 + 완료 갱신)│
│   └ workflow_compiler.py  (블록 조립 + wiki 워커 배선)│
└─────────────────────────────────────────────────────┘
infrastructure/ 변경 없음 · interfaces/ 변경 없음
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md` 코딩 규칙 (루트 + `idt/`)
- [x] `idt/docs/rules/` 세부 규칙
- [x] `docs/wiki/_INDEX.md` 개발 위키

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Design Ref 주석** | exists | `# Design Ref: wiki-procedure-completion §N` | High |
| **Plan SC 주석** | exists | `# Plan SC: FR-0N` | High |
| **state 필드 주석** | exists | 설계 출처·수명주기 명시 (기존 형식) | High |
| **블록 문구 규범** | exists | `[[supervisor-graph-contracts]] §2` 목록 프레이밍 금지 규칙 준수 | High |

### 8.3 Environment Variables Needed

신규 환경변수 없음. (c)안 선택 시 파싱용 모델 설정이 기존 LLM 설정을 재사용하는지 Design에서 확인.

### 8.4 Pipeline Integration

해당 없음.

---

## 9. Next Steps

1. [ ] **선행 피처 `supervisor-early-finish-fix` 완료 확인** (되물음 게이트 존재)
2. [ ] `/pdca design wiki-procedure-completion` — 절차 추출 3안 비교 후 선택
3. [ ] 개발 위키에서 supervisor 그래프 계약 문서 확인
4. [ ] TDD 구현 (`/pdca do`)
5. [ ] Gap 분석 (`/pdca analyze`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-16 | 최초 작성. 트레이스 `01a0a82b` 분석 기반, 범위를 위키 절차로 한정 | 배상규 |
