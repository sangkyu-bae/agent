// Design Ref: image-generation-tool §5.3 / D-10 — 산출 이미지는 JWT 가 필요해 <img src> 직행이 불가.
// 인증 클라이언트로 blob 을 받아 object URL 로 표시하고, 언마운트 시 해제한다.
// 실패(401·404·네트워크)는 다운로드 링크로 폴백 — 히스토리 재조회·토큰 만료에서도 본문이 깨지지 않는다.
import { useEffect, useState } from 'react';
import { ImageOff } from 'lucide-react';
import { documentExtractorService } from '@/services/documentExtractorService';

interface AuthenticatedImageProps {
  fileId: string;
  /** 마크다운 alt = 파일명 (다운로드 파일명으로도 쓴다) */
  alt: string;
}

/** 결과는 fileId 와 함께 보관 — fileId 가 바뀌면 자동으로 로딩 상태로 돌아간다 (effect 내 동기 setState 불필요) */
type LoadResult =
  | { fileId: string; status: 'ready'; url: string }
  | { fileId: string; status: 'error' };

const AuthenticatedImage = ({ fileId, alt }: AuthenticatedImageProps) => {
  const [result, setResult] = useState<LoadResult | null>(null);
  const state = result && result.fileId === fileId ? result : { status: 'loading' as const };

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;

    documentExtractorService
      .fetchGeneratedFileBlob(fileId)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setResult({ fileId, status: 'ready', url: objectUrl });
      })
      .catch(() => {
        if (!cancelled) setResult({ fileId, status: 'error' });
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [fileId]);

  const download = () => void documentExtractorService.downloadGeneratedFile(fileId, alt);

  // 마크다운 img 는 <p> 안에 놓이므로 블록 요소 대신 span 으로 구성한다.
  if (state.status === 'loading') {
    return (
      <span
        role="status"
        aria-label="이미지 불러오는 중"
        className="my-2 block h-48 w-64 max-w-full animate-pulse rounded-xl bg-surface-sunken"
      />
    );
  }

  if (state.status === 'error') {
    return (
      <a
        href={`/api/v1/document-extractor/files/${fileId}`}
        onClick={(e) => {
          e.preventDefault();
          download();
        }}
        className="my-2 inline-flex items-center gap-1.5 rounded-xl border border-border bg-surface-muted px-3 py-2 text-sm text-fg-muted hover:text-fg"
      >
        <ImageOff className="h-4 w-4 shrink-0" strokeWidth={1.75} aria-hidden="true" />
        이미지를 불러오지 못했습니다 · 다운로드 ({alt})
      </a>
    );
  }

  return (
    <img
      src={state.url}
      alt={alt}
      title="클릭하면 다운로드합니다"
      onClick={download}
      className="my-2 block max-h-[512px] max-w-full cursor-pointer rounded-xl border border-border"
    />
  );
};

export default AuthenticatedImage;
