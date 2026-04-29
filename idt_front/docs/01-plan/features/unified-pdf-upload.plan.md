# Plan: unified-pdf-upload

> CollectionDocumentsPage에서 PDF 통합 업로드 모달 구현

## 1. 개요

| 항목 | 내용 |
|------|------|
| Feature ID | UPLOAD-001 |
| 우선순위 | P1 |
| 예상 규모 | Medium (타입 + 서비스 + 훅 + 모달 컴포넌트 + 페이지 연결) |
| 선행 조건 | 백엔드 `POST /api/v1/documents/upload-all` 구현 완료 |

## 2. 배경 및 목적

현재 `CollectionDocumentsPage`에 "문서 업로드" 버튼이 있으나 onClick이 연결되어 있지 않다.
백엔드에 PDF 통합 업로드 API(`/api/v1/documents/upload-all`)가 구현되어 있으므로,
프론트엔드에서 모달 기반 업로드 UI를 구현하여 연결한다.

**핵심 가치**: 기존 2회 API 호출(documents/upload + chunk-index/upload)을 1회로 통합한 백엔드 API를 활용하여 사용자 경험을 단순화한다.

## 3. 기능 요구사항

### FR-01: 업로드 모달 열기/닫기
- CollectionDocumentsPage의 "문서 업로드" 버튼 클릭 시 모달 오픈
- 모달 외부 클릭 또는 X 버튼으로 닫기
- ESC 키로 닫기
- 업로드 진행 중에는 닫기 방지 (확인 다이얼로그)

### FR-02: 파일 선택 (드래그앤드롭 + 클릭)
- EvalDatasetPage와 동일한 디자인 패턴의 드래그앤드롭 영역
- 드래그 오버 시 시각적 피드백 (border-violet-400, bg-violet-50/60)
- 클릭 시 파일 선택 다이얼로그 (PDF만 허용)
- 파일 확장자 검증: `.pdf`만 허용
- 동일 파일 재선택 허용 (input value 초기화)

### FR-03: 청킹 옵션 설정 (선택적)
- 접이식(collapsible) "고급 옵션" 섹션
- child_chunk_size: 숫자 입력 (100~4000, 기본값 500)
- child_chunk_overlap: 숫자 입력 (0~500, 기본값 50)
- top_keywords: 숫자 입력 (1~50, 기본값 10)
- 입력값 범위 검증 (min/max)

### FR-04: API 호출
- `POST /api/v1/documents/upload-all` (multipart/form-data)
- Query 파라미터: user_id, collection_name (자동 주입), child_chunk_size, child_chunk_overlap, top_keywords
- collection_name: URL params(`useParams`)에서 추출
- user_id: 임시로 하드코딩 (추후 auth store 연동)

### FR-05: 업로드 상태 표시
- `idle`: 초기 상태 (파일 선택 영역 표시)
- `loading`: 업로드 + 처리 중 (스피너 + 진행 메시지)
- `success` (completed): Qdrant + ES 모두 성공 → 결과 요약 표시
- `partial`: 한쪽만 성공 → 경고와 함께 결과 표시
- `error` (failed): 양쪽 실패 또는 422 에러 → 에러 메시지 표시

### FR-06: 결과 표시
- 성공 시: document_id, filename, total_pages, chunk_count, 사용된 임베딩 모델
- Qdrant 결과: collection_name, stored_ids 개수, status
- ES 결과: index_name, indexed_count, status
- 청킹 설정: strategy, parent/child 크기, overlap
- 부분 성공 시: 실패한 쪽의 error 메시지 강조
- 실패 시: 에러 메시지 + 재시도 버튼

### FR-07: 완료 후 갱신
- 업로드 성공/부분성공 후 모달 닫기 버튼 활성화
- 모달 닫을 때 `useCollectionDocuments` 쿼리 invalidate → 목록 자동 갱신
- TanStack Query `queryClient.invalidateQueries` 사용

## 4. API 스펙

### POST `/api/v1/documents/upload-all`

**Request** (`multipart/form-data`):

| 파라미터 | 위치 | 타입 | 필수 | 제약 | 기본값 | 설명 |
|----------|------|------|:----:|------|--------|------|
| file | Body (File) | UploadFile | O | PDF만 | - | 업로드할 PDF |
| user_id | Query | string | O | - | - | 문서 소유자 |
| collection_name | Query | string | O | 기존 컬렉션 | - | 대상 컬렉션명 |
| child_chunk_size | Query | integer | X | 100~4000 | 500 | 자식 청크 크기 |
| child_chunk_overlap | Query | integer | X | 0~500 | 50 | 오버랩 크기 |
| top_keywords | Query | integer | X | 1~50 | 10 | 키워드 수 |

**Response (200)**:

```json
{
  "document_id": "uuid",
  "filename": "document.pdf",
  "total_pages": 10,
  "chunk_count": 25,
  "qdrant": {
    "collection_name": "my-collection",
    "stored_ids": ["id-1", "..."],
    "embedding_model": "text-embedding-3-small",
    "status": "success",
    "error": null
  },
  "es": {
    "index_name": "idt-documents",
    "indexed_count": 25,
    "status": "success",
    "error": null
  },
  "chunking_config": {
    "strategy": "parent_child",
    "parent_chunk_size": 2000,
    "child_chunk_size": 500,
    "child_chunk_overlap": 50
  },
  "status": "completed"
}
```

**status**: `"completed"` | `"partial"` | `"failed"`

**Error Codes**: 422 (컬렉션 미존재, 임베딩 모델 오류, PDF 파싱 실패), 500 (양쪽 저장 실패)

## 5. 구현 범위

### 5-1. 신규 파일

| 파일 | 설명 |
|------|------|
| `src/types/unifiedUpload.ts` | 요청/응답 타입 정의 |
| `src/services/unifiedUploadService.ts` | API 호출 함수 |
| `src/hooks/useUnifiedUpload.ts` | TanStack Query useMutation 훅 |
| `src/components/collection/UploadDocumentModal.tsx` | 업로드 모달 컴포넌트 |

### 5-2. 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src/constants/api.ts` | `DOCUMENT_UPLOAD_ALL` 엔드포인트 추가 |
| `src/pages/CollectionDocumentsPage/index.tsx` | 모달 상태 관리 + 버튼 onClick 연결 |
| `src/lib/queryKeys.ts` | (필요 시) 업로드 관련 쿼리 키 추가 |

## 6. 구현 순서

```
1. src/types/unifiedUpload.ts           — 타입 정의
2. src/constants/api.ts                  — 엔드포인트 상수 추가
3. src/services/unifiedUploadService.ts  — API 호출 함수
4. src/hooks/useUnifiedUpload.ts         — useMutation 훅
5. src/components/collection/UploadDocumentModal.tsx — 모달 UI
6. src/pages/CollectionDocumentsPage/index.tsx — 모달 연결
```

## 7. UI 설계 요약

### 모달 레이아웃
```
┌─────────────────────────────────────────┐
│  [X]                                    │
│  PDF 문서 업로드                          │
│  컬렉션: {collectionName}                │
│                                         │
│  ┌─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐  │
│  │                                   │  │
│  │  (upload icon)                    │  │
│  │  파일을 드래그하거나 클릭하여 업로드  │  │
│  │  PDF 파일만 지원                   │  │
│  │                                   │  │
│  └─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘  │
│                                         │
│  ▶ 고급 옵션                             │
│    ┌ child_chunk_size: [500]  ┐         │
│    │ child_chunk_overlap: [50] │         │
│    │ top_keywords: [10]        │         │
│    └──────────────────────────┘         │
│                                         │
│           [업로드 시작]                   │
└─────────────────────────────────────────┘
```

### 상태별 모달 내용
- **idle**: 드래그앤드롭 영역 + 고급 옵션 + 업로드 버튼(비활성)
- **파일 선택됨**: 파일명 표시 + 업로드 버튼(활성)
- **loading**: 스피너 + "문서 처리 중..." 메시지
- **success**: 결과 요약 카드 (Qdrant/ES 상태) + 닫기 버튼
- **partial**: 경고 배지 + 성공/실패 상세 + 닫기 버튼
- **error**: 에러 메시지 + 재시도 버튼 + 닫기 버튼

### 디자인 토큰 (기존 시스템 준수)
- 모달 배경: `bg-black/50` 오버레이
- 모달 본체: `rounded-2xl bg-white shadow-xl`, max-w-lg
- 드래그 영역: EvalDatasetPage 패턴 그대로 (border-2 border-dashed rounded-2xl)
- 버튼: 기존 Primary/Secondary 패턴 사용
- 성공 배지: `bg-emerald-50 text-emerald-600 border-emerald-200`
- 경고 배지: `bg-amber-50 text-amber-600 border-amber-200`
- 에러 배지: `bg-red-50 text-red-500 border-red-200`

## 8. 제약 사항

- user_id는 현재 auth 미완성으로 임시 하드코딩 (`"default-user"`) → 추후 authStore 연동
- 파일 크기 제한은 백엔드에 위임 (프론트에서는 확장자만 검증)
- 다중 파일 업로드는 이번 스코프에서 제외 (단일 파일만)
- 업로드 진행률(%) 표시는 제외 (백엔드가 streaming 응답을 제공하지 않으므로)

## 9. 테스트 계획

| 대상 | 테스트 내용 | 우선순위 |
|------|-----------|---------|
| `useUnifiedUpload` 훅 | mutation 호출, 성공/에러 처리, invalidation | P1 |
| `unifiedUploadService` | multipart/form-data 전송, query params 조합 | P1 |
| `UploadDocumentModal` | 파일 선택, 드래그앤드롭, 상태 전환, 결과 표시 | P2 |
| CollectionDocumentsPage 연동 | 모달 열기/닫기, 목록 갱신 | P2 |

## 10. 참조

- 백엔드 API 문서: `docs/api/unfieid-pdf.md`
- 디자인 참조: `src/pages/EvalDatasetPage/index.tsx` (드래그앤드롭 영역)
- 기존 문서 페이지: `src/pages/CollectionDocumentsPage/index.tsx`
- API 상수: `src/constants/api.ts`
