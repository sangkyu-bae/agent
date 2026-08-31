// Design §8.3 L2 #9~#10 — blueprint 옵션 / pdf 선택 시 MCP 입력 / 범위 검증
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import type { PresentationGeneratorDraft } from '@/types/presentationGenerator';
import PresentationGeneratorConfigPanel from './PresentationGeneratorConfigPanel';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderPanel = (draft: PresentationGeneratorDraft | null, onChange = vi.fn()) => {
  const Wrapper = createWrapper();
  render(
    <Wrapper>
      <PresentationGeneratorConfigPanel draft={draft} onChange={onChange} />
    </Wrapper>
  );
  return onChange;
};

describe('PresentationGeneratorConfigPanel', () => {
  it('옵션 API 의 blueprint 목록을 select 로 보여주고 선택하면 onChange 한다', async () => {
    const onChange = renderPanel(null);
    const select = (await screen.findByLabelText('양식 (blueprint)')) as HTMLSelectElement;
    expect(await screen.findByRole('option', { name: 'golden' })).toBeInTheDocument();
    await userEvent.selectOptions(select, 'bp-1');
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ blueprintId: 'bp-1', maxSlides: 15 }));
    expect(screen.getByRole('alert')).toHaveTextContent('양식(blueprint)을 선택하세요');
  });

  it('등록된 양식이 없으면 /admin/blueprints 안내 링크', async () => {
    server.use(http.get(`*${API_ENDPOINTS.BLUEPRINT_OPTIONS}`, () => HttpResponse.json({ items: [] })));
    renderPanel(null);
    expect(await screen.findByRole('link', { name: '/admin/blueprints' })).toBeInTheDocument();
  });

  it('pdf 선택 시 MCP 도구 입력이 나타나고, max_slides 범위 위반은 alert', async () => {
    const draft: PresentationGeneratorDraft = {
      blueprintId: 'bp-1', outputFormat: 'pptx', mcpPptxToPdfToolId: '', maxSlides: 15,
    };
    const onChange = renderPanel(draft);
    await screen.findByRole('option', { name: 'golden' });
    expect(screen.queryByLabelText(/PPTX→PDF 변환/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('PDF'));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ outputFormat: 'pdf' }));
    renderPanel({ ...draft, outputFormat: 'pdf', maxSlides: 99 });
    expect(await screen.findAllByLabelText(/PPTX→PDF 변환/)).toHaveLength(1);
    expect(screen.getAllByRole('alert').some((a) => a.textContent?.includes('1~60'))).toBe(true);
  });
});
