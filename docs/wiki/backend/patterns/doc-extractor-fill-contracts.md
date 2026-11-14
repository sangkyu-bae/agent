---
title: 문서추출기 값 채움 계약 — DOCX 원본 직접 채움·자리표시·공란·날짜 묶음
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/src/infrastructure/document_extractor/docx_filler.py (_placeholder PUA, _fill_root 2단계, reason 5종, _AFTER_HIGHLIGHT, _PARSER)
  - idt/src/infrastructure/document_extractor/composer.py (_fill_docx 조건, path=docx_direct|html 로그, _today_block)
  - idt/src/domain/document_extractor/policies.py (UnfilledSlotPolicy.UNFILLED_MARKER, SlotGroupPolicy, COMPOSE_GUIDELINES 규칙 6~8)
  - 8a34baa feat(doc-extractor) Word 양식 원본에 값을 직접 채워 서식 보존 (PR #105)
  - 53d8d80 fix(doc-extractor) 자리표시 숫자 충돌·예외 흡수·형광펜 순서 (PR #106, Act-1 G1~G4)
  - e19b5e3 fix(doc-extractor) 공란 표식 라벨 중복·날짜 반쪽 채움·고정 문구 반복 (PR #104)
  - idt/docs/archive/2026-11/docx-format-preserving-fill/docx-format-preserving-fill.analysis.md (G1 재현·Act-1)
  - idt/docs/archive/2026-11/docx-format-preserving-fill/docx-format-preserving-fill.report.md (Lessons, 이월 G5~G10)
confidence: 0.85
version: 1
created: 2026-11-14
updated: 2026-11-14
verified_at: 2fc45c5
---

> 읽는 시점: **문서추출기 합성(`DocumentComposer`)·`DocxFiller`를 고치기 전, 채움 결과에 반쪽 날짜·라벨 중복·
> 엉뚱한 칸 값 소실이 보일 때, 그리고 "원본 문자열 안에서 찾아 바꾸기"를 2단계 이상으로 하는 코드를 어디서든 새로 짤 때.**

## 문제

1. 문서추출기 출력은 원래 DOCX → HTML skeleton → (MCP) DOCX 왕복이라 표 테두리·제목 크기·글꼴이 사라졌다.
2. 원본 DOCX의 **예시값 자리를 찾아 값을 직접 넣는** 방식으로 바꾸자, 값을 바로 넣으면 다음 칸이 방금 넣은 값 안을 찾는 겹침이 생겼다(문서번호 값 안의 연도 등).
3. 2단계 치환(자리표시 → 값)으로 고쳤는데 **자리표시 자체에 숫자**(`PUA+번호+PUA`)가 들어 있어, 뒤 칸의 숫자만인 예시값(`"1"`, `"11"`, `"06"`)이 자리표시 안 숫자를 찾아 들어갔다. 앞 칸 값이 사라지고 PUA 문자가 문서에 남았는데 **결과는 성공으로 반환**됐다(Check G1 Critical, 12칸 픽스처로 재현). 실 LLM E2E 1건은 칸 순서가 운 좋게 맞아 통과했다.
4. (PR #104) 공란 표식 `[미기재] {라벨}`이 양식의 기존 라벨과 중복되고, 년/월/일처럼 한 라벨을 여러 칸으로 쪼갠 날짜가 반쪽만 채워졌으며("[미기재]년 11월 [미기재]일"), LLM이 양식 고정 문구("연", "개월")를 값에 반복했다.

## 검증된 사실

### DOCX 직접 채움 (`DocxFiller`)
- **적용 조건**: `docx_filler` 주입됨(main.py) **AND** `template.source_format == "docx"` **AND** `tool_config.output_format == "docx"`. PDF 원본이나 docx→pdf 출력은 기존 HTML+MCP 경로 그대로다. 원본 경로는 `document_template.source_file_ref`.
- **2단계 치환**: 1단계는 칸 순서대로 예시값 첫 출현 위치에 자리표시만 놓고, 2단계에서 자리표시를 값으로 바꾼다.
- **자리표시 = 칸마다 PUA 문자 1개** (`chr(0xE000 + i)`, 숫자 없음). 예시값에는 PUA 문자가 없으므로 어떤 예시값과도 겹치지 않는다. 칸 상한(30)은 PUA 범위 안이다.
- **결과 불변식 안전망**: 2단계 뒤 소비되지 않은 자리표시가 하나라도 있으면 `placeholder_lost`로 실패 처리 → HTML 폴백. "성공처럼 보이는 손상"을 내보내지 않는다.
- **전부 아니면 폴백**: 못 찾은 칸이 1개라도 있으면 문서 전체를 HTML 경로로 보낸다. `reason`은 `source_missing`·`parse_error`·`fill_error`·`sample_not_found`·`placeholder_lost` 5종이며 composer가 `docx fill fallback` warning에 `reason`·`missing_keys`를 남기고, 완료 로그에 `path=docx_direct|html`이 찍힌다 → 운영 폴백률은 이 두 로그로 집계한다.
- **예외 흡수 지점은 `fill()` 한 곳**: 파싱 이후 단계 전체를 감싸 `fill_error`로 폴백(`exception=e` warning). 값에 섞인 XML 금지 제어문자(PDF 근거에서 유입)는 lxml `ValueError`를 내므로 제거하고 `\r\n`→`\n` 정규화.
- **형광펜 삽입 순서**: `w:highlight`는 CT_RPr 스키마 순서상 `u`·`shd`·`lang`·…·`rPrChange` **앞**에, 그리고 `w:` 외 네임스페이스 요소(`w14:*`) **앞**에 넣어야 Word가 손상으로 보지 않는다(`_AFTER_HIGHLIGHT`).
- 업로드 XML 파서는 `XMLParser(resolve_entities=False, no_network=True)` 명시(lxml 6.1.2 기본도 차단하지만 명시).
- 바꾸는 파트는 `word/document.xml`뿐이고 나머지 zip 파트는 바이트 그대로(E2E에서 `styles.xml` 바이트 동일·표 TableGrid·제목 크기 유지 확인). 텍스트 상자 안 단락은 색인하지 않는다.
- **알려진 폴백 원인(이월, 안전)**: `w:ins`·`w:smartTag`·`w:sdt`·`w:fldSimple`·`w:customXml` 안 run, `w:noBreakHyphen`·`w:sym`은 색인되지 않아 HTML 폴백 — 콘텐츠 컨트롤을 쓰는 양식은 폴백률이 높을 수 있다. Word에서 실제로 여는 확인은 하지 않았다(XML 검증만).

### 합성 규칙 (PR #104)
- 공란 표식은 `[미기재]`만 쓰고(`UNFILLED_MARKER`), 어느 슬롯인지는 `data-unfilled` 속성으로 남긴다. DOCX 직접 경로에선 `[미기재]` + 노란 형광펜.
- **같은 라벨 묶음은 전부 채우거나 전부 비운다** — 프롬프트 규칙 7만으로는 지켜지지 않으므로 `SlotGroupPolicy.blank_partial_groups`가 LLM 응답 뒤 결정적 후처리로 강제한다(라벨 strip 기준 그룹, 2개 이상일 때만).
- 프롬프트 user 블록 맨 앞에 `[기준 정보] 오늘 날짜: YYYY-MM-DD (요일)`을 주입한다. 작성일·심의일 성격 칸은 다른 날짜가 명시되지 않으면 오늘로 채우고, 과거 사건 날짜는 근거에 있을 때만(규칙 6).
- value 칸은 슬롯 목록에 `예시값 형식`을 보여줘 고정 문구 반복을 막는다(규칙 8).

## 다음에 적용하는 법

1. **치환 자리표시·센티널은 "입력 문자 집합과 교집합 0"으로 설계하고 테스트로 고정**한다(이번 G1의 직접 교훈). 숫자·영문·괄호처럼 사용자 값에 나올 수 있는 문자를 자리표시에 넣지 않는다.
2. 다단계 변환 결과에는 **결과 불변식 검사**(자리표시 잔존 0 등)를 기본으로 두고, 위반 시 성공을 반환하지 말고 폴백·실패로 보낸다.
3. 실데이터 E2E 1건 통과는 순서 의존 결함을 증명하지 못한다 — 겹침·숫자 예시값 같은 적대적 픽스처를 별도로 만든다.
4. LLM에게 "묶음 일관성"류 규칙을 줬으면 같은 규칙을 결정적 후처리로도 강제한다(프롬프트는 2차 방어선, [[llm-output-trust-boundary]]).
5. 폴백 경로를 넓히는 수정(새 XML 요소 색인)은 운영 로그의 `reason` 분포를 보고 결정한다. 실패를 흡수하는 범위는 [[degradation-vs-failure-boundary]] 기준(쓸 수 있는 HTML 결과가 있으므로 degraded).
6. 저장 양식 데이터·조회 키·예시값 노출 정책은 [[erd-document-tooling]].
