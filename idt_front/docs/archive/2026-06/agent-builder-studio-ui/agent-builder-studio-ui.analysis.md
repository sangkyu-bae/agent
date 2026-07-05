# agent-builder-studio-ui Gap Analysis (Check)

> **Date**: 2026-06-27
> **Feature**: agent-builder-studio-ui (프론트 React redesign)
> **Design**: [agent-builder-studio-ui.design.md](../02-design/features/agent-builder-studio-ui.design.md)
> **Plan**: [agent-builder-studio-ui.plan.md](../01-plan/features/agent-builder-studio-ui.plan.md)
> **Method**: gap-detector (read-only, evidence-based)

---

## Overall Scores

| Category | Score | Status |
|----------|:-----:|:------:|
| Functional Design Match (FR + 컴포넌트 + 동작) | **97%** | ✅ |
| Architecture Compliance (§9 레이어/의존성) | 100% | ✅ |
| Convention Compliance (§10 네이밍/props/모달) | 100% | ✅ |
| Test Plan Coverage (§8.2 / §11.1) | ~55% | ⚠️ |
| **Overall Match Rate** | **~93%** | ✅ (≥90%) |

---

## FR 검증 (Plan §3.1)

| FR | Status | Evidence |
|----|:------:|----------|
| FR-01 목록↔Studio 전환, 취소→목록 | ✅ | `index.tsx` view 분기, `handleNew/handleEdit`, `StudioHeader` onCancel→`setView('list')` |
| FR-02 좌측 collapsible 지침/모델/도구함 + 양방향 바인딩 | ✅ | `LeftConfigPanel` `CollapsibleSection`별 섹션, `onChange({...form})` |
| FR-03 모델 ⚙→모달, model+temp→form, 저장 시 닫힘 | ✅ | `ModelSettingsModal.handleSave`→`onApply`→`onChange` |
| FR-04 max-tokens/topP/topK 비활성 + API키 경고 | ✅ | disabled inputs + 경고 배너 + `[API 키 미등록]` 라벨 |
| FR-05 +도구 모달 추가/제거, 생성모드 MCP 비활성 | ✅ | `mcpDisabled = !isEditMode && source==='mcp'` + create payload 필터 |
| FR-06 RAG 도구 → RagConfigPanel 노출 | ✅ | `handleToolToggle` toolConfigs 동기화 + 조건부 렌더 |
| FR-07 테스트 탭 스트리밍(edit/저장된 id) | ✅ | `canTest = edit && agentId`, `useAgentRunStream`, per-send UUID |
| FR-08 스킬 탭 attach/detach(edit only) | ✅ | `skill.enabled=isEdit` + `AgentSkillPanel` |
| FR-09 placeholder + "준비중" 툴팁 | ✅ | header 아이콘·버전, 비주얼탭, 서브에이전트, 미들웨어, fix/opener/file/schedule/settings 탭 |
| FR-10 저장/수정/삭제 + 결과 다이얼로그 보존 | ✅ | 기존 핸들러 불변 + `ConfirmDialog` 재사용 |

**10/10 FR 구현 완료.**

---

## Gap List

### 🔵 설계-구현 편차

| # | 항목 | 설계 | 구현 | 심각도 |
|---|------|------|------|:------:|
| 1 | 모델 로드 에러/재시도 | §5.7 `isModelsLoading/isModelsError/onRetryModels`, §6 "모델 로드 실패 → 재시도" | StudioLayout이 `models`만 전달, 모델 로드 실패 시 빈 `<select>` (도구 재시도는 연동됨) | **Medium** |
| 2 | 도구 모달 그룹핑 | §5.4 "내부/MCP 그룹으로 표시" | 평면 리스트 + MCP 뱃지만 | Low |
| 3 | `AgentTestPanelProps.userId` | §5.7 authStore userId 전달 | 생략 — `useAgentRunStream`이 내부에서 authStore 토큰 사용 (정당한 단순화) | Low(info) |
| 4 | 모델 칩 라벨 | mock provider:model | 칩=`model_name`, 모달=`display_name` 경미한 불일치 | Trivial |

### ⚠️ 테스트 커버리지 갭

| 설계 §11.1 기대 | 존재 |
|------------------|:----:|
| ModelSettingsModal.test / ToolPickerModal.test | ✅ |
| StudioLayout / StudioHeader / LeftConfigPanel / AgentTestPanel / TestChatView .test | ❌ (간접: `AgentBuilderStudio.test.tsx`) |

미커버 §8.2 케이스: **TestChatView edit-mode 스트리밍**(WS mock 토큰누적→answer확정), StudioHeader 저장-비활성, 우측 탭 전환.

---

## 확인된 핵심 동작 (정상)

- 모델 모달 = **model + temperature만** form 반영, 추가 파라미터는 비활성·미저장 ✅
- 도구 모달 MCP 생성모드 비활성 (UI + payload 양쪽) ✅
- 테스트 패널 edit 전용, create는 "저장 후 테스트할 수 있습니다" + 입력 비활성, WS 실패 시 `⚠ 실행 실패` 버블 ✅
- 새 대화 시 sessionId+messages 리셋, 멀티턴 sessionId 유지 ✅
- 아키텍처: 컴포넌트는 hooks/props만, 직접 axios 없음, 폼 상태 page 단일 소유 ✅

---

## 권장 조치 (우선순위)

1. **(Medium) 모델 로드 에러/재시도 연동** — `useLlmModels`의 `isLoading/isError/refetch`를 `StudioLayout`→`ModelSettingsModal`로 전달해 도구 패턴과 동일하게 §6 충족.
2. **(Test) TestChatView edit 스트리밍 테스트** 추가 (WS mock) — 최고가치 §8.2 갭 해소.
3. **(Optional) 도구 모달 내부/MCP 그룹핑** 또는 설계 §5.4를 "평면+뱃지"로 동기화.
4. **(Doc) 설계 §3.1/§5.7 동기화** — `ModelSettingsValue` 단순화, `userId` 생략을 해소된 편차로 기록.

---

## 결론

설계-구현 일치도 양호(97% 기능 / ~93% 종합, ≥90% 통과). 미구현·무단 기능 없음.

---

## Act (Iteration 1) — 갭 해소 결과 (2026-06-27)

| 갭 | 조치 | 상태 |
|----|------|:----:|
| #1 모델 로드 에러/재시도 (Medium) | `useLlmModels` `isLoading/isError/refetch`를 page→StudioLayout→LeftConfigPanel→ModelSettingsModal로 연동. 모달이 스켈레톤/에러+재시도/select 분기 렌더 | ✅ CLOSED |
| #2 TestChatView 스트리밍 테스트 | `TestChatView.test.tsx` 추가 (useAgentRunStream mock): edit 전송→사용자메시지+확정 응답, create 비활성, 새 대화 리셋. ModelSettingsModal 로딩/에러 테스트 추가 | ✅ CLOSED |

### 재검증 Match Rate (gap-detector)

| Metric | Before | After |
|--------|:------:|:-----:|
| Functional Design Match | 97% | **99%** |
| Test Plan Coverage | ~55% | **~80%** |
| **Overall** | ~93% | **~97%** |

검증: agent-builder 디렉토리 **30/30 테스트 통과**, type-check clean. 잔여 항목(도구 모달 그룹핑·doc-sync)은 비기능 사소 항목. **≥90% 품질 게이트 충족 → `/pdca report` 준비 완료.**
