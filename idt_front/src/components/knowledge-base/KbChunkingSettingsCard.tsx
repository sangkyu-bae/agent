/**
 * KB 청킹 설정 카드 + 수정 모달 (kb-custom-chunking Design §6.2)
 *
 * 현재 설정 요약을 표시하고, 수정 모달에서 PATCH /chunking으로 전체 교체한다.
 * 변경은 신규 업로드부터 적용 — 안내 문구 고정 노출 (D10).
 */
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import Modal from '@/components/common/Modal';
import { useActiveChunkingProfiles } from '@/hooks/useChunkingProfiles';
import { useUpdateKbChunking } from '@/hooks/useKnowledgeBases';
import { queryKeys } from '@/lib/queryKeys';
import { ApiError } from '@/services/api/ApiError';
import type { ChunkingProfile } from '@/types/chunkingProfile';
import type { KnowledgeBaseInfo } from '@/types/ragToolConfig';
import type { UpdateKbChunkingRequest } from '@/types/knowledgeBase';
import ChunkingModeSelector, {
  type ChunkingMode,
} from './ChunkingModeSelector';
import {
  STRATEGY_OPTIONS,
  buildCustomChunkingConfig,
  formFromConfig,
  validateCustomChunkingForm,
} from './customChunkingForm';
import {
  clauseProfileSummary,
  resolveProfileSelection,
} from './kbProfileSelection';

interface KbChunkingSettingsCardProps {
  kb: KnowledgeBaseInfo;
}

const modeOf = (kb: KnowledgeBaseInfo): ChunkingMode => {
  if (kb.use_custom_chunking) return 'custom';
  if (kb.use_clause_chunking) return 'clause';
  return 'default';
};

const summaryOf = (
  kb: KnowledgeBaseInfo,
  profiles: ChunkingProfile[] | undefined,
): string => {
  if (kb.use_custom_chunking && kb.custom_chunking_config) {
    const config = kb.custom_chunking_config;
    const label =
      STRATEGY_OPTIONS.find((o) => o.value === config.strategy)?.label ??
      config.strategy;
    const parts = [
      `커스텀 — ${label}`,
      `크기 ${config.chunk_size}`,
      `오버랩 ${config.chunk_overlap}`,
    ];
    if (config.boundary_rules?.length) {
      parts.push(`규칙 ${config.boundary_rules.length}개`);
    }
    return parts.join(' · ');
  }
  if (kb.use_clause_chunking) {
    return clauseProfileSummary(
      resolveProfileSelection(kb.chunking_profile_id ?? null, profiles),
    );
  }
  return '기본 청킹 (Parent-Child 2000/500/50)';
};

const KbChunkingSettingsCard = ({ kb }: KbChunkingSettingsCardProps) => {
  const [editOpen, setEditOpen] = useState(false);
  const [mode, setMode] = useState<ChunkingMode>(() => modeOf(kb));
  const [customForm, setCustomForm] = useState(() =>
    formFromConfig(kb.custom_chunking_config),
  );
  const [profileId, setProfileId] = useState<string | null>(
    kb.chunking_profile_id ?? null,
  );
  const [formError, setFormError] = useState('');

  const queryClient = useQueryClient();
  const mutation = useUpdateKbChunking(kb.kb_id);
  const profilesQuery = useActiveChunkingProfiles({
    enabled: modeOf(kb) === 'clause' || (editOpen && mode === 'clause'),
  });
  // 조회 성공 시에만 목록을 넘겨 실패를 삭제로 오판하지 않는다 (FR-09)
  const profiles = profilesQuery.isSuccess ? profilesQuery.data : undefined;

  const openEdit = () => {
    setMode(modeOf(kb));
    setCustomForm(formFromConfig(kb.custom_chunking_config));
    setProfileId(kb.chunking_profile_id ?? null);
    setFormError('');
    mutation.reset();
    setEditOpen(true);
  };

  const handleSave = () => {
    if (mode === 'custom') {
      const error = validateCustomChunkingForm(customForm);
      if (error) {
        setFormError(error);
        return;
      }
    }
    setFormError('');
    const body: UpdateKbChunkingRequest = {
      use_clause_chunking: mode === 'clause',
      chunking_profile_id:
        mode === 'clause'
          ? resolveProfileSelection(profileId, profiles).effectiveId
          : null,
      // 조항 유지 시 기존 오버라이드 보존, 그 외 초기화 (§6.2)
      chunk_size: mode === 'clause' ? (kb.chunk_size ?? null) : null,
      chunk_overlap: mode === 'clause' ? (kb.chunk_overlap ?? null) : null,
      use_custom_chunking: mode === 'custom',
      custom_chunking_config:
        mode === 'custom' ? buildCustomChunkingConfig(customForm) : null,
    };
    mutation.mutate(body, {
      onSuccess: () => setEditOpen(false),
      // 모달을 연 사이 프로파일이 삭제된 경우 목록을 다시 맞춘다 (Design §6.1)
      onError: (err) => {
        if (err instanceof ApiError && err.status === 404) {
          queryClient.invalidateQueries({
            queryKey: queryKeys.chunkingProfiles.all,
          });
        }
      },
    });
  };

  // authClient 인터셉터가 detail을 ApiError.message로 변환한다
  const serverError = mutation.isError
    ? mutation.error instanceof Error
      ? mutation.error.message
      : '청킹 설정 변경에 실패했습니다'
    : '';

  return (
    <div className="mt-4 flex items-center justify-between rounded-xl border border-zinc-200 bg-white px-4 py-3">
      <div>
        <p className="text-[12px] font-medium text-zinc-500">청킹 설정</p>
        <p className="mt-0.5 text-[13.5px] text-zinc-800">
          {summaryOf(kb, profiles)}
        </p>
      </div>
      <button
        onClick={openEdit}
        className="rounded-lg border border-zinc-200 px-3 py-1.5 text-[12.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-50"
      >
        설정 변경
      </button>

      {editOpen && (
        <Modal
          onClose={() => setEditOpen(false)}
          title="청킹 설정 변경"
          size="md"
          showCloseButton={false}
        >
          <div className="space-y-4">
            <ChunkingModeSelector
              mode={mode}
              onModeChange={setMode}
              customForm={customForm}
              onCustomFormChange={setCustomForm}
              profileId={profileId}
              onProfileChange={setProfileId}
              kbChunkSize={kb.chunk_size}
              kbChunkOverlap={kb.chunk_overlap}
            />

            <p className="rounded-lg bg-amber-50 px-3 py-2 text-[12.5px] text-amber-700">
              변경된 설정은 이후 업로드하는 문서부터 적용되며, 기존 문서는
              다시 청킹되지 않습니다.
            </p>

            {(formError || serverError) && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-[13px] text-red-600">
                {formError || serverError}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setEditOpen(false)}
                className="rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-2.5 text-[13.5px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
              >
                취소
              </button>
              <button
                type="button"
                onClick={handleSave}
                disabled={mutation.isPending}
                className="rounded-xl bg-violet-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95 disabled:opacity-50"
              >
                {mutation.isPending ? '저장 중...' : '저장'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

export default KbChunkingSettingsCard;
