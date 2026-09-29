// approval-edit-before-approve Design §5.3 (F1) — 수정 후 승인 순수 규칙
import { describe, expect, it } from 'vitest';
import {
  buildEditForm,
  diffEditedArgs,
  hasNonBodyChange,
} from './approvalEdit';

const displayArgs = {
  to: 'a@x.com',
  subject: '제목',
  body: '원본 본문',
  priority: 1,
};

describe('buildEditForm', () => {
  it('editable_keys 의 현재 값으로 폼 초기값을 만든다', () => {
    expect(buildEditForm(displayArgs, ['to', 'body'])).toEqual({
      to: 'a@x.com',
      body: '원본 본문',
    });
  });

  it('문자열이 아닌 값은 폼에 넣지 않는다', () => {
    expect(buildEditForm(displayArgs, ['priority'])).toEqual({});
  });
});

describe('diffEditedArgs', () => {
  it('바뀐 키만 돌려준다', () => {
    const form = { to: 'a@x.com', subject: '새 제목', body: '원본 본문' };
    expect(diffEditedArgs(displayArgs, form)).toEqual({ subject: '새 제목' });
  });

  it('변경이 없으면 빈 객체', () => {
    expect(diffEditedArgs(displayArgs, { body: '원본 본문' })).toEqual({});
  });
});

describe('hasNonBodyChange', () => {
  it('본문 외 키가 바뀌면 true', () => {
    expect(hasNonBodyChange({ body: 'x', to: 'b' }, 'body')).toBe(true);
  });

  it('본문만 바뀌면 false', () => {
    expect(hasNonBodyChange({ body: 'x' }, 'body')).toBe(false);
  });

  it('본문 키를 모르면 변경이 있는 한 true', () => {
    expect(hasNonBodyChange({ body: 'x' }, null)).toBe(true);
  });
});
