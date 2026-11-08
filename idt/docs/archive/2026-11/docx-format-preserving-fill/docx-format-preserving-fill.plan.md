# docx-format-preserving-fill Planning Document

> **Summary**: 문서추출기 양식의 원본이 Word(DOCX)이면 HTML 왕복 변환 없이 보관된 원본 DOCX의 예시값 자리에 값을 직접 넣어, 표 테두리·글꼴·글자 크기·단락 서식을 그대로 보존한다.
>
> **Project**: sangplusbot (Agent Builder) — idt 백엔드
> **Author**: 배상규
> **Date**: 2026-11-07
> **Status**: Draft

---

## Executive Summary

| Perspective | Content |
|-------------|---------|
| **Problem** | 추출기가 만든 Word 문서는 양식을 DOCX→HTML→DOCX로 왕복 변환해 만들어서, 표 테두리·제목 글자 크기·단락 서식이 사라지고 글꼴이 변환기 기본값(ＭＳ 明朝)으로 바뀐다. 여신심의서처럼 형식이 중요한 문서는 그대로 결재에 쓸 수 없다. |
| **Solution** | 원본 DOCX는 이미 템플릿마다 영구 보관되고 칸마다 예시값이 저장되어 있다. 원본 DOCX의 본문·표에서 예시값을 칸 순서대로 찾아 실제 값으로 바꾸고, 못 찾는 칸이 하나라도 있으면 문서 전체를 기존 HTML 경로로 돌린다. |
| **Function/UX Effect** | 사용자가 올린 양식과 같은 모양의 문서가 나온다. 공란 칸은 `[미기재]`에 노란 형광펜이 칠해져 사람이 채울 곳이 바로 보인다. 이미 등록된 템플릿도 재등록 없이 적용된다. |
| **Core Value** | S3(정형 문서 작성 보조)의 결과물을 "초안"이 아니라 결재에 바로 올릴 수 있는 문서로 만든다. 변환 MCP 호출이 빠지는 만큼 생성 시간과 외부 의존이 줄어든다. |

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | Word 양식이 HTML 왕복 변환으로 서식이 깨져 결재 문서로 쓸 수 없다. |
| **WHO** | P1(심사역 등 문서 작성 최종 사용자)과 P2(양식을 등록하는 에이전트 소유자). |
| **RISK** | 예시값이 여러 run에 쪼개져 있거나 서로 겹치면(문서번호 안의 연도) 엉뚱한 자리를 바꾼다. 못 찾은 칸을 조용히 남기면 예시값이 그대로 결재 문서에 나간다. |
| **SUCCESS** | E2E 여신심의서에서 원본과 결과의 표 수·테두리 스타일·글꼴·제목 크기가 같고, 23개 칸이 모두 원본 위치에 채워지며 공란은 형광펜 표식. 기존 PDF 경로·HTML 경로 회귀 0건. |
| **SCOPE** | M1 DOCX 직접 채움 엔진(순수 로직) → M2 합성기 분기·폴백 배선 → M3 E2E 실측 |

---

## 1. Overview

### 1.1 Purpose

원본이 DOCX인 문서추출기 템플릿은 원본 파일에 값을 직접 넣어 산출한다. LLM이 칸 값을 정하는 단계는 바꾸지 않는다.

### 1.2 Background

여신심의서 작성 에이전트 E2E(2026-11-06) 결과 문서에서 확인한 사실과 코드 근거:

| 구간 | 현재 상태 | 근거 |
|------|----------|------|
| 산출 경로 | `html_skeleton`에 값 치환 → MCP `html_to_docx` 변환 → 저장 | `idt/src/infrastructure/document_extractor/composer.py` `compose()` |
| 서식 손실 | 원본: 표 스타일 TableGrid·제목 32half-pt·런 34개 / 결과: 표 스타일 없음·크기 없음·빈 런 다수, 글꼴 ＭＳ 明朝 | E2E 산출물 XML 비교 |
| 원본 보관 | 템플릿 저장 시 `{archive_dir}/{template_id}.docx`로 영구 복사, 경로는 `source_file_ref` | `source_file_archiver.py` `promote()`, `DocumentTemplate.source_file_ref` |
| 칸 위치 정보 | 각 칸의 `sample_value`(원본에 있던 예시 문자열) 보존, 토큰화는 칸 순서대로 첫 출현 치환 | `TemplateSlot.sample_value`, 프론트 `tokenizeHtml` |
| 값 결정 | LLM이 `{key: value\|null}` JSON만 결정, 문서 변형은 순수 치환 | `composer._decide_slot_values` (D6) |
| 출력 포맷 | `tool_config.output_format`은 원본 포맷을 따름 | `document_template_binding.py` (결정 4) |
| 라이브러리 | `lxml` 설치됨, `python-docx` 미설치 | 로컬 venv 확인 |

사용자 확인 사항(2026-11-07):
- 대상: 원본이 DOCX인 템플릿만. PDF 템플릿은 기존 HTML 경로 유지.
- 못 찾는 칸이 있으면: **문서 전체를 기존 HTML 경로로 폴백**, 어느 칸 때문인지 로그.
- 공란 표시: **`[미기재]` + 노란 형광펜**.
- 구현: **zipfile + lxml, 새 의존성 없음**.

### 1.3 Related Documents

- 선행: `idt/docs/archive/2026-08/document-template-extractor/` (D2 토큰화·D3 원본 보관·D6 값 결정 분리·D8 공란 표식)
- 직전 수정: PR #104 (공란 라벨 중복·날짜 묶음·고정 문구 반복)
- 위키: `docs/wiki/backend/db/erd-document-tooling.md`, `docs/wiki/backend/patterns/degradation-vs-failure-boundary.md`, `docs/wiki/conventions/false-green-quality-gates.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] **M1 DOCX 직접 채움 엔진** (infrastructure, 순수 함수 위주)
  - DOCX(zip)의 `word/document.xml`을 lxml로 파싱, 본문 단락과 표 셀의 텍스트 런(`w:r/w:t`)을 문서 순서로 색인
  - 칸 순서대로 `sample_value`를 공백 무시 정규화 매칭으로 찾는다(여러 런에 걸친 경우 포함). 찾은 범위의 **첫 런 서식을 유지**하고 나머지 런의 해당 글자는 지운다
  - 치환 후 다음 칸은 갱신된 문서에서 다시 찾는다(기존 토큰화와 같은 순차 의미 — 예시값 겹침 대응)
  - 값: 텍스트 이스케이프, 여러 줄 값은 `w:br`로 줄바꿈
  - 공란: `[미기재]` 텍스트 + 런에 `w:highlight w:val="yellow"`
  - 결과: 바이트 + 못 찾은 칸 key 목록
- [ ] **M2 합성기 분기·폴백**
  - `DocumentComposer.compose`: `template.source_format == "docx"`이고 원본 파일이 있으면 M1 경로, 못 찾은 칸이 0개면 그 결과로 저장(MCP 호출 없음)
  - 원본 파일 없음·파싱 실패·못 찾은 칸 ≥ 1 → 기존 HTML 경로로 폴백, 사유와 칸 key를 warning 로그(`exception=` 포함)
  - 파일명·첨부 저장·`ComposeResult`(filled/unfilled) 계약 불변
- [ ] **M3 E2E 실측**: 여신심의서 에이전트로 재실행, 원본 대비 서식 동일성 비교 스크립트

### 2.2 Out of Scope

- PDF 템플릿 서식 보존(기존 HTML 경로 유지)
- 머리글·바닥글·각주·텍스트 상자·도형 안 텍스트(본문·표만 대상, 이 경우 못 찾으면 폴백)
- 칸 값에 따라 표 행을 늘리는 반복 영역
- 프론트 변경(추출·확정 UI 그대로)
- HTML 경로의 서식 개선(변환 MCP 쪽)

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | 원본이 DOCX이고 보관 파일이 있으면 원본 DOCX에 직접 값을 넣어 산출한다. MCP 변환을 호출하지 않는다 | High |
| FR-02 | 칸은 템플릿 `slots` 순서대로 처리하고, 각 칸은 `sample_value`의 **현재 문서 기준 첫 출현**을 바꾼다 | High |
| FR-03 | 매칭은 공백(스페이스·탭·줄바꿈) 차이를 무시하고, 여러 런에 걸친 텍스트도 찾는다 | High |
| FR-04 | 치환 결과는 매칭 범위 첫 런의 서식(`w:rPr`)을 따른다. 범위 안 나머지 런의 해당 글자는 지우고 빈 런은 남겨도 된다 | High |
| FR-05 | 값의 줄바꿈은 `w:br`로, XML 특수문자는 이스케이프한다 | Medium |
| FR-06 | 공란 칸은 `[미기재]` + 노란 형광펜(`w:highlight yellow`)으로 쓴다 | High |
| FR-07 | 칸 하나라도 못 찾으면 문서 전체를 기존 HTML 경로로 산출하고, 못 찾은 key를 warning 로그로 남긴다 | High |
| FR-08 | 원본 파일 없음·zip/XML 파싱 실패도 FR-07과 같이 폴백한다(예외 전파 금지 — 쓸 수 있는 결과가 있으므로 degraded) | High |
| FR-09 | `ComposeResult`의 `filled_slots`·`unfilled_labels`·파일명은 경로와 무관하게 같은 의미다 | High |
| FR-10 | 원본 DOCX의 `document.xml` 외 파트(styles·numbering·theme·media)는 바이트 그대로 유지한다 | High |
| FR-11 | 기존 템플릿은 재등록 없이 적용된다(DB 변경 없음) | High |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement |
|----------|----------|-------------|
| 서식 보존 | E2E 원본 대비 표 수·표 스타일·제목 런 크기·문서 파트 목록 동일 | 비교 스크립트 |
| 호환 | PDF 템플릿·HTML 폴백 경로·기존 composer 테스트 회귀 0 | FAILED 목록 diff |
| 성능 | DOCX 경로 합성 시간 ≤ HTML 경로(변환 MCP 왕복 제거) | 로그 elapsed 비교 |
| 아키텍처 | 매칭·치환 규칙은 순수 함수로 분리, domain은 lxml 미의존 | verify-architecture |
| 의존성 | 새 패키지 0 | pyproject diff |

---

## 4. Success Criteria

- [ ] SC-1: E2E 여신심의서 결과 DOCX가 원본과 표 3개·TableGrid 스타일·제목 크기(32)·파트 목록이 같고, 23개 칸이 모두 원래 위치에 채워진다
- [ ] SC-2: 공란 칸은 `[미기재]` 텍스트에 노란 형광펜이 있다
- [ ] SC-3: 예시값 겹침(문서번호 `2026-여신-0042` vs 연도 `2026`)에서 연도 칸이 문서번호 안을 바꾸지 않는다
- [ ] SC-4: 여러 런에 걸친 예시값을 찾아 첫 런 서식으로 바꾼다
- [ ] SC-5: 못 찾는 칸이 있으면 HTML 경로로 폴백하고 key가 로그에 남는다(산출 성공)
- [ ] SC-6: PDF 템플릿은 기존 경로 그대로(회귀 0)
- [ ] 백엔드 전체 회귀 FAILED diff 0, 수정 파일 ruff 신규 오류 0

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Word가 텍스트를 임의로 런 분할(맞춤법·서식 경계) | High | High | 단락 단위 텍스트 색인 + 런 오프셋 매핑으로 교차 런 매칭(FR-03), 테스트에 분할 런 픽스처 |
| 예시값 겹침으로 엉뚱한 자리 치환 | High | Medium | 칸 순서 순차 치환 + 매 칸 재색인(FR-02). 프론트 토큰화와 같은 순서이므로 HTML 경로와 결과 위치가 같다 |
| 예시값이 단락 경계를 넘음(여러 줄 서술 칸) | Medium | Medium | 단락을 넘는 매칭은 지원하지 않고 폴백(FR-07). E2E 심사 의견 칸이 해당하는지 M3에서 확인 |
| 폴백이 조용히 늘어 서식 보존이 사실상 안 됨 | Medium | Medium | 폴백 사유·key warning 로그 + E2E에서 DOCX 경로 사용 여부를 단언 |
| 첫 런 서식이 라벨 서식(굵게 등)일 때 값도 굵어짐 | Low | Low | 예시값 범위의 첫 런만 쓰므로 라벨과 분리돼 있으면 영향 없음. 관찰 항목 |
| 원본 파일 디스크 유실(볼륨 미마운트) | Medium | Low | FR-08 폴백 |

---

## 6. Impact Analysis

### 6.1 Changed Resources

| Resource | Type | Change |
|----------|------|--------|
| `DocumentComposer.compose` | Infrastructure | DOCX 분기 + 폴백 |
| 신규 `docx_filler.py` (infrastructure/document_extractor) | Infrastructure | lxml 기반 채움 엔진 |
| 신규 순수 매칭 규칙(위치 미정 — Design에서 domain 정책 vs infra 내부 결정) | Domain/Infra | 공백 정규화 매칭·순차 치환 |
| composer DI(`main.py`) | Wiring | 원본 경로 해석에 `source_file_ref` 사용 — 새 의존 주입 여부 Design에서 결정 |

### 6.2 Current Consumers

| Resource | Operation | Code Path | Impact |
|----------|-----------|-----------|--------|
| `DocumentComposer.compose` | CALL | `workflow_compiler._create_document_extractor_node` | None (시그니처 불변) |
| `ComposeResult` | READ | `_render_compose_summary` | None |
| `DocumentConversionAdapter.to_document` | CALL | composer HTML 경로 | DOCX 경로에선 미호출, PDF·폴백은 그대로 |
| `source_file_ref` | READ | (신규) composer | 기존엔 저장만 하고 런타임 미사용 |

---

## 7. Architecture Considerations

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| DOCX 처리 | zipfile+lxml / python-docx | zipfile+lxml | 사용자 확정, 새 의존성 0. 런 교차 매칭은 어느 쪽이든 직접 구현 |
| 못 찾은 칸 | HTML 폴백 / 칸만 공란 / 실패 | HTML 폴백 | 사용자 확정. 예시값이 결재 문서에 남는 위험 차단 |
| 공란 표시 | 표식+형광펜 / 형광펜만 / 표식만 | 표식+형광펜 | 사용자 확정. 기존 D8 의도 유지 |
| 매칭 의미 | 칸 순서 순차 첫 출현 | 고정 | 프론트 토큰화와 같은 위치를 보장 |

---

## 8. Convention Prerequisites

- 백엔드 규칙: 함수 40줄·if 중첩 2단계, logger 사용(print 금지), warning에 `exception=` 전달
- TDD: 픽스처 DOCX는 테스트에서 zipfile로 최소 생성(바이너리 커밋 최소화)
- 회귀 증명: `uv run python -m pytest` 전체 FAILED 목록 diff

---

## 9. Next Steps

1. [ ] `/pdca design docx-format-preserving-fill` — 3안 비교(매칭 규칙 위치·DI 방식)
2. [ ] 구현 M1 → M2 → M3

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-11-07 | Initial draft — 사용자 확인 4항목 반영 | 배상규 |
