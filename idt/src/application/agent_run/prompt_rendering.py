"""LLM 시스템 프롬프트에 prepend되는 사용자 컨텍스트 블록 렌더링.

agent-user-context Design §4.3:
- whitelist: AuthContext의 명시된 필드만 사용
- 절대 금지: employee_no, email, password_hash, user_id(숫자) 노출

supervisor-overblock-fix D1/D2:
- 권한 목록('허용된 정보 영역') 미노출 — 목록이 있으면 LLM이 자체 권한 심사를
  수행해 워커 라우팅 전에 요청을 거부(과차단)하는 실증이 있었음.
  권한 검증·필터링은 도구 3단 방어(USE_RAG_SEARCH 차단 + visibility 필터)가 담당.
- 심사 위임 가드 문구로 교체: 거부·차단 금지 + 미검색 정보는 '확인되지 않습니다'.
"""
from datetime import UTC, datetime

from src.application.wiki.schemas import WikiTreeItem
from src.domain.agent_run.auth_context import AuthContext
from src.domain.agent_run.clock import to_local, weekday_ko
from src.domain.logging.interfaces.logger_interface import LoggerInterface

_ANONYMOUS_BLOCK = ""  # 미인증 시 prepend 생략

# runtime-datetime-context D1 §4.2: 사실(날짜+요일) + 해석 지침 3줄.
# 시각(HH:MM) 미포함 — 하루 단위로만 변해 프롬프트 캐시 프리픽스가 안정적이다.
# 게이트 어휘(거부/차단/권한) 금지 — supervisor-overblock-fix 교훈.
_DATETIME_GUIDE = (
    "'오늘', '최근', '최신', '이번 주/이번 달' 같은 표현은 "
    "위 날짜를 기준으로 해석하세요.\n"
    "웹 검색이 필요하면 검색어에 위 날짜(연-월-일)를 포함하세요.\n"
    "검색 결과나 문서의 날짜가 위 날짜와 다르면 그 날짜를 답변에 함께 밝히세요.\n"
)


def render_datetime_block(
    tz: str | None,
    now_utc: datetime | None = None,
    logger: LoggerInterface | None = None,
) -> str:
    """`[현재 날짜]` 블록 렌더링 — 런타임 시스템 프롬프트 prepend용.

    Design Ref: runtime-datetime-context §D1.

    Args:
        tz: IANA 타임존. None이면 미배선(opt-out)으로 보고 '' 반환 (로그 없음).
        now_utc: 기준 시각(테스트 결정성). None이면 현재 UTC.
        logger: 렌더 실패 시 warning 기록. None이면 조용히 '' 반환.

    Returns:
        블록 텍스트(끝에 '\\n---\\n\\n' 구분자) 또는 ''. 잘못된 tz 등 실패는
        degraded('' + warning) — 날짜 없이도 답변은 가능하므로 실행을
        중단하지 않는다 (FR-11).
    """
    if tz is None:
        return ""
    try:
        local = to_local(now_utc or datetime.now(UTC), tz)
    except Exception as e:  # ZoneInfoNotFoundError 등
        if logger is not None:
            logger.warning("datetime block render failed", tz=tz, exception=e)
        return ""
    return (
        "[현재 날짜]\n"
        f"- {local.strftime('%Y-%m-%d')} ({weekday_ko(local.date())})\n\n"
        f"{_DATETIME_GUIDE}"
        "\n---\n\n"
    )


# worker-context-injection §4.1: 워커 system_prompt에 주입할 에이전트 지침의
# 문자 수 상한. 초과분은 절단하고 생략 사실을 LLM에 알린다 (토큰 폭증 방지).
MAX_AGENT_PROMPT_CHARS = 2000

# §4.1 소프트 가드 — 근거 없는 도구 인자 합성을 막는 지침. 다른 절이 모두
# 비어도 항상 포함된다(도구를 가진 워커에는 언제나 유효한 규범이므로).
_TOOL_USAGE_NORM = (
    "[도구 사용 규범]\n"
    "도구 인자로 URL·식별자·날짜를 추측해서 만들지 마세요.\n"
    "대화 내용, 이전 단계 결과, 이전 도구 응답에 근거가 없으면 도구를 호출하지 말고\n"
    "무엇이 확인되지 않았는지 답변에 밝히세요.\n"
    "데이터를 정재만 할뿐 어떠한 작업을 하지 마세요. 상위에서 노드에서 이를 책임집니다.\n"
)


def render_worker_context_block(
    agent_prompt: str | None,
    worker_description: str | None,
    tool_names: list[str] | None,
    include_tool_norm: bool = True,
) -> str:
    """워커 react agent의 system_prompt에 prepend할 컨텍스트 블록.

    Design Ref: worker-context-injection §4.1.

    supervisor만 에이전트 시스템 프롬프트를 보고 워커는 보지 못하던 유실을
    메운다. 워커는 이 블록으로 '어떤 에이전트의 어떤 역할'인지 알게 된다.

    Args:
        agent_prompt: 에이전트 시스템 프롬프트. 비면 해당 절 생략.
        worker_description: 워커 역할 설명. 비면 해당 절 생략.
        tool_names: 워커에 바인딩된 도구 이름. 비면 해당 절 생략.
        include_tool_norm: 도구 사용 규범 포함 여부. 도구를 직접 호출하지 않는
            노드(analysis 등)는 False — 무관한 지침이 프롬프트를 오염시키지 않도록.

    Returns:
        블록 텍스트(끝에 '\\n---\\n\\n' 구분자). 담을 절이 하나도 없으면 ''
        (규범을 끄고 프롬프트·역할도 비면 미배선으로 보고 기존 동작 보존).
    """
    sections: list[str] = []

    prompt = (agent_prompt or "").strip()
    if prompt:
        sections.append(f"[에이전트 지침]\n{_truncate_prompt(prompt)}\n")

    description = (worker_description or "").strip()
    if description:
        sections.append(f"[당신의 역할]\n{description}\n")

    names = [n for n in (tool_names or []) if n]
    if names:
        listed = "\n".join(f"- {name}" for name in names)
        sections.append(f"[사용 가능한 도구]\n{listed}\n")

    if include_tool_norm:
        sections.append(_TOOL_USAGE_NORM)
    if not sections:
        return ""
    return "\n".join(sections) + "\n---\n\n"


def _truncate_prompt(prompt: str) -> str:
    """상한 초과 시 절단하고 생략 사실을 명시한다 (§4.1)."""
    if len(prompt) <= MAX_AGENT_PROMPT_CHARS:
        return prompt
    return prompt[:MAX_AGENT_PROMPT_CHARS] + "\n…(에이전트 지침 일부 생략)"


def render_user_context_block(ctx: AuthContext | None) -> str:
    """사용자 컨텍스트 블록 한국어 텍스트 생성.

    Args:
        ctx: 현재 사용자 AuthContext. None이거나 role='anonymous'면 빈 문자열.

    Returns:
        prepend용 텍스트 (블록 끝에 '\\n---\\n\\n' 구분자 포함). 미인증이면 ''.

    절대 노출 금지 필드 (whitelist로 강제):
        - user_id (숫자) — 사용자 식별 누설
        - employee_no — 사번 누설
        - email — 이메일 누설
        - tenant_id 같은 메타데이터
        - permissions — 권한 목록 노출 시 LLM 자체 심사 유발 (supervisor-overblock-fix D1)
    """
    if ctx is None or ctx.role == "anonymous":
        return _ANONYMOUS_BLOCK

    role_ko = "관리자" if ctx.role == "admin" else "일반 사용자"
    dept_line = (
        f"- 부서: {ctx.primary_department_name}"
        if ctx.primary_department_name
        else "- 부서: (미배정)"
    )

    return (
        "[현재 사용자 정보]\n"
        f"- 이름: {ctx.display_name}\n"
        f"{dept_line}\n"
        f"- 역할: {role_ko}\n\n"
        "사용자가 '나', '내', '본인'이라고 말하면 위 사용자를 의미합니다.\n\n"
        "정보 접근 권한은 각 도구가 자동으로 검증하고 필터링합니다.\n"
        "권한이나 개인정보 보호를 이유로 요청을 거부하거나 차단하지 마세요.\n"
        "도구의 검색 결과에 없는 내용은 '확인되지 않습니다'라고 답하세요.\n"
        "\n---\n\n"
    )


_TOC_HEADER = (
    "[에이전트 지식 위키 목차]\n"
    "이 에이전트가 보유한 승인 지식 문서 목록입니다 (최신 갱신순).\n"
    "문서의 상세 내용이 필요하면 wiki_read 도구에 아래 id를 전달해 본문을 열람하세요.\n"
    "목차만으로 답하지 말고, 인용이 필요하면 반드시 본문을 열람한 뒤 답하세요.\n\n"
)
_TOC_FOOTER = "---\n\n"


def _toc_line(item: WikiTreeItem) -> str:
    updated = item.updated_at.strftime("%Y-%m-%d") if item.updated_at else "-"
    location = f"{item.path}/{item.title}" if item.path else item.title
    return f"- (id: {item.id}) {location} — 갱신 {updated}\n"


def render_wiki_toc_block(
    items: list[WikiTreeItem], max_items: int, max_bytes: int
) -> str:
    """승인 위키 목차 블록 렌더링 (wiki-agentic-navigation FR-03/FR-04).

    Args:
        items: 승인+미만료 목차 항목 (updated_at 내림차순 전제 — repo가 보장).
        max_items: 표시 상한 건수. 초과분은 뒤에서부터 절단.
        max_bytes: 목록부 UTF-8 바이트 상한. 초과 시 뒤에서부터 줄 단위 절단.

    Returns:
        prepend용 텍스트 (말미 '---' 구분자). items가 비면 '' (FR-04).
    """
    if not items:
        return ""

    total = len(items)
    shown = items[:max_items]

    lines: list[str] = []
    used = 0
    for item in shown:
        line = _toc_line(item)
        line_bytes = len(line.encode("utf-8"))
        if used + line_bytes > max_bytes:
            break
        lines.append(line)
        used += line_bytes

    if not lines:
        # 상한이 극단적으로 작아 한 줄도 못 담는 경우 — 블록 자체 생략
        return ""

    notice = (
        f"\n(전체 {total}건 중 {len(lines)}건 표시 — 이후 생략)\n"
        if len(lines) < total
        else "\n"
    )
    return _TOC_HEADER + "".join(lines) + notice + _TOC_FOOTER


# wiki-folder-summaries D5: 폴더 모드 지도 블록.
# 헤더 태그는 compiler가 모드 판별에 사용한다(문자열 계약 — 변경 시 compiler 동기 수정).
WIKI_FOLDER_HEADER_TAG = "[에이전트 지식 위키 지도]"

_FOLDER_HEADER = (
    f"{WIKI_FOLDER_HEADER_TAG}\n"
    "이 에이전트의 승인 지식은 아래 폴더로 정리되어 있습니다.\n"
    "관련 폴더를 wiki_list 도구로 열어 문서 목록을 확인하고, "
    "문서는 wiki_read 도구로 본문을 열람하세요.\n"
    "지도만으로 답하지 말고, 인용이 필요하면 반드시 본문을 열람한 뒤 답하세요.\n\n"
)


def _folder_line(folder) -> str:
    return f"- {folder.path} — {folder.summary} ({folder.article_count}건)\n"


def render_wiki_folder_block(
    top_folders: list, uncategorized_count: int, max_bytes: int
) -> str:
    """폴더 지도 블록 렌더링 (wiki-folder-summaries FR-04).

    Args:
        top_folders: 최상위(1세그먼트) 폴더 요약 목록 (path 오름차순 전제).
        uncategorized_count: path=None 승인 문서 수 — 0이면 안내줄 생략.
        max_bytes: 목록부 UTF-8 바이트 상한. 초과 시 뒤에서부터 줄 단위 절단.

    Returns:
        prepend용 텍스트 (말미 '---' 구분자). 표시할 것이 없으면 ''.
    """
    if not top_folders and uncategorized_count <= 0:
        return ""

    total = len(top_folders)
    lines: list[str] = []
    used = 0
    for folder in top_folders:
        line = _folder_line(folder)
        line_bytes = len(line.encode("utf-8"))
        if used + line_bytes > max_bytes:
            break
        lines.append(line)
        used += line_bytes

    if not lines and uncategorized_count <= 0:
        return ""

    if uncategorized_count > 0:
        lines.append(
            f"- (미분류) — 폴더 미지정 문서 {uncategorized_count}건 "
            '(wiki_list 경로 "" 로 조회)\n'
        )

    notice = (
        f"\n(전체 폴더 {total}개 중 {min(len(lines), total)}개 표시 — 이후 생략)\n"
        if len([l for l in lines if not l.startswith("- (미분류)")]) < total
        else "\n"
    )
    return _FOLDER_HEADER + "".join(lines) + notice + _TOC_FOOTER
