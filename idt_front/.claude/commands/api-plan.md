# API Plan

API 문서를 컨텍스트로 주입하여 `/pdca plan`을 실행한다.

## 입력
- `$ARGUMENTS` : `{task명} [추가 요구사항]`
  - 예: `/api-plan user-auth`
  - 예: `/api-plan user-auth 소셜로그인 추가하고 싶어`
- 첫 번째 단어를 task명으로 인식하고, 나머지는 추가 요구사항으로 처리한다.

## 실행 흐름

### Step 1 - API 문서 탐색
`docs/api/{task명}.md` 파일을 찾는다.

- 파일이 존재하면:
  ```
  📂 API 문서 로드: docs/api/{task명}.md
  ```
- 파일이 없으면:
  ```
  ❌ docs/api/{task명}.md 가 없습니다.
     먼저 /generate-api-docs {task명} 을 실행하세요.
  ```
  이후 종료.

### Step 2 - /pdca plan 실행
API 문서 내용을 컨텍스트로 주입한 채로 `/pdca plan`을 실행한다.

**추가 요구사항이 없는 경우:**
```
다음 API 문서를 참고하여 /pdca plan {task명} 을 실행해줘.
구현 범위, 엔드포인트, 요청/응답 스펙은 아래 API 문서를 기준으로 한다.

---
{docs/api/{task명}.md 전체 내용}
---
```

**추가 요구사항이 있는 경우:**
```
다음 API 문서를 참고하여 /pdca plan {task명} 을 실행해줘.
구현 범위, 엔드포인트, 요청/응답 스펙은 아래 API 문서를 기준으로 한다.

추가 요구사항: {나머지 인자 전체}

---
{docs/api/{task명}.md 전체 내용}
---
```