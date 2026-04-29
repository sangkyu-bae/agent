# Design: unified-pdf-upload

> Plan 참조: `docs/01-plan/features/unified-pdf-upload.plan.md`

## 1. 구현 순서

```
Step 1. src/types/unifiedUpload.ts            — 타입 정의
Step 2. src/constants/api.ts                   — 엔드포인트 상수 추가
Step 3. src/services/unifiedUploadService.ts   — API 호출 함수
Step 4. src/hooks/useUnifiedUpload.ts          — useMutation 훅
Step 5. src/components/collection/UploadDocumentModal.tsx — 모달 UI
Step 6. src/pages/CollectionDocumentsPage/index.tsx — 모달 연결
```

---

## 2. 타입 정의 (`src/types/unifiedUpload.ts`)

```typescript
// ── 요청 파라미터 (query string) ─────────────────────

interface UnifiedUploadParams {
  user_id: string;
  collection_name: string;
  child_chunk_size?: number;   // 100~4000, default 500
  child_chunk_overlap?: number; // 0~500, default 50
  top_keywords?: number;        // 1~50, default 10
}

// ── 응답 ─────────────────────────────────────────────

interface QdrantResult {
  collection_name: string;
  stored_ids: string[];
  embedding_model: string;
  status: 'success' | 'failed';
  error: string | null;
}

interface EsResult {
  index_name: string;
  indexed_count: number;
  status: 'success' | 'failed';
  error: string | null;
}

interface ChunkingConfig {
  strategy: string;          // "parent_child"
  parent_chunk_size: number; // 2000 (고정)
  child_chunk_size: number;
  child_chunk_overlap: number;
}

type UnifiedUploadStatus = 'completed' | 'partial' | 'failed';

interface UnifiedUploadResponse {
  document_id: string;
  filename: string;
  total_pages: number;
  chunk_count: number;
  qdrant: QdrantResult;
  es: EsResult;
  chunking_config: ChunkingConfig;
  status: UnifiedUploadStatus;
}

// ── 모달 내부 상태 ───────────────────────────────────

type UploadModalStatus = 'idle' | 'loading' | 'success' | 'partial' | 'error';

// ── 고급 옵션 폼 ────────────────────────────────────

interface ChunkingOptions {
  childChunkSize: number;    // default 500
  childChunkOverlap: number; // default 50
  topKeywords: number;       // default 10
}

const DEFAULT_CHUNKING_OPTIONS: ChunkingOptions = {
  childChunkSize: 500,
  childChunkOverlap: 50,
  topKeywords: 10,
};
```

**네이밍 규칙 준수**:
- API 응답: `UnifiedUploadResponse` (`XxxResponse` 접미사)
- API 요청 파라미터: `UnifiedUploadParams` (`XxxParams` 접미사)
- 내부 상태: 접미사 없음 (`ChunkingOptions`, `UploadModalStatus`)

---

## 3. 엔드포인트 상수 (`src/constants/api.ts`)

기존 `API_ENDPOINTS` 객체에 추가:

```typescript
// 기존 코드 위치: "// RAG / Documents" 섹션 하단

// Unified Document Upload
DOCUMENT_UPLOAD_ALL: '/api/v1/documents/upload-all',
```

---

## 4. 서비스 레이어 (`src/services/unifiedUploadService.ts`)

```typescript
import apiClient from '@/services/api/client';
import { API_ENDPOINTS } from '@/constants/api';
import type { UnifiedUploadParams, UnifiedUploadResponse } from '@/types/unifiedUpload';

const unifiedUploadService = {
  uploadDocument: async (
    file: File,
    params: UnifiedUploadParams,
  ): Promise<UnifiedUploadResponse> => {
    const formData = new FormData();
    formData.append('file', file);

    const response = await apiClient.post<UnifiedUploadResponse>(
      API_ENDPOINTS.DOCUMENT_UPLOAD_ALL,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        params,
        timeout: 120_000, // PDF 처리는 오래 걸릴 수 있음
      },
    );
    return response.data;
  },
};

export default unifiedUploadService;
```

**설계 결정**:
- `apiClient` 사용 (auth 미적용 API — Plan 제약사항 참조)
- `params`를 axios의 `params` 옵션으로 전달 → query string 자동 직렬화
- timeout 120초: PDF 파싱 + 임베딩 + 병렬 저장 시간 고려
- `formData`에는 `file`만 추가 (나머지는 query param)

---

## 5. 훅 (`src/hooks/useUnifiedUpload.ts`)

```typescript
import { useMutation } from '@tanstack/react-query';
import unifiedUploadService from '@/services/unifiedUploadService';
import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import type { UnifiedUploadParams, UnifiedUploadResponse } from '@/types/unifiedUpload';

interface UseUnifiedUploadOptions {
  onSuccess?: (data: UnifiedUploadResponse) => void;
  onError?: (error: Error) => void;
}

export const useUnifiedUpload = (
  collectionName: string,
  options?: UseUnifiedUploadOptions,
) =>
  useMutation({
    mutationFn: ({ file, params }: { file: File; params: UnifiedUploadParams }) =>
      unifiedUploadService.uploadDocument(file, params),
    onSuccess: (data) => {
      // 업로드 성공/부분 성공 시 해당 컬렉션 문서 목록 갱신
      if (data.status !== 'failed') {
        queryClient.invalidateQueries({
          queryKey: queryKeys.collections.documents(collectionName),
        });
      }
      options?.onSuccess?.(data);
    },
    onError: (error: Error) => {
      options?.onError?.(error);
    },
  });
```

**설계 결정**:
- `queryKeys.ts` 수정 불필요 — 기존 `queryKeys.collections.documents(name)` 재사용
- `collectionName`을 훅 매개변수로 받아 invalidation 대상 특정
- `failed` 상태에서는 invalidation 생략 (문서 미저장)
- 콜백을 options로 제공하여 모달에서 상태 전환에 활용

---

## 6. 모달 컴포넌트 (`src/components/collection/UploadDocumentModal.tsx`)

### 6-1. Props 인터페이스

```typescript
interface UploadDocumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  collectionName: string;
}
```

### 6-2. 내부 상태

```typescript
const [selectedFile, setSelectedFile] = useState<File | null>(null);
const [isDragOver, setIsDragOver] = useState(false);
const [showOptions, setShowOptions] = useState(false);
const [options, setOptions] = useState<ChunkingOptions>(DEFAULT_CHUNKING_OPTIONS);
const [uploadResult, setUploadResult] = useState<UnifiedUploadResponse | null>(null);
const [modalStatus, setModalStatus] = useState<UploadModalStatus>('idle');
const [errorMessage, setErrorMessage] = useState<string>('');
const fileInputRef = useRef<HTMLInputElement>(null);
```

### 6-3. 상태 전이 다이어그램

```
idle ──[파일 선택]──→ idle (selectedFile 세팅)
idle ──[업로드 클릭]──→ loading
loading ──[200 + completed]──→ success
loading ──[200 + partial]──→ partial
loading ──[200 + failed / 422 / 500]──→ error
success ──[닫기]──→ (모달 닫힘 + invalidation)
partial ──[닫기]──→ (모달 닫힘 + invalidation)
error ──[재시도]──→ loading
error ──[닫기]──→ (모달 닫힘)
```

### 6-4. 핵심 핸들러

```typescript
// 파일 검증
const isValidPdf = (file: File): boolean =>
  file.name.toLowerCase().endsWith('.pdf');

// 파일 선택 (클릭)
const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
  const file = e.target.files?.[0];
  if (file && isValidPdf(file)) {
    setSelectedFile(file);
  } else if (file) {
    alert('PDF 파일만 업로드할 수 있습니다.');
  }
  e.target.value = '';
};

// 드래그앤드롭
const handleDrop = (e: React.DragEvent) => {
  e.preventDefault();
  setIsDragOver(false);
  const file = e.dataTransfer.files[0];
  if (file && isValidPdf(file)) {
    setSelectedFile(file);
  } else if (file) {
    alert('PDF 파일만 업로드할 수 있습니다.');
  }
};

// 업로드 실행
const handleUpload = () => {
  if (!selectedFile) return;
  setModalStatus('loading');
  setErrorMessage('');

  mutation.mutate({
    file: selectedFile,
    params: {
      user_id: 'default-user',
      collection_name: collectionName,
      child_chunk_size: options.childChunkSize,
      child_chunk_overlap: options.childChunkOverlap,
      top_keywords: options.topKeywords,
    },
  });
};

// mutation 콜백
// onSuccess → setUploadResult(data) + setModalStatus(data.status에 따라)
// onError → setModalStatus('error') + setErrorMessage(...)

// 모달 닫기
const handleClose = () => {
  if (modalStatus === 'loading') return; // 업로드 중 닫기 방지
  resetState();
  onClose();
};

// 재시도
const handleRetry = () => {
  setModalStatus('idle');
  setUploadResult(null);
  setErrorMessage('');
};

// ESC 키 처리
useEffect(() => {
  const handleEsc = (e: KeyboardEvent) => {
    if (e.key === 'Escape' && modalStatus !== 'loading') handleClose();
  };
  if (isOpen) window.addEventListener('keydown', handleEsc);
  return () => window.removeEventListener('keydown', handleEsc);
}, [isOpen, modalStatus]);
```

### 6-5. 렌더링 구조 (상태별)

```
<Overlay onClick={handleClose}>
  <ModalContainer onClick={e => e.stopPropagation()}>

    {/* 헤더 — 항상 표시 */}
    <ModalHeader>
      <Title>PDF 문서 업로드</Title>
      <Subtitle>컬렉션: {collectionName}</Subtitle>
      <CloseButton onClick={handleClose} disabled={modalStatus === 'loading'} />
    </ModalHeader>

    {/* 바디 — 상태별 분기 */}
    {modalStatus === 'idle' && (
      <>
        <DropZone />           {/* FR-02 */}
        <SelectedFileInfo />   {/* 파일 선택됨 → 파일명 + 크기 + 제거 버튼 */}
        <AdvancedOptions />    {/* FR-03 */}
      </>
    )}

    {modalStatus === 'loading' && (
      <LoadingView filename={selectedFile.name} />  {/* FR-05 */}
    )}

    {(modalStatus === 'success' || modalStatus === 'partial') && (
      <ResultView result={uploadResult} />  {/* FR-06 */}
    )}

    {modalStatus === 'error' && (
      <ErrorView message={errorMessage} onRetry={handleRetry} />
    )}

    {/* 푸터 — 상태별 버튼 */}
    <ModalFooter>
      {modalStatus === 'idle' && (
        <UploadButton disabled={!selectedFile} onClick={handleUpload} />
      )}
      {(modalStatus === 'success' || modalStatus === 'partial' || modalStatus === 'error') && (
        <CloseButton onClick={handleClose} />
      )}
    </ModalFooter>

  </ModalContainer>
</Overlay>
```

### 6-6. 세부 UI 스펙

#### Overlay
```tsx
// isOpen이 false면 렌더링하지 않음
{isOpen && (
  <div
    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
    onClick={handleClose}
  >
```

#### Modal Container
```tsx
<div
  className="relative w-full max-w-lg rounded-2xl bg-white shadow-xl"
  onClick={e => e.stopPropagation()}
>
```

#### DropZone (idle 상태, 파일 미선택)
EvalDatasetPage 패턴 그대로:
```tsx
<div
  onDrop={handleDrop}
  onDragOver={handleDragOver}
  onDragLeave={() => setIsDragOver(false)}
  onClick={() => fileInputRef.current?.click()}
  className={`group relative flex cursor-pointer flex-col items-center justify-center
    rounded-2xl border-2 border-dashed px-8 py-12 transition-all duration-200
    ${isDragOver
      ? 'border-violet-400 bg-violet-50/60'
      : 'border-zinc-200 bg-zinc-50/50 hover:border-violet-300 hover:bg-violet-50/30'
    }`}
>
  {/* 아이콘 — 기존 gradient 사용 */}
  <div
    className={`mb-4 flex h-14 w-14 items-center justify-center rounded-2xl shadow-md
      transition-all duration-200 ${isDragOver ? 'scale-110' : 'group-hover:scale-105'}`}
    style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
  >
    <UploadIcon className="h-7 w-7 text-white" />
  </div>

  {isDragOver ? (
    <p className="text-[15px] font-semibold text-violet-600">여기에 놓아주세요</p>
  ) : (
    <>
      <p className="text-[15px] font-semibold text-zinc-700">
        파일을 드래그하거나 클릭하여 업로드
      </p>
      <p className="mt-1.5 text-[12.5px] text-zinc-400">PDF 파일만 지원</p>
    </>
  )}

  <input ref={fileInputRef} type="file" accept=".pdf" className="hidden"
    onChange={handleFileChange} />
</div>
```

#### Selected File Info (idle 상태, 파일 선택됨)
```tsx
<div className="mt-3 flex items-center justify-between rounded-xl border border-zinc-200
  bg-zinc-50 px-4 py-3">
  <div className="flex items-center gap-3">
    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-red-50">
      <PdfIcon className="h-5 w-5 text-red-500" />
    </div>
    <div>
      <p className="text-[13.5px] font-medium text-zinc-800">{file.name}</p>
      <p className="text-[12px] text-zinc-400">{formatFileSize(file.size)}</p>
    </div>
  </div>
  <button onClick={() => setSelectedFile(null)}
    className="text-zinc-400 hover:text-red-500 transition-colors">
    <XIcon className="h-4 w-4" />
  </button>
</div>
```

#### Advanced Options (접이식)
```tsx
<button
  onClick={() => setShowOptions(!showOptions)}
  className="mt-4 flex items-center gap-1.5 text-[13px] font-medium text-zinc-500
    hover:text-zinc-700 transition-colors"
>
  <ChevronIcon className={`h-4 w-4 transition-transform ${showOptions ? 'rotate-90' : ''}`} />
  고급 옵션
</button>

{showOptions && (
  <div className="mt-3 space-y-3 rounded-xl border border-zinc-200 bg-zinc-50/50 p-4">
    {/* 각 입력 필드 */}
    <OptionField
      label="청크 크기 (토큰)"
      value={options.childChunkSize}
      onChange={v => setOptions(prev => ({ ...prev, childChunkSize: v }))}
      min={100} max={4000} step={100}
    />
    <OptionField
      label="청크 오버랩 (토큰)"
      value={options.childChunkOverlap}
      onChange={v => setOptions(prev => ({ ...prev, childChunkOverlap: v }))}
      min={0} max={500} step={10}
    />
    <OptionField
      label="키워드 수"
      value={options.topKeywords}
      onChange={v => setOptions(prev => ({ ...prev, topKeywords: v }))}
      min={1} max={50} step={1}
    />
  </div>
)}
```

각 `OptionField`는 인라인으로 구현 (별도 컴포넌트 불필요):
```tsx
// label + number input 한 줄
<div className="flex items-center justify-between">
  <label className="text-[13px] text-zinc-600">{label}</label>
  <input
    type="number"
    value={value}
    onChange={e => onChange(Number(e.target.value))}
    min={min} max={max} step={step}
    className="w-24 rounded-lg border border-zinc-300 bg-white px-3 py-1.5
      text-right text-[13px] text-zinc-800 outline-none
      focus:border-violet-400 transition-colors"
  />
</div>
```

#### Loading View
EvalDatasetPage 로딩 패턴:
```tsx
<div className="flex flex-col items-center justify-center py-12">
  <div className="relative mb-5">
    <div className="h-14 w-14 animate-spin rounded-full border-4 border-zinc-200"
      style={{ borderTopColor: '#7c3aed' }} />
    <div className="absolute inset-0 m-auto h-6 w-6 rounded-full"
      style={{ background: 'linear-gradient(135deg, #7c3aed, #4f46e5)',
        top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }} />
  </div>
  <p className="text-[15px] font-semibold text-zinc-700">문서 처리 중...</p>
  <p className="mt-1 text-[12.5px] text-zinc-400">
    <span className="font-medium text-violet-500">{filename}</span>을(를)
    분석하고 벡터를 생성하고 있습니다
  </p>
</div>
```

#### Result View (success / partial)
```tsx
<div className="space-y-4 py-4">
  {/* 상태 배지 */}
  <StatusBadge status={result.status} />

  {/* 문서 요약 */}
  <div className="rounded-xl border border-zinc-200 bg-white p-4">
    <div className="grid grid-cols-2 gap-3 text-[13px]">
      <InfoItem label="파일명" value={result.filename} />
      <InfoItem label="페이지 수" value={result.total_pages} />
      <InfoItem label="청크 수" value={result.chunk_count} />
      <InfoItem label="임베딩 모델" value={result.qdrant.embedding_model} />
    </div>
  </div>

  {/* Qdrant 결과 */}
  <StorageResultCard
    title="Qdrant (벡터)"
    status={result.qdrant.status}
    detail={`${result.qdrant.stored_ids.length}개 벡터 저장`}
    error={result.qdrant.error}
  />

  {/* ES 결과 */}
  <StorageResultCard
    title="Elasticsearch (BM25)"
    status={result.es.status}
    detail={`${result.es.indexed_count}개 인덱싱`}
    error={result.es.error}
  />
</div>
```

**StatusBadge** 매핑:
| status | 배경 | 텍스트 |
|--------|------|--------|
| `completed` | `bg-emerald-50 border-emerald-200` | `text-emerald-600` "업로드 완료" |
| `partial` | `bg-amber-50 border-amber-200` | `text-amber-600` "부분 성공" |

**StorageResultCard**:
```tsx
<div className={`flex items-center justify-between rounded-xl border p-3 ${
  status === 'success'
    ? 'border-emerald-200 bg-emerald-50/50'
    : 'border-red-200 bg-red-50/50'
}`}>
  <div className="flex items-center gap-2">
    {status === 'success' ? <CheckIcon /> : <XIcon />}
    <span className="text-[13px] font-medium">{title}</span>
  </div>
  <span className="text-[12px] text-zinc-500">{detail}</span>
</div>
{error && (
  <p className="mt-1 px-3 text-[12px] text-red-500">{error}</p>
)}
```

#### Error View
```tsx
<div className="flex flex-col items-center py-12">
  <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl
    bg-red-50 shadow-md">
    <AlertIcon className="h-7 w-7 text-red-500" />
  </div>
  <p className="text-[15px] font-semibold text-zinc-700">업로드 실패</p>
  <p className="mt-1 max-w-sm text-center text-[12.5px] text-zinc-400">{message}</p>
  <button onClick={handleRetry}
    className="mt-4 flex items-center gap-1.5 rounded-xl bg-violet-600 px-4 py-2.5
      text-[13.5px] font-medium text-white shadow-sm hover:bg-violet-700
      active:scale-95 transition-all">
    재시도
  </button>
</div>
```

#### Upload Button (Footer)
```tsx
<button
  disabled={!selectedFile}
  onClick={handleUpload}
  className={`flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3
    text-[14px] font-medium shadow-sm transition-all active:scale-95
    ${selectedFile
      ? 'bg-violet-600 text-white hover:bg-violet-700'
      : 'cursor-not-allowed bg-zinc-100 text-zinc-400'
    }`}
>
  <UploadIcon className="h-4 w-4" />
  업로드 시작
</button>
```

---

## 7. 페이지 연결 (`CollectionDocumentsPage/index.tsx`)

### 변경 사항

```typescript
// 추가 import
import UploadDocumentModal from '@/components/collection/UploadDocumentModal';

// 추가 state
const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);

// 버튼 onClick 연결
<button
  onClick={() => setIsUploadModalOpen(true)}
  className="flex items-center gap-2 rounded-xl bg-violet-600 ..."
>
  문서 업로드
</button>

// 모달 렌더링 (페이지 최하단, return 내부)
<UploadDocumentModal
  isOpen={isUploadModalOpen}
  onClose={() => setIsUploadModalOpen(false)}
  collectionName={collectionName}
/>
```

---

## 8. 유틸리티 함수

`src/utils/formatters.ts`에 이미 `formatFileSize`가 있으면 재사용, 없으면 모달 내부에 인라인 구현:

```typescript
const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};
```

---

## 9. 에러 처리 매핑

| 백엔드 에러 | 프론트 표시 메시지 |
|------------|-------------------|
| 422 `Collection '{name}' not found` | "컬렉션 '{name}'을(를) 찾을 수 없습니다" |
| 422 `Cannot determine embedding model...` | "임베딩 모델을 확인할 수 없습니다. 컬렉션 설정을 확인하세요" |
| 422 `Embedding model '{model}' not registered` | "등록되지 않은 임베딩 모델입니다: {model}" |
| 422 `Failed to parse PDF: {reason}` | "PDF 파일을 읽을 수 없습니다: {reason}" |
| 500 `Both Qdrant and ES storage failed` | "벡터 및 검색 저장소 모두 실패했습니다. 서버 상태를 확인하세요" |
| 네트워크 에러 / timeout | "서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요" |

에러 메시지 추출:
```typescript
const extractErrorMessage = (error: unknown): string => {
  if (error instanceof Error) {
    return error.message;
  }
  return '알 수 없는 오류가 발생했습니다.';
};
```

> `apiClient`의 response interceptor가 `error.response.data.message`를 이미 추출하므로,
> `error.message`에서 백엔드 `detail` 필드 값을 사용할 수 있다.
> 단, 백엔드가 `detail` 키로 반환하므로 interceptor의 `error.response?.data?.detail`도 확인 필요.

---

## 10. 파일 의존성 그래프

```
src/types/unifiedUpload.ts
  ← src/services/unifiedUploadService.ts
       ← src/hooks/useUnifiedUpload.ts
            ← src/components/collection/UploadDocumentModal.tsx
                 ← src/pages/CollectionDocumentsPage/index.tsx

src/constants/api.ts
  ← src/services/unifiedUploadService.ts

src/lib/queryKeys.ts (수정 없음 — 기존 collections.documents 재사용)
src/lib/queryClient.ts (수정 없음)
```

---

## 11. 컴포넌트 규모 예상

| 파일 | 예상 줄 수 | 비고 |
|------|-----------|------|
| `unifiedUpload.ts` | ~50 | 타입 정의만 |
| `api.ts` 변경 | +2 | 엔드포인트 1줄 추가 |
| `unifiedUploadService.ts` | ~25 | 단일 함수 |
| `useUnifiedUpload.ts` | ~30 | useMutation 1개 |
| `UploadDocumentModal.tsx` | ~250 | 5개 상태 렌더링 (모달 한 파일로 유지) |
| `CollectionDocumentsPage` 변경 | +10 | state + import + 모달 렌더링 |

> 모달 컴포넌트가 ~250줄로 200줄 기준을 초과하지만, 상태별 분기가 명확하고
> 외부 의존이 적어 단일 파일로 유지한다. 추후 300줄 초과 시 상태별 뷰를 분리.
