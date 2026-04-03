# OpenAPI 3.0 전체 스펙 참고 템플릿

## 인증 방식별 securitySchemes

```yaml
components:
  securitySchemes:
    # JWT Bearer
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

    # API Key (Header)
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key

    # OAuth2
    OAuth2:
      type: oauth2
      flows:
        password:
          tokenUrl: /auth/token
          scopes:
            read: 읽기 권한
            write: 쓰기 권한

    # Basic Auth
    BasicAuth:
      type: http
      scheme: basic
```

## 파라미터 타입별 예시

```yaml
parameters:
  # Path 파라미터
  - name: user_id
    in: path
    required: true
    schema:
      type: integer
    example: 42

  # Query 파라미터
  - name: page
    in: query
    required: false
    schema:
      type: integer
      default: 1
      minimum: 1
    description: 페이지 번호

  - name: search
    in: query
    required: false
    schema:
      type: string
    description: 검색어

  # Header 파라미터
  - name: X-Request-ID
    in: header
    required: false
    schema:
      type: string
      format: uuid
```

## Pydantic → OpenAPI 스키마 변환

| Pydantic 타입 | OpenAPI 타입 |
|--------------|-------------|
| `str` | `type: string` |
| `int` | `type: integer` |
| `float` | `type: number` |
| `bool` | `type: boolean` |
| `list[str]` | `type: array, items: {type: string}` |
| `Optional[str]` | `type: string, nullable: true` |
| `datetime` | `type: string, format: date-time` |
| `UUID` | `type: string, format: uuid` |
| `EmailStr` | `type: string, format: email` |

## 공통 에러 응답 컴포넌트

```yaml
components:
  responses:
    BadRequest:
      description: 잘못된 요청
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/HTTPError'
          example:
            detail: "Invalid input"

    Unauthorized:
      description: 인증 실패
      content:
        application/json:
          example:
            detail: "Not authenticated"

    Forbidden:
      description: 권한 없음
      content:
        application/json:
          example:
            detail: "Not enough permissions"

    NotFound:
      description: 리소스 없음
      content:
        application/json:
          example:
            detail: "Item not found"

    UnprocessableEntity:
      description: 유효성 검사 실패 (FastAPI 422)
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ValidationError'

  schemas:
    HTTPError:
      type: object
      properties:
        detail:
          type: string

    ValidationError:
      type: object
      properties:
        detail:
          type: array
          items:
            type: object
            properties:
              loc:
                type: array
                items:
                  type: string
              msg:
                type: string
              type:
                type: string
```

## 페이지네이션 응답 패턴

```yaml
schemas:
  PaginatedResponse:
    type: object
    properties:
      items:
        type: array
        items:
          $ref: '#/components/schemas/Item'
      total:
        type: integer
        example: 100
      page:
        type: integer
        example: 1
      size:
        type: integer
        example: 20
      pages:
        type: integer
        example: 5
```