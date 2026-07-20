# agent-eval-gate — Completion Report

> **Feature**: agent-eval-gate — 답변 사용자 평가 수집 + 품질 측정 게이트
> **Author**: 배상규
> **Date**: 2026-07-20
> **Status**: ✅ Completed (Match Rate 97%)
> **비전 근거**: growing-agent 7원칙의 **측정 게이트(measurement gate)** — 성장 축의 마지막 미착수 축 완성

---

## 1. Executive Summary

### 1.1 개요

| 항목 | 값 |
|------|-----|
| Feature | agent-eval-gate |
| 기간 | 2026-07-20 (Plan → Design → Do → Check → Report 단일 세션) |
| PDCA Phase | Report (완료) |
| Match Rate | **97%** (Critical 0 · Major 0 · Minor 5) |
| 회귀 | general_chat 25/25 유지 (튜플 변경 무회귀) |

### 1.2 결과 지표

| 지표 | 값 |
|------|-----|
| 신규 백엔드 소스 | domain/eval · infrastructure/eval · application/eval · eval_router · V052 (≈544 LOC) |
| 백엔드 테스트 | **30 passed** (domain 8 · repository 6 · use_cases 7 · router 9) |
| general_chat 통합 | `_persist_messages` 튜플 반환 + ANSWER_COMPLETED `assistant_message_id` — 회귀 0, G2 검증 테스트 2건 추가 (10 passed) |
| 신규 프론트 소스 | types · service · hooks · MessageFeedback · AgentSatisfactionPanel (≈219 LOC) |
| 프론트 테스트 | MessageFeedback 3 · AgentSatisfactionPanel 3 · useChatStream/streamRouting 회귀 (25 passed) |
| 신규 API | feedback 3종(POST/GET/DELETE) + admin 집계 2종 |
| DB | V052 `message_feedback` (UNIQUE(message_id,user_id) · INDEX(agent_id,rating)) |

### 1.3 Value Delivered (4-관점)

| 관점 | 계획 | 실제 전달 |
|------|------|-----------|
| **Problem** | 답변의 좋고 나쁨을 측정할 사용자 신호 부재 | ✅ 답변(assistant 메시지) 단위 👍/👎 + 코멘트 신호 저장 계층 확보 — 관측성(행위)에 이어 **평가**를 기록 |
| **Solution** | message_id 기반 평가 저장 + 에이전트별 만족도 집계 | ✅ `message_feedback`(V052) upsert/취소 토글, `EvalPolicy.satisfaction`(0건 None), 신규 `/api/v1/admin/eval/*` 집계 라우터 |
| **Function UX Effect** | 답변 아래 👍/👎, 관리자 만족도 위젯 | ✅ MessageBubble 평가 버튼(히스토리 numeric id + 스트리밍 `assistant_message_id` 양방향), AdminDashboard 만족도%+최근 부정 피드백 위젯 |
| **Core Value** | growing-agent 측정 게이트 완성 | ✅ "모델 고정·데이터 성장"의 성장 방향을 정하는 1차 신호(사용자 평가) 확보 — 이후 환류/추출 우선순위의 입력 |

---

## 2. 구현 요약 (Plan 이월 결정 4건)

| # | 결정 | 확정·구현 |
|---|------|-----------|
| ① | 평가 부착 키 | **conversation message_id** — `ConversationMessage.id`(MessageId) 재사용 |
| ② | 취소 표현 | **행 삭제 토글** — 같은 rating + 코멘트 없음 재클릭 시 delete, 아니면 upsert |
| ③ | 집계 API 위치 | **신규 eval 라우터** `/api/v1/admin/eval/*` (admin) — dashboard 라우터 비대화 방지 |
| ④ | 스트리밍 답변 id | **ANSWER_COMPLETED additive `assistant_message_id`** — `_persist_messages`의 `save()` 반환 id 캡처(기존 폐기 값), 실패 시 None(FR-07) |

### 요구사항 충족 (FR-01~07)

| ID | 상태 |
|----|------|
| FR-01 up/down upsert (message_id 키) | ✅ |
| FR-02 평가 취소 토글 | ✅ (행 삭제) |
| FR-03 본인만 조회·수정 (401/404 은닉) | ✅ |
| FR-04 agent_id 파생 저장 (general-chat 포함) | ✅ |
| FR-05 admin 집계(만족도·평가수·최근 부정 N) | ✅ |
| FR-06 채팅 UI 토글 | ✅ (서버 왕복 캐시 갱신 방식 — G1, 아래) |
| FR-07 저장 실패가 채팅 흐름 미차단 | ✅ (`_message_id_of` None 폴백) |

---

## 3. Gap 처리 (Check 97% → Report)

| # | Gap | 심각도 | Report 반영 |
|---|-----|--------|-------------|
| G1 | FR-06 "낙관적+롤백" → 실제 "서버 왕복 후 캐시 갱신" | Minor | 의도적 대체(중복 방지 `isPending` disabled). 낙관적 미도입은 후속 개선 여지로 기록 |
| G2 | ANSWER_COMPLETED payload `assistant_message_id` 명시 검증 부재 | Minor | ✅ **Check 단계에서 테스트 2건 보강 완료** |
| G3 | UC 테스트 파일 병합(`test_use_cases.py`) | Minor | 케이스 동등 — 설계 문구만 상이, 기능 영향 없음 |
| G4 | `DeleteFeedbackUseCase` 설계 UC 목록 누락 | Minor | 추가 구현, DELETE 엔드포인트와 정합 |
| G5 | 취소 토글 `comment is None` 가드 | Minor | 코멘트 동반 시 갱신 유지(additive) |

**미구현 항목 없음. 잔여 전부 Minor(문서-구현 문구 정합).**

---

## 4. 아키텍처 / 컨벤션

- Thin DDD 준수: domain/eval 외부 의존 0, repository `flush()`만(commit 없음), 라우터 비즈니스 로직 없음
- MySQL FK/COLLATE 미명시(V037 선례), ENGINE=InnoDB
- BE↔FE 계약 동기화: `up`/`down` · `satisfaction` null · `message_id` · `assistant_message_id`
- 프론트: queryKey 팩토리(`queryKeys.eval`), 엔드포인트 상수화, presentation→hook→service 계층

---

## 5. 배포 / 이월 (Out of Scope)

| 항목 | 비고 |
|------|------|
| **V052 마이그레이션 배포** | 배포 전 필수 (message_feedback 테이블) |
| E2E 수동 검증 | Qdrant/ES 기동 시 일괄 체크리스트에 편입 |
| agent(비 general-chat) 경로 평가 연동 | `ChatPage` `assistantMessageId: null` — 후속 |
| 평가 신호 기반 자동 환류/추출 우선순위 | 다음 성장 축 (본 기능은 신호 수집만) |

---

## 6. 학습 포인트

- **폐기되던 반환값 캡처 패턴**: `_persist_messages`가 이미 `save()` 결과를 받았으나 버리고 있었음 → 캡처만으로 스트리밍 즉시 평가 가능(결정 ④). "데이터는 있고 노출 경로만 없던" 반복 패턴.
- **평가 대상 id 양방향 해석**: 히스토리 메시지(서버 numeric id)와 방금 스트리밍된 메시지(`feedbackMessageId`)를 `feedbackId()` 단일 로직으로 통합 — placeholder(UUID)는 자연히 미노출.
- **취소=행 삭제**의 단순성: rating=null 상태 관리 대신 존재 행만 집계 → 상태 없음.

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-20 | 완료 보고 (Match 97%, 백엔드 30 + 프론트 6 테스트, V052 배포 이월) | 배상규 |
