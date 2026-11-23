import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest';
import { server } from '@/__tests__/mocks/server';
import { createWrapper } from '@/__tests__/mocks/wrapper';
import { API_ENDPOINTS } from '@/constants/api';
import GroundingJudgeModelCard from './GroundingJudgeModelCard';

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

const renderCard = () => {
  const Wrapper = createWrapper();
  return render(
    <Wrapper>
      <GroundingJudgeModelCard />
    </Wrapper>
  );
};

describe('GroundingJudgeModelCard', () => {
  it('현재 적용 모델과 출처를 보여 준다', async () => {
    renderCard();
    expect(await screen.findByText(/현재 적용/)).toBeInTheDocument();
    expect(screen.getByText('GPT-4o · gpt-4o')).toBeInTheDocument();
    expect(screen.getByText('(서버 환경 설정)')).toBeInTheDocument();
  });

  it('활성 채팅 모델만 선택지로 보이고 설정 안 함이 기본 선택이다', async () => {
    renderCard();
    const select = await screen.findByRole('combobox', { name: '근거 판정 모델' });
    await waitFor(() =>
      expect(screen.getByRole('option', { name: /Claude Sonnet 4.6/ })).toBeInTheDocument()
    );
    expect((select as HTMLSelectElement).value).toBe('');
    expect(screen.getByRole('option', { name: /설정 안 함/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /이미지|image/i })).not.toBeInTheDocument();
  });

  it('바꾸지 않으면 저장 버튼이 비활성이다', async () => {
    renderCard();
    await screen.findByRole('combobox', { name: '근거 판정 모델' });
    expect(screen.getByRole('button', { name: '판정 모델 저장' })).toBeDisabled();
  });

  it('모델을 골라 저장하면 적용 모델이 관리자 설정으로 바뀐다', async () => {
    const user = userEvent.setup();
    renderCard();
    const select = await screen.findByRole('combobox', { name: '근거 판정 모델' });
    await waitFor(() =>
      expect(screen.getByRole('option', { name: /Claude Sonnet 4.6/ })).toBeInTheDocument()
    );
    await user.selectOptions(select, 'uuid-2');
    await user.click(screen.getByRole('button', { name: '판정 모델 저장' }));
    expect(await screen.findByText(/관리자 설정/)).toBeInTheDocument();
    expect(screen.getByText('Claude Sonnet 4.6 · claude-sonnet-4-6')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '판정 모델 저장' })).toBeDisabled();
  });

  it('저장 실패 메시지를 보여 준다', async () => {
    server.use(
      http.put(`*${API_ENDPOINTS.ADMIN_GROUNDING_JUDGE_SETTINGS}`, () =>
        HttpResponse.json(
          { detail: { code: 'JUDGE_MODEL_NOT_FOUND', message: '사용할 수 없는 모델입니다' } },
          { status: 422 }
        )
      )
    );
    const user = userEvent.setup();
    renderCard();
    const select = await screen.findByRole('combobox', { name: '근거 판정 모델' });
    await waitFor(() =>
      expect(screen.getByRole('option', { name: /Claude Sonnet 4.6/ })).toBeInTheDocument()
    );
    await user.selectOptions(select, 'uuid-2');
    await user.click(screen.getByRole('button', { name: '판정 모델 저장' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('사용할 수 없는 모델입니다');
  });

  it('판정 품질 안내 문구가 있다', async () => {
    renderCard();
    expect(await screen.findByText(/근거 판정과 인용 검증에 함께 쓰입니다/)).toBeInTheDocument();
  });
});
