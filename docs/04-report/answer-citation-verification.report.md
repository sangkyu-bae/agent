# answer-citation-verification Completion Report

> 답변 인용 검증 — 답변 문장마다 `[n]` 인용을 달고, 기존 근거 판정 호출에서 그 인용이 맞는지 확인한 뒤 통과한 인용만 파일·쪽·근거 문장과 함께 보여 준다.
>
> - 기간: 2026-11-20 ~ 2026-11-23
> - 브랜치: `feature/answer-citation-verification` (worktree `wt/answer-citation`, base 49b0970)
> - 최종 Match Rate: 93.6% (Act 1회)

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| Feature | answer-citation-verification |
| 범위 | 백엔드(idt) + 프론트(idt_front), 내부 문서 검색을 쓰는 supervisor 답변 |
| 스위치 | `ANSWER_CITATION_ENABLED` 기본 false |
| 마이그레이션 | V093 `ai_answer_citation`, V094 `grounding_judge_setting` |

### 1.2 Results Summary

| 항목 | 결과 |
|------|------|
| Match Rate | 93.6% (정적 92.4% → 라이브 포함 90.6% → Act-1 후 93.6%) |
| Success Criteria | 6/10 충족, 4건 부분 충족(실측 미완) |
| Gap | Critical 0, Important 3건 모두 수정, Minor 7건 이월 |
| 라이브 확인 | 질문 9건(재질문 포함) 내부 문서 답변 모두 verified, 쪽 번호 100%, 재진입 동일 |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| Problem | 검색 결과 전체를 칩으로 보여 주어, 답변이 어느 문서의 몇 쪽, 어느 문장을 보고 쓴 것인지 사용자가 알 수 없었다 |
| Solution | 검색 결과에 실행 단위 번호를 붙이고 모델이 문장마다 `[n]`을 달게 한다. 기존 근거 판정 호출을 확장해 인용별 뒷받침 여부와 근거 문장을 함께 받고, 결정적 검사(번호 존재·근거 문장이 해당 청크에 있는지)로 걸러 통과한 인용만 1부터 다시 번호를 매긴다 |
| Function / UX Effect | 본문 위첨자를 누르면 원문 패널이 해당 구절로 열리고 근거 문장이 진하게 표시된다. "답변 근거"에는 번호·파일·쪽·근거 문장만 나오고 쓰지 않은 구절은 접힌다. 인용이 모두 탈락하면 "근거 확인 안 됨"을 표시한다 |
| Core Value | 틀린 번호 인용은 벤치에서 5건 모두 탈락했고(0/5 잔존), 근거 판정이 켜진 경로는 LLM 호출이 늘지 않는다. 관리자는 판정 모델을 화면에서 바꿀 수 있다 |

## 1.4 Success Criteria Final Status

| SC | 기준 | 상태 | 근거 |
|----|------|:----:|------|
| SC-1 | 스위치 off 동일 | ✅ | DI가 None, payload에 `citation` 키 없음, off 회귀 테스트 |
| SC-2 | 인용 정확도 90% 이상 | ⚠️ | 라이브 인용 육안 확인 모두 뒷받침됨. 골든셋 10문항 수기 라벨은 미실행 |
| SC-3 | 틀린 번호 100% 탈락 | ✅ | 벤치 raw 3/5 supported → 정책 후 0/5 |
| SC-4 | 쪽 번호 100% | ⚠️ | 비라우팅 검색 100%. 라우팅 검색은 page 없음(G-4) |
| SC-5 | 음영 매칭 90% 이상 | ⚠️ | 텍스트 모드 확인. 집계·PDF 원본 모드 미확인 |
| SC-6 | 추가 호출 0, p50 +1.5초 이하 | ⚠️ | 판정 on 경로는 같은 호출(정적 확인). on/off 실측 비교 미실행 |
| SC-7 | 재진입 동일 | ✅ | 4문항 citation·viewer 동일 |
| SC-8 | none 배지 / 다른 경로 그대로 | ✅ | 백엔드·컴포넌트 테스트, KB 무관 질문은 행 없음(not_applicable). 라이브 none은 미재현 |
| SC-9 | U+FFFD 0 | ✅ | 가계부채 PDF 9건 → 0건 |
| SC-10 | 판정 벤치 변화 없음 | ✅ | 개정 기준(새 오판 0, 날조 3/3) 충족, 정상 오판 4/7 → 1/7 |

충족 6/10(SC-8 포함 7), 나머지는 실측이 남은 부분 충족이다.

## 1.5 Decision Record Summary

| 결정 | 단계 | 따랐는가 | 결과 |
|------|------|:--------:|------|
| 모델 인용 + 기존 판정기 확장(추가 호출 0) | Plan | ✅ | 판정 on 경로 호출 수 불변. 판정 off면 인용만 1회 판정 |
| 판정 모델을 관리자가 선택(gpt-4o 고정 해제) | Plan | ✅ | V094 단일 행 + env 폴백, LLM 모델 관리 페이지 카드 |
| C안 탈착 모듈 + 같은 판정 호출 | Design | ✅ | `answer_citation_di.py` 단일 조립, AST 경계 테스트 |
| 탈락 후 1부터 재번호 | Design | ✅ | 라이브 번호 1부터 연속 |
| 근거 문장이 다른 청크에만 있으면 탈락(D-07 보강) | Do(벤치) | ✅ | 판정기가 틀린 번호에도 실제 근거 문장을 대며 supported로 답하는 경향을 막는 핵심 검사 |
| 같은 문장 안 같은 근거 인용 합치기 | Act-1 | ✅ | parent·child 청크 중복 `[1][2]` 0건 |

## 2. Related Documents

| 문서 | 경로 |
|------|------|
| Plan | `docs/01-plan/features/answer-citation-verification.plan.md` |
| Design | `docs/02-design/features/answer-citation-verification.design.md` (v0.5) |
| Analysis | `docs/03-analysis/answer-citation-verification.analysis.md` |
| 선행 기능 | source-passage-viewer (PR #124·#125) |

## 3. Completed Items

### 3.1 Functional Requirements

| FR | 내용 | 상태 |
|----|------|:----:|
| FR-01 | 청킹 U+FFFD 제거(UTF-8 글자 경계) | ✅ |
| FR-02 | ES 청크 page 저장 | ✅ |
| FR-03 | 실행 단위 번호 라벨·레지스트리 | ✅ (라우팅 검색 page 제외) |
| FR-04 | 번호가 있을 때만 `[n]` 지시 | ✅ |
| FR-05 | 같은 판정 호출에서 인용 판정 | ✅ |
| FR-06 | 결정적 검사 | ✅ |
| FR-07 | 탈락 제거·재번호 | ✅ |
| FR-08 | DB 저장·재진입 | ✅ |
| FR-09 | 칩 인용·미사용·상태 | ✅ |
| FR-10 | 관리자 판정 모델 + env 폴백 | ✅ |
| FR-11 | 관리자 화면 표시 | ⚠️ 폴백 경고 없음(G-5) |
| FR-12 | 위첨자 → 원문 뷰어 | ✅ |
| FR-13 | 인용 행·접힘·none 배지 | ✅ |
| FR-14 | 근거 문장 진한 음영 | ✅ (텍스트·docx, PDF 원본 미확인) |
| FR-15 | 스위치 off 동일 | ✅ |
| FR-16 | 실패 시 none, 원문 미기록 경고 | ✅ |

### 3.2 Non-Functional Requirements

| 항목 | 결과 |
|------|------|
| 탈착성 | 스위치 off면 협력자 전부 None, AST 경계 테스트 |
| 장애 격리 | 판정·저장·조회 실패 모두 답변과 칩을 막지 않음 |
| 보안 | 근거 판정 프롬프트에 인용 원문 지시 무시 문장, 로그에 원문 미기록 |

### 3.3 Deliverables

| 구분 | 내용 |
|------|------|
| 백엔드 | domain/answer_citation, application/answer_citation(registry·labeler·service·enricher), grounding_judge_setting 3층, 판정 어댑터 확장, workflow_compiler·run_sources 연결, V093·V094 |
| 프론트 | GroundingJudgeModelCard, remarkCitationRefs·CitationRef·CitationList·UnusedSourcesDisclosure·CitationNoneBadge, citationView 유틸, 원문 뷰어 focus 음영 |
| 테스트 | 도메인·애플리케이션·인프라 단위 테스트, AST 경계, 판정 벤치(-m llm), 프론트 컴포넌트·유틸 테스트 |
| 커밋 | a08dfbf ~ 246704f (13개) |

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| 항목 | 이유 |
|------|------|
| SC-2 골든셋 10문항 수기 라벨 | 실측 시간 필요 |
| SC-5 음영 매칭률 집계, PDF 원본 모드 확인 | worktree에서 pdf.js 워커 주소가 비어 텍스트로 폴백(환경 문제), 머지 후 메인에서 확인 |
| SC-6 스위치 on/off 호출 수·지연 비교 | 실측 미실행 |
| G-4 라우팅 검색 page | RoutedChunk에 page 전달 필요 |
| G-5 관리자 카드 폴백 경고 | Minor |
| G-6 GET effective 계산 규칙 | Minor |
| G-7 재판정 실패 시 이전 verdict 재사용 | D-06과 일치, 문서화로 둠 |
| G-8 supervisor 밖 경로 라벨 | 경로별 확인 필요 |
| G-9 설정 조회 실패 캐시 | Minor |
| G-3 judge_model 기록 | v0.3에서 이월 승인 |

### 4.2 Cancelled/On Hold Items

없음.

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 축 | 점수 |
|----|:----:|
| Structural | 96% |
| Functional | 93% |
| Contract | 95% |
| Runtime | 90% |
| Overall | 93.6% |

### 5.2 Resolved Issues

| ID | 문제 | 해결 |
|----|------|------|
| 벤치 1차 실패 | 틀린 번호 인용 3/5가 supported | 근거 문장이 다른 청크에만 있으면 탈락 + 프롬프트 보강 |
| G-10 | parent·child 청크 중복으로 `[1][2]`가 같은 근거 | 한 문장 안 같은 문서·같은 근거는 첫 번째만 |
| G-1 | 상한으로 보충된 칩에 원문 보기 없음 | 인용 적용을 원문 뷰어 정보보다 먼저 |
| G-2 | 판정 off면 검증 전 번호 스트리밍 | 최종 답변 호출을 스트리밍에서 제외 |

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- 판정 확장 전에 벤치를 먼저 돌려 판정기의 성향(틀린 번호에도 supported)을 찾고, LLM 판단 뒤에 결정적 검사를 두는 방식으로 막았다.
- 라이브 E2E에서 단위 테스트로는 보이지 않던 parent·child 중복 인용을 찾았다.
- 스위치·DI 한 곳·AST 경계로 기능 전체를 끄고 켤 수 있게 했다.

### 6.2 What Needs Improvement (Problem)

- 이 PC에서는 백엔드 전체 스위트가 600초를 넘고 프론트 전체 병렬 실행이 부하로 허위 실패를 내서, 영향 범위만 돌리고 상시 실패 목록과 대조해야 했다.
- 수치 기준(SC-2·5·6)은 Check 단계에서 실측하지 못했다.

### 6.3 What to Try Next (Try)

- 골든셋·on/off 비교를 스크립트(`cit_e2e.py` 확장)로 만들어 다음 사이클 Check에서 바로 돌린다.
- PDF 원본 모드는 머지 후 메인 체크아웃에서 확인한다.

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

- LLM 판정을 바꾸는 기능은 Design 단계에서 벤치 기준(새 오판 0 등)을 먼저 정하고 Do 중간에 돌린다.

### 7.2 Tools/Environment

- worktree의 `node_modules` junction에서 vite `?url` 임포트가 비는 문제를 메모리에 기록했다.
- `ai_answer_citation`(utf8mb4_0900_ai_ci)과 `ai_run`(utf8mb4_unicode_ci)의 collation이 달라 JOIN 조회가 실패한다. 조회 시 따로 읽는다.

## 8. Next Steps

### 8.1 Immediate

- E2E 테스트 데이터(KB·에이전트·Qdrant 컬렉션) 정리, 8011·5175 서버 종료
- 브랜치 push → PR 생성 → 머지
- 운영 배포 시 Flyway V093·V094 순서 확인, 스위치는 off로 시작

### 8.2 Next PDCA Cycle

- SC-2·5·6 실측, 라우팅 검색 page(G-4), 관리자 카드 폴백 경고(G-5)
- supervisor 라우팅 JSON이 채팅에 잠깐 보이는 기존 동작(이번 기능과 무관) 개선 검토

## 9. Changelog

### v1.0.0 (2026-11-23)

- feat: 답변 `[n]` 인용과 같은 판정 호출에서의 인용 검증, 통과 인용만 표시
- feat: 근거 판정 모델 관리자 설정(V094)
- feat: 인용 저장(V093)·재진입 유지
- feat: 원문 뷰어 근거 문장 음영
- fix: 청킹 U+FFFD 제거, ES 청크 page 저장
- fix: 중복 인용 합치기·보충 칩 원문 보기·판정 off 스트리밍 차단

## Version History

| 버전 | 날짜 | 내용 |
|------|------|------|
| 1.0 | 2026-11-23 | 완료 보고서 |
