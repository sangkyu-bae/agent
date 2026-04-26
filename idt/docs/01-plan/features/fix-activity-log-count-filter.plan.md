# Plan: fix-activity-log-count-filter

> Feature: ActivityLogService.get_logs()에서 count()에 limit/offset 전달되는 버그 수정
> Created: 2026-04-22
> Status: Plan
> Task ID: FIX-ACTLOG-002

---

## 1. 목적 (Why)

`GET /api/v1/collections/activity-log` 호출 시 `TypeError: ActivityLogRepository.count() got an unexpected keyword argument 'limit'` 에러가 발생한다.

**에러 요약**
```
File "activity_log_service.py", line 46, in get_logs
    total = await self._repo.count(request_id=request_id, **filters)
TypeError: ActivityLogRepository.count() got an unexpected keyword argument 'limit'
```

---

## 2. 근본 원인 분석

### 호출 흐름

```
collection_router.get_activity_logs (line 125)
  → activity_log.get_logs(
      request_id=...,
      collection_name=..., action=..., user_id=...,
      from_date=..., to_date=...,
      limit=50, offset=0          ← 페이지네이션 파라미터 포함
    )
  → ActivityLogService.get_logs(request_id, **filters)
    → self._repo.find_all(**filters)   ← ✅ limit/offset 파라미터 있음
    → self._repo.count(**filters)      ← ❌ limit/offset 파라미터 없음 → TypeError
```

### 원인 요약

| 레이어 | 문제 |
|--------|------|
| `collection_router.py:125` | `get_logs()`에 `limit`, `offset` 포함하여 전달 |
| `activity_log_service.py:41-46` | `get_logs(request_id, **filters)`가 모든 kwargs를 `find_all()`과 `count()` 양쪽에 그대로 전달 |
| `activity_log_repository.py:74` | `count()` 메서드는 `limit`/`offset`을 파라미터로 받지 않음 (올바른 설계 — count는 페이지네이션 불필요) |

**결론**: `count()`는 총 개수를 세는 메서드이므로 `limit`/`offset`이 불필요한 것이 맞다. 문제는 Service 레이어에서 페이지네이션 파라미터를 필터링 없이 `count()`에 전달하는 것이다.

---

## 3. 해결 방안

### 방안: Service에서 count() 호출 시 페이지네이션 파라미터 제거

`activity_log_service.py`의 `get_logs()` 메서드에서 `count()` 호출 전에 `limit`와 `offset`을 `filters`에서 분리한다.

```python
async def get_logs(
    self, request_id: str, **filters
) -> tuple[list[ActivityLogEntry], int]:
    try:
        logs = await self._repo.find_all(request_id=request_id, **filters)
        count_filters = {
            k: v for k, v in filters.items() if k not in ("limit", "offset")
        }
        total = await self._repo.count(request_id=request_id, **count_filters)
        return logs, total
    except ProgrammingError as e:
        self._logger.warning(
            "Activity log table not available",
            exception=e,
        )
        return [], 0
```

**선택 근거**:
- Repository의 `count()` 시그니처는 올바름 — count에 페이지네이션은 의미 없음
- Router의 호출도 올바름 — 필요한 모든 파라미터를 전달
- Service가 두 메서드의 파라미터 차이를 중재해야 하는 책임

---

## 4. 수정 대상 파일

| # | 파일 | 변경 내용 |
|---|------|----------|
| 1 | `src/application/collection/activity_log_service.py` | `get_logs()`에서 `count()` 호출 시 `limit`/`offset` 제거 |

---

## 5. 구현 순서

1. **테스트 작성** — `get_logs()`에 `limit`/`offset` 전달 시 정상 동작 검증
2. **Service 수정** — `count()` 호출 전 페이지네이션 파라미터 필터링
3. **수동 검증** — `GET /api/v1/collections/activity-log` API 호출 테스트

---

## 6. 테스트 계획

| 케이스 | 기대 결과 |
|--------|----------|
| `get_logs(limit=50, offset=0)` 호출 | 정상 동작, TypeError 없음 |
| `get_logs(limit=50, offset=0, collection_name="test")` | 필터 + 페이지네이션 정상 동작 |
| `get_logs()` (limit/offset 없이) | 기존 동작 유지 |

---

## 7. 영향 범위

- `GET /api/v1/collections/activity-log` 엔드포인트 (직접 영향)
- `get_collection_logs()`는 이미 `limit`/`offset`을 명시적으로 분리하여 전달하므로 영향 없음
- 다른 API 엔드포인트에는 영향 없음

---

## 8. 의존성

- FIX-ACTLOG-001 (테이블 미존재 방어 코드) — 이미 `ProgrammingError` 방어 적용됨, 독립 수정 가능
