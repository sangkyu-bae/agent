import { describe, expect, it } from 'vitest';

import type { ToolTrace } from '@/types/toolTrace';
import { countTools, formatDuration, formatInputLines, formatOutput, rawInput } from './toolTraceFormat';

describe('formatInputLines', () => {
  it('키: 값 줄로 바꾸고 문자열은 따옴표 없이 둔다', () => {
    expect(formatInputLines({ query: '여신 한도', limit: 1, exact: true })).toEqual([
      { key: 'query', value: '여신 한도' },
      { key: 'limit', value: '1' },
      { key: 'exact', value: 'true' },
    ]);
  });

  it('중첩 값은 한 줄 JSON 으로 쓴다', () => {
    expect(formatInputLines({ filter: { board: 'loan' }, ids: [1, 2], none: null })).toEqual([
      { key: 'filter', value: '{"board":"loan"}' },
      { key: 'ids', value: '[1,2]' },
      { key: 'none', value: 'null' },
    ]);
  });

  it('입력이 없거나 비어 있으면 빈 배열', () => {
    expect(formatInputLines(undefined)).toEqual([]);
    expect(formatInputLines({})).toEqual([]);
  });
});

describe('rawInput', () => {
  it('원문 보기는 입력 객체를 그대로 직렬화한다', () => {
    expect(rawInput({ board: 'loan', limit: 1 })).toBe('{"board":"loan","limit":1}');
    expect(rawInput(undefined)).toBe('');
  });
});

describe('formatOutput', () => {
  it('JSON 이면 2칸 들여쓰기로 정리한다', () => {
    expect(formatOutput('{"total":74,"items":[1]}')).toEqual({
      text: '{\n  "total": 74,\n  "items": [\n    1\n  ]\n}',
      isJson: true,
    });
  });

  it('절단으로 JSON 이 깨졌으면 텍스트 그대로 둔다', () => {
    expect(formatOutput('{"total": 74, "items": [')).toEqual({
      text: '{"total": 74, "items": [',
      isJson: false,
    });
  });

  it('평문은 줄바꿈을 보존한다', () => {
    expect(formatOutput('[위키 문서: 배포]\n본문')).toEqual({
      text: '[위키 문서: 배포]\n본문',
      isJson: false,
    });
  });

  it('JSON 스칼라는 정리 대상이 아니다', () => {
    expect(formatOutput('42').isJson).toBe(false);
    expect(formatOutput('"문자열"').isJson).toBe(false);
  });

  it('결과가 없으면 빈 텍스트', () => {
    expect(formatOutput(undefined)).toEqual({ text: '', isJson: false });
  });
});

describe('formatDuration', () => {
  it.each([
    [320, '320ms'],
    [999, '999ms'],
    [1072, '1.1s'],
    [12000, '12.0s'],
  ])('%i → %s', (ms, expected) => {
    expect(formatDuration(ms)).toBe(expected);
  });

  it('값이 없으면 null', () => {
    expect(formatDuration(undefined)).toBeNull();
  });
});

describe('countTools', () => {
  it('추론은 세지 않는다 (Plan FR-12)', () => {
    const trace: ToolTrace = {
      omitted_count: 0,
      items: [
        { seq: 1, kind: 'reasoning', label: '판단', text: 'A' },
        { seq: 2, kind: 'tool', label: '도구', status: 'success' },
        { seq: 3, kind: 'tool', label: '도구', status: 'failed' },
      ],
    };
    expect(countTools(trace)).toBe(2);
  });
});
