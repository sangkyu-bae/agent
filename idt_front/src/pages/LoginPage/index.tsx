import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useLogin } from '@/hooks/useAuth';
import { useAuthStore } from '@/store/authStore';

const ERROR_MESSAGES: Record<string, string> = {
  'Invalid credentials': '이메일 또는 비밀번호를 확인해 주세요.',
  'Account is pending approval': '관리자 승인을 기다려 주세요.',
  'Account has been rejected': '승인이 거절된 계정입니다. 관리자에게 문의하세요.',
};

const LoginPage = () => {
  const { isAuthenticated } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [formError, setFormError] = useState('');
  const { mutate: login, isPending } = useLogin();

  if (isAuthenticated) return <Navigate to="/" replace />;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    login(
      { email, password },
      {
        onError: (error) => {
          const msg = error.message;
          setFormError(ERROR_MESSAGES[msg] ?? '로그인 중 오류가 발생했습니다.');
        },
      }
    );
  };

  return (
    <div className="flex min-h-full items-center justify-center bg-white px-4">
      <div className="w-full max-w-md">
        <div className="rounded-2xl border border-zinc-200 bg-white p-8 shadow-sm">
          {/* 타이틀 */}
          <div className="mb-8 text-center">
            <div
              className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl shadow-md"
              style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
            >
              <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15M14.25 3.104c.251.023.501.05.75.082M19.8 15l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23-.607L5 14.5m14.8.5l-1.57.393A9.065 9.065 0 0112 15m0 0a9.065 9.065 0 00-6.23-.607" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-zinc-900">AI Agent Platform</h1>
            <p className="mt-1 text-[13px] text-zinc-400">계정에 로그인하세요</p>
          </div>

          {/* 에러 배너 */}
          {formError && (
            <div className="mb-4 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-[13px] text-red-600">
              {formError}
            </div>
          )}

          {/* 폼 */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-zinc-700">이메일</label>
              <div className="overflow-hidden rounded-xl border border-zinc-300 bg-white transition-all focus-within:border-violet-400 focus-within:shadow-[0_0_0_3px_rgba(124,58,237,0.08)]">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  required
                  className="block w-full px-4 py-3 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none"
                />
              </div>
            </div>

            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-zinc-700">비밀번호</label>
              <div className="overflow-hidden rounded-xl border border-zinc-300 bg-white transition-all focus-within:border-violet-400 focus-within:shadow-[0_0_0_3px_rgba(124,58,237,0.08)]">
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className="block w-full px-4 py-3 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isPending}
              className="flex w-full items-center justify-center rounded-xl bg-violet-600 px-4 py-3 text-[14px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-60"
            >
              {isPending ? '로그인 중...' : '로그인'}
            </button>
          </form>

          {/* 하단 링크 */}
          <p className="mt-6 text-center text-[13px] text-zinc-400">
            계정이 없으신가요?{' '}
            <Link to="/register" className="font-medium text-violet-600 hover:text-violet-700">
              회원가입
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
