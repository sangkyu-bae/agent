# source-passage-viewer Design Document

> **Summary**: 근거 칩 → 오른쪽 패널에서 문서를 열고 검색된 구절에 음영 표시. 환경변수 하나로 기능 전체를 없던 상태로 되돌릴 수 있는 탈착형 구조
>
> **Project**: sangplusbot (Agent Builder)
> **Author**: 배상규
> **Date**: 2026-11-19
> **Status**: Draft
> **Planning Doc**: [source-passage-viewer.plan.md](../../01-plan/features/source-passage-viewer.plan.md)
> **Selected Architecture**: Option C — 탈착형 실용안 (사용자 선택 2026-11-19)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 근거 칩이 파일명만 알려 주고, 원문에서 그 구절의 위치·문맥을 보여 주지 못한다 |
| **WHO** | 채팅에서 RAG 답변을 받는 사용자, 검색 품질을 점검하는 에이전트 소유자(P2) |
| **RISK** | 파서 추출 텍스트와 뷰어 렌더 텍스트가 달라 음영 매칭이 실패한다(2026-07 문서추출기 사례). 원본 파일 노출 경로에서 KB 권한 검사가 빠진다. **새 기능의 오류가 기존 채팅·업로드·삭제를 막는다** |
| **SUCCESS** | 칩 클릭 → 패널에 문서 표시 → 인용 구절 음영·이동. 원본 PDF/docx 매칭 실패 시 페이지 이동 또는 텍스트 뷰어로 내려감. 권한 없는 사용자는 403. **스위치 off = 기존과 동일(기존 테스트 무수정 통과)** |
| **SCOPE** | 백엔드: `source_viewer` 패키지(정책·저장 포트·로컬 어댑터·enricher·원본 조회 유스케이스·라우터) + 기존 코드 연결 4곳. 프론트: `sourceViewer` 컴포넌트 묶음(패널·텍스트/PDF/docx 뷰어·매칭 유틸) + 연결 3곳 |

---

## 1. Overview

### 1.1 Design Goals

1. 칩에서 원문 구절까지 한 번에 이동한다.
2. **탈착 가능**: 오류가 나면 `.env` 한 줄로 끄고, 기능을 아예 없애려면 패키지 삭제 + 연결 지점 수정으로 끝난다.
3. 새 기능의 어떤 실패도 답변·업로드·삭제를 막지 않는다.

### 1.2 Design Principles

- [[detachable-module-seam]] 준수: optional 협력자 기본값 `None` = 기능 없음. 조립 실패도 `None`. 부가 기능 실패는 입력을 그대로 돌려준다.
- 연결 지점은 AST 경계 테스트에 **전수 열거**한다("아무도 못 물게"가 아니라 "무는 곳을 전부 적는다").
- 스키마 변경 없음. 원본 존재 여부는 저장소가 `document_id`로 판정한다.
- 음영 위치는 문자열 완전일치를 쓰지 않는다(2026-07 교훈). 정규화 매칭 → 페이지 이동 → 텍스트 뷰어 순으로 내려간다.

### 1.3 Plan 대비 변경

| Plan 항목 | Design 결정 | 이유 |
|----------|------------|------|
| `document_metadata`에 원본 컬럼 추가(마이그레이션) | **추가하지 않음**. 저장 키 = `document_id`, 존재 여부는 `exists()` | 기능 제거 시 스키마 흔적 0, 롤백 마이그레이션 불필요 |
| `RunSourcePolicy`에 passages 추가 | 정책은 그대로 두고 **별도 enricher**가 `viewer` 키를 덧붙임 | 코어 정책 무변경, enricher 실패 시 기존 칩 유지 |
| 칩 필드 `document_id`·`kb_id`·`has_original`·`passages` 평면 추가 | **`viewer` 객체 1개**로 묶음 | 프론트는 키 하나의 유무로만 분기 → 서버 스위치가 프론트까지 끔 |

---

## 2. Architecture

### 2.0 Architecture Comparison

| Criteria | A: Minimal | B: Clean | **C: Pragmatic (선택)** |
|----------|:-:|:-:|:-:|
| Approach | 기존 정책·업로드·삭제에 직접 추가, DB 컬럼, 기존 모달 재사용 | 칩 계약 무변경, 런 단위 조회 API, 원본 메타 테이블 | 새 패키지 + optional 협력자 4곳, `viewer` 키 1개 |
| New Files (BE/FE) | 2 / 3 | 12 / 10 | 9 / 8 |
| Modified Files | 9 | 4 | 7 (연결 지점, 각 수 줄) |
| 제거 방법 | 여러 파일 조건문 제거 + 마이그레이션 롤백 | 라우터·테이블 제거 + 프론트 run_id 배선 제거 | `.env` off / 패키지 삭제 + 연결 7곳 |
| Complexity | Low | High | Medium |
| Effort | Low | High | Medium |
| Risk | 실패가 기존 칩으로 번짐 | 프론트 run_id 배선 신규 | 낮음 |

### 2.1 Component Diagram

```
[업로드]  UnifiedUploadUseCase ──(original_sink?)──▶ OriginalStorePort ──▶ LocalDiskOriginalStore
[삭제]    DeleteDocumentUseCase ──(original_sink?)──▶        〃                 {DIR}/{id[:2]}/{id}
[답변]    RunSourcesService ──(viewer_enricher?)──▶ SourceViewerEnricher
                                                     ├─ PassagePolicy (순수: retrieval → passages)
                                                     └─ OriginalStorePort.exists()
          → 칩 payload["viewer"] = {...}           (키 없음 = 기능 없음)

[조회]    GET /api/v1/source-viewer/kb/{kb_id}/documents/{document_id}/original
          source_viewer_router ─▶ GetOriginalUseCase ─▶ KbDocumentGuard(기존) + OriginalStorePort.open()
          전문 텍스트: 기존 GET /api/v1/knowledge-bases/{kb_id}/documents/{document_id}/chunks?include_parent=true

[프론트]  SourceCitation(문서 칩) ──viewer 있을 때만 "원문 보기"──▶ sourceViewerStore.open(viewer, label)
          ChatPage ── lazy(SourceViewerPanel) + ErrorBoundary
                      ├─ TextPassageViewer  (청크 이어 붙이기, chunk_id 매칭)
                      ├─ PdfPassageViewer   (pdfjs-dist 지연 로드, 정규화 매칭)
                      └─ DocxPassageViewer  (docx-preview 기존, 정규화 매칭)
```

### 2.2 Data Flow

**업로드**
1. 기존 흐름대로 파싱 → 청킹 → Qdrant/ES 저장 → `document_metadata` 저장.
2. **인덱싱이 성공한 뒤에만** `original_sink.save(document_id, filename, bytes)`를 호출한다. 인덱싱에 실패하면 원본을 저장하지 않으므로 고아 파일이 생기지 않는다.
3. 저장 실패는 warning만 남기고 업로드 응답은 기존과 같다.

**답변/재진입**
1. `RunSourcesService.build_for_runs`가 기존대로 칩 목록을 만든다.
2. enricher가 있으면 런마다 `enrich(items, evidence)`를 호출한다. 예외가 나면 enrich 전 목록을 그대로 쓴다.
3. enricher는 `kind=document`이고 `kb_id`를 아는 칩에만 `viewer`를 붙인다.

**칩 클릭**
1. 패널이 열리면 청크 API를 먼저 호출한다. 전문 텍스트와 구절의 **전체 내용**을 얻는다(칩의 `content_preview`는 잘려 있다).
2. `viewer.original`이 `pdf`/`docx`면 원본 API로 blob을 받아 원본 뷰어에서 매칭한다. 실패하면 단계적으로 내려간다(§5.4).
3. 원본이 없으면 텍스트 뷰어를 쓴다.

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|-----------|---------|
| `SourceViewerEnricher` | `OriginalStorePort`, `PassagePolicy` | viewer 키 생성 |
| `GetOriginalUseCase` | `KbDocumentGuard`(기존), `OriginalStorePort` | 권한 검사 후 원본 스트림 |
| `LocalDiskOriginalStore` | 파일시스템, `settings.document_original_storage_dir` | 원본 보관 |
| `PdfPassageViewer` | `pdfjs-dist`(신규, 지연 로드) | PDF 렌더 + 텍스트 레이어 |
| `DocxPassageViewer` | `docx-preview`(기존) | docx 렌더 |
| 모든 뷰어 | `utils/passageMatch.ts`(순수) | 정규화 매칭 |

---

## 3. Data Model

### 3.1 백엔드 도메인 (`src/domain/source_viewer/`)

```python
class OriginalKind(StrEnum):      # wire 값
    PDF = "pdf"
    DOCX = "docx"

@dataclass(frozen=True)
class Passage:
    chunk_id: str               # metadata_json["chunk_id"] 우선, 없으면 RetrievalSource.chunk_id
    parent_id: str | None       # metadata_json["parent_id"]
    page: int | None            # metadata_json["page"] (int 변환 실패 시 None)
    rank: int                   # 런 안 검색 순서
    excerpt: str                # content_preview (매칭 실패 시 표시용)

@dataclass(frozen=True)
class ViewerRef:
    document_id: str
    kb_id: str
    original: OriginalKind | None   # None = 원본 없음 또는 미지원 형식 → 텍스트 뷰어
    passages: tuple[Passage, ...]

class PassagePolicy:              # 순수 함수, 외부 의존 없음
    MAX_PASSAGES = 20
    @staticmethod
    def collect(document_id: str, retrievals: list[RetrievalSource]) -> tuple[Passage, ...]: ...
        # document_id 일치 · 웹 컬렉션 제외 · chunk_id 기준 중복 제거 · (created_at, rank_index) 정렬 · 상한
    @staticmethod
    def kb_id_of(retrievals) -> str | None: ...       # metadata_json["kb_id"] 첫 값
    @staticmethod
    def original_kind(filename: str) -> OriginalKind | None: ...   # 확장자 .pdf/.docx 만

class OriginalStorePort(Protocol):
    async def save(self, document_id: str, data: bytes) -> None: ...
    async def exists(self, document_id: str) -> bool: ...
    async def open(self, document_id: str) -> bytes | None: ...
    async def delete(self, document_id: str) -> None: ...

def storage_key(document_id: str) -> str:   # [0-9a-f-]{36} 만 허용, 아니면 ValueError (경로 조작 차단)
```

- `routed` 검색(조항 라우팅)은 `chunk_id`가 `section_ref`라서 청크 API의 id와 맞지 않을 수 있다. 이때 프론트는 `excerpt` 텍스트 매칭으로 내려간다(§5.4).
- 파일명은 `RunSourceItem.label` 대신 `RunEvidence.filenames`와 `metadata_json["filename"]`에서 가져온다(라벨은 clause_title로 대체될 수 있음).

### 3.2 `RunSourceItem` 변경 (코어 변경 유일 지점)

```python
@dataclass(frozen=True)
class RunSourceItem:
    ...
    viewer: Optional[Mapping[str, Any]] = None   # 신규, 기본 None

    def to_payload(self) -> dict:
        ...
        if self.viewer:
            payload["viewer"] = dict(self.viewer)
        return payload
```

### 3.3 Wire 형식 (`DocumentSource.viewer`)

```json
{
  "kind": "document", "source": "여신규정.pdf", "content": "...", "chunk_id": "doc-uuid",
  "viewer": {
    "document_id": "8f1c...-uuid",
    "kb_id": "kb-uuid",
    "original": "pdf",
    "passages": [
      {"chunk_id": "c-1", "parent_id": "p-1", "page": 12, "excerpt": "..."},
      {"chunk_id": "c-7", "parent_id": "p-3", "page": 31, "excerpt": "..."}
    ]
  }
}
```

### 3.4 Database

변경 없음. 원본은 `{DOCUMENT_ORIGINAL_STORAGE_DIR}/{document_id[:2]}/{document_id}` 에 확장자 없이 저장한다. 형식은 파일명 확장자로 판정한다(`document_metadata.filename`).

---

## 4. API Specification

### 4.1 Endpoint List

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| GET | `/api/v1/source-viewer/kb/{kb_id}/documents/{document_id}/original` | 원본 파일(inline) | Required |
| GET | `/api/v1/knowledge-bases/{kb_id}/documents/{document_id}/chunks?include_parent=true` | **기존** — 전문·구절 텍스트 | Required |

라우터는 `SOURCE_VIEWER_ENABLED=true`이고 조립에 성공했을 때만 `include_router` 한다. 끄면 404가 된다.

### 4.2 `GET .../original`

순서: 인증(401) → `KbDocumentGuard.ensure`(KB 없음·문서 불일치 404, 읽기 권한 없음 403) → `storage_key` 검증(404) → `open()` → 없으면 404 `ORIGINAL_NOT_AVAILABLE` → 형식이 pdf/docx가 아니면 415.

응답:
- `200`, `Content-Type`은 `application/pdf` 또는 `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- `Content-Disposition: inline; filename*=UTF-8''{filename}`
- `X-Content-Type-Options: nosniff`, `Cache-Control: private, max-age=300`

에러 본문은 기존 KB 라우터 `_raise_http` 형식(`{"detail": "..."}`)을 따른다.

> 기존 청크 API prefix는 `/api/v1/knowledge-bases` 확인함(`knowledge_base_router.py:61`, `constants/api.ts:122`).

---

## 5. UI/UX Design

### 5.1 Screen Layout

```
┌──────────────── ChatPage ─────────────────┬──── SourceViewerPanel (w-[480px]) ───┐
│ 답변 ...                                   │ 여신규정.pdf      [텍스트|원본]  ✕   │
│ [문서 1 여신규정.pdf ▾] [원문 보기]         │ 구절 1 / 2   ◀ ▶   p.12              │
│                                            │ ┌──────────────────────────────────┐ │
│                                            │ │ ... ████ 음영 구절 ████ ...       │ │
│                                            │ └──────────────────────────────────┘ │
│                                            │ ⚠ 원문에서 정확한 위치를 찾지 못했습니다 │
│                                            │   (구절 내용 + [텍스트로 보기])        │
└────────────────────────────────────────────┴──────────────────────────────────────┘
모바일(< md): 패널이 전체 화면(fixed inset-0)으로 열린다.
```

### 5.2 User Flow

칩의 "원문 보기" → 패널 열림(로딩) → 청크 조회 → (원본 있음) 원본 blob 조회 → 렌더 → 구절 1로 스크롤·음영 → ◀ ▶ 이동 → ✕ 또는 Esc로 닫음.

### 5.3 Component List

| Component | Location | Responsibility |
|-----------|----------|----------------|
| `SourceViewerButton` | `src/components/sourceViewer/` | 문서 칩 옆 버튼. `viewer` 있을 때만 렌더 |
| `SourceViewerPanel` | 〃 | 레이아웃·모드 전환·구절 이동·오류 표시. ChatPage에서 `React.lazy` |
| `SourceViewerBoundary` | 〃 | ErrorBoundary — 패널 오류를 "원문을 열 수 없습니다"로 바꿔 채팅을 보호 |
| `TextPassageViewer` | 〃 | 청크 이어 붙이기 + `<mark>` |
| `PdfPassageViewer` | 〃 | `pdfjs-dist` 동적 import, 현재 페이지 ±1만 렌더, 텍스트 레이어 음영 |
| `DocxPassageViewer` | 〃 | `docx-preview`(기존 DocxPreviewView 격리 방식), DOM Range 음영 |
| `sourceViewerStore` | `src/store/sourceViewerStore.ts` | `{ open, target, mode, index }` |
| `passageMatch` | `src/utils/passageMatch.ts` | 정규화·매칭 순수 함수 |
| `sourceViewerService` | `src/services/sourceViewerService.ts` | 원본 blob, 청크 조회 |
| 타입 | `src/types/sourceViewer.ts` | `SourceViewerRef`, `Passage`, `ORIGINAL_KIND`(as const) |

### 5.4 음영 매칭 규칙 (`passageMatch`)

1. **정규화**: NFKC → 모든 공백·줄바꿈 제거 → 줄끝 하이픈 제거 → 전각/반각 통일. 원문 인덱스로 되돌릴 수 있도록 정규화 문자 → 원문 offset 배열을 함께 만든다.
2. **전체 매칭**: 정규화한 구절을 정규화한 페이지 텍스트에서 `indexOf`.
3. **앵커 매칭**: 실패하면 구절 앞 40자, 뒤 40자를 각각 찾는다. 둘 다 찾고 순서가 맞으며 길이가 구절 길이의 0.5~1.5배면 그 사이를 칠한다.
4. **페이지 이동**: 그래도 실패하면 `page`가 있을 때 그 페이지로 이동하고 "정확한 위치를 찾지 못함" 안내를 띄운다.
5. **텍스트 뷰어 전환**: 안내 문구 아래에 [텍스트로 보기] 버튼을 둔다.

- 탐색 범위: PDF는 `page` ±1 페이지(없으면 전체), docx는 문서 전체.
- 텍스트 뷰어는 정규화 없이 `chunk_id`로 바로 찾는다. `chunk_id`가 맞지 않으면(routed) `excerpt` 정규화 매칭을 쓴다.
- 텍스트 뷰어의 문서 구성: `parents`가 있으면 parent를 `chunk_index` 순으로 잇고, child 구절은 parent 안에서 위치를 찾는다. 없으면 `chunks`를 `chunk_index` 순으로 잇는다.

### 5.5 Page UI Checklist

#### SourceViewerPanel
- [ ] 헤더: 파일명, [텍스트|원본] 전환(원본 없으면 원본 버튼 비활성), 닫기 ✕
- [ ] 구절 카운터 "n / N", ◀ ▶ 버튼(끝에서 비활성), 현재 구절의 page 표시
- [ ] 본문: 음영(`bg-amber-200/70`), 현재 구절은 진한 음영 + `scrollIntoView({block:'center'})`
- [ ] 로딩 스피너, 403 "이 문서를 볼 권한이 없습니다", 404 "문서를 찾을 수 없습니다(삭제되었을 수 있음)"
- [ ] 매칭 실패 안내 + 구절 excerpt + [텍스트로 보기]
- [ ] Esc로 닫기, 다른 칩을 클릭하면 대상 교체
- [ ] 모바일 폭 전체 화면

#### SourceCitation (문서 칩)
- [ ] `viewer`가 없으면 기존과 완전히 같다(스냅샷 동일)
- [ ] `viewer`가 있으면 "원문 보기" 버튼 1개

---

## 6. Error Handling — 실패 흡수 지점

| 지점 | 실패 | 처리 | 기존 기능 영향 |
|------|------|------|---------------|
| 조립(`main.py`) | 설정 오류·경로 생성 실패 | warning 1회 + 모든 협력자 `None`, 라우터 미등록 | 없음 |
| 업로드 `original_sink.save` | 디스크 오류 | warning, 응답 그대로 | 없음(해당 문서는 텍스트 뷰어) |
| 삭제 `original_sink.delete` | 파일 없음·오류 | 없음은 무시, 오류는 warning | 없음 |
| `viewer_enricher.enrich` | 어떤 예외든 | warning + enrich 전 목록 반환 | 없음(칩에 viewer만 빠짐) |
| `exists()` 개별 실패 | | 그 문서만 `original=None` | 없음 |
| 원본 API | 401/403/404/415 | §4.2 | — |
| 프론트 패널 렌더 예외 | | `SourceViewerBoundary` 안내 | 채팅 화면 유지 |
| pdfjs/docx 로드 실패 | 청크 실패 | 텍스트 뷰어로 자동 전환 + 안내 | — |
| 청크 API 실패 | | 패널 오류 표시 | — |

**연결 지점의 예외 흡수는 두 겹으로 한다**: 협력자 내부에서 한 번 흡수하고, 호출 지점에서 `try/except`로 한 번 더 감싼다(prompt-guard 선례).

---

## 7. Security Considerations

- [ ] 원본 API는 기존 `KbDocumentGuard`(KB 읽기 권한 + 문서의 KB 소속)를 그대로 쓴다. RAG 검색도 같은 `can_read_ref` 규칙을 지나므로 칩에 나온 문서와 권한 판정이 같다
- [ ] `storage_key`는 UUID 형식만 허용한다 → `../` 경로 조작 불가. 최종 경로가 저장 루트 안인지 `resolve()`로 한 번 더 확인
- [ ] 응답에 `nosniff`, inline 형식은 pdf/docx만
- [ ] docx 렌더는 기존 shadow DOM 격리를 재사용(외부 리소스·스크립트 차단, document-file-preview에서 검증)
- [ ] pdf.js는 `isEvalSupported: false`, 스크립트 실행 비활성
- [ ] 원본 파일은 업로드 크기 상한 그대로, 디렉터리 권한 0700 권장(배포 가이드)

---

## 8. Test Plan

### 8.1 Test Scope

| Type | Target | Tool | Phase |
|------|--------|------|-------|
| Unit(BE) | `PassagePolicy`, `storage_key`, `LocalDiskOriginalStore`, enricher, `GetOriginalUseCase` | pytest | Do |
| Contract(BE) | 연결 지점 AST 경계, 스위치 off 동등성 | pytest(AST) | Do |
| API(BE) | 원본 라우트 401/403/404/415/200, 미등록 시 404 | TestClient | Do |
| Unit(FE) | `passageMatch` 정규화·앵커·실패 | Vitest | Do |
| Component(FE) | 칩 버튼 유무, 패널 상태·이동·오류·ErrorBoundary | RTL + MSW | Do |
| E2E 수동 | 실제 금융 PDF·docx 업로드 → 질문 → 음영 | 브라우저 | Check |

### 8.2 백엔드 핵심 케이스

| # | 대상 | 케이스 | 기대 |
|---|------|--------|------|
| 1 | PassagePolicy | 같은 문서 3건(중복 chunk 1) + 다른 문서 1 + 웹 1 | 2건, 순서 = (created_at, rank) |
| 2 | PassagePolicy | `page`가 "12"/12/None/"x" | 12/12/None/None |
| 3 | PassagePolicy | 상한 초과 | 20건 |
| 4 | storage_key | `../etc`, 빈 문자열, 정상 UUID | ValueError ×2, 경로 |
| 5 | LocalDisk | save→exists→open→delete→exists | True, bytes, False |
| 6 | Enricher | kb_id 없는 문서 칩 / 웹 칩 | viewer 없음 |
| 7 | Enricher | exists=True & .pdf / exists=True & .hwp / exists=False | pdf / None / None |
| 8 | Enricher | 내부 예외 | 입력 목록 그대로 |
| 9 | RunSourcesService | enricher=None | 기존 결과와 동일(기존 테스트 무수정) |
| 10 | RunSourcesService | enricher가 예외 | 기존 결과와 동일 + warning |
| 11 | UnifiedUpload | sink=None / sink 예외 / 인덱싱 실패 | 기존 동일 / 성공 응답 / save 미호출 |
| 12 | DeleteDocument | sink 예외 | 삭제 성공 |
| 13 | 원본 라우트 | 미인증·타 부서 KB·다른 KB의 문서·원본 없음·hwp·정상 | 401·403·404·404·415·200 + 헤더 |
| 14 | 조립 | enabled=False / 경로 생성 실패 | 협력자 None, 라우트 404 |
| 15 | AST 경계 | `domain/source_viewer`는 stdlib·자기 패키지·`domain.agent_run.entities`만 import | 통과 |
| 16 | AST 경계 | `source_viewer` 패키지를 import하는 파일 = 선언 목록(§11.2)과 정확히 일치 | 통과 |

### 8.3 프론트 핵심 케이스

| # | 대상 | 케이스 | 기대 |
|---|------|--------|------|
| 1 | passageMatch | 줄바꿈·공백 차이, 하이픈 줄바꿈, 전각 | 매칭 + 원문 offset 정확 |
| 2 | passageMatch | 중간 일부만 다름 | 앵커 매칭 성공 |
| 3 | passageMatch | 전혀 없음 | null |
| 4 | SourceCitation | viewer 없음 | 버튼 없음, 기존 테스트 통과 |
| 5 | SourceCitation | viewer 있음 → 클릭 | store.open 호출 |
| 6 | Panel | 원본 없음 | 텍스트 뷰어, 구절 1 음영 |
| 7 | Panel | ◀ ▶ | index 이동, 끝에서 비활성 |
| 8 | Panel | 원본 403/404 | 안내 문구 |
| 9 | Panel | 뷰어 컴포넌트 throw | Boundary 안내, ChatPage 유지 |
| 10 | Panel | pdf 로드 실패(mock) | 텍스트 뷰어 전환 + 안내 |
| 11 | 번들 | `pdfjs-dist`가 초기 chunk에 없음 | 빌드 산출물 확인 |

---

## 9. Clean Architecture

### 9.1 Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `Passage`, `ViewerRef`, `PassagePolicy`, `OriginalStorePort`, `storage_key` | Domain | `idt/src/domain/source_viewer/` |
| `SourceViewerEnricher`, `GetOriginalUseCase`, `OriginalSink`(save/delete 예외 흡수 래퍼) | Application | `idt/src/application/source_viewer/` |
| `LocalDiskOriginalStore` | Infrastructure | `idt/src/infrastructure/source_viewer/` |
| `source_viewer_router` | Interfaces | `idt/src/api/routes/source_viewer_router.py` |
| 조립 `get_source_viewer()` | Composition | `idt/src/api/main.py` |

### 9.2 탈착 경계 (AST 테스트가 강제)

- `domain/source_viewer/**` → 표준 라이브러리, 자기 패키지, `src.domain.agent_run.entities`만 import
- **기존 코드는 `source_viewer` 패키지를 import하지 않는다** — duck typing(`viewer_enricher`, `original_sink`)으로만 받는다. 예외는 `main.py` 하나뿐
- `source_viewer_router`는 `main.py`에서만 include한다

---

## 10. Coding Convention Reference

- 백엔드: `idt/CLAUDE.md`, `idt/docs/rules/`. config 키 docstring에 소비 지점 `파일:라인`을 적는다([[config-single-source-at-consumption]])
- 프론트: 컴포넌트 파일에서 런타임 상수 export 금지 → `ORIGINAL_KIND`는 `src/types/sourceViewer.ts`. 엔드포인트는 `src/constants/api.ts`
- 테스트 먼저 작성(Red → Green). 백엔드 실행은 `uv run python -m pytest`
- 주석: `# Design Ref: source-passage-viewer §N — ...`

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/src/domain/source_viewer/__init__.py
idt/src/domain/source_viewer/models.py          Passage, ViewerRef, OriginalKind
idt/src/domain/source_viewer/policy.py          PassagePolicy, storage_key
idt/src/domain/source_viewer/ports.py           OriginalStorePort
idt/src/application/source_viewer/enricher.py   SourceViewerEnricher
idt/src/application/source_viewer/original_sink.py  OriginalSink (save/delete, 예외 흡수)
idt/src/application/source_viewer/get_original.py   GetOriginalUseCase
idt/src/infrastructure/source_viewer/local_disk_store.py
idt/src/api/routes/source_viewer_router.py
idt/tests/.../source_viewer/ (단위·계약·라우트)

idt_front/src/types/sourceViewer.ts
idt_front/src/services/sourceViewerService.ts
idt_front/src/store/sourceViewerStore.ts
idt_front/src/utils/passageMatch.ts
idt_front/src/components/sourceViewer/{SourceViewerButton,SourceViewerPanel,SourceViewerBoundary,TextPassageViewer,PdfPassageViewer,DocxPassageViewer}.tsx
```

### 11.2 연결 지점 전수 목록 (제거 시 되돌릴 곳)

| # | 파일 | 변경 | 되돌리기 |
|---|------|------|---------|
| 1 | `idt/src/domain/agent_run/source_policy.py` | `RunSourceItem.viewer` 필드 + `to_payload` 2줄 | 필드·2줄 삭제 |
| 2 | `idt/src/application/agent_run/run_sources.py` | `viewer_enricher=None` 인자 + 호출부 try/except | 인자·호출 삭제 |
| 3 | `idt/src/application/unified_upload/use_case.py` | `original_sink=None` 인자 + 인덱싱 성공 후 호출 | 인자·호출 삭제 |
| 4 | `idt/src/application/doc_browse/delete_document_use_case.py` (KB 삭제·일반 삭제 공용) | `original_sink=None` 인자 + 삭제 성공 후 호출 | 인자·호출 삭제 |
| 5 | `idt/src/api/main.py` | `source_viewer_di` import 1개 + `wire_source_viewer(...)` 1줄 + 주입 4곳(`original_sink` 3: 업로드 1·삭제 2, `viewer_enricher` 1: `_make_run_sources_service`) | import·wire·주입 삭제 |
| 5a | `idt/src/api/source_viewer_di.py` (신규) | 조립 전부 — 접근자 `source_viewer_sink()`·`source_viewer_enricher()`·`wire_source_viewer()` | 파일 삭제 |
| 6 | `idt/src/config.py` | `source_viewer_enabled=False`, `document_original_storage_dir=""` | 2키 삭제 |
| 7 | `idt/src/interfaces/schemas/agent_run_response.py` | `SourceItemDto.viewer: dict | None = None` | 필드 삭제 |
| F1 | `idt_front/src/types/chat.ts` | `DocumentSource.viewer?: SourceViewerRef` | 필드 삭제 |
| F2 | `idt_front/src/components/chat/SourceCitation.tsx` | 문서 칩에 `<SourceViewerButton>` 1줄 | 1줄 삭제 |
| F3 | `idt_front/src/pages/ChatPage/index.tsx` | `lazy(SourceViewerPanel)` + Boundary 마운트 | 블록 삭제 |
| F4 | `idt_front/src/constants/api.ts` | 원본 엔드포인트 상수 | 삭제 |

`.env.example`에는 두 키를 추가한다. 이 표는 AST 계약 테스트(§8.2 #16)의 선언 목록과 같아야 한다.

### 11.3 Session Guide

#### Module Map

| Module | Scope Key | 내용 | 의존 |
|--------|-----------|------|------|
| 도메인 + 저장소 | `module-1` | `domain/source_viewer/*`, `LocalDiskOriginalStore`, 단위 테스트 #1~5·15 | — |
| 업로드·삭제 연결 | `module-2` | `OriginalSink`, 연결 #3·#4·#6, 테스트 #11·12 | module-1 |
| 칩 enrich | `module-3` | `SourceViewerEnricher`, 연결 #1·#2·#7, 테스트 #6~10 | module-1 |
| 원본 API + 조립 | `module-4` | `GetOriginalUseCase`, 라우터, 연결 #5, 테스트 #13·14·16 | module-1~3 |
| 프론트 기반 | `module-5` | 타입·서비스·스토어·`passageMatch`·버튼·패널·Boundary·텍스트 뷰어, F1~F4 | module-3·4 계약 |
| 원본 뷰어 | `module-6` | `pdfjs-dist` 도입, PDF·docx 뷰어, 번들 확인 | module-5 |
| 실측 | `module-7` | 실제 금융 PDF·docx로 매칭률 측정, 스위치 off 회귀, 화면 확인 | 전체 |

#### Recommended Session Plan

| Session | Scope | 비고 |
|---------|-------|------|
| 1 | `--scope module-1,module-2` | 백엔드 저장 경로 끝까지 |
| 2 | `--scope module-3,module-4` | 백엔드 완료, 스위치 off 전체 회귀 |
| 3 | `--scope module-5` | 텍스트 뷰어로 SC-2·3·4 충족 |
| 4 | `--scope module-6,module-7` | 원본 뷰어 + 실측(SC-1) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-19 | Initial draft — Option C, 기본 off, 마이그레이션 없음 | 배상규 |
| 0.2 | 2026-11-19 | module-1·2 구현 메모 반영(§12) | 배상규 |

---

## 12. 구현 메모 (Do 중 확정)

| # | 결정 | 근거 |
|---|------|------|
| M1 | `OriginalSink.save`는 pdf/docx만 보관하고 나머지 형식은 저장하지 않는다 | 원본 뷰어가 렌더할 수 없는 형식은 디스크만 차지. 형식 판정은 `PassagePolicy.original_kind` 한 곳 |
| M2 | 업로드 원본 저장 조건: `original_sink` 주입 + `extra_metadata.kb_id` 있음 + `status != "failed"`, 메타데이터 저장 직후 | §2.2 "인덱싱 성공 후". partial(한 저장소 성공)은 검색될 수 있어 보관한다 |
| M3 | 삭제는 `_notify_deleted` 맨 앞에서 `_delete_original` 호출 | 단건·검증·일괄 삭제가 모두 이 지점을 지난다. 저장소 삭제 실패(StoreDeleteFailedError) 시에는 도달하지 않는다 |
| M4 | 원본 쓰기는 임시 파일 → `os.replace` | 쓰다 만 파일이 원본으로 노출되지 않게 |
| M5 | 경계 테스트 #16은 module-1·2 시점에 "선언 목록의 부분집합"으로 검사, module-4에서 main.py 연결 후 "정확히 일치"로 강화 | 조립 전에는 소비자가 0개라 일치 검사가 불가능 |
| M6 | `domain/source_viewer/policy.py`는 웹 컬렉션 이름(`tavily_web`)을 복제 상수로 둔다 | domain 경계(agent_run.entities만 허용) 유지. 값이 바뀌면 `test_filters_document_dedups_and_orders`가 잡는다 |
| M7 | 조립을 `main.py`가 아니라 `src/api/source_viewer_di.py`에 둔다(`graph_rag_di` 선례). 경계 테스트: source_viewer 소비자 = {di, 라우터} 정확히 일치, di 소비자 = {main.py} | 기능 제거 시 main.py 수정이 import·wire·주입 4곳으로 줄어든다 |
| M8 | 원본 API 검사 순서를 권한 → **형식(415)** → 원본(404)으로 바꿨다(Design §4.2는 원본 → 형식) | 형식은 파일명만으로 판정되므로 디스크를 읽기 전에 거른다 |
| M9 | 원본 저장 경로가 비어 있으면(텍스트 전용) 원본 API 라우터를 등록하지 않는다 | 저장소가 없으면 항상 404 — 라우트를 둘 이유가 없다. 텍스트 뷰어는 기존 청크 API를 쓴다 |
| M10 | UUID가 아닌 옛 document_id로 원본을 요청하면 `OriginalNotAvailableError`(404) | 보관 대상이 될 수 없었던 문서 — 프론트는 텍스트 뷰어로 내려간다 |
| M11 | 재진입 API DTO는 문서 외 칩에도 `viewer: null`을 싣는다 | Pydantic 기본 직렬화. 프론트는 `viewer` truthy 여부로만 분기하므로 동작 차이 없음 |
| M12 | 스모크(2026-11-19, 인프로세스 `TestClient(app)`): off → 라우트 없음 404 / on → 부품 3종 조립, 무토큰 401, 없는 KB 404(실DB 경유) | 배선 직후 실런 1회 DoD. 업로드→질문→원본 200 전 구간은 module-7 실측으로 이월 |
| M13 | 패널은 채팅 위에 **겹쳐 띄운다**(md 이상 오른쪽 480px, 모바일 전체 화면). ChatPage 여백 조정 없음 — 사용자 결정(2026-11-19) | ChatPage 연결 지점이 마운트 1줄로 끝난다. 좁은 화면에서는 답변 일부가 가려진다 |
| M14 | ChatPage 는 `SourceViewerMount` 1줄만 둔다. Mount 가 스토어 구독·`lazy(SourceViewerPanel)`·ErrorBoundary 를 맡는다 | 패널 코드는 별도 청크(빌드 실측 4.7KB)로 처음 열 때만 로드. 패널 오류 시 같은 외곽(`SourceViewerShell`)에 안내 + 닫기 |
| M15 | 텍스트 뷰어는 기존 `useKbDocumentChunks(kb, doc, {source:'qdrant', include_parent:true})` 를 재사용하고, 문서 구성·구절 해석·조각 분할은 `utils/buildPassageDocument.ts`(순수 함수)로 분리 | 캐시 키가 KB 화면과 같아 재조회가 줄고, 해석 규칙을 컴포넌트 없이 테스트한다 |
| M16 | `SourceViewerButton` 은 `viewer` truthy 일 때만 렌더 — 재진입 API 의 `viewer: null`(M11)도 버튼 없음 | 서버 스위치 off 면 프론트 변경 없이 기존 화면과 같다 |
