# Plan: fix-permission-lazy-load

> **Feature ID**: FIX-PERM-LAZY-001
> **Created**: 2026-04-26
> **Status**: Draft
> **Priority**: High (프로덕션 장애)

---

## 1. 문제 정의

### 현상
`POST /api/v1/collections` 요청 시 `MissingGreenlet` 예외 발생으로 Collection 생성 실패.

### 에러 메시지
```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
can't call await_only() here. Was IO attempted in an unexpected place?
```

### 호출 체인
```
collection_router.py:275  create_collection
  → use_case.py:116       create_collection → permission_service.create_permission
    → permission_service.py:56  save
      → permission_repository.py:46  model.created_at  ← 💥 여기서 에러
```

---

## 2. 근본 원인 (Root Cause)

`CollectionPermissionRepository.save()` 에서 `flush()` 후 `model.created_at` / `model.updated_at` 속성에 직접 접근함.

이 두 컬럼은 `server_default=func.now()`로 선언되어 있어, `flush()` 후 SQLAlchemy가 해당 속성을 **expired** 상태로 표시한다. expired 속성에 접근하면 SQLAlchemy가 자동으로 **lazy load** (SELECT 쿼리)를 시도하는데, **AsyncSession** 컨텍스트에서는 implicit I/O가 금지되어 `MissingGreenlet` 예외가 발생한다.

### 문제 코드 (`permission_repository.py:38-48`)
```python
self._session.add(model)
await self._session.flush()
# ❌ flush 후 refresh 없이 server_default 컬럼 접근
return CollectionPermission(
    ...
    created_at=model.created_at,   # 💥 lazy load 시도 → MissingGreenlet
    updated_at=model.updated_at,   # 💥 동일 문제
)
```

### 정상 패턴 (`user_repository.py:39-42`)
```python
await self._session.flush()
await self._session.refresh(model)  # ✅ 명시적 refresh로 서버 값 로드
return _to_entity(model)
```

---

## 3. 영향 범위

### 직접 영향
- `POST /api/v1/collections` — scope/permission 포함 Collection 생성 시 100% 실패

### 영향 없는 경로
- `user`/`scope` 파라미터 없이 Collection 생성 시 (permission_service 미호출)
- Collection 조회/삭제/이름변경 — `save()` 미사용
- 다른 repository — 이미 `refresh()` 패턴 적용됨

### 동일 패턴 검증 결과
| Repository | flush 후 refresh | server_default 접근 | 상태 |
|------------|:---------------:|:------------------:|:----:|
| `user_repository.py` | ✅ | ✅ | 정상 |
| `mysql_base_repository.py` | ✅ | ✅ | 정상 |
| `conversation_summary_repository.py` | ✅ | ✅ | 정상 |
| `refresh_token_repository.py` | ❌ | ❌ (접근 안 함) | 정상 |
| `agent_definition_repository.py` | ❌ | ❌ (접근 안 함) | 정상 |
| **`permission_repository.py`** | **❌** | **✅** | **💥 버그** |

---

## 4. 수정 방안

### 방안: `flush()` 후 `refresh(model)` 추가

`permission_repository.py:save()` 메서드에서 `flush()` 직후 `await self._session.refresh(model)` 호출.

```python
self._session.add(model)
await self._session.flush()
await self._session.refresh(model)  # server_default 값 로드
return CollectionPermission(
    ...
    created_at=model.created_at,
    updated_at=model.updated_at,
)
```

**선택 이유**: 프로젝트 내 기존 정상 패턴(`user_repository.py`)과 동일한 방식. 최소 변경으로 문제 해결.

---

## 5. 작업 항목

| # | 작업 | 파일 | 예상 범위 |
|---|------|------|----------|
| 1 | 실패 테스트 작성 (TDD Red) | `tests/infrastructure/collection/test_permission_repository.py` | 신규 |
| 2 | `save()` 메서드에 `refresh()` 추가 | `src/infrastructure/collection/permission_repository.py` | 1줄 추가 |
| 3 | 테스트 통과 확인 (TDD Green) | — | — |
| 4 | 수동 검증: `POST /api/v1/collections` 호출 | — | — |

---

## 6. 검증 기준

- [ ] `POST /api/v1/collections` (scope=PERSONAL) 정상 응답 (200/201)
- [ ] 반환된 permission에 `created_at`, `updated_at` 값 포함
- [ ] `MissingGreenlet` 예외 미발생
- [ ] 기존 테스트 전체 통과
