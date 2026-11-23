# answer-citation-verification — Gap Analysis (Check)

> Feature: 답변 인용 검증 (본문 [n] + 근거 문장·쪽 + 검증 탈락)
> Branch: `feature/answer-citation-verification` (worktree `wt/answer-citation`, base 49b0970)
> 기준 문서: Plan v0.1, Design v0.5 (Version History 0.2–0.5의 변경은 승인된 것으로 본다)
> 분석일: 2026-11-21

## Context Anchor

| 항목 | 내용 |
|------|------|
| WHY | 검색 결과 전체를 칩으로 보여 주면 답변이 실제로 어느 문서의 몇 쪽, 어느 문장을 근거로 했는지 알 수 없어 신뢰를 주기 어렵다 |
| WHO | P2 KB 운영자·에이전트 소유자, 그 에이전트를 쓰는 업무 사용자 |
| RISK | 판정 비용·지연 증가, 틀린 번호 인용, 스위치 off 회귀 |
| SUCCESS | SC-1~SC-10 (Plan §7) |
| SCOPE | 내부 문서 검색 경로만, env 스위치 기본 off, 관리자는 판정 모델만 선택 |

## 1. 점수

| 축 | 점수 | 근거 |
|----|:----:|------|
| Structural | 96% | §11.1 파일 전부 존재. `domain/answer_citation/instruction.py`, `grounding_judge_setting/exceptions.py` 추가. `useCitationView` → `utils/citationView.ts`(v0.5 승인) |
| Functional | 88% | 백엔드 로직 완결(placeholder 없음). 감점: G-1(보충 칩 viewer 없음), G-2(판정 off 경로 스트리밍), G-4(라우팅 검색 page 없음), G-5(관리자 카드 폴백 표시) |
| Contract | 95% | 관리자 API ↔ 프론트 100%, 칩 계약 §4.2 ↔ 백엔드 100%. 라이브 응답의 `citation` 형태를 프론트 렌더링으로 확인(§3) |
| Runtime | 85% | 라이브 E2E 5문항 verified, 재진입 동일, 화면 위첨자·인용 행·문장 음영 확인. 같은 근거 중복 인용(G-10), PDF 원본 모드 미확인 |
| **Overall** | **90.6%** | 0.15×96 + 0.25×88 + 0.25×95 + 0.35×85 |

## 2. 라이브 E2E (2026-11-21)

환경: worktree 백엔드 8011(`ANSWER_CITATION_ENABLED=true`, `SOURCE_VIEWER_ENABLED=true`, 근거 판정 기본 on), 프론트 5175(worktree idt_front), 로컬 DB에 V093·V094 적용, 기본 모델(gpt-4o-mini), hybrid 검색, 가계부채 보도자료 PDF 신규 업로드.

| 문항 | 상태 | 인용 수 | 쪽 | llm_call_count |
|------|------|:------:|:--:|:--------------:|
| 총량관리 목표 조정 | verified | 2 | 2 | 6 |
| 수도권 주담대 한도 | verified | 3 | 3·3·4 | 8 |
| 수도권 주담대 만기 | verified | 1 | 4 | 6 |
| 정책대출 공급 계획 | verified | 2 | 2 | 6 |
| (화면) 한도와 만기 | verified | 4 | 3·3·3·4 | 6 |
| (화면) 파이썬 정렬 — KB 무관 | 행 없음(not_applicable) | — | — | 6 |

확인한 것:
- 본문 `[n]`이 위첨자 버튼("근거 n 원문 보기")으로 렌더링되고, 아래 "답변 근거"에 번호·파일·쪽·근거 문장이 표시된다.
- 위첨자 클릭 → 원문 패널이 해당 구절(4/4, p.4)로 열리고 근거 문장이 진한 음영(`data-spv-focus`)으로 표시된다(텍스트 모드).
- 재진입 API(`/conversations/agents/{agent}/sessions/{session}/sources`)의 `citation`·`viewer`가 실시간 payload와 4문항 모두 동일(SC-7).
- 모든 인용에 쪽 번호가 있음(SC-4, 비라우팅 검색 기준).
- KB 무관 질문은 에이전트가 내부 문서 검색을 쓰지 않아 인용 행이 없고 배지도 없다 — 설계(D-12) 그대로.

확인하지 못한 것:
- "근거 확인 안 됨" 배지(SC-8): 검색은 했지만 인용이 0건인 답변을 라이브로 만들지 못했다. 단위 테스트로만 확인.
- PDF 원본 모드 음영: worktree의 `node_modules` junction 때문에 pdf.js 워커 주소(`?url`)가 비어 "원본 파일을 열 수 없어 텍스트로 보여 줍니다"로 폴백했다. 이번 기능의 문제가 아니라 확인 환경 문제로 판단(이전 사이클에서도 이월된 항목).
- SC-6 스위치 on/off 호출 수·지연 비교, SC-2 골든셋 10문항 수기 라벨, SC-5 음영 매칭률 집계.

## 3. Success Criteria

| SC | 상태 | 근거 |
|----|:----:|------|
| SC-1 스위치 off 동일 | ✅ | DI가 None 반환, payload 키 생략(source_policy.py:73-74), off 회귀 테스트 통과 |
| SC-2 인용 정확도 ≥90% | ⚠️ | 라이브 12건 육안 확인 모두 뒷받침됨. 골든셋 10문항 수기 라벨은 미실행 |
| SC-3 틀린 번호 100% 탈락 | ✅ | 벤치 0/5 잔존(D-07 정책 후) |
| SC-4 쪽 번호 100% | ⚠️ | 비라우팅 검색 12/12. 라우팅 검색은 page=None(G-4) |
| SC-5 음영 매칭 ≥90% | ⚠️ | 텍스트 모드 확인. 집계·PDF 원본 모드 미확인 |
| SC-6 추가 호출 0, p50 +1.5초 이하 | ⚠️ | 판정 on 경로는 같은 판정 호출(정적). on/off 실측 비교 미실행 |
| SC-7 재진입 동일 | ✅ | 4문항 citation·viewer 동일 |
| SC-8 none 배지 / 다른 경로 그대로 | ⚠️ | 백엔드·컴포넌트 테스트 통과, 라이브 none 미재현. G-8 |
| SC-9 U+FFFD 0 | ✅ | 가계부채 PDF 9→0, 청커 테스트 |
| SC-10 판정 벤치 변화 없음 | ✅ | 개정 기준(새 오판 0, 날조 3/3) 충족 |

## 4. Gap 목록

| ID | 심각도 | 위치 | 내용 | 수정안 |
|----|:------:|------|------|--------|
| G-10 | Important | application/answer_citation/labeler.py, registry.py | 같은 문장이 parent·child 두 청크(ccc7c9f5 child / e953a69e parent)에 들어 있으면 번호가 따로 붙어 `[1][2]`가 같은 근거를 가리키고, "답변 근거"에 같은 행이 두 번 나온다(라이브 3/5 문항). 사용자에게 중복으로 보임 | finalize에서 같은 문서·같은 evidence의 인용을 하나로 합치고 재번호(또는 라벨 단계에서 parent_id 기준 중복 제거) |
| G-1 | Important | run_sources.py:77-82 | D-14 보충 칩이 viewer 적용 뒤에 추가되어 "원문 보기"가 없다 | 인용 apply를 viewer enrich 앞으로 옮기거나 보충 칩도 enrich |
| G-2 | Important | workflow_compiler.py:1982-1985 | 근거 판정 off + 인용 on이면 최종 답변 호출에 INTERNAL_LLM_TAG가 없어 검증 전 번호가 스트리밍된다(라이브는 판정 on이라 미재현) | citation_run이 있으면 태그를 단다 |
| G-4 | Minor | tools.py:460-463 | 라우팅 검색은 page=None | RoutedChunk의 page 전달, 또는 SC-4 범위를 비라우팅으로 명시 |
| G-5 | Minor | GroundingJudgeModelCard.tsx | 저장 모델이 비활성이면 select가 "설정 안 함"으로 보이고 경고가 없다 | 폴백 경고 줄 + 비활성 option 표시 |
| G-6 | Minor | grounding_judge_setting/use_cases.py:85-90 | GET effective가 env 빈 값일 때 실제 모델(utility)과 다르게 보고 | env 제공자와 같은 규칙으로 계산 |
| G-7 | Minor | grounded_generation.py:73-74 | 재판정 실패 시 이전 verdict 재사용 | 문서에 명시(D-06과 일치) 또는 judged=False |
| G-8 | Minor | main.py ToolFactory labeler | supervisor 밖 경로도 머리말 번호를 받는다 | 경로별 테스트 확인 또는 supervisor 실행에만 labeler |
| G-9 | Minor | grounding_judge_setting/provider.py:73-81 | 설정 조회 실패를 캐시하지 않아 매 호출 경고 | 실패도 TTL 동안 캐시 |
| G-3 | Minor(승인) | answer_citation/service.py:94-96 | judge_model 항상 NULL (v0.3 이월) | 다음 사이클 |

이번 기능과 무관한 기존 동작(기록만):
- supervisor 라우팅 JSON(`{"next":"FINISH",...}`)이 채팅에 스트리밍되었다가 최종 답변으로 바뀐다 — `run_agent_use_case._map_chat_stream`은 이번 브랜치에서 변경 없음.
- quick KB 생성 응답이 커밋보다 먼저 와서 직후 에이전트 생성이 422 "Knowledge base not found"가 날 수 있다.
- `**…)**와`처럼 닫는 `**` 앞이 문장부호이고 뒤가 글자면 굵게가 적용되지 않는다(CommonMark 규칙).

## 5. Decision Record 확인

| 결정 | 준수 |
|------|:----:|
| C안 탈착 모듈 + 같은 판정 호출 | ✅ AST 경계 테스트, 판정 on 경로 추가 호출 0 |
| 탈락 후 1부터 재번호 | ✅ 라이브 번호 1부터 연속 |
| 관리자 카드는 LLM 모델 관리 페이지 | ✅ GroundingJudgeModelCard |
| env 스위치 기본 off | ✅ `.env.example`, config 기본 false |

## 6. 결론

Critical 0, Important 3(G-10·G-1·G-2), Minor 7. 종합 90.6%.
중복 인용(G-10)은 화면에서 바로 보이는 문제라 Act에서 먼저 고치는 것을 권장한다.
