"""
Modular Todo List Widget.
Displays task checklist with high-contrast checkboxes, strike-through, progress stats.
All text is pure black for optimal E-Ink readability.
"""

from typing import Dict, Any
import cairo
from profiles import DeviceProfile
from widgets.base import (
    WidgetBase, draw_pango_text, draw_pango_text_right, draw_rounded_rect,
    draw_checkbox, draw_task_text,
    INK_BLACK, INK_WHITE, INK_DIVIDER, INK_TRACK_GRAY, INK_RED,
    CARD_PAD_X, CARD_PAD_Y
)


class TodoWidget(WidgetBase):
    id = "todo"
    name = "今日待办清单"
    description = "展示日常任务清单、复选框状态、划线与完成度进度"

    def render(
        self,
        cr: cairo.Context,
        w: int,
        h: int,
        slot_type: str,
        context: Dict[str, Any],
        profile: DeviceProfile
    ):
        todos_data = context.get("todos") or context.get("todo") or {}
        items = todos_data.get("items", [])
        total = todos_data.get("total", 0)
        done_cnt = todos_data.get("completed", 0)
        percent = int((done_cnt / total * 100) if total > 0 else 0)

        pad_x = CARD_PAD_X
        pad_y = CARD_PAD_Y

        # Header Title
        draw_pango_text(cr, "■ 今日重点待办", pad_x, pad_y, 18, bold=True, color=INK_BLACK)

        # Stats tag (e.g. 3/6 · 50%)
        stat_str = f"完成 {done_cnt}/{total} · {percent}%"
        draw_pango_text_right(cr, stat_str, w - pad_x, pad_y + 2, 15, bold=True, color=INK_BLACK)

        # Header underline
        line_y = pad_y + 34
        cr.set_source_rgb(*INK_DIVIDER)
        cr.set_line_width(1.0)
        cr.move_to(pad_x, line_y)
        cr.line_to(w - pad_x, line_y)
        cr.stroke()

        if not items:
            draw_pango_text(cr, "今日无待办或全部已搞定", pad_x, line_y + 40, 16, bold=False, color=INK_BLACK)
            return

        # Dynamic capacity and row flow based on slot height
        bar_y = h - 24
        available_h = bar_y - line_y - 20
        is_quadrant = (slot_type in ("quadrant", "compact") or h < 320)

        if is_quadrant:
            max_items = 4
            font_sz = 15
            box_sz = 18
            row_gap = 14
            min_step = 40
        else:
            max_items = 7
            font_sz = 16
            box_sz = 19
            row_gap = 22
            min_step = int(max(52, min(74, available_h / max(1, min(len(items), max_items)))))

        display_items = items[:max_items]
        cur_y = line_y + 14

        for i, it in enumerate(display_items):
            if cur_y + box_sz > bar_y - 10:
                break

            done = it.get("done", False)
            text = it.get("text", "")
            seq_num = i + 1

            # Crisp vector checkbox with centered checkmark
            draw_checkbox(cr, pad_x, cur_y + 2, size=box_sz, checked=done)

            # Task text with per-line ink-width strikethrough and dynamic height measurement
            text_x = pad_x + box_sz + 12
            max_text_w = w - text_x - pad_x

            _, th = draw_task_text(
                cr, f"{seq_num}. {text}",
                text_x, cur_y,
                font_size=font_sz - 1 if done else font_sz,
                max_width=max_text_w,
                done=done,
                color=INK_BLACK
            )

            # Advance cur_y dynamically based on actual wrapped height so multi-line rows never crowd
            cur_y += max(min_step, int(th + row_gap))

        # Bottom Progress Bar
        bar_w = w - pad_x * 2
        bar_h = 8
        draw_rounded_rect(cr, pad_x, bar_y, bar_w, bar_h, 4)
        cr.set_source_rgb(*INK_TRACK_GRAY)
        cr.fill_preserve()
        cr.set_source_rgb(*INK_BLACK)
        cr.set_line_width(1.0)
        cr.stroke()

        if total > 0 and done_cnt > 0:
            fill_w = max(6, int(bar_w * (done_cnt / total)))
            draw_rounded_rect(cr, pad_x, bar_y, fill_w, bar_h, 4)
            cr.set_source_rgb(*INK_BLACK)
            cr.fill()

