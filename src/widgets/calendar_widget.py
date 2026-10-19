"""
Modular Calendar & Date Widget.
Supports Full, Half-Vertical, and Quadrant slot modes with adaptive LOD.
Includes a mini month calendar grid in full-height mode to eliminate blank space.
"""

import calendar
import datetime
from typing import Dict, Any
import cairo
import gi
gi.require_version('Pango', '1.0')
from gi.repository import Pango
from profiles import DeviceProfile
from widgets.base import (
    WidgetBase, draw_pango_text, draw_pango_text_right, draw_rounded_rect,
    draw_badge_pill, draw_hero_text,
    INK_BLACK, INK_WHITE, INK_DIVIDER, INK_TRACK_GRAY, CARD_PAD_X, CARD_PAD_Y
)


class CalendarWidget(WidgetBase):
    id = "calendar"
    name = "日历与节气"
    description = "展示大字公历日期、星期、农历干支节气与生肖"

    def render(
        self,
        cr: cairo.Context,
        w: int,
        h: int,
        slot_type: str,
        context: Dict[str, Any],
        profile: DeviceProfile
    ):
        cal = context.get("calendar", {})
        if not cal:
            return

        year = cal.get("year", 2026)
        month = cal.get("month", 10)
        day = cal.get("day", 18)
        month_en = cal.get("month_en", "October")
        weekday_cn = cal.get("weekday_cn", "星期日")
        weekday_en = cal.get("weekday_en", "Sunday")
        lunar = cal.get("lunar", {})
        lunar_str = lunar.get("full_str", "")
        ganzhi_str = f"{lunar.get('ganzhi', '--')}年【{lunar.get('zodiac', '--')}】"
        term = lunar.get("term", "")

        pad_x = CARD_PAD_X
        pad_y = CARD_PAD_Y

        if slot_type in ("quadrant", "compact") or h < 320:
            # === Quadrant / Half-Height Mode (e.g. 382x282) ===
            # Top row: Dynamic Year & Month badge + Weekday
            bw, _ = draw_badge_pill(
                cr, f"{year}年{month:02d}月", pad_x, pad_y,
                font_size=13, pad_h=10, height=26
            )
            draw_pango_text(cr, weekday_cn, pad_x + bw + 12, pad_y + 3, 16, bold=True, color=INK_BLACK)
            draw_pango_text_right(cr, weekday_en.upper(), w - pad_x, pad_y + 5, 12, bold=False, color=INK_BLACK)

            # Divider line 1
            line1_y = pad_y + 34
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line1_y)
            cr.line_to(w - pad_x, line1_y)
            cr.stroke()

            # Hero Section: True ink-box Giant Day Number + Vertically Matched Lunar Stack
            hero_y = line1_y + 14
            day_str = f"{day:02d}"
            dw, dh = draw_hero_text(cr, day_str, pad_x, hero_y, 68, bold=True, color=INK_BLACK)

            # Right of giant number: 3-line stack matched to [hero_y, hero_y + dh]
            rx = pad_x + dw + 20
            max_rw = w - rx - pad_x
            draw_pango_text(cr, f"农历  {lunar_str}", rx, hero_y - 1, 16, bold=True, color=INK_BLACK, max_width=max_rw)
            draw_pango_text(cr, f"岁次  {ganzhi_str}", rx, hero_y + 25, 13, bold=False, color=INK_BLACK, max_width=max_rw)

            week_num = datetime.date(year, month, day).isocalendar()[1]
            days_left = 365 - datetime.date(year, month, day).timetuple().tm_yday
            if term:
                draw_pango_text(cr, f"节气 · {term}  ·  第 {week_num} 周", rx, hero_y + 49, 12, bold=True, color=INK_BLACK, max_width=max_rw)
            else:
                draw_pango_text(cr, f"第 {week_num} 周 · 距新年 {days_left} 天", rx, hero_y + 49, 12, bold=False, color=INK_BLACK, max_width=max_rw)

            # Divider line 2 (Symmetric 14px gap below hero_y + dh)
            line2_y = 148
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line2_y)
            cr.line_to(w - pad_x, line2_y)
            cr.stroke()

            # 7-Day Current Week Strip (Borderless open columns; only today highlighted in black pill)
            weekdays = ["一", "二", "三", "四", "五", "六", "日"]
            today_dt = datetime.date(year, month, day)
            cur_weekday_idx = today_dt.weekday()
            monday_dt = today_dt - datetime.timedelta(days=cur_weekday_idx)
            cell_w = (w - pad_x * 2) / 7
            wy = 160
            strip_h = 102

            from calendar_info import get_lunar_date
            event_days = set(context.get("agenda", {}).get("event_dates_in_month", []))

            for i, wd in enumerate(weekdays):
                cur_date = monday_dt + datetime.timedelta(days=i)
                wx = pad_x + i * cell_w
                is_today = (i == cur_weekday_idx)
                has_event = (cur_date.month == month and cur_date.day in event_days)

                try:
                    ld = get_lunar_date(cur_date).get("day_str", "")
                except Exception:
                    ld = ""

                if is_today:
                    draw_rounded_rect(cr, wx + 2, wy, cell_w - 4, strip_h, 6)
                    cr.set_source_rgb(*INK_BLACK)
                    cr.fill()

                    draw_pango_text(cr, f"周{wd}", wx, wy + 10, 12, bold=True, color=INK_WHITE, max_width=cell_w, align=Pango.Alignment.CENTER)
                    draw_pango_text(cr, str(cur_date.day), wx, wy + 35, 21, bold=True, color=INK_WHITE, max_width=cell_w, align=Pango.Alignment.CENTER)
                    if ld:
                        draw_pango_text(cr, ld, wx, wy + 72, 11, bold=True, color=INK_WHITE, max_width=cell_w, align=Pango.Alignment.CENTER)
                    if has_event:
                        draw_rounded_rect(cr, wx + cell_w / 2 - 2, wy + 92, 4, 4, 2)
                        cr.set_source_rgb(*INK_WHITE)
                        cr.fill()
                else:
                    draw_pango_text(cr, f"周{wd}", wx, wy + 10, 12, bold=False, color=INK_BLACK, max_width=cell_w, align=Pango.Alignment.CENTER)
                    draw_pango_text(cr, str(cur_date.day), wx, wy + 35, 19, bold=True, color=INK_BLACK, max_width=cell_w, align=Pango.Alignment.CENTER)
                    if ld:
                        draw_pango_text(cr, ld, wx, wy + 72, 11, bold=False, color=INK_BLACK, max_width=cell_w, align=Pango.Alignment.CENTER)
                    if has_event:
                        draw_rounded_rect(cr, wx + cell_w / 2 - 2, wy + 92, 4, 4, 2)
                        cr.set_source_rgb(*INK_BLACK)
                        cr.fill()

        else:
            # === Full Height Mode (Half-V e.g. 382x580 or Full) ===
            event_days = set(context.get("agenda", {}).get("event_dates_in_month", []))

            # Top Tag Badge (Dynamic width so "月" never touches the border)
            bw, _ = draw_badge_pill(
                cr, f"{year}年{month:02d}月", pad_x, pad_y,
                font_size=14, pad_h=11, height=28
            )
            draw_pango_text(cr, month_en.upper(), pad_x + bw + 12, pad_y + 5, 14, bold=True, color=INK_BLACK)
            week_num = datetime.date(year, month, day).isocalendar()[1]
            draw_pango_text_right(cr, f"第 {week_num} 周", w - pad_x, pad_y + 5, 14, bold=False, color=INK_BLACK)

            # Divider line 1
            line1_y = pad_y + 36
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line1_y)
            cr.line_to(w - pad_x, line1_y)
            cr.stroke()

            # Giant Day Number & Date Details (True ink-box aligned)
            hero_y = line1_y + 20
            day_str = f"{day:02d}"
            dw, dh = draw_hero_text(cr, day_str, pad_x, hero_y, 82, bold=True, color=INK_BLACK)

            # Right of giant number: 3-line stack matched to [hero_y, hero_y + dh]
            text_x = pad_x + dw + 24
            max_rw = w - text_x - pad_x
            draw_pango_text(cr, weekday_cn, text_x, hero_y - 2, 24, bold=True, color=INK_BLACK, max_width=max_rw)
            draw_pango_text(cr, f"农历  {lunar_str}", text_x, hero_y + 34, 16, bold=True, color=INK_BLACK, max_width=max_rw)
            draw_pango_text(cr, f"岁次  {ganzhi_str}", text_x, hero_y + 62, 14, bold=False, color=INK_BLACK, max_width=max_rw)

            # Divider line 2 (Symmetric 20px gap below hero_y + dh)
            div_y = 176
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, div_y)
            cr.line_to(w - pad_x, div_y)
            cr.stroke()

            # Month Calendar Matrix Section Header
            grid_header_y = 192
            draw_pango_text(cr, f"■ 当月全览 · {month_en.upper()}", pad_x, grid_header_y, 15, bold=True, color=INK_BLACK)
            total_days = calendar.monthrange(year, month)[1]
            draw_pango_text_right(cr, f"共 {total_days} 天", w - pad_x, grid_header_y + 1, 13, bold=False, color=INK_BLACK)

            # Weekday column headers
            cal_matrix = calendar.monthcalendar(year, month)
            cw = (w - pad_x * 2) / 7
            headers = ["一", "二", "三", "四", "五", "六", "日"]
            hy = 226

            for col_idx, h_name in enumerate(headers):
                hx = pad_x + col_idx * cw
                draw_pango_text(cr, h_name, hx, hy, 13, bold=True, color=INK_BLACK, max_width=cw, align=Pango.Alignment.CENTER)

            # Subtle hairline separating weekday headers and date matrix
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(0.8)
            cr.move_to(pad_x, 250)
            cr.line_to(w - pad_x, 250)
            cr.stroke()

            # Dynamic row height based on remaining card height
            matrix_start_y = 258
            avail_grid_h = h - matrix_start_y - 16
            num_weeks = max(1, len(cal_matrix))
            row_h = int(avail_grid_h / num_weeks)

            for row_idx, week in enumerate(cal_matrix):
                ry = matrix_start_y + row_idx * row_h
                for col_idx, d_num in enumerate(week):
                    if d_num == 0:
                        continue
                    dx = pad_x + col_idx * cw
                    is_today = (d_num == day)
                    has_event = (d_num in event_days)
                    d_str = str(d_num)

                    if is_today:
                        circle_sz = 34
                        draw_rounded_rect(cr, dx + (cw - circle_sz) / 2, ry + (row_h - circle_sz) / 2, circle_sz, circle_sz, circle_sz / 2)
                        cr.set_source_rgb(*INK_BLACK)
                        cr.fill()
                        draw_pango_text(cr, d_str, dx, ry + (row_h - 20) / 2, 15, bold=True, color=INK_WHITE, max_width=cw, align=Pango.Alignment.CENTER)
                        if has_event:
                            draw_rounded_rect(cr, dx + cw / 2 - 2, ry + (row_h + circle_sz) / 2 - 6, 4, 4, 2)
                            cr.set_source_rgb(*INK_WHITE)
                            cr.fill()
                    else:
                        draw_pango_text(cr, d_str, dx, ry + (row_h - 20) / 2, 15, bold=False, color=INK_BLACK, max_width=cw, align=Pango.Alignment.CENTER)
                        if has_event:
                            draw_rounded_rect(cr, dx + cw / 2 - 2, ry + (row_h + 20) / 2 + 5, 4, 4, 2)
                            cr.set_source_rgb(*INK_BLACK)
                            cr.fill()

