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
}

export interface LlmModelListResponse {
  models: LlmModel[];
}
