---
name: fullstack-feature
description: 풀스택 기능을 처음부터 끝까지 구현할 때 사용한다. 백엔드(FastAPI/Python)와 프론트엔드(React/TypeScript)를 함께 작업하는 경우 반드시 이 스킬을 실행한다. "기능 추가해줘", "API랑 화면 같이 만들어줘", "풀스택으로 구현해줘", "백엔드랑 프론트 연결해줘" 같은 말이 나오면 즉시 실행한다. 단계를 건너뛰거나 순서를 바꾸지 않는다.
---

# Fullstack Feature

백엔드 → 타입 동기화 → 프론트엔드 순서로 구현한다. 스키마가 확정되기 전에 프론트엔드 작업을 시작하지 않는다.

---

## Step 1 — 도메인 설계 (idt/)

시작 전에 프로젝트 컨벤션을 먼저 읽는다.

```bash
cat idt/CLAUDE.md
```

그 다음 도메인 레이어를 설계한다.

1. `idt/src/domain/` — Entity / ValueObject 작성
2. `idt/src/interfaces/schemas/` — Request / Response 스키마 정의 (Pydantic)

**스키마가 확정되기 전까지 Step 4(프론트엔드)를 시작하지 않는다.**

---

## Step 2 — 백엔드 구현 (idt/)

TDD 순서를 지킨다: 테스트 먼저, 구현 나중.

```bash
# 1. 테스트 작성 후 실행 (Red)
pytest idt/tests/ -v

# 2. 구현 후 다시 실행 (Green)
pytest idt/tests/ -v
```

구현 순서:
1. `idt/src/application/` — UseCase 구현
2. `idt/src/infrastructure/` — Adapter 구현
3. `idt/src/api/routes/` — 라우터 등록

완료 후 서버를 실행해서 API가 정상 동작하는지 확인한다.

```bash
cd idt
uvicorn src.api.main:app --reload --port 8000
```

---

## Step 3 — 타입 동기화 (idt/ → idt_front/)

백엔드 스키마를 기준으로 프론트엔드 타입을 맞춘다. 이 단계는 `api-contract-sync` 스킬을 따른다.

```bash
# 확정된 스키마 확인
cat idt/src/interfaces/schemas/{name}.py
```

수정 파일:
- `idt_front/src/types/{name}.ts` — TypeScript 타입 반영
- `idt_front/src/constants/api.ts` — 엔드포인트 상수 추가

**백엔드 스키마가 이후에 변경되면 이 단계부터 다시 실행한다.**

---

## Step 4 — 프론트엔드 구현 (idt_front/)

시작 전에 프론트엔드 컨벤션을 읽는다.

```bash
cat idt_front/CLAUDE.md
```

WebSocket을 사용하는 경우:

```bash
cat idt_front/.env.local | grep VITE_WS_URL
```

TDD 순서를 지킨다: 테스트 먼저, 구현 나중.

```bash
# 1. Vitest 테스트 + MSW 핸들러 작성 후 실행 (Red)
cd idt_front && npx vitest run

# 2. 구현 후 다시 실행 (Green)
cd idt_front && npx vitest run
```

구현 순서:
1. `idt_front/src/services/` — API 서비스 구현
2. `idt_front/src/hooks/` — TanStack Query 훅 구현
3. `idt_front/src/components/` 또는 `pages/` — UI 구현

---

## Step 5 — 통합 확인

백엔드와 프론트엔드를 동시에 실행해서 실제 연동을 확인한다.

```bash
# 터미널 1 — 백엔드
cd idt && uvicorn src.api.main:app --reload --port 8000

# 터미널 2 — 프론트엔드
cd idt_front && npm run dev

# 터미널 3 — TypeScript 타입 오류 확인
cd idt_front && npx tsc --noEmit
```

`tsc --noEmit` 오류가 없으면 완료다.

---

## 완료 보고 형식

```
✅ Fullstack Feature 구현 완료

기능명: {기능명}

백엔드:
  - 도메인: idt/src/domain/{name}.py
  - UseCase: idt/src/application/{name}/use_case.py
  - 라우터: idt/src/api/routes/{name}_router.py

프론트엔드:
  - 타입: idt_front/src/types/{name}.ts
  - 서비스: idt_front/src/services/{name}Service.ts
  - 훅: idt_front/src/hooks/use{Name}.ts
  - 컴포넌트: idt_front/src/components/{Name}.tsx

tsc --noEmit: 오류 없음 ✓
pytest: {N}개 통과 ✓
```