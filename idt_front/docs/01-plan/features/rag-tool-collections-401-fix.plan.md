# rag-tool-collections-401-fix Plan

> Agent Builder 페이지에서 내부문서검색 도구 설정 시 컬렉션 목록 조회 401 오류 수정

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | RAG Tool Collections 401 인증 오류 수정 |
| 작성일 | 2025-05-05 |
| 예상 소요 | 15분 (단순 import 변경) |
| 영향 범위 | `ragToolService.ts` 1개 파일 |

### Value Delivered

| 관점 | 설명 |
|------|------|
| Problem | Agent Builder에서 내부문서검색 도구 추가 시 컬렉션 목록이 401로 로드되지 않음 |
| Solution | `ragToolService`의 HTTP 클라이언트를 `apiClient` → `authApiClient`로 교체 |
| Function UX Effect | 도구 설정 단계에서 컬렉션 목록이 정상 표시되어 에이전트 생성 흐름 완성 |
| Core Value | 인증 보호 엔드포인트에 대한 클라이언트 일관성 확보 |

---

## 1. 배경 및 목표

### AS-IS (현재 문제)

- `ragToolService.ts`가 **`apiClient`** (공개 엔드포인트 전용, 토큰 미주입)를 사용
- 백엔드 `GET /api/v1/rag-tools/collections`는 `Depends(get_current_user)`로 **JWT 인증 필수**
- 결과: 프론트에서 호출 시 `Authorization` 헤더가 빠져 **401 Unauthorized** 반환

### TO-BE (목표)

- `ragToolService.ts`가 **`authApiClient`** (Bearer 토큰 자동 주입 + 401 시 refresh 재시도)를 사용
- Agent Builder 페이지에서 컬렉션 목록이 정상 로드됨

---

## 2. 원인 분석

### 클라이언트 비교

| 클라이언트 | 파일 | 토큰 주입 | 용도 |
|-----------|------|-----------|------|
| `apiClient` | `services/api/client.ts` | ❌ 없음 | 공개 엔드포인트 (로그인 전 접근 가능) |
| `authApiClient` | `services/api/authClient.ts` | ✅ Bearer 자동 | 인증 필요 엔드포인트 |

### 문제 코드 위치

```typescript
// src/services/ragToolService.ts (Line 1)
import apiClient from '@/services/api/client';  // ← 잘못된 클라이언트
```

### 백엔드 인증 요구사항

```python
# idt/src/api/routes/rag_tool_router.py (Line 53-55)
@router.get("/collections", response_model=CollectionsResponse)
async def list_collections(
    current_user: User = Depends(get_current_user),  # ← JWT 필수
```

---

## 3. 수정 계획

### 3-1. ragToolService.ts 클라이언트 교체

**변경 내용**: `apiClient` → `authApiClient` import 변경

```typescript
// Before
import apiClient from '@/services/api/client';

// After
import authApiClient from '@/services/api/authClient';
```

모든 `apiClient.get(...)` 호출을 `authApiClient.get(...)`으로 변경.

### 3-2. 영향 분석

| 엔드포인트 | 인증 필요 여부 | 변경 후 동작 |
|-----------|:---:|------|
| `GET /api/v1/rag-tools/collections` | ✅ | 토큰 자동 주입 → 정상 응답 |
| `GET /api/v1/rag-tools/metadata-keys` | ❌ (현재 미인증) | authClient 사용해도 문제 없음 (토큰이 있으면 보내고, 백엔드가 무시) |

> metadata-keys는 현재 `get_current_user` 없이 동작하지만, 같은 도메인이므로 일관성을 위해 `authApiClient`로 통일.

---

## 4. 검증 방법

1. Agent Builder 페이지 접속
2. 내부문서검색 도구 추가 단계 진입
3. 컬렉션 드롭다운에 목록이 로드되는지 확인
4. 브라우저 DevTools Network 탭에서 `/api/v1/rag-tools/collections` 요청 헤더에 `Authorization: Bearer ...` 존재 확인
5. 401 대신 200 응답 확인

---

## 5. 리스크

| 리스크 | 확률 | 대응 |
|--------|:---:|------|
| accessToken 만료 상태에서 호출 | 낮음 | authApiClient가 자동 refresh 후 재시도 |
| 로그인 전 페이지 접근 | 없음 | Agent Builder는 ProtectedRoute 내부이므로 비인증 시 /login 리다이렉트 |

---

## 6. 완료 기준

- [ ] `ragToolService.ts`에서 `authApiClient` 사용
- [ ] Agent Builder 페이지에서 컬렉션 목록 정상 로드 (200 응답)
- [ ] 기존 테스트 통과 (`useRagToolConfig.test.ts`)
