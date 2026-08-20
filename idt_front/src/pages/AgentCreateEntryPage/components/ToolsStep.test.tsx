// Design §5.4 step③ — 추천 도구 토글·직접 추가·제외 안내의 props 경계.
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
import ToolsStep from './ToolsStep';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const tool = (toolId: string, name: string, description: string) => ({
  tool_id: toolId,
  source: 'internal',
  name,
  description,
  mcp_server_id: null,
  mcp_server_name: null,
  requires_env: [],
  is_builtin: false,
});

const stubCatalog = () =>
  server.use(
    http.get(`*${API_ENDPOINTS.TOOL_CATALOG}`, () =>
      HttpResponse.json({
        tools: [
          tool('internal:a', '문서 검색', '사내 문서를 찾는다'),
          tool('internal:b', '엑셀 내보내기', '표를 저장한다'),
          tool('internal:c', '웹 검색', '웹을 찾는다'),
        ],
      }),
    ),
  );

const setup = (props: Partial<Parameters<typeof ToolsStep>[0]> = {}) => {
  stubCatalog();
  const onToggle = vi.fn();
  const onConfirm = vi.fn();
  const onRestart = vi.fn();
  render(
    <ToolsStep
      recommendedIds={['internal:a', 'internal:b']}
      selectedIds={['internal:a', 'internal:b']}
      unknownIds={[]}
      isPending={false}
      onToggle={onToggle}
      onConfirm={onConfirm}
      onRestart={onRestart}
      {...props}
    />,
    { wrapper: createWrapper() },
  );
  return { onToggle, onConfirm, onRestart, user: userEvent.setup() };
};

const checkboxOf = (name: string) =>
  screen.getByText(name).closest('label')!.querySelector('input')!;

describe('ToolsStep', () => {
  it('추천 도구를 이름·설명과 함께 기본 선택 상태로 보여준다', async () => {
    setup();

    expect(await screen.findByText('문서 검색')).toBeInTheDocument();
    expect(screen.getByText('사내 문서를 찾는다')).toBeInTheDocument();
    expect(screen.getAllByRole('checkbox')).toHaveLength(2);
    expect(checkboxOf('문서 검색')).toBeChecked();
  });

  it('카탈로그에 이름이 없으면 tool_id 를 그대로 보여준다', async () => {
    setup({ recommendedIds: ['internal:zzz'], selectedIds: ['internal:zzz'] });

    expect(await screen.findByText('internal:zzz')).toBeInTheDocument();
  });

  it('체크박스를 누르면 해당 id 로 onToggle 을 올린다', async () => {
    const { onToggle, user } = setup();
    await screen.findByText('엑셀 내보내기');

    await user.click(checkboxOf('엑셀 내보내기'));

    expect(onToggle).toHaveBeenCalledWith('internal:b');
  });

  it('추천 밖에서 고른 도구는 "직접 추가" 배지로 구분한다', async () => {
    setup({
      recommendedIds: ['internal:a'],
      selectedIds: ['internal:a', 'internal:c'],
    });

    expect(await screen.findByText('웹 검색')).toBeInTheDocument();
    expect(screen.getByText('직접 추가')).toBeInTheDocument();
  });

  it('unknownIds 가 있으면 제외 안내를 띄운다', async () => {
    // 조용히 사라지면 사용자는 반영됐다고 오해한다.
    setup({ unknownIds: ['internal:ghost', 'internal:ghost2'] });

    expect(
      await screen.findByText(/2개 도구는 카탈로그에 없거나/),
    ).toBeInTheDocument();
  });

  it('추천이 0건이면 빈 상태를 안내한다', async () => {
    setup({ recommendedIds: [], selectedIds: [] });

    expect(
      await screen.findByText('추천할 도구를 찾지 못했어요.'),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
  });

  it('[이 도구로 진행]은 onConfirm 을 호출한다', async () => {
    const { onConfirm, user } = setup();

    await user.click(screen.getByRole('button', { name: '이 도구로 진행' }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('[처음부터]는 onRestart 를 호출한다 — 되돌리기가 아니라 초기화다', async () => {
    // 무상태 위저드라 step② 복귀가 불가능하다. 라벨과 콜백 이름이 동작과 같아야
    // 호출자가 확인 절차를 빠뜨리지 않는다.
    const { onRestart, user } = setup();

    await user.click(screen.getByRole('button', { name: '처음부터' }));

    expect(onRestart).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: '이전' })).not.toBeInTheDocument();
  });

  it('[도구 더 추가]는 카탈로그 모달을 연다', async () => {
    const { user } = setup();
    await screen.findByText('문서 검색');

    await user.click(screen.getByRole('button', { name: '도구 더 추가' }));

    expect(await screen.findByText('도구 추가')).toBeInTheDocument();
    expect(await screen.findByText('웹 검색')).toBeInTheDocument();
  });

  // wizard-chat-layout FR-09 — 프롬프트 단계 진입 후 도구 카드는 트랜스크립트에
  // 읽기 전용 이력으로 남는다.
  describe('locked', () => {
    it('토글을 잠그고 액션 버튼을 감춘 채 완료 배지를 보여준다', async () => {
      setup({ locked: true });
      await screen.findByText('문서 검색');

      expect(screen.getByText(/선택 완료/)).toBeInTheDocument();
      expect(checkboxOf('문서 검색')).toBeDisabled();
      expect(
        screen.queryByRole('button', { name: '이 도구로 진행' }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: '처음부터' }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: '도구 더 추가' }),
      ).not.toBeInTheDocument();
    });

    it('잠긴 체크박스는 onToggle 을 올리지 않는다', async () => {
      const { onToggle, user } = setup({ locked: true });
      await screen.findByText('엑셀 내보내기');

      await user.click(checkboxOf('엑셀 내보내기'));

      expect(onToggle).not.toHaveBeenCalled();
    });
  });

  it('isPending 이면 모든 조작을 잠근다', async () => {
    setup({ isPending: true });
    await screen.findByText('문서 검색');

    expect(checkboxOf('문서 검색')).toBeDisabled();
    expect(screen.getByRole('button', { name: '처음부터' })).toBeDisabled();
    expect(screen.getByRole('button', { name: '도구 더 추가' })).toBeDisabled();
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /프롬프트 만드는 중/ }),
      ).toBeDisabled(),
    );
  });
});
