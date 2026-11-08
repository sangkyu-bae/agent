# docx-format-preserving-fill Completion Report

> **Feature**: docx-format-preserving-fill (Word 양식 서식 보존)
> **Project**: sangplusbot (Agent Builder) — idt
> **Period**: 2026-11-07 ~ 2026-11-08
> **Author**: 배상규
> **Status**: Completed (Match Rate 97%, Act 1회)
> **PR**: #105 (구현, 머지) · #106 (Act-1 + 분석·보고서)

---

## Executive Summary

### 1.1 Project Overview

문서추출기 양식의 원본이 Word(DOCX)이면 HTML 왕복 변환 없이 보관된 원본 DOCX의 예시값 자리에 값을 직접 넣어 서식을 그대로 보존한다. 직전 PR #104(공란 라벨 중복·날짜 묶음·고정 문구 반복)와 이어지는 여신심의서 E2E 후속 작업이다.

### 1.2 Results Summary

| 항목 | 계획 | 실제 |
|---|---|---|
| 기간 | 한 세션 | Plan·Design·Do 1세션 + Check·Act 1세션 |
| Match Rate | ≥ 90% | 93% → Act-1 후 **97%** |
| 신규 파일 | 2 + 테스트 2 | `docx_filler.py` + 테스트 2 (도메인 정책은 기존 파일에 추가) |
| 수정 파일 | 3 | `policies.py`, `composer.py`, `main.py` |
| 테스트 | — | 추출기 148건(신규 35) 통과, agent_builder 포함 1,498건 통과 |
| 회귀 | 0 | 백엔드 전체 53 failed = master 상시 실패와 동일 |
| 의존성·DB | 0 / 0 | 0 / 0 |

### 1.3 Value Delivered

| Perspective | Planned | Delivered |
|---|---|---|
| **Problem** | DOCX→HTML→DOCX 왕복으로 표 테두리·제목 크기·단락 서식이 사라지고 글꼴이 변환기 기본값으로 바뀐다 | 실 LLM E2E에서 원본 대비 zip 파트 목록 동일, `styles.xml` 바이트 동일, 표 3개 TableGrid 유지, 제목 크기 32 유지 |
| **Solution** | 보관 원본 DOCX에 칸 순서대로 예시값 자리를 찾아 직접 치환, 못 찾으면 HTML 폴백 | 그대로 구현. 예시값 겹침 때문에 2단계 치환(자리표시 → 값)으로 보강 |
| **Function/UX** | 올린 양식과 같은 모양, 공란은 `[미기재]`+형광펜, 기존 템플릿 재등록 없음 | 공란 3곳 노란 형광펜, 기존 템플릿 그대로 적용(DB 변경 0) |
| **Core Value** | 결재에 바로 올릴 수 있는 문서 | 서식이 원본과 같은 문서. 변환 MCP 호출이 빠져 생성 경로 단순화 |

## 1.4 Success Criteria Final Status

| SC | 상태 | 근거 |
|---|---|---|
| SC-1 원본과 서식 동일·23칸 원위치 | ✅ | E2E 비교(파트·스타일·표·크기), 직접 경로는 전 칸 배치 시에만 |
| SC-2 공란 형광펜 | ✅ | `test_unfilled_marker_highlight`, E2E 3곳 |
| SC-3 예시값 겹침 | ✅ | `test_sequential_overlap` + Act-1 `test_digit_sample_does_not_hit_earlier_placeholder` |
| SC-4 교차 run | ✅ | `test_sample_across_runs_uses_first_run_rpr` |
| SC-5 폴백 | ✅ | `test_missing_sample_falls_back_to_html`, Act-1 `fill_error`·`placeholder_lost` |
| SC-6 PDF 회귀 0 | ✅ | `test_pdf_template_never_calls_filler`, 전체 회귀 0 |

**6/6 충족**

## 1.5 Decision Record Summary

| 결정 | 준수 | 결과 |
|---|---|---|
| 원본 DOCX 직접 채움, PDF 제외 | ✅ | PDF·docx→pdf 출력은 기존 경로 |
| 못 찾은 칸 ≥1 → 문서 전체 HTML 폴백 | ✅ | Act-1에서 파싱 이후 예외·자리표시 소실도 폴백으로 확장 |
| 공란 `[미기재]`+형광펜 | ✅ | 스키마 순서 보강(Act-1 G3) |
| zipfile+lxml, 새 의존성 0 | ✅ | 파서 옵션 명시(G4) |
| Option C (domain 정책 + infra filler + 선택 주입) | ✅ | 미주입 시 기존 동작 동일 |
| D1a 2단계 치환 (Do 중 추가) | ✅ (Act-1 보강) | 값을 바로 넣으면 다음 칸이 그 값 안을 찾는 문제를 테스트가 잡음. 자리표시의 숫자 충돌(G1)은 Check에서 재현 후 수정 |

---

## 2. Related Documents

- Plan: `idt/docs/01-plan/features/docx-format-preserving-fill.plan.md`
- Design: `idt/docs/02-design/features/docx-format-preserving-fill.design.md`
- Analysis: `idt/docs/03-analysis/docx-format-preserving-fill.analysis.md`
- 선행: PR #104 (공란 표식·날짜 묶음·고정 문구), `idt/docs/archive/2026-08/document-template-extractor/`

---

## 3. Completed Items

| FR | 상태 |
|---|---|
| FR-01 원본 DOCX 직접 산출, MCP 미호출 | ✅ |
| FR-02 칸 순서·첫 출현 | ✅ (2단계 치환) |
| FR-03 공백 무시·교차 run | ✅ (단락 안) |
| FR-04 첫 run 서식 | ✅ |
| FR-05 줄바꿈·이스케이프 | ✅ (Act-1 `\r\n` 정규화·제어문자 제거) |
| FR-06 공란 형광펜 | ✅ |
| FR-07 못 찾으면 HTML 폴백 + key 로그 | ✅ |
| FR-08 원본 없음·파싱 실패 폴백 | ✅ (Act-1로 파싱 이후 예외까지) |
| FR-09 결과 계약 동일 | ✅ |
| FR-10 다른 파트 바이트 보존 | ✅ |
| FR-11 기존 템플릿 재등록 없음 | ✅ |

---

## 4. Incomplete Items (이월)

| 항목 | 성격 |
|---|---|
| G5 `w:ins`·`w:smartTag`·`w:sdt`·`w:fldSimple`·`w:customXml` 안 run 미색인 → 폴백 | 안전한 폴백, 콘텐츠 컨트롤 양식에서 폴백률 상승 가능 |
| G6 매칭 범위 사이 탭이 값 뒤로 이동 | 표시 미세 차이 |
| G7 빈 run 잔존 | 무해(FR-04 허용) |
| G8 `w:noBreakHyphen`·`w:sym` 미색인 → 폴백 | 안전한 폴백 |
| G9 값 `"{{}}"` 정제 후 빈 문자열 처리 | 경로 간 일관성 미확인 |
| G10 하이퍼링크 run·한 run 다중 `w:t` 테스트 | 테스트 보강 |
| Word 실제 열기 확인 | XML 검증만 함. 사용자 화면 확인 권장 |
| 폴백 발생 비율 관측 | 운영 로그(`path=html`, `reason`) 집계로 확인 |

---

## 5. Quality Metrics

| 축 | Check | Act-1 후 |
|---|:-:|:-:|
| Structural | 97 | 97 |
| Functional | 90 | 96 |
| Contract | 98 | 98 |
| Intent | 95 | 98 |
| Behavioral | 85 | 95 |
| **Overall** | 93 | **97** |

---

## 6. Lessons Learned

### Keep
- 예시값 겹침을 Plan 위험으로 미리 적고 테스트(I-04)로 만든 덕에 Do 중 첫 실패로 2단계 치환을 도입했다.
- Check에서 Critical 판정을 받자마자 12칸 픽스처로 재현해 확신을 얻은 뒤 고쳤다.
- gap-detector 브리프에 "읽을 파일 8개, 15회 안에 보고"를 넣으니 이번엔 한도에 걸리지 않았다.

### Problem
- 2단계 치환을 넣으면서 자리표시 자체가 예시값과 충돌할 수 있다는 점을 놓쳤다. 자리표시는 "어떤 입력과도 겹치지 않는 문자"여야 하는데 숫자를 넣었다.
- E2E는 칸 순서가 운 좋게 맞아 G1을 드러내지 못했다. 실데이터 1건 통과가 안전성을 보장하지 않는다.

### Try
- 치환 자리표시·센티널을 설계할 때 "입력 문자 집합과 교집합 0"을 테스트로 고정한다.
- 산출물 검증 단계에 "자리표시 잔존 0"처럼 결과 불변식 검사를 기본으로 둔다(이번 Act-1 안전망).

---

## 7. Next Steps

1. PR #106 머지
2. 로컬 dev 서버 재시작 후 화면에서 여신심의서 에이전트로 Word 결과를 열어 확인
3. `/pdca archive docx-format-preserving-fill` → worktree `wt/docx-fill` 정리
4. 이월 G5~G10은 운영 폴백 로그를 보고 소형 사이클로

---

## 8. Changelog

### v1.0.0 (2026-11-08)
- Word 양식은 원본 DOCX에 값을 직접 채워 서식 보존(`DocxFiller`), 실패 시 HTML 폴백
- 공란 `[미기재]` 노란 형광펜
- 자리표시 숫자 충돌 수정, 예외 흡수 확대, 형광펜 스키마 순서, 파서 옵션 명시

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-11-08 | 완료 보고서 |
