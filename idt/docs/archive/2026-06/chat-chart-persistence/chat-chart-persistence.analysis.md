# Gap Analysis: chat-chart-persistence

> Analyzed: 2026-06-10 | Phase: Check (gap-detector)
> Design: `idt/docs/02-design/features/chat-chart-persistence.design.md`
> Plan: `idt/docs/01-plan/features/chat-chart-persistence.plan.md`

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 100% | ✅ |
| Architecture Compliance | 100% | ✅ |
| Convention Compliance | 100% | ✅ |
| **Overall** | **100%** | ✅ |

> 검증 항목 8개 + 설계결정 9개(D1~D9) 전부 Full Match, 역방향 Gap 없음, 전 레이어 테스트 커버. 90% 게이트 초과.

---

## 검증 기준별 결과 (Design §6)

| # | 기준 | 구현 위치 | 결과 |
|---|------|-----------|:----:|
| 1 | V031 마이그레이션 존재 + `charts JSON NULL` | `db/migration/V031__...sql:1-3` — `ADD COLUMN charts JSON NULL COMMENT` | ✅ |
| 2 | ORM charts 컬럼 / 매퍼 양방향 / 엔티티 기본값 None | `models/conversation.py:30` (`JSON, nullable=True`), `conversation_mapper.py:49,71` (to_entity/to_model 양방향), `entities.py:57` (`= None`) | ✅ |
| 3 | Agent Run: 차트 런 charts 저장, 비차트 런 NULL | `run_agent_use_case.py:244-246` (`charts=state.charts or None`), `_save_assistant_message:804,824` (키워드 전용 charts) | ✅ |
| 4 | General Chat: 차트 생성→저장 순서 + charts 저장 | `general_chat/use_case.py:201-208` (build→persist 순서), `_persist_messages:453,471` | ✅ |
| 5 | 이력 API 2종 응답 charts (있음=배열/없음=null) | `conversation_history_router.py:40` (MessageItemAPI.charts), `:137`·`:226` (양 엔드포인트 전달); `history_use_case.py:73,187` (MessageItem charts 패스스루) | ✅ |
| 6 | LLM 컨텍스트에 charts 미포함 (D7) | `run_agent_use_case.py:704-706`·`general_chat/use_case.py:506-510,521-525` — 모두 `msg.content`만 사용, charts 미참조 | ✅ |
| 7 | 프론트 이력 로드 → MessageBubble 차트 복원 | `types/chat.ts:108-109` (HistoryMessageItem.charts), `chatService.ts:38` (toMessage 매핑), `:81,103` (양 메서드 toMessage 경유) | ✅ |
| 8 | 기존 테스트 회귀 없음 | 신규 charts 필드 모두 기본값 None/맨뒤 추가 → 기존 위치인자 호출부 무변경. 사전 실패(api 28·infra 30)는 별건 | ✅ |

---

## 설계 결정 준수 (D1~D9)

| # | 결정 | 구현 근거 | 결과 |
|---|------|-----------|:----:|
| D1 | JSON nullable 컬럼 1개, 배열 통째 직렬화 | `models/conversation.py:30` `Mapped[Optional[list]]` + JSON | ✅ |
| D2 | 빈 배열 금지 (None 저장) | `entities.py:63-64` (`len==0` → ValueError); 저장부 모두 `charts or None` (`run_agent:246`, `general_chat:207`) | ✅ |
| D3 | 저장 레이어 개수 상한 없음 (`chart_max_count=3` 생성단이 유일) | `config.py:81`; 저장/매퍼 어디에도 상한 로직 없음 | ✅ |
| D4 | General Chat: build_charts → persist 순서 + 파라미터 | `general_chat/use_case.py:201-208` | ✅ |
| D5 | Agent Run: `_save_assistant_message(..., charts=state.charts or None)` 키워드 전용 | `run_agent_use_case.py:244-246,804` | ✅ |
| D6 | 엔티티 frozen dataclass 맨 뒤 기본값 None | `entities.py:56-57` | ✅ |
| D7 | charts LLM 컨텍스트/요약 미투입 | 3개 context builder(`run_agent:_build_messages`, `general_chat:_build_full_context`/`_build_summarized_context`) 모두 content만; 테스트 고정(`test_use_case.py:569`, `test_run_agent_use_case_stream.py:756`) | ✅ |
| D8 | user 메시지 charts=None | `general_chat/use_case.py:461-465` (user_msg charts 미전달), `run_agent_use_case.py:766-775` (user_msg charts 미전달) | ✅ |
| D9 | 스트리밍 이벤트 스키마 무변경 | `ANSWER_COMPLETED.payload["charts"]` 기존 그대로 (`run_agent:249-250`, `general_chat:217`) | ✅ |

---

## 테스트 커버리지

| 레이어 | 테스트 | 핵심 케이스 |
|--------|--------|-------------|
| domain (entity) | `tests/domain/test_conversation_entities.py:129-174` | 기본값 None, N개 보존, 빈 배열 거부(D2) |
| domain (schema) | `tests/domain/conversation/test_history_schemas.py:70-88` | MessageItem.charts 기본 None/리스트 보존 |
| infrastructure | `tests/infrastructure/test_conversation_mappers.py:121-179` | round-trip(list↔JSON, NULL↔None) 양방향 |
| application (agent) | `tests/application/agent_builder/test_run_agent_use_case_stream.py:699-753` | 차트 런 저장, 비차트 런 None(D2), D7 컨텍스트 미투입 |
| application (general) | `tests/application/general_chat/test_use_case.py:516-587` | 생성→저장 순서, user None(D8), 빌드 실패 graceful, D7 |
| application (history) | `tests/application/conversation/test_history_use_case.py:96-101` | charts 패스스루 |
| interfaces | `tests/api/test_conversation_history_router.py:96-130`, `test_agent_conversation_history_router.py:160-186` | 두 엔드포인트 직렬화(배열/null) |
| frontend | `chatService.test.ts:125-168` (C6 배열 매핑/C7 부재 하위호환), `handlers.ts:285-321` (MSW charts 필드) | 이력 복원 매핑 |

**테스트 결과**: 백엔드 442 passed + interfaces 21 passed (회귀 없음), 프론트 대상 28 passed + `tsc --noEmit` 통과.

---

## 발견된 Gap

- 🔴 **Missing** — 없음
- 🟡 **Added (설계에 없는 구현)** — 없음
- 🔵 **Changed** — 없음

설계상 모든 변경 파일이 명세대로 구현됨. 역방향 누수 없음.

---

## 권장 조치

### 즉시 — 없음
구현이 Design 전 항목·전 설계결정과 일치. 아키텍처(domain→infra 누수 없음, charts는 `list[dict]` 원시타입으로 도메인 전달 — Chart.js 스키마 비노출, §7 준수)·컨벤션(snake_case, 명시적 타입, frozen dataclass) 준수.

### 선택 (다듬기, 비차단)
1. **MSW 기본 핸들러 차트-present 케이스**: `handlers.ts`의 두 이력 핸들러는 `charts: null`만 제공. 차트-배열 복원 경로는 `chatService.test.ts:125` C6 테스트가 `server.use` 오버라이드로 이미 커버하므로 공백 없음. 통합/스토리북 레벨에서 배열 케이스를 더 노출하고 싶으면 기본 핸들러에 1건 추가 고려(선택).

### 운영 적용 시 주의 (코드 Gap 아님)
- **V031 마이그레이션 DB 미적용**: 파일은 생성됐으나 실제 MySQL에는 `ALTER TABLE` 미적용. 운영/로컬 DB 적용 + 서버 재기동 후에야 저장 동작.
- 기존 row charts는 NULL — 과거 차트 소급 복원 없음 (Plan N4 합의).

---

## 결론

Design ↔ 구현 일치도 **100%** (90% 게이트 초과). 동기화 불필요.
다음 단계: `/pdca report chat-chart-persistence` 진행 가능.
