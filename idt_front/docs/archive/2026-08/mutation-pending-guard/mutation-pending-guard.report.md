# mutation-pending-guard Completion Report

> **Summary**: 에이전트 지식 등록 이중 클릭 → 문서 2건 중복 생성 결함을 공통 `LoadingButton` 컴포넌트 + 페이지 가드 + 실패 표면화로 수정. Match Rate 98%, iterate 0회, 신규 회귀 0.
>
> **Feature**: mutation-pending-guard
> **Duration**: 2026-07-29 ~ 2026-08-01 (Plan → Report)
> **Owner**: AI Assistant (배상규)
> **Project**: idt_front (React 19 + TypeScript + TanStack Query)

---

## Executive Summary

### 1.1 Overview

`/agents/{agentId}/workspace` → 지식 페이지(`/agents/{agentId}/knowledge`)에서 지식 문서 저장 시 서버 대기 표시가 없어 사용자가 버튼을 두 번 눌렀고, POST가 2회 발생해 같은 문서가 2건 등록되는 결함이 있었다. 원인은 저장/수정/폐기 버튼이 TanStack Query `mutation.isPending`을 사용하지 않은 것. 프로젝트에 이미 44개 파일이 isPending 패턴을 쓰고 있었으나 **각자 수동으로 붙이는 구조라 누락이 곧 결함**이었다.

해결로 `isPending`을 **필수 prop**으로 강제하는 공통 `LoadingButton`을 신설해 구조적 구멍을 봉인하고, 결함 페이지에 적용했으며, `mutateAsync` 실패 시 침묵하던 에러를 인라인 `role="alert"` 메시지로 표면화했다.

### 1.2 Results

| 항목 | 결과 |
|------|------|
| Match Rate (gap-detector) | **98%** (임계값 90% 상회, iterate 0회) |
| 신규 파일 | 2 (`LoadingButton.tsx` 54줄 + 테스트 63줄) |
| 수정 파일 | 3 (`AgentKnowledgePage/index.tsx`, 동 테스트, `CLAUDE.md`) |
| 테스트 | 신규 9 시나리오 (L1~L5 단위 5 + K1~K5 통합 4블록) — 15/15 통과 |
| TDD | Red 선행 확인 (결함 재현: POST 2회·unhandled rejection) → Green |
| 회귀 | 신규 0 (사전 실패 8건 불변, 부하성 플래키 3건 격리 실행으로 무관 판정) |
| type-check / lint | 통과 (에러 0) |
| 백엔드 변경 | 0 |

### 1.3 Value Delivered

| Perspective | Content |
|-------------|---------|
| **Problem** | 지식 문서 저장 버튼이 서버 응답 대기 중에도 활성 상태(스피너·비활성화 없음)라 이중 클릭 시 POST 2회 → 동일 문서 2건 생성. 실패 시에도 아무 표시 없이 폼만 열려 있어 사용자는 접수 여부·실패 여부를 알 수 없었다. |
| **Solution** | `isPending` 필수 prop + 자동 disable + 인라인 스피너 + 대기 문구를 내장한 공통 `LoadingButton` 신설(3중 방어: disabled 속성·onClick 무시·submitForm 조기 반환). 지식 페이지 저장/폐기 버튼에 적용하고, 실패 시 `role="alert"` 고정 문구 표시 + 폼·입력 보존으로 재시도 가능하게 했다. |
| **Function/UX Effect** | 저장 클릭 즉시 버튼이 "⟳ 저장 중…"으로 바뀌며 재클릭 불가 → 중복 등록 원천 차단. 실패하면 버튼 아래 빨간 에러 문구가 뜨고 작성 내용이 그대로 남아 바로 재시도할 수 있다. MSW 지연 응답 테스트로 "2회 클릭 → POST 1회"를 회귀 안전망으로 고정했다. |
| **Core Value** | "isPending을 각 화면이 수동으로 기억해야 하는" 반복 실수 구조를 타입 레벨(필수 prop)에서 봉인. 기존 44개 파일 무변경(독립 opt-in)으로 회귀 위험 0을 유지하면서, 이후 신규 화면은 LoadingButton만 쓰면 중복 제출이 원천 차단되는 재사용 자산을 확보했다. |

---

## 2. PDCA Cycle Summary

### 2.1 Plan (2026-07-29)

- **문서**: `docs/01-plan/features/mutation-pending-guard.plan.md`
- **사용자 의사결정 3건** (AskUserQuestion): ① 공통 버튼 신설 + 지식 페이지만 적용 (전역 오버레이는 후속) ② 버튼 내 스피너 + disable ③ 실패 처리 포함
- **스코프 밖 명시**: 기존 44개 파일 일괄 마이그레이션, `useIsMutating` 전역 오버레이, 백엔드 멱등성 키

### 2.2 Design (2026-07-29)

- **문서**: `docs/02-design/features/mutation-pending-guard.design.md`
- **핵심 결정**:
  - `isPending` 필수 prop — 가드 누락을 타입 에러로 차단 (결함 근본 원인 대응)
  - 스타일 주입식(`className` 통과) — 디자인 비강제로 점진 채택 장벽 제거
  - 3중 방어 — disabled(1차) + onClick 무시(2차) + submitForm 조기 반환(3차)
  - LoadingButton은 hooks/services 미의존 (Presentation-common 레이어 순수성)
- **테스트 설계**: L1~L5 + K1~K5, MSW `delay()` 기반 결정적 이중 클릭 검증

### 2.3 Do (2026-07-31, TDD)

| 단계 | 내용 | 결과 |
|------|------|------|
| Red 1 | `LoadingButton.test.tsx` L1~L5 작성 | 모듈 없음 실패 확인 |
| Green 1 | `LoadingButton.tsx` 구현 | 5/5 통과 |
| Red 2 | `index.test.tsx` K1~K5 추가 | 4건 실패 — **현재 결함 그대로 재현** (POST 2회, unhandled ApiError) |
| Green 2 | `AgentKnowledgePage` 수정 (가드+에러 표면화) | 10/10 통과 |
| 검증 | type-check·lint·전체 회귀 | 통과, 신규 회귀 0 |

**구현 세부**:
- `src/components/common/LoadingButton.tsx` (신규): `ButtonHTMLAttributes` 확장, `isPending || disabled` 병합, `isPending ? undefined : onClick`, `aria-hidden` 스피너 SVG(`animate-spin`, currentColor), `pendingText ?? children` 폴백, `type="button"` 기본값, 외부 의존성 0
- `src/pages/AgentKnowledgePage/index.tsx` (수정): `submitError` 상태, `isSaving = create ∥ update`, `submitForm` 조기 반환 + try/catch(성공 시에만 폼 닫힘), 에러 초기화 4지점(`openCreate`/`openEdit`/`closeForm`/재시도 진입), 저장·폐기 버튼 LoadingButton 교체
- `CLAUDE.md`: 완료 파일 목록에 LoadingButton 등재 ("뮤테이션 버튼은 이 컴포넌트 사용 권장")

### 2.4 Check (2026-08-01)

- **문서**: `docs/03-analysis/features/mutation-pending-guard.analysis.md` (gap-detector)
- **Match Rate 98%** — LoadingButton 8/8, 페이지 수정 10/10, 테스트 9.5/10, 아키텍처·컨벤션·CLAUDE.md 전부 100%
- **Missing 0건**, Gap 3건 전부 Low/Info:
  - G1 (Low): K1의 2번째 클릭이 userEvent라 조기 반환 가드 계층 자체는 미검증 (L3가 부분 대체) → 후속 테스트 작업 시 강화
  - G2 (Low): className 전달이 `{...rest}` 경유 — 동작 동일, 문서 편차만
  - G3 (Info): 실행 검증은 Do 단계에서 완료된 것으로 확인
- **긍정 편차**: `closeForm` 헬퍼 추출, L2 검증 강화, K1+K2 병합

### 2.5 Act

- iterate 0회 (98% ≥ 90%)

---

## 3. Lessons Learned

| # | 교훈 | 적용 |
|---|------|------|
| 1 | **"수동 반복 패턴은 44번 잘해도 45번째 누락이 결함"** — 관례가 정착돼 있어도 강제 장치(필수 prop)가 없으면 구멍이 남는다 | 공통 컴포넌트에 가드를 내장하고 타입으로 강제하는 방식을 우선 검토 |
| 2 | **disabled 버튼에 userEvent 클릭은 가드 검증이 아니다** — 이벤트 자체가 발생하지 않아 가드가 없어도 통과한다 | 가드 계층 검증은 `fireEvent` 강제 발화 또는 핸들러 직접 호출로 (G1) |
| 3 | **Windows 전체 스위트 실행은 타임아웃 플래키 유발** (import 359s 등 부하) — 실패 3건이 격리 실행에선 전부 통과 | 전체 회귀 실패 시 격리 재실행으로 판정 후 회귀 여부 결론 |
| 4 | **`mutateAsync`는 catch 없으면 unhandled rejection** — 실패 침묵 + 콘솔 오염 | mutateAsync 사용 시 try/catch를 세트로 |

## 4. Follow-ups (스코프 밖 이월)

| 항목 | 내용 | 우선순위 |
|------|------|:---:|
| 수동 검증 | dev 서버에서 스피너·Network POST 1회·백엔드 중단 시 에러 문구 확인 (백엔드 기동 필요) | 배포 전 |
| K1 가드 검증 강화 | G1 — fireEvent 기반 2차 클릭 케이스 추가 | Low |
| LoadingButton 점진 채택 | 기존 화면 수정 시 LoadingButton으로 교체 (일괄 마이그레이션은 하지 않음) | 상시 |
| 전역 뮤테이션 인디케이터 | `useIsMutating` 기반 — 가벼운 뮤테이션 UX 부작용 검토 선행 | 후속 검토 |
| 서버 멱등성 | 백엔드 idempotency key — 프론트 가드는 1차 방어일 뿐 | 후속 검토 |

## 5. Document Index

| Phase | Document |
|-------|----------|
| Plan | `docs/01-plan/features/mutation-pending-guard.plan.md` |
| Design | `docs/02-design/features/mutation-pending-guard.design.md` |
| Analysis | `docs/03-analysis/features/mutation-pending-guard.analysis.md` |
| Report | `docs/04-report/features/mutation-pending-guard.report.md` (본 문서) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-01 | Completion report — Match 98%, iterate 0, 신규 회귀 0 | 배상규 |
