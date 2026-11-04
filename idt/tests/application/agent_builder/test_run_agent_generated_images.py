"""generated_images 채널 수집·답변 후처리 — Design §3.4 / D-03 / §8.2 #10·#11."""
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage

from src.application.agent_builder.run_agent_use_case import RunAgentUseCase, _StreamState
from src.application.image_generation.answer_links import (
    FILES_PATH_PREFIX,
    append_generated_images,
    render_image_summary,
)
from src.domain.image_generation.value_objects import GeneratedImage, GenerationMode

IMG = {"file_id": "f" * 32, "filename": "generated-1.png", "mime": "image/png",
       "width": 1024, "height": 1024, "prompt": "p", "mode": "generate"}


class TestAppendGeneratedImages:
    def test_appends_missing_image_markdown(self) -> None:
        out = append_generated_images("배너를 만들었습니다.", [IMG])
        assert out == f"배너를 만들었습니다.\n\n![generated-1.png]({FILES_PATH_PREFIX}{'f' * 32})"

    def test_skips_when_file_id_already_present(self) -> None:
        answer = f"결과: ![x]({FILES_PATH_PREFIX}{'f' * 32})"
        assert append_generated_images(answer, [IMG]) == answer

    def test_appends_when_only_download_link_remains(self) -> None:
        # 2026-11 실런: final_answer 가 이미지 URL 을 placeholder 로 바꿈
        answer = (
            "배너를 생성했습니다.\n\n![배너](<insert-image-url-here>)\n\n"
            f"다운로드 링크: [generated-1.png]({FILES_PATH_PREFIX}{'f' * 32})"
        )
        out = append_generated_images(answer, [IMG])
        assert out.endswith(f"![generated-1.png]({FILES_PATH_PREFIX}{'f' * 32})")
        assert out.startswith(answer)

    def test_empty_inputs(self) -> None:
        assert append_generated_images("a", []) == "a"
        assert append_generated_images("a", None) == "a"
        assert append_generated_images("", [IMG]).startswith("![generated-1.png]")


class TestRenderSummary:
    def test_contains_three_contract_lines(self) -> None:
        r = GeneratedImage(
            file_id="id1", filename="generated-x.png", width=1024, height=1024, mime="image/png",
            model_id="m", model_name="gpt-image-1", provider="openai", prompt="가을 배너 " * 40,
            mode=GenerationMode.GENERATE, elapsed_ms=10, fell_back_to_generate=True,
        )
        text = render_image_summary(r)
        lines = text.split("\n")
        assert lines[0].startswith("이미지 생성 완료 (generated-x.png, 1024x1024)")
        assert lines[1] == f"![generated-x.png]({FILES_PATH_PREFIX}id1)"
        assert lines[2] == f"다운로드: [generated-x.png]({FILES_PATH_PREFIX}id1)"
        assert lines[3].startswith("프롬프트: ") and len(lines[3]) <= len("프롬프트: ") + 120
        assert "첨부 이미지가 없어 새로 생성" in lines[4]


class TestStreamCaptureAndAnswer:
    def _uc(self) -> RunAgentUseCase:
        uc = RunAgentUseCase.__new__(RunAgentUseCase)
        uc._tool_access_resolver = None  # tool-access-control: optional 의존성 (None=필터 없음)
        uc._logger = MagicMock()
        return uc

    def test_chain_end_captures_generated_images(self) -> None:
        uc = self._uc()
        state = _StreamState()
        uc._map_chain_end(
            "image_generate_worker",
            {"output": {"messages": [AIMessage(content="답")], "generated_images": [IMG]}},
            set(), MagicMock(), None, state,
        )
        assert state.generated_images == [IMG]
        # 빈 델타가 유효 값을 덮지 않는다
        uc._map_chain_end(
            "x", {"output": {"messages": [], "generated_images": []}}, set(), MagicMock(), None, state,
        )
        assert state.generated_images == [IMG]

    def test_resolve_answer_appends_images(self) -> None:
        uc = self._uc()
        state = _StreamState()
        state.final_messages = [AIMessage(content="요약만 남긴 최종 답변")]
        state.generated_images = [IMG]
        answer, _ = uc._resolve_answer(state)
        assert answer.startswith("요약만 남긴 최종 답변")
        assert f"{FILES_PATH_PREFIX}{'f' * 32}" in answer

    def test_resolve_answer_without_images_unchanged(self) -> None:
        uc = self._uc()
        state = _StreamState()
        state.final_messages = [AIMessage(content="그냥 답")]
        answer, _ = uc._resolve_answer(state)
        assert answer == "그냥 답"
