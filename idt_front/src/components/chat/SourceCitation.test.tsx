// wiki-user-facing: 위키 근거 배지 + 기존 출처 렌더링 회귀.
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';

import type { DocumentSource } from '@/types/chat';
import SourceCitation from './SourceCitation';

const docSource: DocumentSource = {
  content: '본문', source: 'policy.pdf', chunk_id: 'c1', score: 0.87,
};
const wikiSource: DocumentSource = {
  content: '정제 본문', source: 'wiki', chunk_id: 'w1', score: 0.92,
};

const renderWithRouter = (sources: DocumentSource[]) =>
  render(
    <MemoryRouter initialEntries={['/chatpage']}>
      <Routes>
        <Route path="/chatpage" element={<SourceCitation sources={sources} />} />
        <Route path="/knowledge/:articleId" element={<div>지식 문서 뷰</div>} />
      </Routes>
    </MemoryRouter>,
  );

describe('SourceCitation', () => {
  it('일반 출처는 기존 형식(파일명+점수)으로 렌더된다', () => {
    renderWithRouter([docSource]);
    expect(screen.getByText('policy.pdf')).toBeInTheDocument();
    expect(screen.getByText('87%')).toBeInTheDocument();
    expect(screen.queryByText('위키 근거')).not.toBeInTheDocument();
  });

  it('위키 출처는 위키 근거 배지로 구분 렌더된다', () => {
    renderWithRouter([docSource, wikiSource]);
    expect(screen.getByText('위키 근거')).toBeInTheDocument();
    expect(screen.getByText('92%')).toBeInTheDocument();
    expect(screen.getByText('policy.pdf')).toBeInTheDocument();
  });

  it('위키 배지 클릭 시 문서 뷰로 이동한다', async () => {
    const user = userEvent.setup();
    renderWithRouter([wikiSource]);
    await user.click(screen.getByText('위키 근거'));
    expect(screen.getByText('지식 문서 뷰')).toBeInTheDocument();
  });

  it('출처가 없으면 렌더되지 않는다', () => {
    const { container } = renderWithRouter([]);
    expect(container.querySelector('button')).toBeNull();
  });
});

// agent-run-source-citations Design §5.4 — 에이전트 근거 4종 + 발췌 패널
describe('SourceCitation — 에이전트 근거', () => {
  const agentDoc: DocumentSource = {
    kind: 'document', source: '최선집행기준설명서.pdf', content: '문서 발췌', chunk_id: 'd1',
  };
  const agentWiki: DocumentSource = {
    kind: 'wiki', source: '배포 승인 절차', content: '[위키 문서: 배포 승인 절차]', chunk_id: 'a-1',
  };
  const agentWeb: DocumentSource = {
    kind: 'web', source: '한국 금리결정', content: '웹 발췌',
    chunk_id: 'https://a.example/x', url: 'https://a.example/x',
  };
  const agentMcp: DocumentSource = {
    kind: 'mcp', source: 'get_inquiry', content: '{"status": "ok"}',
    chunk_id: 'mcp_6ea2f615_get_inquiry',
  };

  it('4종을 종류 텍스트와 함께 표시하고 점수는 표시하지 않는다', () => {
    renderWithRouter([agentDoc, agentWiki, agentWeb, agentMcp]);
    for (const text of ['문서', '위키', '웹', '도구']) {
      expect(screen.getByText(text)).toBeInTheDocument();
    }
    expect(screen.getByText('최선집행기준설명서.pdf')).toBeInTheDocument();
    expect(screen.getByText('get_inquiry')).toBeInTheDocument();
    expect(screen.queryByText(/%$/)).not.toBeInTheDocument();
    expect(screen.queryByText(/mcp_6ea2f615/)).not.toBeInTheDocument();
  });

  it('문서 칩에 순번을 표시한다', () => {
    renderWithRouter([agentDoc, { ...agentDoc, source: 'b.pdf', chunk_id: 'd2' }]);
    const second = screen.getByRole('button', { name: /b\.pdf/ });
    expect(second).toHaveTextContent('2');
  });

  it('aria-controls 는 열린 칩에만 있고 존재하는 패널을 가리킨다', async () => {
    const user = userEvent.setup();
    renderWithRouter([agentDoc]);
    const chip = screen.getByRole('button', { name: /최선집행기준설명서\.pdf/ });
    expect(chip).not.toHaveAttribute('aria-controls');

    await user.click(chip);
    const controls = chip.getAttribute('aria-controls');
    expect(controls).toBeTruthy();
    expect(document.getElementById(controls as string)).toHaveTextContent('문서 발췌');
  });

  it('문서 칩을 누르면 발췌가 펼쳐지고 다시 누르면 닫힌다', async () => {
    const user = userEvent.setup();
    renderWithRouter([agentDoc]);
    const chip = screen.getByRole('button', { name: /최선집행기준설명서\.pdf/ });

    expect(chip).toHaveAttribute('aria-expanded', 'false');
    await user.click(chip);
    expect(chip).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('문서 발췌')).toBeInTheDocument();

    await user.click(chip);
    expect(chip).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('문서 발췌')).not.toBeInTheDocument();
  });

  it('발췌 패널은 한 번에 하나만 열린다', async () => {
    const user = userEvent.setup();
    renderWithRouter([agentDoc, agentMcp]);
    await user.click(screen.getByRole('button', { name: /최선집행기준설명서\.pdf/ }));
    await user.click(screen.getByRole('button', { name: /get_inquiry/ }));
    expect(screen.queryByText('문서 발췌')).not.toBeInTheDocument();
    expect(screen.getByText('{"status": "ok"}')).toBeInTheDocument();
  });

  it('발췌가 없으면 펼칠 수 없다', () => {
    renderWithRouter([{ ...agentDoc, content: '  ' }]);
    expect(screen.queryByRole('button', { name: /최선집행기준설명서\.pdf/ })).toBeNull();
    expect(screen.getByText('최선집행기준설명서.pdf')).toBeInTheDocument();
  });

  it('발췌의 HTML 은 해석하지 않는다', async () => {
    const user = userEvent.setup();
    const { container } = renderWithRouter([
      { ...agentDoc, content: '<img src=x onerror="alert(1)">' },
    ]);
    await user.click(screen.getByRole('button', { name: /최선집행기준설명서\.pdf/ }));
    expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
  });

  it('웹 칩은 새 탭 외부 링크다', () => {
    renderWithRouter([agentWeb]);
    const link = screen.getByRole('link', { name: /한국 금리결정/ });
    expect(link).toHaveAttribute('href', 'https://a.example/x');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('안전하지 않은 URL 의 웹 칩은 링크가 아니다', () => {
    renderWithRouter([{ ...agentWeb, url: 'javascript:alert(1)' }]);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('한국 금리결정')).toBeInTheDocument();
  });

  it('위키 칩은 지식 문서로 이동한다', async () => {
    const user = userEvent.setup();
    renderWithRouter([agentWiki]);
    await user.click(screen.getByRole('button', { name: /배포 승인 절차/ }));
    expect(screen.getByText('지식 문서 뷰')).toBeInTheDocument();
  });

  it('일반 채팅 문서 칩도 발췌를 펼친다 (점수 표시 유지)', async () => {
    const user = userEvent.setup();
    renderWithRouter([docSource]);
    await user.click(screen.getByRole('button', { name: /policy\.pdf/ }));
    expect(screen.getByText('본문')).toBeInTheDocument();
    expect(screen.getByText('87%')).toBeInTheDocument();
  });
});
