// agent-run-tool-trace §5.4 Page UI Checklist / §8.3 L2.
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { ToolTrace } from '@/types/toolTrace';
import ToolTraceList from './ToolTraceList';

const TRACE: ToolTrace = {
  omitted_count: 0,
  items: [
    { seq: 1, kind: 'reasoning', label: '판단', text: '문의 목록을 조회하겠습니다' },
    {
      seq: 2, kind: 'tool', label: 'list_inquiries', source: 'mcp', status: 'success',
      duration_ms: 1072, input: { board: 'customer', limit: 1 },
      output: '{"total":74,"items":[{"subject":"제목"}]}',
    },
    {
      seq: 3, kind: 'tool', label: 'get_inquiry', source: 'mcp', status: 'failed',
      duration_ms: 41, input: { board: 'loan' },
      error: 'Error executing tool get_inquiry: validation error',
    },
    {
      seq: 4, kind: 'tool', label: '에이전트 위키 열람', source: 'internal', status: 'success',
      worker: '[멀티] 답변 작성자', requires_approval: true,
      output: '[위키 문서: 배포]\n본문', output_truncated: true,
    },
  ],
};

const openList = async () => {
  await userEvent.click(screen.getByRole('button', { name: /도구 실행 내역 \(3\)/ }));
};

const toolRow = (label: string) => screen.getByRole('button', { name: new RegExp(label) });

describe('ToolTraceList', () => {
  it('기본 접힘이고 도구 수(추론 제외)를 보여 준다', () => {
    render(<ToolTraceList trace={TRACE} />);
    const header = screen.getByRole('button', { name: /도구 실행 내역 \(3\)/ });
    expect(header).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('list_inquiries')).not.toBeInTheDocument();
  });

  it('도구가 없으면 아무것도 그리지 않는다', () => {
    const { container } = render(
      <ToolTraceList trace={{ omitted_count: 0, items: [{ seq: 1, kind: 'reasoning', label: '판단', text: 'A' }] }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('펼치면 추론과 도구를 순서대로 보여 준다', async () => {
    render(<ToolTraceList trace={TRACE} />);
    await openList();
    expect(screen.getByRole('button', { name: /도구 실행 내역/ })).toHaveAttribute('aria-expanded', 'true');
    const items = within(screen.getByRole('list')).getAllByRole('listitem');
    expect(items.map((li) => li.textContent)).toEqual([
      expect.stringContaining('문의 목록을 조회하겠습니다'),
      expect.stringContaining('list_inquiries'),
      expect.stringContaining('get_inquiry'),
      expect.stringContaining('에이전트 위키 열람'),
    ]);
  });

  it('상태는 아이콘과 텍스트를 함께 쓰고 소요 시간·MCP·워커·승인 배지를 단다', async () => {
    render(<ToolTraceList trace={TRACE} />);
    await openList();
    expect(within(toolRow('list_inquiries')).getByText('성공')).toBeInTheDocument();
    expect(within(toolRow('list_inquiries')).getByText('1.1s')).toBeInTheDocument();
    expect(within(toolRow('list_inquiries')).getByText('MCP')).toBeInTheDocument();
    expect(within(toolRow('get_inquiry')).getByText('실패')).toBeInTheDocument();
    expect(within(toolRow('에이전트 위키 열람')).getByText('[멀티] 답변 작성자')).toBeInTheDocument();
    expect(within(toolRow('에이전트 위키 열람')).getByText('승인 후 실행')).toBeInTheDocument();
  });

  it('도구 행을 펼치면 입력은 키: 값, JSON 결과는 들여쓰기로 보인다', async () => {
    render(<ToolTraceList trace={TRACE} />);
    await openList();
    const row = toolRow('list_inquiries');
    expect(row).toHaveAttribute('aria-expanded', 'false');
    await userEvent.click(row);
    expect(row).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('board')).toBeInTheDocument();
    expect(screen.getByText('customer')).toBeInTheDocument();
    expect(screen.getByTestId('tool-trace-output').textContent).toContain('"total": 74');
  });

  it('원문 보기는 받은 문자열을 그대로 보여 준다', async () => {
    render(<ToolTraceList trace={TRACE} />);
    await openList();
    await userEvent.click(toolRow('list_inquiries'));
    await userEvent.click(screen.getByRole('button', { name: '원문 보기' }));
    expect(screen.getByTestId('tool-trace-output').textContent).toBe(
      '{"total":74,"items":[{"subject":"제목"}]}',
    );
    expect(screen.getByTestId('tool-trace-input').textContent).toBe('{"board":"customer","limit":1}');
    await userEvent.click(screen.getByRole('button', { name: '정리해서 보기' }));
    expect(screen.getByTestId('tool-trace-output').textContent).toContain('"total": 74');
  });

  it('실패 항목은 오류 문구만 보이고 결과 영역이 없다', async () => {
    render(<ToolTraceList trace={TRACE} />);
    await openList();
    await userEvent.click(toolRow('get_inquiry'));
    expect(screen.getByText('Error executing tool get_inquiry: validation error')).toBeInTheDocument();
    expect(screen.queryByTestId('tool-trace-output')).not.toBeInTheDocument();
  });

  it('저장 한도로 잘린 결과는 안내를 단다', async () => {
    render(<ToolTraceList trace={TRACE} />);
    await openList();
    await userEvent.click(toolRow('에이전트 위키 열람'));
    expect(screen.getByText('저장 한도로 일부만 표시됩니다')).toBeInTheDocument();
    expect(screen.getByText('입력 없음')).toBeInTheDocument();
  });

  it('상한을 넘긴 항목 수를 알린다', async () => {
    render(<ToolTraceList trace={{ ...TRACE, omitted_count: 2 }} />);
    await openList();
    expect(screen.getByText('외 2건은 표시하지 않았습니다')).toBeInTheDocument();
  });

  it('결과에 든 HTML 은 텍스트로만 그린다', async () => {
    const xss: ToolTrace = {
      omitted_count: 0,
      items: [{
        seq: 1, kind: 'tool', label: 'scrape', status: 'success',
        output: '<img src=x onerror="alert(1)"><script>alert(1)</script>',
      }],
    };
    const { container } = render(<ToolTraceList trace={xss} />);
    await userEvent.click(screen.getByRole('button', { name: /도구 실행 내역 \(1\)/ }));
    await userEvent.click(toolRow('scrape'));
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByTestId('tool-trace-output').textContent).toContain('<script>');
  });

  it('완료 기록이 없는 호출은 실패가 아니라 "완료 기록 없음"으로 보인다 (Check G-01)', async () => {
    const trace: ToolTrace = {
      omitted_count: 0,
      items: [{ seq: 1, kind: 'tool', label: 'scrape', status: 'incomplete', input: { url: 'a' } }],
    };
    render(<ToolTraceList trace={trace} />);
    await userEvent.click(screen.getByRole('button', { name: /도구 실행 내역 \(1\)/ }));
    const row = toolRow('scrape');
    expect(within(row).getByText('완료 기록 없음')).toBeInTheDocument();
    expect(within(row).queryByText('실패')).not.toBeInTheDocument();
    await userEvent.click(row);
    expect(screen.getByText('실행 완료가 기록되지 않아 결과를 표시할 수 없습니다')).toBeInTheDocument();
    expect(screen.queryByTestId('tool-trace-output')).not.toBeInTheDocument();
  });

  it('원문과 정리 표시가 같으면 원문 보기 버튼을 두지 않는다 (Check G-04)', async () => {
    const trace: ToolTrace = {
      omitted_count: 0,
      items: [
        { seq: 1, kind: 'tool', label: 'plain', status: 'success', output: '평문 결과' },
        { seq: 2, kind: 'tool', label: 'broken', status: 'failed', error: '오류' },
      ],
    };
    render(<ToolTraceList trace={trace} />);
    await userEvent.click(screen.getByRole('button', { name: /도구 실행 내역 \(2\)/ }));
    await userEvent.click(toolRow('plain'));
    await userEvent.click(toolRow('broken'));
    expect(screen.queryByRole('button', { name: '원문 보기' })).not.toBeInTheDocument();
  });

  it('키보드로 펼칠 수 있다', async () => {
    render(<ToolTraceList trace={TRACE} />);
    screen.getByRole('button', { name: /도구 실행 내역/ }).focus();
    await userEvent.keyboard('{Enter}');
    expect(screen.getByText('list_inquiries')).toBeInTheDocument();
  });
});
