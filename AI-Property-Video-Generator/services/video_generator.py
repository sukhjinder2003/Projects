"""Video rendering engine.

Pipeline: Pillow draws every frame (Ken Burns motion, cards, captions, transitions)
and streams raw RGB frames into FFmpeg, which encodes an H.264 MP4. FFmpeg comes
bundled with the `imageio-ffmpeg` package, so no manual FFmpeg install is needed.
"""
from __future__ import annotations

import logging
import math
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from config import Config

log = logging.getLogger(__name__)
ProgressFn = Optional[Callable[[float, str], None]]


class VideoGenerationError(Exception):
    """Raised for any problem the user should be told about."""


# --------------------------------------------------------------------------- #
# Visual styles
# --------------------------------------------------------------------------- #
STYLES = {
    "modern_luxury": dict(
        label="Modern Luxury", description="Dark glass cards, brass accents, serif headlines.",
        title="serif_bold", body="sans", strong="sans_bold",
        panel=(12, 15, 26, 208), panel_text=(250, 246, 238), muted=(206, 192, 156),
        accent=(206, 168, 84), accent_text=(20, 15, 6), radius=8, transition="fade",
        layout="center", dim=0.34, dur_scale=1.0, type_scale=1.0, swatch=("#0c0f1a", "#cea854"),
    ),
    "minimal_professional": dict(
        label="Minimal Professional", description="Clean white cards, quiet teal accent, left aligned.",
        title="sans_bold", body="sans", strong="sans_bold",
        panel=(255, 255, 255, 238), panel_text=(26, 36, 50), muted=(98, 112, 130),
        accent=(16, 126, 134), accent_text=(255, 255, 255), radius=14, transition="slide",
        layout="left", dim=0.22, dur_scale=1.0, type_scale=1.0, swatch=("#ffffff", "#107e86"),
    ),
    "premium_real_estate": dict(
        label="Premium Real Estate", description="Deep green panels, warm cream type, slow zoom transitions.",
        title="serif_bold", body="serif", strong="serif_bold",
        panel=(15, 54, 48, 216), panel_text=(246, 241, 226), muted=(196, 214, 196),
        accent=(232, 196, 120), accent_text=(18, 40, 34), radius=22, transition="zoom",
        layout="center", dim=0.36, dur_scale=1.1, type_scale=1.0, swatch=("#0f3630", "#e8c478"),
    ),
    "social_media": dict(
        label="Social Media Promotional", description="Big bold type, coral accent, fast slide cuts.",
        title="sans_bold", body="sans_bold", strong="sans_bold",
        panel=(22, 22, 34, 228), panel_text=(255, 255, 255), muted=(255, 214, 220),
        accent=(255, 82, 104), accent_text=(255, 255, 255), radius=32, transition="slide",
        layout="center", dim=0.28, dur_scale=0.8, type_scale=1.14, swatch=("#161622", "#ff5268"),
    ),
}


# --------------------------------------------------------------------------- #
# Fonts (system fonts only; works on Windows, macOS and Linux)
# --------------------------------------------------------------------------- #
_FONT_FILES = {
    "serif_bold": ["georgiab.ttf", "timesbd.ttf", "DejaVuSerif-Bold.ttf", "LiberationSerif-Bold.ttf", "NotoSerif-Bold.ttf"],
    "serif": ["georgia.ttf", "times.ttf", "DejaVuSerif.ttf", "LiberationSerif-Regular.ttf", "NotoSerif-Regular.ttf"],
    "sans_bold": ["segoeuib.ttf", "arialbd.ttf", "calibrib.ttf", "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf", "Arial Bold.ttf"],
    "sans": ["segoeui.ttf", "arial.ttf", "calibri.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf", "Arial.ttf"],
}


@lru_cache(maxsize=1)
def _font_index() -> dict[str, str]:
    dirs = [r"C:\Windows\Fonts", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts"),
            "/usr/share/fonts", "/usr/local/share/fonts", "/Library/Fonts", "/System/Library/Fonts",
            os.path.expanduser("~/.fonts"), os.path.expanduser("~/Library/Fonts")]
    index: dict[str, str] = {}
    for d in dirs:
        if d and os.path.isdir(d):
            for root, _, files in os.walk(d):
                for name in files:
                    index.setdefault(name.lower(), os.path.join(root, name))
    return index


@lru_cache(maxsize=256)
def get_font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    index = _font_index()
    for fname in _FONT_FILES[kind]:
        path = index.get(fname.lower())
        if path:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)  # Pillow >= 10.1


_MEAS = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def wrap(text: str, font, max_w: float) -> list[str]:
    """Word-wrap text to max_w pixels (also breaks over-long words)."""
    out: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split():
            while len(word) > 1 and _MEAS.textlength(word, font=font) > max_w:
                cut = len(word)
                while cut > 1 and _MEAS.textlength(word[:cut], font=font) > max_w:
                    cut -= 1
                if line:
                    out.append(line)
                    line = ""
                out.append(word[:cut])
                word = word[cut:]
            trial = f"{line} {word}".strip()
            if _MEAS.textlength(trial, font=font) <= max_w:
                line = trial
            else:
                if line:
                    out.append(line)
                line = word
        if line:
            out.append(line)
    return out or [""]


def fit_font(text: str, kind: str, size: int, max_w: float, min_size: int = 12):
    """Largest font (<= size) in which `text` fits on one line within max_w."""
    while size > min_size:
        f = get_font(kind, size)
        if _MEAS.textlength(text, font=f) <= max_w:
            return f
        size -= 2
    return get_font(kind, min_size)


def fit_line(text: str, kind: str, size: int, max_w: float, min_size: int = 18):
    """Fit one line: shrink the font down to min_size, then truncate with an ellipsis."""
    font = fit_font(text, kind, size, max_w, min_size)
    if _MEAS.textlength(text, font=font) <= max_w:
        return font, text
    while len(text) > 1 and _MEAS.textlength(text + "…", font=font) > max_w:
        text = text[:-1]
    return font, text.rstrip() + "…"


# --------------------------------------------------------------------------- #
# Small math helpers
# --------------------------------------------------------------------------- #
def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_out(x: float) -> float:
    return 1 - (1 - clamp(x)) ** 3


def ease_inout(x: float) -> float:
    x = clamp(x)
    return x * x * (3 - 2 * x)


# --------------------------------------------------------------------------- #
# Layout context
# --------------------------------------------------------------------------- #
class Ctx:
    def __init__(self, W: int, H: int, style: dict):
        self.W, self.H, self.style = W, H, style
        self.u = min(W, H) / 720.0                 # base unit: 1.0 at 720px
        self.landscape = W > H * 1.2
        self.portrait = H > W * 1.2
        self.margin = int(48 * self.u)
        self.max_card_w = int(W * (0.58 if self.landscape else 0.86))
        self.wide_w = int(W * (0.80 if self.landscape else 0.86))
        self.bottom_gap = int(H * (0.14 if self.portrait else 0.07))

    def px(self, n: float) -> int:
        """Font size in pixels (scaled by resolution and style)."""
        return max(10, int(round(n * self.u * self.style["type_scale"])))

    def place(self, w: int, h: int, anchor: str = "center") -> tuple[int, int]:
        x = (self.W - w) // 2 if self.style["layout"] == "center" else self.margin
        if anchor == "center":
            y = (self.H - h) // 2
        elif anchor == "bottom":
            y = self.H - self.bottom_gap - h
        else:
            y = self.margin
        return x, y


# --------------------------------------------------------------------------- #
# Text blocks and cards
# --------------------------------------------------------------------------- #
class Block:
    """Pre-laid-out multi-style paragraph(s)."""

    def __init__(self, parts: list[dict], max_w: float, scale: float = 1.0, align: str = "left"):
        self.lines, self.align, self.w = [], align, 0.0
        y, last_gap = 0.0, 0.0
        for p in parts:
            font = get_font(p["kind"], max(10, int(p["size"] * scale)))
            text = p["text"].upper() if p.get("upper") else p["text"]
            lead = sum(font.getmetrics()) * p.get("lead", 1.1)
            for ln in wrap(text, font, max_w):
                lw = _MEAS.textlength(ln, font=font)
                self.lines.append((ln, font, p["color"], lw, y))
                self.w = max(self.w, lw)
                y += lead
            last_gap = p.get("gap", 0) * scale
            y += last_gap
        self.h = y - last_gap

    def paint(self, d: ImageDraw.ImageDraw, x: float, y: float, width: float):
        for ln, font, color, lw, yo in self.lines:
            lx = x + ((width - lw) / 2 if self.align == "center" else 0)
            d.text((lx, y + yo), ln, font=font, fill=color)


def build_block(parts, max_w, max_h=None, align="left") -> Block:
    scale = 1.0
    while True:
        blk = Block(parts, max_w, scale, align)
        if max_h is None or blk.h <= max_h or scale <= 0.5:
            return blk
        scale -= 0.08


class Card:
    """Rounded translucent panel with an accent rule and text inside."""

    def __init__(self, ctx: Ctx, parts, max_w: int, max_h: Optional[int] = None, fixed_w: Optional[int] = None,
                 rule: bool = True, fill=None):
        st, u = ctx.style, ctx.u
        self.ctx, self.pad = ctx, int(30 * u)
        self.align = "center" if st["layout"] == "center" else "left"
        self.rule_space = int(22 * u) if rule else 0
        self.rule, self.fill = rule, fill or st["panel"]
        inner_w = (fixed_w or max_w) - 2 * self.pad
        inner_h = (max_h - 2 * self.pad - self.rule_space) if max_h else None
        self.block = build_block(parts, inner_w, inner_h, self.align)
        self.w = int(fixed_w or (self.block.w + 2 * self.pad))
        self.h = int(self.block.h + 2 * self.pad + self.rule_space)

    def paint(self, d, x: float, y: float):
        st, u = self.ctx.style, self.ctx.u
        d.rounded_rectangle((x, y, x + self.w, y + self.h), radius=int(st["radius"] * u), fill=self.fill)
        cy = y + self.pad
        if self.rule:
            rw = int(54 * u)
            rx = x + (self.w - rw) / 2 if self.align == "center" else x + self.pad
            d.rectangle((rx, cy, rx + rw, cy + max(3, int(5 * u))), fill=st["accent"])
            cy += self.rule_space
        self.block.paint(d, x + self.pad, cy, self.w - 2 * self.pad)


def draw_pill(d, ctx: Ctx, x: float, y: float, text: str, size: int, max_w: float, dot: bool = True,
              right_align: bool = False, center: bool = False) -> None:
    st, u = ctx.style, ctx.u
    extra = 36 * u + (22 * u if dot else 0)
    font, text = fit_line(text, st["strong"], size, max_w - extra, min_size=max(12, size // 2))
    tw = _MEAS.textlength(text, font=font)
    h = int(sum(font.getmetrics()) + 18 * u)
    w = int(tw + extra)
    if right_align:
        x -= w
    elif center:
        x -= w / 2
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=st["panel"])
    tx = x + 18 * u
    if dot:
        r = 6 * u
        d.ellipse((tx, y + h / 2 - r, tx + 2 * r, y + h / 2 + r), fill=st["accent"])
        tx += 22 * u
    d.text((tx, y + 9 * u), text, font=font, fill=st["panel_text"])


# --------------------------------------------------------------------------- #
# Backdrop with Ken Burns motion
# --------------------------------------------------------------------------- #
def make_canvas(img: Image.Image, bw: int, bh: int) -> Image.Image:
    """Cover-fit when aspect ratios are similar, else blurred-fill + contained photo."""
    if abs(math.log((img.width / img.height) / (bw / bh))) < 0.45:
        return ImageOps.fit(img, (bw, bh), Image.LANCZOS)
    bg = ImageOps.fit(img, (max(8, bw // 4), max(8, bh // 4)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6))
    bg = Image.blend(bg.resize((bw, bh), Image.BICUBIC), Image.new("RGB", (bw, bh), (0, 0, 0)), 0.25)
    fg = ImageOps.contain(img, (bw, bh), Image.LANCZOS)
    bg.paste(fg, ((bw - fg.width) // 2, (bh - fg.height) // 2))
    return bg


class Backdrop:
    ZOOM = 1.15

    def __init__(self, img: Image.Image, ctx: Ctx, *, dim: float = 0.0, blur: float = 0.0,
                 zoom=(1.0, 1.12), pan=(0.0, 0.0, 0.0, 0.0)):
        self.W, self.H = ctx.W, ctx.H
        self.bw, self.bh = int(ctx.W * self.ZOOM), int(ctx.H * self.ZOOM)
        canvas = make_canvas(img, self.bw, self.bh)
        if blur:
            small = canvas.resize((self.bw // 6, self.bh // 6), Image.BILINEAR).filter(ImageFilter.GaussianBlur(blur))
            canvas = small.resize((self.bw, self.bh), Image.BICUBIC)
        if dim:
            canvas = Image.blend(canvas, Image.new("RGB", canvas.size, (8, 10, 16)), dim)
        self.canvas, self.zoom, self.pan = canvas, zoom, pan

    def frame(self, p: float) -> Image.Image:
        e = ease_inout(p)
        z = lerp(self.zoom[0], self.zoom[1], e)
        w, h = self.bw / z, self.bh / z
        px, py = lerp(self.pan[0], self.pan[2], e), lerp(self.pan[1], self.pan[3], e)
        x0, y0 = (self.bw - w) / 2 * (1 + px), (self.bh - h) / 2 * (1 + py)
        return self.canvas.resize((self.W, self.H), Image.BILINEAR, box=(x0, y0, x0 + w, y0 + h))


MOTIONS = [  # (zoom_from, zoom_to, pan_x0, pan_y0, pan_x1, pan_y1)
    (1.00, 1.12, 0, 0, 0, 0), (1.12, 1.00, 0, 0, 0, 0),
    (1.06, 1.12, -0.8, 0, 0.8, 0), (1.06, 1.12, 0.8, 0, -0.8, 0),
    (1.00, 1.10, 0, 0.8, 0, -0.8), (1.10, 1.02, -0.5, -0.5, 0.5, 0.5),
]


def motion(i: int) -> dict:
    m = MOTIONS[i % len(MOTIONS)]
    return dict(zoom=(m[0], m[1]), pan=(m[2], m[3], m[4], m[5]))


# --------------------------------------------------------------------------- #
# Scenes
# --------------------------------------------------------------------------- #
class Scene:
    """A backdrop plus timed elements; each element is fn(draw, dy_offset)."""

    def __init__(self, ctx: Ctx, duration: float, backdrop: Backdrop, pre=None):
        self.ctx, self.duration, self.backdrop, self.pre = ctx, duration, backdrop, pre
        self.elements: list[tuple[float, Callable]] = []

    def add(self, delay: float, fn: Callable) -> None:
        self.elements.append((delay, fn))

    def render(self, t: float) -> Image.Image:
        frame = self.backdrop.frame(clamp(t / self.duration))
        if self.pre:
            self.pre(frame)
        for delay, fn in self.elements:
            a = ease_out((t - delay) / 0.7)
            if a <= 0:
                continue
            if a >= 0.999:
                fn(ImageDraw.Draw(frame, "RGBA"), 0)
            else:
                layer = frame.copy()
                fn(ImageDraw.Draw(layer, "RGBA"), (1 - a) * 28 * self.ctx.u)
                frame = Image.blend(frame, layer, a)
        return frame


def bottom_gradient(ctx: Ctx) -> Callable[[Image.Image], None]:
    mask = Image.new("L", (1, ctx.H))
    start = int(ctx.H * 0.45)
    mask.putdata([0 if y < start else int(185 * ((y - start) / (ctx.H - start)) ** 1.4) for y in range(ctx.H)])
    mask = mask.resize((ctx.W, ctx.H))

    def apply(frame: Image.Image) -> None:
        frame.paste((6, 8, 14), (0, 0), mask)
    return apply


def title_scene(ctx, imgs, prop, script, dur) -> Scene:
    st = ctx.style
    sc = Scene(ctx, dur, Backdrop(imgs[0], ctx, dim=st["dim"], **motion(0)))
    parts = [
        dict(text=f"{prop['property_type']} · {prop['location']}", kind=st["strong"], size=ctx.px(20),
             color=st["accent"], gap=14),
        dict(text=script["headline"], kind=st["title"], size=ctx.px(58), color=st["panel_text"], gap=14, lead=1.05),
        dict(text=script["tagline"], kind=st["body"], size=ctx.px(26), color=st["muted"]),
    ]
    card = Card(ctx, parts, ctx.max_card_w, max_h=int(ctx.H * 0.72))
    x, y = ctx.place(card.w, card.h, "center")
    sc.add(0.25, lambda d, dy: card.paint(d, x, y + dy))
    return sc


def details_scene(ctx, imgs, prop, dur) -> Scene:
    st, u = ctx.style, ctx.u
    sc = Scene(ctx, dur, Backdrop(imgs[1 % len(imgs)], ctx, dim=0.55, blur=4, **motion(1)))
    tw, gap = ctx.wide_w, int(16 * u)
    price = Card(ctx, [
        dict(text="Price", kind=st["strong"], size=ctx.px(20), color=st["muted"], gap=4),
        dict(text=prop["price"], kind=st["title"], size=ctx.px(58), color=st["accent"], gap=8, lead=1.05),
        dict(text=prop["name"], kind=st["strong"], size=ctx.px(26), color=st["panel_text"]),
    ], tw, fixed_w=tw, max_h=int(ctx.H * 0.36))

    chips = [("Type", prop["property_type"])]
    if prop["bedrooms"]:
        chips.append(("Bedrooms", str(prop["bedrooms"])))
    if prop["bathrooms"]:
        chips.append(("Bathrooms", str(prop["bathrooms"])))
    chips.append(("Area", f"{prop['area']} sq. ft."))
    cols = min(len(chips), 4 if ctx.landscape else 2)
    rows = math.ceil(len(chips) / cols)
    chip_w, chip_h = (tw - gap * (cols - 1)) // cols, int(96 * u)
    total_h = price.h + gap + rows * chip_h + (rows - 1) * gap
    x0, y0 = (ctx.W - tw) // 2, (ctx.H - total_h) // 2

    sc.add(0.2, lambda d, dy: price.paint(d, x0, y0 + dy))
    for i, (label, value) in enumerate(chips):
        cx = x0 + (i % cols) * (chip_w + gap)
        cy = y0 + price.h + gap + (i // cols) * (chip_h + gap)
        vfont, value = fit_line(value, st["strong"], ctx.px(34), chip_w - 2 * int(22 * u), ctx.px(20))

        def paint(d, dy, cx=cx, cy=cy, label=label, value=value, vfont=vfont):
            d.rounded_rectangle((cx, cy + dy, cx + chip_w, cy + chip_h + dy), radius=int(st["radius"] * u), fill=st["panel"])
            d.text((cx + 22 * u, cy + 14 * u + dy), label, font=get_font(st["body"], ctx.px(18)), fill=st["muted"])
            d.text((cx + 22 * u, cy + 14 * u + ctx.px(18) * 1.5 + dy), value, font=vfont, fill=st["panel_text"])
        sc.add(0.55 + 0.18 * i, paint)
    return sc


def photo_scene(ctx, img, idx, total, prop, caption, dur, grad) -> Scene:
    st, u = ctx.style, ctx.u
    sc = Scene(ctx, dur, Backdrop(img, ctx, **motion(idx + 2)), pre=grad)
    card = Card(ctx, [dict(text=caption, kind=st["strong"], size=ctx.px(34), color=st["panel_text"], lead=1.12)],
                ctx.max_card_w, max_h=int(ctx.H * 0.3), rule=False)
    x, y = ctx.place(card.w, card.h, "bottom")
    sc.add(0.2, lambda d, dy: card.paint(d, x, y + dy))
    m = ctx.margin
    sc.add(0.0, lambda d, dy: draw_pill(d, ctx, m, m * 0.8, prop["name"], ctx.px(20), ctx.W * 0.62))
    sc.add(0.0, lambda d, dy: draw_pill(d, ctx, ctx.W - m, m * 0.8, f"{idx + 1} / {total}", ctx.px(20), ctx.W * 0.3,
                                         dot=False, right_align=True))
    return sc


def highlights_scene(ctx, imgs, items, dur) -> Scene:
    st, u = ctx.style, ctx.u
    sc = Scene(ctx, dur, Backdrop(imgs[2 % len(imgs)], ctx, dim=0.55, blur=4, **motion(3)))
    tw, gap = (ctx.W * 0.62 if ctx.landscape else ctx.W * 0.86), int(14 * u)
    tw = int(tw)
    head = Card(ctx, [dict(text="Property highlights", kind=st["title"], size=ctx.px(44), color=st["panel_text"])],
                tw, fixed_w=tw)
    row_h = int(64 * u)
    avail = ctx.H * 0.88 - head.h - gap
    k = min(1.0, avail / (len(items) * (row_h + gap)))
    row_h = int(row_h * k)
    total_h = head.h + gap + len(items) * (row_h + gap) - gap
    x0, y0 = (ctx.W - tw) // 2, (ctx.H - total_h) // 2
    sc.add(0.15, lambda d, dy: head.paint(d, x0, y0 + dy))
    for i, text in enumerate(items):
        ry = y0 + head.h + gap + i * (row_h + gap)
        font, text = fit_line(text, st["strong"], ctx.px(32), tw - 90 * u, ctx.px(22))

        def paint(d, dy, ry=ry, text=text, font=font):
            d.rounded_rectangle((x0, ry + dy, x0 + tw, ry + row_h + dy), radius=int(st["radius"] * u), fill=st["panel"])
            r = 8 * u
            d.ellipse((x0 + 26 * u, ry + row_h / 2 - r + dy, x0 + 26 * u + 2 * r, ry + row_h / 2 + r + dy), fill=st["accent"])
            fh = sum(font.getmetrics())
            d.text((x0 + 62 * u, ry + (row_h - fh) / 2 + dy), text, font=font, fill=st["panel_text"])
        sc.add(0.5 + 0.3 * i, paint)
    return sc


def contact_scene(ctx, imgs, prop, script, dur) -> Scene:
    st, u = ctx.style, ctx.u
    sc = Scene(ctx, dur, Backdrop(imgs[0], ctx, dim=0.5, blur=3, **motion(4)))
    tw, gap = ctx.wide_w if not ctx.landscape else int(ctx.W * 0.6), int(16 * u)
    top = Card(ctx, [
        dict(text="Enquire today", kind=st["strong"], size=ctx.px(20), color=st["accent"], gap=12),
        dict(text=prop["cta"], kind=st["title"], size=ctx.px(52), color=st["panel_text"], gap=12, lead=1.05),
        dict(text=script["closing"], kind=st["body"], size=ctx.px(24), color=st["muted"]),
    ], tw, fixed_w=tw, max_h=int(ctx.H * 0.5))
    contact_parts = [dict(text=line, kind=st["strong"], size=ctx.px(30), color=st["accent_text"], gap=4)
                     for line in prop["contact"].split("\n")]
    bottom = Card(ctx, contact_parts, tw, fixed_w=tw, rule=False, fill=st["accent"] + (255,), max_h=int(ctx.H * 0.3))
    total_h = top.h + gap + bottom.h
    x0, y0 = (ctx.W - tw) // 2, (ctx.H - total_h) // 2
    sc.add(0.2, lambda d, dy: top.paint(d, x0, y0 + dy))
    sc.add(0.8, lambda d, dy: bottom.paint(d, x0, y0 + top.h + gap + dy))
    footer = f"{prop['name']} · {prop['location']}"
    sc.add(1.3, lambda d, dy: draw_pill(d, ctx, ctx.W / 2, ctx.H - ctx.margin * 1.4 + dy, footer, ctx.px(20),
                                         ctx.W * 0.9, dot=True, center=True))
    return sc


# --------------------------------------------------------------------------- #
# Timeline, transitions, encoding
# --------------------------------------------------------------------------- #
def transition(a: Image.Image, b: Image.Image, p: float, kind: str) -> Image.Image:
    W, H = a.size
    e = ease_inout(p)
    if kind == "slide":
        out = Image.new("RGB", (W, H))
        off = int(W * e)
        out.paste(a, (-off, 0))
        out.paste(b, (W - off, 0))
        return out
    if kind == "zoom":
        s = 1 + 0.12 * (1 - e)
        w, h = W / s, H / s
        bz = b.resize((W, H), Image.BILINEAR, box=((W - w) / 2, (H - h) / 2, (W + w) / 2, (H + h) / 2))
        return Image.blend(a, bz, e)
    return Image.blend(a, b, e)


def find_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    raise VideoGenerationError(
        "FFmpeg was not found. Run 'pip install -r requirements.txt' (it installs a bundled FFmpeg) "
        "or install FFmpeg and add it to your PATH.")


def ffmpeg_available() -> bool:
    try:
        find_ffmpeg()
        return True
    except VideoGenerationError:
        return False


def _load_images(paths: list[Path]) -> list[Image.Image]:
    imgs = []
    for p in paths:
        try:
            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((2200, 2200), Image.LANCZOS)
                imgs.append(im.copy())
        except Exception as exc:
            raise VideoGenerationError(f"Could not read image '{Path(p).name}': {exc}") from exc
    return imgs


def build_scenes(ctx: Ctx, imgs, prop, script) -> list[Scene]:
    ds = ctx.style["dur_scale"]
    n = len(imgs)
    grad = bottom_gradient(ctx)
    highlights = script["highlights"][:6] or prop["features"][:6]
    scenes = [title_scene(ctx, imgs, prop, script, 3.8 * ds),
              details_scene(ctx, imgs, prop, 4.0 * ds)]
    scenes += [photo_scene(ctx, imgs[i], i, n, prop, script["captions"][i], 3.2 * ds, grad) for i in range(n)]
    scenes += [highlights_scene(ctx, imgs, highlights, (1.8 + 0.5 * len(highlights)) * ds),
               contact_scene(ctx, imgs, prop, script, 5.0 * ds)]
    return scenes


def generate_video(image_paths: list[Path], prop: dict, script: dict, style_key: str, aspect: str,
                   output_path: Path, music_path: Optional[Path] = None, fps: Optional[int] = None,
                   progress: ProgressFn = None) -> Path:
    """Render the promotional video and return the output path."""
    report = progress or (lambda p, m: None)
    if style_key not in STYLES:
        raise VideoGenerationError(f"Unknown video style '{style_key}'.")
    if aspect not in Config.ASPECT_RATIOS:
        raise VideoGenerationError(f"Unsupported aspect ratio '{aspect}'. Choose 16:9, 9:16 or 1:1.")
    ffmpeg = find_ffmpeg()
    fps = fps or Config.FPS
    W, H = Config.ASPECT_RATIOS[aspect]
    style = STYLES[style_key]
    ctx = Ctx(W, H, style)

    report(0.03, "Preparing images…")
    imgs = _load_images(image_paths)
    scenes = build_scenes(ctx, imgs, prop, script)

    tr = 0.6 if style["transition"] == "slide" else 0.8
    starts = [0.0]
    for s in scenes[:-1]:
        starts.append(starts[-1] + s.duration - tr)
    total = starts[-1] + scenes[-1].duration
    n_frames = int(total * fps)

    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "-"]
    if music_path:
        cmd += ["-stream_loop", "-1", "-i", str(music_path)]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart"]
    if music_path:
        cmd += ["-c:a", "aac", "-b:a", "160k",
                "-af", f"volume=0.55,afade=t=in:st=0:d=1.5,afade=t=out:st={max(0, total - 2.5):.2f}:d=2.5",
                "-map", "0:v:0", "-map", "1:a:0", "-t", f"{total:.3f}"]
    cmd += [str(output_path)]

    black = Image.new("RGB", (W, H), (0, 0, 0))
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
    err_text = ""
    try:
        for i in range(n_frames):
            T = i / fps
            k = max(j for j, s in enumerate(starts) if s <= T)
            if k > 0 and T < starts[k] + tr:
                a = scenes[k - 1].render(min(T - starts[k - 1], scenes[k - 1].duration))
                b = scenes[k].render(T - starts[k])
                frame = transition(a, b, (T - starts[k]) / tr, style["transition"])
            else:
                frame = scenes[k].render(min(T - starts[k], scenes[k].duration))
            if T < 0.5:
                frame = Image.blend(black, frame, T / 0.5)
            elif T > total - 0.7:
                frame = Image.blend(frame, black, clamp((T - (total - 0.7)) / 0.7))
            proc.stdin.write(frame.tobytes())
            if i % 6 == 0:
                report(0.08 + 0.88 * i / n_frames, f"Rendering video… {int(100 * i / n_frames)}%")
        proc.stdin.close()
        err_text = proc.stderr.read().decode(errors="replace")
        rc = proc.wait()
    except (BrokenPipeError, OSError):
        err_text = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        raise VideoGenerationError(f"FFmpeg stopped unexpectedly. {err_text.strip()[-400:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
    if rc != 0 or not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        raise VideoGenerationError(f"FFmpeg failed to encode the video. {err_text.strip()[-400:]}")
    report(1.0, "Done")
    return Path(output_path)
