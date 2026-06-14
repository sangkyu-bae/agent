import { useEffect, useState } from 'react';
import { useDepartments } from '@/hooks/useDepartments';
import type { AdminCreateUserRequest, UserRole } from '@/types/auth';

interface UserRegisterModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (body: AdminCreateUserRequest) => void;
  isPending: boolean;
  error: string | null;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const UserRegisterModal = ({
  isOpen,
  onClose,
  onSubmit,
  isPending,
  error,
}: UserRegisterModalProps) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [position, setPosition] = useState('');
  const [employeeNo, setEmployeeNo] = useState('');
  const [joinedAt, setJoinedAt] = useState('');
  const [role, setRole] = useState<UserRole>('user');
  const [departmentId, setDepartmentId] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  const { data: deptData, isLoading: isDeptLoading } = useDepartments();
  const departments = deptData?.departments ?? [];

  // Esc 키로 닫기
  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError(null);

    if (!EMAIL_RE.test(email)) {
      setLocalError('올바른 이메일 형식이 아닙니다.');
      return;
    }
    if (password.length < 8) {
      setLocalError('비밀번호는 8자 이상이어야 합니다.');
      return;
    }
    if (!displayName.trim()) {
      setLocalError('이름을 입력하세요.');
      return;
    }

    const body: AdminCreateUserRequest = {
      email: email.trim(),
      password,
      display_name: displayName.trim(),
      role,
    };
    if (position.trim()) body.position = position.trim();
    if (employeeNo.trim()) body.employee_no = employeeNo.trim();
    if (joinedAt) body.joined_at = joinedAt;
    if (departmentId) body.department_id = departmentId;

    onSubmit(body);
  };

  const inputCls =
    'w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400 focus:ring-2 focus:ring-violet-100';
  const labelCls = 'mb-1.5 block text-[13px] font-medium text-zinc-700';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="사용자 등록"
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl"
      >
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-[15px] font-semibold text-zinc-900">사용자 등록</h2>
            <p className="mt-1 text-[12.5px] text-zinc-400">
              관리자가 직원 계정을 즉시 활성 상태로 생성합니다.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="-mr-1 -mt-1 flex h-8 w-8 items-center justify-center rounded-lg text-zinc-400 transition-all hover:bg-zinc-100 hover:text-zinc-600"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit} noValidate className="mt-4 space-y-4">
          <div>
            <label htmlFor="ur-email" className={labelCls}>
              이메일 <span className="text-red-400">*</span>
            </label>
            <input
              id="ur-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@example.com"
              className={inputCls}
              autoFocus
            />
          </div>

          <div>
            <label htmlFor="ur-password" className={labelCls}>
              비밀번호 <span className="text-red-400">*</span>
            </label>
            <input
              id="ur-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="8자 이상"
              className={inputCls}
            />
          </div>

          <div>
            <label htmlFor="ur-name" className={labelCls}>
              이름 <span className="text-red-400">*</span>
            </label>
            <input
              id="ur-name"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="배상규"
              maxLength={100}
              className={inputCls}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="ur-position" className={labelCls}>
                직급 <span className="text-zinc-400">(선택)</span>
              </label>
              <input
                id="ur-position"
                type="text"
                value={position}
                onChange={(e) => setPosition(e.target.value)}
                placeholder="대리"
                maxLength={50}
                className={inputCls}
              />
            </div>
            <div>
              <label htmlFor="ur-empno" className={labelCls}>
                사번 <span className="text-zinc-400">(선택)</span>
              </label>
              <input
                id="ur-empno"
                type="text"
                value={employeeNo}
                onChange={(e) => setEmployeeNo(e.target.value)}
                placeholder="E1001"
                maxLength={50}
                className={inputCls}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="ur-joined" className={labelCls}>
                입사일 <span className="text-zinc-400">(선택)</span>
              </label>
              <input
                id="ur-joined"
                type="date"
                value={joinedAt}
                onChange={(e) => setJoinedAt(e.target.value)}
                className={inputCls}
              />
            </div>
            <div>
              <label htmlFor="ur-role" className={labelCls}>
                권한 <span className="text-red-400">*</span>
              </label>
              <select
                id="ur-role"
                value={role}
                onChange={(e) => setRole(e.target.value as UserRole)}
                className={inputCls}
              >
                <option value="user">일반 사용자</option>
                <option value="admin">관리자</option>
              </select>
            </div>
          </div>

          <div>
            <label htmlFor="ur-dept" className={labelCls}>
              부서 <span className="text-zinc-400">(선택)</span>
            </label>
            <select
              id="ur-dept"
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value)}
              disabled={isDeptLoading}
              className={inputCls}
            >
              <option value="">부서 선택 안 함</option>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>

          {(localError || error) && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">
              {localError || error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="flex items-center justify-center rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
            >
              {isPending ? (
                <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                '등록'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default UserRegisterModal;
