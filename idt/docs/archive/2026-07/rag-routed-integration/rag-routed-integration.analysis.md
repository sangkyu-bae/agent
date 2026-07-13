# rag-routed-integration Gap Analysis (Check)

> **Design**: `docs/02-design/features/rag-routed-integration.design.md` (D1~D11)
> **Plan**: `docs/01-plan/features/rag-routed-integration.plan.md` (개정판 — FR-01~10, NFR-01~07)
> **Analyzer**: gap-detector Agent (풀스택 — idt + idt_front)
> **Date**: 2026-07-09
> **Match Rate**: **96% → 즉시 조치 후 99%**

---

## 1. 점수 요약

| 카테고리 | 가중치 | 점수 | 상태 |
|----------|:------:|:----:|:----:|
| 설계 결정 D1~D11 | 60% | 98% (11/11 반영, D2 배선 문구 편차 1) | ✅ |
| 흐름·계약 (§4/FR-03/FR-06) | 20% | 97% | ✅ |
| 테스트 계획 (§5) | 20% | 92% → 보강 후 완결 | ✅ |
| **종합** | | **96% → 99%** | ✅ (≥90% — iterate 불요) |

## 2. 핵심 검증 결과 (요지)

- **FR-03 (기준선 바이트 동일)**: false 시 분기 블록 미진입 — 기존 3모드 테스트 무수정 통과 + 전용 테스트로 이중 증명. **사용자 피드백(갈아끼우기 금지)의 코드 검증 완료**
- **FR-07 (권한 누수 0)**: visibility 강제 → `filter_incompatible` 강등 → 기존 경로에 `visibility=public` 유지(테스트 확인). RoutedScope는 kb_id/collection만 매핑 — 요약 payload 부재 키로 새지 않음
- **D4/D5**: 필터 3분류·강등 4사유 reason 코드 전부 정확 반영, viewer_department_ids 무시로 상시 강등 함정 회피
- **D6/D7**: 근거 헤더+요약 150자·폴백 기존 포맷·record_retrieval metadata(`search=routed`)·multi-query 우회 전부 일치
- **D9 프론트**: 타입/DEFAULT/토글(설계 문구 일치)/기존 라디오 불변 — RTL 3케이스
- FR-01 저장 경로: `create_agent_use_case`의 `config.model_dump()`가 필드 화이트리스트 없이 자동 전파(확인)

## 3. 발견된 Gap 및 조치 (전부 Low)

| # | Gap | 심각도 | 조치 (2026-07-09 즉시) |
|---|-----|:------:|------|
| G1 | D2 "생성처 전수" 문구 vs 미들웨어 ToolFactory 미연결 — 해당 팩토리는 hybrid getter도 없는 RAG 비실사용 컨텍스트(toggle=true여도 not_wired 안전 강등) | Low | **설계 D2 문구 갱신**(에이전트 빌더 한정 + 의도적 제외 사유 명시) — Do 단계 판단이 정당, 문서가 실제를 따름 |
| G2 | error 강등 로그가 `error=str(e)` — 스택 트레이스 손실(NFR-06 일관성) | Low | `exception=e`로 코드 수정(warning에 exception= 전달 — hybrid use_case 선례) |
| G3 | §5의 VO 단위 케이스(기본 False·부재 키 복원·직렬화 왕복) 미작성 — 팩토리 테스트로 간접 커버뿐 | Low | `test_rag_tool_config.py`에 3케이스 추가 |

조치 후 잔여 Gap **0건** (107건 재통과).

## 4. Plan 요구사항 충족

- **FR-01~FR-10 전부 충족**, NFR-01~07 준수(함수 40줄, print 0, 마이그레이션 0, 프론트 tsc 0·사전 실패 외 신규 실패 0)
- 설계에 없는 추가 구현/계약 위반 없음 (`_routed_source_label`의 optional 방어는 계약 범위 내)

## 5. 결론

Match Rate 96%(조치 후 99%) ≥ 90% — **Act(iterate) 불요, Report 진행 가능**.
사용자 피드백으로 개정된 구조(독립 opt-in·기준선 보존·교차검증)가 코드와 테스트로 완전히 구현됨.
