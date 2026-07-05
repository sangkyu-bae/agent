// document-template-extractor: extract/refine mutation 훅 (stateless — 캐시 무효화 없음)
import { useMutation } from '@tanstack/react-query';
import { documentExtractorService } from '@/services/documentExtractorService';
import type {
  ExtractDocumentResponse,
  RefineSlotsRequest,
  RefineSlotsResponse,
} from '@/types/documentExtractor';

interface ExtractVars {
  file: File;
  mcpPdfToHtmlToolId?: string;
  mcpHtmlToDocToolId?: string;
}

export const useExtractDocument = () =>
  useMutation<ExtractDocumentResponse, Error, ExtractVars>({
    mutationFn: ({ file, mcpPdfToHtmlToolId, mcpHtmlToDocToolId }) =>
      documentExtractorService.extract(
        file,
        mcpPdfToHtmlToolId,
        mcpHtmlToDocToolId,
      ),
  });

export const useRefineSlots = () =>
  useMutation<RefineSlotsResponse, Error, RefineSlotsRequest>({
    mutationFn: (request) => documentExtractorService.refine(request),
  });
