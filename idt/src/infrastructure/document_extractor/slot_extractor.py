"""SlotExtractor: HTML → 자동화 슬롯 추출/재추천 LLM (Design §3-3).

- 기본 LLM 모델(find_default) + llm_factory, temperature=0.0, 인스턴스 캐시
- 출력: JSON 배열 → TemplateSlot 목록. 불량 슬롯은 drop(경고 로그), 0개는 정상(R2)
- JSON 파싱 실패 시 1회 재시도 후 SlotExtractionFailedError
"""
import json
import re

from src.domain.document_extractor.exceptions import SlotExtractionFailedError
from src.domain.document_extractor.schemas import (
    SLOT_KEY_PATTERN,
    SuggestedSlots,
    TemplateSlot,
)
from src.domain.logging.interfaces.logger_interface import LoggerInterface
from src.infrastructure.langsmith.langsmith import (
    DOCUMENT_EXTRACTOR_PROJECT_NAME,
    make_document_extractor_tracer,
)

_CODE_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n|\n```$")
_VALID_SLOT_TYPES = {"value", "generated"}

_EXTRACT_SYSTEM_PROMPT = """당신은 정형 문서 양식 분석가입니다.
주어진 HTML 문서에서 "반복 사용 시 매번 바뀌는 부분"을 자동화 슬롯으로 추출하세요.

슬롯 유형:
- value: 사실 값이 들어가는 자리 (금액, 날짜, 이름, 번호 등)
- generated: 근거 자료를 바탕으로 서술을 작성하는 자리 (소견, 요약, 의견 등)

출력 형식 — JSON 배열만 출력 (다른 텍스트 금지):
[{"key": "loan_amount", "label": "여신금액", "slot_type": "value",
  "description": "슬롯 설명", "fill_hint": "채움 힌트", "sample_value": "원본에서 발췌한 예시값"}]

규칙:
- key는 영소문자 시작 + [a-z0-9_] 최대 50자 (영문 스네이크 케이스)
- label은 문서에 표기된 한국어 항목명 그대로
- sample_value는 원본 HTML에 있는 실제 값을 그대로 발췌 (프론트 토큰 치환 앵커로 사용)
- 문서 제목/고정 문구처럼 바뀌지 않는 부분은 슬롯이 아님
- 자동화할 부분이 없으면 빈 배열 []
"""

_REFINE_SUFFIX = """
[이전 추천 슬롯]
{prev_slots}

[사용자 보강 요청]
{instruction}

위 요청을 반영해 슬롯 목록 전체를 다시 추천하세요. 출력은 JSON 배열만.
"""


class SlotExtractor:
    """HTML 분석 LLM — 빌드타임 전용(compiler 무관, stateless)."""

    def __init__(
        self,
        llm_factory,
        llm_model_repository,
        logger: LoggerInterface,
        llm_html_max_chars: int = 20000,
    ) -> None:
        self._llm_factory = llm_factory
        self._llm_model_repository = llm_model_repository
        self._logger = logger
        self._llm_cache = None
        self._llm_html_max_chars = llm_html_max_chars
        self._trace_disabled_logged = False

    async def extract(self, html: str, request_id: str) -> SuggestedSlots:
        """HTML → 자동화 슬롯 추천."""
        user_prompt = f"[분석 대상 HTML]\n{self._clip_html(html, request_id)}"
        return await self._suggest(user_prompt, request_id, "slot-extract")

    async def refine(
        self,
        html: str,
        instruction: str,
        prev_slots: list[TemplateSlot],
        request_id: str,
    ) -> SuggestedSlots:
        """이전 추천 + 보강 지시 → 재추천 (GA3)."""
        prev_json = json.dumps(
            [
                {"key": s.key, "label": s.label, "slot_type": s.slot_type}
                for s in prev_slots
            ],
            ensure_ascii=False,
        )
        user_prompt = (
            f"[분석 대상 HTML]\n{self._clip_html(html, request_id)}\n"
            + _REFINE_SUFFIX.format(prev_slots=prev_json, instruction=instruction)
        )
        return await self._suggest(user_prompt, request_id, "slot-refine")

    def _clip_html(self, html: str, request_id: str) -> str:
        """LLM 입력 상한 초과 시 절단 — 모델 TPM 한도 초과(429) 방지.

        반환 html(템플릿 원본)이 아닌 LLM 프롬프트 입력만 자른다.
        """
        if len(html) <= self._llm_html_max_chars:
            return html
        self._logger.warning(
            "SlotExtractor html clipped for llm input",
            request_id=request_id,
            original_chars=len(html),
            max_chars=self._llm_html_max_chars,
        )
        return (
            html[: self._llm_html_max_chars]
            + "\n<!-- 이하 생략: LLM 입력 길이 한도 초과 -->"
        )

    async def _suggest(
        self, user_prompt: str, request_id: str, run_name: str
    ) -> SuggestedSlots:
        llm = await self._get_llm(request_id)
        messages = [
            {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        config = self._build_trace_config(run_name, request_id)
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                response = await llm.ainvoke(messages, config=config)
            except Exception as e:
                # LLM 호출 자체 실패(429/네트워크 등) — SDK가 이미 재시도했으므로
                # 즉시 도메인 예외로 감싸 라우터가 메시지를 UI로 전달하게 한다.
                raise SlotExtractionFailedError(
                    f"슬롯 추출 LLM 호출에 실패했습니다: {e}"
                ) from e
            content = getattr(response, "content", str(response))
            try:
                return self._parse_slots(content, request_id)
            except (ValueError, TypeError) as e:
                last_error = e
                self._logger.warning(
                    "SlotExtractor parse failed, retrying",
                    request_id=request_id,
                    attempt=attempt,
                    error=str(e),
                )
        raise SlotExtractionFailedError(
            f"슬롯 추출 결과를 해석할 수 없습니다: {last_error}"
        )

    def _build_trace_config(self, run_name: str, request_id: str) -> dict:
        """LangSmith 추적 config — 프로젝트 'document-extractor'로 per-run 기록.

        tracer가 None(API 키 없음)이면 callbacks 미설정 — 본 흐름 영향 없음.
        """
        tags = [DOCUMENT_EXTRACTOR_PROJECT_NAME, run_name]
        config: dict = {
            "run_name": run_name,
            "tags": tags,
            "metadata": {"request_id": request_id},
        }
        tracer = make_document_extractor_tracer(tags=tags)
        if tracer is not None:
            config["callbacks"] = [tracer]
        elif not self._trace_disabled_logged:
            self._trace_disabled_logged = True
            self._logger.warning(
                "LangSmith 추적 비활성 — LANGCHAIN_API_KEY/LANGSMITH_API_KEY "
                "미설정으로 document-extractor 프로젝트에 기록되지 않습니다.",
                request_id=request_id,
            )
        return config

    async def _get_llm(self, request_id: str):
        if self._llm_cache is not None:
            return self._llm_cache
        model = await self._llm_model_repository.find_default(request_id)
        if model is None:
            raise SlotExtractionFailedError("기본 LLM 모델이 설정되지 않았습니다.")
        self._llm_cache = self._llm_factory.create(model, 0.0)
        return self._llm_cache

    def _parse_slots(self, content: str, request_id: str) -> SuggestedSlots:
        text = _CODE_FENCE_RE.sub("", content.strip()).strip()
        raw = json.loads(text)
        if not isinstance(raw, list):
            raise ValueError(f"JSON 배열이 아님: {type(raw).__name__}")

        slots: list[TemplateSlot] = []
        seen: set[str] = set()
        for item in raw:
            slot = self._to_slot(item)
            if slot is None or slot.key in seen:
                self._logger.warning(
                    "SlotExtractor dropped invalid/duplicate slot",
                    request_id=request_id,
                    item=str(item)[:200],
                )
                continue
            seen.add(slot.key)
            slots.append(slot)
        return SuggestedSlots(slots=slots)

    @staticmethod
    def _to_slot(item) -> TemplateSlot | None:
        if not isinstance(item, dict):
            return None
        key = item.get("key", "")
        slot_type = item.get("slot_type", "")
        label = item.get("label", "")
        if not SLOT_KEY_PATTERN.match(key or ""):
            return None
        if slot_type not in _VALID_SLOT_TYPES or not label:
            return None
        return TemplateSlot(
            key=key,
            label=label,
            slot_type=slot_type,
            description=str(item.get("description", "") or ""),
            fill_hint=str(item.get("fill_hint", "") or ""),
            sample_value=str(item.get("sample_value", "") or ""),
        )
