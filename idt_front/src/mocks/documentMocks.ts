import type { Document, DocumentChunk, RetrievedChunk } from '@/types/rag';
import type { PaginatedResponse } from '@/types/api';

// ─── Mock Documents ─────────────────────────────────────
export const mockDocumentList: PaginatedResponse<Document> = {
  items: [
    {
      id: 'doc-1',
      name: 'RAG 시스템 설계 문서.pdf',
      size: 524288,
      mimeType: 'application/pdf',
      status: 'ready',
      chunkCount: 12,
      uploadedAt: '2026-03-15T09:00:00Z',
    },
    {
      id: 'doc-2',
      name: '백엔드 API 명세서 v2.docx',
      size: 102400,
      mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      status: 'ready',
      chunkCount: 7,
      uploadedAt: '2026-03-16T14:22:00Z',
    },
    {
      id: 'doc-3',
      name: '서비스 운영 가이드라인.txt',
      size: 35840,
      mimeType: 'text/plain',
      status: 'processing',
      chunkCount: undefined,
      uploadedAt: '2026-03-17T08:10:00Z',
    },
    {
      id: 'doc-4',
      name: '오류 리포트 2026-Q1.pdf',
      size: 204800,
      mimeType: 'application/pdf',
      status: 'error',
      chunkCount: undefined,
      uploadedAt: '2026-03-17T11:05:00Z',
      errorMessage: '지원하지 않는 파일 형식이거나 파일이 손상되었습니다.',
    },
  ],
  total: 4,
  page: 1,
  pageSize: 20,
  hasNext: false,
};

// ─── Mock Chunks ─────────────────────────────────────────
export const mockChunksByDocId: Record<string, DocumentChunk[]> = {
  'doc-1': [
    { id: 'c1-1', documentId: 'doc-1', chunkIndex: 0, tokenCount: 312,
      content: 'RAG(Retrieval-Augmented Generation) 시스템은 외부 지식 베이스를 활용하여 LLM의 응답 품질을 향상시키는 아키텍처입니다. 사용자의 질문을 벡터로 변환하고, 임베딩 데이터베이스에서 유사도 기반으로 관련 문서 청크를 검색합니다.' },
    { id: 'c1-2', documentId: 'doc-1', chunkIndex: 1, tokenCount: 289,
      content: '문서 청킹 전략에는 고정 크기 청킹, 의미 단위 청킹, 재귀적 청킹 등이 있습니다. 본 시스템은 512 토큰 단위의 재귀적 청킹을 채택하며, 문단 경계와 문장 구조를 최대한 보존합니다.' },
    { id: 'c1-3', documentId: 'doc-1', chunkIndex: 2, tokenCount: 341,
      content: '임베딩 모델로는 text-embedding-3-small을 사용하며, 1536차원의 벡터를 생성합니다. 벡터 스토어는 pgvector를 사용하고, 코사인 유사도 기반의 ANN(Approximate Nearest Neighbor) 검색을 수행합니다.' },
    { id: 'c1-4', documentId: 'doc-1', chunkIndex: 3, tokenCount: 276,
      content: '검색 결과의 재랭킹(Reranking) 단계에서는 Cross-Encoder 모델을 통해 초기 검색된 top-20 청크 중 최종 top-5를 선정합니다. 이 과정에서 질문과 청크 간의 관련성을 정밀하게 재평가합니다.' },
    { id: 'c1-5', documentId: 'doc-1', chunkIndex: 4, tokenCount: 298,
      content: 'LLM 컨텍스트 구성 시 검색된 청크와 함께 시스템 프롬프트, 대화 히스토리를 포함합니다. 컨텍스트 윈도우 초과 방지를 위해 총 8,000 토큰 제한을 적용합니다.' },
    { id: 'c1-6', documentId: 'doc-1', chunkIndex: 5, tokenCount: 255,
      content: '응답 생성 시 출처 추적(Source Tracking)을 위해 각 청크의 문서 ID, 청크 인덱스, 유사도 점수를 메타데이터로 함께 반환합니다. 이를 통해 UI에서 출처 표시가 가능합니다.' },
  ],
  'doc-2': [
    { id: 'c2-1', documentId: 'doc-2', chunkIndex: 0, tokenCount: 201,
      content: 'POST /api/chat/message — 새 메시지를 전송하고 AI 응답을 요청합니다. 요청 본문에 sessionId, content, useRag 파라미터를 포함합니다.' },
    { id: 'c2-2', documentId: 'doc-2', chunkIndex: 1, tokenCount: 188,
      content: 'GET /api/chat/sessions — 사용자의 채팅 세션 목록을 페이지네이션으로 반환합니다. page, pageSize 쿼리 파라미터를 지원하며 기본값은 page=1, pageSize=20입니다.' },
    { id: 'c2-3', documentId: 'doc-2', chunkIndex: 2, tokenCount: 224,
      content: 'POST /api/agent/run — AI Agent 실행을 시작합니다. input 텍스트와 선택적 tools 배열을 받아 runId를 반환합니다. 실행 상태는 SSE 또는 폴링으로 추적합니다.' },
    { id: 'c2-4', documentId: 'doc-2', chunkIndex: 3, tokenCount: 196,
      content: 'POST /api/rag/documents/upload — 문서 파일을 업로드합니다. multipart/form-data 형식으로 file 필드와 선택적 metadata JSON을 전송합니다.' },
  ],
};

export const getMockChunks = (docId: string): DocumentChunk[] =>
  mockChunksByDocId[docId] ?? [];

// ─── Mock Vector Search ───────────────────────────────────
// TODO: 서버 연동 시 ragService.retrieve() 호출로 교체

const mockDocumentNames: Record<string, string> = {
  'doc-1': 'RAG 시스템 설계 문서.pdf',
  'doc-2': '백엔드 API 명세서 v2.docx',
};

/**
 * 키워드 기반 유사도 시뮬레이션 (실제 벡터 검색 아님)
 * 쿼리 단어를 청크 내용에서 찾아 매칭 비율로 점수 계산
 */
const simulateScore = (content: string, query: string): number => {
  const keywords = query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
  if (keywords.length === 0) return Math.random() * 0.3 + 0.5;
  const lower = content.toLowerCase();
  const hits = keywords.filter((kw) => lower.includes(kw)).length;
  // 기본 점수 0.50 + 키워드 매칭 보정 + 랜덤 노이즈
  const base = 0.5 + (hits / keywords.length) * 0.45;
  const noise = (Math.random() - 0.5) * 0.06;
  return Math.min(0.99, Math.max(0.30, base + noise));
};

export const getMockVectorSearch = (query: string, topK: number): Promise<RetrievedChunk[]> => {
  // 500~900ms 지연으로 실제 서버 호출 시뮬레이션
  const delay = 500 + Math.random() * 400;

  return new Promise((resolve) => {
    setTimeout(() => {
      const allChunks: RetrievedChunk[] = Object.entries(mockChunksByDocId).flatMap(
        ([docId, chunks]) =>
          chunks.map((chunk) => ({
            documentId: docId,
            documentName: mockDocumentNames[docId] ?? docId,
            chunkIndex: chunk.chunkIndex,
            content: chunk.content,
            score: simulateScore(chunk.content, query),
          }))
      );

      const results = allChunks
        .sort((a, b) => b.score - a.score)
        .slice(0, topK);

      resolve(results);
    }, delay);
  });
};
