# wiki-feedback-loop Completion Report

> **Feature**: wiki-feedback-loop — 이유 있는 👎를 팀 지식(제품 위키) draft로 승격하는 환류 2단계
> **Author**: 배상규
> **기간**: 2026-07-21 (1일, eval-feedback-loop와 연속 세션)
> **Match Rate**: **99%** (gap-detector, 불일치 gap 0, 권고 1건 Check 내 해소)

---

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | wiki-feedback-loop |
| 기간 | 2026-07-21 (Plan→Design→Do→Check→Report) |
| Match Rate | 99% (iterate 0회) |
| 변경 규모 | 신규 4파일 546 LOC(src 2 + tests 2) + 기존 수정 6파일 +168/−15 |
| 마이그레이션 | **0** (source_type 문자열 — CONVERSATION enum 값 기존 정의) |
| 테스트 | 신규 22케이스(T1 9·T2 8·T3 5) / 회귀 wiki+eval+memory 230 pass |
| 브랜치 | `feature/wiki-feedback-loop` — **PR #42(eval-feedback-loop) 위 스택** |

### 1.3 Value Delivered (4관점)

| 관점 | 실제 결과 |
|------|-----------|
| **Problem** | 👎 이유(용어 교정·사실 오류 지적)가 한 사용자의 memory로만 환류되어 팀 차원 지식으로 축적되지 않았음. `WikiSourceType.CONVERSATION`("대화 환류 Phase 3")은 LLM-WIKI-001 설계 때부터 enum에 예약만 되고 사용 0곳 |
| **Solution** | 동일 트리거(comment 있는 👎)에서 memory·wiki **팬아웃** — Q/A 복원 1회 공유, LLM이 팀 일반화 가치를 판정해 가치 있으면 `WikiArticle(DRAFT, conversation, feedback:{message_id}, path="피드백")` 생성. 메시지당 1회 dedup(LLM 호출 전), `wiki_feedback_draft_enabled` 기본 off 독립 opt-in |
| **Function UX Effect** | 사용자 UI 무변경 — 관리자 WikiPage(agent_id="super")에 "대화 환류(conversation)" 초안 출현, 승인 시 wiki-first 검색에 노출되어 **모든 사용자**의 답변 품질에 반영 |
| **Core Value** | 환류 스코프 확장 완성: 개인(memory, PR #42) → **팀(wiki, 본 사이클)** — 한 사용자의 교정이 조직 지식이 되는 Self-Improving RAG 고리, CONVERSATION 예약석 최초 배선 |

---

## 2. 산출물

| 단계 | 문서 |
|------|------|
| Plan | `docs/01-plan/features/wiki-feedback-loop.plan.md` — FR-01~07 |
| Design | `docs/02-design/features/wiki-feedback-loop.design.md` — 결정 ①~⑥ |
| Check | `docs/03-analysis/wiki-feedback-loop.analysis.md` — Match 99% |

## 3. 구현 요약

- **`FeedbackWikiDistiller`** (신규 117 LOC): 판정+정제 LLM 1회 — worthy=false·파싱 실패·빈 필드 None, confidence /100 clamp(비수치는 0.5 강등·초안 유지 — Check 보완), "이유에 없는 원인 추측 금지" 프롬프트
- **`FeedbackWikiService`** (신규 165 LOC): launcher 동형 — `refs_key` dedup을 **LLM 호출 전** 수행, `DRAFT` 하드코딩(자동 승인 불가), `session.begin()` 명시 트랜잭션, 전면 warning 격리
- **팬아웃** (`eval/use_cases.py`): `_is_actionable_negative`(순수 조건) + `_kickoff_feedback_fanout` — 둘 다 off면 복원 조회 0회, memory 경로 인자·순서 불변(기존 17건 무수정 통과)
- **DI**: `get_feedback_wiki_service()` lazy 싱글톤 + submit 주입, config `wiki_feedback_draft_enabled=False`

## 4. FR 이행 — 7/7 ✅

FR-01 트리거 재사용·독립 플래그 / FR-02 가치 없으면 0건 / FR-03 conversation·refs·DRAFT 고정 / FR-04 LLM 전 dedup / FR-05 기본 off 무회귀 / FR-06 지연 0+격리 / FR-07 회귀 230 pass

## 5. 학습 포인트

1. **예약석 채우기**: 설계 단계에서 enum에 미리 자리를 잡아둔 값(CONVERSATION)은 이후 사이클의 변경 표면을 극적으로 줄임 — 이번 배선에서 도메인·마이그레이션·프론트 전부 무변경.
2. **스택 브랜치**: 미머지 PR(#42) 위에 쌓이는 기능은 master가 아니라 기반 feature 브랜치에서 분기 — Do 도중 워킹트리에 기반 코드가 없음을 발견하고 전환. pdca-status 등 상태 파일 충돌은 백업 후 복원으로 해소.
3. **팬아웃 리팩토링 기준선**: 트리거 조건을 순수 함수로 분리하고 서비스별 enabled 판정을 팬아웃에 모으면, 소비자 추가(2번째 환류)가 기존 소비자 테스트 무수정 통과로 검증됨.

## 6. 이월 항목

- **PR 전략**: #42 머지 후 master 베이스 권장 (그 전이면 `feature/eval-feedback-loop` 베이스 스택 PR)
- E2E 수동 검증: 👎+이유 → memory 후보 + wiki 초안 → 각 승인 전 구간 (양 플래그 on + MySQL/Qdrant 기동 시)
- 반복 이유 빈도 집계 기반 승격(여러 👎 묶어 판단) — 후속 후보
- websearch 환류(WEBSEARCH 예약석) · agent 경로 평가 연동(기존 이월)
- 배포: 신규 마이그레이션 없음, 활성화는 `WIKI_FEEDBACK_DRAFT_ENABLED=true`
