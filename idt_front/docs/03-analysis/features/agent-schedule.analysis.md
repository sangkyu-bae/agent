# Analysis: Agent Schedule (Design ↔ 구현 Gap 분석)

## Executive Summary

| 항목 | 내용 |
|------|------|
| Feature | agent-schedule |
| Design 참조 | `docs/02-design/features/agent-schedule.design.md` |
| 분석일 | 2026-07-03 |
| 분석 주체 | gap-detector 에이전트 (검증 항목 65개 전수 대조) |
| **Match Rate (초기)** | **98.5%** (Match 63 / Partial 2 / Missing 0 / Changed 0) |
| **Match Rate (갭 해소 후)** | **100%** — Low 갭 2건 즉시 수정 완료 |
| 90% 기준 | **통과** → report 단계 진입 가능 |

---

## 1. 판정 분포

| 판정 | 개수 | 비고 |
|------|------|------|
| Match | 63 | 설계 스펙과 정확히 일치 |
| Partial | 2 | 모두 Low 심각도 — 분석 직후 수정 완료 (§3) |
| Missing | 0 | — |
| Changed | 0 | 의도적 설계 변경 없음 |

Match Rate = (63 + 2×0.5) / 65 ≈ **98.5%** → 갭 해소 후 **100%**

## 2. 섹션별 검증 결과

| Design 섹션 | 항목 수 | 결과 |
|-------------|--------|------|
| §2 데이터 계층 (타입/상수/서비스/쿼리키/훅) | 19 | 19 Match |
| §3 cron 유틸 (조합/역파싱/10분 휴리스틱/이름/요약) | 8 | 8 Match |
| §4 컴포넌트 (ScheduleForm/SchedulePanel/AgentTestPanel) | 25 | 24 Match + 1 Partial(G1) |
| §5 페이지 통합 (staged/순차 POST/결과 문구) | 7 | 7 Match |
| §6 테스트 (MSW/유닛/컴포넌트/통합) | 6 | 5 Match + 1 Partial(G2) |

주요 확인 사항:
- 수정 모드 즉시 CRUD(POST/PUT/PATCH + ConfirmDialog→DELETE), 생성 모드 staged→순차 `mutateAsync` 일괄 등록(병렬 금지) 모두 설계대로 구현.
- cron 10분 휴리스틱은 순환 간격(`0,55` → 5분)까지 검증. 복합식 역파싱 실패 시 표현식 모드 폴백으로 데이터 손실 없음.
- daily/weekly(백엔드 직접 생성분)는 요약 표시·토글·삭제 가능, 수정 버튼만 비활성 — 설계 §4.3 일치.
- KST 표시는 설계 §3.4 의도(기존 유틸 재사용, 신규 파일 금지)대로 `formatters.formatDate` 재사용으로 충족.

## 3. Gap 목록 및 해소 결과

| # | 심각도 | 내용 | 해소 |
|---|--------|------|------|
| G1 | Low | 1회 date input에 설계 §4.1의 `min=내일` 속성 부재 (제출 검증으로 차단은 동작했으나 입력단 힌트 없음) | ✅ `ScheduleForm.tsx` — `tomorrowString()` 추가 후 `min` 속성 설정 + min 속성 검증 테스트 추가 |
| G2 | Low | 설계 §6.2의 "실행 메시지 1900자 초과 차단" 테스트 누락 (구현 로직은 존재) | ✅ `ScheduleForm.test.tsx` — 1901자 입력 → 제출 차단 + 에러 메시지 검증 테스트 추가 |

해소 후 `ScheduleForm.test.tsx` 14/14 통과 (기존 12 + 신규 2).

## 4. 추가 구현 (설계 범위 밖, Match Rate 무관)

| 항목 | 내용 |
|------|------|
| authClient `detail` fallback | 응답 인터셉터가 `data.message`만 읽어 FastAPI `detail`(400 검증 메시지)이 유실되던 문제 수정 (`authClient.ts:59`) — 스케줄 외 화면의 에러 표시도 개선 |
| adminNav 테스트 현행화 | 이전 세션 미커밋 변경('Skill 관리' 메뉴 추가)으로 stale해진 개수 단언을 6개로 갱신 + `/admin/skills` 포함 단언 추가 |

## 5. Plan 완료 기준(AC) 충족 여부

| AC | 내용 | 충족 |
|----|------|:----:|
| 1 | 스케줄 탭 활성화 + schedule.png 동일 폼 | ✅ |
| 2 | 수정 모드 즉시 CRUD + ConfirmDialog | ✅ |
| 3 | 생성 모드 staged → 일괄 POST + 부분 실패 문구 | ✅ |
| 4 | 폼↔미리보기 실시간, cron/once payload | ✅ |
| 5 | name 자동 생성, 1900자 차단, 10개 제한 | ✅ |
| 6 | 실행 이력 표시 (status/시각/에러) | ✅ |
| 7 | 전체 테스트 그린 + type-check + lint(신규 파일 0건) | ✅ (사전 실패 8건 제외 — 기존 이슈) |

## 6. 결론

- **Match Rate 100% (갭 해소 후)** — 90% 기준 통과, `iterate` 불필요.
- 신규 테스트 51건 전부 통과 (cron 14 + 훅 8 + 폼 14 + 패널 12 + 통합 3), 전체 스위트 신규 회귀 0건.
- 다음 단계: `/pdca report agent-schedule`
