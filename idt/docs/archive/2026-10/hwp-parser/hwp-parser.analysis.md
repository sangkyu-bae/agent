# hwp-parser 갭 분석 보고서

> **분석 대상**: hwp-parser (idt + idt_front)
> **기준 문서**: [계획](hwp-parser.plan.md), [설계 v0.2](hwp-parser.design.md)
> **분석일**: 2026-10-09
> **방법**: gap-detector 정적 분석 + 전체 pytest 회귀 + 커버리지 측정 + 실제 .hwp 1개 스모크 실행 (서버 미기동 → L1 생략)

---

## Context Anchor

| 키 | 내용 |
|----|------|
| **WHY** | 한글 문서를 PDF로 바꾸지 않고 바로 KB에 넣기 위해 |
| **WHO** | P2 KB 운영자·에이전트 소유자 (KB 업로드, doc_chunk API 사용자) |
| **RISK** | HWP 5.0 레코드 구조 해석 오류로 글자가 깨지거나 빠짐. 암호화·배포용 문서는 읽을 수 없음 |
| **SUCCESS** | 실제 .hwp/.hwpx 샘플에서 본문·표 텍스트가 순서대로 추출, KB 업로드 200, 미지원·손상 422, PDF·엑셀 회귀 0건 |
| **SCOPE** | M1 포맷 등록 → M2 HWP 5.0 리더 → M3 HWPX 리더 → M4 어댑터·라우팅·DI → M5 doc_chunk → M6 프론트 |

---

## 전략 정합성 점검

### 핵심 문제 해결 여부
한글 파일을 KB 업로드·`/doc-chunk`에 그대로 올릴 수 있게 됐다. 일반화 원칙(특정 도메인 하드코딩 없음)도 지켰다. **다만 "실제 샘플에서 순서대로 추출"이라는 SUCCESS 기준은 본문만 확인됐고 표·암호·HWPX는 실파일로 확인되지 않았다.**

### 성공 기준 상태 (계획 §4)

| 기준 | 상태 | 근거 |
|------|:----:|------|
| FR-01~FR-10 구현, TDD 순서 | ✅ | 모든 모듈 테스트 선작성(Red 확인) 후 구현 |
| 실제 샘플 픽스처로 기대 텍스트 단언 | ❌ | `tests/fixtures/hwp/`에 README만 있음. F-01~F-04 테스트 5개 실패 상태 |
| KB 업로드 실행 1회 이상 | ⚠️ | 서버 대신 `UnifiedUploadUseCase` 통합 테스트(I-01, 사용자 승인). `.hwpx`만 |
| 회귀 0건 (FAILED 목록 diff) | ✅ | 58 failed = 기존 53 + 샘플 테스트 5. 기존 실패 목록과 차이 없음 |
| 프론트 테스트·`tsc -b` | ✅ | 모달 테스트 4/4. `tsc -b` 오류 211건은 변경 전과 동일 |
| 신규 모듈 커버리지 80% 이상 | ✅ | 93% (hwp 패키지·doc_chunk). 미실행은 `Hwp5Reader.read_sections` OLE 경로 |
| ruff 위반 0 (신규 파일) | ✅ | 신규 파일 0건 |

### 결정 기록 이행

| 결정 | 이행 | 결과 |
|------|:----:|------|
| [Plan] HWP + HWPX 둘 다 | ✅ | 리더 2개 |
| [Plan] olefile + 자체 레코드 파서 | ✅ | 의존성은 olefile 1개 추가 |
| [Plan] 본문 + 표 텍스트 | ✅ | 셀 ` \| `, 행 줄바꿈 |
| [Design] C안 (infra 패키지, 도메인은 상수·예외만) | ✅ | 도메인 레이어 위반 0 |
| [Design] 생성자 optional 마지막 인자 | ✅ | 기존 테스트 수정 0줄 (git diff 확인) |

---

## 1. 분석 개요

- 범위: 계획 FR-01~FR-10, 설계 §3(해석 규칙)·§6(오류)·§7(보안)·§8(테스트)·§10.3(설정)·§11.1(파일 구조)
- 실제 파일 스모크: 사용자 PC의 `Welcome to Hwp.hwp`(한컴 기본 동봉, 23KB, 압축 문서)를 읽기 전용으로 1회 파싱. 저장소에는 넣지 않음
  - 결과: 섹션 1개, 1,991자 정상 추출, 탭 유지, 컨트롤 문자 잔여물 0, **표 없음**(행 주소 오프셋은 여전히 미검증)
  - 의미: OLE 열기 → FileHeader → 섹션 정렬 → 압축 해제 → 레코드 디코딩 경로가 실제 파일에서 처음으로 동작 확인됨

---

## 2. 갭 분석

### 2.3 구조 일치 — 96

설계 §11.1의 파일이 모두 있다. DI 2곳(`main.py` KB 업로드, doc_chunk) 연결됨. 빠진 것은 샘플 파일 4개뿐.

### 2.4 기능 깊이 — 84

| 영역 | 판정 | 비고 |
|------|:----:|------|
| §3.2 HWP 5.0 규칙 (헤더 비트, 레코드 헤더, 컨트롤 문자 표) | 일치 | 표와 1:1 구현. 크기 상한은 섹션 합산이라 설계보다 엄격 |
| §3.3 표 표기·폴백·중첩 | 일치 | `_CELL_ROW_OFFSET=10`은 미검증 추정값 |
| §3.4 HWPX 규칙 | 대부분 일치 | 순회 방식이 설계(재귀)와 다름 → I-4 |
| 머리말·꼬리말·각주 제외 | 설계 미기재 | HWP5는 컨트롤 ID로 명시 제외, HWPX는 경로 고정으로 자연 제외 |

### 2.6 계약 — 91

예외 계층(`HwpParseError(ValueError)` → 422)이 KB 업로드·통합 업로드·doc_chunk 3개 라우터 모두에서 성립한다. 설정 소비 지점(§10.3)과 추가형 생성자도 일치. 감점은 FR-07 로그 누락(I-1).

### 2.7 런타임 검증

서버 미기동(`localhost:8000` 응답 없음)이라 L1(curl)·L2·L3는 생략했다. 대신 인프로세스 통합 테스트(I-01)와 실제 .hwp 스모크로 일부 보완.

### 2.8 Match Rate

```
정적 공식: 구조 96 × 0.2 + 기능 84 × 0.4 + 계약 91 × 0.4 = 89.2%
```

**Match Rate: 89%** (기준 90% 바로 아래)

---

## 3. 갭 목록

### Critical

| # | 갭 | 근거 |
|---|----|------|
| C-1 | 실샘플 단언(계획 DoD) 미충족. 본문은 스모크로 확인했지만 **표 행 표기, 암호 거부, HWPX 실파일**은 한 번도 실파일로 확인되지 않음 | `tests/fixtures/hwp/` README만 존재, `hwp5_reader.py:43` 추정값 |

### Important

| # | 갭 | 근거 | 제안 |
|---|----|------|------|
| I-1 | 리더가 감싼 `HwpParseError`(zlib·ZIP·XML 손상)가 KB 업로드 경로에서 **로그 없이** 422로 끝남. FR-07 "원인 예외 스택 트레이스 로그" 부분 충족 | `hwp_document_parser.py:80-81`, `knowledge_base_router.py:509-510` | 어댑터 `_read`에서 `__cause__`가 있으면 `logger.warning(..., exception=cause)` |
| I-2 | HWP 5.0 **비압축 본문** 경로 테스트 없음. 한글은 기본 압축 저장이라 샘플을 넣어도 계속 미검증일 가능성 | `hwp5_reader.py:213-216` | `read_sections`를 OLE 대역으로 검증하는 단위 테스트 추가 |
| I-3 | `.hwp` 성공 경로가 doc_chunk·KB 업로드 모두 `.hwpx`로만 검증됨 | `test_doc_chunk_use_case.py`, `test_hwp_upload_integration.py` | 샘플 확보 후 `.hwp` 케이스 추가 |
| I-4 | HWPX가 `p > run > (t\|tbl)`만 읽어 **글상자 본문이 HWPX에서만 빠짐**. 같은 문서를 .hwp/.hwpx로 올리면 결과가 다를 수 있음 | `hwpx_reader.py:59-80` vs `hwp5_reader.py:32,174-179` | 설계 §3.4에 제외 기준 명시 + HWPX도 머리말·각주를 이름으로 제외하고 나머지는 재귀 수집 |

### Low (문서 갱신·사소)

- HWPX 중첩 표 셀 텍스트가 구분자 없이 붙음 (`hwpx_reader.py:40-43`)
- 파서 미주입 시 422 메시지의 "Supported" 목록에 hwp가 표시됨 (운영 DI는 둘 다 주입하므로 실영향 없음)
- 계획 FR-04 "탭→공백", FR-06 "page=섹션 번호"가 설계·구현(`\t`, 빈 섹션 제외 후 1..n)과 다름 → 계획 문서 갱신
- HWPX 크기 상한이 이미지(BinData)까지 합산 → 이미지 많은 50MB 초과 .hwpx는 텍스트가 적어도 422

### 검증 필요 (확신도 80% 미만)

| 항목 | 확신도 | 확인 방법 |
|------|:------:|----------|
| `_CELL_ROW_OFFSET`이 10인지 8인지 | 50% | `with_table.hwp`로 F-02 |
| 캡션 달린 표에서 캡션이 첫 셀로 잡히는지 | 50% | 캡션 있는 표 샘플 |
| HWPX `nbSpace`·`fwSpace` 요소 무시로 단어가 붙는지 | 65% | 실제 HWPX 샘플 |
| HWP5 표 셀 안 각주가 셀 텍스트에 섞이는지 | 70% | 각주 포함 표 샘플 |

---

## 5. 테스트 커버리지

| 모듈 | 커버리지 | 미실행 줄 |
|------|:-------:|----------|
| `hwp5_reader.py` | 86% | 207-236 (`read_sections` OLE 경로 — 스모크로는 실행 확인) |
| `hwpx_reader.py` | 99% | 98 |
| `hwp_document_parser.py` | 100% | — |
| `doc_chunk/use_case.py` | 100% | — |
| 합계 | 93% | |

---

## 6. 레이어 준수

도메인(`src/domain`)에서 `olefile`·infrastructure import 0건. 파서 구현은 모두 `infrastructure/parser/hwp/`에 있다.

---

## 9. 권장 조치

1. **샘플 4개 커밋** → F-01~F-04 통과 확인, F-02 결과로 `_CELL_ROW_OFFSET` 확정 (C-1)
2. **I-1**: 어댑터에서 원인 예외가 있는 `HwpParseError`를 warning 로그로 남김 (작은 수정)
3. **I-2**: OLE 대역으로 `read_sections` 비압축·압축·섹션 정렬 단위 테스트 추가
4. **I-4**: HWPX 순회를 재귀 수집 + 이름 기반 제외로 바꾸고 설계 §3.2·§3.4에 제외 기준 명시
5. I-3은 1번 이후 `.hwp` 케이스 추가로 해소

## 10. 설계 문서 갱신 필요

- §3.2·§3.4: 머리말·꼬리말·각주·미주 제외 규칙, 글상자 포함 여부
- §6.1: 원인 예외 로그 정책(FR-07과 일치시키기)
- §10.4·U-04: 함수 이름 `iter_records`·`decode_para_text`(공개 이름)
- 계획 FR-04·FR-06 문구

---

## 11. Act-1 반영 결과 (2026-10-09)

사용자 결정: "지금 모두 수정" + 글상자 텍스트 포함(계획서 §2.2 갱신).

| 갭 | 조치 | 검증 |
|----|------|------|
| I-1 원인 예외 로그 | 어댑터가 `__cause__` 있는 `HwpParseError`를 `logger.warning(exception=원인)`으로 남김. 암호 등 정상 거부는 로그 없음 | `test_hwp_document_parser.py::TestErrors` 2건 추가 |
| I-2 비압축·OLE 경로 | OLE 대역으로 `read_sections` 검증: 비압축, 압축, 섹션 번호 정렬, 섹션 합산 상한, 암호 헤더, BodyText·FileHeader 누락 | `test_hwp5_reader.py::TestReadSectionsOlePath` 6건 |
| I-4 HWPX 순회 | 재귀 순회 + 이름 기반 제외(`header`·`footer`·`footNote`·`endNote`). 글상자 글자 포함. 중첩 표 셀은 공백으로 평탄화. `nbSpace`·`fwSpace`·`hyphen` 처리 | `test_hwpx_reader.py::TestTraversalAlignedWithHwp5` 5건 |
| (검증 필요) HWP5 셀 안 각주 | 표 셀 안에서도 제외 컨트롤을 건너뛰도록 수정 | `test_hwp5_reader.py::TestSkippedControlsInsideTable` |
| 문서 | 설계 v0.3(§3.2·§3.4·§6.1·U-04·U-14·§10.4), 계획 v0.2(§2.2 글상자 포함, FR-04, FR-06) | — |

- 실제 파일 스모크 재실행: `Welcome to Hwp.hwp` 1,991자, 컨트롤 문자 잔여물 0 (변경 전과 동일)
- 전체 회귀: 58 failed / 10394 passed. 기존 실패 목록과 차이 없음, 새 실패는 샘플 테스트 5개뿐
- ruff: 신규 파일 0건

### 재산정

```
구조 96 × 0.2 + 기능 93 × 0.4 + 계약 98 × 0.4 = 95.6%
```

**Match Rate: 89% → 96%**

### 남은 항목 (샘플 파일 필요)

- **C-1**: 표 행 표기(`_CELL_ROW_OFFSET`), 암호 거부, HWPX 실파일을 실제 샘플로 확인 (F-01~F-04)
- **I-3**: `.hwp` 성공 케이스를 doc_chunk·KB 업로드 테스트에 추가
- 실서버 KB 업로드 1회 (설계 §8.4)

---

## 12. 실파일 검증 (2026-10-09, 한글 프로그램 없이)

로컬 PC에 한글이 없어 직접 샘플을 만들 수 없었다. 대신 공개 저장소의 실제 한글 파일을 임시 폴더에 받아 검증했다.

| 확인 항목 | 파일 (출처) | 결과 |
|----------|------------|------|
| 표 행 주소 오프셋 | `table.hwp` (pyhwp) | 셀 LIST_HEADER 원시 바이트: 오프셋 8=열, **10=행**, 12=열 병합, 14=행 병합 → `_CELL_ROW_OFFSET=10` **확정** |
| 표 표기 | `basicsReport.hwp` (hwp.js), `hwp_table_test_saved.hwp` (rhwp) | `과목명 \| ○○○○`, `제목 \| 담당자 \| 세부 내용` |
| 병합 셀 | `sample-5017.hwp` (pyhwp) | `A1 \| B10 B11` |
| **캡션 달린 표** | `table-caption.hwp` (pyhwp) | **결함 발견 → 수정**. 캡션 LIST_HEADER가 TABLE 레코드 앞에 와서 첫 셀로 잡혔다. TABLE 레코드 전 LIST_HEADER는 캡션으로 보고 표 위 한 줄로 출력 |
| 암호·배포용 | `password-12345.hwp`, `viewtext.hwp` (pyhwp) | 둘 다 `HwpEncryptedError`(422) |
| 머리말·꼬리말·각주·미주 | `headerfooter.hwp`, `footnote-endnote.hwp` (pyhwp), `footnote-tbox-01.hwp` (rhwp) | 제외 확인. 글상자 안 각주도 제외 |
| 글상자 | `textbox.hwp` (pyhwp), `footnote-tbox-01.hwp` (rhwp) | 포함 |
| 실제 HWPX | `business_overview.hwpx` 외 4개 (rhwp) | 표·중첩 표·본문 정상, 컨트롤 잔여물 0 |

- `table.hwp`는 셀이 모두 비어 있어 "추출할 텍스트 없음"(422)이 맞는 동작이었다.
- `hwpers_test4_complex_table.hwp`는 표 컨트롤 없이 셀을 일반 문단으로 쓴 파일(다른 라이브러리 생성)이라 표 표기가 안 나오는 것이 정상이다.

### 저장소 반영

- 허용 라이선스 실파일 3개를 `tests/fixtures/hwp/`에 넣고 출처를 `NOTICE.md`에 기록 (hwp.js Apache-2.0 1개, rhwp MIT 2개)
- F 테스트를 이 파일 기준으로 다시 작성: F-01(본문), F-02(표 행·셀), F-03(HWPX 중첩 표), F-05(글상자·각주) — **항상 실행, 전부 통과**
- F-04(암호)는 허용 라이선스 실파일이 없어 단위 테스트 + 이번 로컬 확인으로 대체 (pyhwp는 라이선스 불명확이라 커밋하지 않음)
- 캡션 회귀 방지 테스트 추가 (`TestTableCaption`, 실파일 캡션 바이트 사용)

### 재산정

C-1(실샘플 미검증)·I-3(.hwp 성공 경로) 해소. 남은 것은 실서버 업로드 1회뿐.

```
구조 100 × 0.2 + 기능 97 × 0.4 + 계약 98 × 0.4 = 98.0%
```

**Match Rate: 96% → 98%**

---

## 13. 실서버 경로 E2E (2026-10-11, Design §8.4)

실제 MySQL(3308)·Qdrant(6333)·ES(9200)·OpenAI 임베딩을 쓰는 인프로세스 `TestClient(app)`로 실행했다 (dev 서버 미기동). 일회용 컬렉션 `hwp_e2e_1791717690`과 KB `[E2E] hwp-parser`를 만들어 쓰고 끝나면 지웠다.

| 단계 | 결과 |
|------|------|
| 컬렉션 생성 / KB 생성 | 201 / 201 |
| `hwpjs_basics_report.hwp` 업로드 | **200**, chunk 8, Qdrant success, ES success |
| `rhwp_nested_table.hwpx` 업로드 | **200**, chunk 2, Qdrant success, ES success |
| 손상 `.hwp` 업로드 | **422** `올바른 HWP 파일이 아닙니다` |
| Qdrant 포인트 | 10개. payload `parser="hwp"`, `kb_id`, `collection_name` 정상 |
| ES 검색 `과목명` | 2건 적중. 본문에 `과목명 \| ○○○○` 표 표기, 형태소 키워드 정상 |
| 정리 | KB 삭제 200, 컬렉션 삭제 200, ES 문서 10건 삭제, 실행 중 자동 생성된 빈 `documents` 인덱스 삭제 → 실행 전 상태로 복구 |

### 환경 발견 사항 (이번 기능과 무관, 보고만)

- 로컬 ES 컨테이너에 **플러그인이 하나도 없다** (`analysis-nori` 없음). 앱 기동 시 `documents` 인덱스 생성이 `Unknown tokenizer type [nori_tokenizer]`로 실패하고, 첫 색인 때 기본 매핑으로 자동 생성된다. 한국어 BM25 품질에 영향이 있으므로 ES에 nori 설치 후 인덱스를 다시 만들어야 한다.
- 로컬 Qdrant에는 `wiki_knowledge` 컬렉션만 있다. MySQL의 기존 KB `테스트베이스`(컬렉션 `test10`)는 Qdrant에 실체가 없다 (Qdrant 데이터가 초기화된 것으로 보임).

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 | 작성자 |
|------|------|----------|--------|
| 0.1 | 2026-10-09 | 최초 분석 (Match Rate 89%) | 배상규 |
| 0.2 | 2026-10-09 | Act-1 반영 (I-1·I-2·I-4 해소, 96%) | 배상규 |
| 0.3 | 2026-10-09 | 공개 실파일 검증, 캡션 결함 수정, 픽스처 커밋 (C-1·I-3 해소, 98%) | 배상규 |
| 0.4 | 2026-10-11 | 실서버 경로 E2E 통과 (§13), 로컬 ES nori 미설치 발견 | 배상규 |
