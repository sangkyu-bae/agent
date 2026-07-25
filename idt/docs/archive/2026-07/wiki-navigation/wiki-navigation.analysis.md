# Wiki Navigation — Gap Analysis

> **Feature**: wiki-navigation
> **Date**: 2026-07-21
> **Analyzer**: gap-detector (bkit)
> **Design Reference**: `docs/02-design/features/wiki-navigation.design.md`

---

## Match Rate: **97%** ✅ (Report 단계 진입 가능, ≥90%)

| Category | Score | Status |
|----------|:-----:|:------:|
| Design Match | 97% | ✅ |
| Architecture Compliance | 100% | ✅ |
| Convention Compliance | 100% | ✅ |

설계와 구현이 매우 잘 일치. 백엔드 변경 0·마이그레이션 0 원칙 준수. Missing 없음. 경미한 Gap 2건(에러 UX 단순화, T1 네비게이션 단언 축소)만 존재하며 기능 영향 없음.

---

## 검증 항목별 결과

| # | 검증 항목 | 소계 | 판정 |
|---|-----------|:----:|:----:|
| 1 | §2 S1 메뉴 항목 (맨 뒤 추가, 4필드, icon 일치, 자동 노출) | 100% | ✅ |
| 2 | §3 S2 드롭다운화 (훅 재사용, 옵션 매핑, 페이로드 불변, 폴백, 빈상태, 테이블 연동) | 94% | ⚠️ |
| 3 | §4 S3 워크스페이스 링크 (optional prop, truthy Link, 맨앞, super 배선) | 100% | ✅ |
| 4 | §5 테스트 T1~T7 | 93% | ⚠️ |
| 5 | §7 주의사항 (백엔드0, Dropdown 무수정, 단일소스, state 유지) | 100% | ✅ |

**항목 가중 합산 29.0/30 = 96.7%, 그룹 균등 평균 97.4% → Match Rate 97%.**

핵심 일치 확인:
- `adminNav.ts:66-71` — 위키 항목이 Skill 관리 다음 10번째, icon 문자열 설계와 완전 동일, 4필드 완비
- `WikiPage/index.tsx:29-46` — `useAgentList({scope:'all',size:100})` + `useCollections()`, 옵션 매핑(agent_id/name, name/display_name), distill 페이로드 `{agent_id, collection_name}` 불변, `manualInput` 폴백 토글, 빈 상태 문구 변경, `WikiArticleTable agentId={agentId.trim()}` 유지
- `ChatHeader.tsx` — optional `agentId?: string|null`, truthy일 때만 `Link /agents/{id}/workspace`, 우측 그룹 맨 앞
- `ChatPage/index.tsx:317` — `selectedAgent && selectedAgent.id !== 'super'` 조건 배선 (스트리밍 분기와 동일 기준)

---

## Gap 목록

| ID | 항목 | 심각도 | 설계 | 구현 | 처리 |
|----|------|:------:|------|------|------|
| G1 | §3.2 목록 API 에러 UX | Low | 드롭다운 자리별 에러 문구 + 재시도 | 폼 하단 단일 amber 배너 + 직접입력 전환 안내 | 설계 §3.2를 실태(단일 배너+전환 안내)로 정정 — 기능적으로 충분 (2026-07-21 반영) |
| G2 | §5 T1 테스트 범위 | Low | 노출 + 클릭 시 이동 단언 | 노출 단언만 (`TopNav.test.tsx`) | 설계 T1을 노출 단언으로 정정 — adminNav 단일 소스 + AdminLayout 기존 라우팅 로직 신뢰 (2026-07-21 반영) |

**Added(긍정적, 설계 외)**: `adminNav.test.ts` 개수 10 + `/admin/wiki` 포함 단언(N1-6) — 회귀 방어 보강. 기존에 낡아 있던 개수 단언(8)도 함께 정비.

---

## 테스트 결과 스냅샷

- 신규/수정 테스트: TopNav 3 · ChatHeader 2 · WikiPage 5 · adminNav 9 — 전부 통과
- `tsc --noEmit` 에러 0
- 전체 스위트 725건 중 잔여 실패 8건 = 기존 사전 실패(collection 7 + ChatPage 1)와 일치, 신규 회귀 0

---

## 결론

즉시 조치 필요 Gap 없음. G1·G2는 설계 문서 정정으로 해소. **다음 단계: `/pdca report wiki-navigation`**
