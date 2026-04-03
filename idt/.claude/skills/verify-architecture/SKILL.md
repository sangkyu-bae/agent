---
name: verify-architecture
description: DDD 레이어 의존성 규칙 준수 여부를 검증합니다. 새 모듈 추가 후, PR 전, 레이어 간 임포트 변경 후 사용.
---

# 아키텍처 레이어 검증

## 목적

Thin DDD 아키텍처 규칙 준수 여부를 검증합니다:

1. **Domain → Infrastructure 금지**: `src/domain/` 에서 `src/infrastructure/` 임포트 금지
2. **Domain → LangGraph/LangChain 금지**: `src/domain/` 에서 `langgraph` 임포트 금지 (`langchain_core.documents.Document` 예외)
3. **Router 비즈니스 로직 금지**: `src/api/routes/` 에서 직접 Infrastructure 서비스 인스턴스화 금지
4. **Infrastructure 정책 금지**: `src/infrastructure/` 에서 비즈니스 규칙(Policy 클래스 정의) 금지
5. **Application → Domain 단방향**: Application 레이어는 Infrastructure Adapter와 Domain만 참조 허용

## 실행 시점

- 새로운 모듈을 추가한 후
- 레이어 간 임포트를 수정한 후
- Pull Request를 생성하기 전
- 아키텍처 드리프트가 의심될 때

## Related Files

| File | Purpose |
|------|---------|
| `src/domain/logging/interfaces/logger_interface.py` | Domain 레이어 기본 인터페이스 예시 |
| `src/domain/hallucination/policy.py` | Domain Policy 예시 |
| `src/infrastructure/hallucination/adapter.py` | Infrastructure Adapter 예시 |
| `src/application/hallucination/use_case.py` | Application UseCase 예시 |
| `src/api/routes/analysis_router.py` | API Route 예시 |
| `src/api/main.py` | DI 연결 위치 (Infrastructure 참조 허용) |

## Workflow

### Step 1: Domain → Infrastructure 임포트 검사

**파일:** `src/domain/**/*.py`

**검사:** domain 레이어에서 infrastructure를 직접 임포트하는지 확인합니다.

```bash
grep -rn "from src.infrastructure\|import src.infrastructure" src/domain/ --include="*.py"
```

**PASS:** 출력 없음 (0건)
**FAIL:** 1건 이상 — `src/domain/XXX.py`에서 `src.infrastructure.*`를 임포트하고 있음

**수정 방법:** domain에서 interface(추상 클래스)를 정의하고, infrastructure에서 구현. application/api에서 DI로 연결.

---

### Step 2: Domain → LangGraph 임포트 검사

**파일:** `src/domain/**/*.py`

**검사:** domain 레이어에서 LangGraph를 임포트하는지 확인합니다.

```bash
grep -rn "^from langgraph\|^import langgraph" src/domain/ --include="*.py"
```

**PASS:** 출력 없음 (0건)
**FAIL:** 1건 이상 — domain에서 LangGraph를 사용하고 있음

**수정 방법:** LangGraph StateGraph는 `src/application/` 또는 `src/infrastructure/` 레이어로 이동.

---

### Step 3: Domain → LangChain (langgraph 제외) 임포트 검사

**파일:** `src/domain/**/*.py`

**검사:** domain 레이어에서 LangChain 처리 기능을 임포트하는지 확인합니다. (`langchain_core.documents.Document`는 데이터 타입으로 허용)

```bash
grep -rn "^from langchain\|^import langchain" src/domain/ --include="*.py" | grep -v "langchain_core.documents import Document"
```

**PASS:** 출력 없음 (0건)
**FAIL:** 1건 이상 — domain에서 LangChain 처리 기능을 사용하고 있음

**수정 방법:** LangChain Retriever, Chain, Tool 등은 `src/infrastructure/` 또는 `src/application/` 레이어로 이동.

---

### Step 4: API Routes → Infrastructure 직접 인스턴스화 검사

**파일:** `src/api/routes/**/*.py`

**검사:** routes에서 Infrastructure 서비스를 직접 생성하는지 확인합니다 (로깅 모듈 제외).

```bash
grep -rn "from src.infrastructure" src/api/routes/ --include="*.py" | grep -v "logging"
```

**PASS:** 출력 없음 (0건)
**FAIL:** 1건 이상 — routes에서 Infrastructure를 직접 임포트하고 있음

**수정 방법:** Infrastructure 인스턴스화는 `src/api/main.py`의 `create_app()`에서 DI로 처리. Routes는 `Depends(get_xxx_use_case)` 패턴만 사용.

---

### Step 5: Infrastructure 내 Policy 클래스 정의 검사

**파일:** `src/infrastructure/**/*.py`

**검사:** infrastructure 레이어에서 비즈니스 규칙을 담은 Policy 클래스를 정의하는지 확인합니다.

```bash
grep -rn "^class.*Policy\b" src/infrastructure/ --include="*.py"
```

**PASS:** 출력 없음 (0건)
**FAIL:** 1건 이상 — infrastructure에 Policy 클래스가 존재함

**수정 방법:** Policy 클래스는 `src/domain/*/policy*.py` 또는 `src/domain/policies/` 로 이동.

---

### Step 6: 결과 요약 출력

```markdown
## verify-architecture 결과

| 검사 항목 | 상태 | 위반 수 |
|-----------|------|---------|
| Domain → Infrastructure 임포트 | PASS/FAIL | N건 |
| Domain → LangGraph 임포트 | PASS/FAIL | N건 |
| Domain → LangChain 처리 기능 임포트 | PASS/FAIL | N건 |
| API Routes → Infrastructure 직접 인스턴스화 | PASS/FAIL | N건 |
| Infrastructure Policy 클래스 정의 | PASS/FAIL | N건 |
```

## Output Format

```markdown
### verify-architecture 검증 완료

- 검사 항목: 5개
- 통과: X개
- 이슈: Y개

#### 발견된 이슈
| 파일 | 문제 | 수정 방법 |
|------|------|-----------|
| `src/domain/xxx.py:10` | infrastructure 임포트 | Interface 추상화 후 DI 적용 |
```

## 예외사항

다음은 **위반이 아닙니다**:

1. **`langchain_core.documents.Document` 임포트** — domain 레이어에서 데이터 타입으로 사용하는 것은 허용. `from langchain_core.documents import Document` 패턴
2. **`src/api/main.py`의 Infrastructure 임포트** — `main.py`는 DI 연결 전담 파일로, infrastructure 임포트가 필요하고 허용됨
3. **`src/api/routes/`에서 `get_logger()`** — 로깅 모듈(`src/infrastructure/logging`)은 routes에서도 사용 허용
4. **Infrastructure → Domain 임포트** — 올바른 방향 (infrastructure는 domain interface를 구현), 위반 아님
5. **Application → Infrastructure Adapter 임포트** — Application 레이어는 Infrastructure Adapter와 연결하는 역할, 허용됨
