"""
OpenInk 24-Hour Time-Slot Scheduler & E-Ink Lifespan Protection (DND) Engine.

Supports:
- Custom time-slot rules (`HH:MM` ~ `HH:MM`, including cross-midnight ranges like `23:00` ~ `07:30`).
- Per-slot page filtering (`pages: ["page_1", ...]`) and custom carousel intervals.
- `sleep_dnd` mode: suppresses routine screen refreshes and page flipping during sleep hours
  to prevent unnecessary E-Ink microcapsule wear, while allowing midnight data rollover in memory
  and optional emergency alert override.
"""

import datetime
import re
from typing import Dict, Any, List, Optional, Tuple
from config import normalize_dashboard_pages

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

DEFAULT_SCHEDULE: Dict[str, Any] = {
    "enabled": True,
    "active_interval_sec": 1800,
    "rules": [
        {
            "id": "morning",
            "name": "晨间晨会与气象",
            "start": "07:30",
            "end": "12:00",
            "mode": "carousel",
            "pages": ["page_1"],
            "carousel_interval_sec": 60,
        },
        {
            "id": "work",
            "name": "日间工作与待办",
            "start": "12:00",
            "end": "18:30",
            "mode": "carousel",
            "pages": ["page_1", "page_2"],
            "carousel_interval_sec": 60,
        },
        {
            "id": "evening",
            "name": "晚间日程与倒数",
            "start": "18:30",
            "end": "23:00",
            "mode": "carousel",
            "pages": ["page_2"],
            "carousel_interval_sec": 60,
        },
        {
            "id": "night_sleep",
            "name": "夜间休眠免打扰",
            "start": "23:00",
            "end": "07:30",
            "mode": "sleep_dnd",
            "pages": [],
            "allow_alert_override": True,
        },
    ],
}


def parse_hm(hm_str: str) -> Optional[datetime.time]:
    """Parses 'HH:MM' into datetime.time, or None if invalid."""
    s = (hm_str or "").strip()
    m = _TIME_RE.match(s)
    if not m:
        return None
    return datetime.time(int(m.group(1)), int(m.group(2)))


def is_time_in_range(now_t: datetime.time, start_t: datetime.time, end_t: datetime.time) -> bool:
    """
    Checks if `now_t` falls within `[start_t, end_t)`.
    Supports cross-midnight ranges such as `23:00` ~ `07:30`.
    """
    if start_t == end_t:
        return True
    if start_t < end_t:
        return start_t <= now_t < end_t
    return now_t >= start_t or now_t < end_t


def normalize_schedule_config(raw_schedule: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Validates and normalizes the `schedule` section of config.json."""
    if not isinstance(raw_schedule, dict):
        return dict(DEFAULT_SCHEDULE)

    enabled = bool(raw_schedule.get("enabled", True))
    try:
        active_interval_sec = max(60, min(int(raw_schedule.get("active_interval_sec", 1800)), 86400))
    except (ValueError, TypeError):
        active_interval_sec = 1800

    raw_rules = raw_schedule.get("rules")
    if not isinstance(raw_rules, list):
        raw_rules = DEFAULT_SCHEDULE["rules"]

    clean_rules: List[Dict[str, Any]] = []
    for idx, r in enumerate(raw_rules[:24]):
        if not isinstance(r, dict):
            continue
        start_str = (r.get("start") or "08:00").strip()
        end_str = (r.get("end") or "22:00").strip()
        if not parse_hm(start_str) or not parse_hm(end_str):
            continue
        mode = r.get("mode") if r.get("mode") in ("carousel", "manual", "sleep_dnd") else "carousel"
        pages = r.get("pages") if isinstance(r.get("pages"), list) else []
        pages = [str(p).strip() for p in pages if str(p).strip()]
        try:
            c_int = max(10, min(int(r.get("carousel_interval_sec", 60)), 86400))
        except (ValueError, TypeError):
            c_int = 60

        clean_rules.append({
            "id": (r.get("id") or f"rule_{idx + 1}").strip(),
            "name": (r.get("name") or f"时段 {idx + 1}").strip(),
            "start": start_str,
            "end": end_str,
            "mode": mode,
            "pages": pages,
            "carousel_interval_sec": c_int,
            "allow_alert_override": bool(r.get("allow_alert_override", True)),
        })

    return {
        "enabled": enabled,
        "active_interval_sec": active_interval_sec,
        "rules": clean_rules,
    }


def get_active_rule(schedule_cfg: Dict[str, Any], now: Optional[datetime.datetime] = None) -> Optional[Dict[str, Any]]:
    """Returns the first matching rule for `now`, or None if schedule is disabled or no rule matches."""
    norm = normalize_schedule_config(schedule_cfg)
    if not norm["enabled"]:
        return None
    if now is None:
        now = datetime.datetime.now()
    now_t = now.time()

    for rule in norm["rules"]:
        st = parse_hm(rule["start"])
        et = parse_hm(rule["end"])
        if st and et and is_time_in_range(now_t, st, et):
            return rule
    return None


def filter_pages_for_rule(all_pages: List[Dict[str, Any]], rule: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filters `all_pages` according to `rule['pages']`.
    Falls back to `all_pages` if rule has no page restriction or if no page IDs match.
    """
    if not rule or not rule.get("pages"):
        return all_pages
    wanted = set(rule["pages"])
    filtered = [p for p in all_pages if p.get("id") in wanted]
    return filtered if filtered else all_pages


def calc_seconds_until_next_boundary(schedule_cfg: Dict[str, Any], now: Optional[datetime.datetime] = None) -> int:
    """
    Calculates seconds from `now` until the next schedule boundary:
    - Next midnight `00:00:01` (daily calendar/lunar/countdown rollover)
    - Start or end time of any configured rule
    """
    if now is None:
        now = datetime.datetime.now()

    tomorrow = now.date() + datetime.timedelta(days=1)
    midnight_dt = datetime.datetime.combine(tomorrow, datetime.time(0, 0, 1))
    min_sec = max(1.0, (midnight_dt - now).total_seconds())

    norm = normalize_schedule_config(schedule_cfg)
    if norm["enabled"]:
        for rule in norm["rules"]:
            for hm_str in (rule.get("start"), rule.get("end")):
                t_obj = parse_hm(hm_str or "")
                if not t_obj:
                    continue
                candidate = datetime.datetime.combine(now.date(), t_obj)
                if candidate <= now:
                    candidate = datetime.datetime.combine(tomorrow, t_obj)
                delta = (candidate - now).total_seconds()
                if 0 < delta < min_sec:
                    min_sec = delta

    return max(1, int(min_sec) + 1)


def evaluate_schedule(cfg: Dict[str, Any], now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """
    Evaluates the full effective display state at `now` given global `cfg`.
    """
    if now is None:
        now = datetime.datetime.now()

    dash = cfg.get("dashboard", {})
    all_pages = normalize_dashboard_pages(cfg)
    sched = normalize_schedule_config(cfg.get("schedule"))
    rule = get_active_rule(sched, now=now)
    next_boundary_sec = calc_seconds_until_next_boundary(sched, now=now)

    if rule is None:
        mode = dash.get("mode", "carousel")
        interval = int(dash.get("carousel_interval_sec", 60))
        return {
            "schedule_enabled": sched["enabled"],
            "active_interval_sec": sched["active_interval_sec"],
            "active_rule": None,
            "rule_id": "default",
            "rule_name": "全天常规模式" if not sched["enabled"] else "未命中时段 (默认轮播)",
            "window": "00:00 ~ 24:00",
            "mode": mode,
            "is_dnd": False,
            "allow_alert_override": True,
            "carousel_interval_sec": interval,
            "active_pages": all_pages,
            "next_boundary_sec": next_boundary_sec,
        }

    mode = rule["mode"]
    is_dnd = (mode == "sleep_dnd")
    active_pages = filter_pages_for_rule(all_pages, rule)
    interval = int(rule.get("carousel_interval_sec") or dash.get("carousel_interval_sec", 60))

    return {
        "schedule_enabled": True,
        "active_interval_sec": sched["active_interval_sec"],
        "active_rule": rule,
        "rule_id": rule["id"],
        "rule_name": rule["name"],
        "window": f"{rule['start']} ~ {rule['end']}",
        "mode": mode,
        "is_dnd": is_dnd,
        "allow_alert_override": bool(rule.get("allow_alert_override", True)),
        "carousel_interval_sec": interval,
        "active_pages": active_pages,
        "next_boundary_sec": next_boundary_sec,
    }
