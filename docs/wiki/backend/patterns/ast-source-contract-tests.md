---
title: 소스 코드 계약은 AST 테스트로 강제한다 (문자열 grep 금지)
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/tests/application/prompt_composer/test_use_case.py:335-353 (try/except 부재를 ast.Try/ast.ExceptHandler로 검사)
  - idt/tests/application/prompt_composer/test_use_case.py:356-379 (포트 미선언 메서드 호출 검출)
  - idt/src/domain/prompt_composer/interfaces.py:49-91 (PromptRepositoryPort — list_versions 누락 사건의 대상)
  - idt/tests/infrastructure/tool_selection/test_module_boundaries.py (선행 사이클의 AST import 경계 검사)
  - idt/tests/api/test_prompt_composer_router.py:342-350 (라우트 등록은 TestClient 실제 요청으로)
  - idt/tests/api/test_main.py:23 (`route.path` 순회 — 현 FastAPI에서 깨지는 기존 실패)
  - docs/archive/2026-08/prompt-composer/prompt-composer.report.md (§ 실측 표 118-120행)
confidence: 0.85
version: 1
created: 2026-08-18
updated: 2026-08-18
verified_at: 7c3ffdd
---

# 소스 코드 계약은 AST 테스트로 강제한다 (문자열 grep 금지)

## 문제

"이 UseCase에는 try/except가 없다", "application은 포트에 선언된 메서드만 부른다",
"domain은 langchain을 import하지 않는다" — 이런 **소스 형태에 대한 계약**은 리뷰
규율로는 유지되지 않는다. 그렇다고 문자열 검색으로 검사하면 두 가지로 실패한다.

1. **오탐**: 그 계약을 *설명하는* 주석·독스트링에 금지어가 당연히 등장한다.
   prompt_composer의 UseCase는 "try/except가 생기면 실패 경로가 2벌이 된다"는 설계
   근거를 독스트링에 적고 있어서, `"try" in source` 검사는 항상 실패한다.
2. **미탐**: `self._repository.list_versions()` 처럼 **호출은 하는데 어디에도
   선언되지 않은** 것은 문자열로 찾을 대상 자체가 없다.

## 검증된 사실

### 1. "소스에 X가 없다"류는 `ast.walk` 로 노드 타입을 본다

```python
handlers = [n for n in ast.walk(ast.parse(source))
            if isinstance(n, (ast.Try, ast.ExceptHandler))]
assert handlers == []
```

`ast.Try` 만 보면 안 된다 — 문법 형태에 따라 핸들러 노드만 잡히는 경우가 있으니
`ast.ExceptHandler` 를 함께 넣는다. 주석·독스트링은 AST에 노드로 남지 않으므로
오탐이 원천 제거된다.

### 2. **Protocol 포트는 미선언 메서드 호출을 아무도 안 잡는다**

Python `Protocol` 은 구조적 타이핑이라, UseCase가 포트에 없는 메서드를 불러도
정적 검사도 런타임도 통과한다. 실제로 prompt_composer UseCase가 포트에 선언되지
않은 `list_versions()` 를 호출하고 있었는데 **테스트 전체 초록이었다** — 테스트
대역(`_FakeRepo`)에는 그 메서드가 있었기 때문이다. 구현체를 갈아끼우는 순간
`AttributeError` 가 나는 지연 폭탄이다.

검출법: UseCase 소스에서 `self._repository.X` 형태의 속성 접근 이름을 AST로 모아
포트 선언 집합과 부분집합 비교한다.

```python
called = {n.attr for n in ast.walk(ast.parse(source))
          if isinstance(n, ast.Attribute)
          and isinstance(n.value, ast.Attribute)
          and n.value.attr == "_repository"}
declared = {n for n in dir(PromptRepositoryPort) if not n.startswith("_")}
assert called and called <= declared, f"포트 미선언 호출: {called - declared}"
```

`called and` 가 중요하다 — 필드명을 리팩터링으로 바꾸면 `called` 가 빈 집합이 되어
부분집합 조건이 **공허하게 참**이 된다(빈 집합은 모든 집합의 부분집합). 비어 있지
않음을 함께 단언해야 테스트가 죽지 않는다.

### 3. 선행 사례 — import 경계도 같은 도구로

`tests/infrastructure/tool_selection/test_module_boundaries.py` 가 `domain/**` 의
import를 AST로 파싱해 표준 라이브러리·자기 패키지 외 참조 0을 검사한다
([[detachable-module-seam]] §4). CLAUDE.md §6의 "domain → infrastructure 참조 금지"를
사람이 아니라 CI가 지키게 하는 유일한 수단이다.

### 4. 반대로, **라우트 등록은 정적으로 검증할 수 없다**

현재 이 저장소의 FastAPI 버전은 `include_router()` 를 `_IncludedRouter` 객체로
**지연 보관**한다. 그래서 `app.routes` 를 순회하며 `route.path` 를 읽는 방식은
`'_IncludedRouter' object has no attribute 'path'` 로 깨진다. 기존 실패
`tests/api/test_main.py:23` 이 정확히 이 원인이다.

등록 검증은 **실제 요청**으로 한다:

```python
app = FastAPI(); app.include_router(router)
app.dependency_overrides[get_use_case] = lambda: StubUseCase()
res = TestClient(app).post("/api/v1/prompt-composer/compose", json=_body())
assert res.status_code != 200   # 인증 가드가 살아 있음 = 라우트도 살아 있음
```

404가 아니라는 것(예: 인증 가드 때문에 401)이 곧 "경로가 등록됐다"의 증거다.

## 다음에 적용하는 법

1. Design에 "…하지 않는다"류 계약을 적었으면 **그 계약을 검사하는 AST 테스트를
   같은 커밋에 넣는다.** 계약은 문서가 아니라 테스트에 산다.
2. 새 모듈의 테스트 패키지에 다음 3종을 복제한다 — (a) import 경계, (b) 금지
   구문 부재, (c) 포트 미선언 호출 검출. 셋 다 20줄 미만이고 모듈마다 경로 문자열만
   바꾸면 된다.
3. 집합 비교 단언은 항상 **비어 있지 않음을 함께 단언**한다(공허한 참 방지).
4. 라우터 등록·미들웨어 적용처럼 프레임워크 내부 구조에 의존하는 검증은
   `TestClient` 실제 요청으로만 한다. `app.routes` 순회 금지.
5. `Path(__file__).resolve().parents[N]` 로 소스 경로를 잡을 때 N을 검증하라 —
   테스트 디렉터리 깊이가 바뀌면 조용히 다른 파일을 읽는다(현재 `parents[3]`이
   `idt/` 루트).

## 관련 문서

- LLM 스키마 필드 집합 동등 비교: `backend/patterns/llm-output-trust-boundary.md`
- 탈착 경계 검사의 원형: `backend/patterns/detachable-module-seam.md`
- 초록인데 검증 안 된 게이트들: `conventions/false-green-quality-gates.md`
