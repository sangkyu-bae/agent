/**
 * CustomChunkingFields 테스트 (kb-custom-chunking Design §8.2)
 *
 * 전략 전환 시 필드 표시/초기화, 경계 규칙 편집, 정규식 인라인 에러.
 */
import { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import CustomChunkingFields from './CustomChunkingFields';
import {
  defaultCustomChunkingForm,
  validateCustomChunkingForm,
  buildCustomChunkingConfig,
  type CustomChunkingFormState,
} from './customChunkingForm';

const Harness = ({
  initial = defaultCustomChunkingForm(),
  onState,
}: {
  initial?: CustomChunkingFormState;
  onState?: (v: CustomChunkingFormState) => void;
}) => {
  const [form, setForm] = useState(initial);
  return (
    <CustomChunkingFields
      value={form}
      onChange={(next) => {
        setForm(next);
        onState?.(next);
      }}
    />
  );
};

const selectStrategy = async (label: string) => {
  await userEvent.click(
    screen.getByRole('combobox', { name: '청킹 전략' }),
  );
  await userEvent.click(await screen.findByRole('option', { name: label }));
};

describe('CustomChunkingFields — 전략별 필드 전환', () => {
  it('기본(parent_child)은 크기·오버랩·부모 크기를 노출한다', () => {
    render(<Harness />);
    expect(screen.getByLabelText(/^청크 크기/)).toBeInTheDocument();
    expect(screen.getByLabelText(/오버랩/)).toBeInTheDocument();
    expect(screen.getByLabelText(/부모 청크 크기/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/최소 청크 크기/)).not.toBeInTheDocument();
  });

  it('semantic 선택 시 오버랩이 숨고 0으로 초기화된다 (D12)', async () => {
    let last: CustomChunkingFormState | undefined;
    render(<Harness onState={(v) => (last = v)} />);

    await selectStrategy('시맨틱');

    expect(screen.queryByLabelText(/오버랩/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/최소 청크 크기/)).toBeInTheDocument();
    expect(last?.chunkOverlap).toBe('0');
  });

  it('boundary_pattern 선택 시 경계 규칙 편집기가 열린다', async () => {
    render(<Harness />);
    await selectStrategy('경계 패턴 (정규식)');
    expect(
      screen.getByRole('button', { name: '+ 규칙 추가' }),
    ).toBeInTheDocument();
  });
});

describe('CustomChunkingFields — 경계 규칙 편집', () => {
  it('규칙 추가/삭제가 동작한다', async () => {
    render(<Harness />);
    await selectStrategy('경계 패턴 (정규식)');

    await userEvent.click(screen.getByRole('button', { name: '+ 규칙 추가' }));
    expect(screen.getByLabelText('규칙 1 정규식')).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText('규칙 1 삭제'));
    expect(screen.queryByLabelText('규칙 1 정규식')).not.toBeInTheDocument();
  });

  it('잘못된 정규식에 인라인 에러를 표시한다', async () => {
    render(<Harness />);
    await selectStrategy('경계 패턴 (정규식)');
    await userEvent.click(screen.getByRole('button', { name: '+ 규칙 추가' }));

    // '['는 userEvent 키 디스크립터라 fireEvent로 직접 입력
    fireEvent.change(screen.getByLabelText('규칙 1 정규식'), {
      target: { value: '[unclosed' },
    });

    expect(screen.getByText('잘못된 정규식입니다')).toBeInTheDocument();
  });
});

describe('customChunkingForm — 검증/변환 (백엔드 V-01~V-05 대응)', () => {
  it('유효한 기본 폼은 통과한다', () => {
    expect(validateCustomChunkingForm(defaultCustomChunkingForm())).toBeNull();
  });

  it('오버랩이 크기 이상이면 거부한다', () => {
    const form = {
      ...defaultCustomChunkingForm(),
      chunkSize: '100',
      chunkOverlap: '100',
    };
    expect(validateCustomChunkingForm(form)).toMatch(/오버랩/);
  });

  it('boundary_pattern은 parent 규칙 없이는 거부한다', () => {
    const form: CustomChunkingFormState = {
      ...defaultCustomChunkingForm(),
      strategy: 'boundary_pattern',
      rules: [{ pattern: '^a', priority: '1', level: 'child' }],
    };
    expect(validateCustomChunkingForm(form)).toMatch(/parent/);
  });

  it('빌드 시 미지정 optional은 생략된다', () => {
    const config = buildCustomChunkingConfig(defaultCustomChunkingForm());
    expect(config).toEqual({
      version: 1,
      strategy: 'parent_child',
      chunk_size: 500,
      chunk_overlap: 50,
    });
  });

  it('boundary_pattern 빌드에 규칙이 숫자 priority로 담긴다', () => {
    const form: CustomChunkingFormState = {
      ...defaultCustomChunkingForm(),
      strategy: 'boundary_pattern',
      rules: [{ pattern: '^제\\d+조', priority: '2', level: 'parent' }],
    };
    const config = buildCustomChunkingConfig(form);
    expect(config.boundary_rules).toEqual([
      { pattern: '^제\\d+조', priority: 2, level: 'parent' },
    ]);
  });
});
