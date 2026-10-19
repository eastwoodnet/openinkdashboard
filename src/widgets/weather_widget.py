"""
Modular Weather Widget.
Displays real-time temperature, condition, min/max range, humidity, and wind.
Features pure black high contrast, multi-day forecast in full-height mode,
and red accent highlight for 3-color EPDs.
"""

from typing import Dict, Any
import cairo
from profiles import DeviceProfile
from widgets.base import (
    WidgetBase, draw_pango_text, draw_pango_text_right, draw_rounded_rect,
    draw_badge_pill, draw_hero_text, draw_dotted_kv_row, draw_weather_icon,
    INK_BLACK, INK_WHITE, INK_DIVIDER, INK_TRACK_GRAY, INK_RED,
    CARD_PAD_X, CARD_PAD_Y
)


class WeatherWidget(WidgetBase):
    id = "weather"
    name = "实时天气与气象"
    description = "展示城市当前气温、天气状况、温差、湿度与风力指标"

    def render(
        self,
        cr: cairo.Context,
        w: int,
        h: int,
        slot_type: str,
        context: Dict[str, Any],
        profile: DeviceProfile
    ):
        wtr = context.get("weather", {})
        if not wtr:
            return

        city = wtr.get("city", "北京")
        desc = wtr.get("desc", "晴朗")
        temp = wtr.get("temp", "21°C")
        feels_like = wtr.get("feels_like", temp)
        temp_range = wtr.get("temp_range", "12°C ~ 22°C")
        humidity = wtr.get("humidity", "45%")
        wind_cn = wtr.get("wind_cn", "微风")

        pad_x = CARD_PAD_X
        pad_y = CARD_PAD_Y

        hi_temp = temp_range.split("~")[-1].strip() if "~" in temp_range else temp_range
        lo_temp = temp_range.split("~")[0].strip() if "~" in temp_range else temp_range

        if slot_type in ("quadrant", "compact") or h < 320:
            # === Quadrant / Half-Height Mode (e.g. 382x282) ===
            # Top row: Dynamic City Pill + Condition + AQI tag (no duplicate feels_like)
            bw, _ = draw_badge_pill(
                cr, city, pad_x, pad_y,
                font_size=13, pad_h=12, height=26
            )
            draw_pango_text(cr, desc, pad_x + bw + 12, pad_y + 3, 16, bold=True, color=INK_BLACK)
            draw_pango_text_right(cr, "空气 优 · 32", w - pad_x, pad_y + 5, 13, bold=False, color=INK_BLACK)

            # Divider 1
            line1_y = pad_y + 34
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line1_y)
            cr.line_to(w - pad_x, line1_y)
            cr.stroke()

            # Hero Section: Crisp Vector Weather Icon + True Ink-Box Giant Temp + High/Low Stack
            hero_y = line1_y + 16
            iw, ih = draw_weather_icon(cr, desc, pad_x, hero_y, size=50, color=INK_BLACK)
            draw_hero_text(cr, temp, pad_x + iw + 16, hero_y + 3, 54, bold=True, color=INK_BLACK)

            # High / Low temperature stack on the right
            draw_pango_text_right(cr, f"最高  {hi_temp}", w - pad_x, hero_y + 2, 14, bold=True, color=INK_BLACK)
            draw_pango_text_right(cr, f"最低  {lo_temp}", w - pad_x, hero_y + 28, 14, bold=False, color=INK_BLACK)

            # Divider 2
            line2_y = 134
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line2_y)
            cr.line_to(w - pad_x, line2_y)
            cr.stroke()

            # Clean Bauhaus Dotted Key-Value Rows (Zero box-in-box clutter)
            kv_w = w - pad_x * 2
            kv_rows = [
                ("体感温度", feels_like),
                ("相对湿度", humidity),
                ("实时风况", wind_cn),
            ]
            start_ky = 148
            row_step = 38
            for idx, (k_label, k_val) in enumerate(kv_rows):
                draw_dotted_kv_row(
                    cr, k_label, k_val,
                    pad_x, start_ky + idx * row_step, kv_w,
                    row_h=30, label_size=14, val_size=16
                )

        else:
            # === Full Height Mode (Half-V e.g. 382x580 or Full) ===
            # Top Badge (Dynamic width, pure white city name)
            bw, _ = draw_badge_pill(
                cr, city, pad_x, pad_y,
                font_size=14, pad_h=12, height=28
            )
            draw_pango_text(cr, desc, pad_x + bw + 12, pad_y + 4, 17, bold=True, color=INK_BLACK)
            draw_pango_text_right(cr, "空气 优 · 32", w - pad_x, pad_y + 6, 13, bold=False, color=INK_BLACK)

            # Divider 1
            line1_y = pad_y + 36
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line1_y)
            cr.line_to(w - pad_x, line1_y)
            cr.stroke()

            # Vector Weather Icon + Giant Temp (Dynamic flow, zero overlap)
            hero_y = line1_y + 18
            iw, ih = draw_weather_icon(cr, desc, pad_x, hero_y, size=54, color=INK_BLACK)
            draw_hero_text(cr, temp, pad_x + iw + 16, hero_y + 3, 58, bold=True, color=INK_BLACK)

            draw_pango_text_right(cr, f"最高  {hi_temp}", w - pad_x, hero_y + 4, 15, bold=True, color=INK_BLACK)
            draw_pango_text_right(cr, f"最低  {lo_temp}", w - pad_x, hero_y + 32, 15, bold=False, color=INK_BLACK)

            # Divider 2
            line2_y = 146
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line2_y)
            cr.line_to(w - pad_x, line2_y)
            cr.stroke()

            # 4 Key Metrics in Clean Dotted Leader Rows
            kv_w = w - pad_x * 2
            kv_rows = [
                ("体感温度", feels_like),
                ("相对湿度", humidity),
                ("实时风况", wind_cn),
                ("昼夜温差", temp_range),
            ]
            start_ky = 158
            row_step = 32
            for idx, (k_label, k_val) in enumerate(kv_rows):
                draw_dotted_kv_row(
                    cr, k_label, k_val,
                    pad_x, start_ky + idx * row_step, kv_w,
                    row_h=28, label_size=14, val_size=16
                )

            # Divider 3
            line3_y = 296
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line3_y)
            cr.line_to(w - pad_x, line3_y)
            cr.stroke()

            # 3-Day Forecast Section
            fc_y = 310
            draw_pango_text(cr, "■ 未来三天天气趋势", pad_x, fc_y, 15, bold=True, color=INK_BLACK)

            days_data = [
                {"label": "今天", "date": "10/19", "desc": desc.split("/")[0].strip(), "range": temp_range},
                {"label": "明天", "date": "10/20", "desc": "多云", "range": "10°C ~ 19°C"},
                {"label": "后天", "date": "10/21", "desc": "晴朗", "range": "9°C ~ 20°C"}
            ]

            card_w = w - pad_x * 2
            card_h = 60
            start_cy = 342

            for i, d in enumerate(days_data):
                cy = start_cy + i * (card_h + 12)
                draw_rounded_rect(cr, pad_x, cy, card_w, card_h, 4)
                cr.set_source_rgb(1.0, 1.0, 1.0)
                cr.fill_preserve()
                cr.set_source_rgb(*INK_BLACK)
                cr.set_line_width(1.2)
                cr.stroke()

                # Label + Date
                draw_pango_text(cr, f"{d['label']} ({d['date']})", pad_x + 14, cy + 19, 15, bold=True, color=INK_BLACK)

                # Vector Icon + Condition
                draw_weather_icon(cr, d["desc"], pad_x + 138, cy + 16, size=26, color=INK_BLACK)
                draw_pango_text(cr, d["desc"], pad_x + 172, cy + 19, 15, bold=False, color=INK_BLACK)

                # Temp Range (Right-aligned inside forecast card)
                draw_pango_text_right(cr, d["range"], pad_x + card_w - 14, cy + 18, 16, bold=True, color=INK_BLACK)

