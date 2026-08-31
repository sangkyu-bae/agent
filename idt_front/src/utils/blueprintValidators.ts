// golden-sample-blueprint Design §5.3 — 저장 전 클라이언트 검증 (서버 VO 검증이 최종)
import { BLUEPRINT_LIMITS, type BlueprintDraft, type RelBox } from '@/types/blueprint';

const HEX = /^#[0-9A-Fa-f]{6}$/;

export const isValidBox = (b: RelBox): boolean =>
  [b.x, b.y, b.w, b.h].every((v) => Number.isFinite(v) && v >= 0 && v <= 1) &&
  b.w > 0 &&
  b.h > 0 &&
  b.x + b.w <= 1 + 1e-9 &&
  b.y + b.h <= 1 + 1e-9;

export const isHexColor = (v: string): boolean => HEX.test(v);

/** 빈 배열이면 유효. 위반 메시지를 모아 반환. */
export const validateBlueprintDraft = (draft: BlueprintDraft): string[] => {
  const errors: string[] = [];
  if (!draft.name.trim()) errors.push('이름을 입력하세요.');
  if (draft.name.length > BLUEPRINT_LIMITS.name_max)
    errors.push(`이름은 ${BLUEPRINT_LIMITS.name_max}자 이하여야 합니다.`);
  if (draft.description.length > BLUEPRINT_LIMITS.description_max)
    errors.push(`설명은 ${BLUEPRINT_LIMITS.description_max}자 이하여야 합니다.`);
  if (draft.patterns.length === 0) errors.push('페이지 패턴이 최소 1개 필요합니다.');

  const ids = draft.patterns.map((p) => p.id);
  if (new Set(ids).size !== ids.length) errors.push('패턴 id 가 중복되었습니다.');
  for (const p of draft.patterns) {
    if (p.slots.length === 0) errors.push(`패턴 ${p.id}: 슬롯이 비어 있습니다.`);
    const slotIds = p.slots.map((s) => s.id);
    if (new Set(slotIds).size !== slotIds.length) errors.push(`패턴 ${p.id}: 슬롯 id 중복`);
    for (const s of p.slots) {
      if (!isValidBox(s.box)) errors.push(`패턴 ${p.id} / 슬롯 ${s.id}: 좌표는 0..1 범위`);
    }
  }
  const known = new Set(ids);
  for (const sec of draft.narrative.sections) {
    const missing = sec.pattern_ids.filter((id) => !known.has(id));
    if (missing.length) errors.push(`서사 "${sec.role}": 없는 패턴 ${missing.join(', ')}`);
  }
  for (const [k, v] of Object.entries(draft.style.palette)) {
    if (!isHexColor(v)) errors.push(`팔레트 ${k}: #RRGGBB 형식이어야 합니다.`);
  }
  if (draft.assets.length > BLUEPRINT_LIMITS.max_assets)
    errors.push(`에셋은 ${BLUEPRINT_LIMITS.max_assets}개 이하여야 합니다.`);
  return errors;
};

/** 제외 토글된 패턴을 draft 에서 제거하고 서사 참조도 정리한다 (저장 직전 적용). */
export const excludePatterns = (draft: BlueprintDraft, excluded: string[]): BlueprintDraft => {
  if (excluded.length === 0) return draft;
  const gone = new Set(excluded);
  return {
    ...draft,
    patterns: draft.patterns.filter((p) => !gone.has(p.id)),
    narrative: {
      ...draft.narrative,
      sections: draft.narrative.sections.map((s) => ({
        ...s,
        pattern_ids: s.pattern_ids.filter((id) => !gone.has(id)),
      })),
    },
  };
};

export const isAcceptedSampleFile = (file: File): boolean =>
  /\.(pdf|pptx)$/i.test(file.name) && file.size <= BLUEPRINT_LIMITS.upload_max_bytes;
