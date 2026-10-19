"""
Widget Base Class and Cairo/Pango Drawing Utilities.
Provides local coordinate isolation, pure black high-contrast typography,
and adaptive visual scaling for E-Ink displays.
"""

import math
from typing import Tuple, Optional, Any, Dict
import cairo
import gi
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Pango, PangoCairo

from profiles import DeviceProfile

# Global Font Fallback Chain (Optimized for E-Ink legibility)
DEFAULT_FONT_FAMILY = "WenQuanYi Micro Hei, Segoe UI Emoji, Maple Mono NF CN, Noto Color Emoji, Segoe UI Symbol, sans-serif"

# Strict E-Ink High-Contrast Color Palette
INK_BLACK = (0.0, 0.0, 0.0)             # All text, numbers, and main borders MUST be pure black
INK_WHITE = (1.0, 1.0, 1.0)
INK_SHADOW = (0.42, 0.42, 0.42)         # 42% medium-dark gray for Neo-Brutalist shadow only
INK_TRACK_GRAY = (0.82, 0.82, 0.82)     # Light gray for progress bar track and subtle pills
INK_DIVIDER = (0.70, 0.70, 0.70)       # Crisp divider lines
INK_RED = (0.85, 0.0, 0.0)              # Red accent for 3-color EPDs

# Universal Layout Grid Margins
CARD_PAD_X = 18
CARD_PAD_Y = 16


def draw_rounded_rect(cr: cairo.Context, x: float, y: float, w: float, h: float, r: float):
    """Draw a rounded rectangle path"""
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def draw_pango_text(
    cr: cairo.Context,
    text: str,
    x: float,
    y: float,
    font_size: int,
    bold: bool = False,
    color: Tuple[float, float, float] = INK_BLACK,
    font_family: str = DEFAULT_FONT_FAMILY,
    align: Pango.Alignment = Pango.Alignment.LEFT,
    max_width: Optional[float] = None,
    wrap: bool = False,
    ellipsize: bool = True,
    line_spacing: int = 0
) -> Tuple[float, float]:
    """
    Renders high-contrast text using Pango & Cairo.
    Returns the (width, height) of the rendered layout in pixels.
    """
    layout = PangoCairo.create_layout(cr)
    font_desc = Pango.FontDescription(f"{font_family} {font_size}")
    if bold:
        font_desc.set_weight(Pango.Weight.BOLD)
    else:
        font_desc.set_weight(Pango.Weight.NORMAL)
    layout.set_font_description(font_desc)
    layout.set_text(text, -1)
    layout.set_alignment(align)
    if line_spacing > 0:
        layout.set_spacing(int(line_spacing * Pango.SCALE))

    if max_width is not None and max_width > 0:
        layout.set_width(int(max_width * Pango.SCALE))
        if wrap:
            layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        elif ellipsize:
            layout.set_ellipsize(Pango.EllipsizeMode.END)

    ink_rect, log_rect = layout.get_pixel_extents()
    w = log_rect.width
    h = log_rect.height

    cr.save()
    cr.set_source_rgb(*color)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)
    cr.restore()

    return w, h


def draw_pango_text_right(
    cr: cairo.Context,
    text: str,
    right_x: float,
    y: float,
    font_size: int,
    bold: bool = False,
    color: Tuple[float, float, float] = INK_BLACK,
    font_family: str = DEFAULT_FONT_FAMILY,
    max_width: Optional[float] = None
) -> Tuple[float, float]:
    """
    Renders text aligned to right_x (so text ends precisely at right_x).
    Guarantees consistent right-margin alignment without magic offset constants.
    """
    layout = PangoCairo.create_layout(cr)
    font_desc = Pango.FontDescription(f"{font_family} {font_size}")
    font_desc.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
    layout.set_font_description(font_desc)
    layout.set_text(text, -1)

    if max_width is not None and max_width > 0:
        layout.set_width(int(max_width * Pango.SCALE))
        layout.set_ellipsize(Pango.EllipsizeMode.END)

    _, log_rect = layout.get_pixel_extents()
    w = log_rect.width
    h = log_rect.height

    cr.save()
    cr.set_source_rgb(*color)
    cr.move_to(right_x - w, y)
    PangoCairo.show_layout(cr, layout)
    cr.restore()

    return w, h


def draw_badge_pill(
    cr: cairo.Context,
    text: str,
    x: float,
    y: float,
    font_size: int = 13,
    pad_h: float = 10.0,
    pad_v: float = 4.0,
    height: float = 26.0,
    radius: float = 4.0,
    bg_color: Tuple[float, float, float] = INK_BLACK,
    text_color: Tuple[float, float, float] = INK_WHITE,
    font_family: str = DEFAULT_FONT_FAMILY
) -> Tuple[float, float]:
    """
    Dynamically measures text ink extents and renders a pill badge where text
    is mathematically centered and never overflows or clips the pill border.
    Returns (badge_w, badge_h).
    """
    layout = PangoCairo.create_layout(cr)
    font_desc = Pango.FontDescription(f"{font_family} {font_size}")
    font_desc.set_weight(Pango.Weight.BOLD)
    layout.set_font_description(font_desc)
    layout.set_text(text, -1)

    ink_rect, log_rect = layout.get_pixel_extents()
    tw = max(log_rect.width, ink_rect.width)
    badge_w = tw + pad_h * 2
    badge_h = max(height, log_rect.height + pad_v * 2)

    cr.save()
    draw_rounded_rect(cr, x, y, badge_w, badge_h, radius)
    cr.set_source_rgb(*bg_color)
    cr.fill()

    tx = x + (badge_w - ink_rect.width) / 2.0 - ink_rect.x
    ty = y + (badge_h - ink_rect.height) / 2.0 - ink_rect.y
    cr.set_source_rgb(*text_color)
    cr.move_to(tx, ty)
    PangoCairo.show_layout(cr, layout)
    cr.restore()

    return float(badge_w), float(badge_h)


def draw_hero_text(
    cr: cairo.Context,
    text: str,
    x: float,
    y: float,
    font_size: int,
    bold: bool = True,
    color: Tuple[float, float, float] = INK_BLACK,
    font_family: str = DEFAULT_FONT_FAMILY
) -> Tuple[float, float]:
    """
    Renders large display numbers/text anchored by their true ink bounding box (ink_rect),
    eliminating Pango's internal top/left font leading so giant numbers never sink or clip.
    Returns (ink_width, ink_height).
    """
    layout = PangoCairo.create_layout(cr)
    font_desc = Pango.FontDescription(f"{font_family} {font_size}")
    font_desc.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
    layout.set_font_description(font_desc)
    layout.set_text(text, -1)

    ink_rect, _ = layout.get_pixel_extents()

    cr.save()
    cr.set_source_rgb(*color)
    cr.move_to(x - ink_rect.x, y - ink_rect.y)
    PangoCairo.show_layout(cr, layout)
    cr.restore()

    return float(ink_rect.width), float(ink_rect.height)


def draw_checkbox(
    cr: cairo.Context,
    x: float,
    y: float,
    size: float = 18.0,
    checked: bool = False
):
    """
    Draws a crisp geometric checkbox with a mathematically centered vector checkmark.
    """
    cr.save()
    draw_rounded_rect(cr, x, y, size, size, 3.0)
    if checked:
        cr.set_source_rgb(*INK_BLACK)
        cr.fill_preserve()
        cr.set_line_width(1.4)
        cr.stroke()

        # Pure white vector checkmark centered inside the box
        cr.set_source_rgb(*INK_WHITE)
        cr.set_line_width(2.2)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.move_to(x + size * 0.22, y + size * 0.52)
        cr.line_to(x + size * 0.43, y + size * 0.74)
        cr.line_to(x + size * 0.78, y + size * 0.27)
        cr.stroke()
    else:
        cr.set_source_rgb(*INK_WHITE)
        cr.fill_preserve()
        cr.set_source_rgb(*INK_BLACK)
        cr.set_line_width(1.6)
        cr.stroke()
    cr.restore()


def draw_task_text(
    cr: cairo.Context,
    text: str,
    x: float,
    y: float,
    font_size: int,
    max_width: float,
    done: bool = False,
    color: Tuple[float, float, float] = INK_BLACK,
    font_family: str = DEFAULT_FONT_FAMILY
) -> Tuple[float, float]:
    """
    Renders a single or multi-line wrapped task item.
    When done=True, draws per-line strikethrough matching each individual line's exact ink width.
    Returns (layout_width, layout_height).
    """
    layout = PangoCairo.create_layout(cr)
    font_desc = Pango.FontDescription(f"{font_family} {font_size}")
    font_desc.set_weight(Pango.Weight.NORMAL if done else Pango.Weight.BOLD)
    layout.set_font_description(font_desc)
    layout.set_text(text, -1)
    if max_width > 0:
        layout.set_width(int(max_width * Pango.SCALE))
        layout.set_wrap(Pango.WrapMode.WORD_CHAR)
        layout.set_spacing(int(3 * Pango.SCALE))

    _, log_rect = layout.get_pixel_extents()

    cr.save()
    cr.set_source_rgb(*color)
    cr.move_to(x, y)
    PangoCairo.show_layout(cr, layout)

    if done:
        cr.set_source_rgb(*INK_BLACK)
        cr.set_line_width(1.4)
        it = layout.get_iter()
        while True:
            ink_ext, log_ext = it.get_line_extents()
            lx = x + (ink_ext.x / Pango.SCALE)
            lw = ink_ext.width / Pango.SCALE
            ly = y + (log_ext.y / Pango.SCALE) + (log_ext.height / Pango.SCALE) * 0.52
            if lw > 0:
                cr.move_to(lx, ly)
                cr.line_to(lx + lw, ly)
                cr.stroke()
            if not it.next_line():
                break

    cr.restore()
    return float(log_rect.width), float(log_rect.height)


def draw_dotted_kv_row(
    cr: cairo.Context,
    label: str,
    value: str,
    x: float,
    y: float,
    w: float,
    row_h: float = 28.0,
    label_size: int = 14,
    val_size: int = 15,
    color: Tuple[float, float, float] = INK_BLACK
):
    """
    Renders a clean Bauhaus two-column key-value row with a dotted leader line,
    avoiding heavy nested boxes while keeping left/right alignment crisp.
    """
    lw, lh = draw_pango_text(cr, label, x, y + (row_h - label_size - 4) / 2, label_size, bold=False, color=color)
    vw, vh = draw_pango_text_right(cr, value, x + w, y + (row_h - val_size - 4) / 2, val_size, bold=True, color=color)

    dot_start = x + lw + 10
    dot_end = x + w - vw - 10
    if dot_end > dot_start + 8:
        mid_y = y + row_h * 0.54
        cr.save()
        cr.set_source_rgb(*INK_DIVIDER)
        cr.set_line_width(1.2)
        cr.set_dash([2.0, 4.0])
        cr.move_to(dot_start, mid_y)
        cr.line_to(dot_end, mid_y)
        cr.stroke()
        cr.restore()


def draw_weather_icon(
    cr: cairo.Context,
    desc: str,
    x: float,
    y: float,
    size: float = 48.0,
    color: Tuple[float, float, float] = INK_BLACK
) -> Tuple[float, float]:
    """
    Draws a high-contrast pure black geometric vector weather icon inside (x, y, size, size).
    Eliminates muddy grayscale bitmap emojis and guarantees exact bounding-box width.
    """
    cr.save()
    cr.new_path()
    cr.set_source_rgb(*color)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    lw = max(2.2, size * 0.055)
    cr.set_line_width(lw)

    cx = x + size * 0.5
    cy = y + size * 0.5
    r = size * 0.24

    def _draw_cloud(ox: float, oy: float, s: float):
        cr.new_sub_path()
        cr.arc(ox - s * 0.18, oy + s * 0.06, s * 0.16, math.pi * 0.5, math.pi * 1.45)
        cr.arc(ox - s * 0.02, oy - s * 0.08, s * 0.20, math.pi * 1.05, math.pi * 1.95)
        cr.arc(ox + s * 0.20, oy + s * 0.04, s * 0.15, math.pi * 1.5, math.pi * 0.5)
        cr.close_path()
        cr.set_source_rgb(*INK_WHITE)
        cr.fill_preserve()
        cr.set_source_rgb(*color)
        cr.stroke()

    if "晴" in desc and "云" not in desc:
        # Crisp Bauhaus Sun
        cr.new_sub_path()
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()
        for i in range(8):
            ang = i * (math.pi / 4.0)
            r1 = r + size * 0.07
            r2 = r + size * 0.18
            cr.move_to(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1)
            cr.line_to(cx + math.cos(ang) * r2, cy + math.sin(ang) * r2)
        cr.stroke()
    elif "雨" in desc or "雷" in desc:
        _draw_cloud(cx, cy - size * 0.08, size * 0.9)
        # Raindrops / Lightning
        for i, dx in enumerate([-0.18, 0.0, 0.18]):
            rx_pos = cx + size * dx
            ry_pos = cy + size * 0.16
            cr.move_to(rx_pos, ry_pos)
            cr.line_to(rx_pos - size * 0.06, ry_pos + size * 0.18)
        cr.stroke()
    elif "雪" in desc:
        _draw_cloud(cx, cy - size * 0.08, size * 0.9)
        for dx in [-0.16, 0.0, 0.16]:
            sx = cx + size * dx
            sy = cy + size * 0.24
            sr = size * 0.05
            cr.move_to(sx - sr, sy)
            cr.line_to(sx + sr, sy)
            cr.move_to(sx, sy - sr)
            cr.line_to(sx, sy + sr)
        cr.stroke()
    elif "雾" in desc or "霾" in desc or "尘" in desc or "沙" in desc:
        # Crisp atmospheric haze/mist icon: upper half cloud/sun arc + 3 horizontal mist waves
        cr.new_sub_path()
        cr.arc(cx, cy - size * 0.06, size * 0.20, math.pi, 2 * math.pi)
        cr.stroke()
        for idx, dy in enumerate([0.04, 0.18, 0.32]):
            ly = cy + size * dy
            half_w = size * (0.34 if idx != 2 else 0.24)
            cr.move_to(cx - half_w, ly)
            cr.line_to(cx + half_w, ly)
        cr.stroke()
    else:
        # Partly cloudy / Cloudy
        if "多云" in desc:
            sx, sy, sr = cx - size * 0.16, cy - size * 0.14, size * 0.14
            cr.new_sub_path()
            cr.arc(sx, sy, sr, 0, 2 * math.pi)
            cr.stroke()
        _draw_cloud(cx + size * 0.04, cy + size * 0.04, size * 0.92)

    cr.restore()
    return float(size), float(size)


class WidgetBase:
    """Base class for all modular dashboard widgets"""

    id: str = "base"
    name: str = "Base Widget"
    description: str = "Base widget description"

    def render(
        self,
        cr: cairo.Context,
        w: int,
        h: int,
        slot_type: str,
        context: Dict[str, Any],
        profile: DeviceProfile
    ):
        """
        Draw widget content inside local boundaries (0, 0, w, h).
        Local origin (0, 0) is already translated and isolated.
        :param slot_type: 'full' | 'half_v' | 'half_h' | 'quadrant'
        """
        raise NotImplementedError

