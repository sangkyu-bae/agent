// agent-kb-quick-setup Design §8.3 L2 #10~#12 — 위저드 문서 단계 (MSW 기본 핸들러)
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, afterEach, afterAll, describe, it, expect, vi } from 'vitest';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import DocumentsStep from './DocumentsStep';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderStep = (over: Partial<Parameters<typeof DocumentsStep>[0]> = {}) => {
  const props = {
    agentName: '문서 Q&A 봇',
    attachedKbId: null,
    isPending: false,
    onAttached: vi.fn(),
    onDetach: vi.fn(),
    onSkip: vi.fn(),
    onContinue: vi.fn(),
    ...over,
  };
  const Wrapper = createWrapper();
  render(
    <Wrapper>
      <DocumentsStep {...props} />
    </Wrapper>,
  );
  return props;
};

describe('DocumentsStep', () => {
  it('제목·블록·건너뛰기가 보이고 KB 없이는 [계속]이 비활성이다', async () => {
    renderStep();
    expect(screen.getByText('참고할 문서가 있나요?')).toBeInTheDocument();
    expect(await screen.findByRole('region', { name: '지식 문서' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '건너뛰기' })).not.toBeDisabled();
    expect(screen.getByRole('button', { name: '계속' })).toBeDisabled();
  });

  it('[건너뛰기]는 onSkip 을 부른다', async () => {
    const props = renderStep();
    await userEvent.click(screen.getByRole('button', { name: '건너뛰기' }));
    expect(props.onSkip).toHaveBeenCalled();
  });

  it('KB 가 연결되면 [계속]이 활성화되고 onContinue 를 부른다', async () => {
    const props = renderStep({ attachedKbId: 'kb-public-1' });
    expect(await screen.findByText(/연결됨: 전사 규정/)).toBeInTheDocument();
    const next = screen.getByRole('button', { name: '계속' });
    expect(next).not.toBeDisabled();
    await userEvent.click(next);
    expect(props.onContinue).toHaveBeenCalled();
  });

  it('기존 KB 선택이 onAttached 로 전달된다', async () => {
    const props = renderStep();
    await userEvent.click(await screen.findByRole('combobox', { name: '기존 지식베이스 선택' }));
    await userEvent.click(await screen.findByRole('option', { name: '[부서] 여신 심사 기준' }));
    expect(props.onAttached).toHaveBeenCalledWith('kb-dept-1');
  });

  it('locked 면 버튼이 사라지고 완료 배지만 남는다', async () => {
    renderStep({ attachedKbId: 'kb-public-1', locked: true });
    await screen.findByText(/연결됨/);
    expect(screen.getByText('✓ 문서 연결 완료')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '계속' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '바꾸기' })).not.toBeInTheDocument();
  });

  it('locked + KB 없음이면 건너뜀 배지', () => {
    renderStep({ locked: true });
    expect(screen.getByText('✓ 건너뜀')).toBeInTheDocument();
  });
});
