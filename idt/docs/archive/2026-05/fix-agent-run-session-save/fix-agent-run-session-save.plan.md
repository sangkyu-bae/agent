# FIX-AGENT-RUN-SESSION-SAVE: 에이전트 실행 첫 턴 대화 유실 버그 수정

> 상태: Plan
> 연관 Task: AGENT-RUN-SESSION-001
> 작성일: 2026-05-18
> 우선순위: Critical

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | fix-agent-run-session-save |
| 작성일 | 2026-05-18 |
| 예상 소요 | 0.5일 |

| 관점 | 내용 |
|------|------|
| **Problem** | 에이전트 첫 대화 시 session_id가 없으면 DB에 대화가 저장되지 않아, 두 번째 호출부터 첫 번째 대화 내용이 유실됨 |
| **Solution** | `_save_turn()` 호출 조건을 `request.session_id is not None` 에서 무조건 저장으로 변경 |
| **Function UX Effect** | 에이전트와의 연속 대화에서 첫 번째 질의/응답이 정상적으로 기억되어 문맥 유지됨 |
| **Core Value** | 대화 연속성 보장 — 사용자가 에이전트와 자연스러운 멀티턴 대화 가능 |

---

## 1. 문제 정의 (Problem Statement)

`POST /api/v1/agents/{agent_id}/run` 에서 **첫 번째 호출 시 `session_id`를 보내지 않으면 대화가 DB에 저장되지 않는** 버그가 있다.

사용자 관점: 에이전트와 처음 대화한 내용을 AI가 두 번째 대화부터 전혀 기억하지 못함.

---

## 2. 근본 원인 분석 (Root Cause)

### 2-1. 세션 저장 조건의 논리 오류 (Critical)

**파일**: `src/application/agent_builder/run_agent_use_case.py`

#### 현재 흐름 (버그)

```
1차 호출: request.session_id = None
  → Line 82: session_id = uuid.uuid4()  (새 UUID 채번)
  → Line 84-86: _build_messages(has_session=False) → 현재 쿼리만 반환 (정상)
  → Line 116: if request.session_id is not None: ← ❌ None이므로 False
  → _save_turn() 호출 안 됨 → 첫 턴 DB 미저장
  → Line 130: session_id 반환 (클라이언트에 새 UUID 전달)

2차 호출: request.session_id = <1차에서 받은 UUID>
  → Line 84-86: _build_messages(has_session=True)
  → DB 조회 → 빈 결과 (1차 턴이 저장 안 됐으므로)
  → 이전 대화 없이 현재 쿼리만 반환
  → Line 116: request.session_id is not None → True → _save_turn() 호출
  → 2차 턴만 DB 저장
```

#### 문제의 코드 (Line 116-118)

```python
# ❌ 버그: request의 원본 session_id로 판단 → 첫 호출 시 저장 안 됨
if request.session_id is not None:
    await self._save_turn(
        request.query, answer, request.user_id, session_id, agent_id
    )
```

Line 82에서 `session_id = request.session_id or str(uuid.uuid4())`로 항상 유효한 session_id가 존재하지만, Line 116의 조건문이 **원본 request 값**을 체크하기 때문에 첫 호출 시 저장이 스킵된다.

### 2-2. _build_messages 동작은 정상

```python
# Line 144-146: 첫 호출 시 이전 대화 없이 현재 쿼리만 반환 → 이 부분은 정상
if not has_session:
    return [{"role": "user", "content": query}]
```

첫 호출 시 DB에 기록이 없으므로 현재 쿼리만 사용하는 것은 올바른 동작이다.

---

## 3. 수정 방안

### 3-1. _save_turn() 무조건 호출 (Primary Fix)

```python
# ✅ 수정: session_id는 Line 82에서 항상 존재하므로 무조건 저장
await self._save_turn(
    request.query, answer, request.user_id, session_id, agent_id
)
```

`if request.session_id is not None:` 조건을 제거하고 항상 `_save_turn()`을 호출한다.

**이유**: Line 82에서 `session_id`는 항상 유효한 값이 보장되며, 대화 기록은 세션 존재 여부와 관계없이 저장되어야 한다.

### 3-2. 수정 후 예상 흐름

```
1차 호출: request.session_id = None
  → session_id = uuid.uuid4()
  → _build_messages(has_session=False) → 현재 쿼리만 (정상)
  → LangGraph 실행 → answer 생성
  → _save_turn() 호출 ✅ → 첫 턴 DB 저장
  → session_id 반환

2차 호출: request.session_id = <UUID>
  → _build_messages(has_session=True) → DB에서 1차 턴 로드 ✅
  → 이전 문맥 포함하여 LangGraph 실행
  → _save_turn() 호출 → 2차 턴 DB 저장
  → 연속 대화 정상 동작
```

---

## 4. 영향 범위

| 대상 | 영향 |
|------|------|
| `run_agent_use_case.py` Line 116-118 | 조건문 제거 (1줄 변경) |
| DB `conversation_messages` 테이블 | 기존보다 첫 턴 레코드 추가 저장 (정상 동작) |
| 프론트엔드 | 변경 불필요 (이미 response.session_id 사용 중) |
| 기존 테스트 | RunAgentResponse에 session_id 필드 이미 존재, mock 테스트 영향 없음 |

---

## 5. 테스트 계획 (TDD)

### 5-1. 단위 테스트 추가 (Red → Green)

**파일**: `tests/application/agent_builder/test_run_agent_use_case.py`

| # | 테스트 케이스 | 검증 내용 |
|---|-------------|----------|
| T1 | `test_first_call_without_session_id_saves_turn` | session_id=None 호출 시 `_save_turn` 호출 확인 |
| T2 | `test_first_call_returns_generated_session_id` | session_id=None 시 응답에 UUID 형식 session_id 포함 |
| T3 | `test_second_call_loads_first_turn_history` | 2차 호출 시 `_build_messages`가 1차 턴 메시지를 포함하는지 확인 |
| T4 | `test_consecutive_calls_preserve_conversation` | 1차→2차 연속 호출 시 대화 문맥 유지 통합 확인 |

### 5-2. 기존 라우터 테스트 영향

`tests/api/test_agent_builder_router.py`의 `TestRunAgent` 클래스는 UseCase를 mock하므로 직접적 영향 없음. 단, mock 반환값의 `session_id` 필드가 이미 포함되어 있어 호환성 문제 없음.

---

## 6. 구현 순서

1. **T1~T4 테스트 작성** → Red 확인
2. **`run_agent_use_case.py` Line 116 조건문 제거** → Green 확인
3. **기존 테스트 전체 실행** → 회귀 없음 확인
4. Gap Analysis → 90% 이상 확인

---

## 7. 주의사항

- `_save_turn()` 내부에서 `find_by_session` 호출 후 `len(existing)`으로 turn_index를 계산하므로, 첫 턴의 경우 `base_turn=0` → user=1, assistant=2로 정상 동작
- DB 스키마 변경 불필요 — `conversation_messages` 테이블 구조는 이미 session_id 기반 저장을 지원
- 성능 영향 미미 — 첫 호출에 2개 INSERT 추가 (원래 2차 호출부터 발생하던 것이 1차로 앞당겨짐)
