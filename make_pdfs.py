"""
units.json dagi so'z jadvallaridan namuna uslubidagi PDF lar yaratadi.

Ishlatish:
    python make_pdfs.py            # 3-4, 5-6, 7-8, 9-10 unitlar (standart)
    python make_pdfs.py 11 12      # faqat 11 va 12 unitlar uchun bitta PDF

Kerak: pip install reportlab font-roboto
"""
import json
import math
import os
import sys

import font_roboto
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "pdfs")
FONT_DIR = os.path.join(os.path.dirname(font_roboto.__file__), "files")
pdfmetrics.registerFont(TTFont("Roboto", os.path.join(FONT_DIR, "Roboto-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Roboto-Bold", os.path.join(FONT_DIR, "Roboto-Bold.ttf")))

W, H = 595.92, 842.88

TEAL = HexColor("#0f766e")
TEAL_BG = HexColor("#f0fdfa")
TEAL_SOFT = HexColor("#99f6e4")
INK = HexColor("#0f172a")
GREEN = HexColor("#047857")
GRAY = HexColor("#64748b")
HEAD_BG = HexColor("#f1f5f9")
ZEBRA = HexColor("#f8fafc")
LINE = HexColor("#e2e8f0")
LINE_HEAD = HexColor("#cbd5e1")

X0, XM, X1 = 51.8, 288.0, 544.5
TABLE_TOP = 110.2
HEADER_H = 20.3
ROW_H = 21.75
BOTTOM_LIMIT = 782.0
TITLE = "OWNER BY BOSITXONOV7"

DEFAULT_GROUPS = [[3, 4], [5, 6], [7, 8], [9, 10]]


def y(top):
    """Yuqoridan o'lchangan koordinatani reportlab koordinatasiga o'giradi."""
    return H - top


def wrap(text, font, size, width):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(trial, font, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit(text, font, size, width, min_size=8.5):
    """Matnni sig'dirish uchun shriftni kichraytiradi, bo'lmasa qatorlarga bo'ladi."""
    s = size
    while s > min_size and pdfmetrics.stringWidth(text, font, s) > width:
        s -= 0.25
    if pdfmetrics.stringWidth(text, font, s) <= width:
        return s, [text]
    return min_size, wrap(text, font, min_size, width)


def layout_rows(rows):
    laid = []
    for en, uz in rows:
        s_en, l_en = fit(en, "Roboto-Bold", 11, XM - 60.8 - 8)
        s_uz, l_uz = fit(uz, "Roboto-Bold", 10.5, X1 - 297.6 - 8)
        n = max(len(l_en), len(l_uz))
        laid.append({"en": (s_en, l_en), "uz": (s_uz, l_uz), "h": ROW_H + (n - 1) * 12})
    return laid


def paginate(laid):
    first_row_top = TABLE_TOP + HEADER_H
    avail = BOTTOM_LIMIT - first_row_top
    pages, cur, cur_h = [], [], 0.0
    for r in laid:
        if cur and cur_h + r["h"] > avail:
            pages.append(cur)
            cur, cur_h = [], 0.0
        cur.append(r)
        cur_h += r["h"]
    pages.append(cur)
    return pages


def draw_page_frame(c, unit_title, book, unit_no, page_no):
    # Yuqori sarlavha qutisi
    c.setFillColor(TEAL_BG)
    c.setStrokeColor(TEAL)
    c.setLineWidth(1.5)
    c.roundRect(51.7, y(66.8), 544.5 - 51.7, 66.8 - 37.5, 8, fill=1, stroke=1)
    c.setFillColor(TEAL)
    base_w = pdfmetrics.stringWidth(TITLE, "Roboto-Bold", 16)
    cs = (219.9 - base_w) / (len(TITLE) - 1)
    c.saveState()  # harflar orasidagi masofa faqat shu sarlavhaga tegishli
    t = c.beginText()
    t.setFont("Roboto-Bold", 16)
    t.setCharSpace(cs)
    t.setTextOrigin(187.4, y(57.8))
    t.textOut(TITLE)
    c.drawText(t)
    c.restoreState()

    # Unit nomi, belgi va chiziq
    c.setFillColor(TEAL)
    c.setFont("Roboto-Bold", 18)
    c.drawString(51.0, y(91.5), unit_title)
    c.setFillColor(TEAL_BG)
    c.setStrokeColor(TEAL_SOFT)
    c.setLineWidth(0.75)
    c.roundRect(469.1, y(94.1), 75.8, 16.5, 8.25, fill=1, stroke=1)
    c.setFillColor(TEAL)
    c.setFont("Roboto-Bold", 9.5)
    c.drawString(477.2, y(89.25), "So'z & Tarjima")
    c.rect(51.0, y(102.0), 545.2 - 51.0, 1.5, fill=1, stroke=0)

    # Jadval sarlavhasi
    c.setFillColor(HEAD_BG)
    c.rect(X0, y(TABLE_TOP + HEADER_H), X1 - X0, HEADER_H, fill=1, stroke=0)
    c.setFillColor(LINE_HEAD)
    c.rect(51.0, y(TABLE_TOP), 545.2 - 51.0, 0.7, fill=1, stroke=0)
    c.rect(51.0, y(TABLE_TOP + HEADER_H), 0.8, HEADER_H, fill=1, stroke=0)
    c.rect(XM, y(TABLE_TOP + HEADER_H), 0.8, HEADER_H, fill=1, stroke=0)
    c.rect(X1, y(TABLE_TOP + HEADER_H), 0.7, HEADER_H, fill=1, stroke=0)
    c.setFillColor(INK)
    c.setFont("Roboto-Bold", 10)
    c.drawString(60.8, y(123.75), "Inglizcha so'z / ibora")
    c.drawString(297.6, y(123.75), "O'zbekcha tarjimasi")

    # Pastki qism
    c.setFillColor(LINE_HEAD)
    c.rect(51.0, y(790.8), 545.2 - 51.0, 0.75, fill=1, stroke=0)
    c.setFillColor(GRAY)
    c.setFont("Roboto", 8.5)
    c.drawString(51.0, y(808.5), book)
    c.drawRightString(545.2, y(808.5), f"Unit {unit_no} • Sahifa {page_no}")


def draw_rows(c, rows):
    top = TABLE_TOP + HEADER_H
    for i, r in enumerate(rows):
        h = r["h"]
        if i % 2 == 1:
            c.setFillColor(ZEBRA)
            c.rect(X0, y(top + h), X1 - X0, h, fill=1, stroke=0)
        c.setFillColor(LINE)
        c.rect(51.0, y(top + h), 0.8, h, fill=1, stroke=0)
        c.rect(XM, y(top + h), 0.8, h, fill=1, stroke=0)
        c.rect(X1, y(top + h), 0.7, h, fill=1, stroke=0)
        c.rect(51.0, y(top + h), 545.2 - 51.0, 0.7, fill=1, stroke=0)
        s_en, l_en = r["en"]
        s_uz, l_uz = r["uz"]
        c.setFillColor(INK)
        c.setFont("Roboto-Bold", s_en)
        for k, line in enumerate(l_en):
            c.drawString(60.8, y(top + 14.3 + k * 12), line)
        c.setFillColor(GREEN)
        c.setFont("Roboto-Bold", s_uz)
        for k, line in enumerate(l_uz):
            c.drawString(297.6, y(top + 14.3 + k * 12), line)
        top += h


def build(unit_numbers, data, out_path):
    book = data["book"]
    c = canvas.Canvas(out_path, pagesize=(W, H))
    c.setTitle("Vocabulary Units " + " and ".join(str(n) for n in unit_numbers))
    c.setAuthor("bositxonov7")
    page_no = 0
    for n in unit_numbers:
        unit = data["units"][str(n)]
        pages = paginate(layout_rows(unit["rows"]))
        for idx, rows in enumerate(pages):
            page_no += 1
            suffix = " (davomi)" if idx > 0 else ""
            draw_page_frame(c, f"Unit {n}: {unit['title']}{suffix}", book, n, page_no)
            draw_rows(c, rows)
            c.showPage()
    c.save()


def get_all_groups(data):
    unit_nums = sorted([int(k) for k in data["units"].keys()])
    groups = []
    i = 0
    while i < len(unit_nums):
        if i + 1 < len(unit_nums) and unit_nums[i + 1] == unit_nums[i] + 1:
            groups.append([unit_nums[i], unit_nums[i + 1]])
            i += 2
        else:
            groups.append([unit_nums[i]])
            i += 1
    return groups


def main():
    with open(os.path.join(BASE, "units.json"), encoding="utf-8") as f:
        data = json.load(f)
    os.makedirs(OUT_DIR, exist_ok=True)
    if len(sys.argv) > 1:
        if sys.argv[1] in ("--all", "all"):
            groups = get_all_groups(data)
        else:
            groups = [[int(a) for a in sys.argv[1:]]]
    else:
        # Default: barcha guruhlarni yaratish
        groups = get_all_groups(data)

    for g in groups:
        name = "Vocabulary_Units_" + "_and_".join(str(n) for n in g) + ".pdf"
        out = os.path.join(OUT_DIR, name)
        build(g, data, out)
        print("yaratildi:", out)


if __name__ == "__main__":
    main()
