// agent-create-entry Design §2.4 — 핸드오프 생명주기 계약(G1/G2) 회귀 테스트.
// 이 스토어의 유일한 존재 이유가 "1회 소비 후 소멸"이므로 계약 자체를 테스트한다.
import { describe, it, expect, beforeEach } from 'vitest';
import { useAgentDraftStore } from './agentDraftStore';
import type { ComposeAgentDraftResponse } from '@/types/agentComposer';

const draft: ComposeAgentDraftResponse = {
  status: 'draft',
  coverage: 'full',
  name_suggestion: '규정 봇',
  system_prompt: '너는 사내 규정 안내 봇이다.',
  tool_ids: ['rag_search'],
  workers: [],
  flow_hint: '',
  llm_model_id: 'model-1',
  temperature: 0.7,
  missing_capabilities: [],
  notes: '',
};

describe('agentDraftStore (Design §2.4)', () => {
  beforeEach(() => {
    useAgentDraftStore.getState().clearPendingIntent();
  });

  it('초기 상태는 비어 있다', () => {
    expect(useAgentDraftStore.getState().pendingIntent).toBeNull();
  });

  it('draft 의도를 적재하고 소비하면 같은 값을 돌려준다', () => {
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft });

    const consumed = useAgentDraftStore.getState().consumePendingIntent();

    expect(consumed).toEqual({ kind: 'draft', draft });
  });

  // G2: 읽기와 비우기가 같은 호출 안에서 일어나야 이중 적용이 불가능하다
  it('소비는 1회만 성공하고 두 번째부터는 null이다', () => {
    useAgentDraftStore.getState().setPendingIntent({ kind: 'blank' });

    const first = useAgentDraftStore.getState().consumePendingIntent();
    const second = useAgentDraftStore.getState().consumePendingIntent();

    expect(first).toEqual({ kind: 'blank' });
    expect(second).toBeNull();
  });

  it('소비 직후 스토어 상태가 비워진다', () => {
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft });

    useAgentDraftStore.getState().consumePendingIntent();

    expect(useAgentDraftStore.getState().pendingIntent).toBeNull();
  });

  // G3: 진입 화면 재진입 시 잔여 초안 제거용
  it('clearPendingIntent는 적재된 값을 버린다', () => {
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft });

    useAgentDraftStore.getState().clearPendingIntent();

    expect(useAgentDraftStore.getState().consumePendingIntent()).toBeNull();
  });

  it('나중 적재가 이전 의도를 덮어쓴다', () => {
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft });
    useAgentDraftStore.getState().setPendingIntent({ kind: 'blank' });

    expect(useAgentDraftStore.getState().consumePendingIntent()).toEqual({
      kind: 'blank',
    });
  });

  // G1: persist 미들웨어를 쓰면 새로고침 후 옛 초안이 부활한다
  it('브라우저 스토리지에 아무것도 남기지 않는다', () => {
    useAgentDraftStore.getState().setPendingIntent({ kind: 'draft', draft });

    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
