# Plan: fix-attachment-upload-401

> Feature: 로그인 사용자의 엑셀 첨부 업로드(`POST /api/v1/agent/attachments`) 401 오류 수정
> Created: 2026-06-07
> Status: Plan
> Task ID: FIX-ATTACH-401

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem (문제)** | 로그인한 사용자가 채팅에서 엑셀 파일을 첨부하면 `POST /api/v1/agent/attachments`가 항상 **401 Unauthorized**로 실패한다. |
| **Solution (해결)** | 프론트엔드 `agentAttachmentService`가 토큰을 주입하지 않는 `apiClient`를 사용 중. 토큰을 주입하는 `authApiClient`로 교체한다 (1줄 수정). |
| **Function UX Effect (기능/UX 효과)** | 엑셀 첨부 업로드가 정상 동작하고, Access Token 만료 시 자동 갱신·재시도까지 적용되어 끊김 없는 업로드 경험 제공. |
| **Core Value (핵심 가치)** | 백엔드 인증 로직은 정상 — 프론트 HTTP 클라이언트 선택 실수를 바로잡아 Agent 엑셀 분석 기능 전체를 복구. |

---

## 1. 목적 (Why)

채팅 화면에서 로그인 상태인 사용자가 엑셀 파일을 첨부(업로드)하면
`POST /api/v1/agent/attachments` 요청이 **401 Unauthorized**로 실패한다.

업로드가 실패하면 발급되어야 할 `file_id`가 없어
이후 `/ws/agent/{run_id}` subscribe 단계의 엑셀 분석 기능 전체가 동작하지 않는다.

---

## 2. 근본 원인 분석

### 호출 흐름

```
ChatInput (엑셀 첨부 클릭)
  → onAttachFile(file)
  → agentAttachmentService.uploadExcel(file)
      └─ import apiClient from '@/services/api/client'   ← ❌ 토큰 미주입 클라이언트
  → POST /api/v1/agent/attachments   (Authorization 헤더 없음)
  → [Backend] get_current_user → security = HTTPBearer()
      └─ 자격증명 없음 → 401 Unauthorized   (decode 전 단계에서 차단)
```

### 원인

프론트엔드에는 **두 개의 axios 클라이언트**가 존재한다.

| 클라이언트 | 파일 | Authorization 토큰 주입 | 401 자동 갱신 |
|-----------|------|:----------------------:|:-------------:|
| `apiClient` | `services/api/client.ts` | ❌ (request 인터셉터가 비어 있음) | ❌ |
| `authApiClient` | `services/api/authClient.ts` | ✅ `Bearer ${accessToken}` 주입 | ✅ refresh 후 재시도 |

`agentAttachmentService.ts:1`이 **토큰을 주입하지 않는 `apiClient`** 를 사용하고 있다.

```ts
// idt_front/src/services/agentAttachmentService.ts:1
import apiClient from '@/services/api/client';   // ← 문제 지점
```

```ts
// idt_front/src/services/api/client.ts:12-15
apiClient.interceptors.request.use((config) => {
  // 인증 토큰 등 공통 헤더 처리   ← 주석만 있고 실제 주입 코드 없음
  return config;
});
```

따라서 업로드 요청에 `Authorization` 헤더가 빠지고,
백엔드 `get_current_user`의 `HTTPBearer()`가 자격증명 부재로 **401**을 반환한다.
(JWT 디코드/유저 조회 단계까지 도달하지도 못함 → 백엔드 인증 로직 자체는 정상)

### 결론

- **백엔드(`agent_attachment_router.py`, `dependencies/auth.py`)는 정상** — 수정 불필요
- 문제는 **프론트엔드의 HTTP 클라이언트 선택 실수** 한 곳

---

## 3. 해결 방안

### 방안 (채택): `authApiClient`로 교체

`agentAttachmentService.ts`의 import를 토큰 주입 클라이언트로 변경한다.

```ts
// Before
import apiClient from '@/services/api/client';
...
const response = await apiClient.post(...);

// After
import authApiClient from '@/services/api/authClient';
...
const response = await authApiClient.post(...);
```

`multipart/form-data` 헤더 지정은 그대로 유지한다.
(axios가 헤더를 병합하므로 인터셉터가 주입한 `Authorization`은 보존됨)

**선택 근거**
- 프로젝트의 인증 필요 서비스(`adminService`, `agentBuilderService`, `agentStoreService` 등 다수)가 이미 `authApiClient`를 표준으로 사용 중 — 일관성 확보
- 토큰 주입뿐 아니라 **401 시 refresh → 재시도** 로직까지 자동 적용되어 토큰 만료 케이스도 함께 해결
- 변경 범위 최소(import 1줄 + 호출 식별자) — 부작용 위험 낮음

### 대안 (미채택)

| 대안 | 미채택 사유 |
|------|------------|
| `apiClient`의 빈 request 인터셉터에 토큰 주입 코드 추가 | `apiClient`는 의도적으로 비인증 호출(로그인/공개 엔드포인트)용으로 분리되어 있어, 전역에 토큰을 주입하면 책임 경계가 무너지고 다른 서비스에 의도치 않은 영향 |

---

## 4. 수정 대상 파일

| # | 파일 | 변경 내용 |
|---|------|----------|
| 1 | `idt_front/src/services/agentAttachmentService.ts` | import를 `apiClient` → `authApiClient`로 교체, 호출부 식별자 변경 |

> 백엔드 파일 수정 없음. `idt/src/api/routes/agent_attachment_router.py` 및 `dependencies/auth.py`는 정상.

---

## 5. 구현 순서

1. **테스트 수정/작성** — `agentAttachmentService.test.ts`에서 업로드 요청에 `Authorization: Bearer ...` 헤더가 포함되는지 검증 (MSW 또는 mock 클라이언트 기준)
2. **서비스 수정** — `agentAttachmentService.ts` import/호출부를 `authApiClient`로 교체
3. **수동 검증** — 로그인 상태에서 채팅 화면 엑셀 첨부 → 201 + `file_id` 발급 확인 → 분석까지 end-to-end 확인

---

## 6. 테스트 계획

| 케이스 | 기대 결과 |
|--------|----------|
| 로그인 상태에서 `uploadExcel(file)` 호출 | 요청에 `Authorization: Bearer {accessToken}` 헤더 포함, 201 응답 |
| 응답에 `file_id` 포함 | 정상 발급, 후속 subscribe에서 참조 가능 |
| Access Token 만료 상태에서 업로드 | 401 → refresh → 재시도 1회 후 성공 (authClient 인터셉터) |
| 미로그인 상태에서 업로드 | 토큰 없음 → 401 → `/login` 리다이렉트 (기존 authClient 동작) |
| 잘못된 확장자/대용량 파일 | 백엔드 400 INVALID_ATTACHMENT / 413 ATTACHMENT_TOO_LARGE 정상 반환 |

---

## 7. 영향 범위

- **직접 영향**: 채팅 화면 엑셀 첨부 업로드 흐름 (정상화)
- **백엔드**: 영향 없음 (수정 없음)
- **다른 프론트 서비스**: 영향 없음 (`agentAttachmentService` 단일 파일 변경)

### 추가 점검 권장 (별도 이슈 후보)

동일하게 토큰 미주입 `apiClient`를 사용하는 서비스 중,
**인증이 필요한 엔드포인트**를 호출하는 곳이 있는지 점검 필요:

```
agentService.ts, chatService.ts, ragService.ts, toolService.ts,
toolAdminService.ts, unifiedUploadService.ts, evalService.ts, embeddingModelService.ts
```

> 특히 `unifiedUploadService.ts`(파일 업로드 계열)는 본 버그와 동일 패턴일 가능성이 높아 우선 점검 대상.
> 단, 본 Plan의 범위는 `agent/attachments` 401에 한정하며, 위 점검은 후속 task로 분리한다.

---

## 8. 의존성

- 없음 — 독립 수정 가능
- `useAuthStore`(`accessToken`/`refreshToken`)가 정상 로딩되어 있음을 전제 (기존 로그인 흐름과 동일)
