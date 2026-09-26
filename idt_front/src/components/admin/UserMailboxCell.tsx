// mcp-identity-header Design §5.1 — 전체 사용자 표의 "메일함" 셀 (표시 + 인라인 편집).
// 빈 값 저장 = 해제. 형식 검증·정규화(소문자)는 백엔드 MailboxPolicy 가 담당한다.
import { useState } from 'react';
import LoadingButton from '@/components/common/LoadingButton';
import { useUpdateUserMailbox } from '@/hooks/useAdminUsers';
import { ApiError } from '@/services/api/ApiError';

interface UserMailboxCellProps {
  userId: number;
  mailboxUpn: string | null | undefined;
}

// authClient 인터셉터가 FastAPI detail 을 ApiError.message 로 옮겨 준다.
const serverMessage = (err: unknown): string =>
  err instanceof ApiError && err.message ? err.message : '메일함을 저장하지 못했습니다.';

const UserMailboxCell = ({ userId, mailboxUpn }: UserMailboxCellProps) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const update = useUpdateUserMailbox();

  const startEdit = () => {
    setDraft(mailboxUpn ?? '');
    setError(null);
    setEditing(true);
  };

  const save = () => {
    setError(null);
    const trimmed = draft.trim();
    update.mutate(
      { userId, mailboxUpn: trimmed ? trimmed : null },
      {
        onSuccess: () => setEditing(false),
        onError: (err) => setError(serverMessage(err)),
      },
    );
  };

  if (!editing) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-[13px] text-zinc-600">
          {mailboxUpn ? mailboxUpn : <span className="text-zinc-300">—</span>}
        </span>
        <button
          type="button"
          onClick={startEdit}
          className="rounded-md border border-zinc-200 px-2 py-0.5 text-[11.5px] font-medium text-zinc-500 hover:bg-zinc-50"
        >
          {mailboxUpn ? '편집' : '등록'}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5">
        <input
          type="email"
          aria-label="메일함 주소"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="name@corp.com"
          className="w-48 rounded-lg border border-zinc-300 px-2.5 py-1 text-[13px] outline-none focus:border-violet-400"
        />
        <LoadingButton
          isPending={update.isPending}
          onClick={save}
          className="rounded-lg bg-violet-600 px-2.5 py-1 text-[12px] font-medium text-white hover:bg-violet-700 disabled:opacity-50"
        >
          저장
        </LoadingButton>
        <button
          type="button"
          onClick={() => setEditing(false)}
          disabled={update.isPending}
          className="rounded-lg border border-zinc-200 px-2.5 py-1 text-[12px] text-zinc-500 disabled:opacity-50"
        >
          취소
        </button>
      </div>
      {error && <p className="text-[12px] text-red-600">{error}</p>}
    </div>
  );
};

export default UserMailboxCell;
