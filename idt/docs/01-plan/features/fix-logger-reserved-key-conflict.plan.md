# Plan: fix-logger-reserved-key-conflict

> StructuredLogger에서 Python LogRecord 예약 키와 충돌하는 버그 수정

---

## 1. 문제 정의

### 1-1. 현상

`POST /api/v1/documents/upload-all` 호출 시 500 에러 발생:

```
KeyError: "Attempt to overwrite 'filename' in LogRecord"
```

### 1-2. 근본 원인

`StructuredLogger._log()` (structured_logger.py:118)에서 `kwargs`를 그대로 `extra` dict로 전달한다.
Python의 `logging.LogRecord.makeRecord()`는 `extra` 키가 기존 LogRecord 속성과 겹치면 `KeyError`를 발생시킨다.

**충돌 발생 위치:**

| 파일 | 라인 | 문제 키워드 | LogRecord 예약 속성 |
|------|------|-------------|---------------------|
| `src/application/unified_upload/use_case.py` | 65 | `filename=request.filename` | `filename` |
| `src/infrastructure/department/department_repository.py` | 49 | `name=name` | `name` |

### 1-3. Python LogRecord 예약 속성 목록 (충돌 위험)

```
name, msg, args, levelname, levelno, pathname, filename, module,
exc_info, exc_text, stack_info, lineno, funcName, created, msecs,
relativeCreated, thread, threadName, process, processName, message,
asctime, taskName
```

---

## 2. 영향 범위

- **직접 영향**: `upload-all` API 완전 실패 (500 에러)
- **잠재 영향**: `department_repository.py`의 `name=` 키워드도 동일 충돌 가능
- **향후 위험**: 개발자가 `filename`, `message`, `name` 등 자연스러운 키워드를 사용할 때마다 동일 버그 재발

---

## 3. 수정 전략

### 방안: StructuredLogger에서 예약 키 자동 접두사 부여 (근본 해결)

`_log()` 메서드에서 `extra` dict 구성 시 LogRecord 예약 속성과 겹치는 키에 `ctx_` 접두사를 자동 부여한다.

**장점:**
- 호출측 코드 변경 최소화 (기존 `filename=`, `name=` 그대로 사용 가능)
- 향후 동일 실수 원천 방지
- JSON 포맷터에서 `ctx_filename` 등으로 출력되어 구분 명확

**변경 대상:**

| 파일 | 변경 내용 |
|------|-----------|
| `src/infrastructure/logging/structured_logger.py` | `_log()`에 예약 키 충돌 방지 로직 추가 |
| `tests/` | 예약 키 전달 시 `KeyError` 발생하지 않는지 테스트 |

---

## 4. 구현 계획

### Step 1: 테스트 작성 (TDD Red)

- `filename=`, `name=`, `message=` 등 예약 키를 `logger.info()`에 전달해도 예외 없이 동작하는지 검증하는 테스트

### Step 2: StructuredLogger._log() 수정 (TDD Green)

- `RESERVED_KEYS` 상수 정의 (LogRecord 예약 속성 set)
- `extra` 구성 시 충돌 키에 `ctx_` 접두사 자동 부여

### Step 3: 기존 호출부 확인

- `use_case.py:65`와 `department_repository.py:49`가 수정 없이 정상 동작하는지 확인

---

## 5. 완료 기준

- [ ] `POST /api/v1/documents/upload-all` 호출 시 500 에러 해소
- [ ] 예약 키(`filename`, `name` 등)를 `logger.info()`에 전달해도 `KeyError` 미발생
- [ ] 기존 로그 출력 형식에 영향 없음 (접두사 `ctx_`로 구분)
- [ ] 단위 테스트 통과
