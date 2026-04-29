import { useState, useRef, useCallback } from 'react';
import type { EvalDatasetItem } from '@/types/eval';

const ACCEPTED_EXTENSIONS = ['.pdf', '.doc', '.docx'];

const MOCK_ITEMS: EvalDatasetItem[] = [
  {
    id: 1,
    question: 'RAG(Retrieval-Augmented Generation) 시스템에서 청킹 전략이 검색 품질에 어떤 영향을 미치나요?',
    answer:
      '청킹 전략은 RAG 시스템의 검색 품질에 직접적인 영향을 미칩니다. 고정 크기 청킹은 구현이 간단하지만 문맥이 단절될 수 있고, 의미 기반 청킹은 문단/섹션 경계에서 분할하여 문맥 보존에 유리합니다. 일반적으로 256–512 토큰 크기와 10–20% 오버랩이 권장됩니다.',
  },
  {
    id: 2,
    question: '벡터 데이터베이스에서 코사인 유사도와 유클리드 거리의 차이점은 무엇인가요?',
    answer:
      '코사인 유사도는 벡터의 방향(각도)을 비교하여 크기와 무관한 의미적 유사성을 측정합니다. 유클리드 거리는 공간에서의 절대 거리를 측정합니다. 텍스트 임베딩 검색에는 코사인 유사도가 더 적합하며, 방향이 같으면 크기가 달라도 유사하게 판단합니다.',
  },
  {
    id: 3,
    question: 'LLM의 환각(Hallucination) 현상을 줄이기 위한 RAG의 역할은 무엇인가요?',
    answer:
      'RAG는 외부 문서에서 검색한 실제 정보를 컨텍스트로 제공하여 LLM이 사실에 기반한 답변을 생성하도록 유도합니다. 이를 통해 LLM이 학습 데이터에 없는 최신 정보나 도메인 특화 지식을 환각 없이 활용할 수 있습니다.',
  },
  {
    id: 4,
    question: 'Sparse 검색(BM25)과 Dense 검색(임베딩)을 결합한 하이브리드 검색의 장점은?',
    answer:
      'BM25는 정확한 키워드 매칭에 강하고, 임베딩 기반 검색은 의미적 유사성 파악에 강합니다. 하이브리드 검색은 두 방법의 결과를 RRF(Reciprocal Rank Fusion) 등으로 결합하여 키워드 검색과 의미 검색의 장점을 모두 활용할 수 있습니다.',
  },
  {
    id: 5,
    question: '문서 임베딩 모델 선택 시 고려해야 할 주요 요소는 무엇인가요?',
    answer:
      '주요 고려 요소로는 ① 다국어 지원 여부(한국어 성능), ② 최대 입력 토큰 길이, ③ 임베딩 벡터 차원 수, ④ MTEB 벤치마크 성능, ⑤ 추론 속도와 비용, ⑥ 오픈소스 여부가 있습니다. 한국어 문서에는 multilingual-e5 또는 ko-sbert 계열이 권장됩니다.',
  },
];

type UploadStatus = 'idle' | 'loading' | 'success' | 'error';

const EvalDatasetPage = () => {
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle');
  const [uploadedFileName, setUploadedFileName] = useState<string>('');
  const [items, setItems] = useState<EvalDatasetItem[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isValidFile = (file: File) => {
    const name = file.name.toLowerCase();
    return ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext));
  };

  const processFile = useCallback((file: File) => {
    if (!isValidFile(file)) {
      alert('PDF 또는 Word 문서(.pdf, .doc, .docx)만 업로드할 수 있습니다.');
      return;
    }

    setUploadedFileName(file.name);
    setUploadStatus('loading');
    setItems([]);

    // Mock: 실제 API 호출 대신 2초 후 목데이터 반환
    setTimeout(() => {
      setItems(MOCK_ITEMS);
      setUploadStatus('success');
    }, 2000);
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) processFile(file);
    // 같은 파일 재선택 허용
    e.target.value = '';
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) processFile(file);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => setIsDragOver(false);

  const handleReset = () => {
    setUploadStatus('idle');
    setUploadedFileName('');
    setItems([]);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#fff' }}>
      {/* 헤더 */}
      <header className="flex shrink-0 items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
        <div className="flex items-center gap-3">
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-md"
            style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
          >
            <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z" />
            </svg>
          </div>
          <div>
            <h1 className="text-[15px] font-semibold text-zinc-900">평가 데이터셋 추출</h1>
            <p className="text-[11.5px] font-semibold uppercase tracking-widest text-violet-500">
              Eval Dataset
            </p>
          </div>
        </div>

        {uploadStatus === 'success' && (
          <div className="flex items-center gap-3">
            <span className="text-[12px] text-zinc-400">
              {uploadedFileName} — {items.length}개 항목
            </span>
            <button
              onClick={handleReset}
              className="flex items-center gap-1.5 rounded-xl border border-zinc-200 bg-zinc-50 px-3.5 py-2 text-[13px] font-medium text-zinc-600 transition-all hover:border-zinc-300 hover:bg-zinc-100"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
              </svg>
              새 파일
            </button>
            <button
              onClick={() => {
                const csv = [
                  '순서,질문,답변',
                  ...items.map((item) =>
                    `${item.id},"${item.question.replace(/"/g, '""')}","${item.answer.replace(/"/g, '""')}"`
                  ),
                ].join('\n');
                const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `eval_dataset_${Date.now()}.csv`;
                a.click();
                URL.revokeObjectURL(url);
              }}
              className="flex items-center gap-1.5 rounded-xl bg-violet-600 px-3.5 py-2 text-[13px] font-medium text-white shadow-sm transition-all hover:bg-violet-700 active:scale-95"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
              </svg>
              CSV 다운로드
            </button>
          </div>
        )}
      </header>

      {/* 메인 콘텐츠 */}
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <div style={{ maxWidth: '900px', margin: '0 auto', padding: '2rem 1.5rem' }}>

          {/* 업로드 영역 */}
          {uploadStatus === 'idle' && (
            <div className="mb-8">
              <p className="mb-1.5 text-[12px] text-zinc-400">
                문서를 업로드하면 AI가 평가용 질문-답변 쌍을 자동으로 생성합니다.
              </p>
              <div
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
                className={`group relative flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-8 py-16 transition-all duration-200 ${
                  isDragOver
                    ? 'border-violet-400 bg-violet-50/60'
                    : 'border-zinc-200 bg-zinc-50/50 hover:border-violet-300 hover:bg-violet-50/30'
                }`}
              >
                <div
                  className={`mb-4 flex h-14 w-14 items-center justify-center rounded-2xl shadow-md transition-all duration-200 ${
                    isDragOver ? 'scale-110' : 'group-hover:scale-105'
                  }`}
                  style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
                >
                  <svg className="h-7 w-7 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5" />
                  </svg>
                </div>

                {isDragOver ? (
                  <p className="text-[15px] font-semibold text-violet-600">여기에 놓아주세요</p>
                ) : (
                  <>
                    <p className="text-[15px] font-semibold text-zinc-700">
                      파일을 드래그하거나 클릭하여 업로드
                    </p>
                    <p className="mt-1.5 text-[12.5px] text-zinc-400">
                      PDF, DOC, DOCX 파일 지원
                    </p>
                  </>
                )}

                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.doc,.docx"
                  className="hidden"
                  onChange={handleFileChange}
                />
              </div>
            </div>
          )}

          {/* 로딩 상태 */}
          {uploadStatus === 'loading' && (
            <div className="mb-8 flex flex-col items-center justify-center rounded-2xl border border-zinc-200 bg-zinc-50/50 px-8 py-20">
              <div className="relative mb-5">
                <div
                  className="h-14 w-14 animate-spin rounded-full border-4 border-zinc-200"
                  style={{ borderTopColor: '#7c3aed' }}
                />
                <div
                  className="absolute inset-0 m-auto h-6 w-6 rounded-full"
                  style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)', top: '50%', left: '50%', transform: 'translate(-50%, -50%)' }}
                />
              </div>
              <p className="text-[15px] font-semibold text-zinc-700">문서 분석 중...</p>
              <p className="mt-1 text-[12.5px] text-zinc-400">
                <span className="font-medium text-violet-500">{uploadedFileName}</span> 에서 평가 데이터셋을 생성하고 있습니다
              </p>
            </div>
          )}

          {/* 결과 테이블 */}
          {uploadStatus === 'success' && items.length > 0 && (
            <div>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <h2 className="text-[15px] font-semibold text-zinc-900">추출 결과</h2>
                  <p className="mt-0.5 text-[12px] text-zinc-400">
                    <span className="font-medium text-violet-500">{uploadedFileName}</span> 에서{' '}
                    <span className="font-medium text-zinc-600">{items.length}개</span> 항목 생성됨
                  </p>
                </div>
              </div>

              <div className="overflow-hidden rounded-2xl border border-zinc-200 shadow-sm">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}>
                      <th className="w-16 px-5 py-3.5 text-[11.5px] font-semibold uppercase tracking-widest text-white/80">
                        순서
                      </th>
                      <th className="w-2/5 px-5 py-3.5 text-[11.5px] font-semibold uppercase tracking-widest text-white/80">
                        질문
                      </th>
                      <th className="px-5 py-3.5 text-[11.5px] font-semibold uppercase tracking-widest text-white/80">
                        답변
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-100">
                    {items.map((item, idx) => (
                      <tr
                        key={item.id}
                        className={`transition-colors duration-100 hover:bg-violet-50/40 ${
                          idx % 2 === 0 ? 'bg-white' : 'bg-zinc-50/50'
                        }`}
                      >
                        <td className="px-5 py-4 align-top">
                          <span
                            className="inline-flex h-7 w-7 items-center justify-center rounded-lg text-[12px] font-bold text-white"
                            style={{ background: 'linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)' }}
                          >
                            {item.id}
                          </span>
                        </td>
                        <td className="px-5 py-4 align-top">
                          <p className="text-[14px] leading-[1.7] text-zinc-800">{item.question}</p>
                        </td>
                        <td className="px-5 py-4 align-top">
                          <p className="text-[14px] leading-[1.7] text-zinc-600">{item.answer}</p>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default EvalDatasetPage;
