import { useState } from 'react';
import Modal from '@/components/common/Modal';
import Dropdown from '@/components/common/Dropdown';
import { SCOPE_LABELS } from '@/types/collection';
import type { CollectionScope } from '@/types/ragToolConfig';
import type { CreateKnowledgeBaseRequest } from '@/types/knowledgeBase';
import { useCollectionList } from '@/hooks/useCollections';
import { useDepartments } from '@/hooks/useDepartments';
import { useActiveChunkingProfiles } from '@/hooks/useChunkingProfiles';
import ChunkingModeSelector, {
  type ChunkingMode,
} from './ChunkingModeSelector';
import {
  buildCustomChunkingConfig,
  defaultCustomChunkingForm,
  validateCustomChunkingForm,
} from './customChunkingForm';
import { resolveProfileSelection } from './kbProfileSelection';

interface CreateKnowledgeBaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateKnowledgeBaseRequest) => void;
  isPending: boolean;
  error: string | null;
}

const KB_SCOPES: CollectionScope[] = ['PERSONAL', 'DEPARTMENT', 'PUBLIC'];

const CreateKnowledgeBaseModal = ({
  isOpen,
  onClose,
  onSubmit,
  isPending,
  error,
}: CreateKnowledgeBaseModalProps) => {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [scope, setScope] = useState<CollectionScope>('PERSONAL');
  const [departmentId, setDepartmentId] = useState('');
  const [collectionName, setCollectionName] = useState('');
  // kb-custom-chunking §6.1: radio 3택으로 조항/커스텀 상호배타 원천 차단
  const [chunkingMode, setChunkingMode] = useState<ChunkingMode>('default');
  const [customForm, setCustomForm] = useState(defaultCustomChunkingForm);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [formError, setFormError] = useState('');
  const [wasOpen, setWasOpen] = useState(isOpen);

  const resetForm = () => {
    setName('');
    setDescription('');
    setScope('PERSONAL');
    setDepartmentId('');
    setCollectionName('');
    setChunkingMode('default');
    setCustomForm(defaultCustomChunkingForm());
    setProfileId(null);
    setAdvancedOpen(false);
    setFormError('');
  };

  // 부모가 생성 성공 후 isOpen만 내리는 경로도 다시 열 때 초기화한다 (Check G2)
  if (wasOpen !== isOpen) {
    setWasOpen(isOpen);
    if (isOpen) resetForm();
  }

  const { data: collectionData, isLoading: isCollectionsLoading } =
    useCollectionList();
  const { data: deptData, isLoading: isDeptLoading } = useDepartments();
  const profilesQuery = useActiveChunkingProfiles({
    enabled: isOpen && chunkingMode === 'clause',
  });

  if (!isOpen) return null;

  const collections = collectionData?.collections ?? [];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setFormError('지식베이스 이름을 입력해주세요');
      return;
    }
    if (name.trim().length > 100) {
      setFormError('이름은 100자 이내여야 합니다');
      return;
    }
    if (!collectionName) {
      setFormError('대상 컬렉션을 선택해주세요');
      return;
    }
    if (scope === 'DEPARTMENT' && !departmentId) {
      setFormError('부서를 선택해주세요');
      return;
    }
    if (chunkingMode === 'custom') {
      const chunkingError = validateCustomChunkingForm(customForm);
      if (chunkingError) {
        setFormError(chunkingError);
        return;
      }
    }
    setFormError('');
    onSubmit({
      name: name.trim(),
      description: description.trim() || undefined,
      scope,
      department_id: scope === 'DEPARTMENT' ? departmentId : undefined,
      collection_name: collectionName,
      use_clause_chunking: chunkingMode === 'clause',
      // 비조항 모드에 프로파일을 보내면 백엔드가 422로 거부한다
      chunking_profile_id:
        chunkingMode === 'clause'
          ? resolveProfileSelection(
              profileId,
              profilesQuery.isSuccess ? profilesQuery.data : undefined,
            ).effectiveId
          : undefined,
      use_custom_chunking: chunkingMode === 'custom',
      custom_chunking_config:
        chunkingMode === 'custom'
          ? buildCustomChunkingConfig(customForm)
          : undefined,
    });
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  return (
    <Modal
      onClose={handleClose}
      title="새 지식베이스"
      size="md"
      scroll="content"
      showCloseButton={false}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
            이름
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setFormError('');
            }}
            placeholder="여신 규정집"
            className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[15px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
            설명 (선택)
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="이 지식베이스에 어떤 문서를 모으는지 적어주세요"
            className="w-full rounded-xl border border-zinc-300 px-4 py-2.5 text-[15px] text-zinc-900 placeholder-zinc-400 outline-none transition-all focus:border-violet-400"
          />
        </div>

        <div>
          <label
            htmlFor="kb-collection-select"
            className="mb-1.5 block text-[12px] font-medium text-zinc-500"
          >
            대상 컬렉션
          </label>
          {isCollectionsLoading ? (
            <p className="text-[13px] text-zinc-400">
              컬렉션 목록을 불러오는 중...
            </p>
          ) : collections.length === 0 ? (
            <p className="text-[13px] text-amber-600">
              사용 가능한 컬렉션이 없습니다. 관리자에게 컬렉션 생성을
              요청해주세요.
            </p>
          ) : (
            <Dropdown
              id="kb-collection-select"
              ariaLabel="대상 컬렉션"
              value={collectionName}
              onChange={setCollectionName}
              placeholder="컬렉션을 선택하세요"
              options={collections.map((c) => ({
                value: c.name,
                label: c.name,
              }))}
              className="w-full"
            />
          )}
        </div>

        <div>
          <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
            공개 범위
          </label>
          <div className="space-y-2">
            {KB_SCOPES.map((s) => (
              <label
                key={s}
                className="flex cursor-pointer items-center gap-2.5"
              >
                <input
                  type="radio"
                  name="kb-scope"
                  value={s}
                  checked={scope === s}
                  onChange={() => setScope(s)}
                  className="h-4 w-4 accent-violet-600"
                />
                <span
                  className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11.5px] font-semibold ${SCOPE_LABELS[s].bg} ${SCOPE_LABELS[s].color}`}
                >
                  {SCOPE_LABELS[s].label}
                </span>
                <span className="text-[12px] text-zinc-400">
                  {s === 'PERSONAL' && '나만 접근 가능'}
                  {s === 'DEPARTMENT' && '소속 부서원 접근'}
                  {s === 'PUBLIC' && '전체 접근 가능'}
                </span>
              </label>
            ))}
          </div>
          {scope === 'DEPARTMENT' && (
            <div className="mt-3">
              <label className="mb-1.5 block text-[12px] font-medium text-zinc-500">
                부서 선택
              </label>
              {isDeptLoading ? (
                <p className="text-[13px] text-zinc-400">
                  부서 목록을 불러오는 중...
                </p>
              ) : !deptData?.departments.length ? (
                <p className="text-[13px] text-amber-600">
                  등록된 부서가 없습니다.
                </p>
              ) : (
                <Dropdown
                  ariaLabel="부서 선택"
                  value={departmentId}
                  onChange={setDepartmentId}
                  placeholder="부서를 선택하세요"
                  options={deptData.departments.map((dept) => ({
                    value: dept.id,
                    label: dept.name,
                  }))}
                  className="w-full"
                />
              )}
            </div>
          )}
        </div>

        {/* 고급 옵션 — 청킹 방식 radio 3택 (kb-custom-chunking §6.1) */}
        <div>
          <button
            type="button"
            onClick={() => setAdvancedOpen((v) => !v)}
            className="text-[12.5px] font-medium text-zinc-500 hover:text-zinc-700"
          >
            {advancedOpen ? '▾' : '▸'} 고급 옵션
          </button>
          {advancedOpen && (
            <div className="mt-2">
              <ChunkingModeSelector
                mode={chunkingMode}
                onModeChange={setChunkingMode}
                customForm={customForm}
                onCustomFormChange={setCustomForm}
                profileId={profileId}
                onProfileChange={setProfileId}
              />
            </div>
          )}
        </div>

        {(formError || error) && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">
            {formError || error}
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
            {isPending ? '생성 중...' : '생성'}
          </button>
        </div>
      </form>
    </Modal>
  );
};

export default CreateKnowledgeBaseModal;
