import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  useCollectionDocuments,
  useDocumentChunks,
  useCollectionSearch,
} from '@/hooks/useCollections';
import DocumentTable from '@/components/collection/DocumentTable';
import ChunkDetailPanel from '@/components/collection/ChunkDetailPanel';
import UploadDocumentModal from '@/components/collection/UploadDocumentModal';
import HybridSearchPanel from '@/components/collection/HybridSearchPanel';
import SearchResultList from '@/components/collection/SearchResultList';
import SearchHistoryPanel from '@/components/collection/SearchHistoryPanel';
import type { CollectionSearchResponse } from '@/types/collection';

const DEFAULT_LIMIT = 20;

const EXAMPLE_QUERIES = ['임베딩 벡터 생성', '청킹 전략', 'API 엔드포인트', '리랭킹'];

const CollectionDocumentsPage = () => {
  const { collectionName } = useParams<{ collectionName: string }>();
  const navigate = useNavigate();
  const [offset, setOffset] = useState(0);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [includeParent, setIncludeParent] = useState(false);

  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);

  // Hybrid search local state
  const [searchQuery, setSearchQuery] = useState('');
  const [topK, setTopK] = useState<number>(5);
  const [bm25Weight, setBm25Weight] = useState(0.5);
  const [vectorWeight, setVectorWeight] = useState(0.5);
  const [searchResult, setSearchResult] = useState<CollectionSearchResponse | null>(null);

  const searchMutation = useCollectionSearch();

  const documentsQuery = useCollectionDocuments(collectionName ?? '', {
    offset,
    limit: DEFAULT_LIMIT,
  });

  const chunksQuery = useDocumentChunks(
    collectionName ?? '',
    selectedDocumentId,
    { include_parent: includeParent },
  );

  const documents = documentsQuery.data?.documents ?? [];
  const totalDocs = documentsQuery.data?.total_documents ?? 0;
  const readyCount = documents.filter((d) => d.chunk_count > 0).length;
  const processingCount = documents.filter((d) => d.chunk_count === 0).length;

  const handleSelectDocument = (docId: string) => {
    if (selectedDocumentId === docId) {
      setSelectedDocumentId(null);
    } else {
      setSelectedDocumentId(docId);
      setIncludeParent(false);
    }
  };

  const handleToggleHierarchy = (value: boolean) => {
    setIncludeParent(value);
  };

  const handleSearch = () => {
    if (!searchQuery.trim() || !collectionName) return;
    searchMutation.mutate(
      {
        collectionName,
        data: {
          query: searchQuery.trim(),
          top_k: topK,
          bm25_weight: bm25Weight,
          vector_weight: vectorWeight,
        },
      },
      {
        onSuccess: (data) => setSearchResult(data),
      },
    );
  };

  const handleHistoryApply = (params: {
    query: string;
    topK: number;
    bm25Weight: number;
    vectorWeight: number;
  }) => {
    setSearchQuery(params.query);
    setTopK(params.topK);
    setBm25Weight(params.bm25Weight);
    setVectorWeight(params.vectorWeight);
  };

  if (!collectionName) {
    navigate('/collections', { replace: true });
    return null;
  }

  return (
    <div className="h-full overflow-y-auto">
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      {/* Breadcrumb */}
      <nav className="mb-6 flex items-center gap-2 text-[13.5px]">
        <button
          onClick={() => navigate('/collections')}
          className="text-violet-600 transition-colors hover:underline"
        >
          컬렉션 관리
        </button>
        <span className="text-zinc-300">/</span>
        <span className="font-medium text-zinc-800">{collectionName}</span>
      </nav>

      {/* Page Header */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl shadow-md"
            style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
          >
            <svg className="h-6 w-6 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
            </svg>
          </div>
          <div>
            <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
              RAG
            </p>
            <h1 className="text-2xl font-bold tracking-tight text-zinc-900">
              문서 관리
            </h1>
          </div>
        </div>
        <button
          onClick={() => setIsUploadModalOpen(true)}
          className="flex items-center gap-2 rounded-xl bg-violet-600 px-5 py-2.5 text-[13.5px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
          </svg>
          문서 업로드
        </button>
      </div>

      {/* Status Summary Cards */}
      <div className="mb-6 grid grid-cols-4 gap-4">
        <div className="rounded-2xl border border-zinc-200 bg-white px-5 py-4">
          <p className="text-[12px] text-zinc-400">전체 문서</p>
          <p className="mt-1 text-2xl font-bold text-zinc-900">{totalDocs}</p>
        </div>
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50/50 px-5 py-4">
          <div className="flex items-center gap-1.5">
            <svg className="h-3.5 w-3.5 text-emerald-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
            <p className="text-[12px] text-emerald-600">준비 완료</p>
          </div>
          <p className="mt-1 text-2xl font-bold text-emerald-600">{readyCount}</p>
        </div>
        <div className="rounded-2xl border border-amber-200 bg-amber-50/50 px-5 py-4">
          <div className="flex items-center gap-1.5">
            <svg className="h-3.5 w-3.5 animate-spin text-amber-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182M2.985 19.644l3.182-3.182" />
            </svg>
            <p className="text-[12px] text-amber-600">처리 중</p>
          </div>
          <p className="mt-1 text-2xl font-bold text-amber-600">{processingCount}</p>
        </div>
        <div className="rounded-2xl border border-red-200 bg-red-50/50 px-5 py-4">
          <div className="flex items-center gap-1.5">
            <svg className="h-3.5 w-3.5 text-red-500" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
            </svg>
            <p className="text-[12px] text-red-500">오류</p>
          </div>
          <p className="mt-1 text-2xl font-bold text-red-500">0</p>
        </div>
      </div>

      {/* Document Table */}
      <DocumentTable
        documents={documents}
        totalDocuments={totalDocs}
        offset={offset}
        limit={DEFAULT_LIMIT}
        isLoading={documentsQuery.isLoading}
        isError={documentsQuery.isError}
        selectedDocumentId={selectedDocumentId}
        onSelect={handleSelectDocument}
        onPageChange={setOffset}
        onRetry={() => documentsQuery.refetch()}
      />

      {/* Chunk Detail Panel */}
      {selectedDocumentId && (chunksQuery.isLoading || chunksQuery.data) && (
        <ChunkDetailPanel
          data={chunksQuery.data ?? null}
          isLoading={chunksQuery.isLoading}
          showHierarchy={includeParent}
          onToggleHierarchy={handleToggleHierarchy}
          key={selectedDocumentId}
        />
      )}

      {/* Hybrid Search Section */}
      <div className="mt-8 rounded-2xl border border-zinc-200 bg-white p-6">
        <div className="mb-4 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-100">
            <svg className="h-5 w-5 text-violet-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
            </svg>
          </div>
          <div>
            <h3 className="text-[15px] font-semibold text-zinc-900">하이브리드 검색</h3>
            <p className="text-[12px] text-zinc-400">BM25 + 벡터 검색을 조합하여 최적의 검색 결과를 확인합니다</p>
          </div>
        </div>

        {/* Search Input + Button */}
        <div className="flex gap-3">
          <div className="flex-1 overflow-hidden rounded-2xl border border-zinc-300 bg-white shadow-sm transition-all focus-within:border-violet-400 focus-within:shadow-violet-100/60">
            <div className="flex items-center px-4">
              <svg className="h-4 w-4 shrink-0 text-zinc-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
              </svg>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="검색 쿼리를 입력하세요 (예: 임베딩 벡터 검색 방법)"
                className="block w-full bg-transparent px-3 py-3 text-[14px] text-zinc-900 placeholder-zinc-400 outline-none"
              />
            </div>
          </div>

          <button
            onClick={handleSearch}
            disabled={!searchQuery.trim() || searchMutation.isPending}
            className={`flex items-center gap-2 rounded-2xl px-5 text-[13.5px] font-medium shadow-sm transition-all active:scale-95 ${
              searchQuery.trim() && !searchMutation.isPending
                ? 'bg-violet-600 text-white hover:bg-violet-700'
                : 'cursor-not-allowed bg-zinc-200 text-zinc-400'
            }`}
          >
            {searchMutation.isPending ? (
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            ) : (
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
              </svg>
            )}
            검색
          </button>
        </div>

        {/* Example Queries */}
        <div className="mt-3 flex items-center gap-2">
          <span className="text-[12px] text-zinc-400">예시:</span>
          {EXAMPLE_QUERIES.map((q) => (
            <button
              key={q}
              onClick={() => setSearchQuery(q)}
              className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1 text-[12px] text-zinc-500 transition-all hover:border-zinc-300 hover:bg-zinc-100 hover:text-zinc-700"
            >
              {q}
            </button>
          ))}
        </div>

        {/* Search Options Panel */}
        <div className="mt-4">
          <HybridSearchPanel
            bm25Weight={bm25Weight}
            vectorWeight={vectorWeight}
            topK={topK}
            onBm25WeightChange={setBm25Weight}
            onVectorWeightChange={setVectorWeight}
            onTopKChange={setTopK}
          />
        </div>

        {/* Search Results */}
        {(searchResult || searchMutation.isPending || searchMutation.isError) && (
          <SearchResultList
            results={searchResult?.results}
            isLoading={searchMutation.isPending}
            isError={searchMutation.isError}
            totalFound={searchResult?.total_found ?? 0}
            bm25Weight={searchResult?.bm25_weight ?? bm25Weight}
            vectorWeight={searchResult?.vector_weight ?? vectorWeight}
          />
        )}

        {/* Search History */}
        <SearchHistoryPanel
          collectionName={collectionName}
          onApply={handleHistoryApply}
        />
      </div>

      <UploadDocumentModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        collectionName={collectionName}
      />
    </div>
    </div>
  );
};

export default CollectionDocumentsPage;
