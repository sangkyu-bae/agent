// doc-generator Design §5-1: 백엔드 application/agent_builder/schemas.py 와 1:1

export type GeneratorOutputFormat = 'pdf' | 'docx';

export interface DocumentSectionRequest {
  title: string;
  guidance: string;
}

// 에이전트 생성/수정 payload에 동봉되는 문서 유형 (백엔드 DocumentGenerationTypeRequest)
export interface DocumentGenerationTypeRequest {
  name: string;
  description: string;
  sections: DocumentSectionRequest[];
  output_format: GeneratorOutputFormat;
  mcp_html_to_doc_tool_id: string;
}

// GET detail 응답의 프리필 스냅샷 (백엔드 DocumentGenerationTypeInfo — FR-12)
export type DocumentGenerationTypeInfo = DocumentGenerationTypeRequest;

/** 빌더 폼이 보유하는 문서 유형 드래프트 (저장 시 request로 변환). */
export interface DocumentGeneratorDraft {
  name: string;
  description: string;
  sections: DocumentSectionRequest[];
  outputFormat: GeneratorOutputFormat;
  mcpHtmlToDocToolId: string;
}

// ToolCatalog 상 문서생성기 도구 id (내부 도구 prefix 규약)
export const DOCUMENT_GENERATOR_TOOL_ID = 'internal:document_generator';

// 백엔드 SectionPolicy 상한과 동일 (document_generator_max_sections 기본값)
export const MAX_SECTIONS = 20;

// FR-13: PDF 한글 폰트 이슈 안내 (doc-convert-pdf-korean-font-broken)
export const PDF_KOREAN_FONT_WARNING =
  '현재 PDF 변환은 한글 폰트가 깨질 수 있습니다. 해결 전까지 DOCX를 권장합니다.';

// D1·D3 안내: 소스 지정 UI 없음 — 검색 워커 구성이 곧 근거 소스
export const SOURCE_GUIDANCE_NOTICE =
  '검색 도구(웹 검색·내부 문서 검색)를 함께 선택하면 근거 조사 후 작성합니다. ' +
  '없으면 대화 내용만으로 작성됩니다.';

export const EMPTY_GENERATOR_DRAFT: DocumentGeneratorDraft = {
  name: '',
  description: '',
  sections: [],
  outputFormat: 'docx',
  mcpHtmlToDocToolId: '',
};
