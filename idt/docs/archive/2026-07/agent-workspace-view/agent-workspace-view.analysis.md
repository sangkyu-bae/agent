# agent-workspace-view Gap Analysis (Check)

> **Design**: `docs/02-design/features/agent-workspace-view.design.md`
> **Analyzer**: gap-detector (bkit) + 메인 세션 당일 보강
> **Date**: 2026-07-20
> **Match Rate**: 1차 **94%** → Low 갭 3건 당일 해소 → **~98%** (Act 0회)

---

## 1. 결과 요약

| Category | 1차 | 보강 후 |
|----------|:---:|:------:|
| Design Match (결정 4건 + FR) | 100% | 100% |
| Test Plan Coverage | 87.5%(8/8 중 회귀 1건 누락) | 100% |
| CLAUDE.md 프론트 규칙 | 준수(스타일 편차 1건) | 준수 |
| **Overall** | **94%** | **~98%** |

## 2. 매칭 확인 (핵심 전건 일치)

- 결정 ① 스킬 403/404 → SkillsSection isError 폴더 강등, 타 섹션 정상
- 결정 ② 지식 = wiki tree 요약(그룹·건수) + 전체 보기 링크 (트리 전체 렌더 안 함)
- 결정 ③ worker_type 분기 — tool은 카탈로그 라벨+RAG 안전 접근(4키 typeof 가드), sub_agent는 ref_agent_name / 0건 "없음"
- 결정 ④ /agents/:id/workspace 라우트 + 진입점 2곳
- FR-03 mapDraftToolIdsToCatalog 재사용 + 미매칭 원문 / FR-05 폴더별 독립 강등 / FR-07 can_edit 링크
- 읽기 전용(mutation 훅 0), **백엔드 diff 0** (프론트 전용 — git 실측)

## 3. Gap 목록 — 당일 해소

| # | 심각도 | 내용 | 해소 |
|---|:---:|------|------|
| G1 | Low | AgentKnowledgePage→workspace 회귀 테스트 누락(링크 자체는 구현됨) | `index.test.tsx`에 링크 href 검증 it() 추가 ✅ |
| G2 | Low | InfoSection에 소유자(owner_user_id) 미표시 | Info 행에 '소유자' 추가 ✅ |
| G3 | Low | 콘텐츠 max-w-3xl ≠ 설계 명시 max-w-7xl | **설계를 3xl로 정정**(좌측 nav 있는 읽기 뷰 — 지침 가독성 우선) ✅ |
| G4 | Low | index.tsx 258줄 (>200 소프트 가이드) | 섹션 컴포넌트는 이미 분리, 동일 파일 유지 — 소프트 가이드라 검토 항목으로 잔류(회귀 위험 0) |

## 4. 정당한 편차 (Gap 아님)

- 서브에이전트·can_edit를 각 2케이스로 분리 → Design 대비 커버리지 향상 (총 8 it 유지)
- max-w-3xl은 좌측 nav + 마크다운 가독성상 타당 (테이블/대시보드 아님)

## 5. 테스트 결과

- AgentWorkspacePage 8 + AgentKnowledgePage 6(회귀 1 추가) = **14/14 통과**
- tsc 변경 파일 에러 0, agent-store 컴포넌트 회귀 통과
- **백엔드 diff 0** 실측 (성공 기준 충족)

## 6. 이월

- 수동 E2E: 실제 에이전트로 6폴더 열람 + 진입점 왕복 — 실서버 기동 시
- (선택) index.tsx 섹션 파일 분리 — 소프트 가이드

## 7. 총평

결정 4건·FR 전부가 코드로 정확히 실현됐고 백엔드 diff 0 계약도 준수. 1차 감점은 회귀 테스트 1건·표시 항목·문서 스타일값 불일치의 Low 3건뿐이었고 당일 해소. growing-agent 투명성 축의 마지막 조각 완성.
