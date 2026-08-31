"""run 폰트 3슬롯 설정 (pptx-font-fidelity §12.1 / FR-02).

python-pptx 의 `run.font.name` 은 `<a:latin>` 만 설정한다. 한글 글리프는 East
Asian 타입페이스(`<a:ea>`)를 따르므로, 이를 비워 두면 지정 폰트가 한글에
적용되지 않고 테마 기본값으로 폴백해 문서 전체가 다른 서체로 보인다.
python-pptx 에 ea/cs 설정 API 가 없어 oxml 을 직접 다루는 유일한 지점이며,
네임스페이스는 매직 문자열 대신 `pptx.oxml.ns.qn` 으로만 표기한다.
"""

from __future__ import annotations

from pptx.oxml.ns import qn

_EAST_ASIAN_SLOTS = ("a:ea", "a:cs")


def set_run_font(run, name: str) -> None:
    """run 의 latin·ea·cs 타입페이스를 같은 폰트로 맞춘다. 빈 이름은 무시."""
    if not name:
        return
    run.font.name = name  # <a:latin>
    rpr = run._r.get_or_add_rPr()
    for tag in _EAST_ASIAN_SLOTS:
        element = rpr.find(qn(tag))
        if element is None:
            element = rpr.makeelement(qn(tag), {})
            rpr.append(element)
        element.set("typeface", name)
