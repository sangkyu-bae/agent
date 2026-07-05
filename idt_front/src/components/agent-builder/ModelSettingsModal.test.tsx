import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import type { LlmModel } from '@/types/llmModel';
import ModelSettingsModal from './ModelSettingsModal';

const MODELS: LlmModel[] = [
  {
    id: 'm1',
    provider: 'anthropic',
    model_name: 'claude-haiku-4-5',
    display_name: 'claude-haiku-4-5',
    description: null,
    max_tokens: null,
    is_active: false,
    is_default: true,
  },
  {
    id: 'm2',
    provider: 'openai',
    model_name: 'gpt-4o',
    display_name: 'gpt-4o',
    description: null,
    max_tokens: null,
    is_active: true,
    is_default: false,
  },
];

describe('ModelSettingsModal', () => {
  it('isOpen=false면 렌더되지 않는다', () => {
    render(
      <ModelSettingsModal
        isOpen={false}
        models={MODELS}
        current={{ model: 'claude-haiku-4-5', temperature: 0.7 }}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.queryByText('모델 설정')).toBeNull();
  });

  it('모델 변경 + 저장 시 onApply가 선택값으로 호출된다', async () => {
    const onApply = vi.fn();
    const onClose = vi.fn();
    render(
      <ModelSettingsModal
        isOpen
        models={MODELS}
        current={{ model: 'claude-haiku-4-5', temperature: 0.7 }}
        onApply={onApply}
        onClose={onClose}
      />,
    );

    await userEvent.click(screen.getByRole('combobox'));
    await userEvent.click(screen.getByRole('option', { name: /gpt-4o/ }));
    await userEvent.click(screen.getByRole('button', { name: '저장' }));

    expect(onApply).toHaveBeenCalledWith({ model: 'gpt-4o', temperature: 0.7 });
    expect(onClose).toHaveBeenCalled();
  });

  it('취소 시 onApply 없이 onClose만 호출된다', async () => {
    const onApply = vi.fn();
    const onClose = vi.fn();
    render(
      <ModelSettingsModal
        isOpen
        models={MODELS}
        current={{ model: 'claude-haiku-4-5', temperature: 0.7 }}
        onApply={onApply}
        onClose={onClose}
      />,
    );

    await userEvent.click(screen.getByRole('button', { name: '취소' }));
    expect(onApply).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('최대 토큰/Top P/Top K 입력은 비활성이다', () => {
    render(
      <ModelSettingsModal
        isOpen
        models={MODELS}
        current={{ model: 'claude-haiku-4-5', temperature: 0.7 }}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    const disabledInputs = screen
      .getAllByPlaceholderText('(선택)')
      .filter((el) => (el as HTMLInputElement).disabled);
    expect(disabledInputs).toHaveLength(3);
  });

  it('활성 키가 없으면 경고 배너를 표시한다', () => {
    render(
      <ModelSettingsModal
        isOpen
        models={[MODELS[0]]}
        current={{ model: 'claude-haiku-4-5', temperature: 0.7 }}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/API 키가 등록되지 않았습니다/)).toBeTruthy();
  });

  it('로딩 중에는 스켈레톤을 표시하고 모델 select를 숨긴다', () => {
    render(
      <ModelSettingsModal
        isOpen
        isLoading
        current={{ model: '', temperature: 0.7 }}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(document.querySelector('.animate-pulse')).not.toBeNull();
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('에러 상태에서 다시 시도 버튼 클릭 시 onRetry가 호출된다', async () => {
    const onRetry = vi.fn();
    render(
      <ModelSettingsModal
        isOpen
        isError
        onRetry={onRetry}
        current={{ model: '', temperature: 0.7 }}
        onApply={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText('모델 목록을 불러올 수 없습니다')).toBeTruthy();
    await userEvent.click(screen.getByRole('button', { name: /다시 시도/ }));
    expect(onRetry).toHaveBeenCalled();
  });
});
