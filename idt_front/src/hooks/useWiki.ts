// LLM-WIKI-001: Wiki 관리 TanStack Query 훅.
import { useMutation, useQuery } from '@tanstack/react-query';

import { queryClient } from '@/lib/queryClient';
import { queryKeys } from '@/lib/queryKeys';
import { wikiService } from '@/services/wikiService';
import type {
  CreateWikiRequest,
  DistillRequest,
  ReviewActionRequest,
  UpdateWikiRequest,
} from '@/types/wiki';

const invalidateWiki = () =>
  queryClient.invalidateQueries({ queryKey: queryKeys.wiki.all });

export const useWikiList = (params?: { agent_id?: string; status?: string }) =>
  useQuery({
    queryKey: queryKeys.wiki.list(params),
    queryFn: () => wikiService.getArticles(params),
  });

export const useWikiArticle = (id: string) =>
  useQuery({
    queryKey: queryKeys.wiki.detail(id),
    queryFn: () => wikiService.getArticle(id),
    enabled: !!id,
  });

export const useDistillWiki = () =>
  useMutation({
    mutationFn: (data: DistillRequest) => wikiService.distill(data),
    onSuccess: invalidateWiki,
  });

export const useApproveArticle = () =>
  useMutation({
    mutationFn: ({ id, data }: { id: string; data: ReviewActionRequest }) =>
      wikiService.approve(id, data),
    onSuccess: invalidateWiki,
  });

export const useRejectArticle = () =>
  useMutation({
    mutationFn: (id: string) => wikiService.reject(id),
    onSuccess: invalidateWiki,
  });

export const useDeprecateArticle = () =>
  useMutation({
    mutationFn: (id: string) => wikiService.deprecate(id),
    onSuccess: invalidateWiki,
  });

export const useRestoreArticle = () =>
  useMutation({
    mutationFn: ({ id, data }: { id: string; data: ReviewActionRequest }) =>
      wikiService.restore(id, data),
    onSuccess: invalidateWiki,
  });

export const useUpdateArticle = () =>
  useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateWikiRequest }) =>
      wikiService.update(id, data),
    onSuccess: invalidateWiki,
  });

// ── wiki-user-facing: 소유자 직접 작성 + 지식 트리 ──────────────

export const useWikiTree = (agentId: string) =>
  useQuery({
    queryKey: queryKeys.wiki.tree(agentId),
    queryFn: () => wikiService.getTree(agentId),
    enabled: !!agentId,
  });

export const useCreateWiki = () =>
  useMutation({
    mutationFn: (data: CreateWikiRequest) => wikiService.create(data),
    onSuccess: invalidateWiki,
  });
