# PDCA Report: chat-chart-persistence

> Generated: 2026-06-10
> Phase: Completed (Report)
> Match Rate: 100%
> Scope: 풀스택 (`idt/` 백엔드 + `idt_front/` 프론트엔드)

---

## Executive Summary

### 1.1 Overview

| 항목 | 내용 |
|------|------|
| **Feature** | chat-chart-persistence |
| **기간** | 2026-06-10 (Plan → Design → Do → Check → Report, 단일 세션) |
| **유형** | 풀스택 데이터 영속화 (버그성 결함 수정 + 스키마 확장) |
| **레이어** | DB migration · domain · infrastructure · application · interfaces · frontend |

### 1.2 Results

| 지표 | 값 |
|------|-----|
| **Match Rate** | 100% (Gap: Missing 0 / Added 0 / Changed 0) |
| **검증 기준** | 8/8 충족 |
| **설계 결정 준수** | D1~D9 전부 ✅ |
| **변경 파일** | 백엔드 9 + 프론트 3 = 12 |
| **테스트** | 백엔드 442 + interfaces 21 passed, 프론트 28 passed + `tsc --noEmit` 통과 |
| **신규 테스트** | 22건 (domain 7 · infra 4 · app 8 · interfaces 2 · frontend 2 — 합산 시 케이스 단위 기준) |

### 1.3 Value Delivered

| 관점 | 내용 | 실측 |
|------|------|------|
| **Problem** | 차트(`state["charts"]`)가 `ANSWER_COMPLETED` 스트리밍 이벤트로만 전달되고 assistant 메시지 저장에는 텍스트만 영속화 → 채팅방 재진입 시 차트 영구 소실 | 유실 지점 4개 확정 (테이블 컬럼·엔티티·이력 API·프론트 매핑) |
| **Solution** | `conversation_message.charts` JSON nullable 컬럼(V031) 신설, Agent Run·General Chat 양 경로에서 N개 차트 배열 영속화, 이력 API 2종 → 프론트 `Message.charts` 복원 | 12개 파일, 단일 JSON 컬럼으로 스키마 변경 최소화 |
| **Function UX Effect** | 재진입 시 과거 턴 차트가 기존 `MessageBubble`로 그대로 복원. 라이브 스트리밍 UX·이벤트 스키마 무변경 | 프론트 렌더링 코드 변경 0 (toMessage 매핑만 추가) |
| **Core Value** | 차트가 일회성 시각 효과가 아닌 대화 기록의 일부가 됨. charts는 표시 전용 메타로 LLM 컨텍스트·요약 정책 불변 | D7 회귀 방지 테스트로 메모리 정책 보존 고정 |

---

## 2. PDCA 진행 경과

| Phase | 산출물 | 결과 |
|-------|--------|------|
| **Plan** | `docs/01-plan/features/chat-chart-persistence.plan.md` | 유실 지점 코드 근거 확정, 3개 해결안 비교 후 JSON 컬럼 채택 |
| **Design** | `docs/02-design/features/chat-chart-persistence.design.md` | 설계 결정 D1~D9 확정, 8단계 TDD 순서 정의 |
| **Do** | 구현 12파일 + 테스트 22케이스 | Red→Green 사이클 6회, 전 레이어 TDD |
| **Check** | `docs/03-analysis/chat-chart-persistence.analysis.md` | Match Rate 100%, Gap 0건 |
| **Report** | 본 문서 | 완료 |

---

## 3. 구현 상세

### 3.1 백엔드 (`idt/`)

| 레이어 | 파일 | 변경 |
|--------|------|------|
| migration | `db/migration/V031__alter_conversation_message_add_charts.sql` | `ADD COLUMN charts JSON NULL` (신규) |
| infrastructure | `src/infrastructure/persistence/models/conversation.py` | `charts: Mapped[Optional[list]]` (JSON) |
| infrastructure | `src/infrastructure/persistence/mappers/conversation_mapper.py` | 엔티티↔모델 charts 양방향 |
| domain | `src/domain/conversation/entities.py` | `ConversationMessage.charts` 필드 + 빈 배열 거부(D2) |
| domain | `src/domain/conversation/history_schemas.py` | `MessageItem.charts` |
| application | `src/application/agent_builder/run_agent_use_case.py` | `_save_assistant_message(charts=state.charts or None)` |
| application | `src/application/general_chat/use_case.py` | 차트 생성→저장 순서 변경(D4) + `_persist_messages(charts)` |
| application | `src/application/conversation/history_use_case.py` | MessageItem charts 패스스루 (2곳) |
| interfaces | `src/api/routes/conversation_history_router.py` | `MessageItemAPI.charts` + 엔드포인트 2곳 전달 |

### 3.2 프론트엔드 (`idt_front/`)

| 파일 | 변경 |
|------|------|
| `src/types/chat.ts` | `HistoryMessageItem.charts` |
| `src/services/chatService.ts` | `toMessage` charts 매핑 (null/빈 배열 생략) |
| `src/__tests__/mocks/handlers.ts` | 이력 MSW charts 필드 |
| `MessageBubble.tsx` | **무변경** — 기존 차트 렌더링 재사용 |

---

## 4. 핵심 설계 결정 (D1~D9)

- **D1**: JSON nullable 컬럼 1개, N개 배열 통째 직렬화
- **D2**: 빈 배열 금지 → None 저장 (엔티티 검증 + 저장부 `charts or None` 이중 보장)
- **D3**: 저장 레이어 개수 상한 없음 — 생성단 `chart_max_count`(config)가 유일 상한
- **D4**: General Chat 차트 생성 → 저장 순서로 변경
- **D5**: Agent Run `_save_assistant_message` 키워드 전용 charts
- **D6**: frozen dataclass 맨 뒤 기본값 None → 기존 호출부 무변경 하위호환
- **D7**: charts는 LLM 컨텍스트/요약에 미투입 (메모리 정책 보존)
- **D8**: user 메시지 charts=None
- **D9**: 스트리밍 이벤트 스키마 무변경

---

## 5. 학습 / 회고

### 5.1 잘된 점
- **유실 지점 사전 확정**: Plan 단계에서 테이블·엔티티·API·프론트 4개 지점을 코드 라인으로 짚어 구현 범위 누락 없음.
- **General Chat 순서 문제 발견**: 단순 "저장 시 charts 추가"로는 부족 — 저장이 차트 생성보다 먼저인 구조적 문제를 Design에서 미리 잡아 D4로 해결.
- **하위호환 설계**: 모든 신규 필드를 맨 뒤 기본값 None으로 추가해 기존 위치 인자 호출부·테스트 무변경 → 회귀 0.
- **메모리 정책 보존 고정**: D7을 테스트로 명시 고정해 향후 charts가 LLM 컨텍스트로 새는 회귀를 차단.

### 5.2 주의 / 후속
- **V031 DB 미적용**: 마이그레이션 파일만 생성됨. 운영/로컬 MySQL에 `ALTER TABLE` 적용 + 서버 재기동 필요. (코드 Gap 아님)
- **과거 차트 소급 불가**: 기존 row charts는 NULL. 이미 유실된 차트는 재생성하지 않음 (Plan N4 합의).
- **Excel Standalone 경로 범위 외**: `analysis_router`는 대화 세션이 아니므로 본 기능 대상 아님 (Plan N3).

### 5.3 향후 개선 후보
- MSW 기본 핸들러에 charts-배열 케이스 1건 추가 (현재 C6 테스트가 오버라이드로 커버, 비차단).
- 차트 영속화를 Supervisor 멀티턴 차트 렌더 확장(별도 feature)과 연계 검토.

---

## 6. 다음 단계

- (선택) `/simplify` — 코드 정리
- `/pdca archive chat-chart-persistence` — 완료 문서 아카이브
- **운영 배포 전**: V031 마이그레이션 DB 적용 필수
