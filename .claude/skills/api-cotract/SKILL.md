---
name: api-contract-sync
description: 백엔드 API 스키마나 엔드포인트가 변경될 때 프론트엔드 타입/서비스/훅을 자동으로 동기화한다. `idt/src/api/routes/*.py` 또는 `idt/src/interfaces/schemas/*.py`(혹은 실제 스키마 경로)가 변경된 경우 반드시 이 스킬을 실행한다. 사용자가 "API 바꿨어", "스키마 수정했어", "엔드포인트 추가했어", "타입 맞춰줘" 같은 말을 할 때도 즉시 실행한다.
---

# API Contract Sync

백엔드(Python/FastAPI)와 프론트엔드(TypeScript/React) 사이의 타입 계약을 동기화하는 스킬이다.

## 실행 전 — 변경 내용 파악

먼저 실제로 무엇이 바뀌었는지 확인한다.

```bash
# 변경된 파일 확인
git diff --name-only HEAD

# 스키마/라우터 변경 내용 확인
git diff HEAD -- "src/api/routes/*.py" "src/interfaces/schemas/*.py"
```

확인해야 할 항목:
- 어떤 Request/Response 스키마가 바뀌었는가?
- 새 필드가 추가되었는가? (필수 `field: Type` vs 선택 `field: Optional[Type]`)
- 기존 필드가 삭제 또는 타입 변경되었는가?
- 엔드포인트 URL 또는 HTTP 메서드가 바뀌었는가?

변경 내용을 파악하기 전까지 프론트엔드 파일을 수정하지 않는다.

---

## Step 1 — 프론트엔드 타입 동기화

변경된 스키마에 해당하는 TypeScript 타입 파일을 수정한다.

| 백엔드 | 프론트엔드 |
|--------|-----------|
| `schemas/{Name}Request` | `idt_front/src/types/{name}.ts` |
| `schemas/{Name}Response` | `idt_front/src/types/{name}.ts` |
| `routes/{name}_router.py` (URL 변경) | `idt_front/src/constants/api.ts` |

### 타입 변환 규칙

| Python (Pydantic) | TypeScript |
|-------------------|-----------|
| `str`, `int`, `float`, `bool` | `string`, `number`, `boolean` |
| `Optional[T]` | `T \| undefined` 또는 `field?: T` |
| `List[T]` | `T[]` |
| `datetime` | `string` (ISO 8601) |
| `Enum` | `as const` 객체 또는 TypeScript `enum` |
| `dict` / `Dict[str, T]` | `Record<string, T>` |
| `None` (반환) | `void` 또는 `null` |

**예시:**

백엔드:
```python
class ChatRequest(BaseModel):
    session_id: str
    message: str
    context: Optional[str] = None
```

프론트엔드:
```typescript
export interface ChatRequest {
  session_id: string;
  message: string;
  context?: string;
}
```

---

## Step 2 — 서비스/훅 업데이트

타입이 바뀌면 이를 사용하는 서비스와 훅도 함께 수정한다.

```bash
# 해당 타입을 참조하는 파일 검색
grep -r "{TypeName}" idt_front/src/services/
grep -r "{TypeName}" idt_front/src/hooks/
```

수정 위치:
- `idt_front/src/services/{name}Service.ts` — 함수 파라미터/반환 타입
- `idt_front/src/hooks/use{Name}.ts` — 반환 타입, 상태 타입

---

## Step 3 — API 상수 업데이트 (URL 변경 시)

엔드포인트 URL이 바뀐 경우에만 실행한다.

```typescript
// idt_front/src/constants/api.ts
export const API_ENDPOINTS = {
  // 변경 전
  // CHAT: '/api/v1/conversation/chat',
  // 변경 후
  CHAT: '/api/v1/chat',
} as const;
```

---

## Step 4 — MSW 핸들러 업데이트 (테스트 환경)

`idt_front/src/mocks/handlers.ts`에 해당 엔드포인트 핸들러가 있다면 응답 스키마를 동기화한다.

---

## Step 5 — 검증

```bash
cd idt_front

# TypeScript 타입 오류 확인
npx tsc --noEmit

# 오류가 없으면 완료
```

오류가 발생하면 오류 메시지를 읽고 해당 파일을 수정한 뒤 다시 실행한다.

---

## 완료 보고 형식

동기화가 끝나면 아래 형식으로 요약한다.

```
✅ API Contract Sync 완료

변경된 스키마: ChatRequest, ChatResponse
수정된 파일:
  - idt_front/src/types/chat.ts (session_id 필드 추가)
  - idt_front/src/services/chatService.ts (파라미터 타입 업데이트)
  - idt_front/src/constants/api.ts (URL 변경 없음)

tsc --noEmit: 오류 없음 ✓
```