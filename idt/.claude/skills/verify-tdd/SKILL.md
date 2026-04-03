---
name: verify-tdd
description: 프로덕션 모듈에 대한 테스트 파일 존재 여부를 검증합니다. 새 모듈 추가 후, PR 전, TDD 준수 감사 시 사용.
---

# TDD 커버리지 검증

## 목적

CLAUDE.md TDD 규칙 준수 여부를 검증합니다:

1. **UseCase 테스트 필수**: `src/application/use_cases/*.py` 에 대응하는 테스트 파일 존재 확인
2. **Workflow 테스트 필수**: `src/application/workflows/*.py` 에 대응하는 테스트 파일 존재 확인
3. **Domain Policy 테스트 필수**: `src/domain/*/policy*.py` 에 대응하는 테스트 파일 존재 확인
4. **Infrastructure Adapter 테스트 필수**: `src/infrastructure/*/*.py` (주요 어댑터) 에 대응하는 테스트 파일 존재 확인
5. **API Router 테스트 필수**: `src/api/routes/*.py` 에 대응하는 테스트 파일 존재 확인

## 실행 시점

- 새로운 모듈을 추가한 후
- Pull Request를 생성하기 전
- TDD 준수 여부를 감사할 때
- `src/` 아래에 새 파일을 생성한 후

## Related Files

| File | Purpose |
|------|---------|
| `src/application/use_cases/analyze_excel_use_case.py` | UseCase 예시 |
| `tests/application/test_analyze_excel_use_case.py` | UseCase 테스트 예시 |
| `src/application/workflows/excel_analysis_workflow.py` | Workflow 예시 |
| `tests/application/test_excel_analysis_workflow.py` | Workflow 테스트 예시 |
| `src/domain/hallucination/policy.py` | Domain Policy 예시 |
| `tests/domain/hallucination/test_policy.py` | Domain Policy 테스트 예시 |
| `src/infrastructure/hallucination/adapter.py` | Infrastructure Adapter 예시 |
| `tests/infrastructure/hallucination/test_adapter.py` | Adapter 테스트 예시 |
| `src/api/routes/analysis_router.py` | API Router 예시 |
| `tests/api/test_analysis_router.py` | Router 테스트 예시 |

## Workflow

### Step 1: Application UseCase 테스트 커버리지 검사

**파일:** `src/application/use_cases/*.py`

**검사:** 각 UseCase 파일에 대응하는 테스트 파일이 존재하는지 확인합니다.

```bash
find src/application/use_cases -name "*.py" ! -name "__init__.py" | sort
```

```bash
find tests/application -name "test_*use_case*.py" -o -name "test_*_use_case.py" | sort
```

각 `src/application/use_cases/XXX_use_case.py` → `tests/application/test_XXX_use_case.py` 또는 `tests/application/use_cases/test_XXX_use_case.py`

**PASS:** 모든 UseCase 파일에 대응 테스트 존재
**FAIL:** 테스트 없는 UseCase 파일 존재

---

### Step 2: Application Workflow 테스트 커버리지 검사

**파일:** `src/application/workflows/*.py`

**검사:** 각 Workflow 파일에 대응하는 테스트 파일이 존재하는지 확인합니다.

```bash
find src/application/workflows -name "*.py" ! -name "__init__.py" | sort
```

```bash
find tests/application -name "test_*workflow*.py" | sort
```

각 `src/application/workflows/XXX_workflow.py` → `tests/application/test_XXX_workflow.py`

**PASS:** 모든 Workflow 파일에 대응 테스트 존재
**FAIL:** 테스트 없는 Workflow 파일 존재

---

### Step 3: Application UseCase (서브 디렉토리) 테스트 커버리지 검사

**파일:** `src/application/*/use_case.py`

**검사:** 서브 디렉토리의 use_case.py에 대응 테스트가 있는지 확인합니다.

```bash
find src/application -name "use_case.py" | grep -v "__pycache__" | sort
```

```bash
find tests/application -name "test_use_case.py" | grep -v "__pycache__" | sort
```

각 `src/application/XXX/use_case.py` → `tests/application/XXX/test_use_case.py`

**PASS:** 모든 use_case.py에 대응 테스트 존재
**FAIL:** 테스트 없는 use_case.py 존재

---

### Step 4: Domain Policy 테스트 커버리지 검사

**파일:** `src/domain/**/policy*.py`

**검사:** 각 Domain Policy 파일에 대응하는 테스트 파일이 존재하는지 확인합니다.

```bash
find src/domain -name "policy*.py" ! -name "__init__.py" | grep -v "__pycache__" | sort
```

```bash
find tests/domain -name "test_policy*.py" -o -name "test_*policy.py" | grep -v "__pycache__" | sort
```

각 `src/domain/XXX/policy.py` → `tests/domain/XXX/test_policy.py`

**PASS:** 모든 Domain Policy 파일에 대응 테스트 존재
**FAIL:** 테스트 없는 Policy 파일 존재

---

### Step 5: Infrastructure Adapter 테스트 커버리지 검사

**파일:** `src/infrastructure/**/adapter.py`

**검사:** 각 Infrastructure Adapter 파일에 대응하는 테스트 파일이 존재하는지 확인합니다.

```bash
find src/infrastructure -name "adapter.py" | grep -v "__pycache__" | sort
```

```bash
find tests/infrastructure -name "test_adapter.py" | grep -v "__pycache__" | sort
```

각 `src/infrastructure/XXX/adapter.py` → `tests/infrastructure/XXX/test_adapter.py`

**PASS:** 모든 Adapter 파일에 대응 테스트 존재
**FAIL:** 테스트 없는 Adapter 파일 존재

---

### Step 6: API Router 테스트 커버리지 검사

**파일:** `src/api/routes/*.py`

**검사:** 각 API Route 파일에 대응하는 테스트 파일이 존재하는지 확인합니다.

```bash
find src/api/routes -name "*.py" ! -name "__init__.py" | sort
```

```bash
find tests/api -name "test_*.py" | grep -v "__pycache__" | sort
```

각 `src/api/routes/XXX.py` → `tests/api/test_XXX.py`

**PASS:** 모든 Router 파일에 대응 테스트 존재
**FAIL:** 테스트 없는 Router 파일 존재

---

### Step 7: 결과 요약 출력

```markdown
## verify-tdd 결과

| 검사 항목 | 상태 | 미커버 수 |
|-----------|------|----------|
| Application UseCase | PASS/FAIL | N개 |
| Application Workflow | PASS/FAIL | N개 |
| Application 서브 UseCase | PASS/FAIL | N개 |
| Domain Policy | PASS/FAIL | N개 |
| Infrastructure Adapter | PASS/FAIL | N개 |
| API Router | PASS/FAIL | N개 |
```

## Output Format

```markdown
### verify-tdd 검증 완료

- 검사 항목: 6개
- 통과: X개
- 이슈: Y개

#### 테스트 없는 모듈
| 소스 파일 | 기대 테스트 경로 | 상태 |
|-----------|-----------------|------|
| `src/application/use_cases/new_use_case.py` | `tests/application/test_new_use_case.py` | 테스트 없음 |
```

## 예외사항

다음은 **위반이 아닙니다**:

1. **`__init__.py` 파일** — 모듈 초기화 파일은 테스트 불필요
2. **`src/infrastructure/logging/` 모듈** — Middleware, Formatter, StructuredLogger는 `tests/infrastructure/logging/`에 별도 테스트 존재 가능
3. **`prompts.py`, `schemas.py` 파일** — 단순 상수/스키마 정의 파일은 독립 테스트 없어도 허용 (상위 어댑터 테스트에서 간접 검증)
4. **`src/infrastructure/pipeline/` 내 nodes** — `tests/infrastructure/pipeline/` 에 테스트가 있으면 OK (파일명이 정확히 일치하지 않아도 허용)
5. **`src/infrastructure/persistence/`** — 데이터베이스 모델/맵퍼는 `tests/infrastructure/test_*.py` 에서 통합 테스트로 커버 가능
6. **`src/config.py`** — 전역 설정 파일은 독립 테스트 없어도 허용
7. **`src/api/main.py`** — DI 연결 파일, `tests/api/test_main.py`가 있으면 OK
