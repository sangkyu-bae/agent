---
title: 뮤테이션 버튼은 LoadingButton — isPending 필수 prop + disabled 테스트 함정
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt_front/docs/archive/2026-08/mutation-pending-guard/mutation-pending-guard.report.md
  - idt_front/src/components/common/LoadingButton.tsx
  - idt_front/src/pages/AgentKnowledgePage/index.tsx (적용 선례)
  - 커밋 edef075f
confidence: 0.9
version: 1
created: 2026-08-03
updated: 2026-08-03
verified_at: 4f650d3c
---

## 문제

지식 등록 버튼이 서버 대기 중에도 활성이라 이중 클릭 → POST 2회 → 동일 문서 2건 생성.
프로젝트에 이미 44개 파일이 `mutation.isPending` 패턴을 쓰고 있었지만 **각 화면이 수동으로
붙이는 구조라 45번째 누락이 곧 결함**이었다.

## 검증된 사실

1. **공통 `LoadingButton`** (`src/components/common/LoadingButton.tsx`):
   - `isPending`이 **필수 prop** — 가드 누락을 타입 에러로 차단 (관례를 강제 장치로 승격).
   - 3중 방어: `disabled` 병합(1차) + pending 중 `onClick` 무시(2차) + submit 핸들러 조기
     반환(3차). 스타일은 `className` 주입식(디자인 비강제), hooks/services 의존성 0.
   - 기존 44개 파일은 무변경(독립 opt-in) — 신규/수정 화면의 뮤테이션 버튼만 이걸로 교체.
2. **테스트 함정 — disabled 버튼에 `userEvent.click`은 가드 검증이 아니다**:
   userEvent는 disabled 요소에 이벤트 자체를 발생시키지 않으므로 가드가 없어도 테스트가
   통과한다. 가드 계층 검증은 `fireEvent` 강제 발화 또는 핸들러 직접 호출로 해야 한다.
   이중 제출 자체는 MSW `delay()` 응답으로 "2회 클릭 → POST 1회"를 결정적으로 단언.
3. **`mutateAsync`는 try/catch 세트 필수** — catch 없으면 실패가 침묵하고 unhandled
   rejection이 콘솔을 오염시킨다. 성공 시에만 폼을 닫고, 실패 시 `role="alert"` 인라인
   문구 + 입력 보존으로 재시도 가능하게.

## 다음에 적용하는 법

- 뮤테이션을 트리거하는 버튼은 LoadingButton 사용 (`isPending={mutation.isPending}`).
- 이중 제출 회귀 테스트는 MSW 지연 + 호출 횟수 단언으로 작성하고, disabled 상태 검증과
  가드 로직 검증을 혼동하지 말 것.
- 전역 오버레이(useIsMutating)·백엔드 멱등성 키는 의도적으로 스코프 밖 — 재제안 전 확인.
