// Design Ref: wizard-chat-layout §5.3 — 2-모드 레이아웃 셸의 구조 경계.
// FR-15 회귀 가드: justify-center 는 overflow 시 상단이 잘려 도달 불가가 되므로
// 이 컴포넌트 트리 어디에도 존재해선 안 된다.
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import WizardShell from './WizardShell';

describe('WizardShell — centered 모드', () => {
  it('composer 를 렌더하지 않고 자식을 my-auto 래퍼에 담는다', () => {
    render(
      <WizardShell mode="centered" composer={<div data-testid="composer" />}>
        <div data-testid="child" />
      </WizardShell>,
    );

    expect(screen.queryByTestId('composer')).not.toBeInTheDocument();
    // my-auto 는 콘텐츠가 넘치면 0으로 붕괴해 잘림 없이 일반 스크롤이 된다 (FR-15)
    expect(
      screen.getByTestId('child').closest('.my-auto'),
    ).not.toBeNull();
  });

  it('justify-center 를 어디에도 쓰지 않는다 (FR-15)', () => {
    const { container } = render(
      <WizardShell mode="centered">
        <div />
      </WizardShell>,
    );

    expect(container.querySelector('[class*="justify-center"]')).toBeNull();
  });
});

describe('WizardShell — chat 모드', () => {
  it('composer 가 스크롤 영역 밖 형제로 렌더된다 — 겹침 구조 불가', () => {
    render(
      <WizardShell mode="chat" composer={<div data-testid="composer" />}>
        <div data-testid="child" />
      </WizardShell>,
    );

    const transcript = screen.getByTestId('wizard-transcript');
    const composer = screen.getByTestId('composer');
    expect(transcript.contains(screen.getByTestId('child'))).toBe(true);
    expect(transcript.contains(composer)).toBe(false);
  });

  it('justify-center 를 어디에도 쓰지 않는다 (FR-15)', () => {
    const { container } = render(
      <WizardShell mode="chat" composer={<div />}>
        <div />
      </WizardShell>,
    );

    expect(container.querySelector('[class*="justify-center"]')).toBeNull();
  });

  it('scrollKey 가 바뀌면 하단 근처일 때 맨 아래로 스크롤한다 (FR-10)', () => {
    const { rerender } = render(
      <WizardShell mode="chat" scrollKey="a">
        <div />
      </WizardShell>,
    );
    const el = screen.getByTestId('wizard-transcript');
    const scrollTo = vi.fn();
    el.scrollTo = scrollTo;
    Object.defineProperty(el, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(el, 'clientHeight', { value: 500, configurable: true });
    el.scrollTop = 450; // 바닥까지 50px — near-bottom(≤120px)
    fireEvent.scroll(el);

    rerender(
      <WizardShell mode="chat" scrollKey="b">
        <div />
      </WizardShell>,
    );

    expect(scrollTo).toHaveBeenCalled();
  });

  it('사용자가 위로 스크롤해 읽는 중이면 끌어내리지 않는다', () => {
    const { rerender } = render(
      <WizardShell mode="chat" scrollKey="a">
        <div />
      </WizardShell>,
    );
    const el = screen.getByTestId('wizard-transcript');
    const scrollTo = vi.fn();
    el.scrollTo = scrollTo;
    Object.defineProperty(el, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(el, 'clientHeight', { value: 500, configurable: true });
    el.scrollTop = 0; // 바닥까지 500px — 위를 보는 중
    fireEvent.scroll(el);

    rerender(
      <WizardShell mode="chat" scrollKey="b">
        <div />
      </WizardShell>,
    );

    expect(scrollTo).not.toHaveBeenCalled();
  });
});
