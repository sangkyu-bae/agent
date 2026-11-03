# negative-feedback-drilldown 완료 보고서

> **Status**: Complete (미커밋 — worktree `wt/neg-drilldown`, 브랜치 `feature/negative-feedback-drilldown`)
>
> **Project**: sangplusbot — idt (백엔드) + idt_front (프론트)
> **Version**: 기준 커밋 1baf6d1
> **Author**: 배상규 + Claude
> **Completion Date**: 2026-11-03
> **PDCA Cycle**: Plan → Design → Do → Check → Act-1 → Report
> **원천**: `docs/proposals/2026-10-15.md` 후보 #8 (§2-8)

---

## Executive Summary

### 1.1 Project Overview

| 항목 | 내용 |
|------|------|
| 기능 | 관리자 대시보드의 👎 답변에서 질문·답변·검색 근거·런 상세로 이동 |
| 시작일 | 2026-11-02 |
| 종료일 | 2026-11-03 |
| 기간 | 2일 |

### 1.2 Results Summary

```
┌─────────────────────────────────────────────┐
│  Match Rate: 99% → 100% (Act-1 1회)         │
├─────────────────────────────────────────────┤
│  ✅ FR 완료:        15 / 15                  │
│  ✅ Success Criteria: 9 / 11 (부분 2, 미충족 0) │
│  ⏳ 이월:            2건 (Minor)             │
│  회귀: pytest·Vitest·tsc -b 차이 0          │
└─────────────────────────────────────────────┘
```

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **문제** | 대시보드의 최근 👎 목록은 에이전트 id와 이유만 보여 관리자가 오답 원인을 판단할 수 없었다. 제안서가 가정한 `retrievals` 재사용은 평가 id(assistant)와 런 연결 id(user)가 달라 200 빈 결과로 조용히 실패하는 경로였다. |
| **해결** | 관리자 전용 `GET /api/v1/admin/eval/negative/{message_id}/drilldown`을 추가했다. 평가된 답변에서 `EvalPolicy.find_question`으로 질문을 복원하고, 그 id로 기존 `GetMessageRetrievalsUseCase`에 위임한다. 대시보드 항목은 버튼이 되어 모달을 연다. |
| **기능·UX 효과** | 실데이터 👎 2건 모두 질문·답변·런 1건을 표시한다. 근거 있는 런은 재작성 쿼리 3개·근거 33건을 순위대로 보여 준다. 검색을 쓰지 않은 실행은 "문서 검색을 사용하지 않았습니다"로 구분하고, 런 상세로 한 번에 이동한다. |
| **핵심 가치** | 쌓아 두기만 하던 👎 데이터를 관리자가 원인 확인에 쓸 수 있게 됐다. 조회는 👎가 달린 답변으로 제한되고, 응답에는 사용자 식별자가 없으며, 조회자는 로그에 남는다. |

---

## 1.4 Success Criteria Final Status

| # | 기준 | 상태 | 근거 |
|---|------|:----:|------|
| SC-1 | FR-01~15 구현 및 TDD 테스트 통과 | ✅ | FR 15/15. 백엔드 관련 273건, 패널·모달 30건, 라우터 17건 통과 |
| SC-2 | 실런: 284·267에 질문·답변·런 1건, `groups=[]` | ✅ | TestClient 실앱: 284 → 런 `5a7d6c11` groups 0, 267 → 런 `d1050baa` groups 0 |
| SC-3 | 실런: 👍·평가 없음 404, 비관리자 403 | ✅ | 282·497·283·없는 id 404, 미인증 401, 비관리자 403 |
| SC-4 | 브라우저 실런, 콘솔 오류 0 | ⚠️ 부분 | 흐름 통과. 콘솔 오류는 무관한 것만 있음: `kb-breakdown`·`recent-documents` 500(로컬 DB 콜레이션 1267), Pretendard 폰트 403(worktree junction이 Vite 허용 경로 밖) |
| SC-5 | 근거 있는 런 임시 👎 검증 후 삭제 | ✅ | 메시지 276: 쿼리 3·근거 33건 표시, 삭제 후 잔존 0, 평가 집계 원상태 |
| SC-6 | 회귀 0 (FAILED 목록 diff) | ✅ | pytest 차이 7건 모두 무관(아래 §5.3). Vitest 9건·`tsc -b` 210건으로 master와 목록 동일 |
| SC-7 | SOT·위키 어긋남 보고 | ✅ | §8.1 |
| QC-1 | 신규 코드 커버리지 80% 이상 | ⚠️ 부분 | 분기별 테스트는 있으나 수치 미측정 |
| QC-2 | ruff·eslint·tsc 신규 오류 0 | ✅ | 신규 E501 1건 수정 후 0, 변경 파일 eslint 0, `tsc -b` 목록 동일 |
| QC-3 | MSW 핸들러가 실제 URL·형태와 일치 | ✅ | 실런에서 같은 URL·형태로 200 |
| QC-4 | 마이그레이션 없음 | ✅ | |

**Success Rate**: 9/11 충족 (82%), 부분 2건, 미충족 0건.

## 1.5 Decision Record Summary

| 출처 | 결정 | 준수 | 결과 |
|------|------|:----:|------|
| [Plan] | 제안서 전제 정정 — 질문 복원 후 런 조회 | ✅ | 실앱에서 기존 경로 0건, 신규 경로 1건 재현. 결정이 맞았다 |
| [Plan] | 상세 엔드포인트 신설 | ✅ | 목록 응답 무변경, 모달을 열 때 1회 호출 |
| [Plan] | 질문·답변 전문 노출, 평가자 비노출 | ✅ | 응답 키 재귀 검사 테스트. 단, 런 상세 화면은 기존대로 `user_id`를 표시한다(§4.1) |
| [Plan] | 모달 | ✅ | 공통 `Modal`로 대시보드 맥락 유지 |
| [Plan] | 👎 달린 assistant 메시지로 조회 제한, 고아 피드백 404 | ✅ | 404 4종 실측 |
| [Design] | 설계안 C — `GetMessageRetrievalsUseCase` 위임 | ✅ | 런·근거 규칙 복제 0. 응답 변환도 기존 `MessageRetrievalsResponse.from_dto` 재사용 |
| [Design] | 응답 스키마를 `interfaces/schemas/`에 둠 | ✅ | application → interfaces 역참조 회피 |
| [Design] | `MarkdownRenderer` 재사용 | ✅ | 실데이터에는 표·엑셀 링크가 없어 채팅 전용 동작은 관찰되지 않았다 |
| [Design] | Depends 순서 | ⚠️ 구현이 변경 | `admin`을 먼저 둬 미인증 요청은 세션을 열지 않는다. Design v0.3에 반영 |

---

## 2. Related Documents

| 단계 | 문서 | 상태 |
|------|------|------|
| Plan | [negative-feedback-drilldown.plan.md](../01-plan/features/negative-feedback-drilldown.plan.md) | ✅ v0.2 |
| Design | [negative-feedback-drilldown.design.md](../02-design/features/negative-feedback-drilldown.design.md) | ✅ v0.3 |
| Check | [negative-feedback-drilldown.analysis.md](../03-analysis/negative-feedback-drilldown.analysis.md) | ✅ v0.2 |
| Report | 현재 문서 | ✅ |

---

## 3. Completed Items

### 3.1 Functional Requirements

| ID | 요구사항 | 상태 | 구현 위치 |
|----|---------|:----:|----------|
| FR-01 | admin 전용, 401·403 | ✅ | `eval_router.py` `negative_drilldown` |
| FR-02 | down 평가 없거나 assistant 아니면 404 | ✅ | `drilldown_use_case.py` `_resolve_answer` |
| FR-03 | `EvalPolicy.find_question` 재사용, 같은 turn 과거 행 복원 | ✅ | `_find_question` |
| FR-04 | 질문 id로 런·근거 조회 | ✅ | `_find_runs` |
| FR-05 | 응답 필드 | ✅ | `eval_drilldown_response.py` |
| FR-06 | 사용자 식별자 제외 | ✅ | 허용 필드만 선언 |
| FR-07 | 복원 실패 시 200, `question=null` | ✅ | |
| FR-08 | 원본 삭제 시 404 | ✅ | |
| FR-09 | 조회 로그(본문 미포함) | ✅ | `negative drilldown viewed` |
| FR-10 | 패널 항목 버튼, 선택 시에만 조회 | ✅ | `AgentSatisfactionPanel.tsx` |
| FR-11 | 질문·답변(`MarkdownRenderer`)·이유 | ✅ | `NegativeDrilldownModal.tsx` |
| FR-12 | 런 상세·LangSmith 링크 | ✅ | |
| FR-13 | 근거 없음·런 없음·질문 미복원 문구 구분 | ✅ | |
| FR-14 | 404·오류 안내와 재시도 | ✅ | |
| FR-15 | 프론트 타입 동기화 | ✅ | `types/messageFeedback.ts` |

### 3.2 Non-Functional Requirements

| 항목 | 목표 | 결과 | 상태 |
|------|------|------|:----:|
| 보안 | 관리자 전용·조회 범위 제한·식별자 제외 | 401·403·404 실측, 키 재귀 검사 | ✅ |
| 성능 | 목록 무영향, 모달 열 때 1회 | 테스트로 0회·1회 확인. 응답 시간 측정은 안 함 | ✅ |
| 호환성 | 기존 API·위젯 무변경 | 회귀 목록 차이 0 | ✅ |
| 접근성 | 키보드 조작, 항목 이름 구분 | Enter로 열림, Act-1에서 이름에 agent_id 포함 | ✅ |
| 아키텍처 | Thin DDD | 함수 최대 20줄, 중첩 1단계, 레이어 위반 0 | ✅ |

### 3.3 Deliverables

| 산출물 | 위치 | 상태 |
|--------|------|:----:|
| 포트·저장소 | `idt/src/domain/eval/interfaces.py`, `idt/src/infrastructure/eval/repository.py` | ✅ |
| UseCase (신규) | `idt/src/application/eval/drilldown_use_case.py` | ✅ |
| 응답 스키마 (신규) | `idt/src/interfaces/schemas/eval_drilldown_response.py` | ✅ |
| 라우트·DI | `idt/src/api/routes/eval_router.py`, `idt/src/api/main.py` | ✅ |
| 백엔드 테스트 | `tests/application/eval/test_drilldown_use_case.py`(신규), `tests/infrastructure/eval/test_repository.py`, `tests/api/test_eval_router.py` | ✅ |
| 프론트 계약 | `types/messageFeedback.ts`, `constants/api.ts`, `lib/queryKeys.ts`, `services/messageFeedbackService.ts`, `hooks/useMessageFeedback.ts` | ✅ |
| 모달 (신규)·패널 | `pages/AdminDashboardPage/components/` | ✅ |
| PDCA 문서 | `idt/docs/0{1,2,3,4}-*/` | ✅ |

변경 규모는 수정 13개, 신규 운영 코드 3개·테스트 2개·문서 4개다. 마이그레이션은 없다.

---

## 4. Incomplete Items

### 4.1 Carried Over to Next Cycle

| 항목 | 이유 | 우선순위 |
|------|------|:-------:|
| 질문 행이 조회 도중 삭제되면 500 (M-5) | `GetMessageRetrievalsUseCase`가 `LookupError`를 던지는데 라우터는 `ValueError`만 404로 바꾼다. 세션 조회 직후라 경합 창이 매우 좁다 | Low |
| 패널 버튼 `rose-*` 원색 → 디자인 토큰 (M-8) | 기존 패널 스타일을 그대로 옮겼다. 화면 단위 토큰 이관 사이클에서 처리 | Low |
| 런 상세 화면의 `user_id` 표시 | 드릴다운의 평가자 비노출은 응답 안에서만 성립한다. 런 상세 API는 step 요약으로 질문·답변을 이미 반환한다 | 정책 판단 필요 |
| 운영 데이터 검증 | 로컬 평가 3건뿐이라 표본이 작다. `agent-run-feedback-wiring` 이후 에이전트 경로 데이터가 쌓이면 E2E 이월 목록에서 확인 | Medium |

### 4.2 Cancelled/On Hold Items

없음.

---

## 5. Quality Metrics

### 5.1 Final Analysis Results

| 지표 | 목표 | 최초 | 최종 |
|------|------|:----:|:----:|
| Overall Match Rate | 90% | 99% | 100% |
| Structural / Functional / Contract / Runtime | — | 100 / 97 / 100 / 100 | 100 / 100 / 100 / 100 |
| Critical / Important | 0 / 0 | 0 / 1 | 0 / 0 |
| 보안 이슈 | 0 | 0 | 0 |

### 5.2 Resolved Issues

| 이슈 | 발견 경로 | 해결 |
|------|----------|------|
| 근거 순위가 2부터 표시 | 브라우저 실런 | `rank_index`는 `enumerate(start=1)`로 저장된 값이다. 화면의 +1을 제거하고 테스트 픽스처를 실제 값으로 고쳤다 |
| 코멘트 없는 항목끼리 버튼 이름이 같음 (I-1) | gap-detector + 브라우저 스냅샷 | `aria-label`에 agent_id 포함 |
| 빈 문자열 코멘트 표시 불일치 (M-3) | gap-detector | 패널도 `||` 사용 |
| 404 응답 메시지 미검증 (M-1) | gap-detector | `detail` 단언 추가 |
| 신규 파일 E501 1건 | ruff | docstring 축약 |
| 라우터 테스트 `RunId` 형식 오류 | Red 단계 | 36자 UUID 사용 |

### 5.3 회귀 근거

| 구분 | worktree | master | 목록 차이 |
|------|:-------:|:------:|:--------:|
| pytest 실패 | 60 | 53 | 7 (모두 무관) |
| Vitest 실패 | 9 / 1,532 | 9 / 1,555 | 0 |
| `tsc -b --force` 오류 | 210 | 210 | 0 |

pytest 차이 7건 중 6건은 worktree에 gitignore된 `idt/samples/golden_sample_report.pdf`가 없어서 생겼다. 1건은 성능 측정 테스트로, 단독 재실행 시 master에서도 실패한다. master 쪽 Vitest 수가 많은 것과 기준선 실행 시점의 PII 마스킹 변경은 다른 세션의 미커밋 작업이다.

---

## 6. Lessons Learned & Retrospective

### 6.1 What Went Well (Keep)

- **Plan 전에 로컬 DB를 읽기 전용으로 조회해 제안서 전제 3건을 정정했다.** 그대로 갔다면 프론트만 만들고 빈 결과를 받았을 것이다. id 불일치는 코드 리뷰로는 놓치기 쉽고 조인 한 번으로 드러났다.
- **Design 조사 중 "대화 원문을 노출하는 첫 경로"라는 Plan의 판단을 실측으로 뒤집었다.** 런 상세 API가 step 요약으로 이미 질문·답변을 반환하고 있었다. 위험 서술을 사실에 맞게 고쳤다.
- **규칙을 복제하지 않고 위임했다.** 질문 복원은 `EvalPolicy`, 런·근거 그룹핑과 응답 변환은 기존 코드를 그대로 썼다. 신규 UseCase는 조회 순서만 가진다.
- **실런이 단위 테스트가 못 잡은 결함을 잡았다.** 순위 +1 버그는 픽스처가 0을 써서 통과했고, 실제 데이터에서만 드러났다.

### 6.2 What Needs Improvement (Problem)

- **테스트 픽스처 값을 실제 저장 규칙에서 가져오지 않았다.** `rank_index` 0은 추측이었다. Design 예시도 같은 추측을 적었다.
- **전체 회귀를 병렬로 돌리다 메모리 부족으로 중단됐다.** 백엔드 전체와 프론트 전체를 한 스크립트로 돌린 것이 원인이었다.
- **gap-detector에 Write 도구가 없다는 것을 모르고 파일 저장을 지시했다.** 네트워크 오류로 한 번 중단된 뒤 재개해서 받았다.
- **worktree 환경 차이를 미리 정리하지 않았다.** gitignore된 샘플 파일이 없어 pytest 실패 6건이 생겼고, 원인을 다시 확인해야 했다.

### 6.3 What to Try Next (Try)

- 저장소에서 읽어 오는 값(순위, 시각, id 형식)을 쓰는 테스트 픽스처는 저장 코드나 실데이터 1건에서 값을 가져온다.
- 프론트 전체 회귀는 `--no-file-parallelism`으로 단독 실행한다. 백엔드 스위트와 동시에 돌리지 않는다.
- worktree 생성 직후 gitignore된 테스트 자산(`idt/samples/` 등)을 복사한다.
- 읽기 전용 에이전트에는 파일 저장 대신 응답 본문으로 결과를 받는다.

---

## 7. Process Improvement Suggestions

### 7.1 PDCA Process

| 단계 | 현재 | 제안 |
|------|------|------|
| Plan | 제안서 전제를 코드로만 확인하면 놓친다 | 데이터를 잇는 기능은 Plan 전에 실 DB 조인 1회를 기본 절차로 둔다 |
| Design | 예시 JSON 값을 추측으로 채움 | 예시 값은 실데이터나 저장 코드에서 가져온다 |
| Do | 실런이 DoD에 있어 결함을 잡았다 | 유지 |
| Check | 정적 분석과 실행 증거를 따로 합침 | 유지. 읽기 전용 에이전트의 출력 방식만 조정 |

### 7.2 Tools/Environment

| 영역 | 제안 | 기대 효과 |
|------|------|----------|
| worktree 셋업 | `git-workflow` 스킬 셋업 표에 gitignore된 테스트 자산 복사 추가 | 허위 실패 제거 |
| Vite | worktree에서 `server.fs.allow`에 메인 `node_modules` 경로 추가 검토 | junction 폰트 403 제거 |

---

## 8. Next Steps

### 8.1 Immediate

- [ ] 커밋·PR (worktree `wt/neg-drilldown`, 브랜치 `feature/negative-feedback-drilldown`). `.bkit/` 파일은 커밋에서 제외
- [ ] SOT·위키 갱신 판단 (사용자 호출 시):
  - `docs/SOURCE-OF-TRUTH.md` API 표에 신규 엔드포인트 없음
  - `docs/wiki/frontend/screens/admin-screens.md`에 대시보드 드릴다운 모달 없음
  - `docs/wiki/backend/db/erd-agent-run.md`에 `rank_index`가 1부터라는 사실 없음
- [ ] `/pdca archive negative-feedback-drilldown`

### 8.2 Next PDCA Cycle

| 항목 | 우선순위 |
|------|:-------:|
| `agent-run-feedback-wiring` (Plan 단계) — 에이전트 경로 답변 평가 버튼. 드릴다운에 들어올 데이터가 늘어난다 | High |
| 런 상세 화면의 사용자 식별자 노출 정책 | 정책 판단 |
| M-5·M-8 소형 정리 | Low |

---

## 9. Changelog

### 2026-11-03

**Added:**
- `GET /api/v1/admin/eval/negative/{message_id}/drilldown` (admin) — 👎 답변의 질문·답변·런·검색 근거
- `MessageFeedbackRepositoryInterface.has_negative`
- 대시보드 `NegativeDrilldownModal`

**Changed:**
- `AgentSatisfactionPanel`의 최근 부정 피드백 항목을 버튼으로 바꾸고, 접근성 이름에 에이전트와 이유를 넣었다. 빈 이유도 "(코멘트 없음)"으로 표시한다

**Fixed:**
- (개발 중 발견) 근거 순위 표시가 1씩 밀리던 문제

---

## Version History

| 버전 | 날짜 | 변경 | 작성자 |
|------|------|------|--------|
| 1.0 | 2026-11-03 | 완료 보고서 작성 | 배상규 + Claude |
