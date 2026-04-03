# EVAL-001 — 평가 데이터셋 추출 페이지

## 상태: 완료 (Mock 데이터)

## 목표
PDF/DOC 문서를 업로드하면 서버에서 평가용 질문-답변 쌍을 추출하여 테이블로 표시한다.

## 구현 완료 항목

### 타입
- [x] `src/types/eval.ts` — `EvalDatasetItem`, `EvalDatasetResponse`, `EvalExtractRequest`

### 상수
- [x] `src/constants/api.ts` — `EVAL_DATASET_EXTRACT` 엔드포인트 추가

### 서비스
- [x] `src/services/evalService.ts` — `extractDataset(file)` (multipart/form-data)

### 페이지
- [x] `src/pages/EvalDatasetPage/index.tsx` — 전체 페이지 구현

### 라우터
- [x] `src/App.tsx` — `/eval-dataset` 라우트 추가

### 사이드바
- [x] `src/components/layout/Sidebar.tsx` — "평가 데이터셋" 네비게이션 항목 추가 (active 상태 표시)

## UI 플로우
1. **Idle** — 드래그앤드롭 업로드 존 표시 (클릭 시 파일 탐색기 오픈)
2. **Loading** — 스피너 + "문서 분석 중..." 메시지
3. **Success** — 순서 / 질문 / 답변 테이블 + CSV 다운로드 버튼

## 허용 파일 형식
`.pdf`, `.doc`, `.docx`

## API 연동 (예정)
- 현재: 2초 setTimeout 후 Mock 데이터 반환
- 추후: `evalService.extractDataset(file)` 호출로 교체
- 엔드포인트: `POST /api/eval/extract` (multipart/form-data)
- 응답: `{ documentName, totalCount, items: [{ id, question, answer }] }`
