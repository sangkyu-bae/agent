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
