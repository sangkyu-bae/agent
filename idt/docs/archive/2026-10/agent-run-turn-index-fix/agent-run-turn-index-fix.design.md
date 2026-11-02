# agent-run-turn-index-fix Design Document

> **Summary**: `RunAgentUseCase`의 user/assistant 저장을 `_persist_message` 공용 헬퍼(session_factory 별도 세션 + legacy 분기 한 곳)로 통일해 turn_index 유일성을 보장하고, 👎 질문 복원은 `EvalPolicy.find_question` 순수 함수로 옮겨 과거 중복 행을 폴백으로 호환한다. 신규 파일 0, 수정 3파일.
>
> **Project**: sangplusbot — idt (백엔드)
> **Version**: 기준 커밋 3578c1d
> **Author**: 배상규 + Claude
> **Date**: 2026-10-30
> **Status**: Draft
> **Planning Doc**: [agent-run-turn-index-fix.plan.md](../../01-plan/features/agent-run-turn-index-fix.plan.md)

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

### 1.1 Design Goals

1. **turn 계산을 한 곳으로**: user·assistant 저장이 같은 헬퍼를 타서 "최신 commit 기준 `len+1`"이 두 번 다르게 구현되지 않게 한다.
2. **시그니처 불변**: `_save_user_message`·`_save_assistant_message`의 공개 시그니처와 호출 4곳을 손대지 않는다.
3. **과거 행 호환을 순수 규칙으로**: 질문 복원 규칙을 repo 없이 테스트 가능한 domain 정책으로 두고, 유스케이스는 조회만 한다.

### 1.2 Design Principles

- 쓰기 세션은 `async with session.begin()` (`docs/rules/db-session.md`), repo 내 commit 금지.
- session_factory 미주입(테스트 전용)은 현행 legacy 경로 그대로 — 기존 테스트 무수정 통과.
- 폴백은 1차 규칙(`turn-1`)이 실패할 때만, 모호하면 None(현행 보수성 유지).

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | assistant 메서드에 session_factory 블록 복제, eval 폴백 인라인 | 저장 서비스 추출로 general_chat까지 통일, domain 정책 | 유스케이스 내부 `_persist_message` 공용 헬퍼 + `EvalPolicy.find_question` |
| **New Files** | 0 | 2~3 | 0 |
| **Modified Files** | 2 | 5+ | 3 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Low (turn 계산 4벌) | High | High (turn 계산 1곳) |
| **Effort** | Low | High | Medium |
| **Risk** | 40줄 규칙 충돌 | Plan 범위 초과(일반 채팅 무수정 위반) | Low — user 경로도 헬퍼를 타므로 동일성 테스트로 고정 |
| **Recommendation** | 핫픽스 | 저장 경로 통합 사이클 | **선택** |

**Selected**: Option C — **Rationale**: 사용자 확정(2026-10-30). 결함의 본질이 "같은 계산이 두 세션 컨텍스트에서 다르게 수행됨"이므로 계산을 한 헬퍼로 모으는 것이 재발 방지다. general_chat은 Plan대로 무수정.

### 2.1 Component Diagram

```
RunAgentUseCase
 ├─ _save_user_message(query, …, persist)        ─┐  시그니처 불변
 ├─ _save_assistant_message(answer, …, persist)   ─┤
 │                                                 ▼
 └─ _persist_message(build: Callable[[int], ConversationMessage]) -> ConversationMessage | None
        │  session_factory 있음: async with sf() as s, s.begin():
        │     repo = SQLAlchemyConversationMessageRepository(s)
        │     turn = len(await repo.find_by_session(user, session)) + 1   ← 최신 commit 기준
        │     return await repo.save(build(turn))                         ← 즉시 commit
        └─ 없음(legacy, 테스트 전용): self._message_repo 로 같은 계산

SubmitFeedbackUseCase._find_question(message)
        messages = await self._msg_repo.find_by_session(user, session)   ← 조회만
        return EvalPolicy.find_question(messages, message)               ← 순수 규칙

EvalPolicy.find_question(messages, assistant) -> ConversationMessage | None
        1차: turn == assistant.turn-1 and role == USER  → 정확히 1건이면 그것
        2차: turn == assistant.turn   and role == USER  → 정확히 1건이면 그것 (과거 중복 행)
        그 외(0건·2건 이상): None
```

### 2.2 Data Flow

```
[신규 런]  user 저장: sf 세션 A: find→len=2k → save(turn 2k+1) → commit
           … 그래프 실행 …
           assistant 저장: sf 세션 B: find→len=2k+1(세션 A 커밋 반영) → save(turn 2k+2) → commit
[👎 환류]  find_by_session → EvalPolicy.find_question(messages, assistant)
           신규 행: turn-1 USER 1건 → 반환
           과거 행(user==assistant turn): turn-1 USER 0건 → 같은 turn USER 1건 → 반환
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `_persist_message` | `session_factory`(optional), `SQLAlchemyConversationMessageRepository`, `self._message_repo`(legacy) | 저장 + turn 계산 |
| `_save_user_message` / `_save_assistant_message` | `_persist_message` | 엔티티 빌더만 제공 |
| `SubmitFeedbackUseCase._find_question` | `EvalPolicy.find_question` | 규칙 위임 |
| `EvalPolicy.find_question` | `ConversationMessage`, `MessageRole` (domain) | 순수 함수 — 외부 의존 없음 |

---

## 3. Data Model

변경 없음. `conversation_message` DDL·ORM 무수정. 유니크 제약은 후속 후보로만 기록.

---

## 4. API Specification

변경 없음.

---

## 5. UI/UX Design

해당 없음.

---

## 6. Detailed Design

### 6.1 `RunAgentUseCase` — `src/application/agent_builder/run_agent_use_case.py`

**D1. 공용 헬퍼**

```python
async def _persist_message(
    self,
    user_id: str,
    session_id: str,
    build: Callable[[int], ConversationMessage],
) -> ConversationMessage | None:
    """대화 메시지 저장 — turn_index 계산과 세션 경로를 한 곳에.

    Design Ref: agent-run-turn-index-fix §6.1 D1.
    - Plan FR-01/FR-02: session_factory 주입 시 별도 세션에서 최신 commit 기준
      len+1 을 계산하고 즉시 commit 한다 (AGENT-OBS-001 user 저장 선례 — assistant도
      같은 경로를 타야 요청 세션 REPEATABLE READ 스냅샷이 user 행을 못 보는
      결함이 사라진다).
    - Plan FR-04: 미주입(테스트 전용)이면 요청 세션(self._message_repo) 로 같은 계산.
    """
    uid, sid = UserId(user_id), SessionId(session_id)
    if self._session_factory is not None:
        async with self._session_factory() as session:
            async with session.begin():
                repo = SQLAlchemyConversationMessageRepository(session)
                turn = len(await repo.find_by_session(uid, sid)) + 1
                return await repo.save(build(turn))
    turn = len(await self._message_repo.find_by_session(uid, sid)) + 1
    return await self._message_repo.save(build(turn))
```

**D2. `_save_user_message`**: 본문을 빌더 + `_persist_message` 호출로 교체. 반환 `saved.id.value if saved and saved.id else None` 유지. `persist=False` 조기 반환 유지.

**D3. `_save_assistant_message`**: 동일하게 빌더(charts·analysis_data 포함) + `_persist_message`. 반환 `None` 유지(Plan 확정: id 반환은 #2).

**D4. 호출 4곳 무수정**: `:379`(정상), `:575`(가드 차단), `:630`(강등), `:1031`(승인 재개).

**D5. 불변식 주석**: `_persist_message` docstring에 "user turn=N → assistant turn=N+1, 일반 채팅 `_persist_messages`와 같은 규칙" 명기.

### 6.2 `EvalPolicy` — `src/domain/eval/policies.py`

**D6. 순수 함수 추가**

```python
@staticmethod
def find_question(
    messages: list[ConversationMessage], assistant: ConversationMessage,
) -> ConversationMessage | None:
    """👎 답변의 질문(user 메시지) 복원 규칙.

    Design Ref: agent-run-turn-index-fix §6.2 D6 (Plan FR-05/FR-06).
    1차: turn-1 의 USER (정상 저장). 2차: 같은 turn 의 USER (에이전트 경로
    기존 결함으로 user/assistant 가 같은 turn 인 과거 행). 각 단계에서 정확히
    1건일 때만 채택 — 0건이면 다음 단계, 2건 이상이면 모호 → None.
    """
    target = assistant.turn_index.value
    for turn in (target - 1, target):
        hits = [m for m in messages
                if m.turn_index.value == turn and m.role == MessageRole.USER]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            return None
    return None
```

- domain → domain 의존만(`ConversationMessage`, `MessageRole`). `MagicMock(value=turn)` 픽스처와도 호환(`.turn_index.value`·`.role`만 접근).

### 6.3 `SubmitFeedbackUseCase._find_question` — `src/application/eval/use_cases.py`

**D7.** 조회 후 `EvalPolicy.find_question(messages, message)` 반환. 호출자(`_kickoff_feedback_fanout`)·로그·조회 횟수(1회) 무변경.

### 6.4 변경하지 않는 것

| 대상 | 이유 |
|------|------|
| `general_chat/use_case.py` `_persist_messages` | 정상(Plan FR-09) |
| `conversation/use_case.py`, 이력 API, `BlockedTurnPolicy` | 과거 행 호환 유지 |
| `SQLAlchemyConversationMessageRepository` | `save`·`find_by_session` 그대로 |
| 호출 4곳·`stream()`·승인 재개 시그니처 | D4 |
| 데이터(과거 중복 행) | 읽기 폴백으로 호환 |

---

## 7. Error Handling

| 상황 | 처리 |
|------|------|
| 별도 세션 저장 실패(DB 오류) | 현행과 동일하게 예외 전파(`session.begin()` 롤백). 스트림 상위 핸들러가 RUN_FAILED 처리(기존 동작). 조용한 삭킴 없음(Plan FR-08) |
| session_factory None | legacy 경로 — 테스트 전용. docstring 명기 |
| 질문 복원 0건/모호 | None → 기존 warning "feedback extraction skipped — question not found" + 평가 저장 유지 |

---

## 8. Security Considerations

- 데이터 접근 범위 변화 없음(같은 user_id·session_id 조회). 권한 로직 무관.
- 폴백은 같은 세션 안에서만 매칭 — 타 세션·타 사용자 메시지로 확장되지 않는다.

---

## 9. Test Plan

### 9.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| 단위 (domain) | `EvalPolicy.find_question` 규칙 | pytest, 순수 객체 | Do |
| 단위 (유스케이스) | `_persist_message` 세션 경로·turn 계산, user/assistant 연속 저장 | pytest + 가짜 session_factory(인메모리 리스트로 commit 반영 시뮬레이션) | Do |
| 회귀 | `tests/application/agent_builder`(stream·identity·gated 등), `approval`, `eval`, `general_chat` | pytest | Do/Check |
| 실런 | 인프로세스 `TestClient` REST run(`persist_conversation=True`, 일회용 session_id) → `conversation_message` 조회 → user N / assistant N+1 → 행 삭제 | asyncmy 스크립트 | Check |

### 9.2 Domain — `tests/domain/eval/test_eval_policy_find_question.py` (신규)

| # | 케이스 | 기대 |
|---|--------|------|
| P1 | turn-1 USER 1건(정상 저장) | 그 메시지 |
| P2 | turn-1 USER 0건 · 같은 turn USER 1건(과거 중복 행) | 같은 turn USER |
| P3 | turn-1 USER 2건 | None (모호) |
| P4 | 같은 turn USER 2건, turn-1 0건 | None |
| P5 | USER 없음 | None |
| P6 | turn-1에 ASSISTANT만, 같은 turn에 USER 1건 | 같은 turn USER (role 필터 확인) |

### 9.3 유스케이스 — `tests/application/agent_builder/test_run_agent_turn_index.py` (신규)

가짜 `session_factory`: 호출마다 새 "세션" 객체를 주되, 저장소는 공유 리스트(commit 반영)를 사용해 세션 A의 save가 세션 B의 find에 보이도록 한다. `SQLAlchemyConversationMessageRepository`는 `patch`로 가짜 repo로 치환.

| # | 케이스 | 기대 |
|---|--------|------|
| T1 | 빈 세션에서 user 저장 → assistant 저장 | user turn 1, assistant turn 2 (FR-02) |
| T2 | 기존 4행(2턴) 뒤 user → assistant | 5, 6 |
| T3 | assistant 저장이 `session.begin()` 컨텍스트 안에서 save 호출 | begin 진입 1회, save 1회 |
| T4 | `persist=False` | find·save 호출 0회, user 반환 None |
| T5 | session_factory None (legacy) | `self._message_repo`로 find→save, 기존 동작 동일 |
| T6 | charts·analysis_data가 저장 엔티티에 그대로 | 필드 일치 (FR-07) |
| T7 | 기존 `test_run_agent_use_case_stream.py`·`test_identity_subject_wiring.py`·`approval/test_resume.py`·`test_gated_run_termination.py` | 무수정 통과 (픽스처가 `_session_factory` 속성을 안 가지면 1줄 보정 허용 — 지난 사이클 교훈) |

### 9.4 eval 유스케이스 — `tests/application/eval/test_use_cases.py` (기존 파일에 추가)

| # | 케이스 | 기대 |
|---|--------|------|
| E1 | 과거 중복 행(USER turn 4 + ASSISTANT turn 4) + 👎 comment | kickoff 호출, question.content = USER 내용 |
| E2 | 기존 `test_직전_user_메시지_부재면_warning_후_평가는_성공` 등 | 무수정 통과 |

### 9.5 실런 (Check)

| 단계 | 내용 |
|------|------|
| 실행 | `POST /api/v1/agents/{id}/run` `{query, user_id:"7", session_id:"turnfix-<uuid>", persist_conversation:true}` |
| 확인 | asyncmy: `SELECT role, turn_index FROM conversation_message WHERE session_id=?` → `[('user',1),('assistant',2)]` |
| 정리 | 같은 session_id 행 DELETE (ai_run.user_message_id는 nullable 소프트 참조 — 삭제 전 ai_run 행도 함께 정리하거나 그대로 둠, Check에서 결정) |

---

## 10. Clean Architecture

| Component | Layer | Location | 변경 |
|-----------|-------|----------|------|
| `_persist_message` + 두 저장 메서드 | Application | `src/application/agent_builder/run_agent_use_case.py` | 수정 |
| `EvalPolicy.find_question` | Domain | `src/domain/eval/policies.py` | 추가 |
| `SubmitFeedbackUseCase._find_question` | Application | `src/application/eval/use_cases.py` | 수정 |
| `SQLAlchemyConversationMessageRepository` | Infrastructure | — | 무변경 |

domain은 domain만 import(`src.domain.conversation`). application → infrastructure(repo 클래스) 직접 생성은 기존 user 저장과 동일한 선례.

---

## 11. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 세션 | `async with session_factory() as s: async with s.begin():` — repo 내 commit 금지 |
| 함수 길이 | `_persist_message` ≤ 20줄, 두 저장 메서드는 빌더 + 호출로 각 ≤ 30줄 |
| 주석 | `Design Ref: agent-run-turn-index-fix §6.x Dn` / `Plan FR-nn` |
| 테스트 실행 | `uv run python -m pytest tests/domain/eval tests/application/agent_builder tests/application/eval tests/application/approval -q` |

---

## 12. Implementation Guide

### 12.1 File Structure

```
src/domain/eval/policies.py                              (수정: D6)
src/application/eval/use_cases.py                        (수정: D7)
src/application/agent_builder/run_agent_use_case.py      (수정: D1~D5)
tests/domain/eval/test_eval_policy_find_question.py      (신규: P1~P6)
tests/application/agent_builder/test_run_agent_turn_index.py  (신규: T1~T6)
tests/application/eval/test_use_cases.py                 (추가: E1)
```

### 12.2 Implementation Order

1. [ ] P1~P6 작성 → 실패 → `EvalPolicy.find_question` 구현 → 통과
2. [ ] E1 작성 → 실패 → `_find_question` 위임 → 통과 + eval 스위트
3. [ ] T1~T6 작성 → 실패 → `_persist_message` + 두 저장 메서드 교체 → 통과
4. [ ] 회귀: agent_builder · approval · eval · general_chat
5. [ ] 실런 1회 + 행 정리

### 12.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 질문 복원 폴백 | `module-1` | D6·D7 + P1~P6·E1 | 10-15 |
| 저장 경로 통일 | `module-2` | D1~D5 + T1~T7 | 15-20 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | 전체(S 규모) | 25-35 |
| Session 2 | Check + Report | 전체 | 20-30 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-30 | 초안. Option C 선택(사용자 확정). D1~D7, 테스트 P/T/E 플랜 | 배상규 + Claude |
