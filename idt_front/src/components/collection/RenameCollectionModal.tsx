import { useState } from 'react';

interface RenameCollectionModalProps {
  isOpen: boolean;
  currentName: string;
  onClose: () => void;
  onSubmit: (newName: string) => void;
  isPending: boolean;
  error: string | null;
}

const NAME_PATTERN = /^[a-zA-Z0-9_-]+$/;

const RenameCollectionModal = ({
  isOpen,
  currentName,
  onClose,
  onSubmit,
  isPending,
  error,
}: RenameCollectionModalProps) => {
  const [newName, setNewName] = useState('');
  const [nameError, setNameError] = useState('');

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) {
      setNameError('새 이름을 입력해주세요');
      return;
    }
    if (!NAME_PATTERN.test(newName)) {
      setNameError('영숫자, _, - 만 사용할 수 있습니다');
      return;
    }
    if (newName === currentName) {
      setNameError('현재 이름과 다른 이름을 입력해주세요');
      return;
    }
    setNameError('');
    onSubmit(newName);
  };

  const handleClose = () => {
    setNewName('');
    setNameError('');
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={handleClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-[15px] font-semibold text-zinc-900">
          컬렉션 이름 변경
        </h2>
        <p className="mt-1.5 text-[13px] text-zinc-500">
          &ldquo;{currentName}&rdquo; &rarr; 새 이름:
        </p>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div>
            <input
              type="text"
              value={newName}
              onChange={(e) => {
                setNewName(e.target.value);
                setNameError('');
              }}
              placeholder="new-collection-name"
              className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[15px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400"
              autoFocus
            />
            {nameError && (
              <p className="mt-1 text-[12px] text-red-500">{nameError}</p>
            )}
          </div>

          {error && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">
              {error}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={handleClose}
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
                <svg
                  className="h-4 w-4 animate-spin"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
              ) : (
                '변경'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default RenameCollectionModal;
