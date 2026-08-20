---
title: TSX 파일 작성 함정 — 런타임 export는 컴포넌트 파일 밖으로, 제어 문자는 이스케이프로
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt_front/docs/archive/2026-08/progress-card/progress-card.report.md (§6.2 — react-refresh 규칙으로 Do 단계 재작업)
  - idt_front/docs/archive/2026-08/question-card/question-card.report.md (§6.1/§6.2 — 규칙 선반영으로 예방 + 제어 문자 바이너리화)
  - idt_front/src/types/progress.ts (분리 결과물, ⚠️ 미커밋)
confidence: 0.8
version: 1
created: 2026-08-20
updated: 2026-08-20
verified_at: 7c3ffdd
---

# TSX 파일 작성 함정 — 런타임 export 분리 + 제어 문자 이스케이프

## 문제

새 컴포넌트 파일을 만들 때 반복해서 걸리는 함정 2개. 둘 다 "코드는 맞는데 도구가
거부"하는 유형이라 설계 시점에 모르면 Do 단계 재작업이 된다.

## 검증된 사실

### 1. 컴포넌트 `.tsx`에서 컴포넌트 외 런타임 값을 export하면 안 된다

ESLint `react-refresh/only-export-components` 규칙이 컴포넌트 파일에서의 상수 등
런타임 export를 막는다 (HMR Fast Refresh가 깨지기 때문). progress-card 사이클에서
타입·상수를 컴포넌트에 co-locate했다가 **Do 단계에서 `types/progress.ts` 분리
재작업**이 발생했고, question-card 사이클은 이 규칙을 설계에 선반영해
(`question-card/types.ts` 별도 파일) 재작업 0이었다.

- 타입만 export하는 것은 무방(type-only), **런타임 값(상수·헬퍼)은 `types/`,
  `constants/`, 또는 전용 `types.ts`로** 뺀다.
- 공용 컴포넌트 Design 문서를 쓸 때 파일 구성에 이 분리를 미리 그린다.

### 2. 유니코드 제어 문자를 소스·문서에 직접 쓰면 파일이 바이너리로 인식된다

question-card 사이클에서 제어 문자를 파일에 직접 넣자 git/ripgrep이 그 파일을
**바이너리로 취급**해 diff·grep이 불능이 됐다 (실증: 그 사이클의 report.md 자체가
지금도 `\0` 바이트 때문에 grep에서 "binary file matches"로만 나온다). 특수 문자가
필요하면 처음부터 **이스케이프 표기**(`U+0000` 등)로 쓴다 — 테스트 fixture에 키 입력
문자를 넣을 때 특히 주의.

## 다음에 적용하는 법

1. 새 `.tsx` 컴포넌트 파일 생성 시: 런타임 export가 컴포넌트뿐인지 확인. 상수·타입이
   생기면 즉시 별도 파일로.
2. 소스·마크다운에 비출력 문자를 넣어야 하면 리터럴 붙여넣기 금지, 이스케이프 표기.
   이미 오염된 파일은 `tr -d '\0'`로 읽을 수는 있지만 재저장으로 정화하는 것이 맞다.
