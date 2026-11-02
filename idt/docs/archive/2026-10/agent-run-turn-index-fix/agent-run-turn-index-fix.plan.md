# agent-run-turn-index-fix Planning Document

> **Summary**: 에이전트 실행 경로에서 user/assistant 메시지가 같은 `turn_index`로 저장되는 기존 결함을 고친다. assistant 저장을 user 저장과 같은 session_factory 경로로 옮기고, 과거 중복 행은 👎 질문 복원의 읽기 폴백으로 호환한다.
>
> **Project**: sangplusbot — idt (백엔드)
> **Version**: 기준 커밋 3578c1d
> **Author**: 배상규 + Claude
> **Date**: 2026-10-30
> **Status**: Draft
> **원천**: `docs/proposals/2026-10-15.md` 후보 #1 · prompt-guard 사이클 이월(`docs/archive/2026-10/_INDEX.md`)

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 에이전트 실행 런은 user 메시지를 별도 세션에서 즉시 commit하고, assistant 메시지는 요청 세션의 REPEATABLE READ 스냅샷으로 turn을 계산한다. 방금 commit된 user 행이 안 보여 두 행이 **같은 turn_index**로 저장된다(2026-09-30 이후 11세션 재현). 👎 환류의 질문 복원(`turn_index - 1`)이 에이전트 경로에서 실패한다. |
| **Solution** | `_save_assistant_message`를 `_save_user_message`와 동형으로 session_factory 별도 세션에서 조회·저장·commit한다. `eval._find_question`은 `turn-1` USER를 못 찾으면 같은 turn의 USER로 폴백해 과거 중복 행도 복원한다. |
| **Function/UX Effect** | 사용자에게 직접 보이는 변화는 없다. 에이전트 경로 👎 환류(메모리·위키 draft)가 질문을 찾을 수 있게 되고, 대화 이력 API의 turn 정렬이 user→assistant 순으로 안정된다. |
| **Core Value** | growing-agent Phase 2 "피드백 수집"을 주 경로(에이전트 실행)에서 여는 **기반 결함 제거**. 후속 #2 `agent-run-feedback-wiring`의 선행 조건. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 에이전트 경로 user/assistant가 같은 turn_index로 저장되어 👎 Q/A 복원·turn 페어링이 성립하지 않는다 |
| **WHO** | P1·P4(에이전트 대화 사용자의 👎 환류) · P3(관리자 피드백 데이터) · 후속 #2 구현자 |
| **RISK** | 저장 세션 분리가 ai_run FK·승인 재개 스냅샷 경로와 상호작용해 새 락 대기나 누락을 만들 가능성 |
| **SUCCESS** | 신규 런에서 user turn=N, assistant turn=N+1 · 과거 중복 행에서도 `_find_question` 성공 · 일반 채팅 무수정 · 기존 테스트 통과 |
| **SCOPE** | 백엔드 2파일(run_agent_use_case 저장 메서드 1 · eval 질문 복원 1) + 테스트. 마이그레이션 0 · 데이터 리넘버링 0 · 프론트 0 · id 반환은 #2 |

---

## 1. Overview

### 1.1 Purpose

에이전트 실행 경로(`RunAgentUseCase`)가 저장하는 대화 메시지의 `turn_index`를 유일하게 만든다. 일반 채팅(`_persist_messages`, 한 세션에서 base+1/base+2)과 같은 불변식 "user는 홀수 아님, assistant = user+1"을 에이전트 경로에서도 보장한다.

### 1.2 Background

- **결함 원인** (`src/application/agent_builder/run_agent_use_case.py`): `_save_user_message`는 AGENT-OBS-001 수정으로 session_factory 별도 세션에서 `find_by_session → len+1 → commit`한다(ai_run FK 락 회피). `_save_assistant_message`는 `self._message_repo`(요청 세션)로 같은 계산을 하는데, 요청 세션은 스트림 시작 전에 열린 REPEATABLE READ 스냅샷이라 user 행을 못 본다 → `len(existing)`이 user 저장 전 값 → 같은 turn.
- **파급**: `src/application/eval/use_cases.py` `_find_question`이 `turn_index - 1`·`role == USER`로 질문을 찾는다. 에이전트 경로 메시지에 👎를 붙이면(후속 #2) 질문 복원 실패 → 메모리·위키 환류 불가, 통계만 쌓인다.
- **기존 우회**: `src/domain/prompt_guard/policies.py` `BlockedTurnPolicy`가 `(turn_index, role==USER 선행)` 복합 키로 정렬. 위키 `docs/wiki/backend/db/erd-conversation-eval.md` v2 각주에 결함과 "근본 수정 이월" 기록.
- **이월 이력**: prompt-guard 사이클 Act G-1이 tie만 흡수, 근본 수정은 "독립 사이클 — assistant 저장도 session_factory 경로로"로 이월.
- **호출 지점 4곳**(모두 `_save_assistant_message`): 정상 완료(`:379`), 가드 차단 안내(`:575`), 강등 경로(`:630`), 승인 재개(`:1031`). 시그니처를 바꾸지 않으면 4곳 무수정.

### 1.3 Related Documents

- 원천: `docs/proposals/2026-10-15.md` §2-1
- 위키: `docs/wiki/backend/db/erd-conversation-eval.md` (v2 각주), `docs/wiki/backend/patterns/prompt-injection-guard.md` §5
- 선례: AGENT-OBS-001(user 저장 세션 분리), general_chat `_persist_messages`(session_factory + `session.begin()`)
- 세션 규칙: `docs/rules/db-session.md`
- 후속: `agent-run-feedback-wiring`(#2) — `_save_assistant_message` id 반환 + ANSWER_COMPLETED payload

---

## 2. Scope

### 2.1 In Scope

- [ ] `_save_assistant_message`: `session_factory` 주입 시 별도 세션(`async with session.begin()`)에서 `find_by_session → len+1 → save`. 미주입 시 legacy fallback(현행 요청 세션 경로) 유지.
- [ ] `eval.use_cases._find_question`: `turn-1` USER 우선, 없으면 **같은 turn**의 USER 폴백(과거 중복 행 호환). 둘 다 없거나 모호하면 None(현행).
- [ ] 테스트: 저장 turn 유일성(user N / assistant N+1, 세션 2개 시뮬레이션), 4 호출 지점 회귀, 승인 재개 경로, legacy fallback 불변, eval 폴백 3케이스(정상·과거 중복·부재).
- [ ] 위키 각주(erd-conversation-eval v2 "근본 수정 이월") 갱신은 **사용자가 `/wiki update`를 호출할 때만**.

### 2.2 Out of Scope (사용자 확정 2026-10-30)

- **과거 중복 행 데이터 리넘버링**: 하지 않는다. 읽기 폴백으로 호환한다.
- **`_save_assistant_message` id 반환**: #2 `agent-run-feedback-wiring`에서 payload 연결과 함께.
- user turn 힌트 전달(스트림 상태·승인 스냅샷 시그니처 변경): 하지 않는다.
- DB 유니크 제약(`session_id, turn_index, role`) 추가: 스키마 변경 금지 원칙. 후속 후보로만 기록.
- 일반 채팅 `_persist_messages`·`conversation/use_case.py`: 정상이므로 무수정.
- `BlockedTurnPolicy` 복합 키 정렬: 과거 행 호환을 위해 그대로 둔다.

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | session_factory 주입 시 `_save_assistant_message`는 별도 세션을 열어 최신 커밋 기준으로 `turn = len(existing) + 1`을 계산하고 즉시 commit한다 | High | Pending |
| FR-02 | 같은 런에서 user turn = N이면 assistant turn = N+1 (user 저장 commit 후 assistant 조회가 user 행을 본다) | High | Pending |
| FR-03 | 호출 지점 4곳(정상·가드 차단·강등·승인 재개)의 시그니처·동작 무변경 — `persist=False`면 건너뛴다 | High | Pending |
| FR-04 | session_factory 미주입(테스트·legacy)이면 현행 요청 세션 경로 그대로 (기존 테스트 무수정 통과) | High | Pending |
| FR-05 | `_find_question`: `turn-1`의 USER가 있으면 그것, 없으면 같은 `turn`의 USER, 둘 다 없으면 None | High | Pending |
| FR-06 | 폴백이 둘 이상 매칭되면(같은 turn에 USER 2개) None — 모호성 보수 처리(현행 "모호하면 None" 유지) | Medium | Pending |
| FR-07 | charts·analysis_data 등 assistant 메타 저장 내용은 변경 없음 | High | Pending |
| FR-08 | 저장 실패(세션 오류)는 현행과 같은 예외 전파 — 조용한 삭킴 금지, 스택 포함 로그 | Medium | Pending |
| FR-09 | 일반 채팅 경로·`conversation/use_case.py`·대화 이력 API 무수정 | High | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| 세션 규칙 | Repository 내부 commit 금지 · 쓰기 세션은 `async with session.begin()` (`docs/rules/db-session.md`, agent-memory-extraction 교훈) | 코드 리뷰 + 테스트가 begin() 컨텍스트 진입을 검증 |
| 락 | assistant 별도 세션 commit이 ai_run/ai_run_step 쓰기(Tracker 별도 세션)와 락 대기를 만들지 않음 | 실런 1회(WS 대화) + ai_run 행 정상 종료 확인 |
| 회귀 | `tests/application/agent_builder`·`approval`·`eval`·`general_chat` 무수정 통과 | `uv run python -m pytest` |
| 데이터 | 과거 중복 행 무변경 | 마이그레이션·스크립트 0 |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] FR-01~FR-09 구현 + 선행 테스트 통과
- [ ] 기존 `test_run_agent_use_case_stream.py`·`approval/test_resume.py`·`eval` 스위트 무수정 통과
- [ ] 실런 1회(인프로세스 `TestClient` WS 또는 REST, `persist_conversation=True` 일회용 세션): `conversation_message`에서 user turn N / assistant turn N+1 확인 후 세션 삭제
- [ ] 과거 중복 행 1건에 대해 `_find_question` 폴백이 USER를 돌려주는지 단위 테스트로 고정

### 4.2 Quality Criteria

- [ ] 함수 40줄 규칙: `_save_assistant_message`는 user 메서드와 같은 구조(별도 세션 분기 + legacy 분기). 중복이 커지면 공통 헬퍼 `_next_turn_index(repo, user_id, session_id)` 추출 검토(Design에서 결정)
- [ ] `Design Ref:` 주석
- [ ] 신규 파일 0 · 마이그레이션 0 · 프론트 0 · API 계약 0

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| assistant 별도 세션 commit과 Tracker(ai_run) 별도 세션 간 FK/락 상호작용 | Medium | Low | user 저장이 이미 같은 패턴으로 운영 중(AGENT-OBS-001). assistant는 ai_run이 참조하지 않는다(ai_run.user_message_id만). 실런으로 확인 |
| 승인 재개(`_resume_graph` 후 `:1031`)에서 세션 컨텍스트가 다름 | Medium | Low | 재개 경로도 session_factory 주입 동일. `test_resume.py` 회귀 + 테스트 1건 추가 |
| 동시 요청(같은 세션에 두 런)에서 `len+1` 경합 | Low | Low | 기존 user 저장과 같은 수준의 경합. 유니크 제약은 범위 밖(후속 후보) |
| 폴백이 과거 행과 신규 행을 혼동해 엉뚱한 질문을 복원 | Medium | Low | `turn-1` 우선 → 신규 행은 항상 1차 매칭. 폴백은 1차 실패 시에만 · 다중 매칭 None |
| legacy fallback 유지로 결함 경로가 코드에 남음 | Low | — | docstring에 "session_factory 미주입은 테스트 전용"임을 명기. 운영 DI는 항상 주입(main.py) |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change Description |
|----------|------|--------------------|
| `RunAgentUseCase._save_assistant_message` | Application 메서드 내부 | 저장 세션을 session_factory 별도 세션으로 (시그니처 불변) |
| `SubmitFeedbackUseCase._find_question` (eval) | Application 메서드 내부 | 같은 turn USER 폴백 추가 (시그니처 불변) |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `_save_assistant_message` | CALL | `run_agent_use_case.py:379` 정상 완료(ANSWER_COMPLETED 직전) | 무수정 — 동작: turn 정정 |
| `_save_assistant_message` | CALL | `:575` prompt-guard 차단 안내 저장 | 무수정 — 차단 턴도 user+1 |
| `_save_assistant_message` | CALL | `:630` 강등/실패 경로 | 무수정 |
| `_save_assistant_message` | CALL | `:1031` 승인 재개 후 답변 저장 | Needs verification — 재개 UC의 session_factory 주입 확인 |
| `_save_assistant_message` | TEST | `tests/application/agent_builder/test_run_agent_use_case_stream.py`, `tests/application/approval/test_resume.py` | session_factory None → legacy 경로, 무수정 통과 예상 |
| `self._message_repo.find_by_session` | READ | `_build_messages`(컨텍스트 조립, `:1437-1483`) | 무관 — 이력 읽기 (요청 세션 스냅샷이어도 이번 턴 user는 별도로 주입) |
| `_find_question` | CALL | `SubmitFeedbackUseCase.execute` 👎+comment 환류 팬아웃 | 동작 확장(폴백) — 기존 테스트 무수정 통과 |
| `turn_index` 읽기 | READ | `conversation_history_router.py`, `history_use_case.py`, `BlockedTurnPolicy`, general_chat 정렬 | 무수정 — 신규 행은 더 정확해지고 과거 행은 그대로 |
| `conversation_message` DDL | — | 변경 없음 | None |

### 6.3 Verification

- [ ] 4 호출 지점 전부 무수정으로 통과
- [ ] 세션 규칙(repository 내 commit 금지, `session.begin()`) 준수
- [ ] 스키마·API 변경 없음

---

## 7. Architecture Considerations

### 7.1 Project Level Selection

| Level | Selected |
|-------|:--------:|
| Enterprise (Thin DDD) | ☑ |

### 7.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| 수정 방식 | (a) assistant도 session_factory 경로 / (b) user turn 힌트 전달 / (c) 둘 다 | **(a)** | 사용자 확정. 시그니처 0 변경, 호출 4곳 무수정, user 저장과 대칭 |
| 과거 중복 행 | 읽기 폴백 / 리넘버링 스크립트 / 방치 | **읽기 폴백** | 사용자 확정. 데이터 무변경, 신규·구 행 모두 동작 |
| id 반환 | 이번 / #2 | **#2** | 사용자 확정. 스펙 외 기능 금지 |
| legacy fallback | 유지 / 제거 | **유지** | 기존 테스트(`__new__`·session_factory None 픽스처) 무수정 통과. docstring에 테스트 전용 명기 |
| turn 계산 공통화 | 인라인 유지 / `_next_turn_index` 헬퍼 | Design에서 결정 | 40줄 규칙·중복 정도를 보고 판단 |

### 7.3 Clean Architecture Approach

```
application/agent_builder/run_agent_use_case.py   _save_assistant_message (세션 경로 변경)
application/eval/use_cases.py                     _find_question (폴백)
infrastructure/persistence/repositories/conversation_repository.py  무변경 (save/find_by_session 재사용)
domain/                                            무변경
```

---

## 8. Convention Prerequisites

### 8.1 Existing Project Conventions

- [x] `docs/rules/db-session.md` — 세션 팩토리 사용 시 `async with session.begin()`, repo 내 commit 금지
- [x] `docs/rules/logging.md`
- [x] `docs/rules/testing.md` — TDD, `uv run python -m pytest`

### 8.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 쓰기 세션 | `async with session.begin()` 선례(user 저장·general_chat) | 동일 패턴 | High |
| 주석 | `Design Ref:` | 변경 2곳 부착 | Medium |

### 8.3 Environment Variables Needed

없음.

---

## 9. Next Steps

1. [ ] `/pdca design agent-run-turn-index-fix` — 세션 경로 구조(헬퍼 추출 여부), 폴백 알고리즘, 테스트 플랜 확정
2. [ ] Do: 테스트 선행 → 구현 2파일 → 회귀 → 실런 1회
3. [ ] 후속: `agent-run-feedback-wiring`(#2) 착수, 유니크 제약 후보 기록, 위키 각주 갱신(`/wiki update`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-30 | 초안. 사용자 확정 3건(session_factory 경로·읽기 폴백·id 반환은 #2) | 배상규 + Claude |
