// golden-sample-blueprint Design §5.3 — 목록/상세/추출/저장/갱신/비활성화/폰트/옵션
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/queryKeys';
import { blueprintService } from '@/services/blueprintService';
import type { BlueprintCreateRequest, BlueprintUpdateRequest } from '@/types/blueprint';

export const useBlueprints = (includeInactive = true) =>
  useQuery({
    queryKey: queryKeys.blueprints.list(includeInactive),
    queryFn: () => blueprintService.list(includeInactive),
  });

export const useBlueprint = (id: string | null) =>
  useQuery({
    queryKey: queryKeys.blueprints.detail(id ?? ''),
    queryFn: () => blueprintService.get(id as string),
    enabled: !!id,
  });

export const useBlueprintFonts = () =>
  useQuery({ queryKey: queryKeys.blueprints.fonts(), queryFn: blueprintService.fonts });

export const useBlueprintOptions = (enabled = true) =>
  useQuery({
    queryKey: queryKeys.blueprints.options(),
    queryFn: blueprintService.options,
    enabled,
  });

export const useExtractBlueprint = () =>
  useMutation({
    mutationFn: ({ file, maxPages }: { file: File; maxPages?: number }) =>
      blueprintService.extract(file, maxPages),
  });

export const useCreateBlueprint = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: BlueprintCreateRequest) => blueprintService.create(req),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.blueprints.all }),
  });
};

export const useUpdateBlueprint = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, req }: { id: string; req: BlueprintUpdateRequest }) =>
      blueprintService.update(id, req),
    onSuccess: (data) => {
      qc.setQueryData(queryKeys.blueprints.detail(data.id), data);
      void qc.invalidateQueries({ queryKey: queryKeys.blueprints.all });
    },
  });
};

export const useDeactivateBlueprint = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => blueprintService.deactivate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.blueprints.all }),
  });
};
