import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';

import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import WikiPage from './index';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe('WikiPage', () => {
  it('헤더와 빈 상태 안내가 렌더된다', () => {
    render(<WikiPage />, { wrapper: createWrapper() });
    expect(screen.getByText('위키 관리')).toBeInTheDocument();
    expect(
      screen.getByText(/에이전트 ID를 입력하면 위키 목록이 표시됩니다/),
    ).toBeInTheDocument();
  });

  it('에이전트 ID 입력 시 목록이 로드된다', async () => {
    const user = userEvent.setup();
    render(<WikiPage />, { wrapper: createWrapper() });
    await user.type(screen.getByPlaceholderText('agent_id'), 'agent-1');
    expect(await screen.findByText('위키-w1')).toBeInTheDocument();
  });
});
