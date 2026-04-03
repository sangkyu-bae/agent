export interface EvalDatasetItem {
  id: number;
  question: string;
  answer: string;
}

export interface EvalDatasetResponse {
  documentName: string;
  totalCount: number;
  items: EvalDatasetItem[];
}

export interface EvalExtractRequest {
  file: File;
}
