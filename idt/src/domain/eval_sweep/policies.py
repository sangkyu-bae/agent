"""모델 스윕 도메인 정책.

Design Ref: §3.1 — SweepPolicy(실행 제약) / ToolAccuracyPolicy(도구 호출 정확도).
외부 호출 없이 순수 검증·계산 함수만 보관한다 (domain → infrastructure 참조 금지).
"""
from src.domain.ragas.policies import EvaluationPolicy
from src.domain.ragas.value_objects import MetricType

# 스윕은 agent 대상 전용이다 (Design §2.1 Out of Scope: rag/retrieval 스윕 제외).
_SWEEP_TARGET_TYPE = "agent"


class SweepPolicy:
    """스윕 생성 시 강제 규칙.

    Design Ref: D7 — 순차 실행이므로 모델 수를 제한해 소요시간·비용을 통제한다.
    Design Ref: D9 — temperature는 재현성 NFR을 위해 사용자 선택 없이 고정한다.
    """

    MAX_MODELS = 5
    FIXED_TEMPERATURE = 0.0

    @staticmethod
    def validate(
        *,
        model_ids: list[str],
        judge_llm_model_id: str | None,
        metrics: list[MetricType],
        testset_case_count: int,
    ) -> list[str]:
        """위반 사항을 모두 모아 반환한다 (EvaluationPolicy.validate_config 선례).

        사용자가 400 응답을 여러 번 왕복하지 않도록 조기 반환하지 않는다.
        """
        return [
            *SweepPolicy._validate_models(model_ids),
            *SweepPolicy._validate_judge(judge_llm_model_id),
            *SweepPolicy._validate_metrics(metrics),
            *SweepPolicy._validate_testset(testset_case_count),
        ]

    @staticmethod
    def total_runs(model_ids: list[str]) -> int:
        """스윕 1건이 생성할 evaluation_run 개수 (Design §2.2)."""
        return len(model_ids)

    # ── 개별 규칙 ──────────────────────────────────────────────────

    @staticmethod
    def _validate_models(model_ids: list[str]) -> list[str]:
        if not model_ids:
            return ["최소 1개 이상의 피평가 모델이 필요합니다"]
        if len(model_ids) > SweepPolicy.MAX_MODELS:
            return [
                f"스윕당 모델은 최대 {SweepPolicy.MAX_MODELS}개입니다 "
                f"(선택: {len(model_ids)}개)"
            ]
        if len(set(model_ids)) != len(model_ids):
            return ["동일 모델을 중복 선택할 수 없습니다"]
        return []

    @staticmethod
    def _validate_judge(judge_llm_model_id: str | None) -> list[str]:
        if not judge_llm_model_id or not judge_llm_model_id.strip():
            return ["채점에 사용할 judge 모델을 지정해야 합니다"]
        return []

    @staticmethod
    def _validate_metrics(metrics: list[MetricType]) -> list[str]:
        if not metrics:
            return ["최소 1개 이상의 평가 지표가 필요합니다"]
        # agent 대상 허용 메트릭 판정은 EvaluationPolicy가 단일 진실원이다.
        return EvaluationPolicy.validate_metrics_for_target(
            _SWEEP_TARGET_TYPE, metrics
        )

    @staticmethod
    def _validate_testset(testset_case_count: int) -> list[str]:
        if testset_case_count < 1:
            return ["테스트셋에 평가할 케이스가 없습니다"]
        return []


class ToolAccuracyPolicy:
    """도구 호출 정확도 — expected_tools와 실제 호출의 집합 비교.

    Design Ref: D6 — 순서를 무시한다. 동등한 대안 경로를 오답 처리하지 않기 위함.
    Design Ref: G6 — 기대 도구가 기재되지 않은 케이스는 0점이 아니라 N/A(None)다.
    """

    _KEYS = ("tool_precision", "tool_recall", "tool_f1")

    @staticmethod
    def score(
        expected: list[str] | None, actual: list[str]
    ) -> dict[str, float | None]:
        """precision / recall / f1을 반환한다. 측정 불가 시 전부 None.

        expected 미기재는 "성능이 0"이 아니라 "측정 대상 아님"이다 — 도구를
        지원하지 않는 모델이 부당하게 0점으로 찍히는 것을 막는다 (Plan R-4).
        """
        if not expected:
            return dict.fromkeys(ToolAccuracyPolicy._KEYS, None)

        expected_set, actual_set = set(expected), set(actual)
        hits = len(expected_set & actual_set)

        precision = hits / len(actual_set) if actual_set else 0.0
        recall = hits / len(expected_set)
        return {
            "tool_precision": precision,
            "tool_recall": recall,
            "tool_f1": _f1(precision, recall),
        }


def _f1(precision: float, recall: float) -> float:
    total = precision + recall
    if total == 0:
        return 0.0
    return 2 * precision * recall / total


def mean_ignoring_none(values: list[float | None]) -> float | None:
    """N/A(None)를 분모에서 제외한 평균. 유효 표본이 없으면 None.

    Design Ref: §3.5 — 0.0은 "측정했고 0점"이므로 평균에 반영되어야 하고,
    None은 "측정 불가"라 표본에서 빠져야 한다. 둘을 섞으면 지표가 왜곡된다.
    """
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)
