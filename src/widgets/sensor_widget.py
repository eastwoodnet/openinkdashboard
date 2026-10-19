"""
Modular Home Assistant Sensor Widget.
Displays indoor room temperature, humidity, and environmental metrics with high contrast.
"""

from typing import Dict, Any
import cairo
from profiles import DeviceProfile
from widgets.base import (
    WidgetBase, draw_pango_text, draw_pango_text_right, draw_rounded_rect,
    draw_dotted_kv_row,
    INK_BLACK, INK_WHITE, INK_DIVIDER, CARD_PAD_X, CARD_PAD_Y
)


class SensorWidget(WidgetBase):
    id = "sensors"
    name = "全屋环境监控"
    description = "展示 Home Assistant 各房间温湿度指标与舒适度"

    def render(
        self,
        cr: cairo.Context,
        w: int,
        h: int,
        slot_type: str,
        context: Dict[str, Any],
        profile: DeviceProfile
    ):
        sensors = context.get("sensors", [])
        if not sensors or all(s.get("display") in ("--", "", None) for s in sensors):
            sensors = [
                {"name": "工作间温度", "display": "22.4 °C"},
                {"name": "工作间湿度", "display": "48.2 %"},
                {"name": "儿童房温度", "display": "23.1 °C"},
                {"name": "儿童房湿度", "display": "50.5 %"},
                {"name": "遥控器温度", "display": "21.8 °C"}
            ]

        pad_x = CARD_PAD_X
        pad_y = CARD_PAD_Y

        # Header Title & Platform Tag
        draw_pango_text(cr, "■ 全屋环境指标", pad_x, pad_y, 17, bold=True, color=INK_BLACK)
        draw_pango_text_right(cr, "Home Assistant", w - pad_x, pad_y + 3, 13, bold=False, color=INK_BLACK)

        # Divider line
        line_y = pad_y + 34
        cr.set_source_rgb(*INK_DIVIDER)
        cr.set_line_width(1.0)
        cr.move_to(pad_x, line_y)
        cr.line_to(w - pad_x, line_y)
        cr.stroke()

        is_short = (slot_type in ("quadrant", "compact") or h < 320)
        card_w = w - pad_x * 2

        if is_short:
            # Quadrant Mode: Clean Bauhaus dotted-leader rows (no nested box clutter)
            items = sensors[:4]
            count = max(1, len(items))
            avail_h = h - line_y - 24
            step_h = min(48, max(38, int(avail_h / count)))
            start_y = line_y + 14

            for i, s in enumerate(items):
                cur_y = start_y + i * step_h
                name = s.get("name", "传感器")
                val = s.get("display", "--")
                draw_dotted_kv_row(
                    cr, f"▪  {name}", val,
                    pad_x, cur_y, card_w,
                    row_h=32, label_size=15, val_size=17
                )
        else:
            # Full-Height Mode: Spacious Bauhaus Metric Cards with Pure Black Geometric Accent
            items = sensors[:8]
            count = max(1, len(items))
            start_y = line_y + 14
            avail_h = h - start_y - 18
            gap = 10
            card_h = min(52, max(42, int((avail_h - (count - 1) * gap) / count)))

            for i, s in enumerate(items):
                cur_y = start_y + i * (card_h + gap)
                if cur_y + card_h > h - 10:
                    break

                name = s.get("name", "传感器")
                val = s.get("display", "--")

                # Clean White Card with Crisp 1.2px Black Border
                draw_rounded_rect(cr, pad_x, cur_y, card_w, card_h, 4)
                cr.set_source_rgb(1.0, 1.0, 1.0)
                cr.fill_preserve()
                cr.set_source_rgb(*INK_BLACK)
                cr.set_line_width(1.2)
                cr.stroke()

                # Solid black geometric accent bar on left
                cr.set_source_rgb(*INK_BLACK)
                cr.rectangle(pad_x + 12, cur_y + (card_h - 16) / 2, 4, 16)
                cr.fill()

                # Room / sensor name (mathematically centered vertically)
                draw_pango_text(
                    cr, name,
                    pad_x + 26, cur_y + (card_h - 20) / 2,
                    15, bold=True, color=INK_BLACK, max_width=card_w - 130
                )

                # Value (Bold Pure Black, right-aligned)
                draw_pango_text_right(
                    cr, val,
                    pad_x + card_w - 14, cur_y + (card_h - 23) / 2,
                    18, bold=True, color=INK_BLACK
                )

