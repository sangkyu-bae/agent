// Design Ref: source-passage-viewer §5.3, §6, §8.3 #9 — 패널 오류가 채팅 화면으로 번지지 않는다
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { createWrapper } from '@/__tests__/mocks/wrapper';
import { useSourceViewerStore } from '@/store/sourceViewerStore';

import SourceViewerMount from './SourceViewerMount';

const panelMode = vi.hoisted(() => ({ throws: false }));

vi.mock('./SourceViewerPanel', () => ({
  default: () => {
    if (panelMode.throws) throw new Error('render boom');
    return <div>패널 본문</div>;
  },
}));

const openTarget = () =>
  useSourceViewerStore.getState().open({
    filename: '규정.pdf',
    viewer: { document_id: 'doc-1', kb_id: 'kb-1', original: null, passages: [] },
  });

describe('SourceViewerMount', () => {
  beforeEach(() => {
    panelMode.throws = false;
    useSourceViewerStore.getState().close();
  });
  afterEach(() => vi.restoreAllMocks());

  it('대상이 없으면 아무것도 그리지 않는다', () => {
    const { container } = render(<SourceViewerMount />, { wrapper: createWrapper() });
    expect(container).toBeEmptyDOMElement();
  });

  it('대상이 생기면 패널을 지연 로드해 그린다', async () => {
    openTarget();
    render(<SourceViewerMount />, { wrapper: createWrapper() });
    expect(await screen.findByText('패널 본문')).toBeInTheDocument();
  });

  it('패널이 throw 하면 안내를 보여 주고 닫을 수 있다', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    panelMode.throws = true;
    openTarget();
    render(
      <div>
        <p>채팅 화면</p>
        <SourceViewerMount />
      </div>,
      { wrapper: createWrapper() },
    );
    expect(await screen.findByText('원문을 열 수 없습니다.')).toBeInTheDocument();
    expect(screen.getByText('채팅 화면')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '원문 패널 닫기' }));
    expect(useSourceViewerStore.getState().target).toBeNull();
  });

  // Analysis 갭 #4: Esc 처리가 패널 안에만 있으면 오류 대체 화면은 Esc 로 닫히지 않는다.
  it('오류 대체 화면도 Esc 로 닫힌다', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    panelMode.throws = true;
    openTarget();
    render(<SourceViewerMount />, { wrapper: createWrapper() });
    await screen.findByText('원문을 열 수 없습니다.');
    await userEvent.keyboard('{Escape}');
    expect(useSourceViewerStore.getState().target).toBeNull();
  });
});
