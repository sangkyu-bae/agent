# excel-preview Design Document

> **Summary**: 에이전트 산출 .xlsx를 서버(openpyxl read_only)가 시트별 상위 100×50 문자열 JSON으로 파싱해 주는 프리뷰 API와, 채팅 링크 옆 버튼으로 여는 시트 탭 모달의 상세 설계. 설계안 C(실용 균형) 채택.
>
> **Project**: sangplusbot (idt 백엔드 + idt_front 프론트)
> **Version**: 0.1
> **Author**: 배상규
> **Date**: 2026-10-12
> **Status**: Draft
> **Planning Doc**: [excel-preview.plan.md](../../01-plan/features/excel-preview.plan.md)

---

## Context Anchor

> Plan 문서에서 복사. Design→Do 인계 시 전략 맥락 유지용.

| Key | Value |
|-----|-------|
| **WHY** | 산출 엑셀의 내용 확인이 "다운로드 → 엑셀 실행"을 강제해 검증 왕복이 느리다 |
| **WHO** | 채팅에서 엑셀 산출물을 받는 모든 사용자 (주인공 P2 에이전트 소유자 및 배포받은 부서 사용자) |
| **RISK** | 대용량 시트 파싱이 요청 스레드를 점유하거나 응답이 비대해져 채팅 UI가 멈추는 것 → 서버 측 행/열 상한 + `asyncio.to_thread` + read_only 모드 |
| **SUCCESS** | .xlsx 링크 옆 버튼 → 모달에서 모든 시트 탭·헤더·상위 100행 확인 → 모달 내 다운로드가 기존과 동일 파일을 저장. 10MB 파일 프리뷰 응답 2초 이내. 신규 테스트 RED→GREEN, 기존 `FAILED` 목록 diff 0 |
| **SCOPE** | Phase 1(이번 사이클): 산출 엑셀 프리뷰 API + 모달. Out: 첨부 엑셀·KB 업로드·분석 스냅샷 프리뷰, 서식 렌더, 페이지네이션 |

---

## 1. Overview

### 1.1 Design Goals

- 기존 다운로드 계약(`GET /files/{file_id}`)·링크 형식·에이전트 노드를 **무수정**으로 두고 additive 라우트 1개만 추가한다.
- 셀 직렬화·상한 규칙을 domain Policy로 고정해 후속 접점(첨부·KB·스냅샷)이 같은 응답 스키마를 재사용할 수 있게 한다.
- 모달 상태를 react-markdown의 `memo` 트리 **밖**(Zustand 스토어)에 소유시켜 Plan 리스크(리렌더·상태 유실)를 구조적으로 제거한다.
- 교체 가능한 두 경계를 명시한다: 진입 방식(`EXCEL_PREVIEW_TRIGGER` 상수 1곳), 그리드 구현(`ExcelPreviewGrid` props 인터페이스).

### 1.2 Design Principles

- Thin DDD 준수: 규칙(직렬화·상한·예외)은 domain, 흐름은 application, openpyxl은 infrastructure, HTTP 매핑은 interfaces.
- 과도한 추상화 금지: 소비자 1곳뿐인 ReaderInterface·Context Provider는 만들지 않는다(설계안 B 기각 사유). 리더는 duck-typing 주입.
- document_extractor 기존 관례 준수: pydantic 스키마는 `application/{feature}/schemas.py`, 오류는 `{code, message}` detail, DI placeholder + lifespan override.
- TDD: 각 모듈은 테스트 RED → 구현 GREEN 순. 기존 FAILED 목록 diff 0.

---

## 2. Architecture Options

### 2.0 Architecture Comparison

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| **Approach** | domain 생략, application 1모듈 집중, 모달 상태 markdown 트리 내부 useState | domain에 ReaderInterface까지 전부 분리, 트리거 Context Provider 주입 | domain은 순수 규칙만(Policy·예외), 스키마는 application, 리더 duck-typing, 모달 상태 Zustand |
| **New Files** | ~9 | ~17 | ~14 |
| **Modified Files** | 4 | 5 | 5 |
| **Complexity** | Low | High | Medium |
| **Maintainability** | Medium | High | High |
| **Effort** | Low | High | Medium |
| **Risk** | memo 트리 내부 모달 상태 유실, 레이어 규칙 위반 소지 | 소비자 1곳 추상화 = 금지 항목(두꺼운 DDD) 경계 | Low (balanced) |
| **Recommendation** | Quick wins | Long-term | **Default choice** |

**Selected**: **Option C** — **Rationale**: Plan §7.3 구조를 그대로 따르면서 모달 상태를 Zustand로 markdown 트리 밖에 소유시켜 Plan 리스크를 제거하고, document_extractor 관례(스키마 위치·오류 계약·DI 패턴)와 일치한다. (Checkpoint 3 사용자 확정)

### 2.1 Component Diagram

```
[프론트 idt_front]                          [백엔드 idt]
MarkdownRenderer (.xlsx 링크 감지)
  ├─ 링크 클릭 ──────────────────────────▶ GET /files/{id}            (기존, 무수정)
  └─ "미리보기" 버튼 → excelPreviewStore.open(fileId, filename)
                              │
ChatPage ─ mount ─ ExcelPreviewModal (store 구독)
  ├─ useExcelPreview(fileId | null) ──────▶ GET /files/{id}/preview   (신규)
  │    (enabled: !!fileId, gcTime 0 — TTL 파일이라 캐시 미보관)
  │                                           │ document_extractor_router
  │                                           ▼
  │                                        PreviewExcelUseCase (application)
  │                                           │ store.load → owner → 확장자
  │                                           ▼ asyncio.to_thread
  │                                        ExcelPreviewReader (infrastructure, openpyxl)
  │                                           │ 셀 직렬화·상한 = domain Policy
  ├─ ExcelPreviewGrid (columns/rows만 받는 교체 경계)
  └─ 다운로드 버튼 ─────────────────────▶ documentExtractorService.downloadGeneratedFile (재사용)
```

### 2.2 Data Flow

```
버튼 클릭 → excelPreviewStore.open({fileId, filename})
→ ExcelPreviewModal 열림 → useExcelPreview(enabled=true) → GET /preview
→ UseCase: AgentAttachmentStore.load → owner 검증 → .xlsx 검사
→ to_thread(reader.read(file_path, max_rows, max_cols))
→ reader: openpyxl load_workbook(read_only=True, data_only=True)
   시트별: ws.max_row/max_column 메타 → 상한만큼 행 스트리밍 → Policy.serialize_cell
→ ExcelPreviewResponse JSON → 모달: 시트 탭 + ExcelPreviewGrid + truncated 안내
```

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `document_extractor_router` (+preview) | `PreviewExcelUseCase`, `get_current_user` | HTTP 매핑·오류 변환 |
| `PreviewExcelUseCase` | `AgentAttachmentStore`(기존), reader(주입), domain 예외 | 흐름 제어 |
| `ExcelPreviewReader` | openpyxl, `domain/excel_preview/policies` | 파싱 + 직렬화 규칙 적용 |
| `ExcelPreviewModal` | `excelPreviewStore`, `useExcelPreview`, `ExcelPreviewGrid`, `Modal`(common), `documentExtractorService` | 표시·다운로드 |
| `MarkdownRenderer` | `excelPreviewStore.open`, `EXCEL_PREVIEW_TRIGGER` | 진입점 |

---

## 3. Data Model

### 3.1 백엔드 스키마 (pydantic — `src/application/excel_preview/schemas.py`)

```python
class ExcelPreviewSheet(BaseModel):
    name: str            # 시트 이름
    columns: list[str]   # 첫 행(헤더). 빈 셀은 "". 행 0개면 []
    rows: list[list[str]]  # 2행째부터 상한까지. 모든 셀 문자열
    total_rows: int      # 전체 행 수 (§3.4 산출 규칙)
    total_cols: int      # 전체 열 수
    truncated: bool      # 행 또는 열이 상한에 걸려 잘렸는가

class ExcelPreviewResponse(BaseModel):
    file_id: str
    filename: str
    max_rows: int        # 적용된 행 상한 (config)
    max_cols: int        # 적용된 열 상한 (config)
    sheets: list[ExcelPreviewSheet]  # 통합문서 순서, 모든 시트(빈 시트 포함)
```

### 3.2 프론트 타입 (`idt_front/src/types/excelPreview.ts` — 필드명 snake_case 그대로, FR-14)

```typescript
export interface ExcelPreviewSheet {
  name: string;
  columns: string[];
  rows: string[][];
  total_rows: number;
  total_cols: number;
  truncated: boolean;
}

export interface ExcelPreviewResponse {
  file_id: string;
  filename: string;
  max_rows: number;
  max_cols: number;
  sheets: ExcelPreviewSheet[];
}

/** 진입 방식 스위치 (FR-09). 'link'로 바꾸면 링크 클릭=프리뷰, 다운로드는 모달 안에서만 */
export const EXCEL_PREVIEW_TRIGGER: ExcelPreviewTrigger = 'button';
export type ExcelPreviewTrigger = 'button' | 'link';
```

> 런타임 상수는 컴포넌트 파일이 아닌 `src/types/excelPreview.ts`에 둔다(프로젝트 규칙).

### 3.3 셀 직렬화 규칙 (domain Policy — `src/domain/excel_preview/policies.py`, FR-05 확정)

| 입력 타입 | 출력 문자열 | 예 |
|-----------|------------|----|
| `None` | `""` | 빈 셀 |
| `str` | 그대로 | `"서울"` |
| `bool` | `"true"` / `"false"` | (int보다 먼저 검사 — Python bool은 int 하위 타입) |
| `int` | `str(v)` | `42` → `"42"` |
| `float` 정수값 | 정수 표기 | `1.0` → `"1"` (`v.is_integer()` 검사) |
| `float` 그 외 | `str(v)` | `3.14` → `"3.14"` (NaN/inf → `""`) |
| `datetime.datetime` | ISO 8601 | `"2026-10-12T09:00:00"` |
| `datetime.date` | ISO 날짜 | `"2026-10-12"` |
| `datetime.time` | ISO 시각 | `"09:00:00"` |
| 그 외 | `str(v)` | 방어적 폴백 |

수식 셀은 `data_only=True`로 계산 결과값이 들어오므로 위 규칙에 그대로 수렴한다(캐시 없는 수식은 None → `""`).

### 3.4 total_rows / total_cols 산출 규칙 (Plan 미결 사항 확정)

- 기본: openpyxl read_only의 **`ws.max_row` / `ws.max_column`** (XML 메타 기반, 전 행 순회 없음 — Plan 리스크 1 완화). 단, dimensions 없는 파일은 이 값이 **읽은 만큼 갱신되는 lazy 값**이므로 반드시 iter 전에 캡처하고, 상한 중단 시 메타가 읽은 수보다 작으면 신뢰하지 않는다 (구현: `_resolve_total_rows`). truncated 판정에는 상한 도달 플래그(`hit_limit`)를 OR로 보강한다.
- 메타가 `None`인 비정형 파일: 스트리밍으로 실제 읽은 행 수를 사용한다. 상한에 도달해 중단했다면 `total_rows = 읽은 행 수`, `truncated = true` — "전체 N행" 문구가 하한값이 될 수 있음을 허용한다(Plan에서 "약 N행" 허용 확정). 산출 노드가 만드는 파일은 항상 메타가 있으므로 실사용 영향 없음.
- `truncated = (total_rows − 1 > len(rows)) or (total_cols > max_cols)` — 헤더 1행 제외 기준. 빈 시트(행 0)는 `columns=[], rows=[], total_rows=0, truncated=false`.

### 3.5 Database Schema

해당 없음 — DB 미사용 (AgentAttachmentStore 파일 저장소만 읽음).

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/document-extractor/files/{file_id}/preview` | .xlsx 산출 파일 프리뷰 JSON (신규) | Required (JWT) |
| GET | `/api/v1/document-extractor/files/{file_id}` | 파일 다운로드 (기존, 무수정) | Required (JWT) |

### 4.2 Detailed Specification

#### `GET /api/v1/document-extractor/files/{file_id}/preview`

**Request**: path 파라미터 `file_id` (uuid4 hex 32자 — 형식 검증은 store.load가 수행, 불일치 시 404로 수렴)

**Response (200 OK)**:
```json
{
  "file_id": "3f2a…",
  "filename": "매출현황.xlsx",
  "max_rows": 100,
  "max_cols": 50,
  "sheets": [
    {
      "name": "Sheet1",
      "columns": ["지점", "매출", "날짜"],
      "rows": [["서울", "1200", "2026-10-01"], ["부산", "900", "2026-10-02"]],
      "total_rows": 20001,
      "total_cols": 3,
      "truncated": true
    }
  ]
}
```

**Error Responses** (기존 `_http_error` 형식 `{"detail": {"code", "message"}}`):

| Status | code | 조건 | message |
|--------|------|------|---------|
| 401 | (FastAPI 기본) | 미인증 | — |
| 403 | `FORBIDDEN` | `stored.owner_user_id != current_user.id` | "본인이 생성한 파일만 미리볼 수 있습니다." |
| 404 | `FILE_NOT_FOUND` | store.load None (만료·없음·형식 불일치) | "파일을 찾을 수 없거나 만료되었습니다." |
| 415 | `PREVIEW_UNSUPPORTED` | 확장자 `.xlsx` 외 | "미리보기는 .xlsx 파일만 지원합니다." |
| 422 | `PREVIEW_PARSE_FAILED` | openpyxl 파싱 예외 (손상 파일) | "파일을 해석할 수 없습니다." (원인 스택은 로그에만) |

**검증 순서**: load(404) → owner(403) → 확장자(415) → 파싱(422). 다운로드 라우트와 동일한 순서·검증을 공유한다.

### 4.3 백엔드 구성 요소

| 파일 | 내용 |
|------|------|
| `src/domain/excel_preview/policies.py` | `serialize_cell(value) -> str` (§3.3 테이블), 순수 함수 — 외부 의존 없음 |
| `src/domain/excel_preview/exceptions.py` | `PreviewFileNotFoundError`, `PreviewForbiddenError`, `PreviewUnsupportedError`, `PreviewParseFailedError` |
| `src/application/excel_preview/schemas.py` | §3.1 pydantic 모델 |
| `src/application/excel_preview/preview_use_case.py` | `PreviewExcelUseCase(store, reader, max_rows, max_cols, logger)` — `async execute(file_id, owner_user_id, request_id) -> ExcelPreviewResponse`. load→owner→확장자 검사 후 `asyncio.to_thread(reader.read, …)`. 시작/완료 로그(file_id, sheet_count, elapsed_ms), 비즈니스 거절은 WARNING, 실패는 `exception=` 스택 (LOG-001) |
| `src/infrastructure/excel/preview_reader.py` | `ExcelPreviewReader.read(file_path, max_rows, max_cols) -> list[ExcelSheetData]` — openpyxl `load_workbook(read_only=True, data_only=True)`, 시트별 §3.4 규칙, 셀은 domain Policy 호출. 파싱 예외는 `PreviewParseFailedError`로 래핑(원인 체이닝). `finally: wb.close()` |
| `src/config.py` | `excel_preview_max_rows: int = 100`, `excel_preview_max_cols: int = 50` (+소비 지점 주석) |
| `src/api/routes/document_extractor_router.py` | `get_excel_preview_use_case()` placeholder + `/files/{file_id}/preview` 라우트, 예외→HTTP 매핑 |
| `src/api/main.py` | lifespan에서 UseCase 생성(기존 `get_document_attachment_store`와 동일 store 주입) + `dependency_overrides` 1건 |

> reader 주입은 duck-typing(생성자 파라미터). ReaderInterface 추상 클래스는 만들지 않는다 — 소비자가 1곳뿐이며 테스트는 fake 객체로 충분(과도한 추상화 금지).

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌─ ExcelPreviewModal (common Modal, size='4xl', scroll='body') ──────┐
│  매출현황.xlsx                                            [X]      │
│  ─────────────────────────────────────────────────────────────    │
│  [Sheet1] [Sheet2] [요약]        ← 시트 탭 (활성 탭 강조)          │
│  ⚠ 전체 20,001행 × 3열 중 100행 × 3열 표시   ← truncated일 때만    │
│  ┌──────────────────────────────────────────────┐                 │
│  │ 지점   │ 매출   │ 날짜        ← columns(thead) │ (세로 스크롤)   │
│  │ 서울   │ 1200   │ 2026-10-01                  │ (가로 스크롤)   │
│  │ …                                             │                 │
│  └──────────────────────────────────────────────┘                 │
│                                   [다운로드]  [닫기]   ← footer    │
└────────────────────────────────────────────────────────────────────┘
```

### 5.2 User Flow

```
채팅에 "다운로드: [파일.xlsx](…)" 수신
→ (button 모드) 링크 옆 "미리보기" 버튼 클릭  /  (link 모드) 링크 자체 클릭
→ 모달 열림 + 로딩 스피너 → 시트 탭·그리드 표시
→ 탭 전환(즉시, 추가 요청 없음) → [다운로드] → blob 저장 → 닫기
오류 시: 모달 내 사유 문구 + (415/422는) 다운로드 버튼 유지
```

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `ExcelPreviewModal` | `src/components/chat/` | store 구독, 조회(훅), 탭·상태 분기·다운로드. common `Modal` 사용 |
| `ExcelPreviewGrid` | `src/components/chat/` | `{columns, rows}` props만 받는 순수 `<table>` 렌더 — **교체 경계** |
| `MarkdownRenderer` (수정) | `src/components/chat/` | `.xlsx` 링크 감지 + 트리거 분기 + 버튼 렌더 |
| `excelPreviewStore` | `src/store/excelPreviewStore.ts` | `target: {fileId, filename} \| null`, `open(target)`, `close()` — Zustand |
| `useExcelPreview` | `src/hooks/useExcelPreview.ts` | TanStack Query, `enabled: !!fileId`, `staleTime: 0`, 재시도 1회·4xx 미재시도 |
| `excelPreviewService` | `src/services/excelPreviewService.ts` | `getPreview(fileId)` — authApiClient |

**설계 결정 확정 (Plan 미결)**:
- **모달 상태 소유**: `excelPreviewStore`(Zustand, `src/store/`). `MarkdownRenderer`의 `a` 컴포넌트는 `open()` 호출만 하고 상태를 갖지 않아 `memo` 재파싱 차단과 무관해진다. 모달은 `ChatPage/index.tsx`에 1회 마운트.
- **.xlsx 판별**: 링크 텍스트(`extractText(children)`)가 `.xlsx`로 끝나는지(case-insensitive). 응답 메타 폴백은 도입하지 않는다 — 노드 링크 형식 테스트가 이미 형식을 고정하고 있고, 형식 변경 시 그 테스트가 먼저 깨진다.
- **트리거 상수 주입**: `types/excelPreview.ts`에서 직접 import. 테스트는 `vi.mock('@/types/excelPreview')`로 두 모드를 각각 고정(Plan 리스크 4 대응). Context Provider는 도입하지 않는다.
- **link 모드 다운로드 재진입 방지**: `EXCEL_PREVIEW_TRIGGER === 'link'`일 때 .xlsx 링크 클릭은 `open()`만 호출하고, 다운로드는 모달 footer 버튼으로만 수행.

### 5.4 Page UI Checklist

#### 채팅 메시지 (MarkdownRenderer, button 모드 기본)

- [ ] 링크: `.xlsx` 산출 링크는 기존대로 📄 + 밑줄, 클릭 시 blob 다운로드 (불변)
- [ ] 버튼: `.xlsx` 링크 바로 뒤 "미리보기" 인라인 버튼 (`type="button"`, `aria-label="{파일명} 미리보기"`)
- [ ] 버튼 비노출: `.pdf`/`.docx` 등 다른 확장자 산출 링크, 일반 외부 링크 (렌더 결과 불변 단언)
- [ ] link 모드(테스트로만 검증): 링크 클릭=`open()` 호출, 다운로드 서비스 미호출

#### ExcelPreviewModal

- [ ] 헤더: 파일명 타이틀 + X 닫기 (common Modal — `role="dialog"`, ESC 닫기 제공)
- [ ] 시트 탭: 응답 순서대로 전체 시트, 활성 탭 강조, 클릭 전환 (시트 1개여도 표시)
- [ ] truncated 안내: `truncated=true`인 활성 시트에만 "전체 {total_rows}행 × {total_cols}열 중 상위 {rows.length}행 × {columns.length}열 표시"
- [ ] 그리드: `<table>` 시맨틱 — `<thead>`=columns, `<tbody>`=rows, 모달 내부 가로+세로 스크롤
- [ ] 로딩: 스피너 (조회 중)
- [ ] 오류 404: "파일이 만료되었거나 찾을 수 없습니다." (다운로드 버튼 숨김 — 파일 자체가 없음)
- [ ] 오류 403: "본인이 생성한 파일만 볼 수 있습니다." (다운로드 버튼 숨김)
- [ ] 오류 415/422: "미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다." + 다운로드 버튼 유지
- [ ] 빈 시트: "데이터 없음" 플레이스홀더
- [ ] footer: [다운로드] LoadingButton 패턴, `downloadGeneratedFile(fileId, filename)` 재사용 + [닫기]
- [ ] XSS: 셀 값은 React 텍스트 노드로만 렌더 (`dangerouslySetInnerHTML` 금지)

---

## 6. Error Handling

### 6.1 Error Code Definition

§4.2 표 참조. 프론트 매핑:

| HTTP | 모달 표시 | 다운로드 버튼 |
|------|-----------|:---:|
| 401 | authApiClient 공통 처리(기존 ApiError 경로) | — |
| 403 | "본인이 생성한 파일만 볼 수 있습니다." | 숨김 |
| 404 | "파일이 만료되었거나 찾을 수 없습니다." | 숨김 |
| 415/422 | "미리보기를 만들 수 없습니다. 파일은 다운로드할 수 있습니다." | 유지 |
| 네트워크/5xx | "미리보기를 불러오지 못했습니다. 다시 시도해주세요." | 유지 |

- 오류 판별은 `ApiError.status` 사용 (`err.response` 아님 — authApiClient 인터셉터 규칙).
- 백엔드 파싱 실패는 `logger.error(..., exception=...)`으로 스택 포함 기록 후 422로 수렴 — 프로세스·타 요청에 전파 금지.

### 6.2 Error Response Format

기존 document_extractor 계약 유지: `{"detail": {"code": "...", "message": "..."}}`

---

## 7. Security Considerations

- [x] 인증: 기존 `get_current_user` 의존성 재사용 (401)
- [x] 권한: 다운로드와 동일한 owner-only 검증 (403) — 검증 주체는 UseCase
- [x] 경로 주입: file_id 형식 검증·경로 구성은 store가 전담 (기존 보장 재사용, 신규 경로 조작 없음)
- [x] XSS: 셀 값 텍스트 렌더만, `<script>` 문자열 셀 테스트로 고정
- [x] DoS: 행/열 상한 + read_only 스트리밍 + to_thread (이벤트 루프 비차단), 응답 본문 상한 1MB 목표
- [ ] Rate Limiting: 범위 외 (기존 라우터 전역 정책 따름)

---

## 8. Test Plan

> 테스트 코드는 Do 단계에서 구현과 1세트로 작성(RED→GREEN). 프로젝트 표준: 백엔드 pytest(TestClient 인프로세스), 프론트 Vitest+RTL+MSW. Playwright 미사용 — L3는 수동 E2E로 대체(Plan DoD).

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| L1: API | 프리뷰 라우트 상태코드·응답 형태 | pytest + TestClient | Do |
| L1: Unit | 직렬화 Policy·리더·유스케이스 | pytest (실 .xlsx 픽스처는 openpyxl로 생성) | Do |
| L2: UI | 버튼 노출·모달 상태·탭·그리드·다운로드 호출 | Vitest + RTL + MSW | Do |
| L3: E2E | 생성→미리보기→다운로드 여정 | 수동 (체크리스트) | Check |

### 8.2 L1: 백엔드 테스트 시나리오

| # | 대상 | 시나리오 | 기대 |
|---|------|----------|------|
| 1 | Policy | §3.3 테이블 전체 케이스 (parametrize) | 표의 출력 문자열과 일치. bool이 int보다 먼저 분기 |
| 2 | Reader | 다중 시트(3개)·날짜·수식캐시·빈 셀 픽스처 | 시트 순서 유지, 값 직렬화 일치 |
| 3 | Reader | 2만 행 × 60열 픽스처 | rows 100개·columns 50개, total 20001(헤더 포함)/60, truncated=true, 응답 시간 단언 |
| 4 | Reader | 빈 시트 포함 파일 | `columns=[], rows=[], total_rows=0, truncated=false` |
| 5 | Reader | 손상 파일(비zip 바이트) | `PreviewParseFailedError` (원인 체이닝) |
| 6 | UseCase | 정상 흐름 | store.load→owner→reader 호출 순서, to_thread 사용 |
| 7 | UseCase | 없음/만료·타인·.docx | FileNotFound/Forbidden/Unsupported 예외 각각 |
| 8 | Router | 정상 .xlsx | 200, 응답 스키마 전 필드 |
| 9 | Router | 미인증 | 401 |
| 10 | Router | 타인 파일 / 없는 file_id / .docx / 손상 | 403 FORBIDDEN / 404 FILE_NOT_FOUND / 415 PREVIEW_UNSUPPORTED / 422 PREVIEW_PARSE_FAILED |
| 11 | Router | 기존 다운로드 라우트 테스트 전체 | 무수정 통과 (FAILED diff 0) |
| 12 | Config | 상한 키 기본값·env 반영 | 100/50, override 반영 |

### 8.3 L2: 프론트 테스트 시나리오

| # | 대상 | 시나리오 | 기대 |
|---|------|----------|------|
| 1 | MarkdownRenderer | .xlsx 산출 링크 | 링크 + "미리보기" 버튼, 버튼 클릭 시 `open({fileId, filename})` |
| 2 | MarkdownRenderer | .pdf/.docx 산출 링크, 외부 링크 | 버튼 없음, 기존 렌더 불변 |
| 3 | MarkdownRenderer | 링크 클릭 (button 모드) | `downloadGeneratedFile` 호출 (기존 동작 불변) |
| 4 | MarkdownRenderer | link 모드 (vi.mock) | 링크 클릭=`open()`, 다운로드 미호출 |
| 5 | Modal | 열림 | MSW 핸들러로 조회, 로딩→탭·그리드 렌더. `enabled`로 닫힘 상태 미조회 |
| 6 | Modal | 탭 전환 | 활성 시트 교체, 추가 네트워크 요청 없음 |
| 7 | Modal | truncated 시트 | 안내 문구 표시, 비truncated 시트는 미표시 |
| 8 | Modal | 404/403/415/422/네트워크 | §6.1 문구·다운로드 버튼 유무 각각 |
| 9 | Modal | 빈 시트 | "데이터 없음" |
| 10 | Modal | 다운로드 버튼 | `downloadGeneratedFile(fileId, filename)` 호출, LoadingButton 동작 |
| 11 | Grid | `<script>alert(1)</script>` 셀 | 텍스트로 표시 (innerHTML 미해석) |
| 12 | Grid | columns/rows 렌더 | thead/tbody 구조, 행·열 수 일치 |
| 13 | store | open/close | target 설정·해제 |
| 14 | hook | MSW 정상/오류 | 데이터·ApiError 상태 |

### 8.4 L3: 수동 E2E 체크리스트 (Check 단계)

| # | 시나리오 | 성공 기준 |
|---|----------|----------|
| 1 | 엑셀 생성 에이전트로 .xlsx 산출 → 미리보기 → 전 시트 탭 확인 | 헤더·데이터가 실제 파일과 일치 |
| 2 | 모달에서 다운로드 vs 링크 다운로드 | 두 파일 바이트 동일 |
| 3 | TTL 만료(1h) 후 미리보기 | 404 문구 표시, UI 미깨짐 |
| 4 | 10MB·5시트·2만 행 파일 | 응답 2초 이내, 채팅 UI 비차단 |

### 8.5 Seed Data Requirements

DB seed 불필요. 테스트 픽스처는 openpyxl로 **테스트 내 생성**(커밋 바이너리 금지):

| 픽스처 | 내용 |
|--------|------|
| multi_sheet.xlsx | 시트 3개(일반/빈/날짜·숫자 혼합) |
| large.xlsx | 20,000행 × 60열 (세션 스코프 fixture로 1회 생성) |
| corrupt.xlsx | 비zip 바이트 |
| MSW 핸들러 | 정상 2시트(1개 truncated)·빈 시트·오류 4종 |

---

## 9. Clean Architecture

### 9.1 Layer Structure (이 기능)

| Layer | Responsibility | Location |
|-------|---------------|----------|
| **interfaces** | `/preview` 라우트, 예외→HTTP 매핑 | `src/api/routes/document_extractor_router.py` |
| **application** | `PreviewExcelUseCase`, pydantic 스키마 | `src/application/excel_preview/` |
| **domain** | 직렬화 Policy(순수 함수), 예외 4종 | `src/domain/excel_preview/` |
| **infrastructure** | openpyxl 리더 | `src/infrastructure/excel/preview_reader.py` |

### 9.2 Dependency Rules

```
interfaces → application → domain ← infrastructure
                 └──────→ infrastructure (주입은 main.py DI에서)
domain은 openpyxl·pydantic·LangChain을 import하지 않는다 (표준 lib만)
```

### 9.3 File Import Rules

| From | Can Import | Cannot Import |
|------|-----------|---------------|
| router | application(use case·schemas), domain(exceptions) | infrastructure 직접 |
| use_case | domain, (주입된) reader 객체 | — (reader 클래스 직접 import 금지, 비즈니스 규칙 직접 구현 금지) |
| policies.py | 표준 lib(datetime, math)만 | openpyxl, pydantic, 외부 전부 |
| preview_reader.py | openpyxl, domain(policies·exceptions) | application |

### 9.4 프론트 Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `ExcelPreviewModal` / `ExcelPreviewGrid` | Presentation | `src/components/chat/` |
| `useExcelPreview` | Application | `src/hooks/useExcelPreview.ts` |
| `excelPreviewStore` | Application(상태) | `src/store/excelPreviewStore.ts` |
| `ExcelPreviewResponse` 등 타입·트리거 상수 | Domain | `src/types/excelPreview.ts` |
| `excelPreviewService` | Infrastructure | `src/services/excelPreviewService.ts` |
| `DOCUMENT_EXTRACTOR_FILE_PREVIEW` | Infrastructure | `src/constants/api.ts` |

---

## 10. Coding Convention Reference

### 10.1 적용 관례 (기존 3종 CLAUDE.md + 위키)

| Item | Convention Applied |
|------|-------------------|
| 네이밍 | 백엔드 snake_case / 프론트 컴포넌트 PascalCase.tsx, 훅 use*.ts, 스토어 *Store.ts |
| 런타임 상수 | 컴포넌트 파일 export 금지 → `types/excelPreview.ts`에 `as const` |
| API 계약 | 응답 필드 snake_case 그대로 TS에 복제 (AttachmentUploadResponse 관례, api-contract-sync 4-1) |
| 오류 처리 | 백엔드 `_http_error` 재사용, 스택 없는 에러 처리 금지. 프론트 `ApiError.status` 분기 |
| 로깅 | StructuredLogger, print 금지. 시작/완료(file_id, sheet_count, elapsed_ms)·실패 `exception=` |
| 함수 규모 | 40줄 이하, if 중첩 2단계 이하 — reader의 시트 루프는 보조 함수 분리 |
| 다운로드 | `documentExtractorService.downloadGeneratedFile` 재사용, LoadingButton 패턴 |
| 모달 | common `Modal` 사용 (자체 오버레이 구현 금지) |

### 10.2 Environment Variables

| Variable | Purpose | Default | Scope |
|----------|---------|---------|-------|
| `EXCEL_PREVIEW_MAX_ROWS` | 시트당 프리뷰 행 상한 | 100 | Server |
| `EXCEL_PREVIEW_MAX_COLS` | 시트당 프리뷰 열 상한 | 50 | Server |

프론트 환경변수 추가 없음.

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/
├── src/domain/excel_preview/{__init__,policies,exceptions}.py      (신규)
├── src/application/excel_preview/{__init__,schemas,preview_use_case}.py (신규)
├── src/infrastructure/excel/preview_reader.py                      (신규)
├── src/api/routes/document_extractor_router.py                     (수정: +preview)
├── src/api/main.py                                                 (수정: DI 1건)
├── src/config.py                                                   (수정: 키 2개)
└── tests/{domain,application,infrastructure,api}/...excel_preview* (신규)

idt_front/src/
├── types/excelPreview.ts                                           (신규)
├── constants/api.ts                                                (수정: +PREVIEW)
├── services/excelPreviewService.ts                                 (신규)
├── hooks/useExcelPreview.ts                                        (신규)
├── store/excelPreviewStore.ts                                      (신규)
├── components/chat/{ExcelPreviewModal,ExcelPreviewGrid}.tsx        (신규)
├── components/chat/MarkdownRenderer.tsx                            (수정)
├── pages/ChatPage/index.tsx                                        (수정: 모달 마운트)
└── __tests__/mocks/handlers.ts                                     (수정: MSW)
```

### 11.2 Implementation Order (TDD — 각 단계 테스트 먼저)

1. [ ] config 키 2개 + 테스트
2. [ ] domain: `serialize_cell` Policy + 예외 (테이블 테스트)
3. [ ] infrastructure: `ExcelPreviewReader` (픽스처 생성 포함)
4. [ ] application: 스키마 + `PreviewExcelUseCase` (fake store·reader)
5. [ ] interfaces: `/preview` 라우트 + DI (TestClient 200/401/403/404/415/422)
6. [ ] 프론트 기반: 타입·상수·서비스·스토어·훅 (+MSW)
7. [ ] `ExcelPreviewGrid` → `ExcelPreviewModal` (상태 분기 전체)
8. [ ] `MarkdownRenderer` 수정 (두 트리거 모드) + `ChatPage` 마운트
9. [ ] 전체 회귀: `uv run python -m pytest` FAILED diff 0, `tsc -b` + lint + Vitest

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| 백엔드 프리뷰 API | `module-1` | 구현 순서 1~5 (config→domain→infra→application→router/DI) | 40-50 |
| 프론트 데이터 계층 | `module-2` | 구현 순서 6 (타입·상수·서비스·스토어·훅·MSW) | 20-30 |
| 프론트 UI | `module-3` | 구현 순서 7~9 (Grid→Modal→MarkdownRenderer/ChatPage→회귀) | 40-50 |

#### Recommended Session Plan

| Session | Phase | Scope | Turns |
|---------|-------|-------|:-----:|
| Session 1 | Do | `--scope module-1` | 40-50 |
| Session 2 | Do | `--scope module-2,module-3` | 50-70 |
| Session 3 | Check + Report | 전체 (수동 E2E 포함) | 30-40 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-10-12 | Initial draft — 설계안 C 채택(Checkpoint 3), Plan 미결 3건 확정(모달 상태=Zustand, total_rows=max_row 메타, 트리거 주입=직접 import+vi.mock) | 배상규 |
| 0.2 | 2026-10-12 | Check G-06~08 반영: §8.2 total 20001 정정, §4.3 유스케이스 시그니처(logger·request_id), §2.1 훅 시그니처·gcTime, §3.4 메타 lazy 갱신·hit_limit 보강 기록 | 배상규 |
