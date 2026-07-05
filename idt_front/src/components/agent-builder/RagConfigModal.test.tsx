import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { server } from '@/__tests__/mocks/server';
import { DEFAULT_RAG_CONFIG } from '@/types/ragToolConfig';
import RagConfigModal from './RagConfigModal';

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

describe('RagConfigModal', () => {
  it('isOpen=false면 렌더되지 않는다', () => {
    renderWithQuery(
      <RagConfigModal
        isOpen={false}
        config={{ ...DEFAULT_RAG_CONFIG }}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('열림 시 현재 config 값이 패널에 반영된다', () => {
    renderWithQuery(
      <RagConfigModal
        isOpen
        config={{ ...DEFAULT_RAG_CONFIG, top_k: 7 }}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByRole('dialog', { name: '내부 문서 검색 설정' })).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
  });

  it('값 변경 후 취소하면 onApply가 호출되지 않는다', async () => {
    const onApply = vi.fn();
    const onClose = vi.fn();
    renderWithQuery(
      <RagConfigModal
        isOpen
        config={{ ...DEFAULT_RAG_CONFIG }}
        onApply={onApply}
        onClose={onClose}
      />,
    );

    await userEvent.click(screen.getByRole('radio', { name: /벡터/ }));
    await userEvent.click(screen.getByRole('button', { name: '취소' }));

    expect(onApply).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('값 변경 후 저장하면 변경값으로 onApply가 1회 호출된다', async () => {
    const onApply = vi.fn();
    const onClose = vi.fn();
    renderWithQuery(
      <RagConfigModal
        isOpen
        config={{ ...DEFAULT_RAG_CONFIG, search_mode: 'hybrid' }}
        onApply={onApply}
        onClose={onClose}
      />,
    );

    await userEvent.click(screen.getByRole('radio', { name: /벡터/ }));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));

    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply).toHaveBeenCalledWith(
      expect.objectContaining({ search_mode: 'vector_only' }),
    );
    expect(onClose).toHaveBeenCalled();
  });
});
