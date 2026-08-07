# agent-settings-tab Gap Analysis (Check)

> **Feature**: 에이전트 빌더 설정 탭 활성화 — Recursion Limit 실기능 + 연동 3종 스텁
> **Design**: `docs/02-design/features/agent-settings-tab.design.md`
> **Analyzer**: gap-detector (2026-08-07)
> **Match Rate**: **97.7%** (부분 크레딧) / 95.5% (엄격) — Missing 0, Partial 2

---

## 1. 결과 요약

검증 항목 44개 (설계 결정 D1~D9 = 9, §3 구조·계약 = 4, §4 UI = 6, §5 테스트 = 12,
§7 영향범위 = 5, Plan FR-01~08 = 8):

- **Match 42 / Partial 2 / Missing 0** → (42 + 2×0.5) / 44 = **97.7%**
- 동작상 실질 결함 없음. clamp 미확정 상태에서 저장 클릭 시에도 blur가 click보다
  먼저 발화해 `setForm` 반영 후 저장 실행 — 범위 밖 값의 페이로드 누수 경로 없음.
- 테스트: 신규·수정 30건 통과, 전체 회귀 812 통과 / 실패 8건은 전부 알려진 사전 실패
  (이번 변경 기인 회귀 0).

## 2. Gap 목록

| # | 심각도 | 설명 | 위치 | 처리 |
|---|:--:|---|---|---|
| G1 | Low | 설계 §4 스케치는 안내 카드(bg-zinc-50)가 안내문 전용이고 입력은 카드 밖 — 구현은 카드가 입력까지 감쌈. 토큰·문구는 일치, 시각 구조 차이만 | `SettingsPanel.tsx:77-119` | 수용 (설계 재량 범위 — 문서 §4에 반영 각주 처리 가능) |
| G2 | Info | 테스트 5-1⑤가 `""`만 검증, `"abc"` 미검증 — 단 `input[type=number]`는 jsdom이 비숫자를 `''`로 강제하므로 동일 경로 (실질 미커버 아님) | `SettingsPanel.test.tsx:60-66` | 수용 |
| G3 | Info | D8 "공용 StubSection 렌더러"를 명명 컴포넌트로 추출하지 않고 `STUB_SECTIONS.map` 인라인 — 반복 제거·섹션 교체 용이라는 의도는 충족 | `SettingsPanel.tsx:123-150` | 수용 |
| G4 | Medium(프로세스) | `AgentBuilderStudio.test.tsx:584` stale 단언 보정은 builtin-middleware 소관 — 커밋 시 분리 필요 | 해당 테스트 파일 | **커밋 분리** (아래 권고) |
| G5 | Low(프로세스) | 전체가 미커밋 워킹트리(신규 3파일 untracked) — 아카이브 전 커밋 필요 | git status | 커밋 이월 |

## 3. 설계 외 추가 구현 (전부 무해 판정)

1. `AgentCard` 수정/삭제 버튼 aria-label (`index.tsx:663,674`) — edit 통합 테스트 셀렉터 확보 + 접근성 개선 (삭제 쪽은 편승이나 무해)
2. 테스트 2건 초과 구현: Enter 확정·Telegram 상태 표기 — 커버리지 순증
3. 스텁 토글 `aria-label` — AgentSkillPanel 선례와 일관
4. number 입력 `min`/`max` HTML 속성 — 스피너 UX 보조 (실 가드는 clamp)
5. 라벨 `htmlFor`+`id` — 접근 가능 이름 확보
6. ⚙/↺ SVG 아이콘 인라인 (설계는 문자 표기)
7. `AgentBuilderStudio.test.tsx` stale 단언 수정 — **기능 무관, G4로 분리 권고**

## 4. 권고 조치

1. **커밋 분리**: stale 단언 보정은 별도 커밋
   (`test(front): builtin-middleware 빈 상태 문구 단언 보정`),
   나머지 12개 파일은 `feat(front/agent-builder): 설정 탭 활성화 + Recursion Limit 배선`.
2. **문서 보정(선택)**: Design §4 스케치의 카드 경계 1줄 보정 시 후속 참조 정확.
3. **이월**: E2E 수동 검증(500 저장 → detail 재조회 → edit 재진입 프라임)은
   Plan §4.1 DoD 미수행 — 실서버 기동 시 일괄 체크리스트로 소화.

## 5. 판정

Match Rate 97.7% ≥ 90% → **iterate 불필요, report 진행 가능**.
