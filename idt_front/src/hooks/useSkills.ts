import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { skillService } from '@/services/skillService';
import { queryKeys } from '@/lib/queryKeys';
import type {
  ListSkillsRequest,
  CreateSkillRequest,
  UpdateSkillRequest,
  ForkSkillRequest,
} from '@/types/skill';

export const useSkills = (params: ListSkillsRequest = {}) =>
  useQuery({
    queryKey: queryKeys.admin.skills(params),
    queryFn: () => skillService.getSkills(params),
  });

export const useSkill = (id: string | null) =>
  useQuery({
    queryKey: queryKeys.admin.skill(id ?? ''),
    queryFn: () => skillService.getSkill(id as string),
    enabled: !!id,
  });

const invalidateSkills = (qc: ReturnType<typeof useQueryClient>) =>
  qc.invalidateQueries({ queryKey: [...queryKeys.admin.all, 'skills'] });

export const useCreateSkill = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateSkillRequest) => skillService.createSkill(data),
    onSuccess: () => invalidateSkills(qc),
  });
};

export const useUpdateSkill = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateSkillRequest }) =>
      skillService.updateSkill(id, data),
    onSuccess: () => invalidateSkills(qc),
  });
};

export const useDeleteSkill = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => skillService.deleteSkill(id),
    onSuccess: () => invalidateSkills(qc),
  });
};

export const useForkSkill = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data?: ForkSkillRequest }) =>
      skillService.forkSkill(id, data),
    onSuccess: () => invalidateSkills(qc),
  });
};
