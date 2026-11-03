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
from calendar_info import get_lunar_date
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

            today_dt = datetime.date(year, month, day)
            week_num = today_dt.isocalendar()[1]
            days_left = (datetime.date(year + 1, 1, 1) - today_dt).days
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

            # Weekday column headers in a unified capsule bar (方案三：周一至周日整体胶囊细框，周六日一体化反色色块)
            cal_matrix = calendar.monthcalendar(year, month)
            grid_w = w - pad_x * 2.0
            cw = grid_w / 7.0
            headers = ["一", "二", "三", "四", "五", "六", "日"]

            is_full_screen = (w > 500)
            day_font_sz = 15.0 if is_full_screen else 13.0
            lunar_font_sz = 10.5 if is_full_screen else 9.0

            matrix_start_y = 258
            hy = matrix_start_y - 34
            bar_h = 24.0
            bar_x = pad_x
            bar_w = grid_w
            bar_r = 5.0

            # 1. Outer capsule white background
            draw_rounded_rect(cr, bar_x, hy, bar_w, bar_h, bar_r)
            cr.set_source_rgb(*INK_WHITE)
            cr.fill()

            # 2. Fill the weekend right portion (Saturday & Sunday, cols 5 and 6) with solid black
            sat_x = pad_x + 5 * cw
            sun_right = pad_x + 7 * cw
            block_w = sun_right - sat_x

            cr.save()
            draw_rounded_rect(cr, bar_x, hy, bar_w, bar_h, bar_r)
            cr.clip()
            cr.set_source_rgb(*INK_BLACK)
            cr.rectangle(sat_x, hy, block_w, bar_h)
            cr.fill()
            # Fine vertical divider line between Saturday and Sunday
            cr.set_source_rgb(*INK_WHITE)
            cr.set_line_width(0.8)
            cr.move_to(pad_x + 6 * cw, hy + 3)
            cr.line_to(pad_x + 6 * cw, hy + bar_h - 3)
            cr.stroke()
            cr.restore()

            # 3. Outer capsule 1.2px fine stroke
            draw_rounded_rect(cr, bar_x, hy, bar_w, bar_h, bar_r)
            cr.set_source_rgb(*INK_BLACK)
            cr.set_line_width(1.2)
            cr.stroke()

            # 4. Header text (Mon-Fri black, Sat-Sun bold white)
            for col_idx, h_name in enumerate(headers):
                hx = pad_x + col_idx * cw
                is_weekend = (col_idx in (5, 6))
                if is_weekend:
                    draw_pango_text(cr, h_name, hx, hy + 2, 12.5, bold=True, color=INK_WHITE, max_width=cw, align=Pango.Alignment.CENTER)
                else:
                    draw_pango_text(cr, h_name, hx, hy + 2, 12.5, bold=False, color=INK_BLACK, max_width=cw, align=Pango.Alignment.CENTER)

            # Subtle hairline separating weekday headers and date matrix
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(0.8)
            cr.move_to(pad_x, matrix_start_y - 6)
            cr.line_to(w - pad_x, matrix_start_y - 6)
            cr.stroke()

            # Dynamic row height based on remaining card height
            avail_grid_h = h - matrix_start_y - 14
            num_weeks = max(1, len(cal_matrix))
            row_h = avail_grid_h / num_weeks

            # Vertical spacing: 5px gap between day and lunar text
            v_gap = 5.0
            ink_day_h = 14.0
            ink_lun_h = 11.0
            stack_h = ink_day_h + v_gap + ink_lun_h
            top_margin = max(3.0, (row_h - stack_h) / 2.0)
            y_day_offset = top_margin - 3.0
            y_lun_offset = top_margin + ink_day_h + v_gap - 2.0

            for row_idx, week in enumerate(cal_matrix):
                ry = matrix_start_y + row_idx * row_h
                for col_idx, d_num in enumerate(week):
                    if d_num == 0:
                        continue
                    dx = pad_x + col_idx * cw
                    is_today = (d_num == day)
                    is_weekend = (col_idx in (5, 6))
                    has_event = (d_num in event_days)
                    d_str = str(d_num)

                    # Lunar date calculation
                    cell_dt = datetime.date(year, month, d_num)
                    try:
                        lunar_data = get_lunar_date(cell_dt)
                        l_day = lunar_data.get("day", 1)
                        if l_day == 1:
                            ld_str = lunar_data.get("month_str", "初一")
                            is_lunar_first = True
                        else:
                            ld_str = lunar_data.get("day_str", "")
                            is_lunar_first = False
                    except Exception:
                        ld_str = ""
                        is_lunar_first = False

                    pill_w = min(cw - 6, 50) if is_full_screen else (cw - 6)
                    pill_h = row_h - 4
                    pill_x = dx + (cw - pill_w) / 2
                    pill_y = ry + 2

                    if is_today:
                        # Today: Unified solid black rounded pill with pure white text
                        draw_rounded_rect(cr, pill_x, pill_y, pill_w, pill_h, 6)
                        cr.set_source_rgb(*INK_BLACK)
                        cr.fill()

                        draw_pango_text(cr, d_str, dx, ry + y_day_offset, day_font_sz, bold=True, color=INK_WHITE, max_width=cw, align=Pango.Alignment.CENTER)
                        if ld_str:
                            draw_pango_text(cr, ld_str, dx, ry + y_lun_offset, lunar_font_sz, bold=True, color=INK_WHITE, max_width=cw, align=Pango.Alignment.CENTER)

                        if has_event:
                            draw_rounded_rect(cr, dx + cw / 2 - 2, pill_y + pill_h - 4, 4, 3, 1.5)
                            cr.set_source_rgb(*INK_WHITE)
                            cr.fill()

                    else:
                        # Normal day (clean white background, pure typography contrast)
                        if is_weekend:
                            # Weekend: Heavy Bold (加粗加黑)
                            draw_pango_text(cr, d_str, dx, ry + y_day_offset, day_font_sz, bold=True, color=INK_BLACK, max_width=cw, align=Pango.Alignment.CENTER)
                            if ld_str:
                                draw_pango_text(cr, ld_str, dx, ry + y_lun_offset, lunar_font_sz, bold=True, color=INK_BLACK, max_width=cw, align=Pango.Alignment.CENTER)
                        else:
                            # Weekday: Regular font weight (若为农历月初则加粗月名)
                            draw_pango_text(cr, d_str, dx, ry + y_day_offset, day_font_sz, bold=is_lunar_first, color=INK_BLACK, max_width=cw, align=Pango.Alignment.CENTER)
                            if ld_str:
                                draw_pango_text(cr, ld_str, dx, ry + y_lun_offset, lunar_font_sz, bold=is_lunar_first, color=INK_BLACK, max_width=cw, align=Pango.Alignment.CENTER)

                        if has_event:
                            draw_rounded_rect(cr, dx + cw / 2 - 2, ry + row_h - 4, 4, 3, 1.5)
                            cr.set_source_rgb(*INK_BLACK)
                            cr.fill()

