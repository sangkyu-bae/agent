export interface EmbeddingModel {
  id: number;
  provider: string;
  model_name: string;
  display_name: string;
  vector_dimension: number;
  description: string;
}

export interface EmbeddingModelListResponse {
  models: EmbeddingModel[];
  total: number;
}
