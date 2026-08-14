import { create } from 'zustand';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';

// Design Ref: agent-create-entry §2.4 — 진입 화면(/agent-builder/new)과 스튜디오는
// 서로 다른 라우트에 있어 폼 상태를 직접 넘길 수 없다. 이 스토어가 그 경계를 잇되,
// 값의 수명은 "적재 → 1회 소비 → 소멸"로 한정한다.

/** 진입 화면이 스튜디오에 넘기는 1회성 의도. */
export type AgentCreateIntent =
  | { kind: 'draft'; draft: ComposeAgentDraftResponse }
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
