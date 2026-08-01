# mutation-pending-guard Plan

> 에이전트 지식 등록 시 서버 대기 표시가 없어 이중 클릭 → 문서 2건 중복 생성되는 결함 수정.
> isPending 내장 공통 LoadingButton 신설 + AgentKnowledgePage 적용 + 실패 시 에러 표면화.

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | 뮤테이션 대기 가드 — 공통 LoadingButton + 지식 페이지 중복 제출 방지 |
| 작성일 | 2026-07-29 |
| 예상 소요 | 2~3시간 (공통 컴포넌트 + 페이지 적용 + 테스트) |
| 영향 범위 | 신규 1개 파일(`LoadingButton.tsx`) + 수정 1개 파일(`AgentKnowledgePage/index.tsx`) + 테스트 |

### Value Delivered

| 관점 | 설명 |
|------|------|
| Problem | 지식 문서 저장 버튼이 서버 응답 대기 중에도 활성 상태라 두 번 클릭하면 POST가 2번 나가 같은 문서가 2건 생성됨. 실패 시에도 아무 표시가 없어 사용자가 재시도 여부를 알 수 없음 |
| Solution | TanStack Query `isPending`을 받아 자동으로 disable + 스피너를 표시하는 공통 `LoadingButton` 컴포넌트를 신설하고, 문제된 지식 페이지(저장/수정/폐기)에 적용. `mutateAsync` 실패 시 인라인 에러 메시지 표시 |
| Function UX Effect | 저장 클릭 즉시 버튼이 "저장 중…" + 스피너로 바뀌고 재클릭 불가. 실패하면 버튼 근처에 에러 문구가 뜨고 입력 내용은 보존됨 |
| Core Value | "isPending을 각 화면이 수동으로 기억해야 하는" 구조적 구멍을 공통 컴포넌트로 봉인 — 이후 신규 화면은 LoadingButton만 쓰면 중복 제출이 원천 차단 |

---

## 1. 배경 및 목표

### AS-IS (현재 문제)

**증상**: `/agents/{agentId}/workspace` → "전체 지식 보기" → `/agents/{agentId}/knowledge`에서
새 지식 문서를 저장할 때 스피너/비활성화가 없어 두 번 누르면 문서가 2건 등록된다.

**원인 코드** — `src/pages/AgentKnowledgePage/index.tsx`:

```tsx
// L108-124: submitForm — 대기 가드 없음
const submitForm = async () => {
  ...
  await createMutation.mutateAsync({ ... });  // 실패 시 unhandled rejection
  setFormOpen(false);
};

// L213-219: 저장 버튼 — isPending 미사용
<button
  onClick={submitForm}
  disabled={!form.title.trim() || !form.content.trim()}  // 빈 값 검증만 있음
>
  저장
</button>
```

문제점 3가지:

1. **중복 제출**: `createMutation.isPending` / `updateMutation.isPending`이 버튼 disable에 반영되지 않음 → 응답 대기 중 재클릭 시 POST 2회.
2. **대기 피드백 부재**: 스피너·문구 변화가 없어 사용자는 클릭이 접수됐는지 알 수 없음 (그래서 다시 누름).
3. **실패 침묵**: `mutateAsync` 실패 시 catch가 없어 에러가 어디에도 표시되지 않고 폼만 열린 채 남음.

같은 파일의 **폐기 버튼**(L258, `deprecateMutation.mutate`)도 동일하게 무방비.

### 프로젝트 현황 (조사 결과)

- 이미 **44개 파일**이 `mutation.isPending`으로 각자 disable 처리 중 — 패턴 자체는 정착됐으나 **수동 반복**이라 이번처럼 누락되면 그대로 결함.
- `useIsMutating` / `MutationCache` 기반 전역 장치는 없음.
- `src/components/common/`에 버튼 계열 공통 컴포넌트 없음 (ConfirmDialog, Modal, Dropdown 등만 존재).

### TO-BE (목표)

1. **공통 `LoadingButton`**: `isPending`을 prop으로 받아 자동으로 `disabled` + 스피너 + 대기 문구를 처리하는 컴포넌트 신설.
2. **지식 페이지 적용**: 저장/수정 진입/폐기 버튼을 LoadingButton으로 교체, `submitForm`에 pending 조기 반환 가드 추가.
3. **실패 표면화**: 저장 실패 시 버튼 근처 인라인 에러 메시지 표시, 폼과 입력 내용 유지.
4. **기존 44개 파일은 무변경** — 신규/수정 화면부터 점진 채택 (독립 opt-in 원칙).

### 스코프 밖 (이번에 안 함)

- 기존 44개 파일의 LoadingButton 일괄 마이그레이션.
- `useIsMutating` 기반 전역 오버레이/진행바 (채팅 전송 등 가벼운 뮤테이션에도 떠 UX 부작용 검토 필요 — 후속 과제).
- 백엔드 멱등성 키(idempotency key) 도입 — 프론트 가드로 1차 차단, 서버 측은 별도 과제.

---

## 2. 요구사항

### FR (기능 요구사항)

| ID | 요구사항 | 우선순위 |
|----|----------|:---:|
| FR-01 | 공통 `LoadingButton` 신설: `isPending`이 true면 `disabled` + 인라인 스피너 + `pendingText`(기본: children 유지) 표시 | P1 |
| FR-02 | `isPending` 중 `onClick` 재호출 불가 (disabled + 클릭 무시 이중 방어) | P1 |
| FR-03 | 지식 페이지 저장 버튼에 적용 — 생성(`createMutation`)·수정(`updateMutation`) 대기 중 "저장 중…" 표시 및 비활성화 | P1 |
| FR-04 | `submitForm` 진입 시 이미 pending이면 조기 반환 (키보드 등 우회 경로 방어) | P1 |
| FR-05 | 저장 실패 시 버튼 하단에 인라인 에러 메시지("저장에 실패했습니다. 다시 시도해주세요.") 표시, 폼 유지·입력 보존 | P1 |
| FR-06 | 재시도 성공 또는 폼 닫기 시 에러 메시지 초기화 | P1 |
| FR-07 | 폐기 버튼도 `deprecateMutation.isPending` 가드 적용 | P2 |
| FR-08 | 기존 스타일 토큰 준수 — violet-600 primary, `disabled:opacity-40`, `animate-spin` SVG 스피너 | P2 |

### NFR (비기능 요구사항)

| ID | 요구사항 |
|----|----------|
| NFR-01 | 기존 44개 isPending 사용 파일 무변경 (회귀 0) |
| NFR-02 | TDD — LoadingButton 단위 테스트 + AgentKnowledgePage 이중 클릭 테스트 선작성 (Red → Green) |
| NFR-03 | 백엔드 API 무변경 (프론트 전용) |

---

## 3. 설계 개요

### 3-1. 공통 컴포넌트 — `src/components/common/LoadingButton.tsx` (신규)

```tsx
interface LoadingButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  isPending: boolean;          // TanStack Query mutation.isPending 직결
  pendingText?: string;        // 대기 중 대체 문구 (예: "저장 중…")
}

const LoadingButton = ({ isPending, pendingText, disabled, children, onClick, ...rest }: LoadingButtonProps) => (
  <button
    disabled={isPending || disabled}
    onClick={isPending ? undefined : onClick}   // disabled 우회 이중 방어
    {...rest}
  >
    {isPending && <Spinner />}                  {/* animate-spin 인라인 SVG */}
    {isPending ? (pendingText ?? children) : children}
  </button>
);
```

설계 포인트:

- **스타일은 주입식** — `className`을 그대로 통과시켜 기존 버튼 스타일(페이지별 violet/border 계열)을 유지. 공통 컴포넌트가 디자인을 강제하지 않아 점진 채택이 쉬움.
- **isPending은 필수 prop** — "붙이는 걸 깜빡하는" 실수를 타입 레벨에서 차단.
- 스피너는 `h-3.5 w-3.5 animate-spin` 인라인 SVG (외부 의존성 없음).

### 3-2. 지식 페이지 적용 — `src/pages/AgentKnowledgePage/index.tsx` (수정)

```tsx
const [submitError, setSubmitError] = useState<string | null>(null);
const isSaving = createMutation.isPending || updateMutation.isPending;

const submitForm = async () => {
  if (isSaving) return;                      // FR-04 조기 반환 가드
  setSubmitError(null);
  try {
    if (editingId) { await updateMutation.mutateAsync({ ... }); }
    else           { await createMutation.mutateAsync({ ... }); }
    setFormOpen(false);
  } catch {
    setSubmitError('저장에 실패했습니다. 다시 시도해주세요.');  // FR-05 폼 유지
  }
};

// 저장 버튼
<LoadingButton
  isPending={isSaving}
  pendingText="저장 중…"
  onClick={submitForm}
  disabled={!form.title.trim() || !form.content.trim()}
  className="rounded bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-40"
>
  저장
</LoadingButton>
{submitError && <p className="mt-2 text-xs text-red-600">{submitError}</p>}
```

- 폐기 버튼: `<LoadingButton isPending={deprecateMutation.isPending} pendingText="폐기 중…">` 적용 (FR-07).
- 폼 열기/닫기(`openCreate`/`openEdit`/취소) 시 `setSubmitError(null)` (FR-06).

### 3-3. 변경 파일 목록

| 구분 | 파일 | 내용 |
|------|------|------|
| 신규 | `src/components/common/LoadingButton.tsx` | 공통 대기 버튼 |
| 신규 | `src/components/common/LoadingButton.test.tsx` | 단위 테스트 |
| 수정 | `src/pages/AgentKnowledgePage/index.tsx` | 저장/폐기 가드 + 에러 표시 |
| 수정 | `src/pages/AgentKnowledgePage/index.test.tsx` | 이중 클릭·에러 시나리오 테스트 추가 |

---

## 4. 테스트 계획 (TDD — Red 먼저)

### LoadingButton 단위 테스트

| # | 시나리오 | 기대 |
|---|----------|------|
| 1 | `isPending=false` | children 표시, 클릭 시 onClick 호출 |
| 2 | `isPending=true` | disabled, 스피너 렌더, `pendingText` 표시 |
| 3 | `isPending=true`에서 클릭 | onClick 미호출 |
| 4 | `disabled=true` (isPending과 무관) | 기존 disabled 로직 유지 |

### AgentKnowledgePage 통합 테스트 (MSW)

| # | 시나리오 | 기대 |
|---|----------|------|
| 5 | 저장 응답 지연 중 버튼 2회 클릭 | POST 요청 **1회만** 발생 (MSW 핸들러 호출 카운트) |
| 6 | 저장 대기 중 | 버튼 disabled + "저장 중…" 표시 |
| 7 | 저장 실패(500) | 에러 메시지 표시, 폼 열림 유지, 입력값 보존 |
| 8 | 실패 후 재시도 성공 | 에러 메시지 사라지고 폼 닫힘 |

> 주의: 이 프로젝트 MSW는 전역 setup이 없음 — 테스트 파일에 `server.listen/resetHandlers/close` 3종 훅 직접 선언. vitest는 `--pool=threads`로 실행.

---

## 5. 리스크

| 리스크 | 확률 | 대응 |
|--------|:---:|------|
| 응답 지연 시나리오 테스트의 타이밍 플래키 | 중 | MSW `delay()` + `findBy*` 비동기 쿼리로 결정적 대기 |
| onClick 무시 로직이 form submit 등 다른 트리거를 놓침 | 낮음 | 해당 폼은 `<form>` 미사용(버튼 onClick 직접 호출)이라 경로 단일 — submitForm 조기 반환으로 이중 방어 |
| 기존 페이지가 LoadingButton을 계속 안 쓰는 문제 | 중 | 이번 범위는 지식 페이지만. CLAUDE.md 컴포넌트 목록에 등재해 신규 작업 시 기본 선택지로 노출 |

---

## 6. 완료 기준

- [ ] `LoadingButton` 신규 + 단위 테스트 4건 통과
- [ ] 지식 페이지 저장 이중 클릭 시 POST 1회만 발생 (테스트로 검증)
- [ ] 저장 대기 중 버튼 disabled + 스피너 + "저장 중…" 표시
- [ ] 저장 실패 시 인라인 에러 표시, 폼·입력 보존, 재시도 가능
- [ ] 폐기 버튼 pending 가드 적용
- [ ] 기존 테스트 회귀 없음 (사전 실패 8건 제외)
- [ ] CLAUDE.md 완료 파일 목록에 LoadingButton 등재
