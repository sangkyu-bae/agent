# docx-format-preserving-fill Design Document

> **Summary**: 원본이 DOCX인 추출기 템플릿은 보관 원본의 `document.xml`에서 칸 순서대로 예시값 위치를 찾아 값을 직접 넣는다. 매칭 규칙은 domain 순수 정책, zip/lxml 처리는 infra `DocxFiller`, 합성기는 선택 주입. 선택 설계: **Option C — 실용 균형**.
>
> **Project**: sangplusbot (Agent Builder) — idt
> **Author**: 배상규
> **Date**: 2026-11-07
> **Status**: Draft
> **Plan**: `idt/docs/01-plan/features/docx-format-preserving-fill.plan.md`

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | Word 양식이 HTML 왕복 변환으로 서식이 깨져 결재 문서로 쓸 수 없다. |
| **WHO** | P1(문서 작성 최종 사용자)과 P2(양식 등록자). |
| **RISK** | 예시값이 여러 run에 쪼개져 있거나 서로 겹치면 엉뚱한 자리를 바꾼다. 못 찾은 칸을 조용히 남기면 예시값이 결재 문서에 나간다. |
| **SUCCESS** | E2E 여신심의서 결과가 원본과 표 수·표 스타일·제목 크기·파트 목록이 같고 23칸이 원래 위치에 채워진다. 공란은 형광펜. PDF·HTML 경로 회귀 0. |
| **SCOPE** | M1 매칭 정책 + DocxFiller → M2 합성기 분기·폴백·DI → M3 E2E 실측 |

---

## 1. Overview

### 1.1 Design Goals

1. LLM이 칸 값을 정하는 단계(`_decide_slot_values`, 규칙 1~8, `SlotGroupPolicy`)는 그대로 둔다. 바뀌는 건 "값을 문서에 넣는" 단계뿐이다.
2. 칸 위치는 기존 프론트 토큰화와 **같은 의미**(칸 순서대로, 갱신된 문서 기준 첫 출현, 공백 무시)로 찾는다. 그래야 HTML 경로와 같은 자리가 바뀐다.
3. `document.xml` 외 모든 zip 파트는 바이트 그대로 둔다(스타일·번호·테마·이미지 보존).
4. 실패는 산출 실패가 아니라 폴백이다. 흡수 지점은 `DocxFiller.fill` 한 곳.
5. 미주입이면 기존 동작과 완전히 같다(기존 테스트 무변경).

### 1.2 Design Principles

- **degraded vs 실패**: 쓸 수 있는 결과(HTML 경로)가 있으므로 DOCX 경로 실패는 warning + 폴백(`degradation-vs-failure-boundary`).
- **domain 순수성**: domain은 lxml을 모른다. 문자열 구간 계산만 한다.
- **회귀 증명**: 전체 pytest FAILED 목록 diff(`false-green-quality-gates`).

---

## 2. Architecture

### 2.0 Architecture Comparison

| 항목 | A. 최소 | B. 클린 | **C. 실용 균형 (선택)** |
|---|---|---|---|
| 매칭 규칙 | composer 내부 | domain 정책 + 포트 2개 | domain 순수 정책 `SampleSpanPolicy` |
| zip/lxml | composer 내부 | 어댑터 2개 | infra `DocxFiller` 1개 |
| 합성기 연결 | 직접 | 포트 DI | 생성자 선택 인자 `docx_filler=None` |
| 신규 파일 | 0 | 4~5 | 2 + 테스트 2 |
| 위험 | 40줄 규칙 위반·테스트 곤란 | 과설계 | 덕 타이핑 주입(테스트로 계약 고정) |

선택 사유: 핵심 규칙(교차 run·공백 무시·순차)이 lxml 없이 단위 테스트되고, 미주입 시 기존 동작이 구조적으로 보존된다. 사용자 확인(2026-11-07).

### 2.1 Component Diagram

```
workflow_compiler._create_document_extractor_node (무변경)
  └─ DocumentComposer.compose(llm, template, tool_config, ...)
       ├─ _decide_slot_values  (무변경: LLM → {key: value|null} → SlotGroupPolicy)
       ├─ _replace_tokens      (무변경: html, filled, unfilled — HTML 경로·결과 계약용)
       ├─ _fill_docx (신규)    template.source_format == output_format == "docx" and filler 주입
       │    └─ DocxFiller.fill(source_path, slots, values) → DocxFillResult
       │          ├─ _load_document_xml (zipfile)
       │          ├─ _ParagraphIndex (lxml: w:p → w:t 세그먼트, 텍스트상자 제외)
       │          ├─ SampleSpanPolicy.find_span / split_span   (domain, 순수)
       │          ├─ _apply (run 분할: before | inserted | after, 형광펜·줄바꿈)
       │          └─ _rezip (document.xml 만 교체, 나머지 파트 바이트 복사)
       ├─ file_bytes is None → self._adapter.to_document(html, ...)  (기존 HTML 경로)
       └─ attachment_store.save → ComposeResult (계약 불변)
main.py DI: DocumentComposer(..., docx_filler=DocxFiller(logger))
```

### 2.2 Data Flow

```
values(dict) ──► DocxFiller.fill
                   for slot in slots (템플릿 순서):
                      paragraphs = index(document)          # 매 칸 재색인 (순차 의미)
                      for p in paragraphs (문서 순서):
                          span = SampleSpanPolicy.find_span(p.text, slot.sample_value)
                          if span: parts = split_span(p.lengths, span); _apply(p, parts, value)
                                   break
                      else: missing.append(slot.key)
                   if missing: return DocxFillResult(None, missing, "sample_not_found")
                   return DocxFillResult(bytes, [], None)
```

### 2.3 Dependencies

`lxml`(설치됨), 표준 `zipfile`/`io`/`copy`. 새 패키지 0.

---

## 3. Data Model

DB 변경 없음. 템플릿의 기존 필드만 읽는다: `source_file_ref`(보관 원본 경로), `source_format`, `slots[].sample_value`.

```python
# domain/document_extractor/policies.py
class SampleSpanPolicy:
    @staticmethod
    def find_span(text: str, sample: str) -> tuple[int, int] | None: ...
    @staticmethod
    def split_span(lengths: Sequence[int], span: tuple[int, int]) -> list[tuple[int, int, int]]:
        """[(segment_index, local_start, local_end), ...] — 비어 있는 조각은 제외."""

# infrastructure/document_extractor/docx_filler.py
@dataclass(frozen=True)
class DocxFillResult:
    file_bytes: bytes | None
    missing_keys: list[str]
    reason: str | None        # None | "sample_not_found" | "source_missing" | "parse_error"
```

### 3.1 매칭 규칙 (`find_span`)

- 공백(`str.isspace`)은 양쪽 모두 무시한다. `sample`의 비공백 문자 시퀀스를 `text`의 비공백 문자 시퀀스에서 찾는다.
- 반환 구간은 **원본 `text` 인덱스**: 시작 = 첫 매칭 문자의 위치, 끝 = 마지막 매칭 문자 위치 + 1. 사이의 공백은 구간에 포함된다(지워진다).
- `sample`의 비공백 문자가 0개면 None(매칭 불가 → 폴백).
- 첫 출현만 반환한다.

### 3.2 run 적용 규칙 (`_apply`)

매칭 구간이 걸친 세그먼트(`w:t`)들 중:
- **첫 세그먼트의 run**을 세 run으로 나눈다: `before`(구간 앞 글자, 원 rPr) / `inserted`(값, 원 rPr 복사) / `after`(첫 세그먼트에서 구간 뒤 글자, 원 rPr). 빈 before/after run은 만들지 않는다.
- **나머지 세그먼트**는 구간에 해당하는 글자만 지운다(빈 `w:t`는 남겨도 된다).
- `inserted` run:
  - 값 있음: 줄 단위로 `w:t`, 줄 사이 `w:br`. 모든 `w:t`에 `xml:space="preserve"`.
  - 공란(None/공백): `[미기재]` + rPr에 `<w:highlight w:val="yellow"/>`.
- 세그먼트가 `w:r` 직속이 아닌 경우(필드 코드 `w:instrText` 등)는 색인하지 않는다(→ 못 찾으면 폴백).

### 3.3 색인 대상 (`_ParagraphIndex`)

- `w:body` 아래 모든 `w:p`를 문서 순서로(표 셀 안 포함).
- `w:txbxContent`(텍스트 상자) 조상을 가진 단락은 제외.
- 단락 안 `w:r/w:t`와 `w:hyperlink/w:r/w:t`를 순서대로 세그먼트로.
- 단락 경계를 넘는 매칭은 하지 않는다.

---

## 4. API Specification

외부 API 변경 없음. 내부 계약만:

```python
class DocumentComposer:
    def __init__(self, conversion_adapter, attachment_store, logger, docx_filler=None): ...
    # compose() 시그니처·ComposeResult 불변

class DocxFiller:
    def __init__(self, logger: LoggerInterface): ...
    def fill(self, source_path: str, slots: list[TemplateSlot], values: dict,
             request_id: str) -> DocxFillResult: ...
```

`DocxFiller.fill`은 예외를 던지지 않는다(유일한 흡수 지점). `OSError`·`zipfile.BadZipFile`·`KeyError`(document.xml 없음)·`etree.XMLSyntaxError`를 잡아 `reason`과 함께 반환하고 `logger.warning(..., exception=e)`.

합성기 분기 조건(`_fill_docx`): `self._docx_filler is not None` and `template.source_format == "docx"` and `tool_config.output_format == "docx"`. 결과 `file_bytes is None`이면 `"DocumentComposer docx fill fallback"` warning(`reason`, `missing_keys`, `template_id`) 후 HTML 경로. 성공 시 info 로그 `path="docx_direct"`, HTML 경로는 `path="html"`.

---

## 5. UI/UX

변경 없음. 결과 문서가 원본 양식 모양으로 나온다.

---

## 6. Error Handling

| 상황 | 처리 | 산출 |
|---|---|---|
| 원본 파일 없음 | `reason=source_missing` warning | HTML 경로 |
| zip/XML 손상 | `reason=parse_error` warning(exception) | HTML 경로 |
| 칸 예시값 못 찾음(≥1) | `reason=sample_not_found`, `missing_keys` warning | HTML 경로 |
| 예시값 빈 칸 | 매칭 불가 → 위와 동일 | HTML 경로 |
| HTML 경로 MCP 실패 | 기존대로 전파(`McpConversionError`) | 실패 안내 |

---

## 7. Security Considerations

- `source_file_ref`는 서버가 저장 시 만든 경로(`{archive_dir}/{template_id}.docx`)이고 사용자 입력이 아니다. 그래도 읽기 전에 `Path(...).is_file()`만 확인하고 다른 검증은 하지 않는다(경로는 DB 출처, 템플릿 소유 검증은 기존 로딩에서 끝남).
- 값은 lxml 텍스트 노드로 넣어 XML 주입이 불가능하다. `{{ }}` 제거는 기존 `SlotValuePolicy.sanitize` 재사용.
- zip 해제는 메모리에서 `document.xml` 한 파트만 파싱. 압축 폭탄 대응은 원본이 업로드 시 크기 제한(`DocumentFilePolicy`)을 통과한 파일이라 추가 안 함.

---

## 8. Test Plan

### 8.1 Unit — domain (`tests/domain/document_extractor/test_sample_span_policy.py`)

| ID | 케이스 | 기대 |
|---|---|---|
| U-01 | 단순 포함 | 정확한 구간 |
| U-02 | 공백 차이(`"주식회사\n\t한빛상사"` vs `"주식회사 한빛상사"`) | 매칭, 사이 공백 포함 구간 |
| U-03 | 없음 / 빈 sample / 공백만 sample | None |
| U-04 | 여러 번 출현 | 첫 출현 |
| U-05 | `split_span` 세그먼트 3개 걸침 | `[(0,a,len0),(1,0,len1),(2,0,b)]` |
| U-06 | `split_span` 한 세그먼트 안 | 1개 조각 |
| U-07 | 길이 0 세그먼트가 섞임 | 빈 조각 제외 |

### 8.2 Unit — infra (`tests/infrastructure/document_extractor/test_docx_filler.py`)

픽스처는 테스트 안에서 zipfile로 최소 DOCX 생성(`[Content_Types].xml`·`_rels/.rels`·`word/document.xml`·`word/styles.xml`).

| ID | 케이스 | 기대 |
|---|---|---|
| I-01 | 한 run 안 예시값 | 값으로 교체, rPr(굵게·크기) 유지 |
| I-02 | 예시값이 rPr 다른 3개 run에 걸침 | 첫 run rPr로 값, 나머지 run 해당 글자 삭제 |
| I-03 | 앞뒤 글자 있는 run(`"연 5.8%"`의 `5.8%`) | before `연 ` / inserted / after 유지 |
| I-04 | 순차 겹침: 문서번호 `2026-여신-0042` → 연도 `2026` | 연도는 `2026년` 자리를 바꿈(문서번호 안 아님) |
| I-05 | 표 셀 안 단락 | 교체됨 |
| I-06 | 공란(None) | `[미기재]` run에 `w:highlight yellow` |
| I-07 | 여러 줄 값 | 줄 사이 `w:br` |
| I-08 | 텍스트 상자 안 예시값 | missing → `file_bytes None`, reason `sample_not_found` |
| I-09 | 못 찾는 칸 1개 | missing_keys = [그 key] |
| I-10 | 원본 파일 없음 / zip 아님 | `source_missing` / `parse_error`, 예외 없음 |
| I-11 | `document.xml` 외 파트 | 바이트 동일 |
| I-12 | 결과를 다시 열어 파싱 | 유효한 zip·XML |

### 8.3 Unit — composer (`test_composer.py` 추가)

| ID | 케이스 | 기대 |
|---|---|---|
| C-01 | docx 템플릿 + filler 성공 | adapter 미호출, 저장 바이트 = filler 결과 |
| C-02 | filler missing | adapter 호출(HTML), warning 로그에 missing_keys |
| C-03 | pdf 템플릿 | filler 미호출 |
| C-04 | filler 미주입 | 기존 동작(기존 테스트 전부 무변경 통과) |
| C-05 | 두 경로 `ComposeResult` filled/unfilled 동일 | 동일 |

### 8.4 E2E (M3)

`%TEMP%\wtr_e2e\run_inproc.py`로 여신심의서 에이전트 재실행 → 결과 DOCX와 원본 비교 스크립트:
- 파트 목록 동일, `styles.xml` 바이트 동일
- 표 3개·`w:tblStyle TableGrid` 유지, 제목 `w:sz 32` 유지
- 23칸 위치: 원본 예시값이 남아 있지 않음(공란은 `[미기재]`+highlight)
- 로그 `path="docx_direct"`

---

## 9. Clean Architecture

| 변경 | 레이어 | 근거 |
|---|---|---|
| `SampleSpanPolicy` | domain | 문자열 구간 계산만(외부 의존 없음) |
| `DocxFiller` | infrastructure | zip·lxml·파일 IO |
| `DocumentComposer._fill_docx` | infrastructure | 기존 composer 위치 |
| DI | `api/main.py` | DI 단일 집중 |

domain → infra 참조 없음. 함수 40줄·if 중첩 2단계 준수(`_apply`는 before/inserted/after 생성 헬퍼로 분리).

---

## 10. Coding Convention Reference

- `xml:space="preserve"` 필수(앞뒤 공백 보존)
- 네임스페이스 상수 `W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"`
- 로그: `logger.warning("DocumentComposer docx fill fallback", reason=..., missing_keys=..., exception=e)`
- 설계 주석 `# Design Ref: docx-format-preserving-fill §3.2`

---

## 11. Implementation Guide

### 11.1 File Structure

```
idt/src/domain/document_extractor/policies.py                         [수정: SampleSpanPolicy]
idt/src/infrastructure/document_extractor/docx_filler.py              [신규]
idt/src/infrastructure/document_extractor/composer.py                 [수정: docx_filler 인자, _fill_docx]
idt/src/api/main.py                                                   [수정: DocxFiller 주입]
idt/tests/domain/document_extractor/test_sample_span_policy.py        [신규]
idt/tests/infrastructure/document_extractor/test_docx_filler.py       [신규]
idt/tests/infrastructure/document_extractor/test_composer.py          [수정: C-01~05]
```

### 11.2 Implementation Order

1. `SampleSpanPolicy` (U-01~07)
2. `DocxFiller` (I-01~12)
3. composer 분기 + main.py DI (C-01~05)
4. 추출기 테스트 전체 + 백엔드 전체 회귀 FAILED diff
5. E2E 인프로세스 실측 + 서식 비교

### 11.3 Session Guide

| scope | 내용 | 종료 조건 |
|---|---|---|
| `module-1` | `SampleSpanPolicy` + `DocxFiller` + 테스트 | U·I 테스트 통과 |
| `module-2` | composer 분기·폴백·DI + C 테스트 + 전체 회귀 | FAILED diff 0 |
| `module-3` | E2E 실측·서식 비교 | SC-1~3 확인 |

규모가 작아 한 세션 진행 가능: `/pdca do docx-format-preserving-fill`.

---

## 12. Decision Record

| ID | 결정 | 사유 |
|---|---|---|
| D1 | 칸 순서·매 칸 재색인·첫 출현 | 프론트 토큰화와 같은 위치, 예시값 겹침 대응 |
| D1a | **2단계 치환** (Do 중 추가): 1단계는 사용자 정의 영역 문자 자리표시(`{i}`)로 위치만 잡고, 2단계에서 값으로 바꾼다 | 값을 바로 넣으면 다음 칸이 방금 넣은 값 안을 찾는다(문서번호 값 `2026-여신-0099` 안의 연도 `2026`). I-04 테스트가 실제로 잡았다. 프론트가 `{{key}}`로 토큰화하는 것과 같은 의미 |
| D2 | 단락 경계 넘는 매칭 없음 → 폴백 | 단락 병합은 서식 파괴 위험 |
| D3 | 첫 run 서식으로 값 삽입 | 예시값을 쓴 서식이 값의 서식 |
| D4 | 흡수 지점은 `DocxFiller.fill` 하나 | 폴백 판단을 한 곳에서, composer는 None 여부만 본다 |
| D5 | `document.xml`만 교체 | 스타일·번호·이미지 바이트 보존 |
| D6 | output_format도 docx일 때만 | PDF 출력 요청은 기존 변환 경로 |

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-11-07 | Initial — Option C |
