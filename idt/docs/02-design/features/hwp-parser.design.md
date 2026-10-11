# hwp-parser 설계 문서

> **요약**: HWP 5.0(OLE 바이너리)과 HWPX(ZIP+XML)를 순수 Python으로 읽어 `PDFParserInterface` 구현체로 KB 업로드·doc_chunk에 연결한다
>
> **프로젝트**: sangplusbot (idt / idt_front)
> **작성자**: 배상규
> **작성일**: 2026-10-08
> **상태**: Draft
> **계획 문서**: [hwp-parser.plan.md](../../01-plan/features/hwp-parser.plan.md)
> **선택 설계안**: C안 — Pragmatic(실용 균형)

---

## Context Anchor

| 키 | 내용 |
|----|------|
| **WHY** | 한글 문서를 PDF로 바꾸지 않고 바로 KB에 넣기 위해 |
| **WHO** | P2 KB 운영자·에이전트 소유자 (KB 업로드, doc_chunk API 사용자) |
| **RISK** | HWP 5.0 레코드 구조(컨트롤 문자, 표 중첩)를 잘못 해석해 글자가 깨지거나 빠짐. 암호화·배포용 문서는 읽을 수 없음 |
| **SUCCESS** | 실제 .hwp/.hwpx 샘플에서 본문과 표 텍스트가 순서대로 추출되고, KB 업로드 200, 미지원·손상 파일 422. PDF·엑셀 경로 회귀 0건(FAILED 목록 diff) |
| **SCOPE** | M1 포맷 등록 → M2 HWP 5.0 리더 → M3 HWPX 리더 → M4 어댑터·라우팅·DI → M5 doc_chunk 분기 → M6 프론트 accept |

---

## 1. 개요

### 1.1 설계 목표

- `.hwp`/`.hwpx`의 텍스트를 기존 청킹·임베딩·ES 파이프라인이 그대로 받는 `List[Document]`로 만든다
- 추가만 한다: PDF·엑셀 경로 동작과 기존 생성자 호출부는 바꾸지 않는다
- 암호화·배포용·손상·빈 파일은 처음부터 `ValueError` 계열 예외로 거부한다 (기존 422 매핑)

### 1.2 설계 원칙

- **포맷 해석은 infra에만**: 바이너리·XML 해석은 `infrastructure/parser/hwp/`에 둔다. 도메인에는 포맷 상수와 예외 타입만 둔다 (순수 Python)
- **리더는 섹션별 텍스트만 돌려준다**: 반환형은 `list[str]`(섹션별 텍스트). Document·메타데이터 조립은 어댑터만 한다. 리더를 따로 테스트할 수 있다
- **추가형 확장**: 새 생성자 인자는 마지막 optional 인자로 붙인다 (위키 `additive-contract-extension`)
- **엑셀 어댑터 선례**: 섹션 1개 = Document 1개, `DocumentMetadata` 계약 준수 (청킹·ES·콘텐츠 브라우저가 이 키에 의존)

---

## 2. 설계안 비교

### 2.0 비교표

| 기준 | A안: 최소 변경 | B안: 클린 | C안: 실용 균형 |
|------|:-:|:-:|:-:|
| **방식** | 파일 1개 | 엑셀처럼 4단 구조 (도메인 인터페이스·엔티티·직렬화기) | infra 패키지: 리더 2개 + 어댑터 |
| **새 파일 수** | 1 | 7~8 | 4 |
| **복잡도** | 낮음 (대신 파일이 큼) | 높음 | 중간 |
| **유지보수성** | 낮음 | 높음 | 높음 |
| **작업량** | 적음 | 많음 | 중간 |
| **위험** | 버그 하나 고칠 때 영향 범위가 큼 | 과도한 추상화 (CLAUDE.md §6 위반) | 낮음 |

**선택**: C안. **이유**: 리더 단위로 따로 테스트할 수 있고, 업무 규칙이 없는 엔티티를 도메인에 만들지 않아도 된다.

### 2.1 컴포넌트 구성도

```
                       ┌───────────────────────────────────┐
 KB 업로드 ────────────▶│ ExtensionRoutingParser             │
 (UnifiedUploadUseCase)│  pdf   → PDF 파서                  │
                       │  excel → ExcelDocumentParserAdapter│
                       │  hwp   → HwpDocumentParser  ◀ 신규 │
                       └──────────────┬────────────────────┘
 /doc-chunk ──▶ DocChunkUseCase ──────┤ (.hwp/.hwpx 분기)
                                      ▼
                       ┌───────────────────────────────────┐
                       │ HwpDocumentParser(PDFParserInterface)│
                       │  확장자로 리더 선택 → list[str]       │
                       │  → List[Document] (DocumentMetadata) │
                       └───────┬───────────────────┬───────┘
                               ▼                   ▼
                  Hwp5Reader (olefile+zlib)   HwpxReader (zipfile+etree)
```

### 2.2 데이터 흐름

```
bytes ─▶ HwpDocumentParser.parse_bytes(filename)
          ├─ .hwp  → Hwp5Reader.read_sections(bytes) → ["섹션1 텍스트", ...]
          └─ .hwpx → HwpxReader.read_sections(bytes) → ["섹션1 텍스트", ...]
        ─▶ 빈 섹션 제외 → 남은 게 0개면 오류
        ─▶ Document(page_content=텍스트, metadata=DocumentMetadata(page=i, total_pages=n, parser="hwp"|"hwpx"))
```

### 2.3 의존성

| 컴포넌트 | 의존 대상 | 용도 |
|----------|----------|------|
| Hwp5Reader | `olefile`(신규, BSD), `zlib`, `struct` | OLE 컨테이너 열기, 압축 해제, 레코드 해석 |
| HwpxReader | `zipfile`, `xml.etree.ElementTree` | 섹션 XML 파싱 |
| HwpDocumentParser | 리더 2개, `DocumentMetadata`, `generate_document_id` | Document 조립 |
| ExtensionRoutingParser | `FORMAT_HWP` | 라우팅 |

---

## 3. 데이터 모델

DB 변경 없음. 도메인 엔티티도 만들지 않는다 (설계 의도).

### 3.1 리더 내부 계약

```python
# infrastructure/parser/hwp/_types.py
class HwpSectionReader(Protocol):
    def read_sections(self, data: bytes) -> list[str]: ...
```

- 반환값: 문서 순서대로 섹션별 텍스트. 문단은 `\n`으로 구분, 표는 §3.3 표기
- 실패 시 `HwpParseError` 계열만 던진다 (§6)

### 3.2 HWP 5.0 해석 규칙 (Hwp5Reader)

| 항목 | 규칙 |
|------|------|
| 컨테이너 확인 | `olefile.isOleFile`이 거짓이면 `HwpParseError("올바른 HWP 파일이 아닙니다")` |
| FileHeader | `FileHeader` 스트림 256바이트. 앞 17바이트 시그니처 `b"HWP Document File"`. 오프셋 36의 속성 DWORD: bit0 압축, bit1 암호, bit2 배포용 문서 |
| 거부 | bit1 또는 bit2가 켜져 있으면 `HwpEncryptedError` |
| 섹션 목록 | `BodyText/Section{N}` 스트림을 N 오름차순 정렬 |
| 압축 해제 | 압축 문서면 `zlib.decompressobj(-15)` (raw deflate). 출력이 `max_decompressed_bytes`를 넘으면 중단 |
| 레코드 헤더 | DWORD LE: TagID = bit 0~9, Level = bit 10~19, Size = bit 20~31. Size가 0xFFF면 다음 DWORD가 실제 크기 |
| 사용하는 태그 | `PARA_TEXT=67`, `CTRL_HEADER=71`, `LIST_HEADER=72` (HWPTAG_BEGIN 16 + 오프셋) |
| 제외 컨트롤 | 컨트롤 ID `head`·`foot`·`fn  `·`en  `(머리말·꼬리말·각주·미주)는 하위 레코드까지 건너뛴다. **표 셀 안에서도 같다**. 글상자(`gso `)는 본문으로 보고 포함 |

**PARA_TEXT 디코딩** (UTF-16LE WCHAR 배열, 코드 32 미만은 컨트롤 문자):

| 종류 | 코드 | 차지 폭(WCHAR) | 출력 |
|------|------|:---:|------|
| 문자 컨트롤 | 0, 10, 13, 24~31 | 1 | 10 → `\n`, 13 → 문단 끝(버림), 24 → `-`, 30·31 → 공백, 나머지는 버림 |
| 인라인 컨트롤 | 4~9, 19, 20 | 8 | 9(탭) → `\t`, 나머지는 버림 |
| 확장 컨트롤 | 1~3, 11, 12, 14~18, 21~23 | 8 | 버림 (표·그림 같은 개체의 위치 표시) |

> 위 값은 한컴 공개 HWP 5.0 명세 기준이다. Do 단계에서 이 표를 단위 테스트로 먼저 고정한다 (§8 U-02).

### 3.3 표 텍스트 표기

- `CTRL_HEADER`의 컨트롤 ID가 `"tbl "`(앞 4바이트를 LE로 뒤집은 값)이면 표 모드를 시작하고, 표의 레벨을 기록한다
- 표 안에서 표 레벨+1의 `LIST_HEADER`를 만날 때마다 새 셀이 시작된다. 셀 안의 문단은 공백으로 잇는다
- 행 판별: `LIST_HEADER` 데이터의 셀 행 주소(`UINT16`)를 쓴다. **행이 바뀌면 줄바꿈, 같은 행의 셀은 ` | `로 잇는다**
- 레코드 레벨이 표 레벨 이하로 내려오면 표 모드를 끝낸다. 표 블록 앞뒤에 빈 줄 1개
- 행 주소를 못 읽으면(데이터 길이 부족) 셀을 ` | `로 한 줄에 이어 붙인다 (글자는 유지)
- 중첩 표는 바깥 셀의 텍스트로 평탄화한다 (구조 복원은 스코프 밖)
- **캡션**: 레코드 순서는 `CTRL(tbl) → [캡션 LIST_HEADER·문단] → TABLE(77) → 셀 LIST_HEADER들`이다. TABLE 레코드 전에 나온 LIST_HEADER는 캡션으로 보고 표 위 한 줄로 출력한다 (실파일 `table-caption.hwp`로 확인)

> 행 주소 위치는 실파일(`table.hwp`) 원시 바이트로 확정했다: 셀 LIST_HEADER의 오프셋 8=열, **10=행**, 12=열 병합, 14=행 병합. 명세 문서는 리스트 헤더를 6바이트로 적지만 실파일은 8바이트다.

### 3.4 HWPX 해석 규칙 (HwpxReader)

| 항목 | 규칙 |
|------|------|
| 컨테이너 확인 | `zipfile.is_zipfile`이 거짓이거나 `Contents/section*.xml`이 없으면 `HwpParseError` |
| 암호화 | `META-INF/manifest.xml`에 `encryption-data`가 있으면 `HwpEncryptedError` |
| 섹션 순서 | `Contents/section(\d+)\.xml`을 번호순 정렬 |
| 안전 | `ZipInfo.file_size` 합계가 `max_decompressed_bytes`를 넘으면 중단. 섹션 XML에 `<!DOCTYPE`이 있으면 거부 (엔티티 확장 차단) |
| 네임스페이스 | 로컬 이름으로 매칭 (`{*}p`, `{*}t`, `{*}tbl`, `{*}tr`, `{*}tc`). 버전 차이에 영향받지 않음 |
| 문단 | `p` 아래 `t`의 텍스트를 이어 붙인다 (`tab` → `\t`, `lineBreak` → `\n`) |
| 표 | `tbl > tr > tc`: 셀은 ` | `, 행은 `\n`. §3.3과 같은 표기 |
| 순회 | 섹션 루트부터 재귀 순회. 문단(`p`)은 자기 글자 → 그 안에 박힌 표·글상자 문단 순서로 블록을 만든다. 표 안의 문단은 표 렌더러만 처리한다 (중복 출력 방지) |
| 제외 요소 | 로컬 이름 `header`·`footer`·`footNote`·`endNote` 아래는 건너뛴다 (HWP 5.0 제외 컨트롤과 같은 기준). 글상자(`rect > drawText`) 글자는 포함 |
| 인라인 요소 | `t` 안의 `tab`→`\t`, `lineBreak`→`\n`, `nbSpace`·`fwSpace`→공백, `hyphen`→`-` |
| 셀 평탄화 | 셀 안 문단(중첩 표 포함)을 공백으로 잇는다 (HWP 5.0과 같은 표기) |

---

## 4. API 명세

새 엔드포인트는 없다. 기존 엔드포인트가 받는 확장자만 늘어난다.

| Method | 경로 | 변경 |
|--------|------|------|
| POST | KB 문서 업로드 (knowledge_base_router) | `.hwp/.hwpx` 허용 (`supported_formats` 경유) |
| POST | 통합 업로드 (unified upload) | 같음 (`ExtensionRoutingParser` 경유) |
| POST | `/doc-chunk` | `SUPPORTED_EXTENSIONS`에 `.hwp/.hwpx` 추가 |

응답 스키마는 바뀌지 않는다. 오류 응답은 기존 `ValueError → 422` 매핑을 따른다.

---

## 5. UI/UX 설계

### 5.3 컴포넌트 목록

| 컴포넌트 | 위치 | 변경 |
|----------|------|------|
| KbUploadDocumentModal | `idt_front/src/components/knowledge-base/` | `accept=".pdf,.xlsx,.xls,.hwp,.hwpx"`, 안내 문구 "지원 형식: PDF, 엑셀(.xlsx/.xls), 한글(.hwp/.hwpx) …" |

### 5.4 화면 체크리스트

#### KbUploadDocumentModal
- [ ] 파일 입력 accept에 `.hwp`, `.hwpx` 포함
- [ ] 안내 문구에 한글(.hwp/.hwpx) 표기
- [ ] 기존 엑셀 안내 문구 유지

---

## 6. 오류 처리

### 6.1 오류 정의

| 예외 | 위치 | 발생 조건 | HTTP |
|------|------|----------|------|
| `HwpParseError(ValueError)` | `domain/parser/exceptions.py` | 손상, 시그니처 불일치, 압축 해제 실패, 크기 상한 초과, DOCTYPE 포함 | 422 |
| `HwpEncryptedError(HwpParseError)` | 같음 | 암호, 배포용 문서, HWPX 암호화 | 422 |
| `ValueError("추출할 텍스트가 없습니다…")` | 어댑터 | 모든 섹션이 비어 있음 | 422 |
| `UnsupportedFileFormatError` | 기존 | 등록되지 않은 확장자 | 422 |

- 도메인 예외는 순수 Python이다. `ValueError`를 상속해 기존 라우터 매핑을 그대로 탄다 (kb-excel-upload D2 선례)
- 어댑터는 `HwpParseError`를 그대로 다시 던진다. 단 리더가 감싼 손상 오류(`__cause__` 있음)는 `logger.warning("HWP parse rejected", exception=원인, file_name=…)`로 원인을 남긴다 (Plan FR-07). 암호 문서처럼 원인 예외가 없는 정상 거부는 로그를 남기지 않는다. 예상하지 못한 예외(`struct.error`, `zlib.error`, `KeyError` 등)는 `logger.error("HWP parsing failed", exception=e, file_name=…)`로 남긴 뒤 `raise HwpParseError(...) from e`로 감싼다

### 6.2 오류 응답 형식

기존 422 형식(`{"detail": "<메시지>"}`)과 같다. 메시지 예:
- `"암호가 걸렸거나 배포용으로 저장된 한글 문서는 지원하지 않습니다"`
- `"'x.hwp'에서 추출할 텍스트가 없습니다"`

---

## 7. 보안

- [x] 압축 폭탄: HWP zlib 출력과 HWPX ZIP 전체 크기 모두 `max_decompressed_bytes`로 제한 (config `kb_hwp_max_decompressed_mb`, 기본 50)
- [x] XML 엔티티 확장: `<!DOCTYPE`이 있는 섹션은 거부. 표준 `ElementTree`만 쓰고 외부 참조는 해석하지 않음
- [x] ZIP 경로 조작: 항목을 읽기만 하고 디스크에 풀지 않음
- [x] 로그에 본문 내용을 남기지 않음 (파일명·섹션 수만)

---

## 8. 테스트 계획

### 8.1 테스트 범위

| 종류 | 대상 | 도구 |
|------|------|------|
| 단위 | 리더 디코딩 규칙, 어댑터 메타데이터, 라우팅 | pytest |
| 샘플 파일 기반 | 실제 .hwp/.hwpx 텍스트 추출 | pytest + `tests/fixtures/hwp/` |
| 통합 | KB 업로드·doc_chunk 인프로세스 실행 | pytest + TestClient |
| 프론트 | 업로드 모달 accept·안내 문구 | Vitest + RTL |

### 8.2 단위·샘플 테스트 시나리오

| # | 대상 | 시나리오 | 기대 결과 |
|---|------|----------|----------|
| U-01 | supported_formats | `.hwp`, `.HWPX`, `C:\a\b.hwpx` | `FORMAT_HWP`. display에 hwp, hwpx 포함 |
| U-02 | Hwp5Reader 디코딩 | 문자·인라인(탭)·확장(표 위치) 컨트롤이 섞인 PARA_TEXT 바이트 | §3.2 표대로 정확히 변환 (8 WCHAR 건너뛰기 확인) |
| U-03 | 레코드 헤더 | Size=0xFFF 확장 크기 | 다음 DWORD를 크기로 읽음 |
| U-04 | Hwp5Reader | `iter_records`, `decode_para_text`를 바이트 단위로 검증 + OLE 대역으로 `read_sections`(비압축·압축·섹션 정렬·합산 상한·FileHeader 누락) 검증 | — |
| U-05 | Hwp5Reader | OLE가 아닌 바이트 | `HwpParseError` |
| U-06 | Hwp5Reader | FileHeader 암호·배포용 비트 | `HwpEncryptedError` |
| U-07 | Hwp5Reader | 압축 해제 결과가 상한 초과 | `HwpParseError` |
| U-08 | HwpxReader | 메모리 ZIP (section0/1, 문단 + 표) | 섹션 순서, ` | `·줄바꿈 표기 |
| U-09 | HwpxReader | DOCTYPE 포함 / manifest에 encryption-data | `HwpParseError` / `HwpEncryptedError` |
| U-10 | HwpDocumentParser | 리더가 `["a", "", "b"]` 반환 | Document 2개, page=1·2, total_pages=2, parser="hwp" |
| U-11 | HwpDocumentParser | 모든 섹션이 빔 | `ValueError` (추출할 텍스트 없음) |
| U-12 | HwpDocumentParser | 리더가 `zlib.error` 발생 | `HwpParseError`로 감싸고 error 로그 남김 |
| U-13 | ExtensionRoutingParser | hwp 파서 주입 후 `x.hwp` | hwp 파서로 위임. 주입하지 않으면 `x.hwp` → `UnsupportedFileFormatError` |
| U-14 | DocChunkUseCase | hwp_parser 주입 후 `.hwp` 요청 | 청크 결과 반환. 기존 doc_chunk 테스트는 수정 없이 통과 (`.hwp` 성공 케이스는 샘플 확보 후 추가) |
| F-01 | **실파일** `hwpjs_basics_report.hwp` | 문단 텍스트 | 기대 문구가 순서대로 포함, 컨트롤 문자 잔여물 없음 (`\t\n` 제외 `\x00`~`\x1f`) |
| F-02 | **실파일** `hwpjs_basics_report.hwp` | 표 셀 | `과목명 \| ○○○○` 행 표기(§3.3) 확인 |
| F-03 | **실파일** `rhwp_nested_table.hwpx` | HWPX 중첩 표 | 평탄화 결과 정확히 일치 |
| F-04 | (커밋 불가 — 아래 §8.5) | 문서 암호·배포용 | `HwpEncryptedError` — 단위 테스트 + 로컬 실파일 확인 |
| F-05 | **실파일** `rhwp_footnote_textbox.hwp` | 글상자·각주 | 글상자 글자 포함, 본문·글상자 안 각주 제외 |
| I-01 | KB 업로드 TestClient | `.hwp` 업로드 (벡터·ES는 스텁) | 200, 청크 수 > 0 |

### 8.4 실서버 확인

- 개발 서버(Qdrant/ES 기동)에서 실제 .hwp를 KB에 1회 이상 업로드. 환경이 안 되면 `ops/e2e-carryover-checklist`의 E2E 이월 목록에 올린다

### 8.5 테스트 샘플 파일

로컬에 한글 프로그램이 없어 직접 작성 대신 **허용 라이선스 공개 저장소의 실제 한글 파일**을 쓴다. 출처·라이선스는 `tests/fixtures/hwp/NOTICE.md`.

| 파일 | 원본 (라이선스) | 용도 |
|------|----------------|------|
| `hwpjs_basics_report.hwp` | hahnlee/hwp.js (Apache-2.0) | F-01, F-02 |
| `rhwp_nested_table.hwpx` | edwardkim/rhwp (MIT) | F-03 |
| `rhwp_footnote_textbox.hwp` | edwardkim/rhwp (MIT) | F-05 |

- F-04(암호·배포용)는 허용 라이선스 실파일이 없다. pyhwp 공개 픽스처로 로컬에서만 확인하고(라이선스 불명확이라 커밋 안 함), 저장소에서는 FileHeader 비트 단위 테스트로 고정한다.
- 픽스처 테스트는 **skip하지 않는다** (파일이 없으면 실패. 거짓 초록 품질 게이트 방지).

---

## 9. 레이어 배치

### 9.4 이번 기능의 레이어 배치

| 컴포넌트 | 레이어 | 위치 |
|----------|--------|------|
| `FORMAT_HWP`, 확장자 매핑 | Domain | `src/domain/parser/supported_formats.py` |
| `HwpParseError`, `HwpEncryptedError` | Domain | `src/domain/parser/exceptions.py` |
| `Hwp5Reader`, `HwpxReader`, `HwpSectionReader` | Infrastructure | `src/infrastructure/parser/hwp/` |
| `HwpDocumentParser` | Infrastructure | `src/infrastructure/parser/hwp/hwp_document_parser.py` |
| hwp 분기 | Application | `src/application/doc_chunk/use_case.py` |
| DI | Interfaces | `src/api/main.py` |

의존 방향: application → domain `PDFParserInterface`(변경 없음), infra → domain(예외·메타데이터). 도메인은 infra나 olefile을 import하지 않는다.

---

## 10. 코딩 규칙

### 10.3 설정값

| 키 | 기본값 | 소비 지점 |
|----|--------|----------|
| `kb_hwp_max_decompressed_mb` | 50 | `HwpDocumentParser.__init__` → 두 리더의 `max_decompressed_bytes`로 전달 (docstring에 소비 지점 명기) |

### 10.4 이번 기능의 규칙

| 항목 | 규칙 |
|------|------|
| 함수 길이 | 40줄 이하. 레코드 순회는 `iter_records` 제너레이터, 디코딩은 `decode_para_text`로 분리 (단위 테스트를 위해 공개 이름) |
| 로깅 | `get_logger(__name__)`, 오류 경로는 `exception=e`, print 금지 |
| 주석 | 파일 머리에 `Design Ref: §x` (Do 단계 규칙) |

---

## 11. 구현 가이드

### 11.1 파일 구조

```
idt/
├─ pyproject.toml                                   (수정: olefile)
├─ src/config.py                                    (수정: kb_hwp_max_decompressed_mb)
├─ src/domain/parser/supported_formats.py           (수정)
├─ src/domain/parser/exceptions.py                  (수정)
├─ src/infrastructure/parser/hwp/__init__.py        (신규)
├─ src/infrastructure/parser/hwp/_types.py          (신규: Protocol, 표 렌더링 헬퍼)
├─ src/infrastructure/parser/hwp/hwp5_reader.py     (신규)
├─ src/infrastructure/parser/hwp/hwpx_reader.py     (신규)
├─ src/infrastructure/parser/hwp/hwp_document_parser.py (신규)
├─ src/infrastructure/parser/extension_routing_parser.py (수정: hwp_parser optional)
├─ src/domain/doc_chunk/schemas.py                  (수정)
├─ src/application/doc_chunk/use_case.py            (수정: hwp_parser optional)
├─ src/api/main.py                                  (수정: DI 2곳)
└─ tests/... (domain/parser, infrastructure/parser/hwp, application/doc_chunk, fixtures/hwp)
idt_front/
└─ src/components/knowledge-base/KbUploadDocumentModal.tsx (+ .test.tsx)
```

생성자 변경 (추가형):

```python
ExtensionRoutingParser(pdf_parser, excel_parser, hwp_parser: PDFParserInterface | None = None)
# hwp_parser가 None인데 .hwp 요청이 오면 → UnsupportedFileFormatError (미등록 포맷과 같게 처리)

DocChunkUseCase(pdf_parser, excel_parser, logger, hwp_parser: PDFParserInterface | None = None)
```

### 11.2 구현 순서

1. [ ] M1: `supported_formats` + 예외 (U-01) → `olefile` 의존성, config
2. [ ] M2: `Hwp5Reader` — 레코드 순회, PARA_TEXT 디코딩, 표 표기 (U-02~07, F-01·F-02·F-04)
3. [ ] M3: `HwpxReader` (U-08, U-09, F-03)
4. [ ] M4: `HwpDocumentParser` + `ExtensionRoutingParser` + `main.py` KB DI (U-10~13, I-01)
5. [ ] M5: doc_chunk 분기 + DI (U-14)
6. [ ] M6: 프론트 accept·안내 문구 (Vitest)
7. [ ] 회귀 확인: 변경 전후 FAILED 목록 diff, `/verify-architecture`, `/verify-logging`

### 11.3 세션 가이드

#### 모듈 지도

| 모듈 | Scope 키 | 내용 | 예상 턴 |
|------|----------|------|:------:|
| 포맷 등록 | `module-1` | supported_formats, 예외, config, 의존성 | 3~5 |
| HWP 5.0 리더 | `module-2` | OLE·레코드·디코딩·표 + 실제 샘플 테스트 | 10~15 |
| HWPX 리더 | `module-3` | ZIP/XML, 표 | 6~8 |
| 어댑터·KB 연결 | `module-4` | HwpDocumentParser, 라우팅, DI, I-01 | 6~8 |
| doc_chunk | `module-5` | 분기 + DI | 3~4 |
| 프론트 | `module-6` | accept, 안내 문구, 테스트 | 2~3 |

#### 권장 세션 계획

| 세션 | 단계 | 범위 | 턴 |
|------|------|------|:--:|
| 세션 1 | Do | `--scope module-1,module-2` (샘플 파일 먼저 준비) | 15~20 |
| 세션 2 | Do | `--scope module-3,module-4` | 12~16 |
| 세션 3 | Do | `--scope module-5,module-6` + 회귀 확인 | 6~8 |
| 세션 4 | Check | `/pdca analyze hwp-parser` | 5~8 |

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 | 작성자 |
|------|------|----------|--------|
| 0.1 | 2026-10-08 | 최초 작성 (C안) | 배상규 |
| 0.2 | 2026-10-08 | 문서 전체를 한국어로 다시 작성 | 배상규 |
| 0.3 | 2026-10-09 | Check 반영: 제외 기준(§3.2·§3.4), HWPX 재귀 순회·인라인 요소, 원인 예외 로그(§6.1), U-04·U-14 갱신 | 배상규 |
| 0.4 | 2026-10-10 | 픽스처를 공개 실파일로 교체(§8.2·§8.5), 표 캡션 처리 추가(§3.3 — TABLE 레코드 전 LIST_HEADER는 캡션) | 배상규 |
