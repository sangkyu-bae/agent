# Plan: LLM 모델 관리 어드민 페이지 (llm-register)

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | llm-register |
| 작성일 | 2026-07-11 |
| 예상 소요 | 5~7시간 (타입/서비스/훅 1.5h + 페이지·모달 3h + 네비/라우팅 0.5h + 테스트 1~2h) |
| 참조 API 문서 | `docs/api/llm-register.md` (백엔드 `src/api/routes/llm_model_router.py` 구현 완료) |

### Value Delivered

| 관점 | 설명 |
|------|------|
| **Problem** | 백엔드에는 LLM 모델 CRUD + 가격 관리 API 6종이 모두 구현되어 있으나, 프론트엔드는 목록 조회(GET) 1종만 연동됨. 관리자가 모델을 등록·수정·가격변경·비활성화하려면 API를 직접 호출해야 하고, admin 영역 6개 페이지 어디에도 LLM 모델 관리 메뉴가 없음 |
| **Solution** | `/admin/llm-models` 어드민 페이지 신설 — 모델 테이블 + 등록/수정 모달 + 가격 변경 모달 + 비활성화 확인 다이얼로그. 기존 `llmModelService`/`useLlmModels`를 mutation까지 확장하고 admin 네비게이션에 항목 추가 |
| **Function UX Effect** | 관리자가 UI에서 모델 등록(provider, model_name, api_key_env, base_url 등) → 목록에서 기본 모델 지정·수정 → 가격 설정으로 비용 집계 활성화 → 미사용 모델 비활성화까지 전 과정을 수행. 에이전트 빌더 모델 선택 목록에 즉시 반영 |
| **Core Value** | 에이전트 실행·문서 요약·비용 계산이 모두 참조하는 LLM 모델 레지스트리를 코드 배포 없이 운영 가능. 가격 관리로 AGENT-OBS 비용 집계 정확성 확보 |

---

## 1. 현재 상황 분석

### 1.1 백엔드 (구현 완료 — 변경 없음)

`idt/src/api/routes/llm_model_router.py` (LLM-MODEL-REG-001 §7, LLM-MODEL-REG-002, AGENT-OBS M4):

| Method | Path | Auth | 프론트 연동 상태 |
|--------|------|------|-----------------|
| GET | `/api/v1/llm-models` | user | ✅ `llmModelService.getLlmModels` |
| GET | `/api/v1/llm-models/{id}` | user | ❌ 미연동 |
| POST | `/api/v1/llm-models` | admin | ❌ 미연동 |
| PATCH | `/api/v1/llm-models/{id}` | admin | ❌ 미연동 |
| PATCH | `/api/v1/llm-models/{id}/pricing` | admin | ❌ 미연동 (비용 캐시 무효화 포함) |
| DELETE | `/api/v1/llm-models/{id}` | admin | ❌ 미연동 (soft delete) |

### 1.2 프론트엔드 현황 (갭)

| 레이어 | 현재 | 갭 |
|--------|------|-----|
| `constants/api.ts` | `LLM_MODELS`만 존재 | 단건/가격 경로 함수 없음 |
| `types/llmModel.ts` | `LlmModel` (조회용 최소 필드) | 가격 3필드(`input_price_per_1k_usd`, `output_price_per_1k_usd`, `pricing_updated_at`) 부재, Request 타입 3종 부재 |
| `services/llmModelService.ts` | `getLlmModels`만 존재 | 단건 조회 + 뮤테이션 4종 부재 |
| `lib/queryKeys.ts` | `llmModels.all` / `list` | `detail(id)` 부재 |
| `hooks/useLlmModels.ts` | 조회 쿼리만 존재 | 뮤테이션 훅 부재 |
| admin 영역 | 6개 페이지(`users`, `departments`, `ragas`, `agent-runs`, `mcp-servers`, `skills`) | **LLM 모델 관리 페이지·라우트·네비 항목 없음** |

### 1.3 스펙 유의사항 (백엔드 스키마 실측 확인)

- **가격 필드는 JSON에서 문자열**로 직렬화됨 (`Decimal` → `"0.0025"`). 프론트 타입은 `string | null`, 표시·입력 시 변환 필요.
- **`api_key_env`는 등록 시에만 전달** (write-only). 응답에 노출되지 않으므로 수정 모달에는 표시하지 않음. `provider`, `model_name`, `api_key_env`는 수정 불가(식별자 성격).
- **가격은 등록 시 설정 불가** — 등록 후 `PATCH /{id}/pricing`으로만 설정 (별도 모달 분리 근거).
- **`is_default=true` 지정 시 기존 기본 모델 자동 해제** (서버 처리) → 목록 invalidate로 반영.
- **비활성화 영향**: 비활성 모델을 참조 중인 에이전트 실행·요약 잡은 실행 시점 실패 → 비활성화 확인 다이얼로그에 경고 문구 필수.
- 에러 매핑: POST 409(provider+model_name 중복), 404(단건/수정/가격/비활성화), 422(검증 실패).

### 1.4 기존 소비처 (회귀 주의)

`useLlmModels`는 에이전트 빌더(`ModelSettingsModal`, `SubAgentManagerModal`, `LeftConfigPanel` 등)에서 모델 선택 목록으로 사용 중. 뮤테이션 후 `queryKeys.llmModels.all` invalidate로 빌더 측 목록도 자동 갱신되도록 한다. 기존 훅 시그니처는 변경하지 않는다.

---

## 2. 구현 범위

### 2.1 In-Scope

| # | 항목 | 설명 |
|---|------|------|
| 1 | 엔드포인트 상수 | `LLM_MODEL_DETAIL: (id) => \`/api/v1/llm-models/${id}\``, `LLM_MODEL_PRICING: (id) => \`/api/v1/llm-models/${id}/pricing\`` |
| 2 | 타입 확장 | `LlmModel`에 가격 3필드 추가(`string \| null`) + `CreateLlmModelRequest`, `UpdateLlmModelRequest`, `UpdateLlmModelPricingRequest` 신설 (백엔드 `schemas.py`와 1:1) |
| 3 | 서비스 확장 | `getLlmModel(id)`, `createLlmModel`, `updateLlmModel`, `updateLlmModelPricing`, `deactivateLlmModel` — 모두 `authClient` 사용 |
| 4 | 쿼리 키 | `queryKeys.llmModels.detail(id)` 추가 |
| 5 | 뮤테이션 훅 | `useCreateLlmModel`, `useUpdateLlmModel`, `useUpdateLlmModelPricing`, `useDeactivateLlmModel` — 성공 시 `llmModels.all` invalidate |
| 6 | `AdminLlmModelsPage` | 패턴 A 레이아웃(고정 헤더 + 스크롤 바디, `max-w-7xl`). 테이블 + 비활성 포함 토글 + 모달 3종 + 비활성화 `ConfirmDialog` |
| 7 | 라우팅/네비 | `App.tsx` `AdminRoute` 하위에 `/admin/llm-models` 추가, `constants/adminNav.ts`의 `ADMIN_NAV_ITEMS`에 "LLM 모델" 항목 추가 (TopNav 드롭다운·admin 사이드바 자동 반영) |
| 8 | 테스트 (TDD) | MSW 핸들러 + 서비스/훅 테스트 + 페이지 상호작용 테스트 |

### 2.2 페이지 UI 사양

**테이블 컬럼**: 표시명(+ 기본 모델 배지) / Provider / 모델명(`model_name`) / 상태(활성·비활성) / 입력 단가 / 출력 단가(1K당 USD, 미설정 시 "미설정" 뱃지) / base_url(설정 시 축약 표시) / 액션(수정 · 가격 · 비활성화)

| 요소 | 사양 |
|------|------|
| 비활성 포함 토글 | 헤더 우측 체크박스/토글 → `include_inactive=true` 재조회. 비활성 행은 흐리게 표시 |
| 등록 모달 | provider(셀렉트: openai/anthropic/ollama/perplexity), model_name, display_name, api_key_env(필수), description, max_tokens, base_url, is_active, is_default. 409 응답 시 인라인 에러("이미 등록된 모델") |
| 수정 모달 | display_name, description, max_tokens, base_url, is_active, is_default만 편집 (provider/model_name/api_key_env는 읽기 전용 표시 또는 미노출). 비활성 모델 재활성화도 이 모달의 is_active 토글로 수행 |
| 가격 모달 | input/output 단가 2필드 (number 입력, ≥ 0 검증). 현재 단가·`pricing_updated_at` 표시. 저장 성공 시 "비용 캐시가 갱신되었습니다" 안내 |
| 비활성화 | 공통 `ConfirmDialog`(variant: danger) — "이 모델을 참조 중인 에이전트 실행·문서 요약이 실패할 수 있습니다" 경고 포함 |
| 모달 공통 | 기존 공통 `Modal` 컴포넌트(`components/common/Modal.tsx`) 사용, 어드민 기존 페이지(AdminMcpServersPage 등)의 폼/버튼 스타일 답습 |

### 2.3 Out-of-Scope

- 백엔드 API 변경 없음 (기 구현 6종 그대로 사용)
- 모델 물리 삭제(백엔드 미지원 — soft delete만)
- `api_key_env` 수정 기능 (백엔드 `UpdateLlmModelRequest`에 없음)
- 모델 사용량/비용 통계 표시 (기존 `/admin/agent-runs` 관측 페이지 담당)
- 에이전트 빌더 측 UI 변경 (캐시 invalidate로 자동 반영만 확인)

---

## 3. 구현 순서 (TDD)

### Step 1: 타입 + 상수 + 서비스 (Red → Green)

`types/llmModel.ts` 확장, `constants/api.ts` 경로 함수 2종, `llmModelService` 메서드 5종 추가.
MSW 핸들러(`__tests__/mocks/handlers.ts`)에 llm-models CRUD 핸들러 추가.

- 테스트: 각 메서드가 올바른 경로·메서드·바디로 호출되고 응답을 반환하는지 (기존 `getLlmModels` 테스트 그린 유지).

### Step 2: 쿼리 키 + 뮤테이션 훅 (Red → Green)

`lib/queryKeys.ts`에 `detail(id)`, `hooks/useLlmModels.ts`(또는 동일 파일 내)에 뮤테이션 훅 4종.

- 테스트: 뮤테이션 성공 → `llmModels` 목록 쿼리 invalidate 확인 (`useLlmModels.test.ts` 확장, MSW 파일별 `server.listen` 3종 훅 직접 선언).

### Step 3: AdminLlmModelsPage (Red → Green)

`src/pages/AdminLlmModelsPage/index.tsx` — 테이블 렌더/빈 상태/로딩, 등록·수정·가격 모달, 비활성화 ConfirmDialog, include_inactive 토글.

- 테스트: 목록 렌더 / 등록 플로우(폼 입력 → POST → 목록 갱신) / 수정 모달 프리필 / 가격 모달 검증(음수 거부) / 비활성화 확인 다이얼로그 / 409 에러 표시.

### Step 4: 라우팅 + 네비게이션 (Red → Green)

`App.tsx` AdminRoute 하위 라우트 추가, `constants/adminNav.ts` 항목 추가(아이콘: cpu-chip 계열 Heroicons path).

- 테스트: adminNav 항목 존재 검증(기존 admin-navigation-entry 테스트 패턴 답습).

### Step 5: 전체 검증

`npm run test:run -- --pool=threads` + `npm run type-check` + `npm run lint`.
사전 실패 8건(기존 이슈)은 회귀로 오인하지 않는다.

---

## 4. 영향 파일 목록

### 신규

| 파일 | 내용 |
|------|------|
| `src/pages/AdminLlmModelsPage/index.tsx` (+test) | LLM 모델 관리 어드민 페이지 |

### 수정

| 파일 | 변경 |
|------|------|
| `src/constants/api.ts` | `LLM_MODEL_DETAIL`, `LLM_MODEL_PRICING` 추가 |
| `src/types/llmModel.ts` | 가격 3필드 + Request 타입 3종 |
| `src/services/llmModelService.ts` | 메서드 5종 추가 |
| `src/lib/queryKeys.ts` | `llmModels.detail(id)` |
| `src/hooks/useLlmModels.ts` (+test) | 뮤테이션 훅 4종 |
| `src/constants/adminNav.ts` | "LLM 모델" 네비 항목 |
| `src/App.tsx` | `/admin/llm-models` 라우트 |
| `src/__tests__/mocks/handlers.ts` | llm-models CRUD MSW 핸들러 |

---

## 5. 리스크

| 리스크 | 대응 |
|--------|------|
| 가격 필드 타입 불일치 (JSON 문자열 vs number 입력) | 타입은 `string \| null`로 정의, 가격 모달에서 `parseFloat` 검증 후 number로 전송 (백엔드 Decimal 수용) |
| 에이전트 빌더 모델 목록 회귀 | `useLlmModels` 시그니처 불변 + `llmModels.all` invalidate만 추가. 빌더 관련 기존 테스트 그린 확인 |
| 비활성화로 인한 운영 사고 | ConfirmDialog에 참조 실패 경고 명시, soft delete라 수정 모달에서 재활성화 가능함을 안내 |
| `is_default` 동시성 (서버 자동 해제) | 낙관적 업데이트 미사용 — invalidate 후 서버 상태 재조회로 단순화 |
| 409/404/422 에러 UX | axios 에러의 `detail` 메시지를 모달 내 인라인 에러로 표시 (AdminMcpServersPage 패턴 답습) |

---

## 6. 완료 기준 (Acceptance Criteria)

1. 관리자로 로그인 시 관리 메뉴(TopNav 드롭다운·admin 사이드바)에 "LLM 모델" 항목이 보이고 `/admin/llm-models`로 진입된다 (비admin은 `AdminRoute`에 의해 차단).
2. 모델 목록 테이블에 provider·모델명·표시명·활성/기본 상태·입출력 단가·base_url이 표시되고, 토글로 비활성 모델 포함 조회가 된다.
3. 등록 모달에서 필수 필드 검증 후 등록 성공 시 목록에 반영되고, 중복(409) 시 인라인 에러가 표시된다.
4. 수정 모달에서 display_name·description·max_tokens·base_url·is_active·is_default를 변경할 수 있고, provider·model_name·api_key_env는 편집 불가하다.
5. 가격 모달에서 단가 저장 시 목록의 단가와 `pricing_updated_at`이 갱신된다 (음수 입력은 클라이언트 검증으로 거부).
6. 비활성화 시 경고 다이얼로그를 거쳐 `is_active=false`로 표시되며, 수정 모달에서 재활성화할 수 있다.
7. 모델 등록/수정 후 에이전트 빌더의 모델 선택 목록에 별도 새로고침 없이 반영된다 (쿼리 invalidate).
8. 기존 테스트 스위트 그린 (사전 실패 8건 제외) + 신규 테스트 통과, `type-check`·`lint` 통과.
