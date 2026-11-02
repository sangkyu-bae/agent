export interface LlmModel {
  id: string;
  provider: string;
  model_name: string;
  display_name: string;
  description: string | null;
  max_tokens: number | null;
  is_active: boolean;
  is_default: boolean;
  // LLM-MODEL-REG-002: self-host 엔드포인트(vLLM 등). null이면 provider 기본값.
  base_url?: string | null;
  // AGENT-OBS M4: 토큰 1,000개당 USD 단가 — 백엔드 Decimal이 JSON 문자열로 직렬화됨 ("0.0025")
  input_price_per_1k_usd?: string | null;
  output_price_per_1k_usd?: string | null;
  pricing_updated_at?: string | null;
  // multimodal-extractor: 비전(이미지 입력) 지원 여부 — additive, 구버전 응답은 undefined
  supports_vision?: boolean;
  // image-generation-tool Design §4.2 (V081): 종류(chat|image) — additive, 부재는 chat 으로 간주
  model_kind?: LlmModelKind;
  // image-generation-tool: 장당 단가 USD — 백엔드 Decimal 이 JSON 문자열 ("0.0400"), 미설정 null
  price_per_image_usd?: string | null;
}

export interface LlmModelListResponse {
  models: LlmModel[];
}

/** 모델 종류 — chat: 대화/비전 후보, image: 이미지 생성 도구 전용 (Design D-05) */
export const LLM_MODEL_KIND = {
  CHAT: 'chat',
  IMAGE: 'image',
} as const;
export type LlmModelKind = (typeof LLM_MODEL_KIND)[keyof typeof LLM_MODEL_KIND];

/** POST /api/v1/llm-models — api_key_env는 등록 시에만 전달(write-only, 응답 미노출) */
export interface CreateLlmModelRequest {
  provider: string;
  model_name: string;
  display_name: string;
  description?: string | null;
  api_key_env: string;
  max_tokens?: number | null;
  is_active?: boolean;
  is_default?: boolean;
  base_url?: string | null;
  supports_vision?: boolean;
  // image-generation-tool: 종류(기본 chat)·장당 단가(전송은 number, 수신은 string)
  model_kind?: LlmModelKind;
  price_per_image_usd?: number | null;
}

/** PATCH /api/v1/llm-models/{id} — provider/model_name/api_key_env는 수정 불가(식별자 성격) */
export interface UpdateLlmModelRequest {
  display_name?: string;
  description?: string | null;
  max_tokens?: number | null;
  is_active?: boolean;
  is_default?: boolean;
  base_url?: string | null;
  supports_vision?: boolean;
  // image-generation-tool: undefined = 변경 안 함
  model_kind?: LlmModelKind;
  price_per_image_usd?: number | null;
}

/** PATCH /api/v1/llm-models/{id}/pricing — 전송은 number(≥0), 수신은 string */
export interface UpdateLlmModelPricingRequest {
  input_price_per_1k_usd: number;
  output_price_per_1k_usd: number;
  // image-generation-tool: 생략하면 기존 값 유지
  price_per_image_usd?: number;
}

/** 등록 폼 provider 셀렉트 옵션 */
export const LLM_PROVIDER = {
  OPENAI: 'openai',
  ANTHROPIC: 'anthropic',
  OLLAMA: 'ollama',
  PERPLEXITY: 'perplexity',
} as const;
export type LlmProvider = (typeof LLM_PROVIDER)[keyof typeof LLM_PROVIDER];
