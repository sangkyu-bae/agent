"""LLM 시스템 프롬프트에 prepend되는 사용자 컨텍스트 블록 렌더링.

agent-user-context Design §4.3:
- whitelist: AuthContext의 명시된 필드만 사용
- 절대 금지: employee_no, email, password_hash, user_id(숫자) 노출
- 권한은 한국어 라벨로 변환 (PermissionCode.label_ko)
- LLM이 자체 차단 판단을 하지 않도록 "도구가 자동으로 제외합니다" 문구 강제
"""
from src.domain.agent_run.auth_context import AuthContext
from src.domain.permission.value_objects import PermissionCode


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
    """
    if ctx is None or ctx.role == "anonymous":
        return _ANONYMOUS_BLOCK

    role_ko = "관리자" if ctx.role == "admin" else "일반 사용자"
    dept_line = (
        f"- 부서: {ctx.primary_department_name}"
        if ctx.primary_department_name
        else "- 부서: (미배정)"
    )

    perm_labels: list[str] = []
    for code in sorted(ctx.permissions):  # 결정적 순서 — 스냅샷 테스트 안정성
        try:
            perm_labels.append(f"- {PermissionCode(code).label_ko}")
        except ValueError:
            # DB seed와 enum 불일치 시 graceful skip — 운영 중 라벨 누락 방어
            continue
    perm_block = "\n".join(perm_labels) if perm_labels else "- (권한 없음)"

    return (
        "[현재 사용자 정보]\n"
        f"- 이름: {ctx.display_name}\n"
        f"{dept_line}\n"
        f"- 역할: {role_ko}\n\n"
        "사용자가 '나', '내', '본인'이라고 말하면 위 사용자를 의미합니다.\n\n"
        "[허용된 정보 영역]\n"
        f"{perm_block}\n\n"
        "⚠️ 권한이 없는 정보는 도구가 자동으로 제외합니다.\n"
        "도구의 검색 결과에 없는 내용은 '확인되지 않습니다'라고 답하세요.\n"
        "권한 여부를 직접 판단해서 차단하지 말고, 검색된 사실만 답변하세요.\n"
        "\n---\n\n"
    )
