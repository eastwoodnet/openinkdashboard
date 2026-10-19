"""
Modular 1x1 Full-Screen Focus & Instant Alert Widget.
Supports:
1. Daily Focus Broadside Dashboard (Hero Date + Weather Spotlight + Priority Missions + 7-Day Horizon).
2. Priority Instant Notification / Alert Broadcast Screen reuse.
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
    draw_badge_pill, draw_hero_text, draw_checkbox, draw_task_text,
    draw_dotted_kv_row, draw_weather_icon,
    INK_BLACK, INK_WHITE, INK_DIVIDER, INK_TRACK_GRAY, INK_RED,
    CARD_PAD_X, CARD_PAD_Y
)
from calendar_info import get_lunar_date


class FocusWidget(WidgetBase):
    id = "focus"
    name = "全屏焦点大画报与即时通知"
    description = "1x1全屏看板，支持焦点画报模式与紧急通知覆盖模式"

    def render(
        self,
        cr: cairo.Context,
        w: int,
        h: int,
        slot_type: str,
        context: Dict[str, Any],
        profile: DeviceProfile
    ):
        alert_data = context.get("alert")
        if alert_data and alert_data.get("title"):
            self._render_alert_mode(cr, w, h, alert_data, profile)
        else:
            self._render_broadside_mode(cr, w, h, context, profile)

    def _render_alert_mode(self, cr: cairo.Context, w: int, h: int, alert: Dict[str, Any], profile: DeviceProfile):
        """Full-screen priority alert broadcast layout"""
        pad_x = 36
        pad_y = 30

        # Top Alert Badge (Dynamic width)
        draw_badge_pill(
            cr, "重点紧急通知", pad_x, pad_y,
            font_size=15, pad_h=14, height=32, radius=6
        )

        sender = alert.get("sender", "Home Assistant")
        ts = alert.get("time", "")
        meta_str = f"来源: {sender}  {ts}".strip()
        draw_pango_text_right(cr, meta_str, w - pad_x, pad_y + 7, 14, bold=False, color=INK_BLACK)

        # Header underline
        div1_y = pad_y + 46
        cr.set_source_rgb(*INK_DIVIDER)
        cr.set_line_width(1.6)
        cr.move_to(pad_x, div1_y)
        cr.line_to(w - pad_x, div1_y)
        cr.stroke()

        # Hero Alert Card
        card_y = div1_y + 24
        card_w = w - pad_x * 2
        card_h = h - card_y - 64

        draw_rounded_rect(cr, pad_x, card_y, card_w, card_h, 8)
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.fill_preserve()
        cr.set_source_rgb(*INK_BLACK)
        cr.set_line_width(2.0)
        cr.stroke()

        # Alert Title
        title = alert.get("title", "紧急提醒")
        title_color = INK_RED if profile.has_red_channel else INK_BLACK
        draw_pango_text(cr, f"▲  {title}", pad_x + 24, card_y + 22, 30, bold=True, color=title_color, max_width=card_w - 48)

        # Card inner divider
        inner_div = card_y + 78
        cr.set_source_rgb(*INK_DIVIDER)
        cr.set_line_width(1.0)
        cr.move_to(pad_x + 20, inner_div)
        cr.line_to(pad_x + card_w - 20, inner_div)
        cr.stroke()

        # Alert Body Text (Generous 22pt big-text font size and line spacing)
        body = alert.get("body") or alert.get("text") or "无详细正文内容"
        draw_pango_text(cr, body, pad_x + 24, inner_div + 22, 22, bold=False, color=INK_BLACK, max_width=card_w - 48, wrap=True, line_spacing=8)

        # Bottom Hint Bar
        timeout = alert.get("timeout", 0)
        if timeout >= 60 and timeout % 60 == 0:
            timeout_str = f"■ 自动停留 {timeout // 60} 分钟后恢复常规看板"
        elif timeout > 0:
            timeout_str = f"■ 自动停留 {timeout} 秒后恢复常规看板"
        else:
            timeout_str = "■ 常驻显示（待手动恢复）"
        draw_pango_text(cr, timeout_str, pad_x, h - 34, 14, bold=False, color=INK_BLACK)
        draw_pango_text_right(cr, "按汉王机身任意按键立即关闭通知", w - pad_x, h - 34, 13, bold=False, color=INK_BLACK)

    def _render_broadside_mode(self, cr: cairo.Context, w: int, h: int, context: Dict[str, Any], profile: DeviceProfile):
        """Full-screen Daily Broadside Focus Dashboard layout"""
        cal = context.get("calendar", {})
        wtr = context.get("weather", {})
        todos_data = context.get("todos") or context.get("todo") or {}

        year = cal.get("year", 2026)
        month = cal.get("month", 10)
        day = cal.get("day", 19)
        weekday_cn = cal.get("weekday_cn", "星期一")
        lunar = cal.get("lunar", {})
        lunar_str = lunar.get("full_str", "九月初九")
        ganzhi_str = f"{lunar.get('ganzhi', '丙午')}年【{lunar.get('zodiac', '马')}】"
        term = lunar.get("term", "")

        city = wtr.get("city", "北京")
        desc = wtr.get("desc", "晴朗")
        temp = wtr.get("temp", "16°C")
        feels_like = wtr.get("feels_like", temp)
        temp_range = wtr.get("temp_range", "13°C ~ 18°C")
        humidity = wtr.get("humidity", "45%")
        wind_cn = wtr.get("wind_cn", "微风")

        items = todos_data.get("items", [])
        total = todos_data.get("total", 0)
        done_cnt = todos_data.get("completed", 0)
        percent = int((done_cnt / total * 100) if total > 0 else 0)

        pad_x = 22
        pad_y = 20

        # === 1. MIDDLE SPLIT: LEFT (CALENDAR & WEATHER) | RIGHT (TODOS) ===
        mid_x = int(w / 2)
        divider_bottom = 436

        # Center vertical divider
        cr.set_source_rgb(*INK_DIVIDER)
        cr.set_line_width(1.0)
        cr.move_to(mid_x, pad_y)
        cr.line_to(mid_x, divider_bottom)
        cr.stroke()

        # ========================================================
        # --- LEFT COLUMN: Calendar & Weather Spotlight ---
        # ========================================================
        left_right_edge = mid_x - 18
        left_w = left_right_edge - pad_x

        # --- Part 1: Date & Lunar Calendar (y: 20 -> 174) ---
        bw, _ = draw_badge_pill(
            cr, f"{year}年{month:02d}月", pad_x, pad_y,
            font_size=13, pad_h=11, height=26
        )
        draw_pango_text(cr, weekday_cn, pad_x + bw + 12, pad_y + 3, 17, bold=True, color=INK_BLACK)
        week_num = datetime.date(year, month, day).isocalendar()[1]
        draw_pango_text_right(cr, f"第 {week_num} 周", left_right_edge, pad_y + 5, 13, bold=False, color=INK_BLACK)

        # Giant Day Number & Date Details (True ink-box aligned)
        cal_hero_y = 64
        day_str = f"{day:02d}"
        dw, dh = draw_hero_text(cr, day_str, pad_x, cal_hero_y, 80, bold=True, color=INK_BLACK)

        rx = pad_x + dw + 22
        max_rw = left_right_edge - rx
        draw_pango_text(cr, f"农历  {lunar_str}", rx, cal_hero_y - 1, 17, bold=True, color=INK_BLACK, max_width=max_rw)
        draw_pango_text(cr, f"岁次  {ganzhi_str}", rx, cal_hero_y + 31, 14, bold=False, color=INK_BLACK, max_width=max_rw)

        days_to_ny = 365 - datetime.date(year, month, day).timetuple().tm_yday
        if term:
            countdown_str = f"节气 · {term}  (距新年 {days_to_ny} 天)"
        else:
            countdown_str = f"距 2027 丙午新年还有 {days_to_ny} 天"
        draw_pango_text(cr, countdown_str, rx, cal_hero_y + 60, 12, bold=False, color=INK_BLACK, max_width=max_rw)

        # Horizontal Divider between Date and Weather
        sub_div1 = 170
        cr.set_source_rgb(*INK_DIVIDER)
        cr.set_line_width(1.0)
        cr.move_to(pad_x, sub_div1)
        cr.line_to(left_right_edge, sub_div1)
        cr.stroke()

        # --- Part 2: Real-Time Weather (y: 186 -> 436) ---
        wtr_head_y = 186
        cbw, _ = draw_badge_pill(
            cr, city, pad_x, wtr_head_y,
            font_size=13, pad_h=12, height=26
        )
        draw_pango_text(cr, desc, pad_x + cbw + 12, wtr_head_y + 3, 16, bold=True, color=INK_BLACK)
        draw_pango_text_right(cr, "空气 优 · 32", left_right_edge, wtr_head_y + 5, 13, bold=False, color=INK_BLACK)

        # Weather Hero: Vector Icon + Ink-Box Giant Temp + High/Low Stack
        wtr_hero_y = 228
        iw, _ = draw_weather_icon(cr, desc, pad_x, wtr_hero_y, size=50, color=INK_BLACK)
        draw_hero_text(cr, temp, pad_x + iw + 16, wtr_hero_y + 2, 54, bold=True, color=INK_BLACK)

        hi_temp = temp_range.split("~")[-1].strip() if "~" in temp_range else temp_range
        lo_temp = temp_range.split("~")[0].strip() if "~" in temp_range else temp_range
        draw_pango_text_right(cr, f"最高  {hi_temp}", left_right_edge, wtr_hero_y + 2, 14, bold=True, color=INK_BLACK)
        draw_pango_text_right(cr, f"最低  {lo_temp}", left_right_edge, wtr_hero_y + 28, 14, bold=False, color=INK_BLACK)

        # Clean Bauhaus Dotted Key-Value Rows for Weather Metrics
        kv_rows = [
            ("体感温度", feels_like),
            ("相对湿度", humidity),
            ("实时风况", wind_cn),
        ]
        start_ky = 302
        row_step = 40
        for idx, (k_label, k_val) in enumerate(kv_rows):
            draw_dotted_kv_row(
                cr, k_label, k_val,
                pad_x, start_ky + idx * row_step, left_w,
                row_h=30, label_size=14, val_size=16
            )

        # ========================================================
        # --- RIGHT COLUMN: Priority Missions / Todos ---
        # ========================================================
        rx_start = mid_x + 18
        right_w = w - pad_x - rx_start

        draw_pango_text(cr, "■ 今日重点推进事项", rx_start, pad_y + 2, 17, bold=True, color=INK_BLACK)
        stat_str = f"完成 {done_cnt}/{total} · {percent}%"
        draw_pango_text_right(cr, stat_str, w - pad_x, pad_y + 5, 14, bold=True, color=INK_BLACK)

        # Right sub-divider
        sub_div2 = pad_y + 34
        cr.set_source_rgb(*INK_DIVIDER)
        cr.set_line_width(1.0)
        cr.move_to(rx_start, sub_div2)
        cr.line_to(w - pad_x, sub_div2)
        cr.stroke()

        # Task list with dynamic multi-line vertical flow and per-line strikethrough
        display_items = items[:6]
        bar_y = 418
        cur_y = sub_div2 + 14
        box_sz = 18
        row_gap = 14
        min_step = 44

        for i, it in enumerate(display_items):
            if cur_y + box_sz > bar_y - 10:
                break

            done = it.get("done", False)
            text = it.get("text", "")
            seq_num = i + 1

            draw_checkbox(cr, rx_start, cur_y + 2, size=box_sz, checked=done)

            text_x = rx_start + box_sz + 12
            max_text_w = w - pad_x - text_x
            text_color = INK_RED if (not done and profile.has_red_channel and i == 0) else INK_BLACK

            _, th = draw_task_text(
                cr, f"{seq_num}. {text}",
                text_x, cur_y,
                font_size=15,
                max_width=max_text_w,
                done=done,
                color=text_color
            )

            cur_y += max(min_step, int(th + row_gap))

        # Right column bottom progress bar
        bar_w = right_w
        bar_h = 8
        draw_rounded_rect(cr, rx_start, bar_y, bar_w, bar_h, 4)
        cr.set_source_rgb(*INK_TRACK_GRAY)
        cr.fill_preserve()
        cr.set_source_rgb(*INK_BLACK)
        cr.set_line_width(1.0)
        cr.stroke()

        if total > 0 and done_cnt > 0:
            fill_w = max(6, int(bar_w * (done_cnt / total)))
            draw_rounded_rect(cr, rx_start, bar_y, fill_w, bar_h, 4)
            cr.set_source_rgb(*INK_BLACK)
            cr.fill()

        # === 3. BOTTOM BAR: 7-DAY HORIZON STRIP ===
        line2_y = 446
        cr.set_source_rgb(*INK_DIVIDER)
        cr.set_line_width(1.0)
        cr.move_to(pad_x, line2_y)
        cr.line_to(w - pad_x, line2_y)
        cr.stroke()

        weekdays = ["一", "二", "三", "四", "五", "六", "日"]
        today_dt = datetime.date(year, month, day)
        cur_weekday_idx = today_dt.weekday()
        monday_dt = today_dt - datetime.timedelta(days=cur_weekday_idx)

        total_strip_w = w - pad_x * 2
        col_gap = 8
        cell_w = (total_strip_w - 6 * col_gap) / 7
        wy = 460
        strip_h = 96

        for i, wd in enumerate(weekdays):
            cur_date = monday_dt + datetime.timedelta(days=i)
            cell_x = pad_x + i * (cell_w + col_gap)
            is_today = (i == cur_weekday_idx)

            try:
                ld = get_lunar_date(cur_date).get("day_str", "")
            except Exception:
                ld = ""

            if is_today:
                draw_rounded_rect(cr, cell_x, wy, cell_w, strip_h, 6)
                cr.set_source_rgb(*INK_BLACK)
                cr.fill()

                draw_pango_text(cr, f"周{wd}", cell_x, wy + 8, 12, bold=True, color=INK_WHITE, max_width=cell_w, align=Pango.Alignment.CENTER)
                draw_pango_text(cr, f"{cur_date.month}/{cur_date.day:02d}", cell_x, wy + 33, 18, bold=True, color=INK_WHITE, max_width=cell_w, align=Pango.Alignment.CENTER)
                if ld:
                    draw_pango_text(cr, ld, cell_x, wy + 68, 11, bold=True, color=INK_WHITE, max_width=cell_w, align=Pango.Alignment.CENTER)
            else:
                draw_rounded_rect(cr, cell_x, wy, cell_w, strip_h, 6)
                cr.set_source_rgb(1.0, 1.0, 1.0)
                cr.fill_preserve()
                cr.set_source_rgb(*INK_DIVIDER)
                cr.set_line_width(1.0)
                cr.stroke()

                draw_pango_text(cr, f"周{wd}", cell_x, wy + 8, 12, bold=False, color=INK_BLACK, max_width=cell_w, align=Pango.Alignment.CENTER)
                draw_pango_text(cr, f"{cur_date.month}/{cur_date.day:02d}", cell_x, wy + 33, 17, bold=True, color=INK_BLACK, max_width=cell_w, align=Pango.Alignment.CENTER)
                if ld:
                    draw_pango_text(cr, ld, cell_x, wy + 68, 11, bold=False, color=INK_BLACK, max_width=cell_w, align=Pango.Alignment.CENTER)


class AlertWidget(FocusWidget):
    id = "alert"
    name = "即时通知与大字备忘"
    description = "1x1全屏大字通知或桌面备忘录卡片"

    def render(
        self,
        cr: cairo.Context,
        w: int,
        h: int,
        slot_type: str,
        context: Dict[str, Any],
        profile: DeviceProfile
    ):
        alert_data = context.get("alert") or {
            "title": "桌面重点备忘提醒",
            "body": "可在左侧面板自定义通知标题与正文内容，支持多行自动折行排版与一键全屏推送。",
            "sender": "OpenInk Studio",
            "time": datetime.datetime.now().strftime("%H:%M"),
            "timeout": 0
        }
        self._render_alert_mode(cr, w, h, alert_data, profile)

