"""
Generate the system flow chart as a PNG for presentations.

    python tools/make_flowchart.py

Writes docs/images/system_flow.png

To update the chart, edit the DATA section below and re-run. Nothing else in
the file normally needs touching. Uses Pillow only, which is already a project
dependency, so this adds nothing to the install.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ═════════════════════════════════════════════════════════════════════════════
# DATA — edit this section when the plan changes
# ═════════════════════════════════════════════════════════════════════════════

TITLE = "piply-opdf — How the System Works"
SUBTITLE = "A poor or scanned PDF becomes a searchable, structured HTML document"
FOOTER = (
    "Runs fully offline on ordinary hardware · No cloud services · "
    "Learns from every correction an operator makes"
)
VERSION_NOTE = "Status as at September 2026 · 567 automated tests passing"

# status: "done" | "part" | "plan"
STAGES_TOP = [
    {
        "n": "1", "title": "Document In", "status": "done", "owner": "library",
        "lines": ["PDF or image", "Scanned or digital", "Any page size"],
    },
    {
        "n": "2", "title": "Clean Up", "status": "part", "owner": "library",
        "lines": ["Measure quality", "Fix blur, noise, contrast", "Straighten the page"],
    },
    {
        "n": "3", "title": "Find Layouts", "status": "part", "owner": "library",
        "lines": ["Boxes, tables, titles", "Headers, footers, lists",
                  "Key-values, signatures", "Stamps and logos", "Anything left = Unknown"],
    },
    {
        "n": "4", "title": "Split Into Units", "status": "part", "owner": "library",
        "lines": ["Table → row → cell", "Paragraph → line → word",
                  "Key-value → key / value", "Boxes opened up inside"],
    },
    {
        "n": "5", "title": "Record Everything", "status": "plan", "owner": "library",
        "lines": ["One file per page", "One file per layout",
                  "Position, size, order", "Nothing left out"],
    },
]

STAGES_BOTTOM = [
    {
        "n": "6", "title": "Read The Text", "status": "part", "owner": "library",
        "lines": ["Seen before? reuse it", "Otherwise run OCR",
                  "Score every result"],
    },
    {
        "n": "7", "title": "Person Checks", "status": "plan", "owner": "screen",
        "lines": ["Lowest scores first", "Fix text, type or box",
                  "Keyboard driven"],
    },
    {
        "n": "8", "title": "Deliver", "status": "plan", "owner": "library",
        "lines": ["Searchable HTML", "Structured fields", "Excel and CSV"],
    },
]

MEMORY = {
    "title": "Memory",
    "status": "done",
    "lines": [
        "Only what a person confirmed is stored",
        "Same image next time → filled in instantly, no OCR",
        "Carries across documents and projects",
    ],
}

LEGEND = [
    ("done", "Built and tested"),
    ("part", "Partly built"),
    ("plan", "Planned"),
]

# ═════════════════════════════════════════════════════════════════════════════
# STYLE
# ═════════════════════════════════════════════════════════════════════════════

W, H = 3000, 1530

INK = (28, 37, 54)
INK_SOFT = (86, 96, 114)
MUTED = (140, 148, 162)
CANVAS = (251, 250, 247)
WHITE = (255, 255, 255)
LINE = (214, 208, 196)

STATUS = {
    "done": {"bar": (47, 107, 79), "tint": (237, 244, 239), "label": "Built"},
    "part": {"bar": (161, 124, 58), "tint": (247, 241, 228), "label": "Partly built"},
    "plan": {"bar": (120, 130, 148), "tint": (241, 242, 245), "label": "Planned"},
}

OWNER = {
    "library": (58, 90, 140),
    "screen": (140, 58, 90),
}

FONTS = "C:/Windows/Fonts"


def font(name: str, size: int):
    for candidate in (f"{FONTS}/{name}", name):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_TITLE = font("segoeuib.ttf", 72)
F_SUB = font("segoeui.ttf", 34)
F_NUM = font("segoeuib.ttf", 30)
F_STAGE = font("segoeuib.ttf", 40)
F_BODY = font("segoeui.ttf", 26)
F_SMALL = font("segoeui.ttf", 23)
F_TAG = font("segoeuib.ttf", 20)
F_BAND = font("segoeuib.ttf", 26)


# ═════════════════════════════════════════════════════════════════════════════
# DRAWING
# ═════════════════════════════════════════════════════════════════════════════

def card(d: ImageDraw.ImageDraw, box, stage) -> None:
    """One numbered stage card."""
    x0, y0, x1, y1 = box
    style = STATUS[stage["status"]]

    d.rounded_rectangle([x0 + 5, y0 + 6, x1 + 5, y1 + 6],
                        radius=18, fill=(238, 234, 226))
    d.rounded_rectangle([x0, y0, x1, y1], radius=18,
                        fill=WHITE, outline=LINE, width=2)
    d.rounded_rectangle([x0, y0, x1, y0 + 12], radius=6, fill=style["bar"])

    # Left edge shows which side of the product owns this stage — the engine
    # or the operator screen. Matches the band at the foot of the chart.
    d.rounded_rectangle([x0, y0 + 26, x0 + 11, y1 - 20], radius=5,
                        fill=OWNER[stage["owner"]])

    # number chip
    d.ellipse([x0 + 26, y0 + 40, x0 + 84, y0 + 98], fill=style["bar"])
    tw = d.textlength(stage["n"], font=F_NUM)
    d.text((x0 + 55 - tw / 2, y0 + 54), stage["n"], font=F_NUM, fill=WHITE)

    d.text((x0 + 102, y0 + 50), stage["title"], font=F_STAGE, fill=INK)

    y = y0 + 122
    for line in stage["lines"]:
        d.ellipse([x0 + 34, y + 11, x0 + 44, y + 21], fill=MUTED)
        d.text((x0 + 58, y), line, font=F_BODY, fill=INK_SOFT)
        y += 40

    # status tag
    label = style["label"]
    lw = d.textlength(label, font=F_TAG)
    d.rounded_rectangle([x1 - lw - 46, y1 - 46, x1 - 20,
                        y1 - 14], radius=9, fill=style["tint"])
    d.text((x1 - lw - 33, y1 - 41), label, font=F_TAG, fill=style["bar"])


def arrow(d, start, end, colour=INK_SOFT, width=5, head=20) -> None:
    """Straight arrow with a solid head."""
    x0, y0 = start
    x1, y1 = end
    d.line([x0, y0, x1, y1], fill=colour, width=width)

    if x1 == x0:                      # vertical
        s = 1 if y1 > y0 else -1
        d.polygon([(x1, y1), (x1 - head, y1 - s * head),
                  (x1 + head, y1 - s * head)], fill=colour)
    else:                             # horizontal
        s = 1 if x1 > x0 else -1
        d.polygon([(x1, y1), (x1 - s * head, y1 - head),
                  (x1 - s * head, y1 + head)], fill=colour)


def elbow(d, start, end, colour=INK_SOFT, width=5) -> None:
    """Right-angled connector: down, across, then arrow into the target."""
    x0, y0 = start
    x1, y1 = end
    mid = y0 + (y1 - y0) // 2
    d.line([x0, y0, x0, mid], fill=colour, width=width)
    d.line([x0, mid, x1, mid], fill=colour, width=width)
    arrow(d, (x1, mid), (x1, y1), colour=colour, width=width)


def build() -> Image.Image:
    img = Image.new("RGB", (W, H), CANVAS)
    d = ImageDraw.Draw(img)

    # ── header ───────────────────────────────────────────────────────────────
    d.text((80, 62), TITLE, font=F_TITLE, fill=INK)
    d.text((84, 152), SUBTITLE, font=F_SUB, fill=INK_SOFT)
    d.line([80, 218, W - 80, 218], fill=LINE, width=3)

    # legend, right aligned
    lx = W - 80
    for key, text in reversed(LEGEND):
        tw = d.textlength(text, font=F_SMALL)
        d.text((lx - tw, 96), text, font=F_SMALL, fill=INK_SOFT)
        d.rounded_rectangle([lx - tw - 42, 100, lx - tw - 16, 118], radius=5,
                            fill=STATUS[key]["bar"])
        lx -= tw + 78

    # ── stage rows ───────────────────────────────────────────────────────────
    margin, gap = 80, 52
    cw = (W - 2 * margin - 4 * gap) // 5
    top_y0, top_y1 = 268, 268 + 330
    bot_y0, bot_y1 = 780, 780 + 330

    top_boxes = []
    for i, stage in enumerate(STAGES_TOP):
        x0 = margin + i * (cw + gap)
        box = (x0, top_y0, x0 + cw, top_y1)
        card(d, box, stage)
        top_boxes.append(box)

    for a, b in zip(top_boxes, top_boxes[1:]):
        arrow(d, (a[2] + 8, top_y0 + 165), (b[0] - 10, top_y0 + 165))

    # bottom row runs right to left
    bot_boxes = []
    for i, stage in enumerate(STAGES_BOTTOM):
        x0 = margin + (4 - i) * (cw + gap)
        box = (x0, bot_y0, x0 + cw, bot_y1)
        card(d, box, stage)
        bot_boxes.append(box)

    for a, b in zip(bot_boxes, bot_boxes[1:]):
        arrow(d, (a[0] - 8, bot_y0 + 165), (b[2] + 10, bot_y0 + 165))

    # stage 5 down into stage 6
    last_top = top_boxes[-1]
    first_bot = bot_boxes[0]
    arrow(d, ((last_top[0] + last_top[2]) // 2, top_y1 + 8),
          ((first_bot[0] + first_bot[2]) // 2, bot_y0 - 12))

    # ── memory box ───────────────────────────────────────────────────────────
    # Placed in the space the bottom row leaves free, so the loop is visible
    # without a long detour and no large area of the chart sits empty.
    mx0 = margin
    mx1 = margin + (cw + gap) + cw
    my0, my1 = bot_y0, bot_y1
    style = STATUS[MEMORY["status"]]

    d.rounded_rectangle([mx0 + 5, my0 + 6, mx1 + 5, my1 + 6],
                        radius=18, fill=(238, 234, 226))
    d.rounded_rectangle([mx0, my0, mx1, my1], radius=18, fill=style["tint"],
                        outline=style["bar"], width=3)
    # Memory belongs to the engine, like the other engine stages.
    d.rounded_rectangle([mx0, my0 + 26, mx0 + 11, my1 - 20], radius=5,
                        fill=OWNER["library"])
    d.text((mx0 + 44, my0 + 32), MEMORY["title"], font=F_STAGE, fill=INK)

    tag = "The system gets better every time"
    tw = d.textlength(tag, font=F_TAG)
    d.rounded_rectangle([mx1 - tw - 60, my0 + 38, mx1 -
                        30, my0 + 74], radius=9, fill=WHITE)
    d.text((mx1 - tw - 45, my0 + 45), tag, font=F_TAG, fill=style["bar"])

    y = my0 + 100
    for line in MEMORY["lines"]:
        d.ellipse([mx0 + 48, y + 11, mx0 + 58, y + 21], fill=style["bar"])
        d.text((mx0 + 72, y), line, font=F_BODY, fill=INK_SOFT)
        y += 40

    # person checks → memory → read the text, on two separate corridors so the
    # outward and return legs never overlap
    review_box = bot_boxes[1]
    resolve_box = bot_boxes[0]
    loop = style["bar"]

    out_y = bot_y1 + 70
    back_y = bot_y1 + 150
    review_x = (review_box[0] + review_box[2]) // 2
    memory_x = mx0 + (mx1 - mx0) // 2
    resolve_x = (resolve_box[0] + resolve_box[2]) // 2

    # out: person checks -> memory
    d.line([review_x, bot_y1 + 8, review_x, out_y], fill=loop, width=5)
    d.line([review_x, out_y, memory_x, out_y], fill=loop, width=5)
    arrow(d, (memory_x, out_y), (memory_x, my1 + 8), colour=loop)

    # back: memory -> read the text
    d.line([memory_x + 260, my1 + 8, memory_x + 260, back_y], fill=loop, width=5)
    d.line([memory_x + 260, back_y, resolve_x, back_y], fill=loop, width=5)
    arrow(d, (resolve_x, back_y), (resolve_x, bot_y1 + 8), colour=loop)

    d.text((review_x - 470, out_y - 42), "only confirmed answers are kept",
           font=F_SMALL, fill=loop)
    d.text((memory_x + 290, back_y - 40), "reused instantly next time",
           font=F_SMALL, fill=loop)

    # ── owner band ───────────────────────────────────────────────────────────
    by = 1330
    d.rounded_rectangle([80, by, W - 80, by + 92], radius=14,
                        fill=WHITE, outline=LINE, width=2)

    d.rounded_rectangle([116, by + 30, 150, by + 62],
                        radius=6, fill=OWNER["library"])
    d.text((166, by + 30), "Engine — reusable in any product",
           font=F_BAND, fill=INK)

    d.rounded_rectangle([916, by + 30, 950, by + 62],
                        radius=6, fill=OWNER["screen"])
    d.text((966, by + 30), "Operator screen — uses the engine, never the reverse",
           font=F_BAND, fill=INK)

    note = VERSION_NOTE
    tw = d.textlength(note, font=F_SMALL)
    d.text((W - 116 - tw, by + 34), note, font=F_SMALL, fill=MUTED)

    # ── footer ───────────────────────────────────────────────────────────────
    d.text((84, H - 62), FOOTER, font=F_SMALL, fill=MUTED)

    return img


def main() -> int:
    out = Path(__file__).resolve().parents[1] / \
        "docs" / "images" / "system_flow.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    build().save(out, "PNG", optimize=True)
    print(f"wrote {out}  ({out.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
