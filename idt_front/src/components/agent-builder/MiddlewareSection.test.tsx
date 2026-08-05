// builtin-middleware D10: 폼 미들웨어 섹션 — 빌트인 배지·enforced 잠금·토글.
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MiddlewareSection } from '@/components/agent-builder/LeftConfigPanel';
import type { MiddlewareCatalogItem } from '@/types/middleware';

const item = (
  overrides: Partial<MiddlewareCatalogItem> = {},
): MiddlewareCatalogItem => ({
  middleware_type: 'model_retry',
  name: 'LLM 재시도',
  description: 'LLM 호출 실패 시 지수 백오프로 자동 재시도합니다.',
  is_builtin: true,
  is_enforced: false,
  default_config: { max_retries: 3 },
  is_active: true,
  sort_order: 10,
  ...overrides,
});

const renderSection = (
  props: Partial<Parameters<typeof MiddlewareSection>[0]> = {},
) => {
  const onToggle = vi.fn();
  render(
    <MiddlewareSection
      catalog={[item()]}
      isEditMode={false}
      middlewares={[]}
      excludedBuiltinMiddlewares={[]}
      onToggle={onToggle}
      {...props}
    />,
  );
  return { onToggle };
};

describe('MiddlewareSection (create 모드)', () => {
  it('빌트인은 기본 체크 + "기본" 배지', () => {
    renderSection();
    expect(screen.getByRole('checkbox')).toBeChecked();
    expect(screen.getByText('기본')).toBeInTheDocument();
    expect(screen.getByText(/지수 백오프/)).toBeInTheDocument();
  });

  it('해제 상태(excluded)면 체크 해제', () => {
    renderSection({ excludedBuiltinMiddlewares: ['model_retry'] });
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });

  it('체크 토글 시 onToggle(middleware_type) 호출', () => {
    const { onToggle } = renderSection();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onToggle).toHaveBeenCalledWith('model_retry');
  });

  it('enforced는 체크 고정 + disabled + 잠금 안내', () => {
    const { onToggle } = renderSection({
      catalog: [
        item({
          middleware_type: 'model_call_limit',
          name: '모델 호출 상한',
          is_builtin: false,
          is_enforced: true,
        }),
      ],
    });
    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).toBeChecked();
    expect(checkbox).toBeDisabled();
    expect(screen.getByText(/항상 적용/)).toBeInTheDocument();
    fireEvent.click(checkbox);
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('create 모드에선 비빌트인·비강제 항목을 노출하지 않는다', () => {
    renderSection({
      catalog: [
        item(),
        item({
          middleware_type: 'model_fallback',
          name: '모델 폴백',
          is_builtin: false,
          is_enforced: false,
        }),
      ],
    });
    expect(screen.queryByText('모델 폴백')).not.toBeInTheDocument();
  });

  it('inactive 항목은 숨긴다', () => {
    renderSection({ catalog: [item({ is_active: false })] });
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  });

  it('설정값 요약을 읽기 전용으로 표시한다', () => {
    renderSection();
    expect(screen.getByText(/max_retries: 3/)).toBeInTheDocument();
  });
});

describe('MiddlewareSection (edit 모드)', () => {
  it('전 항목 노출 + 프리필(middlewares) 기준 체크', () => {
    renderSection({
      isEditMode: true,
      middlewares: ['model_retry'],
      catalog: [
        item(),
        item({
          middleware_type: 'model_fallback',
          name: '모델 폴백',
          is_builtin: false,
          is_enforced: false,
        }),
      ],
    });
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes[0]).toBeChecked(); // model_retry (프리필)
    expect(checkboxes[1]).not.toBeChecked(); // model_fallback
  });

  it('edit 모드 토글도 onToggle로 위임', () => {
    const { onToggle } = renderSection({ isEditMode: true, middlewares: [] });
    fireEvent.click(screen.getByRole('checkbox'));
    expect(onToggle).toHaveBeenCalledWith('model_retry');
  });
});
