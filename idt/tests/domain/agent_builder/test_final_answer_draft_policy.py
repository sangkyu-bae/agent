"""FinalAnswerDraftPolicy 단위 테스트.

Design Ref: action-category-compose-node §3.1 / D-07 / Plan FR-17·FR-18
  - detect: 초안 구획 목록 → 마지막 초안의 DraftContext. 없으면 None.
    같은 worker_id의 후속(비초안) 산출이 있으면 그것을 outcome으로 채택 —
    재개 런에서 _restore_state 가 주입한 집행 결과가 "승인 대기" 문구를 이긴다.
  - render_block: 초안 원문·집행 결과 블록. 초안은 한 글자도 바꾸지 않는다.
  - instruction: user tail 지시.

이 정책이 final_answer 초안 처리의 유일한 교체 지점이다(FR-18).
"""
from src.domain.agent_builder.policies import DraftContext, FinalAnswerDraftPolicy


class TestDetect:
    def test_no_sections_returns_none(self):
        assert FinalAnswerDraftPolicy.detect([]) is None
        assert FinalAnswerDraftPolicy.detect([], {}) is None

    def test_single_section(self):
        ctx = FinalAnswerDraftPolicy.detect([("mailer", "안녕하세요", "발송 완료")])
        assert ctx == DraftContext(worker_id="mailer", draft="안녕하세요", outcome="발송 완료")

    def test_last_section_wins(self):
        ctx = FinalAnswerDraftPolicy.detect([
            ("mailer", "첫 초안", "실패"),
            ("mailer", "둘째 초안", "성공"),
        ])
        assert ctx.draft == "둘째 초안"
        assert ctx.outcome == "성공"

    def test_later_output_overrides_outcome(self):
        """D-07: 재개 시 주입된 집행 결과가 초안 메시지 안의 '승인 대기' 문구를 이긴다."""
        ctx = FinalAnswerDraftPolicy.detect(
            [("mailer", "초안", "승인 대기로 등록되었습니다.")],
            later_outputs={"mailer": "메일 발송 성공 (id=42)"},
        )
        assert ctx.outcome == "메일 발송 성공 (id=42)"
        assert ctx.draft == "초안"

    def test_later_output_of_other_worker_is_ignored(self):
        ctx = FinalAnswerDraftPolicy.detect(
            [("mailer", "초안", "대기")], later_outputs={"other": "무관"},
        )
        assert ctx.outcome == "대기"


class TestRenderBlock:
    def test_contains_draft_verbatim(self):
        draft = "첫 줄\n\n  들여쓰기 유지  \n[대괄호] 포함"
        block = FinalAnswerDraftPolicy.render_block(
            DraftContext(worker_id="mailer", draft=draft, outcome="ok")
        )
        assert draft in block
        assert "ok" in block

    def test_block_labels_present(self):
        block = FinalAnswerDraftPolicy.render_block(
            DraftContext(worker_id="w", draft="d", outcome="o")
        )
        assert "초안" in block
        assert "집행 결과" in block

    def test_empty_draft_is_explained(self):
        """§6.1 #2·#3: 작성 실패 런에서는 빈 초안을 '없음'으로 명시한다."""
        block = FinalAnswerDraftPolicy.render_block(
            DraftContext(worker_id="w", draft="", outcome="초안 작성 실패: x")
        )
        assert "초안 작성 실패: x" in block
        assert "없" in block


class TestInstruction:
    def test_instruction_forbids_rewrite(self):
        text = FinalAnswerDraftPolicy.instruction()
        assert "초안" in text
        assert "그대로" in text
