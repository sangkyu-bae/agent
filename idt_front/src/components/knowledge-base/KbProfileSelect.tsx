/**
 * 조항 모드 청킹 프로파일 선택 (kb-profile-selector Design §5.4)
 *
 * 조항 모드에서만 마운트되어 이때만 목록을 조회한다.
 * 선택값은 저장 body를 만드는 부모 모달이 소유한다.
 */
import { useId } from 'react';
import Dropdown, { type DropdownOption } from '@/components/common/Dropdown';
import Button from '@/components/ui/Button';
import { useActiveChunkingProfiles } from '@/hooks/useChunkingProfiles';
import type { ChunkingProfile } from '@/types/chunkingProfile';
import {
  effectiveProfileSizes,
  resolveProfileSelection,
} from './kbProfileSelection';

interface KbProfileSelectProps {
  selectedId: string | null;
  onChange: (profileId: string | null) => void;
  kbChunkSize?: number | null;
  kbChunkOverlap?: number | null;
}

const DEFAULT_PROFILE_VALUE = '';

const NOTICE_CLASS =
  'rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-xs text-warning';

const buildOptions = (
  profiles: ChunkingProfile[],
  defaultProfile: ChunkingProfile | null,
): DropdownOption[] => [
  {
    value: DEFAULT_PROFILE_VALUE,
    label: defaultProfile
      ? `기본 프로파일 따름 (${defaultProfile.name})`
      : '기본 프로파일 따름',
  },
  ...profiles.map((profile) => ({
    value: profile.profile_id,
    label: profile.name,
    badge: profile.is_default ? '기본' : undefined,
  })),
];

const KbProfileSelect = ({
  selectedId,
  onChange,
  kbChunkSize,
  kbChunkOverlap,
}: KbProfileSelectProps) => {
  const selectId = useId();
  const query = useActiveChunkingProfiles();

  if (query.isError) {
    return (
      <div className={`flex items-center justify-between gap-3 ${NOTICE_CLASS}`}>
        <p>
          프로파일 목록을 불러오지 못했습니다. 저장해도 현재 지정은 유지됩니다.
        </p>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          isPending={query.isFetching}
          onClick={() => query.refetch()}
        >
          다시 시도
        </Button>
      </div>
    );
  }

  const profiles = query.isSuccess ? query.data : undefined;
  const selection = resolveProfileSelection(selectedId, profiles);
  const { appliedProfile } = selection;
  const sizes =
    appliedProfile &&
    effectiveProfileSizes(appliedProfile, kbChunkSize, kbChunkOverlap);

  return (
    <div className="space-y-2">
      <label
        htmlFor={selectId}
        className="block text-xs font-medium text-fg-subtle"
      >
        청킹 프로파일
      </label>
      <Dropdown
        id={selectId}
        ariaLabel="청킹 프로파일"
        value={selection.effectiveId ?? DEFAULT_PROFILE_VALUE}
        onChange={(value) => onChange(value || null)}
        options={buildOptions(profiles ?? [], selection.defaultProfile)}
        isLoading={query.isPending}
        className="w-full"
      />

      {selection.isStale && (
        <p className={NOTICE_CLASS}>
          지정한 프로파일이 삭제되어 기본 프로파일로 처리됩니다. 저장하면 기본
          프로파일 따름으로 변경됩니다.
        </p>
      )}
      {selection.usesLegacyFallback && (
        <p className={NOTICE_CLASS}>
          적용할 기본 프로파일이 없어 업로드가 기본 청킹으로 처리됩니다.
        </p>
      )}

      {appliedProfile && sizes && (
        <div className="space-y-0.5 rounded-md bg-surface-muted px-3 py-2 text-xs text-fg-muted">
          {appliedProfile.description && <p>{appliedProfile.description}</p>}
          <p>
            부모 {sizes.parentChunkSize} · 청크 {sizes.chunkSize} · 오버랩{' '}
            {sizes.chunkOverlap}
          </p>
          <p>
            경계 규칙 {appliedProfile.boundary_rules.length}개 · 섹션 요약{' '}
            {appliedProfile.summary_llm_model_id ? '사용' : '미사용'}
          </p>
        </div>
      )}
    </div>
  );
};

export default KbProfileSelect;
