#!/usr/bin/env python
"""Build a designed 16:9 PowerPoint deck from a JSON blueprint.

The engine draws every slide from native shapes and text boxes on a blank
canvas, so the output stays editable in PowerPoint. It is a lean port of the
design language in Noora_PPT Builder (16:9 canvas, one accent colour, thin
rules, a takeaway panel, speaker notes on every slide) with an added
"figure" slide that embeds sourced images and prints their credit line.

Blueprint shape::

    {
      "title": "Deck title",
      "subtitle": "Optional subtitle",
      "author": "Optional author",
      "accent": "#0E7C86",
      "sources": ["Source A", "Source B"],
      "slides": [
        {"kind": "cover", "title": "...", "subtitle": "...", "kicker": "..."},
        {"kind": "agenda", "title": "Agenda", "bullets": ["...", "..."]},
        {"kind": "section", "title": "...", "kicker": "SECTION 01"},
        {"kind": "content", "title": "...", "bullets": ["..."],
         "takeaway": "...", "source": "...", "notes": "..."},
        {"kind": "figure", "title": "...", "query": "gingival sulcus histology",
         "image_path": "figures/sulcus.png", "caption": "...", "credit": "..."},
        {"kind": "summary", "title": "Key takeaways", "bullets": ["..."]}
      ]
    }

Usage::

    python deck_builder.py blueprint.json -o deck.pptx
    python deck_builder.py --example > blueprint.json
    python deck_builder.py blueprint.json --check
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blueprint_io import read_json  # noqa: E402

LOGGER = logging.getLogger("deck_builder")

SLIDE_WIDTH_IN = 13.333
SLIDE_HEIGHT_IN = 7.5
MARGIN_X = 0.85
CONTENT_W = SLIDE_WIDTH_IN - 2 * MARGIN_X

FONT = "Segoe UI"

INK = RGBColor(0x14, 0x17, 0x1C)
DARK = RGBColor(0x0F, 0x14, 0x1A)
PAPER = RGBColor(0xFF, 0xFF, 0xFF)
CANVAS = RGBColor(0xF8, 0xF9, 0xFB)
MUTED = RGBColor(0x5E, 0x68, 0x74)
MUTED_LIGHT = RGBColor(0xA9, 0xB4, 0xC0)
HAIRLINE = RGBColor(0xDD, 0xE2, 0xE8)
ACCENT = RGBColor(0x0E, 0x7C, 0x86)
ACCENT_DEEP = RGBColor(0x0A, 0x3F, 0x4A)
ACCENT_LIGHT = RGBColor(0x7F, 0xD1, 0xD8)

KINDS = ("cover", "agenda", "section", "content", "figure", "summary")

_DEFAULT_ACCENT = ACCENT
_DEFAULT_ACCENT_DEEP = ACCENT_DEEP
_DEFAULT_ACCENT_LIGHT = ACCENT_LIGHT


# ---------------------------------------------------------------------------
# Colour and text helpers
# ---------------------------------------------------------------------------


def _rgb(value: str | None, fallback: RGBColor) -> RGBColor:
    text = (value or "").strip().lstrip("#")
    if len(text) == 6:
        try:
            return RGBColor(int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
        except ValueError:
            pass
    return fallback


def _mix(color: RGBColor, other: RGBColor, ratio: float) -> RGBColor:
    ratio = max(0.0, min(1.0, ratio))
    channels = [int(round(a * (1 - ratio) + b * ratio)) for a, b in zip(color, other)]
    return RGBColor(*channels[:3])


def _textbox(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    *,
    anchor=MSO_ANCHOR.TOP,
):
    box = slide.shapes.add_textbox(
        Inches(left), Inches(top), Inches(width), Inches(height)
    )
    frame = box.text_frame
    frame.clear()
    frame.word_wrap = True
    frame.auto_size = MSO_AUTO_SIZE.NONE
    frame.vertical_anchor = anchor
    frame.margin_left = Inches(0)
    frame.margin_right = Inches(0)
    frame.margin_top = Inches(0)
    frame.margin_bottom = Inches(0)
    return box


def _write(
    frame,
    text: str,
    *,
    size: float,
    color: RGBColor,
    bold: bool = False,
    italic: bool = False,
    font: str = FONT,
    align=PP_ALIGN.LEFT,
    line_spacing: float = 1.0,
    space_after: float = 0.0,
    tracking: int = 0,
    paragraph=None,
):
    para = paragraph if paragraph is not None else frame.paragraphs[0]
    run = para.add_run()
    run.text = str(text)
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    if tracking:
        run.font._rPr.set("spc", str(int(tracking)))
    para.alignment = align
    para.line_spacing = line_spacing
    para.space_after = Pt(space_after)
    return run


def _rect(
    slide,
    left: float,
    top: float,
    width: float,
    height: float,
    *,
    fill: RGBColor | None = None,
    line: RGBColor | None = None,
    shape=MSO_SHAPE.RECTANGLE,
    radius: float | None = None,
):
    box = slide.shapes.add_shape(
        shape, Inches(left), Inches(top), Inches(width), Inches(height)
    )
    if radius is not None:
        try:
            box.adjustments[0] = radius
        except Exception:
            pass
    if fill is None:
        box.fill.background()
    else:
        box.fill.solid()
        box.fill.fore_color.rgb = fill
    if line is None:
        box.line.fill.background()
    else:
        box.line.color.rgb = line
        box.line.width = Pt(1)
    box.shadow.inherit = False
    return box


def _set_alpha(shape, alpha: float) -> None:
    try:
        solid_fill = shape.fill._xPr.find(qn("a:solidFill"))
        srgb = solid_fill.find(qn("a:srgbClr"))
        if srgb is None:
            return
        for existing in srgb.findall(qn("a:alpha")):
            srgb.remove(existing)
        alpha_el = OxmlElement("a:alpha")
        alpha_el.set("val", str(int(max(0.0, min(1.0, alpha)) * 100_000)))
        srgb.append(alpha_el)
    except Exception:  # cosmetic only
        pass


def _bullet(paragraph, color: RGBColor, indent: float = 0.30) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_pr.set("marL", str(int(Inches(indent))))
    p_pr.set("indent", str(-int(Inches(indent))))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum", "a:buClr", "a:buSzPct", "a:buFont"):
        for element in p_pr.findall(qn(tag)):
            p_pr.remove(element)
    bu_clr = OxmlElement("a:buClr")
    srgb = OxmlElement("a:srgbClr")
    srgb.set("val", "%02X%02X%02X" % (color[0], color[1], color[2]))
    bu_clr.append(srgb)
    p_pr.append(bu_clr)
    bu_sz = OxmlElement("a:buSzPct")
    bu_sz.set("val", "85000")
    p_pr.append(bu_sz)
    bu_char = OxmlElement("a:buChar")
    bu_char.set("char", "\u25aa")
    p_pr.append(bu_char)


def _notes(slide, text: str) -> None:
    text = (text or "").strip()
    if not text:
        return
    slide.notes_slide.notes_text_frame.text = text


def _footer(slide, source: str, page: int, *, dark: bool = False) -> None:
    color = MUTED_LIGHT if dark else MUTED
    label = (source or "").strip()
    if label:
        box = _textbox(slide, MARGIN_X, 7.02, CONTENT_W - 0.9, 0.24)
        _write(box.text_frame, label[:150], size=8.5, color=color)
    number = _textbox(slide, SLIDE_WIDTH_IN - MARGIN_X - 0.6, 7.02, 0.6, 0.24)
    _write(
        number.text_frame,
        f"{page:02d}",
        size=8.5,
        color=color,
        align=PP_ALIGN.RIGHT,
        tracking=40,
    )


def _blank_slide(prs: Presentation, background: RGBColor):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = background
    return slide


# ---------------------------------------------------------------------------
# Text fitting
# ---------------------------------------------------------------------------


def estimate_lines(text: str, width_in: float, size_pt: float) -> int:
    usable = max(width_in * 72.0 - 16.0, 40.0)
    per_line = max(1, int(usable / (size_pt * 0.50)))
    words = max(1, math.ceil(len(str(text)) / per_line))
    return max(1, words + (1 if len(str(text)) > per_line * 0.92 * words else 0))


def fit_size(
    paragraphs: Sequence[str],
    width_in: float,
    height_in: float,
    *,
    base: float,
    minimum: float,
    line_factor: float = 1.32,
    gap_factor: float = 0.55,
) -> float:
    """Largest font size at which every paragraph fits the box."""
    size = base
    while size > minimum:
        total = 0.0
        for text in paragraphs:
            lines = estimate_lines(text, width_in, size)
            total += lines * size * line_factor / 72.0 + size * gap_factor / 72.0
        if total <= height_in:
            return size
        size -= 1.0
    return minimum


def _truncate(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]).rstrip(",.;:") + "\u2026"


def _bullets(raw: Sequence[Any], limit: int = 6) -> list[str]:
    cleaned = [_truncate(item, 260) for item in raw if str(item).strip()]
    return cleaned[:limit]


# ---------------------------------------------------------------------------
# Slide builders
# ---------------------------------------------------------------------------


def _cover(prs, spec: Mapping[str, Any], page: int, meta: Mapping[str, Any]) -> None:
    slide = _blank_slide(prs, DARK)
    circle = _rect(slide, 9.4, -1.9, 7.2, 7.2, fill=ACCENT, shape=MSO_SHAPE.OVAL)
    _set_alpha(circle, 0.16)
    ring = _rect(slide, 10.9, 3.6, 3.6, 3.6, fill=None, line=ACCENT_LIGHT, shape=MSO_SHAPE.OVAL)
    ring.line.width = Pt(1.2)
    _set_alpha(ring, 0.16)

    brand = _textbox(slide, MARGIN_X, 0.62, 6.0, 0.3)
    _write(
        brand.text_frame,
        str(spec.get("kicker") or "MEDDRAFT").upper(),
        size=10.5,
        color=ACCENT_LIGHT,
        bold=True,
        tracking=220,
    )
    _rect(slide, MARGIN_X, 1.72, 1.15, 0.055, fill=ACCENT_LIGHT)

    title = _truncate(spec.get("title") or meta.get("title") or "Untitled deck", 130)
    size = fit_size([title], 8.6, 2.35, base=50, minimum=30, line_factor=1.18)
    title_box = _textbox(slide, MARGIN_X, 1.98, 8.6, 2.45)
    _write(
        title_box.text_frame,
        title,
        size=size,
        color=PAPER,
        bold=True,
        line_spacing=1.06,
    )

    subtitle = spec.get("subtitle") or meta.get("subtitle")
    if subtitle:
        sub_box = _textbox(slide, MARGIN_X, 4.55, 7.7, 0.95)
        _write(
            sub_box.text_frame,
            _truncate(subtitle, 180),
            size=15.5,
            color=MUTED_LIGHT,
            line_spacing=1.25,
        )

    sources = spec.get("sources") or meta.get("sources") or []
    if sources:
        text = "  \u00b7  ".join(_truncate(item, 78) for item in sources[:3])
        if len(sources) > 3:
            text += f"  \u00b7  +{len(sources) - 3} more"
        source_box = _textbox(slide, MARGIN_X, 6.28, 8.4, 0.55)
        _write(
            source_box.text_frame,
            f"SOURCES   {text}",
            size=9,
            color=MUTED_LIGHT,
            tracking=60,
        )

    _notes(slide, spec.get("notes", ""))


def _section(prs, spec: Mapping[str, Any], page: int, meta: Mapping[str, Any]) -> None:
    slide = _blank_slide(prs, ACCENT_DEEP)
    kicker = str(spec.get("kicker") or "SECTION")
    number = "".join(ch for ch in kicker if ch.isdigit()) or f"{page:02d}"
    giant = _textbox(slide, 8.9, 1.15, 4.0, 3.4)
    _write(
        giant.text_frame,
        number,
        size=190,
        color=ACCENT,
        bold=True,
        align=PP_ALIGN.RIGHT,
        line_spacing=0.9,
    )
    for run in giant.text_frame.paragraphs[0].runs:
        run.font._rPr.set("spc", "-200")

    label = _textbox(slide, MARGIN_X, 1.55, 6.5, 0.3)
    _write(
        label.text_frame,
        kicker.upper(),
        size=10.5,
        color=ACCENT_LIGHT,
        bold=True,
        tracking=240,
    )
    title = _truncate(spec.get("title") or "Section", 90)
    size = fit_size([title], 7.4, 2.0, base=42, minimum=26, line_factor=1.15)
    title_box = _textbox(slide, MARGIN_X, 2.05, 7.6, 2.1)
    _write(
        title_box.text_frame,
        title,
        size=size,
        color=PAPER,
        bold=True,
        line_spacing=1.08,
    )
    _rect(slide, MARGIN_X, 4.35, 1.15, 0.055, fill=ACCENT_LIGHT)
    _footer(slide, spec.get("source", ""), page, dark=True)
    _notes(slide, spec.get("notes", ""))


def _agenda(prs, spec: Mapping[str, Any], page: int, meta: Mapping[str, Any]) -> None:
    slide = _blank_slide(prs, CANVAS)
    label = _textbox(slide, MARGIN_X, 0.55, CONTENT_W, 0.28)
    _write(
        label.text_frame,
        str(spec.get("kicker") or "AGENDA").upper(),
        size=9.5,
        color=ACCENT,
        bold=True,
        tracking=200,
    )
    title = _truncate(spec.get("title") or "Agenda", 95)
    title_size = fit_size([title], CONTENT_W, 1.0, base=34, minimum=22, line_factor=1.1)
    title_box = _textbox(slide, MARGIN_X, 0.85, CONTENT_W, 1.02)
    _write(
        title_box.text_frame,
        title,
        size=title_size,
        color=INK,
        bold=True,
        line_spacing=1.08,
    )
    _rect(slide, MARGIN_X, 1.99, CONTENT_W, 0.008, fill=HAIRLINE)
    _rect(slide, MARGIN_X, 1.965, 1.15, 0.05, fill=ACCENT)

    items = _bullets(spec.get("bullets") or [], 6)
    if not items:
        items = ["Add agenda items to the blueprint."]
    top = 2.42
    row_h = min(0.86, (6.35 - top) / max(len(items), 1))
    for index, item in enumerate(items):
        y = top + index * row_h
        number = _textbox(slide, MARGIN_X, y + 0.03, 0.8, 0.42)
        _write(
            number.text_frame,
            f"{index + 1:02d}",
            size=15,
            color=ACCENT,
            bold=True,
        )
        text_box = _textbox(slide, MARGIN_X + 0.8, y, CONTENT_W - 0.9, row_h - 0.08)
        size = fit_size([item], CONTENT_W - 0.9, row_h - 0.12, base=18, minimum=12)
        _write(
            text_box.text_frame,
            item,
            size=size,
            color=INK,
            line_spacing=1.22,
        )
    _footer(slide, spec.get("source", ""), page)
    _notes(slide, spec.get("notes", ""))


def _content(prs, spec: Mapping[str, Any], page: int, meta: Mapping[str, Any]) -> None:
    slide = _blank_slide(prs, CANVAS)
    label = _textbox(slide, MARGIN_X, 0.55, CONTENT_W, 0.28)
    _write(
        label.text_frame,
        str(spec.get("kicker") or "KEY CONTENT").upper(),
        size=9.5,
        color=ACCENT,
        bold=True,
        tracking=200,
    )
    title = _truncate(spec.get("title") or "Key content", 95)
    title_size = fit_size([title], CONTENT_W, 1.0, base=31, minimum=22, line_factor=1.1)
    title_box = _textbox(slide, MARGIN_X, 0.85, CONTENT_W, 1.02)
    _write(
        title_box.text_frame,
        title,
        size=title_size,
        color=INK,
        bold=True,
        line_spacing=1.08,
    )
    _rect(slide, MARGIN_X, 1.99, CONTENT_W, 0.008, fill=HAIRLINE)
    _rect(slide, MARGIN_X, 1.965, 1.15, 0.05, fill=ACCENT)

    bullets = _bullets(spec.get("bullets") or [])
    takeaway = _truncate(spec.get("takeaway") or "", 180)
    body_top = 2.26
    body_bottom = 5.92 if takeaway else 6.72
    body_h = body_bottom - body_top

    if bullets:
        base = 27 if len(bullets) <= 2 else 24 if len(bullets) == 3 else 21
        size = fit_size(bullets, CONTENT_W, body_h, base=base, minimum=13)
        box = _textbox(slide, MARGIN_X, body_top, CONTENT_W, body_h)
        frame = box.text_frame
        for index, bullet in enumerate(bullets):
            para = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            _write(
                frame,
                bullet,
                size=size,
                color=INK,
                line_spacing=1.28,
                space_after=size * 0.55,
                paragraph=para,
            )
            _bullet(para, ACCENT, indent=0.30)
    else:
        box = _textbox(slide, MARGIN_X, body_top, CONTENT_W, 1.2)
        _write(
            box.text_frame,
            "Add bullets to the blueprint for this slide.",
            size=14,
            color=MUTED,
            italic=True,
        )

    if takeaway:
        _rect(
            slide,
            MARGIN_X,
            6.05,
            CONTENT_W,
            0.86,
            fill=PAPER,
            line=HAIRLINE,
            shape=MSO_SHAPE.ROUNDED_RECTANGLE,
            radius=0.07,
        )
        _rect(slide, MARGIN_X, 6.05, 0.06, 0.86, fill=ACCENT)
        panel = _textbox(
            slide,
            MARGIN_X + 0.26,
            6.13,
            CONTENT_W - 0.5,
            0.7,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        _write(
            panel.text_frame,
            takeaway,
            size=12.5,
            color=MUTED,
            italic=True,
            line_spacing=1.22,
        )

    _footer(slide, spec.get("source", ""), page)
    _notes(slide, spec.get("notes", ""))


def _resolve_image(value: str | None, base_dir: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text)
    if not path.is_absolute():
        path = base_dir / path
    return path


def _figure(prs, spec: Mapping[str, Any], page: int, meta: Mapping[str, Any]) -> None:
    base_dir: Path = meta.get("base_dir") or Path(".")
    slide = _blank_slide(prs, CANVAS)
    label = _textbox(slide, MARGIN_X, 0.55, 5.8, 0.28)
    _write(
        label.text_frame,
        str(spec.get("kicker") or "FIGURE").upper(),
        size=9.5,
        color=ACCENT,
        bold=True,
        tracking=200,
    )
    title = _truncate(spec.get("title") or "Visual evidence", 70)
    title_size = fit_size([title], 5.6, 1.0, base=29, minimum=20, line_factor=1.12)
    title_box = _textbox(slide, MARGIN_X, 0.86, 5.6, 1.05)
    _write(
        title_box.text_frame,
        title,
        size=title_size,
        color=INK,
        bold=True,
        line_spacing=1.08,
    )
    _rect(slide, MARGIN_X, 1.99, 5.6, 0.008, fill=HAIRLINE)
    _rect(slide, MARGIN_X, 1.965, 1.0, 0.05, fill=ACCENT)

    panel_left, panel_top = 6.95, 1.35
    panel_w, panel_h = 5.55, 4.75
    _rect(slide, panel_left, panel_top, panel_w, panel_h, fill=PAPER, line=HAIRLINE)
    _rect(slide, panel_left, panel_top, panel_w, 0.05, fill=ACCENT)

    image_path = _resolve_image(spec.get("image_path"), base_dir)
    rendered = False
    if image_path and image_path.is_file():
        try:
            with Image.open(image_path) as img:
                iw, ih = img.size
            inner_w = panel_w - 0.36
            inner_h = panel_h - 0.72
            scale = min(inner_w / max(iw, 1), inner_h / max(ih, 1))
            draw_w = max(0.4, iw * scale)
            draw_h = max(0.4, ih * scale)
            left = panel_left + (panel_w - draw_w) / 2
            top = panel_top + 0.16 + (inner_h - draw_h) / 2
            slide.shapes.add_picture(
                str(image_path),
                Inches(left),
                Inches(top),
                Inches(draw_w),
                Inches(draw_h),
            )
            rendered = True
        except Exception as exc:
            LOGGER.warning("Could not place figure %s: %s", image_path, exc)

    if not rendered:
        query = str(spec.get("query") or "").strip()
        fallback = _textbox(
            slide,
            panel_left + 0.3,
            panel_top + 1.55,
            panel_w - 0.6,
            1.5,
            anchor=MSO_ANCHOR.MIDDLE,
        )
        message = "Figure slot" + (f": {query}" if query else "")
        _write(
            fallback.text_frame,
            message,
            size=13,
            color=MUTED,
            italic=True,
            align=PP_ALIGN.CENTER,
        )
        hint = _textbox(slide, panel_left + 0.3, panel_top + 2.55, panel_w - 0.6, 0.7)
        _write(
            hint.text_frame,
            "Run fetch_figures.py to fill this slot.",
            size=9.5,
            color=MUTED_LIGHT,
            align=PP_ALIGN.CENTER,
        )

    caption = _truncate(spec.get("caption") or "", 90)
    credit = _truncate(spec.get("credit") or spec.get("context_url") or "", 110)
    if caption:
        caption_box = _textbox(slide, panel_left, panel_top + panel_h - 0.52, panel_w, 0.28)
        _write(
            caption_box.text_frame,
            caption,
            size=8.5,
            color=MUTED,
            align=PP_ALIGN.CENTER,
        )
    if credit:
        credit_box = _textbox(slide, panel_left, panel_top + panel_h - 0.3, panel_w, 0.24)
        _write(
            credit_box.text_frame,
            credit,
            size=7.5,
            color=MUTED_LIGHT,
            align=PP_ALIGN.CENTER,
        )

    notes = _bullets(spec.get("bullets") or [], 3)
    if notes:
        size = fit_size(notes, 5.6, 3.0, base=15, minimum=11)
        box = _textbox(slide, MARGIN_X, 2.3, 5.6, 3.0)
        frame = box.text_frame
        for index, note in enumerate(notes):
            para = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            _write(
                frame,
                note,
                size=size,
                color=MUTED,
                line_spacing=1.32,
                space_after=10,
                paragraph=para,
            )
            _bullet(para, ACCENT_LIGHT, indent=0.26)

    _footer(slide, spec.get("source", ""), page)
    _notes(slide, spec.get("notes", ""))


def _summary(prs, spec: Mapping[str, Any], page: int, meta: Mapping[str, Any]) -> None:
    slide = _blank_slide(prs, DARK)
    glow = _rect(slide, -1.6, 4.3, 5.6, 5.6, fill=ACCENT, shape=MSO_SHAPE.OVAL)
    _set_alpha(glow, 0.14)

    label = _textbox(slide, MARGIN_X, 0.62, 6.0, 0.3)
    _write(
        label.text_frame,
        str(spec.get("kicker") or "SUMMARY").upper(),
        size=10.5,
        color=ACCENT_LIGHT,
        bold=True,
        tracking=240,
    )
    title = _truncate(spec.get("title") or "Key takeaways", 90)
    title_box = _textbox(slide, MARGIN_X, 0.95, 10.5, 0.9)
    _write(title_box.text_frame, title, size=34, color=PAPER, bold=True)

    subtitle = _truncate(spec.get("subtitle") or "", 140)
    if subtitle:
        sub_box = _textbox(slide, MARGIN_X, 1.86, 9.4, 0.5)
        _write(sub_box.text_frame, subtitle, size=14, color=MUTED_LIGHT)

    items = _bullets(spec.get("bullets") or [], 4) or ["Review the deck for the full narrative."]
    top = 2.62
    row_h = min(1.18, (6.35 - top) / max(len(items), 1))
    for index, item in enumerate(items):
        y = top + index * row_h
        number = _textbox(slide, MARGIN_X, y + 0.04, 0.9, 0.5)
        _write(
            number.text_frame,
            f"{index + 1:02d}",
            size=17,
            color=ACCENT_LIGHT,
            bold=True,
        )
        text_box = _textbox(slide, MARGIN_X + 0.85, y, CONTENT_W - 1.2, row_h - 0.1)
        size = fit_size([item], CONTENT_W - 1.2, row_h - 0.12, base=17, minimum=12)
        _write(
            text_box.text_frame,
            item,
            size=size,
            color=PAPER,
            line_spacing=1.28,
        )

    _footer(slide, spec.get("source", ""), page, dark=True)
    _notes(slide, spec.get("notes", ""))


_BUILDERS = {
    "cover": _cover,
    "agenda": _agenda,
    "section": _section,
    "content": _content,
    "figure": _figure,
    "summary": _summary,
}


# ---------------------------------------------------------------------------
# Blueprint handling
# ---------------------------------------------------------------------------


def validate_blueprint(blueprint: Mapping[str, Any]) -> list[str]:
    """Return human-readable warnings; never raises for missing optional keys."""
    warnings: list[str] = []
    if not isinstance(blueprint, Mapping):
        return ["blueprint must be a JSON object"]
    if not str(blueprint.get("title") or "").strip():
        warnings.append("blueprint has no title")
    slides = blueprint.get("slides")
    if not isinstance(slides, list) or not slides:
        warnings.append("blueprint has no slides")
        return warnings
    for index, slide in enumerate(slides, start=1):
        if not isinstance(slide, Mapping):
            warnings.append(f"slide {index} is not an object")
            continue
        kind = str(slide.get("kind") or "content")
        if kind not in KINDS:
            warnings.append(f"slide {index}: unknown kind {kind!r}; will render as content")
        if kind in ("content", "agenda", "summary") and not slide.get("bullets"):
            warnings.append(f"slide {index} ({kind}): no bullets")
        if kind == "figure" and not slide.get("image_path"):
            if slide.get("query"):
                warnings.append(
                    f"slide {index} (figure): no image_path yet; query is ready for fetch_figures.py"
                )
            else:
                warnings.append(f"slide {index} (figure): needs image_path or query")
    return warnings


def build_deck(
    blueprint: Mapping[str, Any],
    output_path: str | Path,
    *,
    base_dir: str | Path | None = None,
    accent: str | None = None,
) -> dict[str, Any]:
    """Render ``blueprint`` to a .pptx and return a small result record."""
    global ACCENT, ACCENT_DEEP, ACCENT_LIGHT
    ACCENT = _DEFAULT_ACCENT
    ACCENT_DEEP = _DEFAULT_ACCENT_DEEP
    ACCENT_LIGHT = _DEFAULT_ACCENT_LIGHT
    if accent:
        ACCENT = _rgb(accent, ACCENT)
        ACCENT_DEEP = _mix(ACCENT, RGBColor(0x00, 0x00, 0x00), 0.62)
        ACCENT_LIGHT = _mix(ACCENT, PAPER, 0.55)
    elif blueprint.get("accent"):
        ACCENT = _rgb(str(blueprint.get("accent")), ACCENT)
        ACCENT_DEEP = _mix(ACCENT, RGBColor(0x00, 0x00, 0x00), 0.62)
        ACCENT_LIGHT = _mix(ACCENT, PAPER, 0.55)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    warnings = validate_blueprint(blueprint)

    prs = Presentation()
    prs.slide_width = Inches(SLIDE_WIDTH_IN)
    prs.slide_height = Inches(SLIDE_HEIGHT_IN)
    props = prs.core_properties
    props.title = str(blueprint.get("title") or "Presentation")
    props.subject = str(blueprint.get("subtitle") or "")
    props.author = str(blueprint.get("author") or "MedDraft_AI")
    sources = blueprint.get("sources") or []
    if sources:
        props.comments = "Sources: " + "; ".join(str(item) for item in sources)

    meta = {
        "title": blueprint.get("title"),
        "subtitle": blueprint.get("subtitle"),
        "sources": sources,
        "base_dir": Path(base_dir) if base_dir else output_path.parent,
    }

    slides = blueprint.get("slides") or [
        {"kind": "cover", "title": blueprint.get("title") or "Presentation"}
    ]
    if not isinstance(slides, list):
        slides = []

    for index, spec in enumerate(slides, start=1):
        if not isinstance(spec, Mapping):
            continue
        kind = str(spec.get("kind") or "content")
        builder = _BUILDERS.get(kind, _content)
        try:
            builder(prs, spec, index, meta)
        except Exception as exc:  # one broken slide must not kill the deck
            LOGGER.error("Slide %s failed (%s): %s", index, kind, exc)
            slide = _blank_slide(prs, CANVAS)
            box = _textbox(slide, MARGIN_X, 2.5, CONTENT_W, 1.5)
            _write(
                box.text_frame,
                _truncate(spec.get("title") or "Slide", 80),
                size=30,
                color=INK,
                bold=True,
            )
            _notes(slide, spec.get("notes", ""))

    prs.save(str(output_path))
    return {
        "success": True,
        "path": str(output_path),
        "slides": len(prs.slides),
        "warnings": warnings,
    }


def load_blueprint(path: str | Path) -> dict[str, Any]:
    data = read_json(path)
    if not isinstance(data, dict):
        raise ValueError("blueprint must be a JSON object")
    return data


EXAMPLE = {
    "title": "Gingival Sulcus: Structure and Clinical Relevance",
    "subtitle": "A visual walkthrough for the periodontology seminar",
    "author": "MedDraft_AI",
    "accent": "#0E7C86",
    "sources": ["Carranza's Clinical Periodontology", "PubMed review, 2024"],
    "slides": [
        {
            "kind": "cover",
            "kicker": "PERIODONTOLOGY",
            "title": "Gingival Sulcus: Structure and Clinical Relevance",
            "subtitle": "Histology, defence mechanisms, and probing depth",
        },
        {
            "kind": "agenda",
            "title": "Agenda",
            "bullets": [
                "Anatomy of the dentogingival junction",
                "Sulcular fluid and host defence",
                "Probing depth versus attachment loss",
                "Clinical implications",
            ],
        },
        {
            "kind": "section",
            "kicker": "SECTION 01",
            "title": "Anatomy of the dentogingival junction",
        },
        {
            "kind": "content",
            "title": "The sulcus is a dynamic interface",
            "bullets": [
                "The gingival sulcus is the space between the tooth surface and the free gingival margin.",
                "Junctional epithelium attaches to enamel and provides the primary seal.",
                "Sulcular fluid carries immunoglobulins, neutrophils, and antimicrobial peptides.",
            ],
            "takeaway": "Probing depth measures sulcus depth; attachment loss measures destruction.",
            "source": "Carranza's Clinical Periodontology, ch. 1",
            "notes": "Pause here and ask the audience to define probing depth versus attachment loss.",
        },
        {
            "kind": "figure",
            "title": "Histology of the sulcular epithelium",
            "query": "gingival sulcus histology diagram",
            "caption": "Sulcular epithelium and junctional epithelium at the dentogingival junction.",
            "credit": "Sourced figure; verify licence before publication.",
            "bullets": [
                "Non-keratinised sulcular epithelium.",
                "Junctional epithelium is the seal.",
            ],
        },
        {
            "kind": "summary",
            "title": "Key takeaways",
            "bullets": [
                "The sulcus is an anatomical space, not a static line.",
                "Host defence depends on fluid flow and epithelial integrity.",
                "Probing depth alone cannot separate health from attachment loss.",
            ],
        },
    ],
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("blueprint", nargs="?", help="Path to the blueprint JSON file.")
    parser.add_argument("-o", "--out", default=None, help="Output .pptx path.")
    parser.add_argument("--accent", default=None, help="Accent colour as #RRGGBB.")
    parser.add_argument("--check", action="store_true", help="Validate the blueprint and exit.")
    parser.add_argument("--example", action="store_true", help="Print an example blueprint and exit.")
    parser.add_argument("--json", action="store_true", help="Emit a JSON result.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.example:
        print(json.dumps(EXAMPLE, indent=2, ensure_ascii=False))
        return 0

    if not args.blueprint:
        parser.error("blueprint is required unless --example is used")

    try:
        blueprint = load_blueprint(args.blueprint)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    warnings = validate_blueprint(blueprint)
    if args.check:
        payload = {"blueprint": str(args.blueprint), "warnings": warnings}
        print(json.dumps(payload, indent=2, ensure_ascii=False) if args.json else "\n".join(warnings) or "OK")
        return 0 if not warnings else 1

    out = args.out or str(Path(args.blueprint).with_suffix(".pptx"))
    result = build_deck(
        blueprint,
        out,
        base_dir=Path(args.blueprint).parent,
        accent=args.accent,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Wrote {result['path']} ({result['slides']} slides)")
        for warning in result["warnings"]:
            print(f"warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
