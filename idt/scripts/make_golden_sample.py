"""테스트용 Golden Sample PDF 생성기 (golden-sample-blueprint 수동 검증용).

실행: .venv/Scripts/python scripts/make_golden_sample.py [출력경로]
구성(16:9, 6p): 표지(전면 남색 배경+로고+제목) / 목차 / 섹션 리드 / 차트+해설(막대·선 도형) /
표 / 결론. 로고·푸터·페이지 번호는 2~6p 반복. 폰트: 맑은 고딕(Windows).
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz

W, H = 960.0, 540.0
NAVY = (0x1F / 255, 0x3A / 255, 0x5F / 255)
ORANGE = (0xE0 / 255, 0x7A / 255, 0x1F / 255)
TEAL = (0x2A / 255, 0x9D / 255, 0x8F / 255)
GRAY = (0x66 / 255, 0x66 / 255, 0x66 / 255)
LIGHT = (0xF3 / 255, 0xF4 / 255, 0xF6 / 255)
TEXT = (0x22 / 255, 0x22 / 255, 0x22 / 255)
WHITE = (1, 1, 1)

FONT = "C:/Windows/Fonts/malgun.ttf"
FONT_BOLD = "C:/Windows/Fonts/malgunbd.ttf"


def _png_rect(w: int, h: int, color: tuple[int, int, int]) -> bytes:
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h), False)
    pix.clear_with(0)
    for x in range(w):
        for y in range(h):
            pix.set_pixel(x, y, color)
    return pix.tobytes("png")


def _logo_png() -> bytes:
    """주황 사각 + 흰 띠 — 단색 아이콘보다 로고답게."""
    w, h = 180, 60
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, w, h), False)
    for x in range(w):
        for y in range(h):
            on_band = 22 <= y <= 38 and 20 <= x <= 160
            pix.set_pixel(x, y, (255, 255, 255) if on_band else (0xE0, 0x7A, 0x1F))
    return pix.tobytes("png")


LOGO = _logo_png()
COVER_BG = _png_rect(192, 108, (0x1F, 0x3A, 0x5F))


class Deck:
    def __init__(self) -> None:
        self.doc = fitz.open()
        self.n = 0

    def page(self) -> fitz.Page:
        self.n += 1
        return self.doc.new_page(width=W, height=H)

    def text(self, page, xy, s, size=14, color=TEXT, bold=False, width=None):
        font = FONT_BOLD if bold else FONT
        name = "malgunbd" if bold else "malgun"  # 별칭 분리 — 굵기 구분·중복 임베딩 방지
        if width:
            rect = fitz.Rect(xy[0], xy[1] - size, xy[0] + width, xy[1] + size * 6)
            page.insert_textbox(
                rect, s, fontsize=size, fontfile=font, fontname=name, color=color
            )
        else:
            page.insert_text(
                xy, s, fontsize=size, fontfile=font, fontname=name, color=color
            )

    def chrome(self, page, title: str, total: int):
        """제목 바 + 로고 + 푸터 + 페이지 번호 (표지 제외 공통)."""
        page.insert_image(fitz.Rect(800, 22, 920, 62), stream=LOGO)
        self.text(page, (60, 70), title, 24, NAVY, bold=True)
        sh = page.new_shape()
        sh.draw_line((60, 84), (900, 84))
        sh.finish(color=NAVY, width=2)
        sh.draw_rect(fitz.Rect(0, 500, W, H))
        sh.finish(fill=LIGHT, color=None)
        sh.commit()
        self.text(page, (60, 525), "여신심사부 · 대외비 · 2026년 3분기", 10, GRAY)
        self.text(page, (880, 525), f"{self.n} / {total}", 10, GRAY)


def build(out: Path) -> None:
    d = Deck()
    total = 6

    # 1 표지
    p = d.page()
    p.insert_image(fitz.Rect(0, 0, W, H), stream=COVER_BG)
    p.insert_image(fitz.Rect(60, 40, 240, 100), stream=LOGO)
    d.text(p, (60, 250), "2026년 3분기 여신 리스크 보고", 34, WHITE, bold=True)
    d.text(p, (60, 300), "연체율 추이와 포트폴리오 건전성 점검", 18, WHITE)
    d.text(p, (60, 470), "여신심사부  |  2026. 08. 22", 13, WHITE)

    # 2 목차
    p = d.page()
    d.chrome(p, "목차", total)
    for i, line in enumerate(
        ["1. 요약 및 핵심 메시지", "2. 연체율 추이 분석", "3. 포트폴리오 현황", "4. 향후 대응 방안"]
    ):
        d.text(p, (100, 150 + i * 50), line, 16)
        sh = p.new_shape()
        sh.draw_line((100, 160 + i * 50), (860, 160 + i * 50))
        sh.finish(color=(0.85, 0.85, 0.85), width=0.5)
        sh.commit()

    # 3 섹션 리드
    p = d.page()
    d.chrome(p, "1. 요약 및 핵심 메시지", total)
    sh = p.new_shape()
    sh.draw_rect(fitz.Rect(60, 120, 900, 200))
    sh.finish(fill=LIGHT, color=None)
    sh.draw_rect(fitz.Rect(60, 120, 68, 200))
    sh.finish(fill=ORANGE, color=None)
    sh.commit()
    d.text(p, (90, 150), "3분기 연체율은 1.52%로 전분기 대비 0.31%p 상승했으며, 상승분의 78%는 중소기업 부문에서 발생했습니다.", 14, TEXT, width=790)
    for i, b in enumerate([
        "■ 가계 부문은 0.98%로 안정적 (전분기 대비 +0.02%p)",
        "■ 중소기업 부문 2.41% — 제조·도소매 업종 집중",
        "■ 신규 취급 심사 기준 강화 및 조기경보 대상 확대 필요",
    ]):
        d.text(p, (90, 250 + i * 36), b, 14)

    # 4 차트 + 해설 (막대 + 선 도형)
    p = d.page()
    d.chrome(p, "2. 연체율 추이 분석", total)
    quarters = ["'25 3Q", "'25 4Q", "'26 1Q", "'26 2Q", "'26 3Q"]
    sme = [1.62, 1.71, 1.95, 2.08, 2.41]
    house = [0.91, 0.93, 0.95, 0.96, 0.98]
    x0, y0, cw, ch = 90, 130, 480, 320  # 차트 영역
    sh = p.new_shape()
    sh.draw_rect(fitz.Rect(x0, y0, x0 + cw, y0 + ch))
    sh.finish(color=(0.8, 0.8, 0.8), width=0.5)
    for g in range(6):  # 격자 0~3.0%
        y = y0 + ch - g * ch / 5
        sh.draw_line((x0, y), (x0 + cw, y))
        sh.finish(color=(0.9, 0.9, 0.9), width=0.5)
    sh.commit()
    for g in range(6):
        d.text(p, (x0 - 32, y0 + ch - g * ch / 5 + 4), f"{g * 0.6:.1f}%", 9, GRAY)
    slot = cw / len(quarters)
    pts = []
    for i, (q, v, hv) in enumerate(zip(quarters, sme, house, strict=True)):
        bx = x0 + i * slot + slot * 0.25
        bh = v / 3.0 * ch
        sh = p.new_shape()
        sh.draw_rect(fitz.Rect(bx, y0 + ch - bh, bx + slot * 0.5, y0 + ch))
        sh.finish(fill=NAVY, color=None)
        sh.commit()
        d.text(p, (bx + 4, y0 + ch - bh - 6), f"{v:.2f}", 9, NAVY, bold=True)
        d.text(p, (bx - 4, y0 + ch + 16), q, 10, GRAY)
        pts.append((bx + slot * 0.25, y0 + ch - hv / 3.0 * ch))
    sh = p.new_shape()
    for a, b in zip(pts, pts[1:], strict=False):
        sh.draw_line(a, b)
    sh.finish(color=ORANGE, width=2.5)
    for pt in pts:
        sh.draw_circle(pt, 4)
    sh.finish(fill=ORANGE, color=None)
    sh.commit()
    # 범례
    sh = p.new_shape()
    sh.draw_rect(fitz.Rect(x0, 470, x0 + 14, 482))
    sh.finish(fill=NAVY, color=None)
    sh.draw_line((x0 + 110, 476), (x0 + 130, 476))
    sh.finish(color=ORANGE, width=2.5)
    sh.commit()
    d.text(p, (x0 + 20, 480), "중소기업 연체율", 10, GRAY)
    d.text(p, (x0 + 136, 480), "가계 연체율", 10, GRAY)
    # 해설
    d.text(p, (610, 140), "핵심 관찰", 16, NAVY, bold=True)
    for i, b in enumerate([
        "• 중소기업 연체율 5분기 연속 상승 (1.62% → 2.41%)",
        "• 3Q 상승폭 +0.33%p는 최근 2년 내 최대",
        "• 가계 부문은 1% 미만 유지, 변동성 낮음",
        "• 제조업(2.9%)·도소매(2.7%)가 부문 평균을 상회",
    ]):
        d.text(p, (610, 180 + i * 52), b, 13, TEXT, width=280)

    # 5 표
    p = d.page()
    d.chrome(p, "3. 포트폴리오 현황", total)
    header = ["구분", "잔액(억원)", "비중", "연체율", "전분기 대비"]
    rows = [
        ["가계", "12,480", "41.6%", "0.98%", "+0.02%p"],
        ["중소기업", "9,870", "32.9%", "2.41%", "+0.33%p"],
        ["대기업", "5,620", "18.7%", "0.12%", "-0.01%p"],
        ["기타", "2,030", "6.8%", "1.05%", "+0.08%p"],
        ["합계", "30,000", "100%", "1.52%", "+0.31%p"],
    ]
    tx, ty, colw, rh = 60, 120, 168, 44
    sh = p.new_shape()
    sh.draw_rect(fitz.Rect(tx, ty, tx + colw * 5, ty + rh))
    sh.finish(fill=NAVY, color=None)
    for r in range(1, len(rows) + 1):
        if r % 2 == 0:
            sh.draw_rect(fitz.Rect(tx, ty + r * rh, tx + colw * 5, ty + (r + 1) * rh))
            sh.finish(fill=LIGHT, color=None)
    for r in range(len(rows) + 2):
        sh.draw_line((tx, ty + r * rh), (tx + colw * 5, ty + r * rh))
    for c in range(6):
        sh.draw_line((tx + c * colw, ty), (tx + c * colw, ty + (len(rows) + 1) * rh))
    sh.finish(color=(0.8, 0.8, 0.8), width=0.5)
    sh.commit()
    for c, hd in enumerate(header):
        d.text(p, (tx + c * colw + 12, ty + 28), hd, 13, WHITE, bold=True)
    for r, row in enumerate(rows, start=1):
        bold = row[0] == "합계"
        for c, cell in enumerate(row):
            d.text(p, (tx + c * colw + 12, ty + r * rh + 28), cell, 13, TEXT, bold=bold)
    d.text(p, (60, 420), "※ 잔액은 2026. 8. 20 기준, 연체율은 30일 이상 연체 기준", 10, GRAY)

    # 6 결론
    p = d.page()
    d.chrome(p, "4. 향후 대응 방안", total)
    for i, (t, body) in enumerate([
        ("심사 기준 강화", "제조·도소매 업종 신규 취급 시 매출 감소율 20% 이상 건 본부 심사로 상향"),
        ("조기경보 확대", "연체 15일 이상 중소기업 차주에 대해 월 1회 → 격주 모니터링"),
        ("한도 관리", "부문 한도 소진율 85% 초과 시 신규 승인 중단 및 위원회 보고"),
    ]):
        y = 130 + i * 110
        sh = p.new_shape()
        sh.draw_rect(fitz.Rect(60, y, 900, y + 90))
        sh.finish(fill=LIGHT, color=None)
        sh.draw_rect(fitz.Rect(60, y, 68, y + 90))
        sh.finish(fill=TEAL, color=None)
        sh.commit()
        d.text(p, (90, y + 30), t, 15, NAVY, bold=True)
        d.text(p, (90, y + 62), body, 13, TEXT, width=780)

    out.parent.mkdir(parents=True, exist_ok=True)
    d.doc.subset_fonts()
    d.doc.save(out, garbage=4, deflate=True)
    d.doc.close()


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("samples/golden_sample_report.pdf")
    build(target)
    print(target.resolve())
