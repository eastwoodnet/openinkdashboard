"""
Modular External Calendar Agenda & Countdown Widget (Scheme A - P0 Plugin).
Supports Quadrant (382x282), Half-Vertical (382x580), and Full (780x580) slot geometries.
Uses mathematical ink_rect primitives from widgets.base to guarantee zero text collision.
"""

from typing import Dict, Any, List
import cairo
from profiles import DeviceProfile
from widgets.base import (
    WidgetBase, draw_pango_text, draw_pango_text_right, draw_rounded_rect,
    draw_badge_pill,
    INK_BLACK, INK_WHITE, INK_DIVIDER, CARD_PAD_X, CARD_PAD_Y
)


class AgendaWidget(WidgetBase):
    id = "agenda"
    name = "外部日程与倒数日 (ICS)"
    description = "同步 iCloud/Google/飞书 .ics 日历日程与重点纪念日倒计时"

    def render(
        self,
        cr: cairo.Context,
        w: int,
        h: int,
        slot_type: str,
        context: Dict[str, Any],
        profile: DeviceProfile
    ):
        agenda_data = context.get("agenda", {})
        events: List[Dict[str, Any]] = agenda_data.get("events", [])
        countdowns: List[Dict[str, Any]] = agenda_data.get("countdowns", [])
        total = agenda_data.get("total_upcoming", len(events))

        pad_x = CARD_PAD_X
        pad_y = CARD_PAD_Y

        if slot_type in ("quadrant", "compact") or h < 320:
            # === Quadrant Mode (382x282) ===
            bw, _ = draw_badge_pill(
                cr, "日程与倒数", pad_x, pad_y,
                font_size=13, pad_h=10, height=26
            )
            draw_pango_text(cr, "AGENDA", pad_x + bw + 10, pad_y + 5, 13, bold=True, color=INK_BLACK)
            draw_pango_text_right(cr, f"近期 {total} 项", w - pad_x, pad_y + 5, 13, bold=False, color=INK_BLACK)

            # Divider 1
            line1_y = pad_y + 34
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line1_y)
            cr.line_to(w - pad_x, line1_y)
            cr.stroke()

            # Top Highlighted Countdown Box (y: 58 .. 100)
            box_y = line1_y + 10
            box_h = 42
            box_w = w - pad_x * 2
            draw_rounded_rect(cr, pad_x, box_y, box_w, box_h, 6)
            cr.set_source_rgb(0.95, 0.95, 0.95)
            cr.fill_preserve()
            cr.set_source_rgb(*INK_BLACK)
            cr.set_line_width(1.4)
            cr.stroke()

            if countdowns:
                cd = countdowns[0]
                d_away = cd.get("days_away", 0)
                cd_badge_txt = "今天到期" if d_away == 0 else f"还有 {d_away} 天"
                # Measure exact ink width of badge text to right-align pill 10px from box border
                import gi
                gi.require_version('PangoCairo', '1.0')
                from gi.repository import Pango, PangoCairo
                tmp_l = PangoCairo.create_layout(cr)
                fd = Pango.FontDescription("WenQuanYi Micro Hei 12")
                fd.set_weight(Pango.Weight.BOLD)
                tmp_l.set_font_description(fd)
                tmp_l.set_text(cd_badge_txt, -1)
                ink_r, _ = tmp_l.get_pixel_extents()
                pill_w = max(ink_r.width + 18, 56)
                pill_x = w - pad_x - 10 - pill_w
                draw_badge_pill(
                    cr, cd_badge_txt, pill_x, box_y + 8,
                    font_size=12, pad_h=9, height=26
                )
                title_max_w = pill_x - (pad_x + 12) - 10
                draw_pango_text(
                    cr, f"★ {cd.get('title', '重要日程')}",
                    pad_x + 12, box_y + 11, 14, bold=True, color=INK_BLACK, max_width=title_max_w
                )
            else:
                draw_pango_text(cr, "★ 暂无近期倒数日事件", pad_x + 12, box_y + 11, 14, bold=False, color=INK_BLACK)

            # Agenda Rows (3 rows in y: 112 .. 266)
            list_start_y = box_y + box_h + 12
            row_h = 48
            display_events = events[:3]

            if not display_events:
                draw_pango_text(cr, "近期暂无待办日程安排", pad_x, list_start_y + 40, 15, bold=False, color=INK_BLACK)
            else:
                for idx, ev in enumerate(display_events):
                    ry = list_start_y + idx * row_h
                    badge_txt = ev.get("day_badge", "近期")
                    is_today = (ev.get("days_away", 99) == 0)

                    bw_ev, _ = draw_badge_pill(
                        cr, badge_txt, pad_x, ry + 8,
                        font_size=12, pad_h=8, height=24,
                        bg_color=INK_BLACK if is_today else (0.35, 0.35, 0.35),
                        text_color=INK_WHITE
                    )

                    time_str = ev.get("time", "全天")
                    tx = pad_x + bw_ev + 10
                    tw, _ = draw_pango_text(cr, time_str, tx, ry + 11, 13, bold=True, color=INK_BLACK)

                    title_x = tx + tw + 10
                    max_tw = w - pad_x - title_x
                    draw_pango_text(
                        cr, ev.get("title", ""),
                        title_x, ry + 10, 14, bold=True, color=INK_BLACK, max_width=max_tw
                    )

                    if idx < len(display_events) - 1:
                        div_y = ry + row_h - 4
                        cr.set_source_rgb(*INK_DIVIDER)
                        cr.set_line_width(0.8)
                        cr.move_to(pad_x, div_y)
                        cr.line_to(w - pad_x, div_y)
                        cr.stroke()

        else:
            # === Half-Vertical (382x580) or Full (780x580) Mode ===
            import gi
            gi.require_version('PangoCairo', '1.0')
            from gi.repository import Pango, PangoCairo

            bw, _ = draw_badge_pill(
                cr, "日程表与倒数日", pad_x, pad_y,
                font_size=14, pad_h=11, height=28
            )
            ics_cnt = agenda_data.get("ics_count", 0)
            sub_label = f"ICS 订阅({ics_cnt})" if ics_cnt > 0 else "AGENDA"
            draw_pango_text(cr, sub_label, pad_x + bw + 12, pad_y + 5, 13, bold=True, color=INK_BLACK)
            draw_pango_text_right(cr, f"共 {total} 项", w - pad_x, pad_y + 5, 14, bold=False, color=INK_BLACK)

            # Divider 1
            line1_y = pad_y + 36
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, line1_y)
            cr.line_to(w - pad_x, line1_y)
            cr.stroke()

            # Section 1: Milestone Countdowns (2 cards)
            sec1_y = line1_y + 14
            draw_pango_text(cr, "■ 重点日程与纪念日倒数", pad_x, sec1_y, 14, bold=True, color=INK_BLACK)

            cd_start_y = sec1_y + 28
            cd_card_h = 46
            cd_gap = 8
            top_cds = countdowns[:2]

            for i in range(2):
                cy = cd_start_y + i * (cd_card_h + cd_gap)
                draw_rounded_rect(cr, pad_x, cy, w - pad_x * 2, cd_card_h, 6)
                cr.set_source_rgb(0.96, 0.96, 0.96)
                cr.fill_preserve()
                cr.set_source_rgb(*INK_BLACK)
                cr.set_line_width(1.4)
                cr.stroke()

                if i < len(top_cds):
                    cd = top_cds[i]
                    d_away = cd.get("days_away", 0)
                    badge_str = "就是今天" if d_away == 0 else f"还有 {d_away} 天"
                    tmp_l = PangoCairo.create_layout(cr)
                    fd = Pango.FontDescription("WenQuanYi Micro Hei 13")
                    fd.set_weight(Pango.Weight.BOLD)
                    tmp_l.set_font_description(fd)
                    tmp_l.set_text(badge_str, -1)
                    ink_r, _ = tmp_l.get_pixel_extents()
                    pill_w = max(ink_r.width + 20, 62)
                    px = w - pad_x - 10 - pill_w
                    draw_badge_pill(
                        cr, badge_str, px, cy + 9,
                        font_size=13, pad_h=10, height=28
                    )
                    max_cw = px - (pad_x + 12) - 8
                    draw_pango_text(
                        cr, f"★ {cd.get('title', '')}",
                        pad_x + 12, cy + 14, 14, bold=True, color=INK_BLACK, max_width=max_cw
                    )
                else:
                    draw_pango_text(cr, "★ 可在左侧面板添加纪念日或 .ics 订阅", pad_x + 12, cy + 13, 13, bold=False, color=INK_BLACK)

            # Divider 2
            div2_y = cd_start_y + 2 * cd_card_h + cd_gap + 14
            cr.set_source_rgb(*INK_DIVIDER)
            cr.set_line_width(1.0)
            cr.move_to(pad_x, div2_y)
            cr.line_to(w - pad_x, div2_y)
            cr.stroke()

            # Section 2: Chronological Agenda Timeline
            sec2_y = div2_y + 14
            draw_pango_text(cr, "■ 近期日程时间轴 · TIMELINE", pad_x, sec2_y, 14, bold=True, color=INK_BLACK)

            tl_start_y = sec2_y + 30
            avail_h = h - tl_start_y - 16
            max_rows = 6
            row_h = int(avail_h / max_rows)
            tl_events = events[:max_rows]

            for idx, ev in enumerate(tl_events):
                ry = tl_start_y + idx * row_h
                badge_txt = ev.get("day_badge", "近期")
                is_today = (ev.get("days_away", 99) == 0)

                bw_ev, _ = draw_badge_pill(
                    cr, badge_txt, pad_x, ry + int((row_h - 24) / 2),
                    font_size=12, pad_h=8, height=24,
                    bg_color=INK_BLACK if is_today else (0.35, 0.35, 0.35),
                    text_color=INK_WHITE
                )

                time_str = ev.get("time", "全天")
                tx = pad_x + bw_ev + 10
                tw, _ = draw_pango_text(cr, time_str, tx, ry + int((row_h - 18) / 2), 13, bold=True, color=INK_BLACK)

                title_x = tx + tw + 10
                max_tw = w - pad_x - title_x
                draw_pango_text(
                    cr, ev.get("title", ""),
                    title_x, ry + int((row_h - 19) / 2), 14, bold=True, color=INK_BLACK, max_width=max_tw
                )

                if idx < len(tl_events) - 1:
                    line_y = ry + row_h - 1
                    cr.set_source_rgb(*INK_DIVIDER)
                    cr.set_line_width(0.8)
                    cr.move_to(pad_x, line_y)
                    cr.line_to(w - pad_x, line_y)
                    cr.stroke()
