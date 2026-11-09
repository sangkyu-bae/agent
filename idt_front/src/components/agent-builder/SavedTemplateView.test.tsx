// extractor-template-preview Design §8.3 F4–F6: 저장된 양식 보기
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { AgentDocumentTemplateResponse } from '@/types/documentExtractor';
import SavedTemplateView from './SavedTemplateView';

const TEMPLATE: AgentDocumentTemplateResponse = {
  template_id: 'tpl-1',
  name: '여신 승인 신청서',
  source_format: 'docx',
  html_skeleton: '<p>차주: {{borrower_name}}</p><p>{{opinion}}</p>',
  slots: [
    {
      key: 'borrower_name',
      label: '차주명',
      slot_type: 'value',
      description: '',
      sample_value: '홍길동',
    },
    {
      key: 'opinion',
      // 실DB 라벨에는 원본 HTML 의 개행·탭이 섞여 있다
      label: '심사\n\t\t\t의견',
      slot_type: 'generated',
      description: '',
      sample_value: '',
    },
  ],
  samples_hidden: false,
  is_inherited: false,
  updated_at: '2026-11-09T00:00:00',
};

const renderView = (
  props: Partial<Parameters<typeof SavedTemplateView>[0]> = {},
) => {
  const onReplace = vi.fn();
  render(
    <SavedTemplateView
      template={TEMPLATE}
      isLoading={false}
      isError={false}
      onReplace={onReplace}
      {...props}
    />,
  );
  return { onReplace };
};

describe('SavedTemplateView', () => {
  it('F4: 양식 이름·포맷·슬롯 수·미리보기·슬롯 목록을 보여준다', () => {
    renderView();

    expect(screen.getByRole('heading', { name: '저장된 양식' })).toBeInTheDocument();
    expect(screen.getByText('여신 승인 신청서')).toBeInTheDocument();
    expect(screen.getByText('DOCX')).toBeInTheDocument();
    expect(screen.getByText('슬롯 2')).toBeInTheDocument();
    expect(screen.getByText(/채울 위치 확인용/)).toBeInTheDocument();

    const frame = screen.getByTitle('저장된 양식 미리보기');
    expect(frame).toHaveAttribute('sandbox', '');
    // 토큰 자리에 라벨이 하이라이트로 들어간다
    expect(frame.getAttribute('srcdoc')).toContain('차주명');
    expect(frame.getAttribute('srcdoc')).not.toContain('{{borrower_name}}');

    expect(screen.getByText('차주명')).toBeInTheDocument();
    // 라벨 공백은 접어서 보여준다
    expect(screen.getByText('심사 의견')).toBeInTheDocument();
    expect(screen.getByText('예: 홍길동')).toBeInTheDocument();
    expect(screen.getByText('값')).toBeInTheDocument();
    expect(screen.getByText('작성')).toBeInTheDocument();
  });

  it('F5: 예시값이 숨겨진 응답이면 안내를 띄우고 예시값을 그리지 않는다', () => {
    renderView({
      template: {
        ...TEMPLATE,
        samples_hidden: true,
        slots: TEMPLATE.slots.map((s) => ({ ...s, sample_value: '' })),
      },
    });

    expect(screen.getByText(/예시값은 양식을 만든 사용자에게만 보입니다/)).toBeInTheDocument();
    expect(screen.queryByText(/^예:/)).toBeNull();
  });

  it('F6: 포크로 받은 양식이면 배지를 단다', () => {
    renderView({ template: { ...TEMPLATE, is_inherited: true } });

    expect(screen.getByText('포크로 받은 양식')).toBeInTheDocument();
  });

  it('새 파일로 교체 버튼은 onReplace 를 부른다', async () => {
    const { onReplace } = renderView();

    await userEvent.click(screen.getByRole('button', { name: '새 파일로 교체' }));

    expect(onReplace).toHaveBeenCalledTimes(1);
  });

  it('로딩 중이면 불러오는 중 문구를 보여준다', () => {
    renderView({ template: undefined, isLoading: true });

    expect(screen.getByText('저장된 양식을 불러오는 중…')).toBeInTheDocument();
    expect(screen.queryByTitle('저장된 양식 미리보기')).toBeNull();
  });

  it('F9: 오류이거나 양식이 없으면 오류 문구와 교체 버튼만 보여준다', () => {
    renderView({ template: null, isError: false });

    expect(screen.getByText('저장된 양식을 불러오지 못했습니다')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '새 파일로 교체' })).toBeInTheDocument();
    expect(screen.queryByTitle('저장된 양식 미리보기')).toBeNull();
  });
});
