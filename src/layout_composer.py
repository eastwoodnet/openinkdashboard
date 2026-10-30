"""
Modular Layout Composer for Hanvon N516 (800x600 · 16-Level Grayscale E-Ink).
Supports 5 core slot templates:
- 2_1: 左二右一 (Left 2 Quadrants + Right 1 Full-Height)
- 1_2: 左一右二 (Left 1 Full-Height + Right 2 Quadrants)
- 2x2: 对称四分屏 (4 Quadrants)
- 1x2: 左右双栏 (2 Full-Height Columns)
- 1x1: 全屏单卡大画报 / 即时通知覆盖 (Full Screen)
"""

import os
import time
from typing import Dict, Any, List, Optional
import cairo
from PIL import Image

from profiles import DeviceProfile, get_profile
from widgets.base import WidgetBase, draw_rounded_rect, INK_SHADOW
from widgets.calendar_widget import CalendarWidget
from widgets.weather_widget import WeatherWidget
from widgets.todo_widget import TodoWidget
from widgets.sensor_widget import SensorWidget
from widgets.focus_widget import FocusWidget, AlertWidget
from widgets.agenda_widget import AgendaWidget
from plugins import PLUGIN_WIDGETS

# Global Registry of Available Widgets (Core + External Plugins)
WIDGET_REGISTRY: Dict[str, WidgetBase] = {
    "calendar": CalendarWidget(),
    "weather": WeatherWidget(),
    "todo": TodoWidget(),
    "sensors": SensorWidget(),
    "focus": FocusWidget(),
    "alert": AlertWidget(),
    "agenda": AgendaWidget(),
    **PLUGIN_WIDGETS,
}

# Standard 5-Page N516 Dashboard Playlist
DEFAULT_PLAYLIST: List[Dict[str, Any]] = [
    {
        "num": "01",
        "name": "daily_focus",
        "title": "今日聚焦 (2|1 左二右一)",
        "template": "2_1",
        "slots": {
            "top_left": "calendar",
            "bottom_left": "weather",
            "right": "todo"
        }
    },
    {
        "num": "02",
        "name": "month_environment",
        "title": "月历与全屋监控 (1|2 左一右二)",
        "template": "1_2",
        "slots": {
            "left": "calendar",
            "top_right": "weather",
            "bottom_right": "sensors"
        }
    },
    {
        "num": "03",
        "name": "classic_dashboard",
        "title": "经典四分屏 (2×2 对称四象限)",
        "template": "2x2",
        "slots": {
            "top_left": "calendar",
            "top_right": "weather",
            "bottom_left": "sensors",
            "bottom_right": "todo"
        }
    },
    {
        "num": "04",
        "name": "forecast_missions",
        "title": "气象趋势与任务推进 (1×2 左右双栏)",
        "template": "1x2",
        "slots": {
            "left": "weather",
            "right": "todo"
        }
    },
    {
        "num": "05",
        "name": "broadside_focus",
        "title": "全屏焦点大画报 (1×1 单卡大屏)",
        "template": "1x1",
        "slots": {
            "full": "focus"
        }
    }
]


class LayoutComposer:
    def __init__(self, profile: DeviceProfile = None):
        self.profile = profile or get_profile("n516")

    def get_template_slots(self, template_id: str, pad: float = 10.0, gap: float = 8.0) -> List[Dict[str, Any]]:
        """
        Calculates bounding boxes for slots in the 800x600 logical canvas.
        Returns list of {'id': slot_id, 'type': slot_type, 'x': x, 'y': y, 'w': w, 'h': h}
        """
        W = self.profile.width
        H = self.profile.height

        col_w = (W - pad * 2 - gap) / 2
        col_h = H - pad * 2
        half_h = (H - pad * 2 - gap) / 2

        if template_id == "1x1":
            return [
                {"id": "full", "type": "full", "x": pad, "y": pad, "w": W - pad * 2, "h": H - pad * 2}
            ]
        elif template_id == "1x2":
            return [
                {"id": "left", "type": "half_v", "x": pad, "y": pad, "w": col_w, "h": col_h},
                {"id": "right", "type": "half_v", "x": pad + col_w + gap, "y": pad, "w": col_w, "h": col_h}
            ]
        elif template_id == "2x2":
            return [
                {"id": "top_left", "type": "quadrant", "x": pad, "y": pad, "w": col_w, "h": half_h},
                {"id": "top_right", "type": "quadrant", "x": pad + col_w + gap, "y": pad, "w": col_w, "h": half_h},
                {"id": "bottom_left", "type": "quadrant", "x": pad, "y": pad + half_h + gap, "w": col_w, "h": half_h},
                {"id": "bottom_right", "type": "quadrant", "x": pad + col_w + gap, "y": pad + half_h + gap, "w": col_w, "h": half_h}
            ]
        elif template_id == "2_1":
            return [
                {"id": "top_left", "type": "quadrant", "x": pad, "y": pad, "w": col_w, "h": half_h},
                {"id": "bottom_left", "type": "quadrant", "x": pad, "y": pad + half_h + gap, "w": col_w, "h": half_h},
                {"id": "right", "type": "half_v", "x": pad + col_w + gap, "y": pad, "w": col_w, "h": col_h}
            ]
        elif template_id == "1_2":
            return [
                {"id": "left", "type": "half_v", "x": pad, "y": pad, "w": col_w, "h": col_h},
                {"id": "top_right", "type": "quadrant", "x": pad + col_w + gap, "y": pad, "w": col_w, "h": half_h},
                {"id": "bottom_right", "type": "quadrant", "x": pad + col_w + gap, "y": pad + half_h + gap, "w": col_w, "h": half_h}
            ]
        else:
            return self.get_template_slots("2_1", pad, gap)

    def render_screen(
        self,
        template_id: str,
        slot_assignments: Dict[str, str],
        context: Dict[str, Any],
        output_path: Optional[str] = None,
        rotate: bool = False
    ) -> Image.Image:
        """
        Renders a composite 800x600 screen using the given layout template and slot mappings.
        :param rotate: If True, rotates 90° clockwise to 600x800 for N516 Xfbdev framebuffer.
                       If False (default), preserves 800x600 landscape orientation for Web preview.
        """
        W = self.profile.width
        H = self.profile.height

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        cr = cairo.Context(surface)

        # Clear background to pure white
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.paint()

        slots = self.get_template_slots(template_id)

        for slot_info in slots:
            sid = slot_info["id"]
            stype = slot_info["type"]
            x = slot_info["x"]
            y = slot_info["y"]
            w = slot_info["w"]
            h = slot_info["h"]

            widget_key = slot_assignments.get(sid)
            widget = WIDGET_REGISTRY.get(widget_key) or PLUGIN_WIDGETS.get(widget_key)

            # === Neo-Brutalist Card Decorator ===
            card_r = 6.0
            shadow_off = 5.0

            # 1. Medium-dark gray drop shadow (42% gray)
            draw_rounded_rect(cr, x + shadow_off, y + shadow_off, w, h, card_r)
            cr.set_source_rgb(*INK_SHADOW)
            cr.fill()

            # 2. Pure white card background
            draw_rounded_rect(cr, x, y, w, h, card_r)
            cr.set_source_rgb(1.0, 1.0, 1.0)
            cr.fill_preserve()

            # 3. Crisp 1.8px black single-line border
            cr.set_source_rgb(0.0, 0.0, 0.0)
            cr.set_line_width(1.8)
            cr.stroke()

            # 4. Render Widget inside translated & clipped local coordinate system
            if widget:
                cr.save()
                cr.translate(x, y)
                draw_rounded_rect(cr, 1, 1, w - 2, h - 2, card_r)
                cr.clip()
                widget.render(cr, int(w), int(h), stype, context, self.profile)
                cr.restore()

        surface.flush()
        buf = surface.get_data()
        stride = surface.get_stride()
        img = Image.frombuffer("RGBA", (W, H), buf, "raw", "BGRA", stride, 1)

        if rotate:
            if self.profile.rotation == 270:
                img = img.transpose(Image.Transpose.ROTATE_90)
            elif self.profile.rotation == 180:
                img = img.transpose(Image.Transpose.ROTATE_180)
            elif self.profile.rotation == 0:
                pass
            else:  # 90° (default for N516)
                img = img.transpose(Image.Transpose.ROTATE_270)

        # 16-level grayscale compact quantization for N516
        gray_img = img.convert("L")
        gray_img = gray_img.point(lambda p: (p // 17) * 17)
        final_img = gray_img.convert("P", palette=Image.Palette.ADAPTIVE, colors=16)

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            final_img.save(output_path, "PNG", optimize=True)

        return final_img

    def render_alert_screen(
        self,
        title: str,
        text: str,
        sender: str = "快捷指令",
        duration_min: int = 15,
        output_path: Optional[str] = None,
        rotate: bool = True
    ) -> Image.Image:
        """
        Renders a 1x1 full-screen priority alert card using FocusWidget.
        """
        alert_ctx = {
            "alert": {
                "title": title,
                "body": text,
                "sender": sender,
                "time": time.strftime("%H:%M"),
                "timeout": duration_min * 60
            }
        }
        return self.render_screen(
            template_id="1x1",
            slot_assignments={"full": "focus"},
            context=alert_ctx,
            output_path=output_path,
            rotate=rotate
        )
