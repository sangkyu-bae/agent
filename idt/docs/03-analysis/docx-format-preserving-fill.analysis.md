# docx-format-preserving-fill Gap Analysis

> **Feature**: docx-format-preserving-fill
> **Date**: 2026-11-07
> **Analyzer**: gap-detector(정적) + 세션 런타임 검증·재현
> **Code**: master `6d5577b` (PR #105 머지)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | Word 양식이 HTML 왕복 변환으로 서식이 깨져 결재 문서로 쓸 수 없다. |
| **WHO** | P1(문서 작성 최종 사용자)과 P2(양식 등록자). |
| **RISK** | 예시값 교차 run·겹침, 못 찾은 칸의 조용한 잔존. |
| **SUCCESS** | 원본과 표·스타일·제목 크기·파트 동일, 23칸 원위치, 공란 형광펜, 회귀 0. |
| **SCOPE** | M1 매칭 정책 + DocxFiller → M2 합성기 분기·폴백·DI → M3 E2E |

---

## Strategic Alignment

핵심 문제(서식 손실)는 해결됐다. 실 LLM E2E에서 `path=docx_direct`로 생성됐고, 원본 대비 zip 파트 목록 동일·`styles.xml` 바이트 동일·표 3개 TableGrid 유지·제목 크기 32 유지·공란 3곳 형광펜을 확인했다.

다만 **조용한 손상 경로 1건(G1, Critical, 세션 재현 완료)**이 있다. 계획의 핵심 위험("못 찾은 칸을 조용히 남기면 예시값이 결재 문서에 나간다")과 같은 계열이라 Report 전에 처리해야 한다.

### Success Criteria Status

| SC | 상태 | 근거 |
|----|------|------|
| SC-1 서식 동일·23칸 | ✅ | E2E 비교 결과, `docx_filler.py:93-99`(전 칸 배치 시에만 직접 경로) |
| SC-2 공란 형광펜 | ✅ | `docx_filler.py:190-195,225-234`, `test_unfilled_marker_highlight`, E2E 3곳 |
| SC-3 예시값 겹침 | ⚠️ | 2단계 치환으로 I-04 통과. 단, 숫자만인 예시값이 자리표시 안 숫자와 충돌(G1) |
| SC-4 교차 run | ✅ | `test_sample_across_runs_uses_first_run_rpr` |
| SC-5 폴백 | ✅ | `test_missing_sample_falls_back_to_html`. 단, 파싱 이후 예외는 폴백되지 않음(G2) |
| SC-6 PDF 회귀 0 | ✅ | `test_pdf_template_never_calls_filler`, 전체 회귀 53 failed = master 기준 동일 |

### Decision Record Verification

| ID | 준수 | 비고 |
|----|:--:|------|
| D1 칸 순서·재색인·첫 출현 | ✅ | |
| D1a 2단계 치환 | ⚠️ | 자리표시에 숫자가 들어가 G1 발생 |
| D2 단락 경계 없음 | ✅ | |
| D3 첫 run 서식 | ✅ | |
| D4 흡수 지점 1곳 | ⚠️ | 파일 로딩·파싱 예외만 흡수(G2) |
| D5 document.xml만 교체 | ✅ | |
| D6 docx→docx만 | ✅ | 추가 테스트 포함 |

---

## 1. Match Rate

| 축 | 점수 |
|---|:-:|
| Structural | 97% |
| Functional | 90% |
| Contract | 98% |
| Intent | 95% |
| Behavioral | 85% |
| **Overall** | **약 93%** |

런타임: 추출기 테스트 141건 통과, 백엔드 전체 회귀 0건, E2E 서식 동일(위).

---

## 2. Gap List

| # | 심각도 | 확신 | 내용 | 조치 후보 |
|---|---|:-:|---|---|
| **G1** | **Critical** | 재현됨 | 자리표시 `{i}` 안의 숫자를 뒤 칸의 숫자만인 예시값(`"1"`, `"11"`, `"06"`)이 찾아 들어간다. 앞 칸 값이 사라지고 사용자 정의 문자가 문서에 남는데, 결과는 성공으로 반환돼 폴백도 안 된다. 12칸 픽스처로 재현(A0 값 소실, 잔여 PUA, 원래 `1` 자리는 미치환) | 숫자 없는 자리표시(칸마다 PUA 코드포인트 1개 `chr(0xE000+i)`) + 2단계 후 모든 자리표시 소비 검증, 실패 시 `sample_not_found` 폴백. 회귀 테스트 추가 |
| **G2** | Important | 80% | `fill`이 파싱 이후 예외(값의 XML 금지 제어문자 → lxml `ValueError`, rPr 안 주석 노드 등)를 흡수하지 않아 HTML 폴백 대신 합성 실패가 된다(D4·FR-08 위반) | 1~3단계를 감싸 예외 시 warning(`exception=e`) + `reason="fill_error"` 폴백. 제어문자 값 테스트 |
| **G3** | Important | 60% | 형광펜 삽입 위치: `rPrChange`(CT_RPr 마지막 자식)와 비 `w:` 네임스페이스 확장 요소(`w14:*`) 뒤에 붙을 수 있어 Word가 손상으로 볼 위험 | `_AFTER_HIGHLIGHT`에 `rPrChange` 추가, 비 `w:` 요소 앞에 삽입 |
| G4 | Minor | 확인됨 | 사용자 업로드 XML 기본 파서 사용. lxml 6.1.2라 외부 엔티티는 기본 차단이지만 명시 파서가 안전 | `XMLParser(resolve_entities=False, no_network=True)` 한 줄 |
| G5 | Minor | 75% | `w:ins`·`w:smartTag`·`w:sdt`·`w:fldSimple`·`w:customXml` 안 run 미색인 → 폴백(안전) | 이월 |
| G6 | Minor | 70% | 매칭 범위 사이의 탭이 값 뒤로 밀림 | 이월 |
| G7 | Minor | 70% | 빈 run 잔존(FR-04 허용) | 이월 |
| G8 | Minor | 60% | `w:noBreakHyphen`·`w:sym` 미색인 → 폴백(안전) | 이월 |
| G9 | Minor | 미확인 | 값 `"{{}}"`이 정제 후 빈 문자열이면 공란 표식 대신 빈 run | 이월 |
| G10 | Minor | 90% | 테스트 공백: 하이퍼링크 run, 한 run 다중 `w:t`, 뒤따르는 tab/br, `w:u`와 형광펜 순서, document.xml 없는 zip, 손상 XML, C-04 명시 테스트 | G1~G3 수정 시 일부 보강 |

---

## 3. Test Coverage (Design ID → 테스트)

U-01~07, I-01~12, C-01·02·03·05 모두 대응 테스트 있음. C-04(미주입=기존 동작)는 기존 합성기 테스트로 암묵 검증. I-10은 `KeyError`·XML 오류 케이스 없음.

---

## 4. Act-1 결과 (Critical+Important 수정)

| # | 조치 | 검증 |
|---|---|---|
| G1 | 자리표시를 칸마다 PUA 문자 1개(`chr(0xE000+i)`, 숫자 없음)로 변경. 2단계 후 자리표시가 하나라도 소비되지 않으면 `placeholder_lost`로 HTML 폴백(성공으로 내보내지 않음) | 재현 픽스처(12칸 + 숫자 예시값 `1`) 테스트 통과, 안전망 테스트 추가 |
| G2 | 파싱 이후 단계 전체를 감싸 예외 시 warning(`exception=`) + `fill_error` 폴백. 값의 XML 금지 제어문자 제거, `\r\n`→`\n` | 제어문자 값·예상 밖 예외 테스트 통과 |
| G3 | `rPrChange`를 형광펜 뒤 요소로 추가, `w:` 외 네임스페이스(w14 등) 요소 앞에 삽입, 주석 노드 건너뜀 | `w:u`/`rPrChange` 순서·`w14:ligatures` 순서 테스트 통과 |
| G4 | `XMLParser(resolve_entities=False, no_network=True)` 명시 | 외부 엔티티 테스트 통과(lxml 6.1.2는 기본도 차단), document.xml 없는 zip 테스트 추가 |

검증: 추출기 테스트 148건(+Act-1 8건) 통과, agent_builder 포함 1,498건 통과, 린트 통과. 실 LLM E2E 재실행 `path=docx_direct`, 파트·`styles.xml` 동일, 표 3개 TableGrid·제목 크기 32 유지, 형광펜 3곳, PUA 잔존 0.

Overall: **약 97%** (Functional 96 · Behavioral 95, 나머지 동일). Minor G5~G10은 이월(전부 안전한 폴백 또는 무해).

## Version History

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-11-07 | gap-detector 정적 분석 + G1 세션 재현 |
| 0.2 | 2026-11-07 | Act-1: G1~G4 수정, E2E 재확인 |
