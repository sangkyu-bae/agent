---
name: api-doc-generator
description: >
  FastAPI 프로젝트의 코드를 자동 분석하여 OpenAPI/Swagger(YAML), Markdown, HTML 형식의 API 문서를 생성합니다.
  routes/ 또는 routers/ 폴더 구조를 탐색하고, 엔드포인트별 요청/응답 예시, 스키마, 인증 방식, 에러 코드를 자동 추출합니다.
  다음 상황에서 반드시 이 skill을 사용하세요:
  - "API 문서 만들어줘", "swagger 생성해줘", "문서화해줘"
  - "엔드포인트 정리해줘", "API 스펙 뽑아줘", "readme에 API 추가해줘"
  - routes/, routers/ 폴더가 있는 FastAPI 프로젝트에서 문서 관련 요청이 올 때
  - OpenAPI, Markdown, HTML 중 어떤 형식이든 API 문서 생성 요청
---

# API Doc Generator Skill

FastAPI 프로젝트를 **코드 분석**하여 세 가지 형식의 API 문서를 자동 생성하는 skill입니다.

## 출력 형식
| 형식 | 파일 | 용도 |
|------|------|------|
| OpenAPI 3.0 | `docs/openapi.yaml` | Swagger UI, Postman import |
| Markdown | `docs/API.md` | GitHub README, 팀 내부 공유 |
| HTML | `docs/index.html` | 브라우저에서 바로 열람 |

---

## Step 1: 프로젝트 구조 파악

```bash
# 프로젝트 루트에서 실행
find . -type f -name "*.py" | grep -E "(route|router|api|endpoint)" | head -30
ls -la routes/ routers/ 2>/dev/null || echo "폴더 확인 필요"
```

탐색 우선순위:
1. `routes/` 또는 `routers/` 폴더의 모든 `.py` 파일
2. `main.py` 또는 `app.py` (라우터 등록 확인)
3. `models/` 또는 `schemas/` (Pydantic 모델 추출)
4. `dependencies/` 또는 `auth/` (인증 방식 파악)

---

## Step 2: 코드 분석 항목

각 라우터 파일에서 아래 항목을 추출합니다.

### 2-1. 엔드포인트 기본 정보
```python
# 추출 대상 패턴
@router.get("/path", tags=["Tag"], summary="요약", description="설명")
@router.post("/path", status_code=201)
@router.put("/path/{id}")
@router.delete("/path/{id}")
@router.patch("/path/{id}")
```

추출 항목:
- HTTP 메서드, 경로, tags, summary, description
- Path/Query/Body 파라미터
- 반환 타입 (`response_model=`)
- `status_code`

### 2-2. 인증/Authorization 방식
```python
# 아래 패턴을 찾아 인증 방식 판별
Depends(get_current_user)        # → Bearer Token (JWT)
Depends(oauth2_scheme)           # → OAuth2
APIKeyHeader(name="X-API-Key")   # → API Key Header
HTTPBasic()                      # → Basic Auth
```

### 2-3. Request/Response 스키마
```python
# Pydantic 모델에서 추출
class UserCreate(BaseModel):
    email: str
    password: str
    name: Optional[str] = None
```

필드별로 타입, 필수 여부, 기본값, `Field(description=...)` 추출.

### 2-4. 에러 코드
```python
# 아래 패턴 탐색
raise HTTPException(status_code=404, detail="Not found")
raise HTTPException(status_code=422, detail="Validation error")
responses={404: {"description": "Not found"}}
```

---

## Step 3: 문서 생성

### 3-1. OpenAPI YAML 생성

`docs/openapi.yaml` 형식 (참고: `references/openapi-template.md`):

```yaml
openapi: "3.0.3"
info:
  title: "{프로젝트명} API"
  version: "1.0.0"
  description: "자동 생성된 API 문서"

servers:
  - url: http://localhost:8000
    description: Local

security:
  - BearerAuth: []   # 인증 방식에 따라 변경

components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

paths:
  /endpoint:
    get:
      summary: "요약"
      tags: [Tag]
      parameters: [...]
      responses:
        "200":
          description: "성공"
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ResponseModel"
              example:
                id: 1
                name: "홍길동"
        "401":
          $ref: "#/components/responses/Unauthorized"
        "404":
          $ref: "#/components/responses/NotFound"

components:
  responses:
    Unauthorized:
      description: "인증 실패"
      content:
        application/json:
          example:
            detail: "Not authenticated"
    NotFound:
      description: "리소스 없음"
      content:
        application/json:
          example:
            detail: "Not found"
  schemas:
    # Pydantic 모델에서 추출한 스키마
```

### 3-2. Markdown 문서 생성

`docs/API.md` 구조:

```markdown
# {프로젝트명} API 문서

> 자동 생성 일시: {날짜}

## 인증

> 모든 API는 `Authorization: Bearer <token>` 헤더가 필요합니다.

---

## {Tag명}

### `GET /endpoint`

**설명**: 엔드포인트 설명

**인증 필요**: ✅ / ❌

#### Query Parameters
| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| page | integer | ❌ | 1 | 페이지 번호 |

#### Request Body
\`\`\`json
{
  "email": "user@example.com",
  "password": "string"
}
\`\`\`

#### Response `200`
\`\`\`json
{
  "id": 1,
  "email": "user@example.com",
  "name": "홍길동"
}
\`\`\`

#### 에러 응답
| 코드 | 설명 |
|------|------|
| 401 | 인증 실패 |
| 404 | 리소스 없음 |
| 422 | 유효성 검사 실패 |

---
```

### 3-3. HTML 문서 생성

`docs/index.html`에 Swagger UI 또는 커스텀 HTML로 생성합니다.

**옵션 A: Swagger UI** (openapi.yaml이 있을 때 권장)
```html
<!DOCTYPE html>
<html>
<head>
  <title>{프로젝트명} API Docs</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist/swagger-ui-bundle.js"></script>
  <script>
    SwaggerUIBundle({ url: "./openapi.yaml", dom_id: '#swagger-ui' })
  </script>
</body>
</html>
```

**옵션 B: 커스텀 HTML** (standalone, CDN 의존성 없음)
- `references/html-template.md` 참고
- 다크/라이트 모드, 사이드바 네비게이션, curl 예시 포함

---

## Step 4: 출력 파일 저장

```bash
mkdir -p docs
# 생성한 파일들을 docs/ 에 저장
```

저장 후 사용자에게 안내:
```
✅ API 문서 생성 완료!

📁 docs/
├── openapi.yaml  → Swagger UI / Postman에서 import
├── API.md        → GitHub에서 바로 보기
└── index.html    → 브라우저에서 열기 (open docs/index.html)

🔗 FastAPI 내장 문서: http://localhost:8000/docs
```

---

## 주의사항 & 팁

- **타입 힌트 없는 함수**: 파라미터 타입을 `any`로 표시하고 주석 추가
- **동적 라우터** (`include_router` 중첩): `main.py`에서 prefix 추적
- **Pydantic v1 vs v2**: `schema()` vs `model_json_schema()` 메서드 차이 인식
- **실제 예시 값 생성**: `Field(example=...)` 또는 `Config.schema_extra` 우선, 없으면 타입 기반으로 합리적인 예시 생성
- FastAPI가 이미 `/openapi.json` 엔드포인트를 제공한다면, 앱을 실행해서 직접 가져오는 방법도 제안할 것:
  ```bash
  curl http://localhost:8000/openapi.json -o docs/openapi.json
  ```

## 참고 파일

- `references/openapi-template.md` — OpenAPI 3.0 전체 스펙 예시
- `references/html-template.md` — 커스텀 HTML 문서 템플릿