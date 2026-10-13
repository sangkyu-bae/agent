---
title: 한글(HWP 5.0/HWPX) 파서 — 실파일로 확정한 포맷 사실과 검증 방법
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/infrastructure/parser/hwp/hwp5_reader.py (_CELL_ROW_OFFSET=10, _Table 캡션 처리, _CTRL_SKIPPED, parse_file_header 플래그)
  - idt/src/infrastructure/parser/hwp/hwpx_reader.py (_DOCTYPE_RE 거부, _SKIPPED 이름 제외, nbSpace/fwSpace 치환)
  - idt/src/infrastructure/parser/hwp/hwp_document_parser.py (확장자→리더, 섹션=Document, DocumentMetadata 계약)
  - idt/src/infrastructure/parser/extension_routing_parser.py (hwp_parser optional 마지막 인자)
  - idt/src/api/main.py (HwpDocumentParser DI 2곳 — KB 업로드·doc_chunk), idt/src/config.py kb_hwp_max_decompressed_mb
  - idt/tests/fixtures/hwp/NOTICE.md (공개 실파일 3개 출처·라이선스)
  - idt/docs/archive/2026-10/hwp-parser/hwp-parser.analysis.md (§12 실파일 검증 표, §13 실서버 E2E)
  - idt/docs/archive/2026-10/hwp-parser/hwp-parser.report.md (§1.5 결정, §6 회고)
  - 커밋 8821876, 02677d0, de628f2
confidence: 0.85
version: 1
created: 2026-10-13
updated: 2026-10-13
verified_at: 3b6353b
---

# 한글(HWP 5.0/HWPX) 파서 — 실파일로 확정한 포맷 사실과 검증 방법

> 읽는 시점: **`infrastructure/parser/hwp/`를 고치거나 표·캡션·각주 처리 결과가 이상할 때**,
> 다른 업로드 진입점(컬렉션 업로드·document_extractor)에 한글 지원을 넓힐 때,
> 그리고 **새 바이너리 포맷 파서를 시작할 때**(검증용 실파일 확보 방식의 선례).

## 문제

KB 업로드가 pdf/xlsx/xls만 받아 한글 문서는 PDF 변환이 강제됐다. pyhwp는 AGPL이라 쓸 수 없어
순수 Python으로 직접 파싱해야 했는데, 로컬에 한글 프로그램이 없어 **샘플을 만들 수 없었고**
명세 문서와 실파일이 다른 지점이 있었다.

## 검증된 사실

### 1. 구현 선택 — 의존성은 `olefile`(BSD) 1개

- HWP 5.0: `olefile`로 OLE를 열고 `FileHeader` 플래그(오프셋 36, UINT32 LE) → 압축 비트면 섹션별
  zlib inflate(상한 `kb_hwp_max_decompressed_mb`, 기본 50MB 섹션 합산) → 레코드 헤더(tag 10bit·level 10bit·size 12bit)
  순회 → `PARA_TEXT`(UTF-16LE)에서 컨트롤 문자 제거. **암호(0x2)·배포용(0x4) 비트는 `HwpEncryptedError` → 422**.
- HWPX: ZIP 안 섹션 XML을 재귀 순회. `<!DOCTYPE|<!ENTITY`가 있으면 거부(XXE 방어).
- 컨트롤 ID는 UINT32 LE라 바이트가 뒤집혀 있다: `b" lbt"`=tbl, `b"daeh"`=head, `b"toof"`=foot, `b"  nf"`=fn, `b"  ne"`=en.
- 제외 기준은 두 포맷 동일: 머리말·꼬리말·각주·미주 제외(표 셀 안에 있어도), **글상자는 포함**.
  HWPX는 요소 이름(`header/footer/footNote/endNote`)으로, HWP5는 컨트롤 ID로.
- 표 표기: 셀 ` | `, 행 줄바꿈, 캡션은 표 위 한 줄. 중첩 표는 평탄화. `nbSpace`/`fwSpace`는 공백으로 치환
  (안 하면 단어가 붙는다).

### 2. 명세와 실파일이 다른 지점 — 셀 행 주소 오프셋은 **10**

명세는 문단 리스트 헤더를 6바이트로 적지만 실파일은 8바이트다. pyhwp `table.hwp` 원시 바이트로
확인: **오프셋 8=열, 10=행, 12=열 병합, 14=행 병합** (`_CELL_ROW_OFFSET = 10`). Do 단계 내내 추정값
(확신도 50%)이었고 실파일 검증에서 확정됐다.

### 3. 캡션 LIST_HEADER는 TABLE 레코드 **앞**에 온다

레코드 순서는 `CTRL(tbl) → [캡션 LIST_HEADER·문단] → TABLE → 셀 LIST_HEADER들`. 캡션을 셀로 세면
캡션이 첫 셀이 된다 — **합성 바이트 테스트는 이 케이스를 우연히 통과**하고 있었고 pyhwp
`table-caption.hwp` 실파일에서 결함이 드러났다. 지금은 TABLE 레코드 전 LIST_HEADER를 캡션으로 모은다.
캡션 자동 번호("표 1")는 컨트롤이라 번호 없이 나온다(검색 영향 작음, 보류).

### 4. 한글 프로그램 없이 실파일 19개로 검증한 방법

공개 파서 저장소의 테스트 픽스처를 임시 폴더에 받아 로컬 검증하고, **허용 라이선스 3개만 커밋**:
hwp.js(Apache-2.0) `basicsReport.hwp`, rhwp(MIT) `footnote-tbox-01.hwp`·`centered_cell_nested_table.hwpx`.
pyhwp(AGPL) 파일은 로컬 확인에만 썼고 저장소에 넣지 않았다(암호 파일 422 확인 포함). 출처·라이선스는
`tests/fixtures/hwp/NOTICE.md`. Windows curl이 인증서 폐기 확인에 실패하면 `--ssl-no-revoke`.

다른 라이브러리가 표 컨트롤 없이 셀을 일반 문단으로 쓴 파일(`hwpers_test4_complex_table.hwp`)은 표 표기가
안 나오는 것이 정상이다 — 파일 구조 그대로.

### 5. 배선은 추가형 — 기존 테스트 수정 0줄

`ExtensionRoutingParser(..., hwp_parser=None)`·`DocChunkUseCase`에 **optional 마지막 인자**로 붙였다.
등록된 포맷이라도 파서 미주입이면 미지원과 같게 처리. `HwpParseError(ValueError)`는 기존 ValueError
편승으로 KB 업로드·통합 업로드·doc_chunk 3개 라우터 모두 422. 메타데이터는 엑셀 어댑터와 같은
`DocumentMetadata` 계약(page/total_pages/parser/document_id — 청킹·ES·콘텐츠 브라우저가 의존).
프론트는 `KbUploadDocumentModal` `accept=".pdf,.xlsx,.xls,.hwp,.hwpx"`.

환경 메모: 로컬 ES에 `analysis-nori`가 없어 `documents` 인덱스가 한국어 분석기 없이 생성됐다 —
한글 문서 검색 품질을 볼 때 nori 설치 후 인덱스 재생성이 선행이다.

## 다음에 적용하는 법

1. **바이너리 포맷 파서는 Plan에서 "검증용 실파일 출처와 라이선스"를 먼저 정한다.** 샘플이 없으면
   오프셋 같은 수치가 사이클 끝까지 추정값으로 남는다.
2. 합성 바이트 테스트는 가능하면 **실파일에서 뽑은 바이트**를 그대로 쓴다. 손으로 만든 바이트는
   구현의 가정을 그대로 복제해 결함을 숨긴다.
3. 다른 진입점에 한글을 넓힐 때는 `HwpDocumentParser`를 같은 optional 인자 패턴으로 주입한다(main.py DI 2곳 참조).
4. 한글·이스케이프·NUL이 섞인 파일 수정은 셸 heredoc 대신 Edit 도구나 스크립트 파일로(여러 번 깨졌다).

## 관련 문서

- 확장자 라우팅 선례: `backend/api/router-map.md` (excel_upload 행)
- additive 인자 패턴: `conventions/additive-contract-extension.md`
- 회귀 증명 방식: `conventions/false-green-quality-gates.md`
