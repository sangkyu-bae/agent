// graph-rag-foundation Design §5.3 — 그래프 RAG 관리자 화면·빌더 토글 쿼리
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { graphRagService } from '@/services/graphRagService';
import type {
  EntityListParams,
  ExtractMode,
  GraphRagSettingsRequest,
  KbDocumentJobsResponse,
  ReviewRejectRequest,
  SearchTestRequest,
  StageChangeRequest,
  TopicCreateRequest,
  TopicUpdateRequest,
} from '@/types/graphRag';

const JOB_POLL_MS = 5_000;
const ACTIVE_JOB = new Set(['pending', 'processing']);

/** 빌더·채팅 노출 판단. 실패하면 보이지 않음(토글 DOM 없음). */
export const useGraphRagCapabilities = () =>
  useQuery({
    queryKey: queryKeys.graphRag.capabilities(),
    queryFn: graphRagService.getCapabilities,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

export const useGraphRagSettings = () =>
  useQuery({
    queryKey: queryKeys.graphRag.settings(),
    queryFn: graphRagService.getSettings,
  });

export const useUpdateGraphRagSettings = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: GraphRagSettingsRequest) => graphRagService.updateSettings(req),
    onSuccess: (data) => qc.setQueryData(queryKeys.graphRag.settings(), data),
  });
};

export const useChangeGraphRagStage = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: StageChangeRequest) => graphRagService.changeStage(req),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.graphRag.settings(), data);
      qc.invalidateQueries({ queryKey: queryKeys.graphRag.capabilities() });
    },
  });
};

export const useGraphRagHealth = () =>
  useQuery({
    queryKey: queryKeys.graphRag.health(),
    queryFn: graphRagService.getHealth,
    staleTime: 30_000,
  });

/** 진행 중 잡이 있으면 5초마다 다시 읽고, 없으면 멈춘다(§5.4 추출 탭). */
export const useGraphKbDocuments = (kbId: string | null) =>
  useQuery({
    queryKey: queryKeys.graphRag.kbDocuments(kbId ?? ''),
    queryFn: () => graphRagService.getKbDocuments(kbId as string),
    enabled: !!kbId,
    refetchInterval: (query) => {
      const data = query.state.data as KbDocumentJobsResponse | undefined;
      return data?.items.some((d) => d.job && ACTIVE_JOB.has(d.job.status))
        ? JOB_POLL_MS
        : false;
    },
  });

export const useExtractGraphDocument = (kbId: string | null) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ documentId, mode }: { documentId: string; mode: ExtractMode }) =>
      graphRagService.extract(documentId, mode),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: queryKeys.graphRag.kbDocuments(kbId ?? '') }),
  });
};

export const useGraphReview = (enabled = true) =>
  useQuery({
    queryKey: queryKeys.graphRag.review('pending'),
    queryFn: () => graphRagService.getReview('pending'),
    enabled,
  });

const useInvalidateAfterReview = () => {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: queryKeys.graphRag.review('pending') });
    // 주제 판정 처리는 주제 목록(상태·문서 수)도 바꾼다
    qc.invalidateQueries({ queryKey: [...queryKeys.graphRag.all, 'topics'] });
  };
};

export const useApproveGraphReview = () => {
  const refresh = useInvalidateAfterReview();
  return useMutation({
    mutationFn: ({ id, note }: { id: string; note?: string | null }) =>
      graphRagService.approveReview(id, note),
    onSuccess: refresh,
  });
};

export const useRejectGraphReview = () => {
  const refresh = useInvalidateAfterReview();
  return useMutation({
    mutationFn: ({ id, req }: { id: string; req: ReviewRejectRequest }) =>
      graphRagService.rejectReview(id, req),
    onSuccess: refresh,
  });
};

export const useGraphTopics = (includeRetired = false, enabled = true) =>
  useQuery({
    queryKey: queryKeys.graphRag.topics(includeRetired),
    queryFn: () => graphRagService.getTopics(includeRetired),
    enabled,
  });

export const useCreateGraphTopic = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: TopicCreateRequest) => graphRagService.createTopic(req),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...queryKeys.graphRag.all, 'topics'] }),
  });
};

export const useUpdateGraphTopic = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, req }: { id: string; req: TopicUpdateRequest }) =>
      graphRagService.updateTopic(id, req),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...queryKeys.graphRag.all, 'topics'] }),
  });
};

export const useGraphEntities = (params: EntityListParams, enabled = true) =>
  useQuery({
    queryKey: queryKeys.graphRag.entities({ ...params }),
    queryFn: () => graphRagService.getEntities(params),
    enabled,
    placeholderData: (prev) => prev,
  });

export const useGraphEntity = (id: string | null) =>
  useQuery({
    queryKey: queryKeys.graphRag.entity(id ?? ''),
    queryFn: () => graphRagService.getEntity(id as string),
    enabled: !!id,
  });

export const useGraphSearchTest = () =>
  useMutation({ mutationFn: (req: SearchTestRequest) => graphRagService.searchTest(req) });

export const useGraphIntegrity = () =>
  useMutation({ mutationFn: (kbId?: string | null) => graphRagService.checkIntegrity(kbId) });
