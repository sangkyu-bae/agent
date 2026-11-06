"""PiiMessageMasker 단위 테스트 — Design §4.2."""

import json

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from pydantic import BaseModel

from tests.application.pii_masking._support import make_masker

PHONE = "010-1234-5678"
EMAIL = "hong@example.com"


def _scope(masker):
    return masker.new_scope()


class TestPlaceholderNotice:
    """Check G-13 — 마스킹된 요청에는 placeholder 가 실제 값이라는 안내가 붙는다.

    안내가 없으면 "확인된 값만 써라" 규칙을 가진 인자 작성 LLM 이 `[EMAIL_1]` 을
    미확인 값으로 보고 도구 호출을 포기한다 (승인 스모크 실런에서 재현).
    """

    def test_notice_appended_to_system_when_placeholder_sent(self):
        from src.domain.pii_masking.policies import PII_PLACEHOLDER_NOTICE

        masker = make_masker()
        body, system = masker.mask_request(
            [HumanMessage(content=f"{EMAIL} 로 보내줘")],
            _scope(masker),
            system=SystemMessage(content="너는 메일 보조다."),
        )
        assert body[0].content == "[EMAIL_1] 로 보내줘"
        assert system.content.startswith("너는 메일 보조다.")
        assert system.content.endswith(PII_PLACEHOLDER_NOTICE)

    def test_notice_creates_system_when_missing(self):
        from src.domain.pii_masking.policies import PII_PLACEHOLDER_NOTICE

        masker = make_masker()
        _, system = masker.mask_request(
            [HumanMessage(content=PHONE)], _scope(masker)
        )
        assert isinstance(system, SystemMessage)
        assert system.content == PII_PLACEHOLDER_NOTICE

    def test_no_notice_when_nothing_masked(self):
        masker = make_masker()
        original = SystemMessage(content="규정 안내")
        body, system = masker.mask_request(
            [HumanMessage(content="금리 알려줘")], _scope(masker), system=original
        )
        assert system is original
        assert body[0].content == "금리 알려줘"

    def test_no_notice_for_user_typed_literal_only(self):
        # 사용자가 직접 친 `[PHONE_1]` 은 vault 에 없는 문자열이다 — 안내 대상 아님.
        masker = make_masker()
        _, system = masker.mask_request(
            [HumanMessage(content="[PHONE_1] 이 뭐야")], _scope(masker)
        )
        assert system is None

    def test_no_notice_in_shadow_mode(self):
        masker = make_masker(mode="shadow")
        body, system = masker.mask_request(
            [HumanMessage(content=PHONE)], _scope(masker)
        )
        assert system is None
        assert body[0].content == PHONE

    def test_notice_text_has_no_numbered_placeholder(self):
        # 번호 있는 예시는 다음 호출에서 입력 문자열로 예약되어 번호 체계를 흐린다.
        from src.domain.pii_masking.policies import PII_PLACEHOLDER_NOTICE
        from src.domain.pii_masking.schemas import PLACEHOLDER_PATTERN

        assert PLACEHOLDER_PATTERN.search(PII_PLACEHOLDER_NOTICE) is None


class TestMaskMessages:
    def test_mask_messages_all_roles_masked(self):
        masker = make_masker()
        scope = _scope(masker)
        out = masker.mask_messages(
            [
                SystemMessage(content=f"담당 {PHONE}"),
                HumanMessage(content=f"{PHONE}로 보내"),
                ToolMessage(content=f"sent {EMAIL}", tool_call_id="c1"),
            ],
            scope,
        )
        assert [m.content for m in out] == [
            "담당 [PHONE_1]",
            "[PHONE_1]로 보내",
            "sent [EMAIL_1]",
        ]

    def test_mask_messages_keeps_ids_and_types(self):
        masker = make_masker()
        original = ToolMessage(content=PHONE, tool_call_id="c1", id="m1")
        (out,) = masker.mask_messages([original], _scope(masker))
        assert isinstance(out, ToolMessage)
        assert (out.tool_call_id, out.id) == ("c1", "m1")

    def test_mask_messages_does_not_mutate_input(self):
        masker = make_masker()
        original = HumanMessage(content=PHONE)
        masker.mask_messages([original], _scope(masker))
        assert original.content == PHONE

    def test_mask_messages_unchanged_message_returned_as_same_object(self):
        masker = make_masker()
        original = HumanMessage(content="규정 알려줘")
        assert masker.mask_messages([original], _scope(masker))[0] is original

    def test_mask_messages_tool_call_args_masked(self):
        masker = make_masker()
        message = AIMessage(
            content="",
            tool_calls=[
                {"name": "send", "args": {"to": EMAIL, "cc": [PHONE]}, "id": "c1"}
            ],
        )
        (out,) = masker.mask_messages([message], _scope(masker))
        assert out.tool_calls[0]["args"] == {"to": "[EMAIL_1]", "cc": ["[PHONE_1]"]}
        assert out.tool_calls[0]["id"] == "c1"

    def test_mask_messages_raw_openai_tool_calls_masked(self):
        masker = make_masker()
        raw = [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "send", "arguments": json.dumps({"to": EMAIL})},
            }
        ]
        message = AIMessage(content="", additional_kwargs={"tool_calls": raw})
        (out,) = masker.mask_messages([message], _scope(masker))
        dumped = json.dumps(out.additional_kwargs, ensure_ascii=False)
        assert EMAIL not in dumped
        assert "[EMAIL_1]" in dumped

    def test_mask_messages_image_block_untouched(self):
        # FR-16: 텍스트 블록만 마스킹하고 이미지 블록은 그대로 둔다.
        masker = make_masker()
        # base64 안에 전화번호 모양 숫자열이 있어도 건드리면 안 된다.
        url = "data:image/png;base64,iVBOR 010-1234-5678 9001011234567+/="
        image = {"type": "image_url", "image_url": {"url": url}}
        message = HumanMessage(content=[{"type": "text", "text": PHONE}, image])
        (out,) = masker.mask_messages([message], _scope(masker))
        assert out.content == [{"type": "text", "text": "[PHONE_1]"}, image]

    def test_mask_messages_same_value_across_messages_same_placeholder(self):
        masker = make_masker()
        out = masker.mask_messages(
            [HumanMessage(content=PHONE), AIMessage(content=f"확인 {PHONE}")],
            _scope(masker),
        )
        assert [m.content for m in out] == ["[PHONE_1]", "확인 [PHONE_1]"]

    def test_mask_messages_literal_in_later_message_reserved_first(self):
        # Design §6.2: 뒤 메시지의 `[PHONE_1]` 문자열과 번호가 겹치면 안 된다.
        masker = make_masker()
        out = masker.mask_messages(
            [HumanMessage(content=PHONE), HumanMessage(content="양식 [PHONE_1] 칸")],
            _scope(masker),
        )
        assert out[0].content == "[PHONE_2]"

    def test_mask_messages_shadow_returns_original_objects(self):
        masker = make_masker(mode="shadow")
        original = HumanMessage(content=PHONE)
        scope = _scope(masker)
        assert masker.mask_messages([original], scope)[0] is original
        assert scope.vault.counts()


class TestRestore:
    def test_restore_message_content_and_tool_calls(self):
        masker = make_masker()
        scope = _scope(masker)
        masker.mask_messages([HumanMessage(content=f"{PHONE} {EMAIL}")], scope)
        reply = AIMessage(
            content="[PHONE_1] 로 보냄",
            tool_calls=[{"name": "send", "args": {"to": "[EMAIL_1]"}, "id": "c1"}],
        )
        out = masker.restore_message(reply, scope)
        assert out.content == f"{PHONE} 로 보냄"
        assert out.tool_calls[0]["args"] == {"to": EMAIL}

    def test_restore_message_raw_tool_call_arguments(self):
        masker = make_masker()
        scope = _scope(masker)
        masker.mask_messages([HumanMessage(content=EMAIL)], scope)
        raw = [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "send", "arguments": '{"to": "[EMAIL_1]"}'},
            }
        ]
        out = masker.restore_message(
            AIMessage(content="", additional_kwargs={"tool_calls": raw}), scope
        )
        args = out.additional_kwargs["tool_calls"][0]["function"]["arguments"]
        assert json.loads(args) == {"to": EMAIL}

    def test_restore_output_pydantic_nested(self):
        class Inner(BaseModel):
            note: str

        class Decision(BaseModel):
            next: str
            reason: str
            items: list[Inner]
            score: int

        masker = make_masker()
        scope = _scope(masker)
        masker.mask_messages([HumanMessage(content=PHONE)], scope)
        decision = Decision(
            next="worker",
            reason="[PHONE_1] 확인",
            items=[Inner(note="[PHONE_1]")],
            score=3,
        )
        out = masker.restore_output(decision, scope)
        assert isinstance(out, Decision)
        assert out.reason == f"{PHONE} 확인"
        assert out.items[0].note == PHONE
        assert out.score == 3

    def test_restore_output_include_raw_dict(self):
        masker = make_masker()
        scope = _scope(masker)
        masker.mask_messages([HumanMessage(content=PHONE)], scope)
        out = masker.restore_output(
            {
                "raw": AIMessage(content="[PHONE_1]"),
                "parsed": {"a": "[PHONE_1]"},
                "parsing_error": None,
            },
            scope,
        )
        assert out["raw"].content == PHONE
        assert out["parsed"] == {"a": PHONE}

    def test_restore_output_string(self):
        masker = make_masker()
        scope = _scope(masker)
        masker.mask_messages([HumanMessage(content=PHONE)], scope)
        assert masker.restore_output("[PHONE_1]", scope) == PHONE

    def test_restore_output_structured_orphan_kept_for_tool_blocking(self):
        # Design D-08: 파이프라인은 구조화 출력(arguments_json)을 그대로 도구 인자로
        # 쓴다. 고아를 redact하면 `[REDACTED_EMAIL]`로 MCP가 실행되므로 남겨 둔다.
        class Args(BaseModel):
            arguments_json: str

        masker = make_masker()
        scope = _scope(masker)
        masker.mask_messages([HumanMessage(content=EMAIL)], scope)
        out = masker.restore_output(
            Args(arguments_json='{"to": "[EMAIL_9]", "cc": "[EMAIL_1]"}'), scope
        )
        assert out.arguments_json == f'{{"to": "[EMAIL_9]", "cc": "{EMAIL}"}}'

    def test_restore_output_raw_message_still_redacts_orphan(self):
        masker = make_masker()
        out = masker.restore_output({"raw": AIMessage(content="[PHONE_9]")}, _scope(masker))
        assert out["raw"].content == "[REDACTED_PHONE]"

    def test_restore_message_orphan_redacted(self):
        masker = make_masker()
        out = masker.restore_message(AIMessage(content="[PHONE_9]"), _scope(masker))
        assert out.content == "[REDACTED_PHONE]"


class TestOrphanArgs:
    def test_has_orphan_args_hallucinated_placeholder(self):
        masker = make_masker()
        assert masker.has_orphan({"to": "[EMAIL_9]"}, _scope(masker)) is True

    def test_restore_message_orphan_in_tool_args_kept_for_blocking(self):
        # 그래프 테스트 결함: 인자의 고아를 redact하면 `[REDACTED_EMAIL]`로 도구가
        # 실행된다. 인자는 알려진 placeholder만 원복하고 고아는 남겨 차단 대상으로 둔다.
        masker = make_masker()
        scope = _scope(masker)
        masker.mask_messages([HumanMessage(content=EMAIL)], scope)
        reply = AIMessage(
            content="[EMAIL_9] 확인",
            tool_calls=[
                {
                    "name": "send",
                    "args": {"to": "[EMAIL_9]", "cc": "[EMAIL_1]"},
                    "id": "c1",
                }
            ],
        )
        out = masker.restore_message(reply, scope)
        assert out.tool_calls[0]["args"] == {"to": "[EMAIL_9]", "cc": EMAIL}
        assert out.content == "[REDACTED_EMAIL] 확인"
        assert masker.has_orphan(out.tool_calls[0]["args"], scope) is True

    def test_restore_message_shadow_literal_not_restored(self):
        # shadow는 외부로 원문을 보냈다. 응답의 placeholder 형태 문자열은
        # 원래부터 있던 문자열이다.
        masker = make_masker(mode="shadow")
        scope = _scope(masker)
        masker.mask_messages([HumanMessage(content=PHONE)], scope)
        reply = AIMessage(
            content="양식 [PHONE_1]",
            tool_calls=[{"name": "send", "args": {"to": "[PHONE_1]"}, "id": "c1"}],
        )
        out = masker.restore_message(reply, scope)
        assert out.content == "양식 [PHONE_1]"
        assert out.tool_calls[0]["args"] == {"to": "[PHONE_1]"}
