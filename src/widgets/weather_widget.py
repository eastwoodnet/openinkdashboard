"""
Modular Weather Widget.
Displays real-time temperature, condition, min/max range, humidity, and wind.
Features pure black high contrast and real multi-day forecasts in full-height mode.
"""

from typing import Dict, Any
import cairo
from profiles import DeviceProfile
from widgets.base import (
    WidgetBase, draw_pango_text, draw_pango_text_right, draw_rounded_rect,
    draw_badge_pill, draw_hero_text, draw_dotted_kv_row, draw_weather_icon,
    INK_BLACK, INK_DIVIDER, CARD_PAD_X, CARD_PAD_Y
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

        city = wtr.get("city", "--")
        desc = wtr.get("desc", "天气不可用")
        temp = wtr.get("temp", "--°C")
        feels_like = wtr.get("feels_like", "--°C")
        temp_range = wtr.get("temp_range", "--°C ~ --°C")
        humidity = wtr.get("humidity", "--%")
        wind_cn = wtr.get("wind_cn", "--")
        forecast = wtr.get("forecast") or []

        pad_x = CARD_PAD_X
        pad_y = CARD_PAD_Y

        hi_temp = temp_range.split("~")[-1].strip() if "~" in temp_range else temp_range
        lo_temp = temp_range.split("~")[0].strip() if "~" in temp_range else temp_range

        if slot_type in ("quadrant", "compact") or h < 320:
            # === Quadrant / Half-Height Mode ===
            bw, _ = draw_badge_pill(
                cr, city, pad_x, pad_y,
                font_size=13, pad_h=12, height=26
            )
            desc_x = pad_x + bw + 12
            draw_pango_text(
                cr, desc, desc_x, pad_y + 3, 16, bold=True, color=INK_BLACK,
                max_width=w - desc_x - pad_x
            )

            line1_y = pad_y + 34
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line1_y)
            cr.line_to(w - pad_x, line1_y)
            cr.stroke()

            hero_y = line1_y + 16
            iw, ih = draw_weather_icon(cr, desc, pad_x, hero_y, size=50, color=INK_BLACK)
            draw_hero_text(cr, temp, pad_x + iw + 16, hero_y + 3, 54, bold=True, color=INK_BLACK)

            draw_pango_text_right(cr, f"最高  {hi_temp}", w - pad_x, hero_y + 2, 14, bold=True, color=INK_BLACK)
            draw_pango_text_right(cr, f"最低  {lo_temp}", w - pad_x, hero_y + 28, 14, bold=False, color=INK_BLACK)

            line2_y = 134
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line2_y)
            cr.line_to(w - pad_x, line2_y)
            cr.stroke()

            kv_w = w - pad_x * 2
            kv_rows = [
                ("体感温度", feels_like),
                ("相对湿度", humidity),
                ("实时风况", wind_cn),
            ]
            start_ky = 146
            available_h = h - start_ky - pad_y
            row_step = min(38, max(30, int((available_h - 30) / 2)))
            for idx, (k_label, k_val) in enumerate(kv_rows):
                draw_dotted_kv_row(
                    cr, k_label, k_val,
                    pad_x, start_ky + idx * row_step, kv_w,
                    row_h=30, label_size=14, val_size=16
                )

        else:
            # === Full Height Mode ===
            bw, _ = draw_badge_pill(
                cr, city, pad_x, pad_y,
                font_size=14, pad_h=12, height=28
            )
            desc_x = pad_x + bw + 12
            draw_pango_text(
                cr, desc, desc_x, pad_y + 4, 17, bold=True, color=INK_BLACK,
                max_width=w - desc_x - pad_x
            )

            line1_y = pad_y + 36
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line1_y)
            cr.line_to(w - pad_x, line1_y)
            cr.stroke()

            hero_y = line1_y + 18
            iw, ih = draw_weather_icon(cr, desc, pad_x, hero_y, size=54, color=INK_BLACK)
            _, th = draw_hero_text(cr, temp, pad_x + iw + 16, hero_y + 3, 58, bold=True, color=INK_BLACK)

            draw_pango_text_right(cr, f"最高  {hi_temp}", w - pad_x, hero_y + 4, 15, bold=True, color=INK_BLACK)
            draw_pango_text_right(cr, f"最低  {lo_temp}", w - pad_x, hero_y + 32, 15, bold=False, color=INK_BLACK)

            line2_y = hero_y + max(ih, th + 3) + 16
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line2_y)
            cr.line_to(w - pad_x, line2_y)
            cr.stroke()

            kv_w = w - pad_x * 2
            kv_rows = [
                ("体感温度", feels_like),
                ("相对湿度", humidity),
                ("实时风况", wind_cn),
                ("昼夜温差", temp_range),
            ]
            start_ky = line2_y + 12
            row_step = 32
            for idx, (k_label, k_val) in enumerate(kv_rows):
                draw_dotted_kv_row(
                    cr, k_label, k_val,
                    pad_x, start_ky + idx * row_step, kv_w,
                    row_h=28, label_size=14, val_size=16
                )

            line3_y = start_ky + len(kv_rows) * row_step + 4
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line3_y)
            cr.line_to(w - pad_x, line3_y)
            cr.stroke()

            fc_y = line3_y + 14
            draw_pango_text(cr, "■ 未来三天天气趋势", pad_x, fc_y, 15, bold=True, color=INK_BLACK)
            start_cy = fc_y + 30

            days_data = forecast[:3]
            if not days_data:
                draw_pango_text(
                    cr, "三日天气预报不可用", pad_x, start_cy + 8, 16,
                    bold=False, color=INK_BLACK
                )
                return

            card_w = w - pad_x * 2
            card_gap = 8
            available_h = h - pad_y - start_cy
            card_h = min(60, int((available_h - card_gap * (len(days_data) - 1)) / len(days_data)))
            if card_h < 36:
                draw_pango_text(
                    cr, "三日天气预报空间不足", pad_x, start_cy + 8, 14,
                    bold=False, color=INK_BLACK
                )
                return

            for i, day in enumerate(days_data):
                cy = start_cy + i * (card_h + card_gap)
                draw_rounded_rect(cr, pad_x, cy, card_w, card_h, 4)
                cr.set_source_rgb(1.0, 1.0, 1.0)
                cr.fill_preserve()
                cr.set_source_rgb(*INK_BLACK)
                cr.set_line_width(1.2)
                cr.stroke()

                text_y = cy + (card_h - 16) / 2
                range_text = day.get("range", "--°C ~ --°C")
                range_w, _ = draw_pango_text_right(
                    cr, range_text, pad_x + card_w - 12, text_y, 15,
                    bold=True, color=INK_BLACK, max_width=card_w * 0.36
                )

                icon_x = pad_x + card_w * 0.37
                draw_pango_text(
                    cr, f"{day.get('label', '近期')} ({day.get('date', '--')})",
                    pad_x + 12, text_y, 14, bold=True, color=INK_BLACK,
                    max_width=icon_x - pad_x - 22
                )

                desc_x = icon_x + 32
                desc_max_w = pad_x + card_w - 12 - range_w - 10 - desc_x
                if desc_max_w >= 14:
                    draw_weather_icon(
                        cr, day.get("desc", "天气不可用"), icon_x,
                        cy + (card_h - 24) / 2, size=24, color=INK_BLACK
                    )
                    draw_pango_text(
                        cr, day.get("desc", "天气不可用"), desc_x, text_y, 14,
                        bold=False, color=INK_BLACK, max_width=desc_max_w
                    )
