# agent-workspace-view Completion Report

> **Feature**: agent-workspace-view — 에이전트 구성을 폴더처럼 열람하는 투명성 뷰
> **Author**: 배상규
> **Cycle**: Plan → Design → Do → Check → Report (2026-07-20 당일 완결)
> **Match Rate**: 1차 94% → Low 갭 3건 당일 해소 → **~98%** (Act 0회)

---

## Executive Summary

### 1.1 프로젝트 개요

| 항목 | 내용 |
|------|------|
| Feature | agent-workspace-view (growing-agent 투명성 축 — 사용자 원 요청 "폴더형 열람") |
| 기간 | 2026-07-20 당일 사이클 |
| 산출물 | 프론트 5파일(신규 페이지 1 + 테스트 1 + 진입점/라우트 3) · **백엔드 diff 0** |
| Match Rate | ~98% — 핵심 결정 4건·FR 전건 일치, 감점은 Low 3건(당일 해소) |

### 1.2 결과 요약

| 지표 | 값 |
|------|-----|
| 테스트 | AgentWorkspacePage 8 + AgentKnowledgePage 6(회귀 1 추가) = 14 통과 |
| 신규 계약 파일 | 0 — 훅·타입·MSW 전부 기존재 재사용 |
| 백엔드 변경 | **0줄** (git 실측) |
| Act 반복 | 0회 |

### 1.3 Value Delivered

| 관점 | 내용 |
|------|------|
| **Problem** | 에이전트가 어떤 지침·도구·지식으로 움직이는지 볼 수 없어 블랙박스 — 데이터(AgentDetail)는 노출됐으나 열람 화면이 없었다 |
| **Solution** | `/agents/:id/workspace` 읽기 전용 폴더 트리 뷰 — 지침·도구·서브에이전트·스킬·지식·정보 6폴더를 기존 훅(useAgentDetail/useAgentSkills/useWikiTree) 조립으로 통합. 백엔드 무변경 |
| **Function UX Effect** | 에이전트를 "열어보는" 경험 — 📄 지침.md 전문, 🔧 도구별 RAG 설정 뱃지, 📖 지식 폴더 원클릭 이동, 지식 브라우저·스토어 모달과 상호 링크 |
| **Core Value** | growing-agent 7원칙 중 **투명성 축의 마지막 조각** — 위키(지식)에 이어 나머지 구성 전부를 가시화. 구성을 검증할 수 있어야 성장(승인·환류)에 대한 신뢰가 성립 |

---

## 2. 구현 결과

- **AgentWorkspacePage**: 좌측 폴더 nav 6항목 + 우측 섹션 렌더. 지침 마크다운 전문, 도구는 카탈로그 라벨+RAG 설정(컬렉션·KB·위키 우선·라우팅) tool_config 안전 접근, 서브에이전트 ref_agent_name, 지식 wiki tree 요약+링크, 정보(소유자 포함)
- **읽기 전용**: mutation 훅 0, 소유자는 can_edit 시에만 "수정하기"(agent-builder 링크) — 열람·편집 분리
- **폴더별 독립 강등**(FR-05): agent detail 실패만 페이지 전체 안내, skills/tree 실패는 해당 폴더만
- **진입점 2곳**: AgentKnowledgePage 헤더 ↔ AgentDetailModal, 지식 브라우저와 대칭 URL

## 3. Lessons Learned

1. **훅 반환 타입은 서비스가 아니라 훅 선언을 봐야 한다** — `useToolCatalog`가 `CatalogTool[]` 배열을 직접 반환하는데 응답 객체로 오인해 도구 섹션 크래시. 테스트가 즉시 잡음.
2. **데이터가 이미 있으면 기능은 화면 조립** — AgentDetail이 필요 필드 전부를 노출하고 있어 신규 API·타입·훅 0으로 완결. "블랙박스 해소"는 새 데이터가 아니라 노출 경로였다.
3. **gap-detector 감점이 전부 Low(테스트 1·표시 항목·문서 스타일값)** — 문서 스타일값(max-w)은 코드가 옳아 설계를 정정하는 것이 맞는 방향.

## 4. 이월 항목

| 항목 | 비고 |
|------|------|
| 수동 E2E | 실제 에이전트로 6폴더 열람 + 진입점 왕복 — 실서버 기동 시 |
| (선택) 섹션 파일 분리 | index.tsx 258줄 — 소프트 가이드, 회귀 위험 0 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-07-20 | 당일 사이클 완결 — Match ~98%, 백엔드 diff 0 | 배상규 |
