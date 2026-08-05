---
title: Supervisor 그래프 계약 — 워커 산출물 1건·목록 프레이밍 금지·강제 라우팅 범위
status: approved
reviewer: 배상규
source_type: conversation
source_refs:
  - idt/docs/archive/2026-07/worker-toolmessage-leak-fix/worker-toolmessage-leak-fix.report.md
  - idt/docs/archive/2026-07/data-inventory-requery/data-inventory-requery.report.md
  - 커밋 08d37cab (수퍼바이저 과차단 + 재질문 재검색 우회 수정)
  - 커밋 392d4637 (워커 트레이스 유출→고아 tool 400 방어)
  - idt/src/application/agent_builder/workflow_compiler.py (_wrap_worker, final_answer 필터)
confidence: 0.9
version: 1
created: 2026-08-03
updated: 2026-08-03
verified_at: 4f650d3c
---

Supervisor 그래프(에이전트 실행 경로)를 수정할 때 지켜야 할, 실장애로 검증된 계약 3가지.

## 1. 워커 산출물은 AIMessage(name=worker_id) 정확히 1건

- **장애**: 도구를 호출하는 react 워커의 내부 트레이스(tool_calls AIMessage + ToolMessage +
  최종 AIMessage)가 supervisor state로 통째로 유출 → final_answer의 필터가 AIMessage만
  제거해 **ToolMessage가 고아로 잔류** → OpenAI 400
  (`role 'tool' must be a response to a preceding message with 'tool_calls'`)로 런 전체 실패.
- **계약**: `_wrap_worker`는 react 결과의 최종 content로 `AIMessage(name=worker_id)` 1건만
  재생성해 반환한다. search/analysis/sub_agent/document_extractor는 원래 준수 —
  새 워커 래퍼를 만들 때 이 규약부터 확인. 2차 방어로 final_answer의 conversation 필터가
  tool 타입 메시지도 제거하며, token_delta는 신규 산출분 기준으로 계산한다.
- 멀티턴에서는 state에 남은 고아 tool 메시지가 **후속 턴까지 오염**시키므로 1차 차단이 핵심.

## 2. 프롬프트에 "할 수 있는 것 목록"을 주지 마라 (목록 프레이밍은 방어 지시를 이긴다)

- **장애**: 수퍼바이저 프롬프트에 권한/기능 목록을 넣자 LLM이 목록 밖 요청을 전부
  거부(과차단)했다. "목록에 없어도 위임하라"류 방어 지시는 목록 프레이밍을 이기지 못한다.
- **수정**: 권한 목록 제거 + 위임 가드 + 결정 프롬프트의 2차 방어선 (커밋 08d37cab).
- **적용**: 라우팅/위임 프롬프트는 화이트리스트 나열 대신 "기본은 위임, 예외만 명시" 프레임으로.

## 3. 결정적 강제 라우팅은 "현재 턴 수집분"에만 반응

- **장애**: 이전 턴 검색결과 재주입분이 `is_search_result()`를 통과해 분석 워커 강제 라우팅을
  트리거 → 범위 확대 재질문("전체 사용자")에서 재검색 기회 자체가 사라져 오응답.
- **계약**: 재주입분(REINJECTED_MARKER)은 강제 라우팅 트리거에서 제외. 재사용 vs 재수집
  판단은 보유 데이터 인벤토리 블록([이번 턴 수집/이전 턴 보유] + 원 질문 + 출처)을 근거로
  **LLM이 수행**한다. 결정적 라우팅=확실한 신호 전용, 불확실 판단=LLM — 책임 분리.
- **교차 회귀 주의**: `is_search_result` 같은 규약은 첨부 라우팅·데이터 연속성·시각화가
  공유한다. 규약을 바꾸면 소비자 전수를 확인할 것 (한 기능의 수정이 다른 기능을 깬 선례).
