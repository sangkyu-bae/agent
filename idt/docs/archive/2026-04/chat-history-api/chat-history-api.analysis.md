# CHAT-HIST-001: 대화 히스토리 조회 API — Gap Analysis

> 상태: Check
> Plan 참조: docs/01-plan/features/chat-history-api.plan.md
> Design 참조: docs/02-design/features/chat-history-api.design.md
> 분석일: 2026-04-17
> **Match Rate: 98%**

---

## 1. 요약 점수표

| 항목 | 점수 | 상태 |
|------|:----:|:----:|
| Design 매칭 (파일/스키마/DI/엔드포인트) | 100% | Aligned |
| 아키텍처 규칙 (DDD 레이어) | 100% | Aligned |
| 테스트 커버리지 (케이스 수) | 100% | 18/18 |
| LOG-001 준수 | 100% | Aligned |
| 라우터 등록 / DI 오버라이드 | 100% | Aligned |
| Minor 편차 (문서 불일치 2건) | -2점 | 비기능 |
| **종합 Match Rate** | **98%** | ≥90% → Report 진행 가능 |

---

## 2. Aligned (설계 대비 구현 일치)

### 2-1. Domain (`src/domain/conversation/history_schemas.py`)
- `SessionSummary`, `SessionListResponse`, `MessageItem`, `MessageListResponse` 모두 `frozen=True` dataclass로 구현 — Design §2-1 일치
- `SessionSummary.from_raw` 메서드가 `LAST_MESSAGE_MAX_LENGTH=100` 상수로 truncate 규칙 캡슐화 — Design §2-1 "도메인 메서드로 캡슐화" 일치

### 2-2. Application (`src/application/conversation/history_use_case.py`)
- 클래스 시그니처 Design §2-2 완전 일치
  - `__init__(repo: ConversationMessageRepository, logger: LoggerInterface)` (L17–23)
  - `get_sessions(user_id, request_id)` (L25), `get_messages(user_id, session_id, request_id)` (L46)
- 추상 Repository와 Logger 인터페이스에만 의존 — infra 직접 참조 없음 (DDD 규칙 준수)
- 빈 결과 정책: 세션/메시지 없으면 빈 response 반환, 예외 없음 — Design §2-2 일치

### 2-3. Repository Interface (`src/application/repositories/conversation_repository.py`)
- `find_sessions_by_user(user_id: UserId) -> List[SessionSummary]` 추상 메서드 추가 (L70–82)

### 2-4. Repository 구현 (`src/infrastructure/persistence/repositories/conversation_repository.py`)
- `find_sessions_by_user` 구현 (L109–167) — Design §2-3 "두 번의 쿼리" 전략 그대로 적용
  - Step 1 (L119–130): GROUP BY 집계 + `last_message_at DESC` 정렬
  - Step 2 (L138–157): `role == "user"` 필터 IN-clause 쿼리 + Python-side dedup
  - Step 3 (L159–167): `SessionSummary.from_raw(...)` 호출로 100자 truncate 적용

### 2-5. Router (`src/api/routes/conversation_history_router.py`)
- prefix `/api/v1/conversations`, tag `conversation-history` (L13) — Design §2-4 일치
- `GET /sessions` (L55) + `GET /sessions/{session_id}/messages` (L77–79), 둘 다 `user_id` Query 파라미터
- Pydantic 응답 스키마 4종 인라인 정의 (L16–47)
- DI placeholder `get_history_use_case()` (L50–52) — `NotImplementedError` 패턴 일치
- `request_id`는 `uuid.uuid4()`로 생성하여 use case에 전파 (L61, L87)

### 2-6. Main 앱 배선 (`src/api/main.py`)
- `conversation_history_router` + `get_history_use_case` import (L59–62)
- `create_history_use_case_factory()` (L880–889) — `SQLAlchemyConversationMessageRepository` + `app_logger` 주입
- `app.dependency_overrides[get_history_use_case] = create_history_use_case_factory()` (L1101)
- `app.include_router(conversation_history_router)` (L1145)
- 기존 `create_conversation_use_case_factory()` (L395) 패턴과 일관성 유지

### 2-7. Tests (18/18 케이스, Design §6 완전 일치)
| 파일 | 계획 | 실제 |
|------|:---:|:---:|
| `tests/domain/conversation/test_history_schemas.py` | 4 | 4 |
| `tests/application/conversation/test_history_use_case.py` | 8 | 8 |
| `tests/api/test_conversation_history_router.py` | 6 | 6 |

### 2-8. LOG-001 준수
- `get_sessions`: `info("get_sessions started", request_id=, user_id=)` (L29–31), `info("get_sessions completed", request_id=, session_count=)` (L34–38), `error("get_sessions failed", exception=e, request_id=)` (L41–43)
- `get_messages`: 동일 패턴 (L50–55, L70–74, L79–81)
- `exception=` kwarg + `raise`로 스택 트레이스 보존 — LOG-001 규칙 완전 준수
- `request_id` 모든 로그 호출에 전파

---

## 3. Minor Deviations (비기능 편차 2건)

### D1. Design 문서의 `src/main.py` 경로 불일치
- **Design §3 (L202), §4 (L241)**: `src/main.py` 참조
- **실제 프로젝트 구조**: `src/api/main.py`
- **영향**: 구현은 올바르게 `src/api/main.py`에 적용됨. 기능적 문제 없음
- **권장**: Design 문서 §3/§4 경로를 `src/api/main.py`로 수정

### D2. Design §4 신규 파일 테이블에 테스트 파일 1개만 나열
- **문제**: Design §4 "신규 파일" 테이블(L229–234)에 `test_history_use_case.py`만 등록, 나머지 2개 테스트 파일은 별도 "테스트 파일" 테이블(L243–248)에 기재
- **영향**: 문서 일관성 문제만 있음. 세 테스트 파일 모두 존재하며 케이스 수 일치
- **권장**: §4 테이블 통합 정리

---

## 4. What's Missing

**기능적으로 누락된 항목 없음.**

- 신규 파일 4개 (도메인 스키마, UseCase, 라우터, 테스트 3종) 모두 존재
- 수정 파일 3개 (Repo 인터페이스, Repo 구현, `src/api/main.py`) 모두 적용
- FastAPI 앱에 라우터 등록 완료
- 기존 feature 패턴과 일관된 DI factory 오버라이드
- LOG-001 구조화 로깅 (`exception=`, `request_id=`)
- 빈 결과 정책 (예외 없이 빈 응답)
- 도메인 dataclass ↔ Pydantic 응답 스키마 미러링

---

## 5. 권장 Fix

1. **Design 문서 경로 정정** (D1, D2)
   - `docs/02-design/features/chat-history-api.design.md` §3 L202, §4 L241: `src/main.py` → `src/api/main.py`
   - §4 "신규 파일" 테이블에 누락된 테스트 파일 2개 추가 또는 중복 행 정리

2. **선택적 하드닝** (기능 외)
   - `history_use_case.py` L62 `id=m.id.value if m.id else 0` — 영속 메시지는 항상 id 보유하므로 `0` fallback은 방어적 코드. 필요 시 assertion으로 강화 가능

3. **완료 기준 검증** (Design §8 DoD)
   ```bash
   pytest tests/domain/conversation/test_history_schemas.py \
          tests/application/conversation/test_history_use_case.py \
          tests/api/test_conversation_history_router.py -v
   # 18/18 통과 확인

   /verify-logging
   /verify-architecture
   /verify-tdd
   ```

---

## 6. 다음 단계

Match Rate 98% ≥ 90% 기준 충족 → **Report 단계 진행**

```
/pdca report chat-history-api
```

(iterate는 불필요. Design 문서 경로 수정은 Report 진행과 병행 가능)
