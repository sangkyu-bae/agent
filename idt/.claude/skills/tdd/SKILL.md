---
name: tdd
description: TDD 방식으로 새 기능을 개발할 때 사용. 테스트 먼저 작성 → 실패 확인 → 구현 → 통과 확인의 엄격한 사이클을 강제한다.
argument-hint: "[task-id 또는 모듈 설명]"
---

# TDD Strict Workflow

`$ARGUMENTS`에 대해 아래 사이클을 컴포넌트마다 반복한다.

## 1. RED: 테스트 먼저 작성

구현 코드보다 테스트 파일을 먼저 생성한다.

**레이어별 mock 규칙:**

| 레이어 | 규칙 |
|--------|------|
| domain | mock 금지 — 순수 로직만 검증 |
| infrastructure | Mock / AsyncMock 사용 |
| application | 의존성 Mock 주입 |

**테스트 네이밍:** `test_<행위>_<조건>_<결과>`

## 2. RED 확인: 실패 검증

```bash
pytest <test_file> -v
```

- "구현이 없어서" 실패해야 함 (ImportError, AttributeError)
- 테스트 문법 오류로 실패하면 테스트 수정 후 재실행

## 3. GREEN: 최소 구현

- 테스트 통과를 위한 최소한의 코드만 작성
- 이 단계에서 테스트 수정 금지
- `pytest <test_file> -v` 로 통과 확인

## 4. REFACTOR (필요 시)

- 테스트 전부 통과한 후에만 리팩토링
- 리팩토링 후 테스트 재실행 확인

## 5. 반복

다음 기능/케이스에 대해 1~4 반복. 한 번에 모든 테스트 작성 금지 — 하나씩 점진적으로.

## 진행 보고 형식

```
[RED]      ✗ test_xxx — ImportError (구현 없음)
[GREEN]    ✓ test_xxx — PASSED
[REFACTOR] 변경 없음 / 요약
```
