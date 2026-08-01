---
template: design
version: 1.0
feature: mutation-pending-guard
date: 2026-07-29
author: 배상규
project: idt_front
version_project: 0.0.0
---

# mutation-pending-guard Design Document

> **Summary**: TanStack Query `isPending`을 필수 prop으로 받아 자동 disable + 스피너를 표시하는 공통 `LoadingButton`을 신설하고, 지식 등록 중복 제출 결함이 있는 `AgentKnowledgePage`(저장/수정/폐기)에 적용한다. `mutateAsync` 실패 시 인라인 에러를 표시하고 폼·입력을 보존한다. 기존 44개 isPending 사용 파일은 무변경.
>
> **Project**: idt_front
> **Version**: 0.0.0
> **Author**: 배상규
> **Date**: 2026-07-29
> **Status**: Draft
> **Planning Doc**: [mutation-pending-guard.plan.md](../../01-plan/features/mutation-pending-guard.plan.md)

### Pipeline References

| Phase | Document | Status |
|-------|----------|--------|
| Phase 5 | Design System — 공통 버튼 컴포넌트 (this design) | 🔄 |
| Phase 6 | UI Integration — 지식 페이지 적용 (this design) | 🔄 |

---

## 1. Overview

### 1.1 Design Goals

- **중복 제출 원천 차단**: 뮤테이션 대기 중 버튼이 자동으로 disable되어 두 번째 클릭이 물리적으로 불가능하게 한다.
- **대기 피드백 제공**: 클릭 즉시 스피너 + 대기 문구("저장 중…")로 요청이 접수됐음을 보여준다 (재클릭 동기 제거).
- **실패 표면화**: `mutateAsync` 실패 시 인라인 에러 메시지를 표시하고 폼과 입력값을 보존해 재시도 가능하게 한다.
- **구조적 봉인**: `isPending`을 **필수 prop**으로 강제하는 공통 컴포넌트로, "붙이는 걸 깜빡하는" 실수를 타입 레벨에서 차단한다.

### 1.2 Design Principles

- **독립 opt-in**: 기존 44개 isPending 사용 파일은 건드리지 않는다. 이번엔 결함이 확인된 `AgentKnowledgePage`에만 적용하고, 이후 신규/수정 화면부터 점진 채택한다.
- **스타일 주입식**: LoadingButton은 디자인을 강제하지 않는다. `className`을 그대로 통과시켜 페이지별 기존 버튼 스타일(violet primary, border ghost 등)을 유지한다 → 채택 장벽 최소화.
- **이중 방어**: `disabled` 속성 + `onClick` 무시(컴포넌트 레벨) + `submitForm` 조기 반환(페이지 레벨) 3중 가드.
- **No Backend Coupling**: 프론트 전용. API/타입/서비스 변경 없음. 서버 멱등성 키는 별도 과제.

---

## 2. Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ components/common/LoadingButton.tsx  (NEW — 공통)           │
│   props: isPending(필수), pendingText?, ...button attrs     │
│   - isPending → disabled + 스피너 + pendingText             │
│   - isPending 중 onClick 무시 (이중 방어)                   │
└──────────────────────┬──────────────────────────────────────┘
                       │ 사용 (이번 범위)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ pages/AgentKnowledgePage/index.tsx  (수정)                  │
│   isSaving = create.isPending || update.isPending           │
│   submitForm: pending 조기 반환 + try/catch → submitError   │
│   ├─ 저장 버튼    → LoadingButton (isSaving, "저장 중…")    │
│   ├─ 폐기 버튼    → LoadingButton (deprecate.isPending)     │
│   └─ submitError  → 버튼 하단 인라인 <p> 표시               │
└──────────────────────┬──────────────────────────────────────┘
                       │ 기존 훅 그대로 (변경 없음)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│ hooks/useWiki.ts — useCreateWiki / useUpdateArticle /       │
│ useDeprecateArticle (TanStack Query useMutation, 무변경)    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Interaction Flow

#### 2.2.1 정상 저장 (중복 클릭 차단)

```
사용자 "저장" 클릭
  → submitForm 진입: isSaving=false → 통과, setSubmitError(null)
  → createMutation.mutateAsync(...) 시작 → isPending=true
  → LoadingButton: disabled + 스피너 + "저장 중…" 렌더
  → (사용자가 다시 클릭해도) disabled라 클릭 이벤트 미발생
     └ 가사 disabled 우회(포커스+Enter 등)해도 onClick=undefined + submitForm 조기 반환
  → 응답 성공 → invalidateWiki → setFormOpen(false) → 트리에 1건만 반영
```

#### 2.2.2 저장 실패 (에러 표면화)

```
mutateAsync reject (4xx/5xx/네트워크)
  → catch → setSubmitError('저장에 실패했습니다. 다시 시도해주세요.')
  → 폼 유지, form state(제목/경로/본문) 보존, isPending=false → 버튼 재활성화
  → 재시도 클릭 → setSubmitError(null) → 성공 시 에러 없이 폼 닫힘
  → "취소" 클릭 → setFormOpen(false) + setSubmitError(null)
```

#### 2.2.3 폐기 (FR-07)

```
"폐기" 클릭 → deprecateMutation.mutate(article.id)
  → isPending 동안 LoadingButton disabled + "폐기 중…"
  → 완료 → invalidateWiki로 목록 갱신 (기존 동작 유지)
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `LoadingButton` | (없음 — React만) | 공통 대기 버튼, 외부 의존성 0 |
| `AgentKnowledgePage` | `LoadingButton`, `useWiki` 훅 3종(기존) | 가드 적용 대상 |

---

## 3. Component Specification

### 3.1 `LoadingButton` — `src/components/common/LoadingButton.tsx` (신규)

```tsx
// mutation-pending-guard: TanStack Query isPending과 직결되는 공통 대기 버튼.
// isPending을 필수로 받아 "가드 누락" 실수를 타입 레벨에서 차단한다.
import type { ButtonHTMLAttributes } from 'react';

interface LoadingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** mutation.isPending 직결 — true면 disable + 스피너 */
  isPending: boolean;
  /** 대기 중 대체 문구 (미지정 시 children 유지) */
  pendingText?: string;
}

const LoadingButton = ({
  isPending,
  pendingText,
  disabled,
  children,
  onClick,
  className,
  type = 'button',
  ...rest
}: LoadingButtonProps) => (
  <button
    type={type}
    disabled={isPending || disabled}
    onClick={isPending ? undefined : onClick}
    className={className}
    {...rest}
  >
    {isPending && (
      <svg
        aria-hidden="true"
        className="mr-1.5 inline h-3.5 w-3.5 animate-spin"
        viewBox="0 0 24 24"
        fill="none"
      >
        <circle
          className="opacity-25"
          cx="12" cy="12" r="10"
          stroke="currentColor" strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z"
        />
      </svg>
    )}
    {isPending ? (pendingText ?? children) : children}
  </button>
);

export default LoadingButton;
```

**설계 결정**:

| # | 결정 | 근거 |
|---|------|------|
| ① | `isPending` 필수 prop | optional이면 안 넘기는 실수가 재발 — 타입 에러로 강제 |
| ② | `onClick={isPending ? undefined : onClick}` | disabled 우회 경로(프로그래매틱 click 등) 이중 방어 |
| ③ | `className` 통과 (기본 스타일 없음) | 페이지별 기존 스타일 유지, 점진 채택 장벽 제거 |
| ④ | `type="button"` 기본값 | form 내부 사용 시 의도치 않은 submit 방지 |
| ⑤ | 스피너 `aria-hidden` + 문구 변경으로 상태 전달 | 스크린리더는 "저장 중…" 텍스트로 인지, 스피너는 장식 |
| ⑥ | 스피너 인라인 SVG | 외부 라이브러리 의존 없음, `animate-spin`은 Tailwind 기본 제공 |
| ⑦ | `pendingText` 미지정 시 children 유지 | 짧은 아이콘 버튼 등 문구 교체가 어색한 경우 대응 |

### 3.2 `AgentKnowledgePage` 수정 — `src/pages/AgentKnowledgePage/index.tsx`

#### 상태 추가

```tsx
const [submitError, setSubmitError] = useState<string | null>(null);
const isSaving = createMutation.isPending || updateMutation.isPending;
```

#### `submitForm` 변경 (L108-124 대체)

```tsx
const submitForm = async () => {
  if (isSaving) return; // FR-04: disabled 우회 경로 방어
  setSubmitError(null);
  const path = form.path.trim() === '' ? null : form.path.trim();
  try {
    if (editingId) {
      await updateMutation.mutateAsync({
        id: editingId,
        data: { title: form.title, content: form.content, path },
      });
    } else {
      await createMutation.mutateAsync({
        agent_id: agentId ?? '',
        title: form.title,
        content: form.content,
        path,
      });
    }
    setFormOpen(false); // 성공 시에만 닫음
  } catch {
    // FR-05: 폼·입력 보존, 인라인 에러 표시. 상세 사유는 콘솔/인터셉터 몫.
    setSubmitError('저장에 실패했습니다. 다시 시도해주세요.');
  }
};
```

#### 에러 초기화 지점 (FR-06)

| 지점 | 처리 |
|------|------|
| `openCreate()` | `setSubmitError(null)` 추가 |
| `openEdit()` | `setSubmitError(null)` 추가 |
| 취소 버튼 | `setFormOpen(false); setSubmitError(null);` |
| `submitForm` 진입 시 | `setSubmitError(null)` (재시도 시 즉시 제거) |

#### 버튼 교체 (L212-226 영역)

```tsx
<div className="flex gap-2">
  <LoadingButton
    isPending={isSaving}
    pendingText="저장 중…"
    onClick={submitForm}
    disabled={!form.title.trim() || !form.content.trim()}
    className="rounded bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-violet-700 disabled:opacity-40"
  >
    저장
  </LoadingButton>
  <button
    onClick={() => {
      setFormOpen(false);
      setSubmitError(null);
    }}
    className="rounded border border-zinc-300 px-3 py-1.5 text-xs text-zinc-600"
  >
    취소
  </button>
</div>
{submitError && (
  <p role="alert" className="mt-2 text-xs text-red-600">
    {submitError}
  </p>
)}
```

#### 폐기 버튼 교체 (L257-262, FR-07)

```tsx
<LoadingButton
  isPending={deprecateMutation.isPending}
  pendingText="폐기 중…"
  onClick={() => deprecateMutation.mutate(article.id)}
  className="rounded border border-red-200 px-3 py-1.5 text-xs text-red-600 hover:bg-red-50"
>
  폐기
</LoadingButton>
```

> 수정 진입 버튼(`openEdit`)은 서버 통신이 아니므로 LoadingButton 불필요 — 일반 버튼 유지.

---

## 4. UI/UX Design

### 4.1 버튼 상태 매트릭스 (저장 버튼)

| 상태 | 조건 | 표시 | 클릭 가능 |
|------|------|------|:---:|
| 기본 | 제목·본문 입력됨, idle | `저장` (violet-600) | ✅ |
| 입력 미완 | 제목 또는 본문 공백 | `저장` (opacity-40) | ❌ |
| 대기 | `isSaving === true` | `⟳ 저장 중…` (opacity-40, 스피너 회전) | ❌ |
| 실패 후 | reject 직후 | `저장` 재활성 + 하단 빨간 에러 문구 | ✅ (재시도) |

### 4.2 에러 메시지

```
┌──────────────────────────────────────┐
│ [⟳ 저장 중…]  [취소]                 │   ← 대기 중
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│ [저장]  [취소]                       │   ← 실패 후
│ 저장에 실패했습니다. 다시 시도해주세요. │   (text-xs text-red-600, role="alert")
└──────────────────────────────────────┘
```

- `role="alert"` — 스크린리더 즉시 공지 + 테스트 셀렉터(`findByRole('alert')`)로 활용.
- 문구는 고정 1종 (서버 상세 메시지 노출 안 함 — 보안·일관성).

### 4.3 스타일 토큰 준수 (CLAUDE.md)

| 항목 | 적용 |
|------|------|
| Primary 버튼 | `bg-violet-600 hover:bg-violet-700` (기존 유지) |
| Disabled | `disabled:opacity-40` (기존 유지) |
| 스피너 | `animate-spin` + `currentColor` (버튼 텍스트 색 자동 상속) |
| 에러 | `text-red-600` (Destructive 계열) |

---

## 5. Error / Edge Cases

| 케이스 | 처리 |
|--------|------|
| 대기 중 재클릭 | `disabled` → 클릭 미발생. 우회 시 `onClick=undefined` + `submitForm` 조기 반환 |
| 대기 중 "취소" 클릭 | 허용 (폼 닫힘). 진행 중 요청은 완료되면 invalidate로 트리 반영 — 데이터 정합성 문제 없음 |
| 생성과 수정이 동시에 pending | 불가능한 상태이지만 `isSaving`이 OR 조건이라 어느 쪽이든 가드됨 |
| 실패 후 문구 수정 없이 재시도 | 허용 — 일시적 서버 오류 대응 |
| 폐기 실패 | `mutate()` 기본 동작(무표시) 유지 — 이번 범위는 pending 가드만 (P2). 에러 표시는 스코프 밖 |
| 네트워크 초저속으로 수 초 대기 | 스피너 지속 표시. 타임아웃은 axios 인스턴스 기본값에 위임 |

---

## 6. Security Considerations

- [x] 서버 에러 상세(스택/메시지)를 화면에 노출하지 않음 — 고정 문구만 표시.
- [x] 프론트 가드는 UX 레이어 — 진짜 중복 방지의 최종 책임은 서버(멱등성)임을 Plan 스코프 밖 항목으로 명시.
- [x] 입력값 보존은 메모리(state)만 사용 — localStorage 등 영속 저장 없음.

---

## 7. Test Plan (TDD — Red 먼저)

### 7.1 Test Scope

| Type | Target | Tool |
|------|--------|------|
| Unit | `LoadingButton` 상태·클릭 가드 | Vitest + RTL |
| Integration | `AgentKnowledgePage` 중복 제출·에러 시나리오 | Vitest + RTL + MSW (기존 `index.test.tsx`에 추가) |

> 기존 `AgentKnowledgePage/index.test.tsx`의 인프라 재사용: per-file MSW 훅(`server.listen/resetHandlers/close`), `createWrapper`, `renderPage`, `loginAsOwner`. vitest 실행은 `--pool=threads`.

### 7.2 Test Cases

#### 7.2.1 `LoadingButton.test.tsx` (신규)

| # | 케이스 | 검증 |
|---|--------|------|
| L1 | idle: children 표시 + onClick 호출 | `isPending=false`에서 클릭 → handler 1회 호출 |
| L2 | pending: disabled + pendingText | `isPending=true` → `toBeDisabled()`, "저장 중…" 텍스트 |
| L3 | pending: 클릭해도 onClick 미호출 | `fireEvent.click` 강제 발화 → handler 0회 |
| L4 | pendingText 미지정 시 children 유지 | `isPending=true`, pendingText 없음 → children 그대로 |
| L5 | 자체 disabled 우선 | `disabled=true, isPending=false` → disabled 유지 |

#### 7.2.2 `AgentKnowledgePage/index.test.tsx` (추가)

| # | 케이스 | 사전조건 | 검증 |
|---|--------|----------|------|
| K1 | **이중 클릭 시 POST 1회** | owner 로그인, MSW POST에 `delay(150)` + 호출 카운터 | 저장 2회 클릭 → 카운터 === 1 |
| K2 | 대기 중 버튼 상태 | K1과 동일 | 클릭 직후 `저장 중…` 표시 + `toBeDisabled()` |
| K3 | 실패 시 에러 + 폼 보존 | MSW POST 500 응답 | `findByRole('alert')` 표시, 제목 input 값 유지, 폼 열림 유지 |
| K4 | 재시도 성공 시 에러 해제·폼 닫힘 | K3 후 핸들러를 성공으로 교체 | 재클릭 → alert 사라짐, 폼 닫힘 |
| K5 | 취소 시 에러 초기화 | K3 후 취소 클릭 | 폼 닫힘, 재오픈 시 alert 없음 |

#### 7.2.3 K1 핸들러 패턴 (플래키 방지)

```typescript
let createCalls = 0;
server.use(
  http.post('*/api/v1/wiki', async () => {
    createCalls += 1;
    await delay(150);                       // msw의 delay — 결정적 대기
    return HttpResponse.json({ id: 'new-1' }, { status: 201 });
  }),
);
// 클릭 2회 → await waitFor(() => expect(폼 닫힘)) 후 expect(createCalls).toBe(1)
```

> 실제 엔드포인트 경로는 구현 시 `wikiService.create`가 쓰는 상수(`API_ENDPOINTS`)와 일치시킬 것.

---

## 8. Clean Architecture

### 8.1 Layer Assignment

| Layer | Responsibility | 이번 기능 매핑 |
|-------|---------------|----------------|
| **Presentation (common)** | 재사용 UI | `components/common/LoadingButton.tsx` |
| **Presentation (page)** | 페이지 조립 + 로컬 상태 | `pages/AgentKnowledgePage/index.tsx` (`submitError`) |
| **Application** | 서버 상태 | `hooks/useWiki.ts` (무변경) |
| **Infrastructure** | HTTP | `services/wikiService.ts` (무변경) |

### 8.2 Import Rules Compliance

| From | To | 허용 여부 |
|------|------|:---:|
| `pages/AgentKnowledgePage` → `components/common/LoadingButton` | Page → Common | ✅ |
| `components/common/LoadingButton` → (React만) | 의존성 없음 | ✅ |
| LoadingButton → hooks/services | ❌ 금지 — isPending은 prop으로만 받음 | ✅ (준수) |

---

## 9. Coding Convention Reference

| Item | Convention Applied |
|------|-------------------|
| 컴포넌트 파일 | PascalCase `LoadingButton.tsx`, `components/common/` 배치 |
| Props 타입 | `interface LoadingButtonProps` 파일 상단, `ButtonHTMLAttributes` 확장 |
| Export | `export default` 파일 하단 단독 선언 |
| 테스트 위치 | 소스 옆 `LoadingButton.test.tsx`, 페이지 테스트는 기존 파일에 추가 |
| 절대 경로 | `@/components/common/LoadingButton` |
| 주석 | 파일 헤더에 feature 슬러그(`mutation-pending-guard`) 표기 (기존 관례) |

---

## 10. Implementation Guide

### 10.1 변경 파일 목록

#### 신규 파일

| 파일 | 역할 |
|------|------|
| `src/components/common/LoadingButton.tsx` | 공통 대기 버튼 |
| `src/components/common/LoadingButton.test.tsx` | L1~L5 단위 테스트 |

#### 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `src/pages/AgentKnowledgePage/index.tsx` | `submitError` 상태, `isSaving`, `submitForm` try/catch + 조기 반환, 저장/폐기 버튼 LoadingButton 교체, 에러 초기화 4지점 |
| `src/pages/AgentKnowledgePage/index.test.tsx` | K1~K5 통합 테스트 추가 |
| `CLAUDE.md` (idt_front) | 완료 파일 목록에 LoadingButton 등재 |

### 10.2 TDD 구현 순서

```
Phase 1: LoadingButton (Red → Green)
  1. Red  — LoadingButton.test.tsx L1~L5 작성 → 실패 (모듈 없음)
  2. Green — LoadingButton.tsx 구현 → L1~L5 통과

Phase 2: 지식 페이지 가드 (Red → Green)
  3. Red  — index.test.tsx에 K1~K5 추가 → K1(POST 2회)·K3(alert 없음) 실패 확인
  4. Green — AgentKnowledgePage 수정 (3.2 스펙대로) → K1~K5 통과

Phase 3: 검증
  5. npm run type-check + npm run lint
  6. npm run test:run -- --pool=threads (전체 회귀 — 사전 실패 8건 제외 기준)
  7. npm run dev → 수동 검증:
     - 저장 클릭 → 스피너 + "저장 중…" + 재클릭 불가 확인
     - DevTools Network에서 POST 1회만 발생 확인
     - 백엔드 중단 후 저장 → 에러 문구 + 입력 보존 확인
     - 폐기 버튼 pending 동작 확인
  8. CLAUDE.md 완료 파일 목록 갱신
```

---

## 11. Definition of Done

- [ ] `LoadingButton.tsx` 신규 — isPending 필수 prop, 스피너, pendingText, onClick 이중 방어
- [ ] `LoadingButton.test.tsx` L1~L5 통과
- [ ] `AgentKnowledgePage` — 저장 이중 클릭 시 POST 1회 (K1), 대기 표시 (K2)
- [ ] 실패 시 인라인 에러 + 폼·입력 보존 (K3), 재시도 (K4), 취소 초기화 (K5)
- [ ] 폐기 버튼 pending 가드 적용
- [ ] `npm run type-check`, `npm run lint`, `npm run test:run` 통과 (기존 회귀 0)
- [ ] 수동 검증 완료 (스피너·Network 1회·에러 표시)
- [ ] CLAUDE.md 완료 파일 목록에 LoadingButton 등재

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-29 | Initial design — Plan 기반 (공통 LoadingButton + 지식 페이지 적용 + 에러 표면화) | 배상규 |
