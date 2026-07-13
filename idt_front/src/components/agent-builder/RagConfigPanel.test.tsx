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

describe('RagConfigPanel — 위키 우선 검색 토글', () => {
  it('체크 시 use_wiki_first=true로 onChange가 호출된다', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel
        config={{ ...DEFAULT_RAG_CONFIG, use_wiki_first: false }}
        onChange={onChange}
      />,
    );

    const toggle = await screen.findByRole('checkbox', { name: /위키 우선 검색/ });
    await user.click(toggle);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ use_wiki_first: true }),
    );
  });
});

describe('RagConfigPanel — 라우팅 검색 토글 (rag-routed-integration)', () => {
  it('기본값은 off이며, 체크 시 use_routed_search=true로 onChange가 호출된다', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel config={{ ...DEFAULT_RAG_CONFIG }} onChange={onChange} />,
    );

    const toggle = await screen.findByRole('checkbox', {
      name: /라우팅 검색 \(3계층 요약\)/,
    });
    expect(toggle).not.toBeChecked();
    await user.click(toggle);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ use_routed_search: true }),
    );
  });

  it('토글이 켜진 config는 체크 상태로 렌더되고, 해제 시 false로 전달된다', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel
        config={{ ...DEFAULT_RAG_CONFIG, use_routed_search: true }}
        onChange={onChange}
      />,
    );

    const toggle = await screen.findByRole('checkbox', {
      name: /라우팅 검색 \(3계층 요약\)/,
    });
    expect(toggle).toBeChecked();
    await user.click(toggle);
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ use_routed_search: false }),
    );
  });

  it('기존 검색 모드 라디오는 토글과 무관하게 유지된다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel
        config={{ ...DEFAULT_RAG_CONFIG, use_routed_search: true }}
        onChange={onChange}
      />,
    );

    expect(await screen.findByRole('radio', { name: '하이브리드' })).toBeChecked();
  });
});

describe('RagConfigPanel — scope 뱃지', () => {
  it('컬렉션 드롭다운 옵션에 scope 라벨이 포함된다', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel config={{ ...DEFAULT_RAG_CONFIG }} onChange={onChange} />,
    );

    await user.click(
      await screen.findByRole('combobox', { name: '검색 대상 컬렉션' }),
    );
    const optionTexts = screen.getAllByRole('option').map((o) => o.textContent);
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

    await screen.findByRole('combobox', { name: '검색 대상 컬렉션' });
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

    await screen.findByRole('combobox', { name: '검색 대상 컬렉션' });
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

    await screen.findByRole('combobox', { name: '검색 대상 컬렉션' });
    expect(screen.queryByText(/에이전트 공개 범위가 자동 제한/)).not.toBeInTheDocument();
  });

  it('컬렉션 미선택 시 제한 안내 메시지가 표시되지 않는다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel config={{ ...DEFAULT_RAG_CONFIG }} onChange={onChange} />,
    );

    await screen.findByRole('combobox', { name: '검색 대상 컬렉션' });
    expect(screen.queryByText(/에이전트 공개 범위가 자동 제한/)).not.toBeInTheDocument();
  });
});

describe('RagConfigPanel — 지식베이스 선택 (kb-rag-filter)', () => {
  it('지식베이스 드롭다운에 KB 이름과 scope 라벨이 표시된다', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel config={{ ...DEFAULT_RAG_CONFIG }} onChange={onChange} />,
    );

    await user.click(
      await screen.findByRole('combobox', { name: '검색 대상 지식베이스' }),
    );
    const optionTexts = screen.getAllByRole('option').map((o) => o.textContent);
    expect(optionTexts.some((t) => t?.includes('전사 규정'))).toBe(true);
    expect(optionTexts.some((t) => t?.includes('[부서]') && t?.includes('여신 심사 기준'))).toBe(true);
    expect(optionTexts.some((t) => t?.includes('[개인]') && t?.includes('내 메모'))).toBe(true);
  });

  it('KB 선택 시 kb_id 설정 + 컬렉션/필터 초기화로 onChange가 호출된다', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel
        config={{
          ...DEFAULT_RAG_CONFIG,
          collection_name: 'documents',
          metadata_filter: { department: 'finance' },
        }}
        onChange={onChange}
      />,
    );

    await user.click(
      await screen.findByRole('combobox', { name: '검색 대상 지식베이스' }),
    );
    await user.click(screen.getByRole('option', { name: /전사 규정/ }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({
        kb_id: 'kb-public-1',
        collection_name: undefined,
        metadata_filter: {},
      }),
    );
  });

  it('KB 선택 상태면 컬렉션 드롭다운이 비활성화되고 안내가 표시된다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel
        config={{ ...DEFAULT_RAG_CONFIG, kb_id: 'kb-public-1' }}
        onChange={onChange}
      />,
    );

    const collDropdown = await screen.findByRole('combobox', {
      name: '검색 대상 컬렉션',
    });
    expect(collDropdown).toBeDisabled();
    expect(
      await screen.findByText(/지식베이스의 컬렉션이 자동 적용/),
    ).toBeInTheDocument();
  });

  it('개인 KB 선택 시 공개범위 제한 안내가 표시된다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel
        config={{ ...DEFAULT_RAG_CONFIG, kb_id: 'kb-personal-1' }}
        onChange={onChange}
      />,
    );

    expect(
      await screen.findByText(/개인용이므로 에이전트 공개 범위가 자동 제한/),
    ).toBeInTheDocument();
  });

  it('공개 KB 선택 시 제한 안내가 표시되지 않는다', async () => {
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel
        config={{ ...DEFAULT_RAG_CONFIG, kb_id: 'kb-public-1' }}
        onChange={onChange}
      />,
    );

    await screen.findByRole('combobox', { name: '검색 대상 지식베이스' });
    expect(screen.queryByText(/에이전트 공개 범위가 자동 제한/)).not.toBeInTheDocument();
  });

  it('KB 해제(선택 안 함) 시 kb_id가 undefined로 전달된다', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    renderWithQuery(
      <RagConfigPanel
        config={{ ...DEFAULT_RAG_CONFIG, kb_id: 'kb-public-1' }}
        onChange={onChange}
      />,
    );

    await user.click(
      await screen.findByRole('combobox', { name: '검색 대상 지식베이스' }),
    );
    await user.click(screen.getByRole('option', { name: '선택 안 함' }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ kb_id: undefined, metadata_filter: {} }),
    );
  });
});
