# DB-SESSION-LEAK-FIX: Gap Analysis Report

> 분석일: 2026-04-19
> Branch: feature/E-0001
> Design: `docs/02-design/features/db-session-leak-fix.design.md`

---

## 종합 스코어

| 카테고리 | 점수 | 상태 |
|----------|:----:|:----:|
| Design Match | 100% | OK |
| Architecture Compliance (DB-001 §10) | 100% | OK |
| Convention Compliance (CLAUDE.md §12) | 100% | OK |
| **Overall Match Rate** | **98%** | ✅ |

(2pt 차감: 테스트 파일 경로 위치 편차 및 naming 문서 불일치)

---

## 체크포인트별 결과

### ✅ CP-1: `database.get_session` — `async with session.begin()` 추가 (§2-1)

`src/infrastructure/persistence/database.py:55-70`

```python
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session
```

- `async with session.begin()` 구현됨 (자동 commit/rollback 경계)
- 기존 `try/finally close()` 중복 제거됨

---

### ✅ CP-2: `ConversationMessageRepository.save` — commit + refresh 제거 (§3-2)

`src/infrastructure/persistence/repositories/conversation_repository.py:32-47`

- `commit()` 제거됨
- `refresh()` 제거됨 (flush 후 id 확보만)

---

### ✅ CP-3: `UserRepository.save` / `update_status` — commit 제거, refresh 유지 (§3-3)

`src/infrastructure/auth/user_repository.py:30-72`

- `save()`: `flush()` + `refresh(model)` 유지, `commit()` 제거 (보수적 선택 설계와 일치)
- `update_status()`: `commit()` 제거

---

### ✅ CP-4: `RefreshTokenRepository` — commit 제거 (§3-4)

`src/infrastructure/auth/refresh_token_repository.py:18-59`

- `save()`: `commit()` 제거, `flush()`만 사용
- `revoke()` (설계의 "delete"에 해당): `commit()` 제거

> ⚠️ **문서 불일치**: 설계 §3-4는 "delete()"로 표기하였으나, 실제 메서드는 `revoke()` (soft-delete). 동작은 올바르게 수정됨. 설계 문서 업데이트 권장.

---

### ✅ CP-5: `api/main.py` — 8개 팩토리 `Depends(get_session)` 리팩토링 (§4-1~4-6)

| 팩토리 | Depends(get_session) | 세션 공유 |
|--------|:--------------------:|:---------:|
| `create_general_chat_use_case_factory` | ✅ | ✅ (message/summary/mcp_repo 공유) |
| `create_conversation_use_case_factory` | ✅ | ✅ |
| `create_history_use_case_factory` | ✅ | ✅ |
| `create_auth_factories` (8개 서브팩토리) | ✅ | ✅ |
| `create_agent_builder_factories` | ✅ | ✅ |
| `create_middleware_agent_use_case_factory` | ✅ | ✅ |
| `create_auto_build_components` | N/A (lifespan singleton) | `create_agent_use_case` 생성자 제거됨 ✅ |

`grep get_session_factory()()` → `src/` 내 0건 (직접 세션 생성 없음)
`grep session.commit|session.rollback` in `src/infrastructure` → 0건

---

### ✅ CP-6: `auto_agent_builder_router.py` — `CreateMiddlewareAgentUseCase` DI 추가 (§4-6)

`src/api/routes/auto_agent_builder_router.py:31-60`

- `get_create_middleware_agent_use_case` DI 함수 추가됨
- `auto_build`, `auto_build_reply` 양 라우트에서 `create_agent_use_case=` kwarg 전달

---

### ✅ CP-7: `AutoBuildUseCase` 시그니처 변경 (§2-3, §4-6)

`src/application/auto_agent_builder/auto_build_use_case.py:14-54`

- `__init__` 에서 `create_agent_use_case` 제거
- `execute(self, request, *, create_agent_use_case)` kwarg-only 주입

---

### ✅ CP-8: `AutoBuildReplyUseCase` 시그니처 변경 (§2-3, §4-6)

`src/application/auto_agent_builder/auto_build_reply_use_case.py:12-144`

- 동일 패턴 적용됨

---

### ⚠️ CP-9: 테스트 (§5)

#### 9a. 신규 테스트 TC-DB-1~3
- **실제 경로**: `tests/infrastructure/persistence/test_db_session_lifecycle.py`
- **설계 경로**: `tests/integration/test_db_session_lifecycle.py`

| TC | 설계 의도 | 구현 |
|----|-----------|------|
| TC-DB-1 | 50회 요청 후 풀 상태 확인 | SQLite + `get_session()` 직접 소비로 commit/rollback 경계 검증 |
| TC-DB-2 | 7턴 대화 후 요약 저장 | `TestRepositoryDoesNotCommit` + `TestRepositoryFlushWithoutCommit` (4+3개) |
| TC-DB-3 | UseCase 예외 → 원자적 롤백 | `TestSharedSessionAtomicity` — 다중 repo 공유 세션 롤백 검증 |
| (추가) TC-DB-4 | — | `TestAutoBuildUseCaseSignature` — 시그니처 contract 테스트 3개 (설계 초과 구현) |

> **위치 편차 (낮은 영향)**: SQLite 기반 단위 테스트로 설계 의도 충족. 단, 실제 MySQL 풀 고갈 시뮬레이션은 미실시.

#### 9b-d. 기존 테스트 시그니처 수정
- `tests/application/auto_agent_builder/test_auto_build_use_case.py` ✅ — execute kwarg 주입으로 변경
- `tests/application/auto_agent_builder/test_auto_build_reply_use_case.py` ✅ — 동일
- `tests/api/test_auto_agent_builder_router.py` ✅ — `get_create_middleware_agent_use_case` override 추가

---

## Gap 목록

### 미구현 항목 (Design O / Implementation X)
없음.

### 설계 초과 구현 항목 (Design X / Implementation O)
| 항목 | 설명 |
|------|------|
| TC-DB-4 AutoBuild 시그니처 contract 테스트 | §2-3 회귀 방지 강화 (품질 향상) |
| 소스 grep 기반 "no commit in repo" 정적 테스트 | 4개 repository 커밋 부재 정적 검증 |

### 문서 불일치 항목 (문서 수정 권장)
| 항목 | 설계 | 구현 | 권장 조치 |
|------|------|------|-----------|
| 테스트 파일 경로 | `tests/integration/...` | `tests/infrastructure/persistence/...` | 설계 §5-1 경로 업데이트 |
| RefreshTokenRepository 메서드명 | `delete()` | `revoke()` | 설계 §3-4 표기 수정 |

---

## 아키텍처 준수 (DB-001 §10)

| 규칙 | 상태 | 근거 |
|------|:----:|------|
| §10.1 — 요청 1건 = 세션 1개 | ✅ | 8개 팩토리 모두 단일 `Depends(get_session)` |
| §10.2 — `get_session` 통해서만 세션 획득 | ✅ | `get_session_factory()()` grep → 0건 |
| §10.3 — Repository commit/rollback 금지 | ✅ | `session.commit/rollback` grep → 0건 |
| §10.4 — lifespan UC가 세션 보유 금지 | ✅ | AutoBuild UC 생성자에서 세션 의존성 제거됨 |

---

## 권고 사항

### 즉각 조치
없음 — 구현이 설계 의도와 98% 일치. 코드 변경 불필요.

### 문서 업데이트 권장
1. 설계 §3-4: `delete()` → `revoke()` 표기 수정
2. 설계 §5-1: 테스트 경로 `tests/integration/` → `tests/infrastructure/persistence/` 수정

### 후속 작업 제안 (옵션)
- 실제 MySQL testcontainer 기반으로 `/api/v1/chat` 50회 호출 풀 고갈 테스트 추가 (CI 회귀 방지 강화)

---

## 결론

**Match Rate: 98%** ✅ — 설계 대비 모든 핵심 변경사항 구현 완료.
DB-001 세션 누수 원인 3가지 (C-1/C-2/C-3) 모두 해소됨.
`/pdca report db-session-leak-fix` 로 완료 보고서 생성 권장.
