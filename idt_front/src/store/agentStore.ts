import { create } from 'zustand';
import type { AgentRun, AgentStatus } from '@/types/agent';
import { createLoadingSlice, type LoadingSlice } from './commonSlices';

interface AgentOwnState {
  currentRun: AgentRun | null;
  agentStatus: AgentStatus;
  history: AgentRun[];
  setCurrentRun: (run: AgentRun) => void;
  setAgentStatus: (status: AgentStatus) => void;
  clearCurrentRun: () => void;
}

type AgentState = LoadingSlice & AgentOwnState;

export const useAgentStore = create<AgentState>()((...args) => {
  const [set, get] = args;
  return {
    ...createLoadingSlice<AgentState>()(...args),

    currentRun: null,
    agentStatus: 'idle',
    history: [],

    setCurrentRun: (run) => set({ currentRun: run }),
    setAgentStatus: (agentStatus) => set({ agentStatus }),
    clearCurrentRun: () => {
      const { currentRun } = get();
      if (currentRun) {
        set((state) => ({
          history: [currentRun, ...state.history],
          currentRun: null,
          agentStatus: 'idle',
        }));
      }
    },
  };
});
