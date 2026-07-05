import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import Modal from './Modal';

describe('Modal', () => {
  it('isOpen=false면 렌더되지 않는다', () => {
    render(
      <Modal isOpen={false} title="테스트 모달" onClose={vi.fn()}>
        <p>본문</p>
      </Modal>,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('타이틀/본문/footer를 렌더하고 role=dialog + aria-modal을 부여한다', () => {
    render(
      <Modal title="테스트 모달" onClose={vi.fn()} footer={<button>저장</button>}>
        <p>본문 콘텐츠</p>
      </Modal>,
    );
    const dialog = screen.getByRole('dialog', { name: '테스트 모달' });
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(screen.getByText('본문 콘텐츠')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '저장' })).toBeInTheDocument();
  });

  it('X 버튼 클릭 시 onClose가 호출된다', async () => {
    const onClose = vi.fn();
    render(
      <Modal title="테스트 모달" onClose={onClose}>
        <p>본문</p>
      </Modal>,
    );
    await userEvent.click(screen.getByRole('button', { name: '닫기' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('ESC 키 입력 시 onClose가 호출된다', async () => {
    const onClose = vi.fn();
    render(
      <Modal title="테스트 모달" onClose={onClose}>
        <p>본문</p>
      </Modal>,
    );
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('배경 클릭 시 onClose가 호출되고, 콘텐츠 클릭은 무시된다', async () => {
    const onClose = vi.fn();
    render(
      <Modal title="테스트 모달" onClose={onClose}>
        <p>본문</p>
      </Modal>,
    );
    await userEvent.click(screen.getByText('본문'));
    expect(onClose).not.toHaveBeenCalled();

    const overlay = screen.getByRole('dialog').parentElement!;
    await userEvent.click(overlay);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closeOnBackdrop=false면 배경 클릭이 무시된다', async () => {
    const onClose = vi.fn();
    render(
      <Modal title="테스트 모달" closeOnBackdrop={false} onClose={onClose}>
        <p>본문</p>
      </Modal>,
    );
    const overlay = screen.getByRole('dialog').parentElement!;
    await userEvent.click(overlay);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('disableClose=true면 배경/ESC/X 모두 닫히지 않는다', async () => {
    const onClose = vi.fn();
    render(
      <Modal title="테스트 모달" disableClose onClose={onClose}>
        <p>본문</p>
      </Modal>,
    );
    await userEvent.keyboard('{Escape}');
    const overlay = screen.getByRole('dialog').parentElement!;
    await userEvent.click(overlay);
    expect(screen.getByRole('button', { name: '닫기' })).toBeDisabled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('title 생략 시 헤더를 렌더하지 않는다', () => {
    render(
      <Modal onClose={vi.fn()}>
        <p>본문</p>
      </Modal>,
    );
    expect(screen.queryByRole('button', { name: '닫기' })).toBeNull();
    expect(document.querySelector('h2')).toBeNull();
  });
});
