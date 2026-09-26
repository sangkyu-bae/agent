# worker-capability-denial-guard Planning Document

> **Summary**: 워커가 "어떤 도구로도 조회할 수 없다"고 에이전트 전체 능력을 부정하면, supervisor가 그 주장을 검증 없이 수용해 조기 FINISH하는 경로를 막는다.
>
> **Project**: sangplusbot (idt 백엔드)
> **Version**: 미지정
> **Author**: 배상규
> **Date**: 2026-09-25
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | `list_inquiries` 워커가 사용자의 부수 질문("각각 본문을 읽을 수 있나요?")에 자기 도구 범위만 보고 "본문은 어떤 도구로도 조회할 수 없도록 제한되어 있다"고 답했다. 같은 에이전트에 `get_inquiry`(본문 조회) 워커가 등록돼 있고 supervisor도 첫 결정에서 이를 인지했지만, 워커의 '불가' 주장이 컨텍스트에 남자 supervisor는 자기 워커 목록 대신 그 주장을 채택해 FINISH했다. |
| **Solution** | (A) 워커 규범: 워커는 `[현재 작업]`만 수행하고 에이전트 능력·범위에 관한 질문에는 답하지 않는다. (B) supervisor 결정적 신호: 워커 산출에서 능력 부정 문구를 설정 패턴으로 감지해 "[워커 능력 부정 감지] 능력 판단은 사용 가능한 워커 목록으로만" 블록을 렌더하고, 미해소 상태의 첫 FINISH를 1회 되돌린다(기존 되물음 게이트 재사용). |
| **Function/UX Effect** | 사용자가 "본문을 읽을 수 있나요?"라고 물으면 에이전트가 "네, 문의 번호를 지정하면 본문을 조회할 수 있습니다"처럼 실제 능력에 맞게 답한다. 워커의 잘못된 '불가' 선언이 최종 답변에 새지 않는다. 추가 LLM 호출 없음. |
| **Core Value** | 에이전트의 능력은 워커 한 명의 시야가 아니라 **등록된 워커 목록**이 결정한다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 워커의 능력 부정 발언을 supervisor가 진실로 채택해 가능한 작업을 "불가"로 종료한다 (로컬 런 `031564e4`, `aff5935c` 실증) |
| **WHO** | P2 — KB 운영자/에이전트 소유자. 도구를 여러 개 등록한 에이전트가 등록한 만큼의 능력을 발휘하기를 기대하는 사용자 |
| **RISK** | 패턴 오탐으로 정당한 "확인되지 않았습니다" 답변까지 되물어 지연·토큰이 늘어난다 |
| **SUCCESS** | 재현 시나리오에서 능력 부정 블록이 렌더되고 첫 FINISH가 1회 되돌려진다. 신호가 없으면 결정 프롬프트가 기존과 바이트 동일. 워커 규범 추가 후 워커가 task 밖 능력 질문에 답하지 않는다 |
| **SCOPE** | A(워커 규범 1건) + B(능력 부정 신호·블록·기존 1회 되물음 게이트 재사용·패턴 config 외부화). 데이터 수정(MCP description·에이전트 프롬프트)은 권고만 |

---

## 1. Overview

### 1.1 Purpose

워커가 자기 도구 범위를 **에이전트 전체 능력으로 착각한 '불가' 선언**을 했을 때, supervisor가 그 선언을 검증 없이 최종 답변의 근거로 삼는 경로를 차단한다. "이 워커가 못 한다"와 "이 에이전트가 못 한다"는 다른 상태인데, 현재 시스템은 후자를 워커의 말로 판정한다.

### 1.2 Background

로컬 DB 실행 이력(`ai_run` `031564e4-281a-45b7-9b2a-13ba6b9a48ac`, 2026-09-25 08:35, 에이전트 `e557f77e…` "상상인플러스저축은행의 문의 글을 확인하고 어떤 문제들이 있었는지 분석하는 에이전트") 분석 결과:

1. 사용자 질문: "답변이 안 된 문의 글을 확인해서 뭐뭐가 있는지 알려주실래요? 그리고 **각각 본문을 읽을 수 있나요?**"
2. supervisor 1단계 reasoning: *"각각 본문을 읽을 수 있는지는 목록 조회 후 개별 건에 대해 **get_inquiry 사용 가능 여부를 설명**하면 됩니다"* → `list_inquiries_worker` 호출 (task 필드에 목록 조회만 지시)
3. `list_inquiries_worker`(react 워커, 미분류 카테고리)는 대화 전문 + `[현재 작업]`을 받는다. 도구를 1회 호출해 48건을 정상 반환한 뒤, **task 밖인 두 번째 질문에 스스로 답했다**:
   > "제가 접근할 수 있는 정보는 목록 수준까지만입니다. 문의 글의 상세 본문 내용은 **어떤 도구로도 조회할 수 없도록 제한**되어 있습니다. → 본문 전체를 읽어서 요약해 드리는 것은 제 권한/범위 밖입니다."
4. supervisor 4단계 reasoning: *"새로운 목록 조회나 개별 문의 조회 요청이 없으므로 추가 워커 호출 없이, 내가 어떤 정보까지 볼 수 있고(목록 수준), **본문은 볼 수 없다는 점을 다시 한 번 정리**해 주면 충분하다"* → `FINISH`
5. `final_answer` 노드가 워커 주장을 그대로 종합해 사용자에게 "본문은 어떤 워커로도 조회할 수 없도록 제한되어 있다"고 안내했다.

실제로 이 에이전트의 `agent_tool`에는 `get_inquiry`("문의 한 건의 본문과 기존 답변을 조회합니다")가 등록돼 있고, supervisor의 `사용 가능한 워커` 목록에도 포함돼 있었다.

세 가지 결함이 겹쳤다.

**결함 1 (A) — 워커가 task 밖 질문에 답한다.**
`_build_worker_input`(`workflow_compiler.py:285`)은 대화 전문에 `[현재 작업]`을 덧붙인다. 워커는 task를 수행한 뒤 대화에 남은 다른 질문(에이전트 능력 질문)에도 답했다. 기존 `_TOOL_USAGE_NORM`(`prompt_rendering.py:75`)의 "에이전트 전체가 그 기능을 갖고 있지 않다고 단정하지 마세요" 규범은 있었으나, 워커가 참조한 도구 description 자체에 *"원문은 어떤 도구로도 볼 수 없습니다"*(연락처 마스킹 설명)라는 문구가 있어 규범이 description에 밀렸다. 규범은 "단정하지 말라"만 있고 **"능력 질문에는 답하지 말라"**가 없다.

**결함 2 (B) — 능력 부정이 결정적 신호로 잡히지 않는다.**
`supervisor-early-finish-fix`가 만든 되물음 게이트(`route_to_worker_or_final`, `finish_challenge_pending`)는 `last_worker_empty`(빈 결과)에만 반응한다. 이번 산출은 48건 정상 데이터라 `EmptyResultPolicy`가 신호를 세우지 않았고, `ToolErrorPolicy`도 오류가 아니므로 침묵했다. 워커 산출의 **'불가' 주장**을 잡는 정책은 없다.

**결함 3 (데이터) — 도구 description·에이전트 프롬프트의 "원문"이 모호하다.**
`list_inquiries` description: "고객 연락처는 마스킹되어 있습니다 … **원문은 어떤 도구로도 볼 수 없습니다**". 에이전트 Tool Guidelines: "조회 시 고객의 개인정보는 마스킹되어 있으므로 **원문을 확인할 수 없다**". 둘 다 연락처 원문을 뜻하지만 워커 LLM은 문의 본문으로 읽었다. 코드 밖(MCP 저장소·DB 데이터)이라 본 피처 범위 밖이며 §2.2에 권고로 남긴다.

### 1.3 Related Documents

- 선행 설계: `supervisor-early-finish-fix` — 되물음 게이트(D-05)·상태 필드 수명주기(D-02)·패턴 config 외부화(D-07)를 본 피처가 그대로 재사용한다
- 선행 설계: `worker-context-injection` §4.1 — 워커 컨텍스트 블록·`_TOOL_USAGE_NORM`이 A의 확장 지점
- 선행 설계: `wiki-guided-routing` D4 — `last_worker_error` 신호 채널의 원형
- 근거 트레이스: 로컬 `ai_run` `031564e4-281a-45b7-9b2a-13ba6b9a48ac`(실패), `aff5935c-cccc-4e0e-b76b-196ed4ea7a08`(동일 패턴, 08:31)
- 대상 에이전트/도구: `agent_definition` `e557f77e-9209-4a1a-a4b2-ed937176c757`, MCP `Customer Inquiry MCP`(`6ea2f615…`, localhost:8007) — `list_inquiries` / `get_inquiry` / `submit_reply`(승인 필요)

---

## 2. Scope

### 2.1 In Scope

- [ ] (A) `_TOOL_USAGE_NORM`에 규범 추가: 워커는 `[현재 작업]`에 적힌 일만 수행하고, 에이전트가 무엇을 할 수 있는지·다른 정보를 볼 수 있는지 묻는 질문에는 답하지 않는다 (판단은 상위 노드 책임)
- [ ] (B) `CapabilityDenialPolicy` 도메인 정책 신설 — 워커 산출의 능력 부정 문구 판정. `EmptyResultPolicy`와 동형(문자열만 입력, 사유 요약만 출력, 원문 미포함)
- [ ] (B) 능력 부정 문구 패턴을 `config`로 외부화 (`empty_result_patterns` 선례)
- [ ] (B) `SupervisorState`에 능력 부정 신호 필드 추가 (`last_worker_empty` 동형: 워커 노드가 매번 덮어쓰고, supervisor가 소비 후 리셋)
- [ ] (B) 신호 배선: react 워커(`_wrap_worker`) 산출에 판정 적용. search/collect/action 노드는 Design에서 포함 여부 결정
- [ ] (B) supervisor 결정 프롬프트에 "[워커 능력 부정 감지]" 블록 렌더 — 워커의 불가 주장은 그 워커의 도구 범위일 뿐이며, 능력 판단은 `사용 가능한 워커` 목록으로만 한다. 해당 기능을 가진 워커가 있으면 호출하거나 사용자에게 가능함을 정확히 답하라
- [ ] (B) 능력 부정 미해소 상태의 첫 FINISH를 기존 `finish_challenge_pending` 게이트로 1회 되돌린다 (되물음 상한은 빈 결과와 **합산 1회** — 무한 루프 불가)
- [ ] (B) 블록 우선순위: 오류 블록 > 빈 결과 블록 > 능력 부정 블록 — 동시 렌더 금지(지시 충돌 방지)
- [ ] 되물음 발동 사실·사유 구조화 로그
- [ ] 회귀 보호: 신호가 없으면 supervisor 결정 프롬프트 바이트 동일
- [ ] 기대 동작(§3.1 FR-10)을 코드가 아닌 **블록 문구·config**로 표현해, 향후 "본문을 바로 읽어 보여줌" 모드로 바꿀 때 코드 구조 변경 없이 전환 가능하게 한다

### 2.2 Out of Scope

- 복합 질문에서 supervisor가 **능동적으로** `get_inquiry`를 N건 호출해 본문 요약까지 제공하는 동작 → 사용자 결정: 1차는 "가능함을 답하고 대상 확인"까지. 전환 지점은 §7.2에 명시
- MCP `list_inquiries` description 수정("**연락처** 원문은 어떤 도구로도 볼 수 없습니다"로 명확화) → 별도 저장소(`sangplus/mcp`) 데이터. **권고**: 본 피처와 무관하게 수정 권장
- 에이전트 프롬프트 Tool Guidelines 문구 수정("개인정보 원문") → DB 데이터. 프롬프트 컴포저가 생성한 문구라면 컴포저 개선은 별도 피처
- `final_answer` 노드에서 워커의 능력 주장을 필터링·중화 → 되물음으로 supervisor가 재결정하면 불필요. 필터는 정당한 "확인 불가" 안내까지 지울 위험
- LLM 판정기(보조 LLM으로 능력 부정 여부 판단) → 사용자 결정: 패턴 기반
- 워커 입력에서 대화 전문을 잘라 task만 넘기는 구조 변경 → 워커가 대화 근거(대상·기간)를 잃는다. 기존 `_build_worker_input` 계약 유지
- `_TOOL_USAGE_NORM` 외 다른 워커 지시 문자열 변경

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | (A) `_TOOL_USAGE_NORM`에 규범 추가: 워커는 `[현재 작업]`에 적힌 일만 수행한다. 대화에 있는 다른 질문, 특히 "~을 볼 수 있나요/할 수 있나요" 같은 에이전트 능력·범위 질문에는 답하지 않는다 — 그 판단은 상위 노드가 워커 목록으로 한다. 'A라고만 하라'류 절대 프레이밍 금지(early-finish-fix 실측 회귀 교훈), 도구 결과 전달 의무보다 뒤에 둔다 | High | Pending |
| FR-02 | (B) `CapabilityDenialPolicy.detect(body, patterns) -> str` 신설. 워커 산출 본문에 설정 패턴 중 하나가 포함되면 사유 요약(원문 미포함, 120자 이내)을, 아니면 `''`을 반환한다. str이 아니면 판정 생략 | High | Pending |
| FR-03 | (B) 패턴을 `config`(`capability_denial_patterns`, 콤마 구분 문자열)로 외부화한다. 기본값은 실측 문구 기반: "어떤 도구로도", "어떤 워커로도", "조회할 수 없도록 제한", "권한/범위 밖", "제 권한 밖", "제 범위 밖". `src/api/main.py`가 tuple로 정규화해 `WorkflowCompiler` 생성자에 kwarg 주입 — application/domain은 config를 직접 import하지 않는다 | High | Pending |
| FR-04 | (B) `SupervisorState`에 `last_worker_denial: str` 추가. 워커 노드가 매번 덮어쓰고(정상이면 `''`), supervisor가 블록 렌더 후 `''`로 리셋한다. 모든 종료 경로(한도·강제 라우팅·결정 실패·조기 return)에서 리셋한다 | High | Pending |
| FR-05 | (B) `_wrap_worker`(react 워커) 산출에 판정을 적용한다. `last_worker_error`가 있으면 판정을 건너뛴다(블록 충돌 방지). search/collect/action 함수 노드 포함 여부는 Design에서 결정하되, 포함 시 `_with_empty_signal`과 같은 등록 지점에서 한 번에 덮는다 | High | Pending |
| FR-06 | (B) supervisor 결정 프롬프트에 "[워커 능력 부정 감지]" 블록을 렌더한다. 내용: 직전 워커가 자기 도구 범위를 근거로 불가를 선언했다 / 워커는 자기 도구 하나만 안다 / 에이전트 능력 판단은 위 `사용 가능한 워커` 목록으로만 한다 / 해당 기능을 가진 워커가 있으면 FINISH 대신 그 워커를 호출하거나, 사용자 질문이 능력 확인이면 가능함과 필요한 입력(예: 문의 번호)을 answer에 정확히 적어라 / 목록에도 없으면 FINISH하고 무엇이 불가한지 밝혀라. 워커·도구 이름을 나열하지 않는다(그래프 계약 ② 목록 프레이밍 금지) | High | Pending |
| FR-07 | (B) 블록 배타: `error_block`이 있으면 빈 결과·능력 부정 블록 모두 생략, `empty_block`이 있으면 능력 부정 블록 생략. 한 결정에 안내 블록은 최대 1개 | High | Pending |
| FR-08 | (B) 능력 부정 블록이 렌더된 결정에서 FINISH를 선택하면 기존 `finish_challenge_pending`으로 1회 되돌린다. `finish_challenge_pending = bool(empty_block or denial_block)`. 되물음 상한 1회는 두 신호 합산이며, `limit_reached`·`approval_pending`이 우선한다(기존 route 순서 유지) | High | Pending |
| FR-09 | 신호가 없으면(`last_worker_denial == ''`) supervisor 결정 프롬프트는 기존과 바이트 동일하다. FR-01 규범 추가로 워커 프롬프트만 바뀐다 | High | Pending |
| FR-10 | 기대 동작(1차): 복합 질문 "목록 + 본문 읽을 수 있나요?"에서 되물음 후 supervisor가 (i) `get_inquiry` 워커를 호출하거나 (ii) FINISH하되 answer/최종 답변에 "본문 조회가 가능하며 문의 번호를 지정해 달라"를 담는다. 둘 중 어느 쪽이든 "본문은 어떤 도구로도 볼 수 없다"는 문장이 최종 답변에 나가지 않는다. 향후 (i)를 기본으로 바꾸려면 FR-06 블록 문구만 조정한다 | High | Pending |
| FR-11 | 되물음 발동 시 `logger.info`로 사유·request_id·워커 id를 구조화 기록한다 (early-finish-fix FR-09 carry item과 같은 형식) | Medium | Pending |
| FR-12 | `ai_run_step`의 supervisor `output_summary`(reasoning)에서 되물음 후 재결정이 추적되도록 기존 `_step_output_summary` 경로를 유지한다 (추가 작업 없음, 검증만) | Low | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 비용 | 능력 부정 판정에 추가 LLM 호출 0회. 되물음 발동 시 supervisor 결정 1회 추가 상한 | 코드 리뷰 + `ai_llm_call` 건수 대조 |
| 토큰 | 능력 부정 블록은 발동 시에만 렌더, 400자 이내. 워커 규범 추가분 150자 이내 | 상수 길이 단위 테스트 |
| 회귀 | `tests/application/agent_builder`, `tests/application/agent_run` 기존 테스트 전량 통과(master 상시 실패 목록 제외) | `uv run python -m pytest` |
| 안전성 | 되물음 무한 루프 불가 — 빈 결과와 합산 1회, 한도 가드 우선 | 되물음 2회차 허용·한도 우선 단위 테스트 |
| 과탐 통제 | 패턴은 짧은 상위 문자열("할 수 없습니다")을 넣지 않는다. 오탐 시 비용은 되물음 1회로 상한 | config 주석 + 오탐 시나리오 테스트(정당한 "확인되지 않았습니다" 답변은 미발동) |
| 아키텍처 | domain → infrastructure 참조 없음, 정책은 domain, config는 kwarg 주입 | `/verify-architecture` |
| 로깅 | print() 미사용, 구조화 로거 | `/verify-logging` |
| 외부 콘텐츠 안전 | 사유 요약에 워커 산출 원문을 담지 않는다(고객 문의 본문의 지시문 승격 방지) | 정책 단위 테스트 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01 ~ FR-12 구현 완료
- [ ] TDD 준수: 각 FR마다 실패하는 테스트 선작성 → 구현 → 통과
- [ ] 재현 단위 시나리오: 워커 AIMessage가 "본문은 어떤 도구로도 조회할 수 없도록 제한되어 있습니다"를 포함한 state에서 supervisor가 FINISH를 선택하면 1회 되돌려지고, 재결정 프롬프트에 능력 부정 블록이 있으며, 두 번째 FINISH는 통과한다
- [ ] 오탐 시나리오: 워커가 "요청하신 2023년 데이터는 도구 결과에서 확인되지 않았습니다"라고 답한 state에서는 신호가 서지 않는다
- [ ] 실런 재현(L3, 선택): 로컬 MCP 8007 대상 에이전트 `e557f77e…`에 동일 질문을 `persist_conversation: false`로 실행해, `ai_run_step` supervisor reasoning에 되물음 후 재결정이 남고 최종 답변에 "어떤 도구로도 볼 수 없다"가 없음을 확인. `list_inquiries`/`get_inquiry`는 읽기 전용이라 부작용 없음 (`submit_reply`는 승인 게이트)
- [ ] `_TOOL_USAGE_NORM` 스냅샷/포함 단언 테스트 갱신
- [ ] `/verify-architecture`, `/verify-logging`, `/verify-tdd` 통과
- [ ] 코드 리뷰 완료

### 4.2 Quality Criteria

- [ ] 함수 길이 40줄 이내, if 중첩 2단계 이내 (CLAUDE.md §3). `supervisor_node`는 이미 145줄(early-finish-fix carry item) — 블록 렌더는 별도 함수로 분리하고 본문 길이를 늘리지 않는다
- [ ] 신규 모듈·정책에 대응 테스트 파일 존재
- [ ] lint 오류 0
- [ ] 신호 없는 에이전트의 결정 프롬프트 바이트 동일 회귀 테스트 통과

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| 패턴 **오탐** — 워커의 정당한 "이 워커의 범위 밖" 표기(early-finish-fix가 권장한 문구)까지 잡는다 | Medium | High | 기본 패턴에서 "이 워커의 범위 밖"을 **제외**한다. 잡는 대상은 '어떤 도구로도/어떤 워커로도/조회할 수 없도록 제한/제 권한·범위 밖'처럼 에이전트 전체 또는 화자 권한을 부정하는 문구로 한정. 오탐 비용은 되물음 1회 |
| 패턴 **미탐** — 표현이 달라 신호가 안 선다 | Medium | Medium | A 규범이 1차 방어(질문에 답하지 않음). 패턴은 config라 배포 없이 추가. 실런 트레이스로 표현 수집 |
| 되물음 후 supervisor가 같은 결정을 반복해 사용자 체감 개선이 없다 | High | Medium | 블록에 "능력 판단은 워커 목록으로만" + "가능함과 필요한 입력을 answer에 적어라"를 명시. 실런(L3)으로 확인. 개선 없으면 Design에서 블록 문구 강화 |
| A 규범이 워커의 정상적인 "도구 결과에 없는 내용은 확인되지 않았다" 답변을 억제한다 | Medium | Low | 규범 대상을 '에이전트 능력·범위 질문'으로 한정하고, 기존 "무엇이 확인되지 않았는지 밝히세요" 규범과 나란히 둔다. early-finish-fix 실측 회귀(절대 프레이밍 → 도구 결과 전달 생략) 재발 방지 문구 검토 |
| 빈 결과·능력 부정 신호가 같은 턴에 동시에 서면 지시가 충돌한다 | Medium | Low | FR-07 배타 순서. `finish_challenge_pending`은 하나의 플래그로 합산 1회 |
| 되물음이 `max_iterations`·승인 대기와 충돌해 종료를 막는다 | High | Low | 기존 route 순서 유지(approval > limit > challenge). 단위 테스트로 고정 |
| 신규 state 필드가 기존 체크포인트·payload에 누출 | Low | Low | `last_worker_empty`와 동일 형태·수명주기. `run_agent_use_case.py` payload 구성 확인 |
| 데이터 결함(§1.2 결함 3)이 남아 워커가 계속 오독한다 | Medium | High | 본 피처는 오독이 있어도 최종 답변이 오염되지 않게 하는 것이 목표. description 수정은 §2.2 권고로 별도 진행 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `src/application/agent_run/prompt_rendering.py` · `_TOOL_USAGE_NORM` | Prompt 상수 | (A) task 외 능력 질문 무응답 규범 1건 추가 |
| `src/domain/agent_builder/policies.py` · `CapabilityDenialPolicy` | Domain Policy | (B) 신설 — 능력 부정 문구 판정. `EmptyResultPolicy` 형태를 따름 |
| `src/config.py` · `capability_denial_patterns` | Config | (B) 패턴 설정값 추가 |
| `src/api/main.py` | Composition Root | (B) config → tuple 정규화 → `WorkflowCompiler(capability_denial_patterns=)` 주입 |
| `src/application/agent_builder/supervisor_state.py` · `SupervisorState` | State 스키마 | (B) `last_worker_denial: str` 추가 |
| `src/application/agent_builder/supervisor_nodes.py` | Graph Node | (B) `_render_capability_denial_block` 추가, 결정 프롬프트 조립부 삽입, 블록 배타, 모든 종료 경로 리셋, `finish_challenge_pending` 합산 |
| `src/application/agent_builder/workflow_compiler.py` | Graph Compiler | (B) 생성자 kwarg 추가, `_wrap_worker`(및 Design 결정에 따라 함수 노드) 산출에 판정 배선 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `_TOOL_USAGE_NORM` | READ | `render_worker_context_block` → `workflow_compiler.py:720`(react/action/search/collect 워커), `:600`(생성기 노드), wiki 워커 | Needs verification — 모든 도구 워커 프롬프트가 길어짐 |
| `_TOOL_USAGE_NORM` | READ | `tests/application/agent_run/test_prompt_rendering.py` | Breaking — 스냅샷/포함 단언 갱신 |
| `SupervisorState` | READ/WRITE | `supervisor_nodes.py` 전 노드·route 함수 | None — TypedDict 필드 추가는 하위호환. 단, 종료 경로 5곳 모두 리셋 추가 필요 |
| `SupervisorState` | WRITE | `workflow_compiler.py` `_wrap_worker`, `_with_empty_signal`, `build_initial_state` | Needs verification — 초기값 `''` 추가, 신호 세팅 지점 추가 |
| `SupervisorState` | READ | `run_agent_use_case.py` payload 구성 | Needs verification — 신규 필드 누출 여부 |
| `finish_challenge_pending` | READ | `route_to_worker_or_final` | None — 세팅 조건만 확장, route 로직 불변 |
| `finish_challenge_pending` | READ | `tests/application/agent_builder/test_supervisor_empty_block.py`, `test_empty_result_integration.py` | Needs verification — 합산 1회 의미로 단언 확인 |
| 결정 프롬프트 조립부 (`supervisor_nodes.py:346-375`) | READ | `test_supervisor_nodes.py` 외 바이트 동일 회귀 테스트 | Needs verification — 신호 없을 때 동일해야 함 |
| `WorkflowCompiler.__init__` | CALL | `src/api/main.py`, 테스트 픽스처 다수 | None — kwarg 기본값 `None`으로 하위호환 |
| `src/config.py` | READ | `src/api/main.py` | None — 필드 추가 |

### 6.3 Verification

- [ ] 위 소비자 전부가 변경 후 정상 동작함을 테스트로 확인
- [ ] 권한·인증 경로 변경 없음 확인
- [ ] state 필드 추가가 기존 체크포인트 직렬화를 깨지 않음 확인
- [ ] 신호 없는 에이전트의 결정 프롬프트가 기존과 바이트 동일함 확인
- [ ] 빈 결과 되물음 기존 테스트가 합산 1회 의미에서도 통과함 확인

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | 단순 구조 | 정적 사이트 | ☐ |
| **Dynamic** | 기능 모듈 + BaaS | 웹앱, SaaS MVP | ☐ |
| **Enterprise** | 엄격한 레이어 분리, DI | 복잡한 아키텍처 | ☑ |

기존 프로젝트가 Thin DDD (domain / application / infrastructure / interfaces)이므로 그대로 따른다.

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 판정 위치 | domain policy / application / infrastructure | **domain policy** | `EmptyResultPolicy`·`ToolErrorPolicy` 선례. 문자열만 받고 LangChain 타입 미참조 |
| 판정 방식 | 문구 패턴(config) / 워커 목록 교차 검증 / LLM 판정 | **문구 패턴(config)** | 사용자 선택. LLM 호출 0회, 오탐 비용은 되물음 1회로 상한 |
| 되물음 플래그 | 기존 `finish_challenge_pending` 재사용 / 별도 플래그 | **재사용(합산 1회)** | route 로직 불변, 무한 루프 불가 보장을 한 곳에서 유지. 별도 플래그는 2회 되물음 가능해져 상한 논리가 둘로 갈라짐 |
| 신호 전달 채널 | state 필드 / 메시지 삽입 | **state 필드** | `last_worker_empty` 동형. 메시지 삽입은 워커 산출=AIMessage 1건 규약을 깨고 컨텍스트 오염 재발 |
| 기대 동작 표현 위치 | 코드 분기 / 블록 문구 + config | **블록 문구 + config** | 사용자 요구 "나중에 변경에 용이하게". 1차는 "가능함을 답하고 대상 확인"이지만, 능동 조회 모드 전환은 블록 문구 조정만으로 가능하게 둔다 |
| 워커 규범 위치 | `_TOOL_USAGE_NORM` / 워커별 instruction / task 문구 | **`_TOOL_USAGE_NORM`** | 모든 도구 워커에 공통 적용. task 문구는 supervisor LLM 산출이라 보장 불가 |
| 판정 적용 범위 | react 워커만 / 함수 노드(search·collect·action) 포함 | **Design에서 결정** | 실측 결함은 react 워커. 함수 노드는 단일샷이라 능력 질문에 답할 여지가 적지만 `_with_empty_signal`과 같은 지점에서 한 번에 덮으면 비용이 낮음 |
| 데이터 결함 처리 | 본 피처에 포함 / 권고 | **권고** | 사용자 미선택. 코드 밖(별도 MCP 저장소·DB 데이터) |

### 7.3 Clean Architecture Approach

```
Selected Level: Enterprise (Thin DDD)

변경 위치:
┌─────────────────────────────────────────────────────────┐
│ domain/agent_builder/policies.py                        │
│   └ CapabilityDenialPolicy (신설, 규칙만)               │
├─────────────────────────────────────────────────────────┤
│ application/agent_builder/                              │
│   ├ supervisor_state.py   (last_worker_denial 추가)     │
│   ├ supervisor_nodes.py   (블록 렌더 + 배타 + 합산 게이트)│
│   └ workflow_compiler.py  (kwarg 주입 + 워커 → 신호 배선)│
│ application/agent_run/                                  │
│   └ prompt_rendering.py   (A 규범 1건)                  │
├─────────────────────────────────────────────────────────┤
│ config.py                 (capability_denial_patterns)  │
│ api/main.py               (tuple 정규화 → kwarg 주입)   │
└─────────────────────────────────────────────────────────┘
infrastructure/ 변경 없음 · interfaces/ 변경 없음
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `CLAUDE.md`에 코딩 규칙 존재 (루트 + `idt/`)
- [x] `idt/docs/rules/` 세부 규칙 존재 (logging, testing, db-session, tool-and-mcp)
- [x] `docs/wiki/_INDEX.md` 개발 위키 존재 — Design 착수 전 supervisor 그래프 계약 문서 참조
- [ ] `CONVENTIONS.md` 루트 파일 (미존재, 불필요)

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| **Design Ref 주석** | exists | 신규 코드에 `# Design Ref: worker-capability-denial-guard §N` 부착 | High |
| **Plan SC 주석** | exists | 핵심 로직에 `# Plan SC: FR-0N` 부착 | High |
| **정책 클래스 네이밍** | exists (`EmptyResultPolicy`) | `CapabilityDenialPolicy` — 동일 컨벤션 | High |
| **state 필드 주석** | exists | 설계 출처·수명주기 주석 (`last_worker_empty` 형식) | Medium |
| **설정값 네이밍** | exists (`empty_result_patterns`) | `capability_denial_patterns` — 동일 형식(콤마 구분 str) | Medium |
| **프롬프트 규범 낱말** | exists | '생략'은 절단 안내와 겹쳐 테스트 오탐 — 다른 낱말 사용 (early-finish-fix 교훈) | Medium |

### 8.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `CAPABILITY_DENIAL_PATTERNS` | 능력 부정 판정 문구 목록(콤마 구분). config 기본값 제공, 환경변수는 선택 | Server | ☑ (기본값으로 충분, `.env` 필수 아님) |

신규 외부 서비스·시크릿 없음.

### 8.4 Pipeline Integration

해당 없음 (기존 시스템 결함 수정, 9-phase 파이프라인 신규 진입 아님).

---

## 9. Next Steps

1. [ ] `/pdca design worker-capability-denial-guard` — 3가지 설계안 비교. 핵심 결정: 판정 적용 범위(react만 vs 함수 노드 포함), 블록 문구, 종료 경로 리셋 지점 정리
2. [ ] 개발 위키 `docs/wiki/_INDEX.md`에서 supervisor 그래프 계약(①②③)·되물음 게이트 문서 확인
3. [ ] TDD 구현 (`/pdca do`)
4. [ ] Gap 분석 (`/pdca analyze`) + 실런 L3 재현(로컬 MCP 8007)
5. [ ] 별도 권고: `sangplus/mcp` `list_inquiries` description을 "**연락처** 원문은 어떤 도구로도 볼 수 없습니다"로, 에이전트 `e557f77e…` Tool Guidelines를 "개인정보 원문"으로 명확화

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-25 | 최초 작성. 로컬 런 `031564e4` 분석 기반, A+B 범위·패턴 config·1차 기대 동작 확정 | 배상규 |
