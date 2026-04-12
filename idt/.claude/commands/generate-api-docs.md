# Generate API Docs

주어진 task명으로 API 문서를 생성한다.

## 입력
- `$ARGUMENTS` : task명 (예: `/generate-api-docs user-auth`)

## 탐색 및 판단 흐름

### Step 1 - design 파일 탐색
`docs/archive/` 하위에서 `{task명}` 폴더를 찾아 파일명에 `design` 이 포함된 파일을 읽는다.

읽은 후 아래를 출력한다:
```
📂 읽은 파일: docs/archive/yyyy-mm/{task명}/{파일명}
```

### Step 2 - design 충분 여부 판단
design 파일을 읽은 후 API 문서 생성에 충분한지 판단하고 아래 중 하나를 출력한다:

- 충분한 경우:
```
✅ design 문서만으로 충분합니다. API 문서를 생성합니다.
```

- 부족한 경우 (이유 포함):
```
⚠️ design 문서만으로 부족합니다. 이유: {예: 응답 스펙 누락, 에러 코드 없음 등}
→ report 파일을 추가로 탐색합니다.
```

### Step 3 - 부족한 경우 report, plan 순으로 추가 탐색
파일명에 `report`, 그 다음 `plan` 이 포함된 파일을 순서대로 읽는다.
읽을 때마다 아래를 출력한다:
```
📂 읽은 파일: docs/archive/yyyy-mm/{task명}/{파일명}
```
충분해지는 시점에 탐색을 멈춘다.

### Step 4 - API 스펙 없음
모든 파일을 읽어도 API 설계가 없으면 아래를 출력하고 종료한다:
```
❌ API 스펙이 없는 task입니다.
```

## 출력
- `docs/api/` 폴더가 없으면 생성
- 이미 `docs/api/{task명}.md` 가 존재하면 덮어쓰기 전에 확인

`docs/api/{task명}.md` 를 아래 포맷으로 생성:

```markdown
# {task명} API

> {한 줄 기능 요약}

## 개요

| 항목 | 내용 |
|------|------|
| Base URL | |
| Auth | |

---

## 엔드포인트 목록

| Method | Path | 설명 |
|--------|------|------|

---

## 상세 스펙

### {Method} {Path}

{설명}

**Request**
\```json
\```

**Response**
\```json
\```

**Error Codes**

| 코드 | 설명 |
|------|------|
```