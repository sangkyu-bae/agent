import { create } from 'zustand';
import type { Message, ChatSession } from '@/types/chat';
import { createLoadingSlice, type LoadingSlice } from './commonSlices';

interface ChatOwnState {
  sessions: ChatSession[];
  activeSessionId: string | null;
  isStreaming: boolean;
  streamingContent: string;

  setActiveSession: (sessionId: string) => void;
  addMessage: (sessionId: string, message: Message) => void;
  setStreaming: (isStreaming: boolean) => void;
  appendStreamingContent: (delta: string) => void;
  commitStreamingMessage: (role: 'assistant') => void;
  reset: () => void;
}

type ChatState = LoadingSlice & ChatOwnState;

export const useChatStore = create<ChatState>()((...args) => {
  const [set, get] = args;
  return {
    ...createLoadingSlice<ChatState>()(...args),

    sessions: [],
    activeSessionId: null,
    isStreaming: false,
    streamingContent: '',

    setActiveSession: (sessionId) => set({ activeSessionId: sessionId }),

    addMessage: (sessionId, message) =>
      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === sessionId ? { ...s, messages: [...s.messages, message] } : s,
        ),
      })),

    setStreaming: (isStreaming) =>
      set({ isStreaming, streamingContent: isStreaming ? '' : get().streamingContent }),

    appendStreamingContent: (delta) =>
      set((state) => ({ streamingContent: state.streamingContent + delta })),

    commitStreamingMessage: (role) => {
      const { activeSessionId, streamingContent } = get();
      if (!activeSessionId || !streamingContent) return;
      const message: Message = {
        id: crypto.randomUUID(),
        role,
        content: streamingContent,
        createdAt: new Date().toISOString(),
      };
      get().addMessage(activeSessionId, message);
      set({ streamingContent: '', isStreaming: false });
    },

    reset: () =>
      set({
        sessions: [],
        activeSessionId: null,
        isStreaming: false,
        streamingContent: '',
        status: 'idle',
        error: null,
      }),
  };
});
