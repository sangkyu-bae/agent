"""prompt-guard 규칙 카탈로그 — Design Ref: §3.2 (카테고리·tier 배정의 SoT).

패턴은 NormalizationPolicy 로 정규화된(NFKC·casefold·zero-width 제거·공백 축약)
텍스트에 IGNORECASE|MULTILINE 으로 적용된다.

BLOCK 원칙: 대상 명사(지시·프롬프트·규칙·설정·시스템) + 덮어쓰기/유출 동사의
**동시 출현**.
명사 없는 '무시'·'역할' 류 단독 신호는 REVIEW 로 두어 판정기가 본다 (Plan RISK: 오차단).

Do 단계 정정(코퍼스 기반, Design §3.2 대비):
- ko.override.02 는 "새 규칙은 다음과 같습니다: ..." 같은 선의 문장을 막지 않도록
  대상을 시스템 프롬프트·'너의 지시/규칙' 으로 좁혔다.
- ko.leak.01 의 명사에서 '지시사항·설정·규칙' 을 빼고(사내 규정 질문과 충돌)
  프롬프트·지시문·시스템 메시지만 남겼다. '너의 규칙을 알려줘' 류는 ko.leak.02 REVIEW.
- any.jailbreak.01 의 '탈옥' 은 모드/실행 요구와 결합될 때만 매치한다
  ('아이폰 탈옥의 위험' 은 선의). 'without limits/rules' 는 금융 문장
  ('card without limits')과 충돌해 제외했다. 단독 'DAN' 은 이름과 충돌해
  'dan mode/모드' 결합만 BLOCK.
- 코퍼스로 넓힌 패턴(Check G-2 기록): ko.override.01 +원래·지침·조사/채움말·'무\\s*시';
  en.override.01 +of·guidelines; en.leak.01 +tell;
  any.delim.01 `^`→`(?:^|\\s)` +'system: you are';
  ko.role.01 +니; en.role.01 +'pretend that you'·'act as my'; ko.soft.01 +잊고;
  ko.soft.02 +지침·해제; en.soft.01 +instructions·'(previous|prior) instructions'.
"""
from __future__ import annotations

from src.domain.prompt_guard.schemas import GuardRule, GuardTier, RuleCategory

_KO_PARTICLE = r"(?:은|는|을|를|이|가|의|들을|들은)?"
_KO_FILLER = r"(?:\s*(?:전부|모두|다|싹|완전히|일단|이제))?"
_KO_TARGET_NOUN = (
    r"(?:지시사항|지시|프롬프트|규칙|설정|명령|가이드라인|지침|시스템\s*메시지)"
)
_KO_OVERRIDE_VERB = r"(?:무\s*시|잊|버리|취소|해제|리셋|초기화|지우)"

DEFAULT_RULES: tuple[GuardRule, ...] = (
    # ── 지시 덮어쓰기 (BLOCK) ───────────────────────────────────────────
    GuardRule(
        id="ko.override.01", category=RuleCategory.OVERRIDE, lang="ko",
        pattern=(
            r"(?:이전|앞의?|위의?|기존|지금까지(?:의|\s*받은)?|모든|원래)\s*(?:모든\s*)?"
            + _KO_TARGET_NOUN + r"\s*" + _KO_PARTICLE + _KO_FILLER + r"\s*"
            + _KO_OVERRIDE_VERB
        ),
        tier=GuardTier.BLOCK,
    ),
    GuardRule(
        id="ko.override.02", category=RuleCategory.OVERRIDE, lang="ko",
        pattern=(
            r"(?:새로운?|새|진짜|실제)\s*(?:시스템\s*프롬프트|(?:너의|네|당신의)\s*(?:지시|규칙))"
            r"\s*(?:은|는|이|가)?\s*(?:다음과\s*같|이렇|아래)"
        ),
        tier=GuardTier.BLOCK,
    ),
    GuardRule(
        id="en.override.01", category=RuleCategory.OVERRIDE, lang="en",
        pattern=(
            r"ignore\s+(?:all\s+|any\s+|the\s+|your\s+|of\s+)*"
            r"(?:previous|prior|above|earlier|preceding)\s+"
            r"(?:instructions?|prompts?|rules?|directions?|guidelines?)"
        ),
        tier=GuardTier.BLOCK,
    ),
    GuardRule(
        id="en.override.02", category=RuleCategory.OVERRIDE, lang="en",
        pattern=(
            r"(?:disregard|forget|override|bypass)\s+(?:all\s+|any\s+|your\s+|the\s+)*"
            r"(?:previous|prior|above|system|original)\s+"
            r"(?:instructions?|prompts?|rules?|guidelines?)"
        ),
        tier=GuardTier.BLOCK,
    ),
    # ── 시스템 프롬프트 유출 요구 (BLOCK) ───────────────────────────────
    GuardRule(
        id="ko.leak.01", category=RuleCategory.PROMPT_LEAK, lang="ko",
        pattern=(
            r"(?:시스템|초기|원래|숨겨진|내부|너의|네|당신의)\s*"
            r"(?:프롬프트|지시문|시스템\s*메시지)\s*(?:전체|전부|내용)?\s*"
            r"(?:을|를|이|가|은|는)?[^\n]{0,20}?"
            r"(?:출력|보여|알려|공개|말해|복사|반복|그대로)"
        ),
        tier=GuardTier.BLOCK,
    ),
    GuardRule(
        id="en.leak.01", category=RuleCategory.PROMPT_LEAK, lang="en",
        pattern=(
            r"(?:reveal|show|print|repeat|output|display|dump|leak|tell)\s+(?:me\s+)?"
            r"(?:your\s+|the\s+)?(?:system\s+prompt|initial\s+(?:prompt|instructions)|"
            r"hidden\s+(?:prompt|instructions)|instructions\s+above)"
        ),
        tier=GuardTier.BLOCK,
    ),
    GuardRule(
        id="en.leak.02", category=RuleCategory.PROMPT_LEAK, lang="en",
        pattern=(
            r"what\s+(?:is|are|were)\s+your\s+"
            r"(?:system\s+prompt|(?:initial\s+|original\s+)?instructions)"
        ),
        tier=GuardTier.BLOCK,
    ),
    # ── 가짜 시스템 구분자 (BLOCK) ──────────────────────────────────────
    GuardRule(
        id="any.delim.01", category=RuleCategory.FAKE_DELIMITER, lang="any",
        pattern=(
            r"\[\s*system\s*\]|<\|im_start\|>\s*system|<\|system\|>|<system>|"
            r"<<\s*sys\s*>>|"
            r"\[\s*inst\s*\]|(?:^|\s)#{1,3}\s*system\s*:|\bsystem\s*:\s*you\s+are"
        ),
        tier=GuardTier.BLOCK,
    ),
    # ── 탈옥 토큰 (BLOCK) ───────────────────────────────────────────────
    GuardRule(
        id="any.jailbreak.01", category=RuleCategory.JAILBREAK_TOKEN, lang="any",
        pattern=(
            r"developer\s+mode|do\s+anything\s+now|\bdan\s*(?:mode|모드)|jailbreak|"
            r"탈옥\s*(?:모드|해줘|시켜|프롬프트|상태)|무제한\s*모드|검열\s*(?:없이|해제)|"
            r"without\s+(?:any\s+)?(?:restrictions|filters|censorship)"
        ),
        tier=GuardTier.BLOCK,
    ),
    # ── 역할 탈취 (REVIEW — Design D1) ──────────────────────────────────
    GuardRule(
        id="ko.role.01", category=RuleCategory.ROLE_HIJACK, lang="ko",
        pattern=r"(?:너|당신|넌|니)\s*(?:는|은)?\s*(?:이제|지금부터|오늘부터)",
        tier=GuardTier.REVIEW,
    ),
    GuardRule(
        id="en.role.01", category=RuleCategory.ROLE_HIJACK, lang="en",
        pattern=(
            r"you\s+are\s+now|from\s+now\s+on\s+you|"
            r"pretend\s+(?:to\s+be|you\s+are|that\s+you)|"
            r"act\s+as\s+(?:if|a|an|my)|roleplay\s+as"
        ),
        tier=GuardTier.REVIEW,
    ),
    # ── 약한 신호 (REVIEW) ──────────────────────────────────────────────
    GuardRule(
        id="ko.soft.01", category=RuleCategory.SOFT_SIGNAL, lang="ko",
        pattern=r"무\s*시|잊어|잊고|신경\s*쓰지",
        tier=GuardTier.REVIEW,
    ),
    GuardRule(
        id="ko.soft.02", category=RuleCategory.SOFT_SIGNAL, lang="ko",
        pattern=(
            r"(?:규칙|제한|설정|지침)\s*(?:을|를|들을)?\s*"
            r"(?:바꿔|변경|수정|풀어|없애|해제)"
        ),
        tier=GuardTier.REVIEW,
    ),
    GuardRule(
        id="ko.leak.02", category=RuleCategory.PROMPT_LEAK, lang="ko",
        pattern=(
            r"(?:너의|네|니|당신의)\s*(?:지시사항|지시|규칙|설정)\s*(?:을|를)?"
            r"[^\n]{0,10}?(?:보여|알려|공개|출력|말해)"
        ),
        tier=GuardTier.REVIEW,
    ),
    GuardRule(
        id="en.soft.01", category=RuleCategory.SOFT_SIGNAL, lang="en",
        pattern=(
            r"new\s+instructions?|"
            r"your\s+(?:rules|restrictions|guidelines|instructions)|"
            r"\bignore\b|disregard|(?:previous|prior)\s+instructions?"
        ),
        tier=GuardTier.REVIEW,
    ),
)
