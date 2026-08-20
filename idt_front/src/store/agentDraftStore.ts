import { create } from 'zustand';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';

// Design Ref: agent-create-entry §2.4 — 진입 화면(/agent-builder/new)과 스튜디오는
// 서로 다른 라우트에 있어 폼 상태를 직접 넘길 수 없다. 이 스토어가 그 경계를 잇되,
// 값의 수명은 "적재 → 1회 소비 → 소멸"로 한정한다.

/**
 * 위저드가 확정한 결과 (agent-create-wizard §2.2).
 *
 * `session_id`/`version_id` 를 함께 넘기는 이유: 스튜디오가 저장에 성공한 뒤
 * 프롬프트 세션에 `agent_id` 를 백필해야 버전 이력이 에이전트에 연결된다.
 * 새로고침하면 유실되지만 그건 정의된 동작이다 — 바인딩 실패가 저장을
 * 뒤집지 않으므로 고아 세션이 남을 뿐이다 (Design A-7).
 */
export interface WizardResult {
  systemPrompt: string;
  /** 사용자가 프롬프트를 편집했는지 — 편집본만 새 버전으로 저장한다. */
  promptEdited: boolean;
  toolIds: string[];
  suggestedName: string;
  sessionId: string | null;
  versionId: string | null;
}

/** 진입 화면이 스튜디오에 넘기는 1회성 의도. */
export type AgentCreateIntent =
  | { kind: 'draft'; draft: ComposeAgentDraftResponse }
  | { kind: 'wizard'; result: WizardResult }
  | { kind: 'blank' };

interface AgentDraftState {
  /** 소비 대기 중인 의도. 소비 즉시 null. */
  pendingIntent: AgentCreateIntent | null;
  setPendingIntent: (intent: AgentCreateIntent) => void;
  /** 읽기+비우기 원자적 1회. 소비 대상이 없으면 null. */
  consumePendingIntent: () => AgentCreateIntent | null;
  clearPendingIntent: () => void;
}

// Design §2.4 G1: persist 미들웨어를 쓰지 않는다.
// 새로고침/재로그인 후 옛 초안이 되살아나는 경로를 아예 만들지 않기 위함이며,
// 새로고침 시 초안 유실은 버그가 아니라 정의된 동작이다.
export const useAgentDraftStore = create<AgentDraftState>()((set, get) => ({
  pendingIntent: null,

  setPendingIntent: (intent) => set({ pendingIntent: intent }),

  // Design §2.4 G2: 읽기와 비우기는 같은 호출 안에서 끝낸다.
  // 분리하면 그 사이에 재진입한 소비자가 같은 초안을 두 번 적용할 수 있다.
  consumePendingIntent: () => {
    const current = get().pendingIntent;
    if (current) set({ pendingIntent: null });
    return current;
  },

  clearPendingIntent: () => set({ pendingIntent: null }),
}));
