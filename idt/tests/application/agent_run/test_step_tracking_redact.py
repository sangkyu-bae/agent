"""step input_summary 이미지 축약 — chat-image-attachment Design §7 / §8.2 #19."""
from langchain_core.messages import HumanMessage

from src.application.agent_run.step_tracking import _summarize_state_input

_B64 = "A" * 4000
_IMG = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_B64}", "detail": "high"}}


def test_list_content_user_message_is_summarized_without_base64() -> None:
    state = {
        "messages": [HumanMessage(content=[{"type": "text", "text": "표의 3분기 값은?"}, _IMG])],
        "iteration_count": 0,
        "last_worker_id": "",
    }
    out = _summarize_state_input(state)
    assert out is not None
    assert "표의 3분기 값은?" in out
    assert "[image:image/png]" in out
    assert "base64" not in out and "AAAA" not in out


def test_dict_user_message_with_list_content() -> None:
    state = {"messages": [{"role": "user", "content": [{"type": "text", "text": "q"}, _IMG]}]}
    out = _summarize_state_input(state)
    assert out is not None and "user=q" in out and "AAAA" not in out


def test_str_content_unchanged() -> None:
    state = {"messages": [HumanMessage(content="plain")], "iteration_count": 2, "last_worker_id": "w"}
    assert _summarize_state_input(state) == "iter=2 | last_worker=w | user=plain"
