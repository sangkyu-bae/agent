// agent-token-limit Design D11 §5.2 — 한도 도달 사유별 채팅 안내 문구
import { describe, it, expect } from 'vitest';
import { limitReachedNotice } from './limitNotice';

describe('limitReachedNotice', () => {
  it('token 사유는 토큰 예산 문구와 설정 안내를 낸다', () => {
    const text = limitReachedNotice('token', true);
    expect(text).toContain('토큰 예산 한도에 도달');
    expect(text).toContain('토큰 예산을 올릴 수 있습니다');
  });

  it('iteration 사유는 반복 실행 문구를 낸다', () => {
    expect(limitReachedNotice('iteration', true)).toContain('반복 실행 한도에 도달');
  });

  it('사유 없이 도달만 표시되면 일반 문구를 낸다 (구 서버 호환)', () => {
    expect(limitReachedNotice(undefined, true)).toContain('실행 한도에 도달');
  });

  it('도달하지 않았으면 null', () => {
    expect(limitReachedNotice(undefined, false)).toBeNull();
    expect(limitReachedNotice(undefined, undefined)).toBeNull();
  });

  it('사유가 있으면 reached 플래그 없이도 문구를 낸다', () => {
    expect(limitReachedNotice('token', undefined)).toContain('토큰 예산');
  });
});
