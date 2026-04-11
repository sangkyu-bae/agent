import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useRegister } from '@/hooks/useAuth';
import { useAuthStore } from '@/store/authStore';

const RegisterPage = () => {
  const { isAuthenticated } = useAuthStore();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [formError, setFormError] = useState('');
  const [isSuccess, setIsSuccess] = useState(false);
  const { mutate: register, isPending } = useRegister();

  if (isAuthenticated) return <Navigate to="/" replace />;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setFormError('');
    register(
      { email, password },
      {
        onSuccess: () => setIsSuccess(true),
        onError: (error) => {
          const msg = error.message;
          if (msg.includes('already registered') || msg.includes('Email already')) {
            setFormError('이미 가입된 이메일입니다.');
          } else if (msg.includes('at least 8')) {
            setFormError('비밀번호는 8자 이상이어야 합니다.');
          } else {
            setFormError('회원가입 중 오류가 발생했습니다.');
          }
        },
      }
    );
  };

  if (isSuccess) {
    return (
      <div className="flex min-h-full items-center justify-center bg-white px-4">
        <div className="w-full max-w-md">
          <div className="rounded-2xl border border-zinc-200 bg-white p-8 shadow-sm text-center">
            <div
              className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full"
              style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
            >
              <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <h2 className="text-xl font-bold text-zinc-900">가입 신청이 완료되었습니다</h2>
            <p className="mt-2 text-[13px] text-zinc-500">
              관리자가 계정을 승인하면 로그인할 수 있습니다.
            </p>
            <Link
              to="/login"
              className="mt-6 inline-flex items-center justify-center rounded-xl bg-violet-600 px-6 py-2.5 text-[14px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
            >
              로그인 페이지로 이동
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-white px-4">
      <div className="w-full max-w-md">
        <div className="rounded-2xl border border-zinc-200 bg-white p-8 shadow-sm">
          <div className="mb-8 text-center">
            <div
              className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl shadow-md"
              style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
            >
              <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-zinc-900">회원가입</h1>
            <p className="mt-1 text-[13px] text-zinc-400">가입 후 관리자 승인이 필요합니다</p>
          </div>

          {formError && (
            <div className="mb-4 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-[13px] text-red-600">
              {formError}
            </div>
          )}

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
                  placeholder="8자 이상"
                  required
                  minLength={8}
                  className="block w-full px-4 py-3 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isPending}
              className="flex w-full items-center justify-center rounded-xl bg-violet-600 px-4 py-3 text-[14px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-60"
            >
              {isPending ? '가입 중...' : '회원가입'}
            </button>
          </form>

          <p className="mt-6 text-center text-[13px] text-zinc-400">
            이미 계정이 있으신가요?{' '}
            <Link to="/login" className="font-medium text-violet-600 hover:text-violet-700">
              로그인
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default RegisterPage;
