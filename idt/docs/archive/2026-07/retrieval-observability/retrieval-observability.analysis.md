# Gap Analysis: retrieval-observability

> **Design**: [retrieval-observability.design.md](../02-design/features/retrieval-observability.design.md) (v0.1)
> **Plan**: [retrieval-observability.plan.md](../01-plan/features/retrieval-observability.plan.md)
> **Analyzed**: 2026-07-10 (gap-detector agent)
> **Match Rate**: **100%** (41/41 — Match 41 / Partial 0 / Missing 0 / Deviation 0)

---

## 1. 판정 요약

Design의 핵심 결정 D1~D9 전부, 컴포넌트/파일 수준 32개 항목 전부 구현 일치. 차단성 갭 없음.

### 1.1 Decision-level (D1~D9) — 9/9 Match

| Decision | 구현 위치 | 판정 |
|---|---|:--:|
| D1 run open 위치 (chart-edit 이후, start_run 실패 시 degraded) | `general_chat/use_case.py` `_begin_observability` | Match |
| D2 user_message_id deferred attach | `use_case.py` + `tracker.attach_user_message` + repo UPDATE | Match |
| D3 sentinel `GENERAL_CHAT_AGENT_ID = "general-chat"` | `use_case.py` 상수 | Match |
| D4 UsageCallback 생성 + astream_events config 부착 | `use_case.py` stream_kwargs | Match |
| D5 search_query = 엔진 투입 문자열 | `tools.py` 3개 경로 | Match |
| D6 multi_query fused hit 단위 + matched_queries | `tools.py` hit_queries 역맵 + `per_query_hits` | Match |
| D7 개별 점수 getattr / routed NULL | `tools.py` `_format_results` / `_record_routed_retrieval` | Match |
| D8 조회 API agent_run_router에 추가 | `agent_run_router.py` | Match |
| D9 search_mode / query_source 직교 분리 | migration 주석 + 각 경로 | Match |

### 1.2 Component-level — 32/32 Match

V046 마이그레이션(8컬럼 nullable), `RetrievalSource` 엔티티/ORM/매퍼 왕복, 인터페이스 2메서드,
`record_retrieval` 확장 kwargs, `attach_user_message` best-effort, `PerQueryHits` + zip 채움,
tool 3개 검색 경로의 기록 컨텍스트, general_chat 라이프사이클(begin/finish/fail/reset),
`get_run_tracker()` lazy singleton + HTTP/WS 공용 배선, 조회 UseCase/라우터/스키마/예외 — 전부 구현 일치.
상세 표는 gap-detector 실행 로그 참조.

### 1.3 아키텍처 & 계약 준수 — 전부 Pass

- domain → infrastructure 참조 없음
- Repository는 flush까지만 (commit은 tracker 세션 소유)
- best-effort 계약: 기록 실패가 채팅/검색 흐름을 차단하지 않음 (전부 warning-only)
- additive-only 하위호환 (전 필드 nullable/optional default)
- 대화 메모리 정책 불변 (deferred attach로 저장 시점·turn_index 무변경)

### 1.4 테스트 — Design §6 계획 11개 항목 커버

| 테스트 파일 | 커버 항목 | 결과 |
|---|---|:--:|
| `tests/application/agent_run/test_tracker_retrieval_context.py` | §6-1,2 | 통과 |
| `tests/application/multi_query/test_per_query_hits.py` | §6-3 | 통과 |
| `tests/application/rag_agent/test_tool_retrieval_context.py` | §6-4~6 | 통과 |
| `tests/application/general_chat/test_observability.py` | §6-7~9 | 통과 |
| `tests/api/test_message_retrievals_api.py` | §6-10 | 통과 (개별 실행) |
| 기존 회귀 스위트 (§6-11) | tests/domain + tests/application **3,628개 통과** | 통과 |

참고: tests/api 실행 중 간헐 소켓 에러(WinError 10014)는 변경 전 기준선(git stash)에서 동일 재현되는
기존 환경 이슈로 확인 — 신규 회귀 아님.

---

## 2. Gap 목록

**차단성 갭 없음.** Advisory 1건은 분석 직후 반영 완료:

| 심각도 | 내용 | 조치 |
|---|---|---|
| Low (반영됨) | `GeneralChatUseCase.__init__`의 `tracker: Any` — Design §4.4는 `RunTracker \| None` | `TYPE_CHECKING` 가드 import + `"RunTracker \| None"` 힌트로 수정, general_chat 64개 테스트 재통과 |
| Info | `_multi_query_search`가 `search_query=query`를 추가 전달 (Design 스니펫보다 보강) | 갭 아님 — D6 폴백을 실효화하는 올바른 개선 |
| Info | Plan의 `query_source=routed`는 Design D9에서 `search_mode=routed + query_source=original`로 정규화 | 구현은 Design 준수 — Plan↔Design 문서 차이일 뿐 |

---

## 3. 결론

- **Match Rate 100% ≥ 90%** → Act(iterate) 불필요, Report 진행 가능
- 배포 전 체크: DB에 **V046 마이그레이션 적용** 필요
- 후속(Out of Scope 확인): collection_search/wiki/hybrid 직접 API 배선, 프론트 근거 표시 UI(+타입 동기화)
