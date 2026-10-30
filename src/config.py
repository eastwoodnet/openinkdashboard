"""
统一配置加载、持久化与安全脱敏模块 (v1.2).

- 本地 `config.json` 已被 `.gitignore` 隔离，绝不入库；
- 仓库仅保留脱敏模板 `config.example.json`；
- 敏感凭据一律通过环境变量注入（HA_TOKEN / N516_PASSWORD / OPENINK_API_TOKEN），严禁明文落盘。
"""

import os
import json
import urllib.parse
from typing import Dict, Any, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
EXAMPLE_CONFIG_PATH = os.path.join(BASE_DIR, "config.example.json")

SENSITIVE_KEYS = {"token", "password", "secret", "api_key", "private_key", "access_token"}

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
                    "title": "OpenInk 里程碑发布",
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


def _strip_plaintext_secrets(obj: Any) -> Any:
    """递归剥离任何字典中的明文密钥字段，防止意外写入磁盘。"""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            if k.lower() in SENSITIVE_KEYS:
                continue
            cleaned[k] = _strip_plaintext_secrets(v)
        return cleaned
    elif isinstance(obj, list):
        return [_strip_plaintext_secrets(item) for item in obj]
    return obj


def sanitize_for_client(obj: Any) -> Any:
    """对返回给前端 API 的配置数据进行递归脱敏掩码。"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in SENSITIVE_KEYS and isinstance(v, str) and v:
                out[k] = "***"
            else:
                out[k] = sanitize_for_client(v)
        return out
    elif isinstance(obj, list):
        return [sanitize_for_client(item) for item in obj]
    return obj


def mask_url_for_log(url: str) -> str:
    """日志输出时隐藏 URL 路径与查询参数中的敏感 Token。"""
    try:
        parsed = urllib.parse.urlsplit(url.strip())
        if parsed.scheme and parsed.netloc:
            host = parsed.hostname or parsed.netloc
            return f"{parsed.scheme}://{host}/***"
    except Exception:
        pass
    return "<masked-url>"


def validate_external_url(raw_url: str, allow_private_lan: bool = False) -> str:
    """
    校验外部请求 URL 协议与目标地址，防范 SSRF 与非法协议读取。
    - 仅允许 http://, https://, webcal://（自动转为 https://）；
    - 默认拦截回环地址与云元数据地址（127.0.0.0/8, localhost, 169.254.169.254）。
    """
    clean = (raw_url or "").strip()
    if not clean:
        return ""
    if clean.startswith("webcal://"):
        clean = "https://" + clean[len("webcal://"):]
    parsed = urllib.parse.urlsplit(clean)
    if parsed.scheme not in ("http", "https"):
        return ""
    host = (parsed.hostname or "").lower()
    if not host:
        return ""
    blocked_hosts = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "169.254.169.254", "metadata.google.internal"}
    if not allow_private_lan and (host in blocked_hosts or host.startswith("127.") or host.startswith("169.254.")):
        return ""
    return clean


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
    """读取 config.json 并与默认值合并。文件缺失时回退 config.example.json 或默认配置。"""
    cfg = dict(DEFAULT_CONFIG)
    source_path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else (
        EXAMPLE_CONFIG_PATH if os.path.exists(EXAMPLE_CONFIG_PATH) else None
    )
    if source_path:
        try:
            with open(source_path, "r", encoding="utf-8") as f:
                cfg = _merge(DEFAULT_CONFIG, json.load(f))
        except Exception as e:
            print(f"[Config Warning] 读取配置文件失败: {e}，使用默认配置")
    cfg.setdefault("dashboard", {})["pages"] = normalize_dashboard_pages(cfg)
    return cfg


def save_config(updates: dict) -> dict:
    """将更新项合并写入 config.json 并返回最新配置（递归剥离任何明文密钥）。"""
    current = load_config()
    merged = _merge(current, updates)
    if "dashboard" in merged:
        pages = normalize_dashboard_pages(merged)
        merged["dashboard"]["pages"] = pages
        merged["dashboard"]["template"] = pages[0]["template"]
        merged["dashboard"]["slots"] = pages[0]["slots"]
    merged = _strip_plaintext_secrets(merged)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
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
