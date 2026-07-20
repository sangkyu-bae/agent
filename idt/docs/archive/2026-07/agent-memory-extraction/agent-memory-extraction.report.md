# agent-memory-extraction Completion Report (메모리 Phase 2)

> **Feature**: agent-memory-extraction — 대화 자동 메모리 추출 + 승인 게이트
> **Author**: 배상규
> **Cycle**: Plan → Design → Do → Check → Report (2026-07-20 당일 완결)
> **Match Rate**: 1차 97% → 갭 당일 보강 → **100%** (Act 0회)

---

## Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| Feature | agent-memory-extraction (growing-agent 메모리 축 2단계) |
| 기간 | 2026-07-20 (Plan→Report 당일 사이클) |
| 산출물 | 백엔드 신규 3 + additive 8 · 프론트 additive 7 · **마이그레이션 0** (Phase 1 예약 컬럼) |
| Match Rate | 100% — 구현 결함 0, 감점은 테스트 커버리지 3건뿐(당일 해소) |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| 신규/확장 테스트 | 125건 (백엔드 108 + 프론트 17) — 전부 통과 |
| 기존 회귀 | 0건 (general_chat 25/25 전체 통과, Phase 1 memory 스위트 확장 통과) |
| Act 반복 | 0회 (1차 97% → 테스트 3건 보강 → 100%) |
| 배포 위험 | 0 — `memory_extraction_enabled=False` 기본, off 시 Phase 1과 100% 동일 |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | Phase 1 메모리는 사용자가 직접 옮겨 적어야만 쌓였다 — 대화에서 반복 드러나는 배경 정보로는 에이전트가 성장하지 못함 |
| **Solution** | 답변 완료 후 백그라운드 LLM 추출(fire-and-forget, 실패 격리) → `pending` 적재 → 사용자 승인 시에만 주입 대상. 마이그레이션 0으로 Phase 1 스키마 선반영의 배당을 회수 |
| **Function UX Effect** | 채팅 지연 0(sync kickoff 즉시 반환). `/settings` "승인 대기 N건" 앰버 카드 — 원클릭 승인/거부, 승인 즉시 다음 질문부터 반영, 거부는 재노출 없음 |
| **Core Value** | growing-agent 7원칙 "인간 승인 게이트 + 출처 불변식(source_run_id)"의 메모리 축 완성 — 자동 학습과 금융 도메인 보수성(무단 학습 금지) 양립. 위키(distill→승인)와 메모리(추출→승인) 양 축이 동형 구조로 정렬됨 |

---

## 2. 구현 결과

- **추출 파이프라인**: general_chat `_finish_observability` 직후 `kickoff()` — launcher 가드 패턴(_tasks 보관+done_callback), pending 상한 도달 시 **LLM 호출 자체 스킵**, 마지막 턴 4000자 절단, chart-edit 턴 제외
- **추출기**: WikiDistiller 동형(JSON 배열 강제·코드펜스/블록 리스트 정규화·파싱 실패 `[]`) + 프롬프트 규칙 4종(지속 사실만/중복 금지/**PII 금지**/빈 배열 허용)
- **정합**: 기존 active+pending을 프롬프트 제공 + `dedup_candidates`(strip 일치) 코드 차단 — 위키 distill의 중복 검사 부재 실수 미반복
- **승인 게이트**: `validate_transition`(pending만) + 승인 시 active 상한 재검증, 404 은닉·422 계약 Phase 1 승계
- **프론트**: `GET ?status=pending` + approve/reject 훅(`memories.all` invalidate로 양 목록 동시 갱신) + PendingSection(0건 미렌더)

## 3. Lessons Learned

1. **repo update() 화이트리스트 함정을 CC 메모리로 선제 차단** — Phase 1 update가 mem_type/content만 써서 status 전이가 조용히 미저장될 뻔. 과거 세션의 "4곳 세트" 교훈이 실제 결함을 구현 중에 잡았고, 회귀 테스트로 고정.
2. **읽기 세션과 쓰기 세션은 다르다** — assembler(읽기)는 `session_factory()`만으로 충분하지만 쓰기는 `async with session.begin():`(RunTracker 선례) 필수. 누락 시 저장이 조용히 유실.
3. **스키마 선반영의 배당** — Phase 1에서 status/source_run_id/confidence를 미리 넣어둔 덕에 Phase 2가 마이그레이션 0·당일 사이클로 완결.
4. **gap-detector 감점이 전부 테스트 커버리지**였다는 것 = 설계 §4 테스트 플랜을 구현 중 체크리스트로 쓰면 1차 100%도 가능.

## 4. 이월 항목

| 항목 | 비고 |
|------|------|
| E2E 실측 | `.env` on → 채팅 → pending → 승인 → 주입 확인 — KB 공통 체크리스트 합류 |
| Phase 3 후보 | run 딥링크 근거 표시, pii_masking 엔진 연동, org 스코프, expires_at 만료 배치 |
| 운영 결정 | 검증 후 `memory_extraction_enabled=True` 전환 시점 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-20 | 당일 사이클 완결 — Match 100%, 회귀 0, 마이그레이션 0 | 배상규 |
