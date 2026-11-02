// image-generation-tool Design §4.2 / D-05 — model_kind 필터 (순수 함수).
// 채팅·비전 드롭다운은 chat 만, 이미지 생성 설정은 활성 image 만 노출한다.
// 구버전 응답(model_kind 부재)은 chat 으로 간주한다 (additive 계약).
import { LLM_MODEL_KIND, type LlmModel } from '@/types/llmModel';

type KindAware = Pick<LlmModel, 'model_kind'>;

export const isChatModel = (m: KindAware): boolean =>
  (m.model_kind ?? LLM_MODEL_KIND.CHAT) === LLM_MODEL_KIND.CHAT;

export const isImageModel = (m: KindAware): boolean => m.model_kind === LLM_MODEL_KIND.IMAGE;

export const filterChatModels = <T extends KindAware>(models: T[] | undefined): T[] =>
  (models ?? []).filter(isChatModel);

export const filterActiveImageModels = <T extends KindAware & Pick<LlmModel, 'is_active'>>(
  models: T[] | undefined,
): T[] => (models ?? []).filter((m) => isImageModel(m) && m.is_active);
