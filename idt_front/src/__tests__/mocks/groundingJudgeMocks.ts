// answer-citation-verification Design §4.2 — 근거 판정 모델 관리자 설정 MSW 기본 핸들러
import { http, HttpResponse } from 'msw';
import { API_ENDPOINTS } from '@/constants/api';
import type { GroundingJudgeSettingResponse } from '@/types/groundingJudge';

export const mockGroundingJudgeSetting: GroundingJudgeSettingResponse = {
  judge_llm_model_id: null,
  effective: { model_id: 'uuid-1', model_name: 'gpt-4o', display_name: 'GPT-4o', source: 'env' },
};

const MODEL_NAMES: Record<string, [string, string]> = {
  'uuid-1': ['gpt-4o', 'GPT-4o'],
  'uuid-2': ['claude-sonnet-4-6', 'Claude Sonnet 4.6'],
};

export const groundingJudgeHandlers = [
  http.get(`*${API_ENDPOINTS.ADMIN_GROUNDING_JUDGE_SETTINGS}`, () =>
    HttpResponse.json(mockGroundingJudgeSetting)
  ),
  http.put(`*${API_ENDPOINTS.ADMIN_GROUNDING_JUDGE_SETTINGS}`, async ({ request }) => {
    const { judge_llm_model_id: id } = (await request.json()) as {
      judge_llm_model_id: string | null;
    };
    if (id === null) return HttpResponse.json(mockGroundingJudgeSetting);
    const names = MODEL_NAMES[id];
    if (!names) {
      return HttpResponse.json(
        { detail: { code: 'JUDGE_MODEL_NOT_FOUND', message: '사용할 수 없는 모델입니다' } },
        { status: 422 }
      );
    }
    return HttpResponse.json({
      judge_llm_model_id: id,
      effective: { model_id: id, model_name: names[0], display_name: names[1], source: 'admin' },
    });
  }),
];
