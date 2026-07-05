import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ScheduleForm from './ScheduleForm';
import { mockSchedule } from '@/__tests__/mocks/handlers';

const renderForm = (props: Partial<Parameters<typeof ScheduleForm>[0]> = {}) => {
  const onSubmit = vi.fn();
  const onCancel = vi.fn();
  render(
    <ScheduleForm
      isSubmitting={false}
      submitError={null}
      onSubmit={onSubmit}
      onCancel={onCancel}
      {...props}
    />,
  );
  return { onSubmit, onCancel };
};

describe('ScheduleForm — 기본 렌더', () => {
  it('반복 유형 + 폼 모드로 시작하고 미리보기가 0 9 * * *이다', () => {
    renderForm();
    expect(screen.getByRole('button', { name: '반복' })).toBeInTheDocument();
    expect(screen.getByLabelText('분')).toHaveValue('0');
    expect(screen.getByLabelText('시')).toHaveValue('9');
    expect(screen.getByText('0 9 * * *')).toBeInTheDocument();
    expect(screen.getByText('Asia/Seoul')).toBeInTheDocument();
  });

  it('드롭다운 변경이 미리보기에 반영된다', async () => {
    renderForm();
    await userEvent.selectOptions(screen.getByLabelText('시'), '18');
    await userEvent.selectOptions(screen.getByLabelText('분'), '30');
    expect(screen.getByText('30 18 * * *')).toBeInTheDocument();
  });

  it('표현식 모드 전환 시 입력값이 미리보기에 반영된다', async () => {
    renderForm();
    await userEvent.click(screen.getByRole('button', { name: '스케줄 표현식' }));
    const input = screen.getByLabelText('cron 표현식');
    expect(input).toHaveValue('0 9 * * *');
    await userEvent.clear(input);
    await userEvent.type(input, '*/30 * * * *');
    expect(screen.getByText('*/30 * * * *')).toBeInTheDocument();
  });
});

describe('ScheduleForm — 검증', () => {
  it('실행 메시지가 비어있으면 제출을 차단한다', async () => {
    const { onSubmit } = renderForm();
    await userEvent.click(screen.getByRole('button', { name: '생성' }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('실행 메시지를 입력해주세요.')).toBeInTheDocument();
  });

  it('실행 메시지 1900자 초과 시 제출을 차단한다', async () => {
    const { onSubmit } = renderForm();
    // 1901자 입력 — userEvent.type은 키 단위라 느려서 fireEvent.change 사용
    fireEvent.change(screen.getByLabelText('실행 메시지'), {
      target: { value: 'a'.repeat(1901) },
    });
    await userEvent.click(screen.getByRole('button', { name: '생성' }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('실행 메시지는 최대 1900자입니다.')).toBeInTheDocument();
  });

  it('1회 모드 날짜 입력은 내일 이후만 선택 가능하다 (min 속성)', async () => {
    renderForm();
    await userEvent.click(screen.getByRole('button', { name: '1회' }));
    const dateInput = screen.getByLabelText('실행 날짜');
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const expected = `${tomorrow.getFullYear()}-${String(tomorrow.getMonth() + 1).padStart(2, '0')}-${String(tomorrow.getDate()).padStart(2, '0')}`;
    expect(dateInput).toHaveAttribute('min', expected);
  });

  it('잘못된 cron 표현식은 제출을 차단한다', async () => {
    const { onSubmit } = renderForm();
    await userEvent.type(screen.getByLabelText('실행 메시지'), '뉴스 요약');
    await userEvent.click(screen.getByRole('button', { name: '스케줄 표현식' }));
    const input = screen.getByLabelText('cron 표현식');
    await userEvent.clear(input);
    await userEvent.type(input, '*/5 * * * *');
    await userEvent.click(screen.getByRole('button', { name: '생성' }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText(/최소 10분/)).toBeInTheDocument();
  });

  it('1회 모드에서 과거 날짜는 차단한다', async () => {
    const { onSubmit } = renderForm();
    await userEvent.click(screen.getByRole('button', { name: '1회' }));
    await userEvent.type(screen.getByLabelText('실행 메시지'), '리포트');
    const dateInput = screen.getByLabelText('실행 날짜');
    // jsdom에서 date input은 fireEvent성 change 필요 — userEvent.type로 값 입력
    await userEvent.type(dateInput, '2020-01-01');
    await userEvent.click(screen.getByRole('button', { name: '생성' }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText('실행 날짜는 미래 날짜여야 합니다.')).toBeInTheDocument();
  });

  it('서버 400 메시지(submitError)를 표출한다', () => {
    renderForm({ submitError: '연속 발화 간격이 10분 미만입니다.' });
    expect(screen.getByText('연속 발화 간격이 10분 미만입니다.')).toBeInTheDocument();
  });
});

describe('ScheduleForm — 제출 payload', () => {
  it('반복(cron) payload — name 자동 생성 포함', async () => {
    const { onSubmit } = renderForm();
    // userEvent.type에서 '{{'는 리터럴 '{'로 입력된다
    await userEvent.type(screen.getByLabelText('실행 메시지'), '{{today} 뉴스 요약');
    await userEvent.click(screen.getByRole('button', { name: '생성' }));
    expect(onSubmit).toHaveBeenCalledWith({
      name: '매일 09:00 실행',
      spec: { schedule_type: 'cron', cron_expr: '0 9 * * *' },
      instruction: '{today} 뉴스 요약',
      timezone: 'Asia/Seoul',
      enabled: true,
    });
  });

  it('1회(once) payload', async () => {
    const { onSubmit } = renderForm();
    await userEvent.click(screen.getByRole('button', { name: '1회' }));
    await userEvent.type(screen.getByLabelText('실행 날짜'), '2099-12-31');
    await userEvent.type(screen.getByLabelText('실행 메시지'), '연말 리포트');
    await userEvent.click(screen.getByRole('button', { name: '생성' }));
    expect(onSubmit).toHaveBeenCalledWith({
      name: '1회 2099-12-31 09:00',
      spec: { schedule_type: 'once', run_date: '2099-12-31', time_of_day: '09:00' },
      instruction: '연말 리포트',
      timezone: 'Asia/Seoul',
      enabled: true,
    });
  });
});

describe('ScheduleForm — 수정 모드 (initial 주입)', () => {
  it('단순 cron은 폼 모드로 파싱되어 열린다', () => {
    renderForm({
      initial: mockSchedule({
        spec: { schedule_type: 'cron', cron_expr: '30 18 * * 1' },
      }),
    });
    expect(screen.getByLabelText('분')).toHaveValue('30');
    expect(screen.getByLabelText('시')).toHaveValue('18');
    expect(screen.getByLabelText('요일')).toHaveValue('1');
    expect(screen.getByRole('button', { name: '저장' })).toBeInTheDocument();
  });

  it('복합 cron은 표현식 모드로 열린다', () => {
    renderForm({
      initial: mockSchedule({
        spec: { schedule_type: 'cron', cron_expr: '*/30 * * * *' },
      }),
    });
    expect(screen.getByLabelText('cron 표현식')).toHaveValue('*/30 * * * *');
  });

  it('수정 제출 시 기존 enabled 상태를 유지한다', async () => {
    const { onSubmit } = renderForm({
      initial: mockSchedule({
        enabled: false,
        instruction: '기존 메시지',
        spec: { schedule_type: 'cron', cron_expr: '0 9 * * *' },
      }),
    });
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({ enabled: false, instruction: '기존 메시지' }),
    );
  });
});
