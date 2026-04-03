---
name: verify-logging
description: LOG-001 로깅 규칙 준수 여부를 검증합니다. 새 서비스/어댑터 추가 후, 에러 처리 수정 후 사용.
---

# 로깅 규칙 검증 (LOG-001)

## 목적

LOG-001 로깅 규칙 준수 여부를 검증합니다:

1. **print() 금지**: 프로덕션 소스에 `print()` 사용 금지 (tests/ 제외)
2. **Exception 파라미터 필수**: except 블록의 `logger.error()` / `logger.critical()`에 `exception=` 파라미터 필수
3. **민감 정보 로깅 금지**: password, token, api_key, secret 등 평문 로깅 금지
4. **로거 타입 준수**: 로거는 `LoggerInterface` DI 또는 `get_logger()` 팩토리만 사용
5. **기본 Python logging 직접 사용 금지**: `import logging; logging.info(...)` 직접 사용 금지

## 실행 시점

- 새로운 서비스, 어댑터, UseCase를 추가한 후
- 에러 처리 코드를 수정한 후
- LOG-001 규칙 준수 여부를 감사할 때
- Pull Request를 생성하기 전

## Related Files

| File | Purpose |
|------|---------|
| `src/domain/logging/interfaces/logger_interface.py` | LoggerInterface 정의 |
| `src/infrastructure/logging/structured_logger.py` | StructuredLogger 구현 및 `get_logger()` 팩토리 |
| `src/infrastructure/logging/__init__.py` | 로깅 모듈 export (`StructuredLogger`, `get_logger`) |
| `src/infrastructure/llm/claude_client.py` | DI 방식 로거 사용 예시 |
| `src/infrastructure/embeddings/openai_embedding.py` | `get_logger()` 팩토리 방식 사용 예시 |
| `src/infrastructure/logging/middleware/exception_handler_middleware.py` | Middleware 로깅 예시 |

## Workflow

### Step 1: print() 사용 검사

**파일:** `src/**/*.py` (tests/ 제외)

**검사:** 프로덕션 소스 파일에서 `print()` 사용 여부를 확인합니다.

```bash
grep -rn "print(" src/ --include="*.py"
```

**PASS:** 출력 없음 (0건)
**FAIL:** 1건 이상 — `src/XXX.py`에서 `print()` 사용 중

**수정 방법:** `print(...)` → `logger.info(...)` 또는 `logger.debug(...)`로 교체.

---

### Step 2: except 블록의 error 로그에 exception 파라미터 검사

**파일:** `src/**/*.py` (tests/ 제외)

**검사:** except 블록 내 `logger.error()` / `logger.critical()` 호출에 `exception=` 파라미터가 있는지 확인합니다.

```bash
grep -n "except" src/infrastructure/llm/claude_client.py src/infrastructure/hallucination/adapter.py src/infrastructure/query_rewrite/adapter.py src/infrastructure/research_agent/generator_adapter.py src/infrastructure/research_agent/relevance_adapter.py src/infrastructure/research_agent/router_adapter.py src/infrastructure/tools/sandbox_executor.py src/infrastructure/parser/pymupdf_parser.py src/infrastructure/embeddings/openai_embedding.py 2>/dev/null | head -30
```

그 다음, 각 except 블록 근처에서 error 로그를 확인합니다:

```bash
grep -rn -A 5 "except " src/ --include="*.py" | grep -B 3 "logger.error\|logger.critical" | grep -v "exception=" | head -20
```

**PASS:** 모든 except 블록의 error/critical 로그에 `exception=` 파라미터 포함
**FAIL:** `exception=` 없는 `logger.error()` / `logger.critical()` 존재

**수정 방법:**
```python
# 위반
except Exception as e:
    logger.error("작업 실패", code=code)  # exception= 누락

# 준수
except Exception as e:
    logger.error("작업 실패", exception=e, code=code)
```

---

### Step 3: 민감 정보 평문 로깅 검사

**파일:** `src/**/*.py`

**검사:** 로그 메시지에 민감 정보 키워드가 포함되어 있는지 확인합니다.

```bash
grep -rn "logger\.\(info\|debug\|warning\|error\|critical\).*\(password\|api_key\|secret\|token\|Authorization\)" src/ --include="*.py"
```

**PASS:** 출력 없음 (0건)
**FAIL:** 1건 이상 — 민감 정보를 로그에 평문으로 기록할 위험 있음

**수정 방법:** 민감 정보는 마스킹 처리: `api_key=api_key[:4] + "****"` 또는 로그에서 완전히 제외.

---

### Step 4: 기본 Python logging 직접 사용 검사

**파일:** `src/**/*.py` (tests/, structured_logger.py 제외)

**검사:** `import logging` 후 `logging.info()`와 같이 기본 Python logging을 직접 사용하는지 확인합니다.

```bash
grep -rn "^import logging$" src/ --include="*.py" | grep -v "structured_logger\|formatters\|test_"
```

```bash
grep -rn "logging\.info\|logging\.error\|logging\.warning\|logging\.debug\|logging\.critical" src/ --include="*.py" | grep -v "structured_logger\|formatters\|test_\|\.getLogger\|\.setLevel\|\.addHandler\|\.propagate\|\.handlers"
```

**PASS:** 출력 없음 (0건)
**FAIL:** 1건 이상 — `StructuredLogger` 또는 `LoggerInterface`를 우회하여 기본 logging 직접 사용 중

**수정 방법:**
```python
# 위반
import logging
logging.info("처리 시작")

# 준수
from src.infrastructure.logging import get_logger
logger = get_logger(__name__)
logger.info("처리 시작")
```

---

### Step 5: 결과 요약 출력

```markdown
## verify-logging 결과

| 검사 항목 | 상태 | 위반 수 |
|-----------|------|---------|
| print() 금지 | PASS/FAIL | N건 |
| except 블록 exception 파라미터 | PASS/FAIL | N건 |
| 민감 정보 평문 로깅 | PASS/FAIL | N건 |
| 기본 logging 직접 사용 금지 | PASS/FAIL | N건 |
```

## Output Format

```markdown
### verify-logging 검증 완료

- 검사 항목: 4개
- 통과: X개
- 이슈: Y개

#### 발견된 이슈
| 파일 | 문제 | 수정 방법 |
|------|------|-----------|
| `src/infrastructure/xxx.py:42` | exception= 파라미터 누락 | `logger.error("...", exception=e)` 로 수정 |
```

## 예외사항

다음은 **위반이 아닙니다**:

1. **`src/infrastructure/logging/structured_logger.py`의 `import logging`** — StructuredLogger 구현 파일로, 내부적으로 Python logging을 래핑하는 것이 목적
2. **`src/infrastructure/logging/formatters/` 파일의 `import logging`** — 포매터 구현 파일로 허용
3. **`tests/` 디렉토리의 `print()`** — 테스트 파일에서의 print()는 디버깅 용도로 허용
4. **`logger.error("...", exception=result)` 에서 `result`가 Exception이 아닌 경우** — `CodeExecutionResult.error` 등 비-Exception 에러 결과 전달은 허용
5. **`get_logger()` 팩토리 사용 vs `LoggerInterface` DI** — 두 패턴 모두 허용; 외부 클라이언트가 없는 모듈 레벨 로거는 `get_logger()` 사용 가능
6. **`.getLogger()`, `.setLevel()`, `.addHandler()`, `.propagate`** — Python logging 설정 코드로, 기본 logging 직접 사용이 아님
