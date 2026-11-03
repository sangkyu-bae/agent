# negative-feedback-drilldown 분석 보고서

> **분석 유형**: Gap 분석 (Design vs 구현) + 런타임 검증
>
> **Project**: sangplusbot — idt + idt_front
> **Version**: worktree `wt/neg-drilldown`, 브랜치 `feature/negative-feedback-drilldown` (기준 1baf6d1, 미커밋)
> **Analyst**: 배상규 + Claude (정적 분석: gap-detector)
> **Date**: 2026-11-03
> **Design Doc**: [negative-feedback-drilldown.design.md](../02-design/features/negative-feedback-drilldown.design.md) (v0.2)

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | 👎 데이터는 쌓이지만 관리자가 질문·답변·실행 근거를 열어 볼 화면이 없어 원인을 판단할 수 없다. |
| **WHO** | P3 관리자(부서·시스템) — 👎 원인을 확인하고 위키 draft 승인 여부를 판단하는 사람. |
| **RISK** | 대화 원문을 관리자 화면에 처음 표시한다(런 상세 API는 이미 반환 중). 평가 id(assistant)와 런 연결 id(user)가 달라 질문 복원을 빠뜨리면 200 빈 결과로 조용히 실패한다. |
| **SUCCESS** | 로컬 실데이터 👎 2건 모두 질문·답변·런 링크 표시, 👎 없는 메시지 404, 비관리자 403, 응답에 사용자 id 없음, 회귀 0. |
| **SCOPE** | 신규 조회 UseCase·엔드포인트 1개, 프론트 타입·서비스·훅·모달, 패널 항목 버튼화, 테스트. |

---

## Strategic Alignment Check

PRD는 없다. 원천은 `docs/proposals/2026-10-15.md` §2-8이다.

| 항목 | 기대 | 판정 |
|------|------|:----:|
| 핵심 문제(WHY) | 관리자가 👎 답변의 원인을 화면에서 판단 | ✅ 질문·답변·이유·근거·런 링크를 한 모달에서 확인 |
| 대상(WHO) | P3 관리자 | ✅ `require_role("admin")`, 비관리자 403 실측 |
| 제안서 전제 정정 | assistant id로 `retrievals` 호출 시 빈 결과 | ✅ 질문 복원 후 조회. 실앱에서 기존 경로 0건, 신규 경로 1건 재현 |

### Success Criteria Status (Plan §4)

| # | 기준 | 판정 | 근거 |
|---|------|:----:|------|
| SC-1 | FR-01~15 구현 및 TDD 테스트 통과 | ✅ | FR 15/15 코드 근거(§2.4). 백엔드 관련 273건, 프론트 패널·모달 28건 통과 |
| SC-2 | 실런: 284·267에 질문·답변·런 1건, `groups=[]` | ✅ | TestClient 실앱: 284 → q11자/a238자/런 `5a7d6c11` groups 0, 267 → q14자/a309자/런 `d1050baa` groups 0 |
| SC-3 | 실런: 👍·평가 없음 404, 비관리자 403 | ✅ | 282(👍)·497(평가 없음)·283(user 메시지)·999999999 → 404, 미인증 401, user 2 → 403 |
| SC-4 | 브라우저 실런, 콘솔 오류 0 | ⚠️ | 흐름은 통과(§2.7 L2·L3). 콘솔 오류는 있으나 전부 무관: `kb-breakdown`·`recent-documents` 500(로컬 DB 콜레이션 1267), Pretendard 폰트 403(worktree junction이 Vite 허용 경로 밖). 이 기능의 요청은 전부 200 |
| SC-5 | 근거 있는 런 임시 👎 검증 후 삭제 | ✅ | 메시지 276: 재작성 쿼리 3개·근거 33건 표시, 삭제 후 잔존 0 |
| SC-6 | pytest·Vitest FAILED 목록 기준선 동일 | ✅ | pytest: worktree 60 vs master 53, 차이 7건 모두 무관(§5.2). Vitest: 양쪽 9건으로 목록 동일(§5.3) |
| SC-7 | SOT·위키 어긋남 보고 | ✅ | §10에 기록 (수정은 사용자 호출 시) |
| QC-1 | 신규 코드 커버리지 80% 이상 | ⚠️ | 분기별 테스트는 있으나 커버리지 수치 미측정 |
| QC-2 | ruff·eslint·tsc 신규 오류 0 | ✅ | ruff 신규 E501 1건 수정 후 0, 변경 파일 eslint 0, `tsc -b --force` 양쪽 210건으로 오류 목록 동일(변경 파일 0건) |
| QC-3 | MSW 핸들러가 실제 URL·형태와 일치 | ✅ | 실런에서 같은 URL·형태로 200 |
| QC-4 | 마이그레이션 없음 | ✅ | |

**Success Rate**: 9/11 충족, 2건 부분, 미충족 0건. 부분 2건은 SC-4(콘솔의 무관한 오류)와 QC-1(커버리지 수치 미측정)이다.

### Decision Record Verification

| 출처 | 결정 | 준수 | 비고 |
|------|------|:----:|------|
| [Plan] | 상세 엔드포인트 신설 | ✅ | `GET /api/v1/admin/eval/negative/{message_id}/drilldown` |
| [Plan] | 질문·답변 전문, 평가자 비노출 | ✅ | 응답 키 재귀 검사 테스트. 런 상세 화면의 `user_id`는 범위 밖(Design §7) |
| [Plan] | 모달 | ✅ | 공통 `Modal` 3xl·body scroll |
| [Design] | 설계안 C — `GetMessageRetrievalsUseCase` 위임 | ✅ | `drilldown_use_case.py:93-97` |
| [Design] | `MarkdownRenderer` 재사용 | ✅ | 실데이터 2건에는 표·엑셀 링크가 없어 채팅 전용 동작은 관찰되지 않음 |
| [Design] | Depends 순서 | ⚠️ 의도적 차이 | 구현은 `admin`을 먼저 둬 미인증 시 세션을 만들지 않는다(위키 규칙). Design §4.3 갱신 필요(M-2) |

---

## 1. Analysis Overview

### 1.1 Analysis Purpose
Design v0.2와 worktree 구현을 대조하고, Do 단계 실행 결과로 런타임 동작을 확정한다.

### 1.2 Analysis Scope
- Design: `idt/docs/02-design/features/negative-feedback-drilldown.design.md`
- 구현: `idt/src`(신규 2·수정 4), `idt/tests`(신규 1·수정 2), `idt_front/src`(신규 2·수정 7)
- 정적 분석은 gap-detector가 읽기 전용으로 수행했다. 런타임은 Do 단계 실행 기록이다.

---

## 2. Gap Analysis

### 2.1 API Endpoints

| Design | 구현 | 상태 |
|--------|------|:----:|
| `GET /api/v1/admin/eval/negative/{message_id}/drilldown` | `eval_router.py:127-145` | ✅ |

### 2.2 Data Model

스키마 변경 없음. 포트 메서드 `has_negative` 추가(`domain/eval/interfaces.py:34-36`, 구현 `infrastructure/eval/repository.py:79-89`).

### 2.3 Component Structure

| Design | 구현 | 상태 |
|--------|------|:----:|
| `NegativeDrilldownModal` | `pages/AdminDashboardPage/components/NegativeDrilldownModal.tsx` | ✅ |
| `AgentSatisfactionPanel` 버튼화 | 같은 폴더 `AgentSatisfactionPanel.tsx:59-77` | ✅ |

### 2.4 Functional Depth

placeholder·TODO 0건. FR 15/15에 코드 근거가 있다(gap-detector 대응표). 얕은 파일 0개.

### 2.5 Page UI Checklist Verification

| 화면 | 설계 항목 | 구현 | 누락 | 비율 |
|------|:--------:|:----:|:----:|:----:|
| AgentSatisfactionPanel | 3 | 3 | 0 | 100% (I-1은 품질 결함) |
| NegativeDrilldownModal | 12 | 12 | 0 | 100% |

**Functional Match Rate**: 97% — 접근성 NFR 부분 충족(I-1)으로 3%p 감점.

### 2.6 API Contract Verification

| 엔드포인트 | Design | Server | Client | 결과 |
|-----------|:------:|:------:|:------:|:----:|
| drilldown | ✅ §4.2 | ✅ `eval_drilldown_response.py:17-22` | ✅ `messageFeedback.ts:26-47`, `api.ts:349-350` | PASS |

필드 12개의 이름·nullable이 일치한다. 프론트 `RetrievalDto`에 점수 보조 필드가 없는 것은 Design §11.5의 의도된 축소다.

**Contract Match Rate**: 1/1 = 100%

### 2.7 Runtime Verification Results

#### L1: API (TestClient 실앱, 실 DB)

| # | 시나리오 | 기대 | 실제 | 통과 |
|---|---------|------|------|:----:|
| 1 | 284 관리자 | 200, 런 1·groups 0 | 200, `5a7d6c11` groups 0 | ✅ |
| 2 | 267 관리자 | 200, 런 1 | 200, `d1050baa` groups 0 | ✅ |
| 3 | 282 (👍만) | 404 | 404 | ✅ |
| 4 | 497 (평가 없음) | 404 | 404 | ✅ |
| 5 | 283 (user 메시지) | 404 | 404 | ✅ |
| 6 | 없는 id | 404 | 404 | ✅ |
| 7 | 미인증 | 401 | 401 | ✅ |
| 8 | 비관리자 | 403 | 403 | ✅ |
| 9 | 응답 키 | `user_id`·`session_id` 없음 | 키 5개(agent_id, answer, message_id, question, runs) | ✅ |
| 10 | 기존 `retrievals`에 assistant id | 0건(전제 재현) | 284·267 모두 0건 | ✅ |
| 11 | openapi 경로 등록 | 있음 | 있음 | ✅ |

**L1**: 11/11 = 100%

#### L2: UI (Chrome, worktree 서버 8010·5174)

| # | 동작 | 결과 | 통과 |
|---|------|------|:----:|
| 1 | 대시보드 패널 | 👎 3건이 버튼으로 표시 | ✅ |
| 2 | 임시 👎(276) 클릭 | 모달, 쿼리 3·근거 33건, 순위 `1.`부터 | ✅ (수정 후) |
| 3 | 닫기 | 모달 닫힘, 패널 유지 | ✅ |
| 4 | 284 클릭 | "코멘트 없음", "이 실행은 문서 검색을 사용하지 않았습니다" | ✅ |

**L2**: 4/4 = 100%

#### L3: E2E

| # | 시나리오 | 결과 | 통과 |
|---|---------|------|:----:|
| 1 | 대시보드 → 모달 → "런 상세" → `/admin/agent-runs/5a7d6c11…` | 런 상세 진입, 모달 언마운트, 오류 없음 | ✅ |

**L3**: 1/1 = 100%

실런에서 결함 1건을 발견해 수정했다. `rank_index`는 1부터 저장되는데(`rag_agent/tools.py:336, 430` `enumerate(start=1)`) 화면에서 +1을 더해 2부터 표시됐다. 테스트 픽스처가 0을 써서 단위 테스트가 잡지 못했다. 픽스처를 실제 값으로 고친 Red 테스트 후 수정했다.

**Runtime Match Rate**: 100%

### 2.8 Match Rate Summary

```
┌─────────────────────────────────────────────┐
│  Structural Match Rate:  100%               │
│  Functional Match Rate:   97%               │
│  Contract Match Rate:    100%               │
│  Runtime Match Rate:     100%               │
│  ─────────────────────────────────────────── │
│  Overall Match Rate:      99%               │
│  = 100×0.15 + 97×0.25 + 100×0.25 + 100×0.35 │
└─────────────────────────────────────────────┘
```

---

## 3. Code Quality Analysis

### 3.1 Gap 목록

| ID | 심각도 | 내용 | 근거 | 조치 |
|----|:-----:|------|------|------|
| I-1 | Important | 패널 버튼 `aria-label`에 에이전트 id가 없다. 코멘트 없는 👎 2건의 버튼 이름이 둘 다 "코멘트 없음 상세 보기"가 된다(브라우저 스냅샷 실측) | `AgentSatisfactionPanel.tsx:62` | 이름에 agent_id 포함 + 이름 구분 단언 |
| M-1 | Minor | 404 테스트가 `detail`을 단언하지 않음 | `test_eval_router.py:249-255` | 단언 1줄 |
| M-2 | Minor | Depends 순서가 Design §4.3과 다름(구현이 더 나음) | `eval_router.py:133-134` | Design 갱신 |
| M-3 | Minor | 빈 문자열 코멘트를 패널(`??`)과 모달(`||`)이 다르게 표시 | `AgentSatisfactionPanel.tsx:62,67`, `NegativeDrilldownModal.tsx:107` | 패널도 `||`로 통일 |
| M-4 | Minor | 기존 패널 테스트 3건의 렌더 헬퍼에 `MemoryRouter` 추가(단언 무변경) | `AgentSatisfactionPanel.test.tsx:16-25` | Report에 기록 |
| M-5 | Minor | 질문 행이 조회 도중 삭제되면 `MessageNotFoundError`(LookupError)가 500으로 전파 | `get_message_retrievals_use_case.py:74-76`, `eval_router.py:143` | 경합 창이 좁아 기록만 |
| M-6 | Minor | 모달 부제가 Design 예시(줄인 id)와 달리 agent_id 전체 표시 | `NegativeDrilldownModal.tsx:147` | Design 예시 정정 |
| M-7 | Minor | Design §2.3 의존 목록의 `Badge` 미사용 | — | Design 정정 |
| M-8 | Minor | 패널 버튼이 기존 `rose-*` 원색 유지 | `AgentSatisfactionPanel.tsx:64` | 후속 토큰 이관 |

Critical: 0건.

### 3.2 Act-1 처리 결과 (2026-11-03)

| ID | 처리 | 근거 |
|----|------|------|
| I-1 | ✅ 수정 | `aria-label`을 `{agent_id} {이유 또는 코멘트 없음} 상세 보기`로 변경. Red→Green 테스트 "코멘트가 없어도 에이전트로 버튼 이름이 구분된다" |
| M-1 | ✅ 수정 | 404 응답의 `detail` 단언 추가 |
| M-2 | ✅ Design 갱신 | §4.3 Depends 순서 |
| M-3 | ✅ 수정 | 패널도 `||` 사용. 테스트 "빈 문자열 코멘트는 코멘트 없음으로 표시한다" |
| M-6·M-7 | ✅ Design 갱신 | §5.1 부제 예시, §2.3 `Badge` 제거 |
| M-4 | 기록 | 기존 패널 테스트는 렌더 헬퍼만 바뀌었고 단언은 그대로 |
| M-5 | 이월 | 질문 행 삭제 경합 시 500. 경합 창이 좁아 기록만 |
| M-8 | 이월 | 패널 원색 → 토큰 이관은 후속 사이클 |

수정 후 결과: 패널·모달 30건, 라우터 17건 통과.

### 3.2 Security

| 항목 | 판정 |
|------|:----:|
| 관리자 전용(401·403 실측) | ✅ |
| 👎 달린 assistant 메시지로 조회 제한(404 실측) | ✅ |
| 응답 사용자 식별자 제외(재귀 키 검사 + 실측) | ✅ |
| 조회 로그에 본문 미기록(테스트) | ✅ |
| 외부 링크 `rel="noopener noreferrer"`(테스트) | ✅ |

---

## 4. Performance Analysis

목록 응답은 변경하지 않았다. 드릴다운은 모달을 열 때 1회 호출된다(테스트로 0회·1회 확인). 쿼리는 `has_negative` 1 + 메시지 1 + 세션 메시지 1 + 위임 내부 메시지 1·런 1·런별 근거 N이다. 별도 측정은 하지 않았다.

---

## 5. Test Coverage

### 5.1 테스트 현황

| 범위 | 신규 테스트 | 결과 |
|------|:----------:|------|
| UseCase | 11 | 통과 |
| 저장소 `has_negative` | 4 | 통과 |
| 라우터 | 8 | 통과 |
| 모달 | 14 | 통과 |
| 패널 | 5 (기존 3 유지) | 통과 |

Design §8.2 6/6, §8.3 9/9, §8.4 11/11 시나리오에 대응 테스트가 있다.

### 5.2 회귀 (pytest FAILED 목록 diff)

| 구분 | 실패 수 |
|------|:------:|
| master(기준선) | 53 |
| worktree | 60 |
| worktree에만 있는 실패 | 7 |
| master에만 있는 실패 | 0 |

7건의 원인은 다음과 같다. 모두 이번 변경과 무관하다.
- `tests/application/blueprint/test_extraction_use_case.py` 6건: worktree에 gitignore된 `idt/samples/golden_sample_report.pdf`가 없어 `FileNotFoundError`
- `tests/infrastructure/document_font/test_html_font_embedder.py::test_embed_overhead_within_budget` 1건: 성능 측정 테스트. 단독 재실행 시 master에서도 실패

기준선을 실행한 master 체크아웃에는 다른 세션의 미커밋 PII 마스킹 변경이 있었다. 비교 결과에는 영향이 없었다.

### 5.3 회귀 (Vitest·tsc, Check 수정 후)

메모리 부족 중단을 피하려고 `--no-file-parallelism`으로 한 번에 하나씩 실행했다.

| 구분 | worktree | master |
|------|:-------:|:------:|
| Vitest 실패 | 9 / 1,532 | 9 / 1,555 |
| 실패 목록 차이 | 0건 | 0건 |
| `tsc -b --force` 오류 | 210 | 210 |
| 오류 목록 차이 | 0건 | 0건 |

실패 9건은 기존 상시 실패(ChatPage TC-FE-2, CreateCollectionModal 1, UpdateScopeModal 6, DatasetsTab 업로드)와 같다. master 쪽 테스트 수가 23건 많은 것은 다른 세션의 미커밋 변경 때문이다.

---

## 6. Clean Architecture Compliance

| 레이어 | 확인 | 판정 |
|--------|------|:----:|
| domain | 포트 추상 메서드만 추가 | ✅ |
| application | domain·application만 import, infrastructure import 0 | ✅ |
| infrastructure | domain 포트 구현, commit 0 | ✅ |
| interfaces | 응답 스키마가 application DTO 참조(기존 `multimodal.py`·`blueprint.py` 선례) | ✅ |
| api | 위임·변환만, 같은 요청 세션 주입 | ✅ |

함수 길이 최대 20줄, if 중첩 1단계, print 0건.

---

## 7. Convention Compliance

| 항목 | 판정 |
|------|:----:|
| 컴포넌트 파일 런타임 상수 export 없음 | ✅ |
| 신규 코드 `zinc-400` 없음 | ✅ |
| queryKeys 팩토리·서비스 레이어 경유 | ✅ |
| 신규 모달 토큰·`components/ui` 사용 | ✅ |
| 패널 기존 원색 유지 | ⚠️ M-8 |

---

## 8. Overall Score

```
┌─────────────────────────────────────────────┐
│  최초 Match Rate: 99%                        │
│  Act-1 후 Match Rate: 100% (Functional 100)  │
├─────────────────────────────────────────────┤
│  Critical 0 · Important 0 · Minor 이월 2     │
│  회귀: pytest·Vitest·tsc 차이 0              │
└─────────────────────────────────────────────┘
```

---

## 9. Recommended Actions

| 우선 | 항목 | 파일 |
|:---:|------|------|
| 1 | I-1 패널 버튼 접근성 이름 구분 | `AgentSatisfactionPanel.tsx`, `.test.tsx` |
| 2 | M-1 404 detail 단언, M-3 빈 코멘트 표시 통일 | `test_eval_router.py`, `AgentSatisfactionPanel.tsx` |
| 3 | Vitest 전체·`tsc -b` 실행(메모리 여유 시) | — |
| 4 | M-2·M-6·M-7 Design 정정 | Design 문서 |

---

## 10. Design Document Updates Needed

- [ ] §4.3 Depends 순서를 구현(`admin` 먼저)에 맞춤 — M-2
- [ ] §5.1 부제 예시를 agent_id 전체로 — M-6
- [ ] §2.3 의존 목록에서 `Badge` 제거 — M-7

SOT·위키 어긋남(수정은 사용자 호출 시):
- `docs/SOURCE-OF-TRUTH.md` API 표에 신규 엔드포인트 없음
- `docs/wiki/frontend/screens/admin-screens.md`에 대시보드 드릴다운 모달 없음

---

## 11. Next Steps

- [ ] Gap 처리 방침 결정 → 수정 시 `/pdca iterate`
- [ ] 프론트 전체 회귀
- [ ] `/pdca report negative-feedback-drilldown`

---

## Version History

| 버전 | 날짜 | 변경 | 작성자 |
|------|------|------|--------|
| 0.1 | 2026-11-03 | 최초 분석 — 정적(gap-detector) + Do 런타임 실행 기록 통합 | 배상규 + Claude |
| 0.2 | 2026-11-03 | Act-1 반영(I-1·M-1·M-3 수정, Design 정정), 프론트 전체 회귀·`tsc -b` 결과 추가 | 배상규 + Claude |
