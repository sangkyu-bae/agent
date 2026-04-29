# chat-sidebar-collapse Gap Analysis

> **Feature**: chat-sidebar-collapse
> **Date**: 2026-04-29
> **Design Doc**: docs/02-design/features/chat-sidebar-collapse.design.md
> **Match Rate**: 91% (10/11 requirements met)

---

## Summary

| Category | Total | Match | Gap | Rate |
|----------|-------|-------|-----|------|
| Component Changes | 8 | 8 | 0 | 100% |
| State Model | 1 | 1 | 0 | 100% |
| Route Conditions | 1 | 1 | 0 | 100% |
| Test Plan | 1 | 0 | 1 | 0% |
| **Total** | **11** | **10** | **1** | **91%** |

---

## Detailed Comparison

### 1. ChatHistoryPanel.tsx — ✅ PASS

| Design Requirement | Status | Evidence |
|-------------------|--------|----------|
| `onToggle` prop added | ✅ | Line 7: `onToggle: () => void` |
| Collapsed state (w-12 icon strip) | ✅ | Lines 36-56: conditional render with `w-12`, two icon buttons |
| Container class matches design | ✅ | `flex h-full w-12 shrink-0 flex-col items-center border-r border-zinc-200 bg-white pt-4 gap-1` |
| PanelLeftOpen icon + `title="펼치기"` | ✅ | Lines 37-45 |
| SquarePen icon + `title="새 채팅"` | ✅ | Lines 46-54 |
| Icon button: `h-9 w-9 rounded-lg` + hover | ✅ | Lines 40, 49 |
| Icon size: `h-5 w-5` | ✅ | Lines 42, 51 |
| Expanded state (w-72 + close button) | ✅ | Lines 59-165 |
| Header: `justify-between px-4 pt-5 pb-3` | ✅ | Line 62 |
| Close button: `h-8 w-8 rounded-lg` | ✅ | Line 66 |
| Right area: pen icon + "채팅" text | ✅ | Lines 72-77 |
| Border changed from `border-l` to `border-r` | ✅ | Lines 36, 60 |

### 2. AppSidebar.tsx — ✅ PASS

| Design Requirement | Status | Evidence |
|-------------------|--------|----------|
| `onToggleChatPanel` prop removed | ✅ | Not in interface (lines 6-10) |
| `isChatPanelOpen` prop removed | ✅ | Not in interface (lines 6-10) |
| Chat toggle button (section b) removed | ✅ | Section (b) is now "새 에이전트" button only |

### 3. AgentChatLayout.tsx — ✅ PASS

| Design Requirement | Status | Evidence |
|-------------------|--------|----------|
| AppSidebar: chat props removed | ✅ | Lines 74-78: only `agents`, `selectedAgentId`, `onSelectAgent` |
| Rendering condition: `isChatRoute` | ✅ | Line 80: `{isChatRoute && (` |
| `isOpen={isChatPanelOpen}` | ✅ | Line 82 |
| `onToggle={toggleChatPanel}` | ✅ | Line 83 |

### 4. layoutStore.ts — ✅ PASS (No Change Required)

| Design Requirement | Status | Evidence |
|-------------------|--------|----------|
| Interface unchanged | ✅ | Lines 4-10 match design spec exactly |
| persist key `'layout-preferences'` | ✅ | Line 22 |

### 5. Route Display Conditions — ✅ PASS

| Design Requirement | Status | Evidence |
|-------------------|--------|----------|
| `/chatpage` → ChatHistoryPanel visible | ✅ | AgentChatLayout line 22, 80 |
| Other routes → not rendered | ✅ | Conditional rendering via `isChatRoute` |

### 6. Test Plan — ❌ FAIL

| Design Test Case | Status |
|-----------------|--------|
| ChatHistoryPanel `isOpen=false` → w-12 icon strip | ❌ No test file |
| ChatHistoryPanel `isOpen=true` → w-72 full panel | ❌ No test file |
| Expand icon click → `onToggle` called | ❌ No test file |
| Collapse button click → `onToggle` called | ❌ No test file |
| Collapsed new chat icon → `onNewChat` called | ❌ No test file |
| AppSidebar has no chat toggle button | ❌ No test file |
| Non-chat route → ChatHistoryPanel not rendered | ❌ No test file |

**Missing files**:
- `src/components/layout/ChatHistoryPanel.test.tsx`
- `src/components/layout/AppSidebar.test.tsx`
- `src/components/layout/AgentChatLayout.test.tsx`

---

## Gap List

| # | Gap | Severity | File |
|---|-----|----------|------|
| G-1 | 7 test cases from Design Section 8.2 not implemented | Medium | `src/components/layout/ChatHistoryPanel.test.tsx` (missing) |

---

## Recommendation

Match Rate is **91%** (≥ 90% threshold). Implementation code fully matches design.

The only gap is the missing test suite. Options:
1. **Proceed to report** — implementation is complete and correct
2. **Write tests first** — add the 7 test cases from Design Section 8.2 to reach 100%
