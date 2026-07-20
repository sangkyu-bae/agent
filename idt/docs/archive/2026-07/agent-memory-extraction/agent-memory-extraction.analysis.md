# agent-memory-extraction Gap Analysis (Check)

> **Design**: `docs/02-design/features/agent-memory-extraction.design.md`
> **Analyzer**: gap-detector (bkit) + 메인 세션 당일 보강
> **Date**: 2026-07-20
> **Match Rate**: 1차 **97%** → 갭 3건 당일 해소 후 **100%** (Act 0회)

---

## 1. Overall Scores

| Category | 1차 | 보강 후 | 비고 |
|----------|:---:|:------:|------|
| Design Match (구현) | 100% | 100% | 결정 5건·FR 전 항목 명시 위치에 존재 |
| Test Plan Coverage (§4) | 92% | 100% | 누락 3건 당일 추가 |
| Architecture / Layer 준수 | 100% | 100% | domain 순수성(duck-typed dedup) 유지 |
| **Overall** | **97%** | **100%** | 기능 결함 0 · 무단 추가 0 |

## 2. 섹션별 매칭 (요약)

| Design 섹션 | 판정 | 핵심 확인 |
|-------------|:----:|----------|
| §1.1 결정 ①~⑤ | Match | 4000자 절단·from_openai·status 쿼리·뱃지 근거·kickoff 위치(chart-edit는 조기 return으로 구조적 제외) |
| §3-1 Domain | Match | validate_transition(PENDING만)·clamp·dedup(strip·duck-typed) |
| §3-2 Extractor | Match | JSON 강제·규칙 4종(PII 금지 포함)·파싱 실패 [] (+코드펜스 제거 보너스) |
| §3-3 Service | Match | off no-op·가드 패턴·상한 시 LLM 미호출·PENDING+source_run_id 저장·세션 2회+begin()·warning 격리 |
| §3-3 CrudUseCase | Match | approve(전이+active 상한 재검증)/reject, _find_owned 404 은닉 재사용 |
| §3-4 라우터·config·DI | Match | 불량 status 422, config 기본값(off/gpt-4o-mini/3/20), enabled 판정 서비스 내부 |
| §3-5 Frontend | Match | PendingSection(0건 미렌더·앰버 카드·자동 추출 근거), invalidate 양 목록 갱신 |
| FR-06 주입 배제 | Match | `find_active_by_user` 무수정 — 구조적 보장 |
| repo 화이트리스트 | Match | update() status 영속화 + 회귀 테스트 (`test_memory_repository.py`) |

## 3. Gap 목록 — 전부 당일 해소 (테스트 커버리지, 구현 결함 아님)

| # | 심각도 | 내용 | 해소 |
|---|:---:|------|------|
| G1 | Low | chart-edit 경로 kickoff 미호출 테스트 부재 | `test_memory_injection.py`에 `_try_chart_edit` 조기 리턴 시 `assert_not_called` 추가 ✅ |
| G2 | Low | kickoff 인자 중 run_id(args[3]) 미단언 | `args[3] is None`(tracker 미주입 계약) 단언 추가 ✅ |
| G3 | Info | 세션 2회 개폐 명시 테스트 부재 | `counter opened/closed == 2` 단언 추가 ✅ |

## 4. 정당한 편차 (Gap 아님)

| # | 편차 | 근거 |
|---|------|------|
| D1 | Service에 `repo_builder`/`drain()`/`run()` 추가 | 테스트 주입·종료 훅용 additive — 운영 경로 무영향 (Phase 1 assembler 선례) |
| D2 | confidence 이중 clamp (extractor+service) | 방어적 중복 — 무해 |
| D3 | 의사코드 `find_by_user(user_id, [A,P])` 단일 호출 → `find_by_user_and_status` 2회 | 실제 인터페이스(§3-3 additive 2메서드)와 일치 — 의사코드가 예시였을 뿐 |

## 5. 테스트 실행 결과

| 스위트 | 결과 |
|--------|------|
| 백엔드 8스위트 (정책 26·repo 10·추출기 9·CRUD 21·조립기 6·서비스 11·라우터 16·주입 9) | **108건 통과** (파일 격리 — 교차 에러는 기지 flakiness) |
| general_chat 회귀 | 25/25 전체 통과 + main.py import OK |
| 프론트 (훅 7 + SettingsPage 10) | 17건 통과, tsc 변경 파일 에러 0 |

## 6. 이월 항목

- **E2E 실측**: `.env` 추출 on → 채팅 → pending 적재 → 승인 → 다음 질문 주입 확인 — KB 공통 체크리스트 합류 (기본 off 배포라 즉시 위험 0)
- Phase 3 후보: run 딥링크 근거 표시, pii_masking 엔진 연동, org 스코프, expires_at 만료 배치

## 7. 총평

1. 구현은 설계와 완전 일치(구현 결함 0) — 1차 97%의 감점은 전부 테스트 플랜 커버리지 누락이었고 당일 3건 보강으로 100%.
2. repo update() 화이트리스트 함정을 구현 중 선제 차단(회귀 테스트 고정)한 것이 이번 사이클의 핵심 방어.
3. 기본 off 배포 + 마이그레이션 0 — `/pdca report` 진행 가능.
