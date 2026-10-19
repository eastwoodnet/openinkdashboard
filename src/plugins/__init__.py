"""
OpenInk Dynamic External Data Source Plugin Manager.

Architectural Boundary:
- Built-in Core Data Sources (Always loaded):
  - `calendar`: 本地公历、农历干支生肖、二十四节气
  - `weather`: 城市实时气象与趋势预报
  - `todo`: 本地待办事项清单
  - `focus` / `alert`: 全屏综合焦点画报与即时大字通知

- External Plugin Data Sources (Loaded ONLY when `plugins.<id>.enabled == True`):
  - `agenda`: 外部日历同步与重要纪念日倒数 (ICS 订阅)
  - `sensors`: Home Assistant 智能家居环境传感器
"""

from typing import Dict, Any, List
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


def _fetch_sensors_plugin(cfg: Dict[str, Any]) -> List[Dict[str, str]]:
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
        {"id": "sensor.workroom_temperature", "name": "工作间温度", "display": "22.4 °C"},
        {"id": "sensor.workroom_humidity", "name": "工作间湿度", "display": "48.2 %"},
        {"id": "sensor.kids_room_temperature", "name": "儿童房温度", "display": "23.1 °C"},
        {"id": "sensor.kids_room_humidity", "name": "儿童房湿度", "display": "50.5 %"},
        {"id": "sensor.zhi_neng_yao_kong_temperature", "name": "遥控器温度", "display": "21.8 °C"},
    ]
    default_map = {d["name"]: d["display"] for d in defaults}
    fallback = []
    for s in (sensor_cfgs or defaults):
        name = s.get("name", "传感器")
        disp = s.get("display") or default_map.get(name, "22.0 °C")
        fallback.append({"id": s.get("id", ""), "name": name, "display": disp})
    return fallback


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
    plugins_cfg = cfg.get("plugins", {})
    enabled_ids = get_enabled_plugin_ids(cfg)
    plugin_ctx: Dict[str, Any] = {}

    if "agenda" in enabled_ids:
        agenda_cfg = plugins_cfg.get("agenda", {})
        plugin_ctx["agenda"] = fetch_agenda_data(agenda_cfg, force_refresh=force_refresh)

    if "sensors" in enabled_ids:
        plugin_ctx["sensors"] = _fetch_sensors_plugin(cfg)

    return plugin_ctx
