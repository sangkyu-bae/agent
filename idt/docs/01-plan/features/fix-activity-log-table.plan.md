# Plan: fix-activity-log-table

> Feature: collection_activity_log 테이블 미존재 오류 수정
> Created: 2026-04-22
> Status: Plan
> Task ID: FIX-ACTLOG-001

---

## 1. 목적 (Why)

`GET /api/v1/collections/activity-log` 호출 시 `Table 'idt.collection_activity_log' doesn't exist` (MySQL 1146) 에러가 발생한다.
마이그레이션 SQL 파일(`V011`)은 존재하지만 실제 DB에 미적용된 상태이며, 테이블 부재 시 500 에러가 그대로 노출된다.

**에러 요약**
```
asyncmy.errors.ProgrammingError: (1146, "Table 'idt.collection_activity_log' doesn't exist")
```

**호출 경로**
```
collection_router.get_activity_logs (line 125)
  → ActivityLogService.get_logs (line 42)
    → ActivityLogRepository.find_all (line 71)
      → session.execute → MySQL 1146 에러
```

---

## 2. 현재 상태 분석

| 항목 | 상태 | 파일 |
|------|------|------|
| SQLAlchemy Model | ✅ 구현 완료 | `src/infrastructure/collection/models.py` |
| Repository | ✅ 구현 완료 | `src/infrastructure/collection/activity_log_repository.py` |
| Application Service | ✅ 구현 완료 | `src/application/collection/activity_log_service.py` |
| Router (API) | ✅ 구현 완료 | `src/api/routes/collection_router.py:113` |
| 마이그레이션 SQL | ✅ 파일 존재 | `db/migration/V011__create_collection_activity_log.sql` |
| **DB 테이블** | ❌ **미생성** | MySQL `idt` 스키마에 테이블 없음 |
| **방어 코드** | ❌ **미구현** | 테이블 부재 시 500 에러 그대로 노출 |

---

## 3. 해결 방안

### 3-1. 마이그레이션 SQL 재작성

기존 `V011` 파일을 검증하고, 필요 시 `IF NOT EXISTS` 추가하여 멱등성 확보.

**현재 V011 내용** (이미 올바름):
```sql
CREATE TABLE collection_activity_log (
    id              BIGINT       AUTO_INCREMENT PRIMARY KEY,
    collection_name VARCHAR(100) NOT NULL,
    action          VARCHAR(30)  NOT NULL,
    user_id         VARCHAR(100) NULL,
    detail          JSON         NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_cal_collection (collection_name),
    INDEX ix_cal_action (action),
    INDEX ix_cal_created_at (created_at),
    INDEX ix_cal_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**변경**: `CREATE TABLE IF NOT EXISTS`로 수정하여 중복 실행 시에도 안전하게 동작.

### 3-2. 방어 코드 추가

`ActivityLogService` 레벨에서 DB 테이블 관련 예외(`ProgrammingError 1146`)를 잡아 500 대신 적절한 응답을 반환.

| 메서드 | 방어 동작 |
|--------|----------|
| `get_logs()` | `ProgrammingError` 캐치 → 빈 목록 + total=0 반환, 경고 로그 |
| `get_collection_logs()` | 동일 |
| `log()` (쓰기) | 이미 try/except 처리됨 (warning 로그) — 변경 불필요 |

**방어 코드 위치**: `src/application/collection/activity_log_service.py`

**방어 전략**: Repository가 아닌 Service 레이어에서 처리 (DDD 규칙: Repository는 순수 데이터 접근만 담당)

---

## 4. 수정 대상 파일

| # | 파일 | 변경 내용 |
|---|------|----------|
| 1 | `db/migration/V011__create_collection_activity_log.sql` | `IF NOT EXISTS` 추가 |
| 2 | `src/application/collection/activity_log_service.py` | `get_logs`, `get_collection_logs`에 ProgrammingError 방어 코드 추가 |

---

## 5. 구현 순서

1. **V011 마이그레이션 SQL 수정** — `IF NOT EXISTS` 추가
2. **DB에 마이그레이션 수동 적용** — `V011` SQL 실행 (사용자 수동)
3. **ActivityLogService 방어 코드 추가** — 읽기 메서드에 예외 처리
4. **테스트 작성** — 테이블 미존재 시 방어 동작 검증

---

## 6. 테스트 계획

| 케이스 | 기대 결과 |
|--------|----------|
| 테이블 존재 + GET /activity-log | 정상 200 + 로그 목록 |
| 테이블 미존재 + GET /activity-log | 200 + 빈 목록 (total=0) + 서버 경고 로그 |
| 테이블 미존재 + activity log 쓰기 | 기존 동작 유지 (warning 로그, 에러 무시) |

---

## 7. 영향 범위

- `/api/v1/collections/activity-log` GET 엔드포인트
- `/api/v1/collections/{name}/activity-log` GET 엔드포인트 (동일 서비스 사용 시)
- 다른 API 엔드포인트에는 영향 없음

---

## 8. 의존성

- LOG-001 (로깅 규칙 참조)
- MYSQL-001 (MySQL Repository 공통 모듈)
