# supervisor-early-finish-fix Planning Document

> **Summary**: 수집 워커가 빈 결과를 냈을 때 supervisor가 "데이터 없음"으로 오판해 조기 FINISH하는 것을 막는다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 미지정
> **Author**: 배상규
> **Date**: 2026-09-16
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 수집 워커가 성공(HTTP 200)했지만 결과가 비어 있을 때, supervisor가 이를 "데이터 자체가 없음"으로 단정하고 남은 수단을 시도하지 않은 채 FINISH한다. 워커가 자기 도구 범위를 에이전트 전체 능력으로 착각해 "그 기능은 제공되지 않습니다"라고 단언하는 것도 이 오판을 부추긴다. |
| **Solution** | (D) 워커의 에이전트 전체 능력 부정 발언을 규범으로 금지하고, (C) "수집 성공 + 결과 비었음"을 결정적 신호로 뽑아 supervisor 결정 프롬프트에 알린 뒤, 미해소 상태의 첫 FINISH 시도를 1회 되돌린다. |
| **Function/UX Effect** | 조작(검색 실행·필터 적용) 후에만 데이터가 나오는 페이지에서 사용자가 빈손 답변 대신 실제 데이터를 받는다. 워커의 잘못된 "불가" 선언이 최종 답변에 새지 않는다. |
| **Core Value** | 에이전트가 "못 찾았다"와 "아직 안 해봤다"를 구분한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 빈 결과를 데이터 부재로 오판해 남은 워커를 시도하지 않고 종료한다 (트레이스 `01a0a82b` 실증) |
| **WHO** | P2 — KB 운영자/에이전트 소유자. 자연어로 수집 지침을 등록하고 결과를 신뢰해야 하는 사용자 |
| **RISK** | 빈 결과 오탐으로 정상적인 "0건" 응답까지 되물어 지연·토큰이 늘어난다 |
| **SUCCESS** | 재현 시나리오에서 FINISH 1회 차단이 발생하고 후속 워커가 실행된다. 빈 결과 신호가 없으면 결정 프롬프트가 기존과 바이트 동일 |
| **SCOPE** | D(워커 규범 1건) + C(빈 결과 신호·블록·1회 되물음). 위키 절차 체크리스트(A)는 후속 피처 |

---

## 1. Overview

### 1.1 Purpose

수집 워커의 산출이 비어 있을 때 supervisor가 **남은 수단을 시도하지 않고 종료하는 경로를 차단**한다. "수집이 실패했다"와 "수집은 됐는데 내용이 없다"는 서로 다른 상태인데, 현재 시스템은 후자를 인지하지 못한다.

### 1.2 Background

LangSmith 트레이스 `01a0a82b-77db-7ea2-85a2-2aad1548f371` (2026-09-16 12:03) 분석 결과:

1. supervisor가 `scrape_url` 워커로 `fsb.or.kr/ratedepo_0100.act`를 수집 → HTTP 200, 본문에 "등록된 데이터가 없습니다"
2. 해당 페이지는 **검색 버튼을 눌러야 표가 채워지는** 구조라, 클릭 전 스크래핑은 원래 비어 있는 게 정상
3. supervisor 3번째 결정: *"결과상 '등록된 데이터가 없습니다'라서 저축은행별 금리 표 데이터 자체가 없는 상태임이 확인된다. 추가로 다른 워커(브라우저 조작 등)를 써도 같은 조회일·조건에서는 표를 얻을 수 없으므로"* → `FINISH`
4. 실제로는 `available_workers`에 `browser_open/snapshot/click/extract`가 모두 있었고, 같은 페이지를 클릭까지 조작한 다른 런(`01a08b28`)은 정상적으로 표를 가져왔다

두 가지 시스템 결함이 겹쳤다.

**결함 1 (D) — 워커의 능력 부정이 컨텍스트를 오염시킨다.**
`wiki_read_worker`는 `wiki_read` 도구 하나만 바인딩된다 (`worker_skeleton_builder.py:86` — 도구 1개 = 워커 1개). 그런데 이 워커가 다음과 같이 답했고, 이 AIMessage가 supervisor 최종 결정 컨텍스트에 그대로 남았다:

> "지금 이 환경에서는 실제로 브라우저를 열어 fsb.or.kr 사이트에 접속하거나, 검색 버튼을 누르거나, HTML을 실시간으로 스크래핑하는 기능이 제공되지 않습니다."

워커가 자기 도구 범위를 **에이전트 전체 능력으로 착각**해 사실과 다른 단언을 했다.

**결함 2 (C) — 빈 결과가 실패 신호로 잡히지 않는다.**
`_render_worker_error_block` (`supervisor_nodes.py:64`)은 `state["last_worker_error"]`가 있을 때만 "[직전 수집 실패]" 블록을 렌더한다. 이 신호는 `ToolErrorPolicy`가 도구 예외·오류 접두어에서 뽑는다. 이번 케이스는 도구가 정상 성공했으므로 신호가 서지 않았고, 재시도를 유도할 어떤 블록도 뜨지 않았다.

### 1.3 Related Documents

- 선행 설계: `wiki-guided-routing` (D3 지침 우선 블록 / D4 직전 실패 블록) — 본 피처는 D4의 사각지대를 메운다
- 선행 설계: `worker-context-injection` §4.1 — 워커 컨텍스트 블록 규범이 확장 지점
- 근거 트레이스: LangSmith `01a0a82b-77db-7ea2-85a2-2aad1548f371` (실패), `01a08b28-a8d2-76e1-b3a8-9cef0d67e8d5` (정상 대조군)
- 후속 피처: `wiki-procedure-completion` (A — 위키 절차 완주 체크리스트)

---

## 2. Scope

### 2.1 In Scope

- [ ] (D) 워커 컨텍스트 블록의 `[도구 사용 규범]`에 "에이전트 전체 능력 부정 금지" 규범 1건 추가
- [ ] (C) `EmptyResultPolicy` 도메인 정책 신설 — 수집 워커 산출의 빈 결과 판정
- [ ] (C) `SupervisorState`에 빈 결과 신호 필드 추가 (`last_worker_error`와 동형: 워커가 세팅, supervisor가 소비 후 리셋)
- [ ] (C) supervisor 결정 프롬프트에 "[수집 결과 비어 있음]" 블록 렌더
- [ ] (C) 빈 결과 미해소 상태의 첫 FINISH 시도를 1회 되돌리는 게이트
- [ ] 빈 결과 판정 패턴을 설정값으로 외부화 (코어 하드코딩 금지)
- [ ] 회귀 보호: 빈 결과 신호가 없으면 결정 프롬프트 바이트 동일

### 2.2 Out of Scope

- 위키 지침의 다단계 절차를 체크리스트로 승격하는 것 → 후속 피처 `wiki-procedure-completion`
- supervisor 자체 계획(위키와 무관하게 스스로 세운 다음 단계) 추적 → 범위 밖 (질의 결과 "위키 지침 절차만")
- 브라우저 도구군(`browser_open/snapshot/click/extract`)을 한 워커로 번들링 → 별건 구조 개선, 별도 PDCA
- MCP 도구 description 수정 (`scrape_url`의 상호작용 불가 명시) → 데이터 변경이라 코드 피처 밖
- `quality_gate_enabled` 기본값 변경
- 위키 문서 본문 수정

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | (D) `_TOOL_USAGE_NORM`에 규범 추가: 워커는 자기 도구로 못 하는 일을 "이 워커의 범위 밖"으로만 기술하고, 에이전트 전체가 불가능하다고 단언하지 않는다 | High | Pending |
| FR-02 | (C) `EmptyResultPolicy` 신설. 1차로 구조적 신호(유효 데이터 부재 — 표 행 0, 본문 대비 데이터 비율), 2차 보조로 설정된 문구 패턴으로 빈 결과를 판정한다 | High | Pending |
| FR-03 | (C) 빈 결과 판정 문구 패턴을 `config`로 외부화한다. 도메인 정책과 코어 코드에 한국어 문자열을 상수로 박지 않는다 | High | Pending |
| FR-04 | (C) `SupervisorState`에 빈 결과 신호 필드를 추가한다. 수집 워커 노드가 매번 덮어쓰고(정상이면 빈 값), supervisor가 블록 렌더 후 리셋한다 | High | Pending |
| FR-05 | (C) supervisor 결정 프롬프트에 "[수집 결과 비어 있음]" 블록을 렌더한다. 내용: 수집은 성공했으나 결과가 비었음 / 조작 후에만 데이터를 렌더하는 페이지일 수 있음 / 상호작용 가능한 워커가 남아 있으면 FINISH 전에 시도 | High | Pending |
| FR-06 | (C) 빈 결과가 미해소인 상태에서 FINISH를 선택하면 **1회에 한해** 되돌려 supervisor 재결정을 유도한다. 두 번째 FINISH는 허용한다 | High | Pending |
| FR-07 | (C) 되물음 횟수를 state에 보관해 1회 상한을 결정적으로 보장한다. `max_iterations`·`token_limit` 가드보다 후순위로 평가해 한도 도달 시 되물음이 종료를 막지 않는다 | High | Pending |
| FR-08 | 빈 결과 신호가 없고 D 규범만 추가된 경우, supervisor 결정 프롬프트는 기존과 바이트 동일하다 | High | Pending |
| FR-09 | 되물음이 발동한 사실과 그 사유를 구조화 로그로 남긴다 (`logger.info`, request_id 포함) | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 비용 | 빈 결과 판정에 추가 LLM 호출 0회 (결정적 판정만) | 코드 리뷰 + 트레이스의 LLM 런 수 대조 |
| 토큰 | 추가 블록은 발동 시에만 렌더, 400자 이내 | 상수 길이 단위 테스트 |
| 회귀 | 기존 supervisor·prompt_rendering 테스트 전량 통과 | `pytest tests/application/agent_builder tests/application/agent_run` |
| 안전성 | 되물음으로 인한 무한 루프 불가 (상한 1회, 결정적) | 되물음 2회차 허용 단위 테스트 |
| 아키텍처 | domain → infrastructure 참조 없음, 정책은 domain에 위치 | `/verify-architecture` |
| 로깅 | print() 미사용, 구조화 로거 사용 | `/verify-logging` |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-09 구현 완료
- [ ] TDD 준수: 각 FR마다 실패하는 테스트 선작성 → 구현 → 통과
- [ ] 재현 시나리오 테스트: 수집 워커가 "빈 결과"를 반환한 state에서 supervisor가 FINISH를 선택하면 1회 되돌려지고, 두 번째 FINISH는 통과한다
- [ ] D 규범 추가 후 워커 컨텍스트 블록 스냅샷 테스트 갱신
- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과
- [ ] 코드 리뷰 완료

### 4.2 Quality Criteria

- [ ] 함수 길이 40줄 이내, if 중첩 2단계 이내 (CLAUDE.md §3)
- [ ] 신규 모듈에 대응 테스트 파일 존재
- [ ] lint 오류 0
- [ ] 위키 미등록 에이전트의 결정 프롬프트 바이트 동일 회귀 테스트 통과

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 빈 결과 **오탐** — 정상적인 "검색 결과 0건"을 미실행으로 오판해 불필요한 워커를 부른다 | Medium | Medium | 되물음 상한 1회로 비용을 구조적으로 제한. 블록 문구를 "시도하라"가 아닌 "남아 있으면 고려하라"로 조건부 서술 |
| 빈 결과 **미탐** — 사이트마다 빈 표현이 달라 판정이 빗나간다 | Medium | Medium | 1차 판정을 문자열이 아닌 구조적 신호로 두고, 패턴은 설정값이라 배포 없이 추가 가능 |
| 되물음이 `max_iterations` 도달 상황과 충돌해 종료를 막는다 | High | Low | FR-07 — 한도 가드를 되물음보다 먼저 평가. 한도 도달 시 되물음 미발동 단위 테스트 |
| D 규범 추가가 다른 워커의 정상적인 "확인되지 않습니다" 응답을 억제한다 | Medium | Low | 규범 문구를 "도구 결과에 없는 내용은 확인되지 않는다고 답하라"(기존 사용자 컨텍스트 규범)와 충돌하지 않게 작성. 부정 대상은 '에이전트 전체 능력'으로 한정 |
| 신규 state 필드가 기존 그래프 컴파일·체크포인트와 충돌 | Medium | Low | `last_worker_error`와 동일한 형태·수명주기로 추가해 선례를 따름 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/application/agent_run/prompt_rendering.py` · `_TOOL_USAGE_NORM` | Prompt 상수 | (D) 능력 부정 금지 규범 1건 추가 |
| `src/domain/agent_builder/policies.py` · `EmptyResultPolicy` | Domain Policy | (C) 신설 — 빈 결과 판정. `ToolErrorPolicy` 형태를 따름 |
| `src/config.py` | Config | (C) 빈 결과 문구 패턴 설정값 추가 |
| `src/application/agent_builder/supervisor_state.py` · `SupervisorState` | State 스키마 | (C) 빈 결과 신호 필드 + 되물음 횟수 필드 추가 |
| `src/application/agent_builder/supervisor_nodes.py` | Graph Node | (C) 빈 결과 블록 렌더 함수 추가, 결정 프롬프트 조립부에 삽입, FINISH 되물음 게이트 |
| `src/application/agent_builder/workflow_compiler.py` | Graph Compiler | (C) 수집 워커 노드가 빈 결과 신호를 세팅하도록 배선 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `_TOOL_USAGE_NORM` | READ | `render_worker_context_block` → `workflow_compiler.py:580` (search/collect 워커) | Needs verification — 모든 도구 워커 프롬프트가 길어짐 |
| `_TOOL_USAGE_NORM` | READ | `render_worker_context_block` → `workflow_compiler.py:635` (wiki 워커) | Needs verification — 본 결함의 직접 대상 |
| `_TOOL_USAGE_NORM` | READ | `render_worker_context_block` → `workflow_compiler.py:650`대 (미분류 react 워커) | Needs verification |
| `_TOOL_USAGE_NORM` | READ | `tests/application/agent_run/test_prompt_rendering.py` | Breaking — 스냅샷/포함 단언 갱신 필요 |
| `SupervisorState` | READ/WRITE | `supervisor_nodes.py` (supervisor / quality_gate / route 함수 전부) | None — 필드 추가는 TypedDict 하위호환 |
| `SupervisorState` | READ/WRITE | `workflow_compiler.py` 워커 래퍼 (`_wrap_worker`) | Needs verification — 신호 세팅 지점 추가 |
| `SupervisorState` | READ | `run_agent_use_case.py` (payload 구성) | Needs verification — 신규 필드 누출 여부 확인 |
| 결정 프롬프트 조립부 (`supervisor_nodes.py:300-310`) | READ | `tests/application/agent_builder/test_*` 다수 | Needs verification — 바이트 동일 회귀 테스트 존재 여부 확인 |
| `route_to_worker_or_final` | READ | `workflow_compiler.py` 그래프 엣지 등록 | Needs verification — 되물음을 여기에 둘지 supervisor 노드에 둘지는 Design에서 결정 |

### 6.3 Verification

- [ ] 위 소비자 전부가 변경 후 정상 동작함을 테스트로 확인
- [ ] 권한·인증 경로 변경 없음 확인
- [ ] state 필드 추가가 기존 체크포인트 직렬화를 깨지 않음 확인
- [ ] 위키 미등록 에이전트의 결정 프롬프트가 기존과 동일함 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 구조 | 정적 사이트 | ☐ |
| **Dynamic** | 기능 모듈 + BaaS | 웹앱, SaaS MVP | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DI | 복잡한 아키텍처 | ☑ |

기존 프로젝트가 Thin DDD (domain / application / infrastructure / interfaces) 이므로 그대로 따른다.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 빈 결과 판정 위치 | domain policy / application / infrastructure | **domain policy** | `ToolErrorPolicy` 선례. 외부 라이브러리 타입 비참조, duck typing |
| 판정 방식 | 구조적 신호 / 문자열 패턴 / LLM 판정 | **구조적 신호 1차 + 패턴 2차** | 사용자 선택. LLM 호출 0회 유지, 한국어 문자열의 코어 하드코딩 회피 |
| 패턴 보관 위치 | 코어 상수 / config / DB | **config** | CLAUDE.md §3 "config 값 하드코딩 금지" + "특화는 데이터로" |
| FINISH 차단 강도 | 프롬프트 지시 / 결정적 차단 / 1회 되물음 | **1회 되물음** | 사용자 선택. 기존 "강제 아님" 철학과 결정적 보장의 절충, 무한루프 불가 |
| 신호 전달 채널 | state 필드 / 메시지 삽입 | **state 필드** | `last_worker_error` 동형. 메시지 삽입은 컨텍스트 오염 재발 위험 |
| 되물음 구현 지점 | supervisor 노드 / route 함수 | **Design에서 결정** | route 함수는 순수 함수라 state 쓰기가 어려움 — 설계 단계에서 3안 비교 |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

변경 위치:
┌─────────────────────────────────────────────────────┐
│ domain/agent_builder/policies.py                    │
│   └ EmptyResultPolicy (신설, 규칙만)                │
├─────────────────────────────────────────────────────┤
│ application/agent_builder/                          │
│   ├ supervisor_state.py   (신호 필드 추가)          │
│   ├ supervisor_nodes.py   (블록 렌더 + 되물음 게이트)│
│   └ workflow_compiler.py  (워커 → 신호 배선)        │
│ application/agent_run/                              │
│   └ prompt_rendering.py   (D 규범 1건)              │
├─────────────────────────────────────────────────────┤
│ config.py                 (빈 결과 패턴 설정값)      │
└─────────────────────────────────────────────────────┘
infrastructure/ 변경 없음 · interfaces/ 변경 없음
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md`에 코딩 규칙 존재 (루트 + `idt/`)
- [x] `idt/docs/rules/` 세부 규칙 존재 (logging, testing, db-session, tool-and-mcp)
- [x] `docs/wiki/_INDEX.md` 개발 위키 존재 — 작업 착수 전 관련 문서 참조 필수
- [ ] `CONVENTIONS.md` 루트 파일 (미존재, 불필요)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Design Ref 주석** | exists | 신규 코드에 `# Design Ref: supervisor-early-finish-fix §N` 부착 | High |
| **Plan SC 주석** | exists | 핵심 로직에 `# Plan SC: FR-0N` 부착 | High |
| **정책 클래스 네이밍** | exists (`ToolErrorPolicy`) | `EmptyResultPolicy` — 동일 컨벤션 | High |
| **state 필드 주석** | exists | 필드마다 설계 출처·수명주기 주석 (기존 `last_worker_error` 형식) | Medium |
| **설정값 네이밍** | exists | `src/config.py` 기존 네이밍 확인 후 맞춤 | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| (빈 결과 패턴 설정) | 빈 결과 판정 보조 문구 목록 | Server | ☑ — 환경변수로 뺄지 config 기본값으로 둘지는 Design에서 결정 |

신규 외부 서비스·시크릿 없음.

### 8.4 Pipeline Integration

해당 없음 (기존 시스템 결함 수정, 9-phase 파이프라인 신규 진입 아님).

---

## 9. Next Steps

1. [ ] `/pdca design supervisor-early-finish-fix` — 3가지 설계안 비교 (특히 되물음 구현 지점: supervisor 노드 내부 / route 함수 / 별도 게이트 노드)
2. [ ] 개발 위키 `docs/wiki/_INDEX.md`에서 supervisor 그래프 계약 문서 확인
3. [ ] TDD 구현 (`/pdca do`)
4. [ ] Gap 분석 (`/pdca analyze`)
5. [ ] 후속 피처 `wiki-procedure-completion` (A) 착수 — 본 피처의 되물음 메커니즘에 의존

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-16 | 최초 작성. 트레이스 `01a0a82b` 분석 기반, D+C 범위 확정 | 배상규 |
