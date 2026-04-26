import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { server } from '@/__tests__/mocks/server';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import type { RagToolConfig } from '@/types/ragToolConfig';
import type { ReactNode } from 'react';
import RagConfigPanel from './RagConfigPanel';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderWithQuery = (ui: ReactNode) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
  );
};

describe('RagConfigPanel — scope 뱃지', () => {
  it('컬렉션 드롭다운 옵션에 scope 라벨이 포함된다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel config={{ ...DEFAULT_RAG_CONFIG }} onChange={onChange} />,
    );

    const select = await screen.findByRole('combobox');
    const options = select.querySelectorAll('option');

    const optionTexts = Array.from(options).map((o) => o.textContent);
    expect(optionTexts.some((t) => t?.includes('[공개]'))).toBe(true);
    expect(optionTexts.some((t) => t?.includes('[부서]'))).toBe(true);
    expect(optionTexts.some((t) => t?.includes('[개인]'))).toBe(true);
  });

  it('PERSONAL 컬렉션 선택 시 제한 안내 메시지가 표시된다', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel
        config={{ ...DEFAULT_RAG_CONFIG, collection_name: 'tech_manuals' }}
        onChange={onChange}
      />,
    );

    await screen.findByRole('combobox');
    expect(await screen.findByText(/개인용이므로 에이전트 공개 범위가 자동 제한/)).toBeInTheDocument();
  });

  it('DEPARTMENT 컬렉션 선택 시 제한 안내 메시지가 표시된다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel
        config={{ ...DEFAULT_RAG_CONFIG, collection_name: 'finance_docs' }}
        onChange={onChange}
      />,
    );

    await screen.findByRole('combobox');
    expect(await screen.findByText(/부서용이므로 에이전트 공개 범위가 자동 제한/)).toBeInTheDocument();
  });

  it('PUBLIC 컬렉션 선택 시 제한 안내 메시지가 표시되지 않는다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel
        config={{ ...DEFAULT_RAG_CONFIG, collection_name: 'documents' }}
        onChange={onChange}
      />,
    );

    await screen.findByRole('combobox');
    expect(screen.queryByText(/에이전트 공개 범위가 자동 제한/)).not.toBeInTheDocument();
  });

  it('컬렉션 미선택 시 제한 안내 메시지가 표시되지 않는다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel config={{ ...DEFAULT_RAG_CONFIG }} onChange={onChange} />,
    );

    await screen.findByRole('combobox');
    expect(screen.queryByText(/에이전트 공개 범위가 자동 제한/)).not.toBeInTheDocument();
  });
});
