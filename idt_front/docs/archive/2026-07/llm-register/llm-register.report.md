# llm-register Completion Report

> **Summary**: LLM 모델 관리 어드민 페이지 완성 — 백엔드에 기 구현된 LLM 모델 CRUD + 가격 관리 API 6종을 프론트에 전면 연동하여 `/admin/llm-models` 페이지를 신설. Gap 분석 98.3% → Act 보정 1회로 **최종 Match Rate 100%**.
>
> **Feature**: llm-register
> **Duration**: 2026-07-11 (단일 세션 PDCA 사이클: Plan → Design → Do → Check → Act → Report)
> **Owner**: 배상규 (AI Assistant)
> **Project**: idt_front (React 19 + TypeScript + TanStack Query v5)
> **API Doc**: `docs/api/llm-register.md` (백엔드 `idt/src/api/routes/llm_model_router.py`)

---

## Executive Summary

### Overview

백엔드에는 LLM 모델 레지스트리 API 6종(목록/단건/등록/수정/가격변경/비활성화)이 완성되어 있었으나, 프론트엔드는 목록 조회 1종만 연동되어 관리자가 모델을 관리할 UI가 전무했다 (admin 메뉴 6종 어디에도 부재). 본 사이클로 `/admin/llm-models` 관리 페이지, 뮤테이션 서비스/훅 레이어, admin 네비게이션 항목을 신설하여 모델 등록→기본 지정→가격 설정→비활성화의 전 수명주기를 UI에서 운영할 수 있게 했다.

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | LLM 모델 CRUD + 가격 API 6종 중 프론트 연동은 GET 목록 1종(17%)뿐. 모델 등록·가격 설정·비활성화는 API 직접 호출로만 가능했고, admin 영역(사용자/부서/RAGAS/Agent Run/MCP/Skill)에 LLM 모델 관리 메뉴 자체가 없었다. 가격 미설정 모델은 AGENT-OBS 비용 집계에서 누락되는 운영 리스크도 존재. |
| **Solution** | 계약 레이어(타입 3종+가격 필드, 엔드포인트 상수 2종, 서비스 메서드 5종) → 훅 레이어(뮤테이션 4종, `llmModels.all` invalidate) → `AdminLlmModelsPage`(테이블 + 등록/수정 모달 + 가격 모달 + 비활성화 ConfirmDialog + 비활성 포함 토글) → 네비/라우팅(`ADMIN_NAV_ITEMS` 7번째 항목 + `AdminRoute` 하위 라우트) 4단계로 구현. 기존 `useLlmModels` 시그니처는 불변 유지. |
| **Function/UX Effect** | 관리자가 UI에서 모델 등록(provider/모델명/api_key_env/base_url) → 기본 모델 지정(서버 자동 해제 반영) → 토큰 단가 설정(비용 캐시 즉시 무효화) → soft delete 비활성화·재활성화까지 수행. 모든 변경은 invalidate로 에이전트 빌더 모델 선택 목록에 새로고침 없이 반영. 409/422/404는 `ApiError.message` 기반 인라인 에러로 표면화. |
| **Core Value** | 에이전트 실행·문서 요약·비용 계산이 모두 참조하는 LLM 모델 레지스트리를 **코드 배포 없이 운영** 가능. API 커버리지 1/6 → 6/6 (100%), 신규 테스트 20건, 최종 Match Rate 100%, 회귀 0건. |

### 결과 지표

| 지표 | 값 |
|------|-----|
| Match Rate | 98.3% (Check) → **100%** (Act 보정 1회 후, 89/89 항목) |
| API 연동 커버리지 | 1/6 → **6/6** |
| 신규 테스트 | 20건 (훅 10 + 페이지 9 + 네비 1) 전부 통과 |
| 전체 스위트 | 549 통과 / 실패 8건은 사전 이슈(collection 모달) — **회귀 0건** |
| 품질 게이트 | type-check ✅ / 신규·수정 파일 lint clean ✅ |
| 변경 규모 | 신규 2파일(페이지+테스트), 수정 9파일 |

---

## PDCA Cycle Summary

### Plan Phase
- **Document**: `docs/01-plan/features/llm-register.plan.md`
- **입력**: `/api-plan llm-register` — API 문서(`docs/api/llm-register.md`) 컨텍스트 주입
- **핵심 확인**: 백엔드 6종 구현 완료 실측(라우터+스키마), 프론트 갭 6개 레이어 식별, admin 메뉴 부재 확인
- **주요 결정**: 가격 필드 `string | null`(Decimal JSON 직렬화), api_key_env write-only, 가격 모달 분리, `llmModels.all` invalidate 전략

### Design Phase
- **Document**: `docs/02-design/features/llm-register.design.md`
- **아키텍처**: Page → hooks(TanStack Query) → service(authClient) → API 4계층, 검증된 AdminMcpServersPage/useMcpServers 패턴 답습
- **설계 중 보정 2건** (구현 전/중 실측으로 문서 동기화):
  - 에러 계약: `authClient`가 FastAPI `detail`을 `ApiError(message, status)`로 정규화 → axios 파싱 대신 `ApiError.message` 사용
  - 레이아웃: AdminLayout `<main>` 자체 스크롤 확인 → 패턴 A 대신 admin 관례(`max-w-7xl` 단순 래퍼)

### Do Phase (TDD, 5 Phase)

#### 신규 파일
| 파일 | 내용 |
|------|------|
| `src/pages/AdminLlmModelsPage/index.tsx` | 페이지 + `LlmModelFormModal`(등록/수정 겸용) + `LlmModelPricingModal` + `PriceCell` |
| `src/pages/AdminLlmModelsPage/index.test.tsx` | P1~P9 페이지 상호작용 테스트 |

#### 수정 파일
| 파일 | 변경 |
|------|------|
| `src/types/llmModel.ts` | 가격 3필드 + `Create/Update/UpdatePricing` Request + `LLM_PROVIDER` as const |
| `src/constants/api.ts` | `LLM_MODEL_DETAIL`, `LLM_MODEL_PRICING` |
| `src/services/llmModelService.ts` | `getLlmModel`/`create`/`update`/`updatePricing`/`deactivate` 5종 |
| `src/lib/queryKeys.ts` | `llmModels.detail(id)` |
| `src/hooks/useLlmModels.ts` (+test) | 뮤테이션 훅 4종 + invalidate + (Act) `invalidateOn404`·`keepPreviousData` |
| `src/constants/adminNav.ts` (+test) | "LLM 모델" 항목 (cpu-chip 아이콘, 7개) |
| `src/App.tsx` | `/admin/llm-models` 라우트 (AdminRoute > AdminLayout) |
| `src/__tests__/mocks/handlers.ts` | GET 가격 필드+include_inactive 분기, POST(409 분기), PATCH×2, DELETE |

#### 구현 중 발견·해결 이슈
1. **jsdom HTML 폼 제약 검증**이 커스텀 인라인 에러를 가로챔(`min=0` 위반 시 submit 미발생) → 폼 `noValidate` 적용으로 인라인 에러 UX 통일
2. number input에 userEvent로 음수 타이핑 불가 → 테스트에서 `fireEvent.change` 사용

### Check Phase (Gap Analysis)
- **Document**: `docs/03-analysis/features/llm-register.analysis.md` (bkit:gap-detector, 89항목 정적 비교)
- **결과**: **98.3%** — Match 86 / Partial 3 / Missing 0, 아키텍처·컨벤션 100%
- Partial 3건(전부 Low): ①404 실패 시 invalidate 누락 ②단가 `/1K` 접미사 누락 ③토글 로딩 깜빡임

### Act Phase (보정 1회 — 사용자 지시로 3건 전부 구현 보정)
| Gap | 보정 | 위치 |
|-----|------|------|
| #1 | `invalidateOn404` 헬퍼 — update/pricing/deactivate `onError`에서 404 시 목록 재동기화 | `useLlmModels.ts` |
| #2 | `PriceCell`에 `/1K` 접미사(`$0.0025 /1K`) + P2 테스트 갱신 | `AdminLlmModelsPage/index.tsx` |
| #3 | `placeholderData: keepPreviousData`(토글 시 테이블 유지) + `isFetching` 미세 스피너 | `useLlmModels.ts` + 페이지 헤더 |

보정 후 재검증: 테스트 19/19, type-check, lint clean → **Match Rate 100%**

---

## Lessons Learned

1. **에러 계약은 인터셉터까지 확인**: 설계 시 axios 에러 파싱을 가정했으나 `authClient`가 이미 `ApiError`로 정규화 — 공통 인프라 계약을 설계 단계에서 실측하면 재작업이 준다.
2. **jsdom 폼 제약 검증**: `noValidate` 없는 폼의 `min`/`required` 위반은 jsdom에서 submit 이벤트 자체를 차단해 커스텀 검증 테스트가 조용히 실패한다. 커스텀 인라인 에러 UX를 쓰는 폼은 `noValidate`가 정합적.
3. **Vitest Windows 워커**: `--pool=threads`도 간헐 기동 타임아웃 발생 — `--maxWorkers=1` 재시도로 안정화.
4. **쿼리 키 전환 깜빡임**: 토글로 쿼리 키가 바뀌는 목록 UI는 `placeholderData: keepPreviousData`가 기본값으로 적합.

## Follow-ups (선택)

- E2E 수동 검증: 실서버(admin 계정)에서 등록→기본지정→가격→비활성화→재활성화 사이클 + 빌더 목록 갱신 확인 (jsdom 외 실브라우저 확인은 미수행)
- `getLlmModel`/`queryKeys.llmModels.detail`은 현재 미소비 자산 — 상세 화면 필요 시 활용
- 사전 실패 8건(collection 모달 QueryClient 미주입 등)은 본 기능과 무관한 별도 정리 대상

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-11 | 완료 보고서 — Match Rate 100% (Act 1회) | 배상규 |
