# agent-eval-gate Plan Document

> **Feature**: agent-eval-gate — 답변 사용자 평가 수집 + 품질 측정 게이트
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: Draft
> **비전 근거**: growing-agent-vision 7원칙 중 "측정 게이트(measurement gate)" — 성장 축의 **미착수 마지막 축**. "사용자가 평가했을 때 자동으로 문맥을 이해하고 성장하는 에이전트"(사용자 원 요청)의 신호 수집 계층

---

## Executive Summary

| 관점 | 내용 |
|------|------|
| **Problem** | 에이전트 답변의 좋고 나쁨을 측정할 신호가 없다 — 관측성(run/검색 근거)은 "무엇을 했는가"만 기록하고, "그 답변이 도움됐는가"라는 사용자 판단은 어디에도 남지 않아 성장(환류·튜닝)의 근거가 없다 |
| **Solution** | 답변(assistant 메시지)에 **좋아요/싫어요 + 선택 코멘트** 평가를 부착하는 계층 — 메시지 id 기반 저장(retrieval-observability의 message_id 조회 선례 재사용), 에이전트별 품질 지표(만족도) 집계. 이후 환류/추출 우선순위·측정 게이트의 입력이 됨 |
| **Function UX Effect** | 채팅 답변 아래 👍/👎 버튼 — 클릭 시 즉시 저장, 관리자 대시보드에 에이전트별 만족도(👍 비율)·최근 부정 피드백 표시 |
| **Core Value** | growing-agent 7원칙의 **측정 게이트 완성** — "모델 고정·데이터 성장"에서 성장의 방향을 정하는 신호(사용자 평가)를 확보. 이후 어떤 답변/지식이 좋은지 자동 판단의 1차 재료 |

---

## 1. 배경 / 문제 (실코드 확인)

- 관측성(retrieval-observability, V046): `ai_run`·`ai_retrieval_source`가 "검색·LLM 호출"을 기록하고 `GET /conversations/messages/{id}/retrievals`로 메시지→run 조회 가능 — **행위**는 추적되나 **평가**는 없음.
- `ConversationMessage.id`(도메인 `MessageId`) + 프론트 `Message.id` 존재 → 답변 메시지 단위 평가 부착 가능.
- admin 대시보드(admin-dashboard, 2026-07-18)가 usage 집계·위젯 구조 보유 → 만족도 위젯 추가 지점 존재.
- ragas는 오프라인 RAG 평가 데이터셋 — 사용자 실시간 피드백과 별개(혼동 금지).

## 2. 목표 / 범위

### In Scope (신호 수집 계층)

1. **평가 저장** — `message_feedback`(신규 테이블 V052): message_id·user_id·rating(up/down)·comment(선택)·agent_id·created_at. 동일 사용자 재평가는 upsert(마지막 값)
2. **API** — `POST /conversations/messages/{id}/feedback`(up/down/취소) + `GET .../feedback`(본인 값). 인증 필수, 본인 것만
3. **집계** — 에이전트별 만족도(👍/(👍+👎))·평가 수·최근 부정 피드백 N건 조회 (admin)
4. **프론트** — 채팅 assistant 메시지에 👍/👎 토글(낙관적 반영) + admin 대시보드 만족도 위젯

### Out of Scope

- 평가 신호로 **자동 환류/메모리 추출 우선순위 조정**(다음 축 — 이건 신호 수집만)
- 답변 자동 재생성·A/B
- 코멘트 자연어 분석/분류
- 실시간 알림

## 3. 요구사항

| ID | 요구사항 | 비고 |
|----|----------|------|
| FR-01 | assistant 메시지에 up/down 평가 저장, 동일 사용자 재평가 upsert | message_id 키 |
| FR-02 | 평가 취소(토글 off) 지원 — 삭제 or null | |
| FR-03 | 본인 평가만 조회·수정 (401/404 은닉 — 메모리 계약 계승) | |
| FR-04 | agent_id 함께 저장 — 에이전트별 집계 위해 (메시지에서 파생) | general-chat sentinel 포함 |
| FR-05 | 관리자 집계: 에이전트별 만족도·평가 수·최근 부정 N건 | admin 권한 |
| FR-06 | 채팅 UI 낙관적 토글(👍/👎), 실패 시 롤백 | |
| FR-07 | 평가 저장 실패가 채팅 흐름을 막지 않음 | best-effort |

## 4. 성공 기준

- Match ≥ 90%, 기존 conversation·observability 회귀 0
- 답변 평가 → 저장 → 집계 반영 전 구간 단위 테스트

## 5. 리스크

| 리스크 | 완화 |
|--------|------|
| message_id가 프론트에 안정적으로 노출되는지 | Design에서 대화 히스토리 응답의 message id 실측 — 스트리밍 답변의 id 확보 시점 확인 |
| agent_id 파생 | 메시지 저장 시 이미 agent_id 보유(ConversationMessage.agent_id) — 재사용 |
| 평가 남용/조작 | 본인 1메시지 1평가(upsert) + 인증 필수 |
| 집계 쿼리 비용 | message_feedback(agent_id, rating) 인덱스 |

## 6. Design 이월 결정

| # | 결정 대상 | 후보 |
|---|-----------|------|
| ① | 평가 부착 키 | conversation message_id vs ai_run run_id (메시지가 사용자 대면 단위 → message_id 유력) |
| ② | 취소 표현 | 행 삭제 vs rating=null 상태 유지 |
| ③ | 집계 API 위치 | admin_dashboard 확장 vs 신규 엔드포인트 |
| ④ | 스트리밍 답변 id 확보 | ANSWER_COMPLETED에 assistant message_id 추가 노출 vs 히스토리 재조회 |

## 7. 참조

- 메시지·관측성: `ConversationMessage`(id·agent_id) · `GET /conversations/messages/{id}/retrievals`(retrieval-observability) · [[retrieval-observability-completed]]
- 집계 선례: admin-dashboard · usage API
- 계약 패턴: 메모리 CRUD(401/404 은닉·본인만) — [[project-agent-memory-completion]]
- 비전: `docs/architecture/growing-agent-vision.md` 측정 게이트
