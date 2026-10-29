"""
统一配置加载与持久化模块 (v1.1 - 支持外部数据源插件与多页动态复用).

config.json 为唯一配置来源；敏感凭据通过环境变量注入（HA_TOKEN / N516_PASSWORD）。
"""

import os
import json
from typing import Dict, Any, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "city": "Beijing",
    "dashboard": {
        "mode": "carousel",
        "carousel_interval_sec": 60,
        "template": "2_1",
        "slots": {
            "top_left": "calendar",
            "bottom_left": "weather",
            "right": "todo"
        },
        "pages": [
            {
                "id": "page_1",
                "title": "第 1 页 · 主看板",
                "template": "2_1",
                "slots": {
                    "top_left": "calendar",
                    "bottom_left": "weather",
                    "right": "todo"
                }
            }
        ]
    },
    "plugins": {
        "agenda": {
            "enabled": True,
            "ics_urls": [],
            "items": [
                {
                    "title": "OpenInk v1.1 里程碑发布",
                    "date": "+6",
                    "time": "全天",
                    "is_countdown": True
                },
                {
                    "title": "架构评审与墨水屏实机联调",
                    "date": "+0",
                    "time": "15:00",
                    "is_countdown": False
                },
                {
                    "title": "外部 ICS 日历同步功能验收",
                    "date": "+1",
                    "time": "10:30",
                    "is_countdown": False
                },
                {
                    "title": "家庭周末出行计划",
                    "date": "+4",
                    "time": "09:00",
                    "is_countdown": False
                },
                {
                    "title": "每月固定账单与发薪日",
                    "date": "+12",
                    "time": "全天",
                    "is_countdown": True
                }
            ]
        },
        "sensors": {
            "enabled": True
        }
    },
    "device": {
        "host": "192.168.111.1",
        "port": 22,
        "user": "root",
        "password_env": "OPENINK_DEVICE_PASSWORD",
        "ssh_alias": "eink",
        "dashboard_dir": "/tmp/dashboard",
        "rotation": 90
    },
    "todos_file": "todos.txt",
    "font_family": "WenQuanYi Micro Hei, Segoe UI Emoji, Maple Mono NF CN, Noto Color Emoji, Segoe UI Symbol, sans-serif",
    "card_shadow": True,
    "shadow_offset": 5,
    "shadow_gray": 0.42,
    "homeassistant": {
        "url": "",
        "token_env": "HA_TOKEN",
        "sensors": []
    }
}


def _merge(base: dict, override: dict) -> dict:
    """浅层 dict 递归合并，override 优先。"""
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def normalize_dashboard_pages(cfg: dict) -> List[Dict[str, Any]]:
    """
    Ensures `dashboard.pages` is always a non-empty list of `{id, title, template, slots}`.
    If only legacy `dashboard.template` / `dashboard.slots` exist, migrates them to `pages[0]`.
    """
    dash = cfg.get("dashboard", {})
    pages = dash.get("pages")
    if isinstance(pages, list) and len(pages) > 0:
        normalized = []
        for idx, p in enumerate(pages):
            normalized.append({
                "id": p.get("id") or f"page_{idx + 1}",
                "title": p.get("title") or f"第 {idx + 1} 页",
                "template": p.get("template") or "2_1",
                "slots": dict(p.get("slots") or {"top_left": "calendar", "bottom_left": "weather", "right": "todo"})
            })
        return normalized

    tpl = dash.get("template", "2_1")
    slots = dash.get("slots", {"top_left": "calendar", "bottom_left": "weather", "right": "todo"})
    return [
        {
            "id": "page_1",
            "title": "第 1 页 · 主看板",
            "template": tpl,
            "slots": dict(slots)
        }
    ]


def load_config() -> dict:
    """读取 config.json 并与默认值合并。文件缺失或损坏时回退默认值。"""
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = _merge(DEFAULT_CONFIG, json.load(f))
        except Exception as e:
            print(f"[Config Warning] 读取 config.json 失败: {e}，使用默认配置")
    cfg.setdefault("dashboard", {})["pages"] = normalize_dashboard_pages(cfg)
    return cfg


def save_config(updates: dict) -> dict:
    """将更新项合并写入 config.json 并返回最新配置（绝不写入明文密钥）。"""
    current = load_config()
    merged = _merge(current, updates)
    # Keep pages[0] and legacy template/slots synced
    if "dashboard" in merged:
        pages = normalize_dashboard_pages(merged)
        merged["dashboard"]["pages"] = pages
        merged["dashboard"]["template"] = pages[0]["template"]
        merged["dashboard"]["slots"] = pages[0]["slots"]
    # 确保不落盘明文凭据
    if "homeassistant" in merged:
        merged["homeassistant"].pop("token", None)
    if "device" in merged:
        merged["device"].pop("password", None)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    return merged


def get_secret(section: dict, key: str = "token") -> str:
    """
    按 config 中的 `{key}_env` 变量名从环境变量读取密钥。
    未设置时返回空串。
    """
    env_name = section.get(f"{key}_env")
    if not env_name:
        return section.get(key, "")
    return os.environ.get(env_name, "")
