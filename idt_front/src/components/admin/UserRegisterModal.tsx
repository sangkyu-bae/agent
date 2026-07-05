import { useState } from 'react';
import { useDepartments } from '@/hooks/useDepartments';
import Dropdown from '@/components/common/Dropdown';
import Modal from '@/components/common/Modal';
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
    <Modal
      onClose={onClose}
      title="사용자 등록"
      subtitle="관리자가 직원 계정을 즉시 활성 상태로 생성합니다."
      size="lg"
      scroll="content"
      closeOnBackdrop={false}
    >
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
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
              <Dropdown
                id="ur-role"
                value={role}
                onChange={(v) => setRole(v as UserRole)}
                options={[
                  { value: 'user', label: '일반 사용자' },
                  { value: 'admin', label: '관리자' },
                ]}
                className="w-full"
              />
            </div>
          </div>

          <div>
            <label htmlFor="ur-dept" className={labelCls}>
              부서 <span className="text-zinc-400">(선택)</span>
            </label>
            <Dropdown
              id="ur-dept"
              value={departmentId}
              onChange={setDepartmentId}
              disabled={isDeptLoading}
              options={[
                { value: '', label: '부서 선택 안 함' },
                ...departments.map((d) => ({ value: d.id, label: d.name })),
              ]}
              className="w-full"
            />
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
    </Modal>
  );
};

export default UserRegisterModal;
