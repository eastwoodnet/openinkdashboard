"""
OpenInk Startup-Time External Plugin Manager (v1.2).

Architectural Design:
- Zero Runtime Polling Overhead: Plugins are discovered ONCE at service startup (`discover_plugins()`).
  Adding or updating a plugin bundle only requires a service restart (`systemctl restart openink`).
- Built-in Core Data Sources (Always loaded):
  - `calendar`: 本地公历、农历干支生肖、二十四节气
  - `weather`: 城市实时气象与趋势预报
  - `todo`: 本地待办事项清单
  - `focus` / `alert`: 全屏综合焦点画报与即时大字通知
- External Plugin Data Sources (Executed ONLY when `plugins.<id>.enabled == True`):
  - `agenda`: 外部日历同步与重要纪念日倒数 (ICS 订阅)
  - `sensors`: Home Assistant 智能家居环境传感器
  - Custom plugins in `src/plugins/<plugin_id>/` (containing `manifest.json` + `plugin.py`)
"""

import os
import json
import importlib.util
from typing import Dict, Any, List, Callable, Optional
from config import get_secret
from plugins.homeassistant import HomeAssistantClient
from plugins.ics_agenda import fetch_agenda_data

PLUGIN_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "agenda",
        "tier": "P0",
        "name": "📆 外部日历同步与倒数日 (ICS)",
        "short_name": "日程与倒数",
        "description": "支持 iCloud / Google / 飞书 .ics 日历订阅与纪念日倒计时，自动联动月历打点",
        "implemented": True,
        "slot_options": {
            "quadrant": {"id": "agenda", "name": "📆 外部日程与倒数 (Plugin)", "desc": "重点倒数日胶囊 + 近期 3 项 ICS 日程"},
            "half_v":   {"id": "agenda", "name": "📆 外部日程时间轴 (Plugin)", "desc": "2 项里程碑倒计时 + 6 项近期日程时间轴"},
            "full":     {"id": "agenda", "name": "📆 全屏日程与倒数日 (Plugin)", "desc": "780×580 全宽展示里程碑倒计时与日程时间轴"}
        }
    },
    {
        "id": "sensors",
        "tier": "EXT",
        "name": "🌡️ Home Assistant 环境监控",
        "short_name": "环境传感器",
        "description": "拉取 Home Assistant 温湿度与传感器状态，支持自定义房间指标",
        "implemented": True,
        "slot_options": {
            "quadrant": {"id": "sensors", "name": "🌡️ 室内环境指标 (Plugin)", "desc": "Home Assistant 4 项温湿度虚线双栏"},
            "half_v":   {"id": "sensors", "name": "🌡️ 全屋环境监控 (Plugin)", "desc": "Home Assistant 最多 8 项房间温湿度卡"},
            "full":     {"id": "sensors", "name": "🌡️ 全屏全屋环境监控 (Plugin)", "desc": "780×580 全宽展示 HA 各房间温湿度卡片"}
        }
    }
]


def _fetch_agenda_plugin(cfg: Dict[str, Any], force_refresh: bool = False) -> Dict[str, Any]:
    agenda_cfg = cfg.get("plugins", {}).get("agenda", {})
    return fetch_agenda_data(agenda_cfg, force_refresh=force_refresh)


def _fetch_sensors_plugin(cfg: Dict[str, Any], force_refresh: bool = False) -> List[Dict[str, str]]:
    """Fetches Home Assistant sensor data when the `sensors` plugin is enabled."""
    plugins_cfg = cfg.get("plugins", {})
    sensors_plugin = plugins_cfg.get("sensors", {})
    ha_cfg = cfg.get("homeassistant", {})

    sensor_cfgs = sensors_plugin.get("items") or ha_cfg.get("sensors", [])
    token = get_secret(ha_cfg, "token")
    if ha_cfg.get("url") and token and sensor_cfgs:
        ha = HomeAssistantClient(ha_cfg["url"], token)
        data = ha.get_sensors_data(sensor_cfgs)
        if data and any(d.get("display") not in ("--", "", None) for d in data):
            return data

    defaults = [
        {"id": "sensor.living_room_temperature", "name": "客厅温度", "display": "22.4 °C"},
        {"id": "sensor.living_room_humidity", "name": "客厅湿度", "display": "48.2 %"},
    ]
    default_map = {d["name"]: d["display"] for d in defaults}
    fallback = []
    for s in (sensor_cfgs or defaults):
        name = s.get("name", "传感器")
        disp = s.get("display") or default_map.get(name, "22.0 °C")
        fallback.append({"id": s.get("id", ""), "name": name, "display": disp})
    return fallback


PLUGIN_COLLECTORS: Dict[str, Callable[[Dict[str, Any], bool], Any]] = {
    "agenda": _fetch_agenda_plugin,
    "sensors": _fetch_sensors_plugin,
}

PLUGIN_WIDGETS: Dict[str, Any] = {}


def register_plugin(
    manifest: Dict[str, Any],
    collector: Optional[Callable[[Dict[str, Any], bool], Any]] = None,
    widget: Optional[Any] = None,
):
    """Registers a plugin's manifest, data collector, and Cairo widget renderer."""
    pid = (manifest.get("id") or "").strip()
    if not pid:
        return
    manifest.setdefault("implemented", True)
    existing_idx = next((i for i, item in enumerate(PLUGIN_CATALOG) if item.get("id") == pid), None)
    if existing_idx is not None:
        PLUGIN_CATALOG[existing_idx] = manifest
    else:
        PLUGIN_CATALOG.append(manifest)

    if collector is not None:
        PLUGIN_COLLECTORS[pid] = collector
    if widget is not None:
        PLUGIN_WIDGETS[pid] = widget


def discover_plugins(plugins_dir: Optional[str] = None) -> List[str]:
    """
    Scans `src/plugins/<plugin_id>/` once at startup for self-contained plugin bundles
    (`manifest.json` + `plugin.py`). Zero background threads or runtime file watchers.
    """
    base_dir = plugins_dir or os.path.dirname(os.path.abspath(__file__))
    discovered: List[str] = []
    if not os.path.isdir(base_dir):
        return discovered

    for entry in sorted(os.listdir(base_dir)):
        if entry.startswith(("_", ".")):
            continue
        sub_dir = os.path.join(base_dir, entry)
        if not os.path.isdir(sub_dir):
            continue
        manifest_path = os.path.join(sub_dir, "manifest.json")
        plugin_py = os.path.join(sub_dir, "plugin.py")
        if not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            pid = manifest.get("id") or entry
            manifest["id"] = pid

            collector_fn = None
            widget_inst = None
            if os.path.isfile(plugin_py):
                spec = importlib.util.spec_from_file_location(f"plugins.{pid}.plugin", plugin_py)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    collector_fn = getattr(mod, "collect", None)
                    widget_cls = getattr(mod, "WIDGET_CLASS", None)
                    widget_inst = getattr(mod, "WIDGET", None) or (widget_cls() if widget_cls else None)

            register_plugin(manifest, collector=collector_fn, widget=widget_inst)
            discovered.append(pid)
        except Exception as e:
            print(f"[Plugin Loader Warning] Skip invalid plugin '{entry}': {e}")

    return discovered


# Run once at startup
discover_plugins()


def get_enabled_plugin_ids(cfg: Dict[str, Any]) -> List[str]:
    """Returns list of currently enabled external plugin IDs."""
    plugins_cfg = cfg.get("plugins", {})
    enabled: List[str] = []
    for item in PLUGIN_CATALOG:
        if not item.get("implemented"):
            continue
        pid = item["id"]
        p_conf = plugins_cfg.get(pid, {})
        if p_conf.get("enabled", False):
            enabled.append(pid)
    return enabled


def load_enabled_plugins_context(cfg: Dict[str, Any], force_refresh: bool = False) -> Dict[str, Any]:
    """
    Dynamically executes collectors ONLY for enabled external plugins.
    Disabled plugins are skipped completely.
    """
    enabled_ids = get_enabled_plugin_ids(cfg)
    plugin_ctx: Dict[str, Any] = {}

    for pid in enabled_ids:
        collector = PLUGIN_COLLECTORS.get(pid)
        if collector:
            try:
                plugin_ctx[pid] = collector(cfg, force_refresh)
            except Exception as e:
                print(f"[Plugin Warning] Collector '{pid}' failed: {type(e).__name__}")

    return plugin_ctx
