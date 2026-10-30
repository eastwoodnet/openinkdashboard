"""
P0 External Data Source Plugin: ICS Calendar Sync & Countdowns (agenda).
Supports:
- Standard RFC 5545 iCalendar (.ics) URL subscription (iCloud, Google, Feishu, DingTalk, Outlook, Nextcloud).
- Automatic webcal:// to https:// conversion and local TTL caching.
- Recurring event expansion (FREQ=YEARLY, MONTHLY, WEEKLY, DAILY).
- Custom user-configured schedule items and countdown milestones.
- Provides `event_dates_in_month` for CalendarWidget dot markers.
"""

import datetime
import os
import re
import time
import urllib.request
from typing import Dict, Any, List, Optional, Set, Tuple
from config import validate_external_url, mask_url_for_log

_ics_cache: Dict[str, Tuple[float, str]] = {}
ICS_CACHE_TTL = 900  # 15 minutes cache for remote ICS URLs
MAX_ICS_BYTES = 2 * 1024 * 1024  # 2MB safety cap


def _unfold_ics_lines(raw_text: str) -> List[str]:
    """Unfolds RFC 5545 folded lines (lines starting with space or tab)."""
    unfolded: List[str] = []
    for raw_line in raw_text.splitlines():
        if raw_line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += raw_line[1:]
        else:
            unfolded.append(raw_line.strip())
    return unfolded


def _parse_ics_datetime(prop_key: str, prop_val: str) -> Tuple[Optional[datetime.date], Optional[str], bool]:
    """
    Parses DTSTART/DTEND value into (date_obj, time_str_HH_MM, is_all_day).
    Supports:
    - 20261019
    - 20261019T143000
    - 20261019T063000Z (converted to local UTC+8)
    """
    val = prop_val.strip()
    is_all_day = ("VALUE=DATE" in prop_key.upper() and "VALUE=DATE-TIME" not in prop_key.upper()) or len(val) == 8

    try:
        if len(val) == 8 and val.isdigit():
            d = datetime.datetime.strptime(val, "%Y%m%d").date()
            return d, None, True

        # Match YYYYMMDDTHHMMSS(Z)
        m = re.match(r"^(\d{8})T(\d{4,6})(Z?)$", val)
        if m:
            d_part, t_part, z_flag = m.group(1), m.group(2)[:4], m.group(3)
            dt = datetime.datetime.strptime(d_part + t_part, "%Y%m%d%H%M")
            if z_flag == "Z":
                # Convert UTC to local time (UTC+8)
                dt = dt + datetime.timedelta(hours=8)
            return dt.date(), dt.strftime("%H:%M"), is_all_day
    except Exception:
        pass

    return None, None, True


def _apply_rrule_to_today(
    start_date: datetime.date,
    rrule_str: str,
    today: datetime.date,
    horizon_days: int = 60
) -> List[datetime.date]:
    """Expands simple RRULE (YEARLY, MONTHLY, WEEKLY, DAILY) into upcoming dates within [today, today + horizon_days]."""
    results: List[datetime.date] = []
    rule_upper = rrule_str.upper()

    # Check UNTIL bound if present
    until_m = re.search(r"UNTIL=(\d{8})", rule_upper)
    if until_m:
        try:
            until_date = datetime.datetime.strptime(until_m.group(1), "%Y%m%d").date()
            if until_date < today:
                return []
        except Exception:
            pass

    end_window = today + datetime.timedelta(days=horizon_days)

    if "FREQ=YEARLY" in rule_upper:
        for yr in (today.year, today.year + 1):
            try:
                candidate = datetime.date(yr, start_date.month, start_date.day)
                if today <= candidate <= end_window:
                    results.append(candidate)
            except ValueError:
                pass
    elif "FREQ=MONTHLY" in rule_upper:
        for offset in range(0, 3):
            yr = today.year + (today.month + offset - 1) // 12
            mo = (today.month + offset - 1) % 12 + 1
            try:
                candidate = datetime.date(yr, mo, start_date.day)
                if today <= candidate <= end_window:
                    results.append(candidate)
            except ValueError:
                pass
    elif "FREQ=WEEKLY" in rule_upper:
        delta_days = (start_date.weekday() - today.weekday()) % 7
        first = today + datetime.timedelta(days=delta_days)
        cur = first
        while cur <= end_window:
            if cur >= start_date:
                results.append(cur)
            cur += datetime.timedelta(days=7)
    elif "FREQ=DAILY" in rule_upper:
        for d_off in range(0, min(14, horizon_days + 1)):
            cur = today + datetime.timedelta(days=d_off)
            if cur >= start_date:
                results.append(cur)

    return results


def parse_ics_content(raw_ics: str, today: Optional[datetime.date] = None, horizon_days: int = 60) -> List[Dict[str, Any]]:
    """
    Parses raw .ics content and returns normalized event dicts within [month_start, today + horizon_days].
    """
    if today is None:
        today = datetime.date.today()

    month_start = datetime.date(today.year, today.month, 1)
    window_end = today + datetime.timedelta(days=horizon_days)

    lines = _unfold_ics_lines(raw_ics)
    events: List[Dict[str, Any]] = []

    in_event = False
    cur_props: Dict[str, Tuple[str, str]] = {}

    for line in lines:
        if line == "BEGIN:VEVENT":
            in_event = True
            cur_props = {}
        elif line == "END:VEVENT":
            in_event = False
            dt_info = cur_props.get("DTSTART")
            summary_info = cur_props.get("SUMMARY")
            if dt_info and summary_info:
                start_date, time_str, is_all_day = _parse_ics_datetime(dt_info[0], dt_info[1])
                title = summary_info[1].replace("\\,", ",").replace("\\;", ";").replace("\\n", " ").strip()
                rrule_info = cur_props.get("RRULE")

                if start_date and title:
                    candidate_dates: List[datetime.date] = []
                    if rrule_info:
                        candidate_dates = _apply_rrule_to_today(start_date, rrule_info[1], month_start, horizon_days + 31)
                    elif month_start <= start_date <= window_end:
                        candidate_dates = [start_date]

                    for c_date in candidate_dates:
                        days_away = (c_date - today).days
                        events.append({
                            "title": title,
                            "date": c_date.strftime("%Y-%m-%d"),
                            "month": c_date.month,
                            "day": c_date.day,
                            "time": time_str or "全天",
                            "is_all_day": is_all_day,
                            "days_away": days_away,
                            "source": "ics"
                        })
        elif in_event and ":" in line:
            k_part, v_part = line.split(":", 1)
            base_key = k_part.split(";", 1)[0].upper()
            cur_props[base_key] = (k_part, v_part)

    return events


def _fetch_ics_url(url: str, force_refresh: bool = False) -> str:
    """Fetches an .ics URL (or local file path) with TTL caching."""
    clean_url = url.strip()
    if not clean_url:
        return ""
    if clean_url.startswith("webcal://"):
        clean_url = "https://" + clean_url[len("webcal://"):]

    now = time.time()
    if not force_refresh and clean_url in _ics_cache:
        ts, cached_body = _ics_cache[clean_url]
        if now - ts < ICS_CACHE_TTL:
            return cached_body

    try:
        if clean_url.startswith(("http://", "https://")):
            safe_url = validate_external_url(clean_url)
            if not safe_url:
                print(f"[ICS Plugin Warning] Blocked unsafe or invalid URL: {mask_url_for_log(clean_url)}")
                return ""
            req = urllib.request.Request(
                safe_url,
                headers={"User-Agent": "OpenInk-CalendarSync/1.2"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read(MAX_ICS_BYTES).decode("utf-8", errors="replace")
        elif clean_url.endswith(".ics") and os.path.isfile(clean_url) and not os.path.islink(clean_url):
            with open(clean_url, "r", encoding="utf-8") as f:
                body = f.read(MAX_ICS_BYTES)
        else:
            return ""
        _ics_cache[clean_url] = (now, body)
        return body
    except Exception as e:
        print(f"[ICS Plugin Warning] Failed to fetch {mask_url_for_log(clean_url)}: {type(e).__name__}")
        if clean_url in _ics_cache:
            return _ics_cache[clean_url][1]
        return ""


def _format_day_badge(days_away: int, date_str: str) -> str:
    if days_away == 0:
        return "今天"
    elif days_away == 1:
        return "明天"
    elif days_away == 2:
        return "后天"
    elif 0 < days_away <= 7:
        return f"{days_away}天后"
    else:
        return date_str[5:]  # MM-DD


def fetch_agenda_data(plugin_cfg: Dict[str, Any], today: Optional[datetime.date] = None, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Aggregates events from configured .ics URLs and custom agenda/countdown items.
    Returns structured dict for AgendaWidget and CalendarWidget dot markers:
    {
      "events": [...],         # Upcoming chronological agenda items (days_away >= 0)
      "countdowns": [...],     # Highlighted milestone countdowns
      "event_dates_in_month": [int, ...], # Day numbers in current month that have events
      "total_upcoming": int,
      "ics_count": int
    }
    """
    if today is None:
        today = datetime.date.today()

    ics_urls: List[str] = plugin_cfg.get("ics_urls", [])
    if isinstance(ics_urls, str):
        ics_urls = [u.strip() for u in ics_urls.splitlines() if u.strip()]

    custom_items: List[Dict[str, Any]] = plugin_cfg.get("items", [])

    all_events: List[Dict[str, Any]] = []

    # 1. Parse remote/local .ics feeds
    for url in ics_urls:
        raw_ics = _fetch_ics_url(url, force_refresh=force_refresh)
        if raw_ics:
            all_events.extend(parse_ics_content(raw_ics, today=today))

    # 2. Parse custom configured schedule & countdown items
    for item in custom_items:
        title = (item.get("title") or "").strip()
        date_str = (item.get("date") or "").strip()
        time_str = (item.get("time") or "全天").strip()
        is_countdown = bool(item.get("is_countdown", False))
        if not title:
            continue

        target_date: Optional[datetime.date] = None
        # Support YYYY-MM-DD or MM-DD (recurring yearly) or relative "+N"
        if re.match(r"^\+\d+$", date_str):
            target_date = today + datetime.timedelta(days=int(date_str[1:]))
        elif re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            try:
                target_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        elif re.match(r"^\d{2}-\d{2}$", date_str):
            try:
                mo, da = map(int, date_str.split("-"))
                candidate = datetime.date(today.year, mo, da)
                if candidate < today:
                    candidate = datetime.date(today.year + 1, mo, da)
                target_date = candidate
            except ValueError:
                pass

        if target_date is None:
            target_date = today

        days_away = (target_date - today).days
        all_events.append({
            "title": title,
            "date": target_date.strftime("%Y-%m-%d"),
            "month": target_date.month,
            "day": target_date.day,
            "time": time_str if time_str else "全天",
            "is_all_day": (time_str in ("", "全天")),
            "is_countdown": is_countdown,
            "days_away": days_away,
            "source": "custom"
        })

    # Collect all event days in the current calendar month for CalendarWidget dots
    event_dates_in_month: Set[int] = set()
    for ev in all_events:
        if ev.get("date", "").startswith(today.strftime("%Y-%m-")):
            event_dates_in_month.add(ev["day"])

    # Filter upcoming events (days_away >= 0) and sort chronologically
    upcoming = [ev for ev in all_events if ev["days_away"] >= 0]
    upcoming.sort(key=lambda e: (e["days_away"], "00:00" if e["time"] == "全天" else e["time"]))

    for ev in upcoming:
        ev["day_badge"] = _format_day_badge(ev["days_away"], ev["date"])

    # Extract countdown highlights (explicitly marked `is_countdown` or all-day events within 90 days)
    countdowns = [ev for ev in upcoming if ev.get("is_countdown") or (ev["is_all_day"] and ev["days_away"] > 0)]
    if not countdowns:
        countdowns = upcoming[:2]

    return {
        "events": upcoming,
        "countdowns": countdowns[:4],
        "event_dates_in_month": sorted(event_dates_in_month),
        "total_upcoming": len(upcoming),
        "ics_count": len([u for u in ics_urls if u.strip()])
    }
