"""최종 답변 인용 지시 문구 — 문구 SoT (answer-citation-verification §10.2, FR-04)."""

from __future__ import annotations


class FinalAnswerCitationPolicy:
    @staticmethod
    def instruction() -> str:
        return (
            "\n\n[인용 규칙]\n"
            "수집된 검색 결과의 각 청크 머리말에는 "
            "[출처 n: 파일 · 쪽] 형태의 번호가 있습니다.\n"
            "- 답변 문장이 어떤 청크의 내용에 근거하면 "
            "그 문장 끝 마침표 앞에 [n]을 붙이세요"
            " (예: 총량 목표를 경상성장률 이내로 관리합니다[1].).\n"
            "- 여러 청크에 근거하면 [1][3]처럼 이어 붙입니다.\n"
            "- 검색 결과에 근거하지 않는 문장(인사, 일반 안내)에는 붙이지 마세요.\n"
            "- 머리말에 없는 번호를 만들지 마세요."
        )
