# agent-memory Completion Report (Phase 1)

> **Feature**: agent-memory — 사용자 메모리 CRUD + General Chat 상주 주입
> **Author**: 배상규
> **Cycle**: Plan(2026-07-16) → Design(2026-07-18) → Do(2026-07-20) → Check(2026-07-20) → Report(2026-07-20)
> **Match Rate**: **98%** (iterate 0회)

---

## Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| Feature | agent-memory (Phase 1 — growing-agent 로드맵 메모리 축 1단계) |
| 기간 | 2026-07-16 ~ 2026-07-20 (Do는 당일 완결) |
| 산출물 | 백엔드 12파일 + 테스트 6파일(57건), 프론트 9파일 + 테스트 2파일(10건), V050 마이그레이션 |
| Match Rate | 98% — Gap Low 1건(무해), 기능 누락·무단 추가 0 |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| 신규 테스트 | 67건 (백엔드 57 + 프론트 10) — 전부 통과 |
| 기존 회귀 | 0건 (general_chat 무수정 통과 · wiki 훅 7건 통과 · 변경 파일 tsc 에러 0) |
| 검증 스킬 | verify-architecture / verify-tdd / verify-logging 전부 PASS (신규 모듈 위반 0) |
| Act 반복 | 0회 (1차 Check 98%) |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | 사용자 배경(소속·용어 정의·답변 선호)을 매 대화마다 다시 설명해야 했고, AI가 무엇을 기억하는지 볼 수도 지울 수도 없었다 |
| **Solution** | 사용자가 직접 등록·수정·삭제하는 메모리 계층(V050) + General Chat 시스템 프롬프트 상주 주입 — 개수 상한 30·문자 예산 800으로 컨텍스트 폭주 구조 차단, 실패는 ""로 격리되어 채팅 무영향 |
| **Function UX Effect** | `/settings` "AI가 기억하는 내용"에서 타입 뱃지 목록·카운터(N/30)·인라인 수정·상한 안내를 제공 — 등록 즉시 다음 질문부터 답변에 반영되고, 삭제하면 즉시 사라지는 투명한 제어 |
| **Core Value** | growing-agent 7원칙 중 "컨텍스트 하드캡 + 투명성"의 첫 구현체 — Phase 2(자동 추출·승인 게이트)가 스키마 재작업 없이 얹히는 기반(tier/scope/status/source_run_id/confidence 선반영) |

---

## 2. PDCA 사이클 요약

### 2.1 Plan → Design에서 확정된 결정 5건

| # | 결정 | 확정안 |
|---|------|--------|
| ① | DDL·인덱스 | V050, `idx_memory_user_status(user_id,status)` 단일 복합 인덱스, VARCHAR enum, FK 없음 |
| ② | 에러 계약 | 401 / **타인·미존재 404 은닉** / 422 |
| ③ | 주입 지점 | `_create_agent(tools, auth_ctx, memory_block="")` — agent-user-context prepend 선례에 한 항 삽입 |
| ④ | 토큰 근사 | 한글 최악 1자≈1토큰 보수 근사 — 캡 800을 문자 예산으로 |
| ⑤ | 관리 UI | SettingsPage 신설 + `/settings` 라우트 (Plan의 "기존 존재" 전제를 실측으로 정정) |

### 2.2 구현 결과 (Do)

- **domain**: Memory 엔티티(3 Enum·12필드) + MemoryPolicy(CONTENT_MAX=500, TYPE_PRIORITY, truncate_to_budget) + 저장소 인터페이스
- **infrastructure**: MemoryModel(V050 정합) + MemoryRepository(search_history 경량 패턴, flush까지만)
- **application**: MemoryCrudUseCase(404 은닉) + MemoryContextAssembler(session_factory per-call, FR-05/06/07/09)
- **interfaces**: memory_router 4 엔드포인트 + config 2키(30/800) + main.py DI(assembler 싱글톤)
- **general_chat**: `memory_assembler` optional(None 기본) — **기존 테스트 무수정 통과로 회귀 0 입증**
- **front**: 계약 5종 동기화 + SettingsPage 신설 + `/settings` 라우트 + TopNav 진입점 + MSW 4종

### 2.3 Check 결과

- Match Rate 98%. Gap은 G1(모델 SMALLINT vs DDL TINYINT — production 무영향) 1건뿐.
- gap-detector가 제기한 G2(FR-07 로깅 스택트레이스)는 실코드 검증으로 **Gap 아님 확정** — StructuredLogger가 `exception=`을 `exc_info` 튜플로 변환해 기록.
- 정당한 편차 4건(스키마 파일 위치·repo_builder 옵션·프론트 상수 통합·수정 버튼 진입)을 분석 문서에 기록 — 재분석 시 오인 방지.

---

## 3. Lessons Learned

1. **optional 의존성(None 기본) 패턴의 3연승** — chart-builder → tracker → memory_assembler. 기존 테스트 무수정 통과가 "회귀 0"의 증명이 되는 구조라, 앱 싱글톤에 기능을 얹을 때의 기본형으로 굳어짐.
2. **설계 의사코드는 실행 환경 검증이 필요** — `datetime.min.timestamp()`가 Windows에서 OSError(이중 안정 정렬로 대체), 프론트 422 표면화는 authApiClient가 detail을 `ApiError(message)`로 변환하는 구조라 `err.message` 사용. 둘 다 계약은 유지하되 구현만 조정.
3. **테스트 마커는 헤더 문구와 겹치지 않게** — 절단 테스트의 "다"가 렌더 헤더 "다음은…"과 충돌. 한글 단일 문자 마커 대신 "AAA" 같은 고유 문자열 사용.
4. **파일 격리 실행 원칙 재확인** — 교차 실행 시 socket OSError가 매 실행 다른 테스트에서 발생(기지의 Windows 이벤트루프 flakiness). 격리 실행으로만 판정.

## 4. 이월 항목 (후속)

| 항목 | 비고 |
|------|------|
| **V050 적용** | V051(wiki path)과 함께 배포 전 필수 |
| 실서버 E2E | 등록 → `[사용자 메모리]` 블록 주입(LangSmith trace) → 삭제 후 미주입 — KB 공통 체크리스트 |
| G1 타입 정합화 | 다음 스키마 변경 시 TINYINT/SMALLINT 정리 |
| Phase 2 | 대화 자동 추출 + pending 승인 게이트 (스키마 선반영 완료) |
| Phase 3 | org 스코프 + Tier 1 온디맨드 (비교 문서 §5-1 결정과 연동) |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-20 | 사이클 완결 보고 — Match 98%, iterate 0회, 회귀 0 | 배상규 |
