/**
 * KbProfileSelect 테스트 (kb-profile-selector Design §8.3)
 */
import { useState } from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import KbProfileSelect from './KbProfileSelect';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

interface HarnessProps {
  initialId?: string | null;
  onChange?: (id: string | null) => void;
  kbChunkSize?: number | null;
  kbChunkOverlap?: number | null;
}

const Harness = ({
  initialId = null,
  onChange = vi.fn(),
  kbChunkSize,
  kbChunkOverlap,
}: HarnessProps) => {
  const [selectedId, setSelectedId] = useState(initialId);
  return (
    <KbProfileSelect
      selectedId={selectedId}
      onChange={(id) => {
        setSelectedId(id);
        onChange(id);
      }}
      kbChunkSize={kbChunkSize}
      kbChunkOverlap={kbChunkOverlap}
    />
  );
};

const renderSelect = (props: HarnessProps = {}) =>
  render(<Harness {...props} />, { wrapper: createWrapper() });

const combobox = () =>
  screen.findByRole('combobox', { name: '청킹 프로파일' });

describe('KbProfileSelect', () => {
  it('C1: 기본 따름 항목과 기본 badge를 보여준다', async () => {
    renderSelect();

    await userEvent.click(await combobox());

    expect(
      screen.getByRole('option', {
        name: /기본 프로파일 따름 \(금융 조항 기본\)/,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('option', { name: /금융 조항 기본.*기본\]/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole('option', { name: '계약서' })).toBeInTheDocument();
  });

  it('C2: 프로파일을 고르면 onChange를 호출하고 상세를 바꾼다', async () => {
    const onChange = vi.fn();
    renderSelect({ onChange });

    expect(await screen.findByText(/경계 규칙 2개/)).toBeInTheDocument();
    expect(screen.getByText(/섹션 요약 사용/)).toBeInTheDocument();

    await userEvent.click(await combobox());
    await userEvent.click(screen.getByRole('option', { name: '계약서' }));

    expect(onChange).toHaveBeenCalledWith('prof-contract');
    expect(screen.getByText(/부모 3000/)).toBeInTheDocument();
    expect(screen.getByText(/경계 규칙 1개/)).toBeInTheDocument();
    expect(screen.getByText(/섹션 요약 미사용/)).toBeInTheDocument();
  });

  it('C3: 기본 따름을 고르면 null로 알린다', async () => {
    const onChange = vi.fn();
    renderSelect({ initialId: 'prof-contract', onChange });

    await userEvent.click(await combobox());
    await userEvent.click(
      screen.getByRole('option', { name: /기본 프로파일 따름/ }),
    );

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('C4: KB 오버라이드가 있으면 실제 적용 크기를 보여준다', async () => {
    renderSelect({ kbChunkSize: 700, kbChunkOverlap: 0 });

    expect(await screen.findByText(/청크 700/)).toBeInTheDocument();
    expect(screen.getByText(/오버랩 0/)).toBeInTheDocument();
  });

  it('C5: 조회 실패 시 안내하고 재시도로 다시 조회한다', async () => {
    let calls = 0;
    server.use(
      http.get(`*${API_ENDPOINTS.CHUNKING_PROFILES}`, () => {
        calls += 1;
        return HttpResponse.json({ detail: 'boom' }, { status: 500 });
      }),
    );
    renderSelect({ initialId: 'prof-contract' });

    expect(
      await screen.findByText(/저장해도 현재 지정은 유지됩니다/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/삭제되어 기본 프로파일로 처리됩니다/),
    ).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));

    await waitFor(() => expect(calls).toBe(2));
  });

  it('C6: 지정 ID가 목록에 없으면 삭제 경고를 보여준다', async () => {
    renderSelect({ initialId: 'prof-deleted' });

    expect(
      await screen.findByText(/삭제되어 기본 프로파일로 처리됩니다/),
    ).toBeInTheDocument();
    expect(await combobox()).toHaveTextContent('기본 프로파일 따름');
  });

  it('C7: 프로파일이 없으면 기본 청킹 안내를 보여준다', async () => {
    server.use(
      http.get(`*${API_ENDPOINTS.CHUNKING_PROFILES}`, () =>
        HttpResponse.json({ profiles: [], total: 0 }),
      ),
    );
    renderSelect();

    expect(
      await screen.findByText(/업로드가 기본 청킹으로 처리됩니다/),
    ).toBeInTheDocument();
  });

  it('C8: 관리자 API를 호출하지 않는다', async () => {
    let adminCalls = 0;
    server.use(
      http.get(`*${API_ENDPOINTS.ADMIN_CHUNKING_PROFILES}`, () => {
        adminCalls += 1;
        return HttpResponse.json({ detail: 'forbidden' }, { status: 403 });
      }),
    );
    renderSelect();

    await screen.findByText(/경계 규칙 2개/);
    expect(adminCalls).toBe(0);
  });
});
