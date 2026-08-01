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
from src.application.wiki.schemas import WikiTreeItem
from src.domain.agent_run.auth_context import AuthContext

_ANONYMOUS_BLOCK = ""  # 미인증 시 prepend 생략


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
