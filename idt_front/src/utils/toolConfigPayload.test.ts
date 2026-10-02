// approval-gate-run-termination Design §5.1 (F2) — 저장 시 본문 인자 병합
import { describe, expect, it } from 'vitest';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import { buildToolConfigsForSave, draftArgKeysFromWorkers } from './toolConfigPayload';

const MCP_ID = 'mcp:6ea2f615-515e-4f65-aabe-388970dbafbe:submit_reply';
const RAG_ID = 'internal:internal_document_search';

describe('buildToolConfigsForSave', () => {
  it('설정이 하나도 없으면 undefined (서버 기존값 승계)', () => {
    expect(buildToolConfigsForSave({}, {})).toBeUndefined();
  });

  it('본문 인자를 tool_configs 에 싣는다', () => {
    expect(buildToolConfigsForSave({}, { [MCP_ID]: 'reply_content' })).toEqual({
      [MCP_ID]: { draft_arg_key: 'reply_content' },
    });
  });

  it('빈 값은 null — 서버 저장값을 지운다', () => {
    expect(buildToolConfigsForSave({}, { [MCP_ID]: '  ' })).toEqual({
      [MCP_ID]: { draft_arg_key: null },
    });
  });

  it('RAG 설정은 그대로 두고 함께 보낸다', () => {
    const rag = { ...DEFAULT_RAG_CONFIG };
    expect(
      buildToolConfigsForSave({ [RAG_ID]: rag }, { [MCP_ID]: 'reply_content' }),
    ).toEqual({
      [RAG_ID]: rag,
      [MCP_ID]: { draft_arg_key: 'reply_content' },
    });
  });

  it('값 앞뒤 공백은 제거한다', () => {
    expect(buildToolConfigsForSave({}, { [MCP_ID]: ' reply_content ' })).toEqual({
      [MCP_ID]: { draft_arg_key: 'reply_content' },
    });
  });
});

describe('draftArgKeysFromWorkers', () => {
  it('저장된 워커 tool_config 의 draft_arg_key 를 복원한다', () => {
    expect(
      draftArgKeysFromWorkers([
        { tool_id: MCP_ID, tool_config: { draft_arg_key: 'reply_content', top_k: 5 } },
        { tool_id: 'mcp:x:get_inquiry', tool_config: null },
        { tool_id: 'internal_document_search', tool_config: { top_k: 5 } },
      ]),
    ).toEqual({ [MCP_ID]: 'reply_content' });
  });

  it('빈 문자열·null 은 복원하지 않는다', () => {
    expect(
      draftArgKeysFromWorkers([
        { tool_id: MCP_ID, tool_config: { draft_arg_key: '' } },
        { tool_id: 'mcp:y:z', tool_config: { draft_arg_key: null } },
      ]),
    ).toEqual({});
  });
});
