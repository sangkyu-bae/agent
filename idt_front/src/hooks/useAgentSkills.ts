import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentSkillService } from '@/services/agentSkillService';
import { queryKeys } from '@/lib/queryKeys';

/** 에이전트에 부착된 Skill 목록. */
export const useAgentSkills = (agentId: string | null) =>
  useQuery({
    queryKey: queryKeys.agentBuilder.skills(agentId ?? ''),
    queryFn: () => agentSkillService.listAttached(agentId as string),
    enabled: !!agentId,
  });

export const useAttachSkill = (agentId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (skillId: string) =>
      agentSkillService.attach(agentId, skillId),
    onSuccess: () =>
      qc.invalidateQueries({
        queryKey: queryKeys.agentBuilder.skills(agentId),
      }),
  });
};

export const useDetachSkill = (agentId: string) => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (skillId: string) =>
      agentSkillService.detach(agentId, skillId),
    onSuccess: () =>
      qc.invalidateQueries({
        queryKey: queryKeys.agentBuilder.skills(agentId),
      }),
  });
};
